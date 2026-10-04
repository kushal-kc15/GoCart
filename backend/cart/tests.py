from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from products.models import Category, Product
from .models import Cart, CartItem

User = get_user_model()


class CartViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password="pass12345"
        )
        self.category = Category.objects.create(name="Fruits", slug="fruits")
        self.product = Product.objects.create(
            category=self.category, name="Apple", slug="apple", price=100, stock=5
        )
        self.add_url = reverse("cart:add_to_cart")
        self.update_url = reverse("cart:update_quantity")
        self.remove_url = reverse("cart:remove_from_cart")
        self.cart_url = reverse("cart:cart_detail")

    def _login(self):
        self.client.force_login(self.user)

    # ---- add_to_cart ----
    def test_add_requires_login(self):
        res = self.client.post(self.add_url, {"product_id": self.product.id})
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/login", res.url)
        self.assertFalse(CartItem.objects.exists())

    def test_anonymous_add_redirects_to_login_with_page_as_next(self):
        res = self.client.post(
            self.add_url, {"product_id": self.product.id, "next": "/products/?page=2"}
        )
        # next is the page they were on, not the POST-only add URL.
        self.assertEqual(
            res.url, reverse("accounts:login") + "?next=%2Fproducts%2F%3Fpage%3D2"
        )

    def test_anonymous_add_keeps_card_anchor_in_next(self):
        res = self.client.post(
            self.add_url,
            {"product_id": self.product.id, "next": "/products/?page=2#product-5"},
        )
        # The # is encoded inside next, so it survives the trip through login.
        self.assertEqual(
            res.url,
            reverse("accounts:login") + "?next=%2Fproducts%2F%3Fpage%3D2%23product-5",
        )

    def test_anonymous_add_shows_login_message(self):
        res = self.client.post(
            self.add_url, {"product_id": self.product.id, "next": "/products/"},
            follow=True,
        )
        self.assertContains(res, "Please log in to add items to your cart.")

    def test_anonymous_add_ignores_external_next(self):
        res = self.client.post(
            self.add_url,
            {"product_id": self.product.id, "next": "http://evil.example.com/"},
        )
        self.assertNotIn("evil.example.com", res.url)

    def test_login_after_anonymous_add_returns_to_page_not_add_url(self):
        self.client.post(
            self.add_url, {"product_id": self.product.id, "next": "/products/"}
        )
        res = self.client.post(
            reverse("accounts:login"),
            {"email": "alice@example.com", "password": "pass12345", "next": "/products/"},
        )
        # Lands on the product list (a GET), so no 405, and nothing was auto-added.
        self.assertEqual(res.url, "/products/")
        self.assertFalse(CartItem.objects.exists())

    def test_add_uses_quantity(self):
        self._login()
        self.client.post(self.add_url, {"product_id": self.product.id, "quantity": 3})
        item = CartItem.objects.get(cart__user=self.user, product=self.product)
        self.assertEqual(item.quantity, 3)

    def test_add_defaults_quantity_to_one(self):
        self._login()
        self.client.post(self.add_url, {"product_id": self.product.id})
        item = CartItem.objects.get(cart__user=self.user, product=self.product)
        self.assertEqual(item.quantity, 1)

    def test_add_caps_at_stock(self):
        self._login()
        self.client.post(self.add_url, {"product_id": self.product.id, "quantity": 99})
        item = CartItem.objects.get(cart__user=self.user, product=self.product)
        self.assertEqual(item.quantity, self.product.stock)

    def test_add_redirects_to_safe_next(self):
        self._login()
        res = self.client.post(
            self.add_url, {"product_id": self.product.id, "next": "/products/"}
        )
        self.assertEqual(res.url, "/products/")

    def test_add_rejects_external_next(self):
        self._login()
        res = self.client.post(
            self.add_url,
            {"product_id": self.product.id, "next": "http://evil.example.com/"},
        )
        self.assertEqual(res.url, self.cart_url)

    # ---- Buy Now (same form as Add to Cart, extra buy_now field) ----
    def test_buy_now_adds_item_and_goes_to_checkout(self):
        self._login()
        res = self.client.post(self.add_url, {
            "product_id": self.product.id, "quantity": 2,
            "next": "/products/apple/", "buy_now": "1",
        })
        self.assertEqual(res.url, reverse("orders:checkout"))
        item = CartItem.objects.get(cart__user=self.user, product=self.product)
        self.assertEqual(item.quantity, 2)

    def test_add_without_buy_now_returns_to_page(self):
        self._login()
        res = self.client.post(
            self.add_url, {"product_id": self.product.id, "next": "/products/apple/"}
        )
        self.assertEqual(res.url, "/products/apple/")

    # ---- line_total ----
    def test_line_total_is_price_times_quantity(self):
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, product=self.product, quantity=3)
        self.assertEqual(item.line_total, 300)  # Rs. 100 x 3

    # ---- update_quantity ----
    def test_update_increments_and_decrements(self):
        self._login()
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        self.client.post(self.update_url, {"item_id": item.id, "action": "inc"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

        self.client.post(self.update_url, {"item_id": item.id, "action": "dec"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_update_dec_floored_at_one(self):
        self._login()
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, product=self.product, quantity=1)

        self.client.post(self.update_url, {"item_id": item.id, "action": "dec"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_update_inc_capped_at_stock(self):
        self._login()
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(
            cart=cart, product=self.product, quantity=self.product.stock
        )
        self.client.post(self.update_url, {"item_id": item.id, "action": "inc"})
        item.refresh_from_db()
        self.assertEqual(item.quantity, self.product.stock)

    # ---- remove_from_cart ----
    def test_remove_deletes_item(self):
        self._login()
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, product=self.product, quantity=2)

        self.client.post(self.remove_url, {"item_id": item.id})
        self.assertFalse(CartItem.objects.filter(id=item.id).exists())

    # ---- scoping: can't touch another user's cart ----
    def test_cannot_modify_other_users_item(self):
        other = User.objects.create_user(
            username="bob", email="bob@example.com", password="pass12345"
        )
        other_cart = Cart.objects.create(user=other)
        other_item = CartItem.objects.create(
            cart=other_cart, product=self.product, quantity=1
        )

        self._login()
        res = self.client.post(
            self.remove_url, {"item_id": other_item.id}
        )
        self.assertEqual(res.status_code, 404)
        self.assertTrue(CartItem.objects.filter(id=other_item.id).exists())
