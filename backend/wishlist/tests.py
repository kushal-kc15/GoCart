import re

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from cart.models import Cart, CartItem
from products.models import Category, Product
from .models import Wishlist, WishlistItem

User = get_user_model()

# The header common.js sends with every in-place request.
XHR = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def flashes(response):
    """Flash messages queued during this request (they would show on the next page)."""
    return [str(m) for m in get_messages(response.wsgi_request)]


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


class ToggleJsonTests(WishlistTestBase):
    """The in-place path: the same POST as the heart form, plus the XHR header."""

    def _post(self, product, action, **extra):
        return self.client.post(
            self.toggle_url, {"product_id": product.id, "action": action, **extra}, **XHR
        )

    def test_add_replies_with_json_and_saves(self):
        self.client.force_login(self.user)
        res = self._post(self.apple, "add", next="/products/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/json")
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["saved"])
        self.assertEqual(data["product_id"], self.apple.id)
        self.assertEqual(data["message"], "Apple saved to your wishlist.")
        self.assertEqual(data["level"], "success")
        self.assertEqual(data["wishlist_count"], 1)
        self.assertEqual(data["cart_count"], 0)
        self.assertEqual(self._items(self.user).count(), 1)

    def test_remove_replies_with_json_and_deletes(self):
        self._save(self.user, self.apple)
        self._save(self.user, self.mango)
        self.client.force_login(self.user)
        data = self._post(self.apple, "remove").json()
        self.assertFalse(data["saved"])
        self.assertEqual(data["message"], "Apple removed from your wishlist.")
        self.assertEqual(data["wishlist_count"], 1)
        self.assertEqual(list(self._items(self.user).values_list("product", flat=True)), [self.mango.id])

    def test_adding_twice_keeps_one_row(self):
        self.client.force_login(self.user)
        self._post(self.apple, "add")
        data = self._post(self.apple, "add").json()
        self.assertEqual(data["wishlist_count"], 1)
        self.assertEqual(self._items(self.user).count(), 1)

    def test_queues_no_flash_message(self):
        self.client.force_login(self.user)
        res = self._post(self.apple, "add")
        self.assertEqual(flashes(res), [])
        # ...so the next full page doesn't show it a second time
        self.assertNotContains(self.client.get(self.page_url), "saved to your wishlist")

    def test_count_matches_the_header_badge(self):
        # A hidden product is not counted by the header badge, so not here either.
        hidden = Product.objects.create(
            category=self.apple.category, name="Plum", slug="plum", price=50, stock=5,
            is_available=False,
        )
        self._save(self.user, hidden)
        self.client.force_login(self.user)
        data = self._post(self.apple, "add").json()
        self.assertEqual(data["wishlist_count"], 1)
        badge = self.client.get(reverse("home")).context["wishlist_count"]
        self.assertEqual(data["wishlist_count"], badge)

    def test_reply_also_has_the_cart_count(self):
        CartItem.objects.create(
            cart=Cart.objects.create(user=self.user), product=self.mango, quantity=3
        )
        self.client.force_login(self.user)
        self.assertEqual(self._post(self.apple, "add").json()["cart_count"], 3)

    def test_remove_only_touches_own_wishlist(self):
        self._save(self.other, self.apple)
        self.client.force_login(self.user)
        self._post(self.apple, "remove")
        self.assertEqual(self._items(self.other).count(), 1)

    def test_unknown_product_is_404(self):
        self.client.force_login(self.user)
        res = self.client.post(self.toggle_url, {"product_id": 9999, "action": "add"}, **XHR)
        self.assertEqual(res.status_code, 404)

    def test_logged_out_gets_the_login_url_as_json(self):
        data = {"product_id": self.apple.id, "action": "add", "next": "/products/?page=2#product-5"}
        res = self.client.post(self.toggle_url, data, **XHR)
        self.assertEqual(res.status_code, 401)
        self.assertFalse(res.json()["ok"])
        # the very same URL the plain form post redirects to
        plain = self.client.post(self.toggle_url, data)
        self.assertEqual(res.json()["redirect"], plain.url)
        self.assertFalse(Wishlist.objects.exists())

    def test_logged_out_keeps_the_login_message_for_the_login_page(self):
        res = self._post(self.apple, "add", next="/products/")
        self.assertEqual(flashes(res), ["Please log in to save items to your wishlist."])
        login_page = self.client.get(res.json()["redirect"])
        self.assertContains(login_page, "Please log in to save items to your wishlist.")

    def test_plain_post_still_redirects_with_a_flash_message(self):
        self.client.force_login(self.user)
        res = self.client.post(
            self.toggle_url, {"product_id": self.apple.id, "action": "add", "next": "/products/"}
        )
        self.assertRedirects(res, "/products/", fetch_redirect_response=False)
        self.assertEqual(flashes(res), ["Apple saved to your wishlist."])

    def test_csrf_token_from_the_form_is_accepted_and_none_is_refused(self):
        self._save(self.user, self.apple)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        post = {"product_id": self.apple.id, "action": "remove"}

        self.assertEqual(client.post(self.toggle_url, post, **XHR).status_code, 403)
        self.assertEqual(self._items(self.user).count(), 1)

        # common.js sends FormData(form), which includes this hidden field
        html = client.get(self.page_url).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
        res = client.post(self.toggle_url, {**post, "csrfmiddlewaretoken": token}, **XHR)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json()["saved"])
        self.assertFalse(self._items(self.user).exists())


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

    # ---- hooks for common.js (a removed product leaves the page in place) ----
    def _tags(self, html, name):
        """The opening tags that carry the given data attribute."""
        return re.findall(rf"<[^>]*{name}[^>]*>", html)

    def test_filled_page_shows_the_grid_and_hides_the_empty_message(self):
        self._save(self.user, self.apple)
        self._save(self.user, self.mango)
        self.client.force_login(self.user)
        html = self.client.get(self.page_url).content.decode()
        (grid,) = self._tags(html, "data-wishlist-filled")
        (empty,) = self._tags(html, "data-wishlist-empty")
        self.assertNotIn("hidden", grid)
        self.assertIn("hidden", empty)
        self.assertIn("data-wishlist-count>(2)<", html)

    def test_empty_page_hides_the_grid_and_shows_the_empty_message(self):
        self.client.force_login(self.user)
        html = self.client.get(self.page_url).content.decode()
        (grid,) = self._tags(html, "data-wishlist-filled")
        (empty,) = self._tags(html, "data-wishlist-empty")
        self.assertIn("hidden", grid)
        self.assertNotIn("hidden", empty)
        self.assertIn("data-wishlist-count>(0)<", html)
        self.assertContains(self.client.get(self.page_url), "Your wishlist is empty")

    def test_cards_are_set_up_to_leave_the_page_when_unsaved(self):
        self._save(self.user, self.apple)
        self._save(self.user, self.mango)
        self.client.force_login(self.user)
        html = self.client.get(self.page_url).content.decode()
        self.assertEqual(html.count(" data-remove-on-unsave"), 2)
        # per card: the heart and the Remove button both save in place
        self.assertEqual(html.count('data-ajax="wish-toggle" data-once'), 4)
        self.assertEqual(html.count('class="wl-remove"'), 2)

    def test_product_list_cards_stay_when_unsaved(self):
        # The list is not the wishlist: un-hearting there only empties the heart
        Category.objects.filter(slug="fruits").update(
            parent=Category.objects.create(name="Food", slug="food")
        )
        self._save(self.user, self.apple)
        self.client.force_login(self.user)
        html = self.client.get(reverse("products:product_list")).content.decode()
        self.assertNotIn("data-remove-on-unsave", html)

    def test_header_badge_count(self):
        self._save(self.user, self.apple)
        self._save(self.user, self.mango)
        self._save(self.other, self.apple)
        self.client.force_login(self.user)
        res = self.client.get(reverse("home"))
        self.assertContains(
            res, '<span class="cart-badge wishlist-badge" data-wishlist-badge>2</span>', html=True
        )

    def test_badge_is_hidden_when_empty(self):
        # Always in the page (common.js fills it in place), just hidden at 0
        self.client.force_login(self.user)
        res = self.client.get(reverse("home"))
        self.assertContains(
            res, '<span class="cart-badge wishlist-badge" data-wishlist-badge hidden></span>',
            html=True,
        )

    def test_badge_is_hidden_when_logged_out(self):
        res = self.client.get(reverse("home"))
        self.assertContains(
            res, '<span class="cart-badge wishlist-badge" data-wishlist-badge hidden></span>',
            html=True,
        )

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

    def test_every_heart_is_set_up_for_in_place_saving(self):
        # common.js saves a heart without a reload only when its form has data-ajax="wish-toggle";
        # data-once stays too, so the form still works (and can't double submit) without it.
        self.client.force_login(self.user)
        pages = {
            "home": reverse("home"),
            "product list": reverse("products:product_list"),
            "item page": reverse("products:product_detail", args=["apple"]),
        }
        for name, url in pages.items():
            with self.subTest(page=name):
                html = self.client.get(url).content.decode()
                hearts = html.count('class="wish-form"')
                self.assertGreater(hearts, 0)
                self.assertEqual(html.count('data-ajax="wish-toggle" data-once'), hearts)

    def test_item_page_main_and_related_hearts(self):
        self._save(self.user, self.apple)
        self.client.force_login(self.user)
        url = reverse("products:product_detail", args=["apple"])
        res = self.client.get(url)
        html = res.content.decode()
        # Same SVG heart as the other pages: main image (apple, saved) + related card (mango, not saved)
        self.assertEqual(html.count('class="wish"'), 2)
        self.assertRegex(html, r'aria-label="Save Apple to wishlist"\s+aria-pressed="true"')
        self.assertRegex(html, r'aria-label="Save Mango to wishlist"\s+aria-pressed="false"')
        self.assertContains(res, f'value="{url}#relatedGrid"')
