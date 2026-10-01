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
