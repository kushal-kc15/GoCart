from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from products.models import Category, Product
from .models import Wishlist, WishlistItem

User = get_user_model()


class WishlistTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="asha", email="asha@example.com", password="pass12345"
        )
        self.other = User.objects.create_user(
            username="bob", email="bob@example.com", password="pass12345"
        )
        category = Category.objects.create(name="Fruits", slug="fruits")
        self.apple = Product.objects.create(
            category=category, name="Apple", slug="apple", price=100, stock=10
        )
        self.mango = Product.objects.create(
            category=category, name="Mango", slug="mango", price=200, stock=10
        )
        self.toggle_url = reverse("wishlist:toggle")
        self.page_url = reverse("wishlist:wishlist_detail")

    def _save(self, user, product):
        wishlist, _ = Wishlist.objects.get_or_create(user=user)
        return WishlistItem.objects.create(wishlist=wishlist, product=product)

    def _items(self, user):
        return WishlistItem.objects.filter(wishlist__user=user)


class ToggleTests(WishlistTestBase):
    def test_add(self):
        self.client.force_login(self.user)
        res = self.client.post(
            self.toggle_url, {"product_id": self.apple.id, "action": "add", "next": "/products/"}
        )
        self.assertRedirects(res, "/products/", fetch_redirect_response=False)
        self.assertEqual(list(self._items(self.user).values_list("product", flat=True)), [self.apple.id])

    def test_add_twice_keeps_one_row(self):
        self.client.force_login(self.user)
        for _ in range(2):
            self.client.post(self.toggle_url, {"product_id": self.apple.id, "action": "add"})
        self.assertEqual(self._items(self.user).count(), 1)

    def test_remove(self):
        self._save(self.user, self.apple)
        self.client.force_login(self.user)
        self.client.post(self.toggle_url, {"product_id": self.apple.id, "action": "remove"})
        self.assertFalse(self._items(self.user).exists())

    def test_remove_only_touches_own_wishlist(self):
        self._save(self.other, self.apple)
        self.client.force_login(self.user)
        self.client.post(self.toggle_url, {"product_id": self.apple.id, "action": "remove"})
        self.assertEqual(self._items(self.other).count(), 1)

    def test_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.toggle_url).status_code, 405)

    def test_anonymous_redirects_to_login_keeping_card_anchor(self):
        res = self.client.post(
            self.toggle_url,
            {"product_id": self.apple.id, "action": "add", "next": "/products/?page=2#product-5"},
        )
        # The # is encoded inside next, so it survives the trip through login.
        self.assertEqual(
            res.url,
            reverse("accounts:login") + "?next=%2Fproducts%2F%3Fpage%3D2%23product-5",
        )
        self.assertFalse(Wishlist.objects.exists())

    def test_anonymous_sees_login_message(self):
        res = self.client.post(
            self.toggle_url, {"product_id": self.apple.id, "next": "/products/"}, follow=True
        )
        self.assertContains(res, "Please log in to save items to your wishlist.")


class WishlistPageTests(WishlistTestBase):
    def test_login_required(self):
        res = self.client.get(self.page_url)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/login", res.url)

    def test_lists_only_own_items(self):
        self._save(self.user, self.apple)
        self._save(self.other, self.mango)
        self.client.force_login(self.user)
        res = self.client.get(self.page_url)
        self.assertContains(res, f'id="product-{self.apple.id}"')
        self.assertNotContains(res, f'id="product-{self.mango.id}"')
        self.assertContains(res, 'class="wl-remove"')

    def test_empty_state(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.page_url), "Your wishlist is empty")

    def test_header_badge_count(self):
        self._save(self.user, self.apple)
        self._save(self.user, self.mango)
        self._save(self.other, self.apple)
        self.client.force_login(self.user)
        res = self.client.get(reverse("home"))
        self.assertContains(res, '<span class="cart-badge wishlist-badge">2</span>', html=True)

    def test_no_badge_when_empty(self):
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse("home")), "wishlist-badge")

    def test_profile_links_to_wishlist(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse("accounts:profile"))
        self.assertContains(res, f'href="{self.page_url}"')


class HeartTests(WishlistTestBase):
    def setUp(self):
        super().setUp()
        # Put the products under a department so the list and item pages find them.
        dept = Category.objects.create(name="Food", slug="food")
        Category.objects.filter(slug="fruits").update(parent=dept)
        Product.objects.filter(pk=self.apple.pk).update(is_featured=True)

    def test_product_list_fills_only_saved_hearts(self):
        self._save(self.user, self.apple)
        self.client.force_login(self.user)
        html = self.client.get(reverse("products:product_list")).content.decode()
        self.assertEqual(html.count('aria-pressed="true"'), 1)
        self.assertEqual(html.count('aria-pressed="false"'), 1)  # mango
        self.assertIn(f'value="/products/#product-{self.apple.id}"', html)

    def test_no_extra_queries_per_saved_card(self):
        self.client.force_login(self.user)
        url = reverse("products:product_list")
        with CaptureQueriesContext(connection) as none_saved:
            self.client.get(url)
        self._save(self.user, self.apple)
        self._save(self.user, self.mango)
        with CaptureQueriesContext(connection) as two_saved:
            self.client.get(url)
        self.assertEqual(len(two_saved), len(none_saved))

    def test_logged_out_hearts_are_outlines(self):
        res = self.client.get(reverse("products:product_list"))
        self.assertNotContains(res, 'aria-pressed="true"')
        self.assertContains(res, 'aria-pressed="false"', count=2)

    def test_home_heart_returns_to_its_slider(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse("home"))
        self.assertContains(res, 'value="/#featured"')

    def test_item_page_main_and_related_hearts(self):
        self._save(self.user, self.apple)
        self.client.force_login(self.user)
        url = reverse("products:product_detail", args=["apple"])
        res = self.client.get(url)
        self.assertContains(res, 'class="rp-fav rp-fav--main"')
        self.assertContains(res, "♥")  # apple (main) is saved
        self.assertContains(res, "♡")  # mango (related) is not
        self.assertContains(res, f'value="{url}#relatedGrid"')
