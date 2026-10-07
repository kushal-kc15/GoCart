import re

from django.contrib.messages import get_messages
from django.db import connection
from django.template.defaultfilters import floatformat
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.contrib.auth import get_user_model

from products.models import Category, Product
from wishlist.models import Wishlist, WishlistItem
from .models import Cart, CartItem

User = get_user_model()

# The header common.js sends with every in-place request.
XHR = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def flashes(response):
    """Flash messages queued during this request (they would show on the next page)."""
    return [str(m) for m in get_messages(response.wsgi_request)]


class CartViewsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password="pass12345",
            email_verified=True,
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

    # ---- sold out / hidden products (a page that was open for a while) ----
    def test_add_out_of_stock_adds_nothing(self):
        self._login()
        Product.objects.filter(pk=self.product.pk).update(stock=0)
        res = self.client.post(
            self.add_url, {"product_id": self.product.id, "next": "/products/"}
        )
        self.assertEqual(res.url, "/products/")
        self.assertFalse(CartItem.objects.exists())
        self.assertEqual(flashes(res), ["Apple is out of stock."])

    def test_add_hidden_product_adds_nothing(self):
        self._login()
        Product.objects.filter(pk=self.product.pk).update(is_available=False)
        res = self.client.post(
            self.add_url, {"product_id": self.product.id, "next": "/products/"}
        )
        self.assertEqual(res.url, "/products/")
        self.assertFalse(CartItem.objects.exists())
        self.assertEqual(flashes(res), ["Apple is no longer available."])

    def test_buy_now_out_of_stock_stays_on_the_page(self):
        self._login()
        Product.objects.filter(pk=self.product.pk).update(stock=0)
        res = self.client.post(self.add_url, {
            "product_id": self.product.id, "next": "/products/apple/", "buy_now": "1",
        })
        self.assertEqual(res.url, "/products/apple/")  # not checkout: nothing was added
        self.assertFalse(CartItem.objects.exists())

    # ---- messages (same wording as the in-place path) ----
    def test_add_says_added(self):
        self._login()
        res = self.client.post(self.add_url, {"product_id": self.product.id})
        self.assertEqual(flashes(res), ["Apple added to your cart."])

    def test_add_over_stock_says_only_n_in_stock(self):
        self._login()
        res = self.client.post(self.add_url, {"product_id": self.product.id, "quantity": 99})
        self.assertEqual(flashes(res), ["Only 5 of Apple in stock."])

    def test_adding_more_when_cart_has_all_the_stock(self):
        self._login()
        CartItem.objects.create(
            cart=Cart.objects.create(user=self.user), product=self.product, quantity=5
        )
        res = self.client.post(self.add_url, {"product_id": self.product.id})
        item = CartItem.objects.get(cart__user=self.user, product=self.product)
        self.assertEqual(item.quantity, 5)
        self.assertEqual(flashes(res), ["Only 5 of Apple in stock."])

    def test_update_inc_at_stock_says_only_n_in_stock(self):
        self._login()
        cart = Cart.objects.create(user=self.user)
        item = CartItem.objects.create(cart=cart, product=self.product, quantity=5)
        res = self.client.post(self.update_url, {"item_id": item.id, "action": "inc"})
        self.assertEqual(flashes(res), ["Only 5 of Apple in stock."])

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


class CartJsonTests(TestCase):
    """The in-place path: same POSTs as the forms, plus the XHR header, answered with JSON."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password="pass12345"
        )
        category = Category.objects.create(name="Fruits", slug="fruits")
        self.apple = Product.objects.create(
            category=category, name="Apple", slug="apple", price=100, stock=5
        )
        self.mango = Product.objects.create(
            category=category, name="Mango", slug="mango", price="99.50", stock=5
        )
        self.add_url = reverse("cart:add_to_cart")
        self.update_url = reverse("cart:update_quantity")
        self.remove_url = reverse("cart:remove_from_cart")
        self.client.force_login(self.user)

    def _post(self, url, data):
        return self.client.post(url, data, **XHR)

    def _item(self, product, quantity=1):
        cart, _ = Cart.objects.get_or_create(user=self.user)
        return CartItem.objects.create(cart=cart, product=product, quantity=quantity)

    # ---- add_to_cart ----
    def test_add_replies_with_json_and_no_redirect(self):
        res = self._post(self.add_url, {"product_id": self.apple.id, "quantity": 2, "next": "/products/"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/json")
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["level"], "success")
        self.assertEqual(data["message"], "Apple added to your cart.")
        self.assertEqual(data["quantity"], 2)
        self.assertEqual(data["cart_count"], 2)
        self.assertEqual(data["wishlist_count"], 0)
        item = CartItem.objects.get(cart__user=self.user, product=self.apple)
        self.assertEqual(item.quantity, 2)

    def test_add_queues_no_flash_message(self):
        res = self._post(self.add_url, {"product_id": self.apple.id})
        self.assertEqual(flashes(res), [])
        # ...so the next full page doesn't show it a second time
        page = self.client.get(reverse("cart:cart_detail"))
        self.assertNotContains(page, "added to your cart")

    def test_cart_count_adds_up_every_line(self):
        self._item(self.mango, 3)
        data = self._post(self.add_url, {"product_id": self.apple.id, "quantity": 2}).json()
        self.assertEqual(data["cart_count"], 5)

    def test_add_over_stock_says_only_n_in_stock(self):
        data = self._post(self.add_url, {"product_id": self.apple.id, "quantity": 99}).json()
        self.assertTrue(data["ok"])  # something was added, just not everything asked for
        self.assertEqual(data["level"], "info")
        self.assertEqual(data["message"], "Only 5 of Apple in stock.")
        self.assertEqual(data["quantity"], 5)
        self.assertEqual(data["cart_count"], 5)

    def test_add_out_of_stock_is_an_error_and_adds_nothing(self):
        Product.objects.filter(pk=self.apple.pk).update(stock=0)
        data = self._post(self.add_url, {"product_id": self.apple.id}).json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["level"], "error")
        self.assertEqual(data["message"], "Apple is out of stock.")
        self.assertEqual(data["cart_count"], 0)
        self.assertFalse(CartItem.objects.exists())

    def test_add_hidden_product_is_an_error_and_adds_nothing(self):
        Product.objects.filter(pk=self.apple.pk).update(is_available=False)
        data = self._post(self.add_url, {"product_id": self.apple.id}).json()
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "Apple is no longer available.")
        self.assertFalse(CartItem.objects.exists())

    def test_add_unknown_product_is_404(self):
        self.assertEqual(self._post(self.add_url, {"product_id": 9999}).status_code, 404)

    def test_logged_out_add_gets_the_login_url_as_json(self):
        self.client.logout()
        data = {"product_id": self.apple.id, "next": "/products/?page=2#product-5"}
        res = self._post(self.add_url, data)
        self.assertEqual(res.status_code, 401)
        self.assertFalse(res.json()["ok"])
        # the very same URL the plain form post redirects to
        plain = self.client.post(self.add_url, data)
        self.assertEqual(res.json()["redirect"], plain.url)
        self.assertFalse(CartItem.objects.exists())

    def test_logged_out_add_keeps_the_login_message_for_the_login_page(self):
        self.client.logout()
        res = self._post(self.add_url, {"product_id": self.apple.id, "next": "/products/"})
        self.assertEqual(flashes(res), ["Please log in to add items to your cart."])
        login_page = self.client.get(res.json()["redirect"])
        self.assertContains(login_page, "Please log in to add items to your cart.")

    # ---- update_quantity ----
    def test_update_inc_and_dec_reply_with_quantity_and_summary(self):
        item = self._item(self.apple, 1)
        data = self._post(self.update_url, {"item_id": item.id, "action": "inc"}).json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "")  # a normal + says nothing
        self.assertEqual(data["item_id"], item.id)
        self.assertEqual(data["quantity"], 2)
        self.assertEqual(data["cart_count"], 2)
        self.assertEqual(data["product_count"], 1)
        self.assertEqual(data["subtotal"], "Rs. 200")
        self.assertEqual(data["shipping"], "Rs. 100")
        self.assertEqual(data["grand_total"], "Rs. 300")

        data = self._post(self.update_url, {"item_id": item.id, "action": "dec"}).json()
        self.assertEqual(data["quantity"], 1)
        self.assertEqual(data["subtotal"], "Rs. 100")
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    def test_summary_adds_every_line_and_keeps_two_decimals_when_needed(self):
        apple = self._item(self.apple, 1)
        self._item(self.mango, 1)
        data = self._post(self.update_url, {"item_id": apple.id, "action": "inc"}).json()
        # 100 x 2 + 99.50 x 1
        self.assertEqual(data["product_count"], 2)
        self.assertEqual(data["cart_count"], 3)
        self.assertEqual(data["subtotal"], "Rs. 299.50")
        self.assertEqual(data["grand_total"], "Rs. 399.50")

    def test_summary_matches_the_cart_page(self):
        apple = self._item(self.apple, 1)
        self._item(self.mango, 2)
        data = self._post(self.update_url, {"item_id": apple.id, "action": "inc"}).json()
        page = self.client.get(reverse("cart:cart_detail"))
        self.assertEqual(data["subtotal"], f"Rs. {floatformat(page.context['subtotal'], '-2')}")
        self.assertEqual(data["grand_total"], f"Rs. {floatformat(page.context['grand_total'], '-2')}")
        self.assertEqual(data["shipping"], f"Rs. {page.context['shipping']}")

    def test_update_inc_at_stock_keeps_quantity_and_explains(self):
        item = self._item(self.apple, 5)
        res = self._post(self.update_url, {"item_id": item.id, "action": "inc"})
        data = res.json()
        self.assertEqual(data["quantity"], 5)
        self.assertEqual(data["level"], "info")
        self.assertEqual(data["message"], "Only 5 of Apple in stock.")
        self.assertEqual(flashes(res), [])

    def test_update_dec_at_one_keeps_one(self):
        item = self._item(self.apple, 1)
        data = self._post(self.update_url, {"item_id": item.id, "action": "dec"}).json()
        self.assertEqual(data["quantity"], 1)

    # ---- remove_from_cart ----
    def test_remove_replies_with_summary(self):
        apple = self._item(self.apple, 2)
        self._item(self.mango, 1)
        res = self._post(self.remove_url, {"item_id": apple.id})
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["message"], "Apple removed from your cart.")
        self.assertEqual(data["item_id"], apple.id)
        self.assertFalse(data["cart_empty"])
        self.assertEqual(data["cart_count"], 1)
        self.assertEqual(data["product_count"], 1)
        self.assertEqual(data["subtotal"], "Rs. 99.50")
        self.assertFalse(CartItem.objects.filter(pk=apple.id).exists())
        self.assertEqual(flashes(res), [])

    def test_removing_the_last_item_says_the_cart_is_empty(self):
        apple = self._item(self.apple, 2)
        data = self._post(self.remove_url, {"item_id": apple.id}).json()
        self.assertTrue(data["cart_empty"])
        self.assertEqual(data["cart_count"], 0)
        self.assertEqual(data["product_count"], 0)
        self.assertEqual(data["subtotal"], "Rs. 0")
        self.assertEqual(data["shipping"], "Free")
        self.assertEqual(data["grand_total"], "Rs. 0")

    # ---- other people's carts, logged-out users ----
    def test_cannot_touch_another_users_item(self):
        bob = User.objects.create_user(username="bob", email="bob@example.com", password="pass12345")
        bobs_item = CartItem.objects.create(
            cart=Cart.objects.create(user=bob), product=self.apple, quantity=1
        )
        for url, extra in ((self.update_url, {"action": "inc"}), (self.remove_url, {})):
            with self.subTest(url=url):
                res = self._post(url, {"item_id": bobs_item.id, **extra})
                self.assertEqual(res.status_code, 404)
        bobs_item.refresh_from_db()
        self.assertEqual(bobs_item.quantity, 1)

    def test_logged_out_update_and_remove_still_redirect_to_login(self):
        # login_required answers these; common.js follows the redirect to the login page.
        item = self._item(self.apple, 1)
        self.client.logout()
        for url in (self.update_url, self.remove_url):
            with self.subTest(url=url):
                res = self._post(url, {"item_id": item.id, "action": "inc"})
                self.assertEqual(res.status_code, 302)
                self.assertIn(reverse("accounts:login"), res.url)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 1)

    # ---- CSRF ----
    def test_csrf_token_from_the_form_is_accepted_and_none_is_refused(self):
        item = self._item(self.apple, 1)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)

        refused = client.post(self.update_url, {"item_id": item.id, "action": "inc"}, **XHR)
        self.assertEqual(refused.status_code, 403)

        # common.js sends FormData(form), which includes this hidden field
        html = client.get(reverse("cart:cart_detail")).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html).group(1)
        res = client.post(
            self.update_url,
            {"item_id": item.id, "action": "inc", "csrfmiddlewaretoken": token},
            **XHR,
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["quantity"], 2)


class CartPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password="pass12345"
        )
        self.client.force_login(self.user)
        self.category = Category.objects.create(name="Fruits", slug="fruits")
        self.apple = Product.objects.create(
            category=self.category, name="Apple", slug="apple", price=100, stock=5
        )
        self.banana = Product.objects.create(
            category=self.category, name="Banana", slug="banana", price=50, stock=5
        )
        self.cart = Cart.objects.create(user=self.user)
        self.url = reverse("cart:cart_detail")

    def _add(self, product, quantity=1):
        CartItem.objects.create(cart=self.cart, product=product, quantity=quantity)

    # ---- slim heading ----
    def test_heading_shows_item_count(self):
        self._add(self.apple, 3)
        response = self.client.get(self.url)
        self.assertContains(response, '<h1 class="cart-title">Shopping Cart</h1>', html=True)
        self.assertContains(response, "3 items")
        self.assertNotContains(response, "cart-hero")

    def test_heading_count_is_singular_for_one_item(self):
        self._add(self.apple)
        html = self.client.get(self.url).content.decode()
        self.assertRegex(html, r"\b1 item\b(?!s)")

    # ---- You may also like ----
    def _suggested(self, response):
        return [p.name for p in response.context["recommended_products"]]

    def test_suggestions_exclude_cart_items(self):
        self._add(self.apple)
        response = self.client.get(self.url)
        self.assertEqual(self._suggested(response), ["Banana"])
        self.assertContains(response, 'id="recs"')
        self.assertContains(response, "You may also like")

    def test_suggestions_hidden_when_nothing_to_show(self):
        self._add(self.apple)
        self._add(self.banana)
        response = self.client.get(self.url)
        self.assertEqual(self._suggested(response), [])
        self.assertNotContains(response, 'id="recs"')
        self.assertNotContains(response, "You may also like")

    def test_no_extra_queries_per_card(self):
        self._add(self.apple)
        with CaptureQueriesContext(connection) as one_card:
            self.client.get(self.url)  # suggests Banana only
        for i in range(4):
            Product.objects.create(
                category=self.category, name=f"Extra {i}", slug=f"extra-{i}", price=10, stock=5
            )
        with CaptureQueriesContext(connection) as five_cards:
            response = self.client.get(self.url)
        self.assertEqual(len(self._suggested(response)), 5)
        self.assertEqual(len(five_cards), len(one_card))

    def test_empty_cart_page_still_works(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your cart is empty.")
        self.assertContains(response, "0 items")
        self.assertContains(response, 'class="pay-btn disabled"')
        self.assertEqual(self._suggested(response), ["Banana", "Apple"])  # newest first

        # No products at all: the page still works, just without the section
        Product.objects.all().delete()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="recs"')

    # ---- hooks for cart.js (the cart changes in place) ----
    def _parts(self, html, name):
        """The opening tags that carry data-cart-filled / data-cart-empty."""
        return re.findall(rf"<[^>]*{name}[^>]*>", html)

    def test_filled_cart_shows_the_list_and_hides_the_empty_message(self):
        self._add(self.apple)
        html = self.client.get(self.url).content.decode()
        filled = self._parts(html, "data-cart-filled")
        empty = self._parts(html, "data-cart-empty")
        # list head, list, "continue shopping" link, checkout link / the empty message, disabled checkout
        self.assertEqual(len(filled), 4)
        self.assertEqual(len(empty), 2)
        self.assertTrue(all("hidden" not in tag for tag in filled))
        self.assertTrue(all("hidden" in tag for tag in empty))

    def test_empty_cart_hides_the_list_and_shows_the_empty_message(self):
        html = self.client.get(self.url).content.decode()
        filled = self._parts(html, "data-cart-filled")
        empty = self._parts(html, "data-cart-empty")
        self.assertEqual(len(filled), 4)
        self.assertEqual(len(empty), 2)
        self.assertTrue(all("hidden" in tag for tag in filled))
        self.assertTrue(all("hidden" not in tag for tag in empty))
        self.assertContains(self.client.get(self.url), 'class="pay-btn disabled"')

    def test_rows_and_forms_are_set_up_for_in_place_updates(self):
        self._add(self.apple, 1)
        self._add(self.banana, 3)
        html = self.client.get(self.url).content.decode()
        self.assertEqual(html.count("data-cart-row data-ajax-lock"), 2)
        self.assertEqual(html.count('data-ajax="cart-qty"'), 4)     # - and + for each row
        self.assertEqual(html.count('data-ajax="cart-remove"'), 2)  # trash for each row
        self.assertEqual(html.count("data-cart-dec"), 2)
        self.assertEqual(html.count("data-cart-qty>"), 2)
        # - is disabled at 1 (cart.js re-enables it when the quantity goes up)
        self.assertEqual(len(re.findall(r"data-cart-dec disabled>", html)), 1)

    def test_summary_numbers_have_hooks_and_the_same_text_as_the_json(self):
        self._add(self.apple, 2)
        html = self.client.get(self.url).content.decode()
        self.assertIn('data-cart-items-label>2 items<', html)
        self.assertIn('data-cart-products-label>(1 product)<', html)
        self.assertIn('data-cart-subtotal>Rs. 200<', html)
        self.assertIn('data-cart-shipping>Rs. 100<', html)
        self.assertIn('data-cart-total>Rs. 300<', html)

    def test_suggestion_card_hearts_save_in_place_but_add_to_cart_reloads(self):
        self._add(self.apple)
        html = self.client.get(self.url).content.decode()
        recs = html.split('id="recs"', 1)[1]
        self.assertIn('data-ajax="wish-toggle"', recs)
        # Adding from here changes the cart list above, so it stays a normal form post
        form = recs.split('class="add-to-cart-form"', 1)[1].split("</form>", 1)[0]
        self.assertNotIn("data-ajax", form)

    def test_suggestion_card_forms_work(self):
        self._add(self.apple)
        html = self.client.get(self.url).content.decode()
        recs = html.split('id="recs"', 1)[1]
        self.assertIn(f'name="product_id" value="{self.banana.id}"', recs)
        self.assertIn('name="buy_now"', recs)
        self.assertIn(f'name="next" value="{self.url}#recs"', recs)  # heart comes back here

        # Add to Cart returns to the cart, where Banana moves into the cart list
        response = self.client.post(
            reverse("cart:add_to_cart"),
            {"product_id": self.banana.id, "next": self.url},
            follow=True,
        )
        names = sorted(item.product.name for item in response.context["cart_items"])
        self.assertEqual(names, ["Apple", "Banana"])
        self.assertEqual(self._suggested(response), [])


class AddToCartFormsTests(TestCase):
    """Which Add to Cart forms common.js sends in place (data-ajax) and which stay normal posts."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password="pass12345"
        )
        food = Category.objects.create(name="Food", slug="food")
        fruits = Category.objects.create(name="Fruits", slug="fruits", parent=food)
        self.apple = Product.objects.create(
            category=fruits, name="Apple", slug="apple", price=100, stock=5, is_featured=True
        )
        Product.objects.create(category=fruits, name="Mango", slug="mango", price=80, stock=5)
        self.client.force_login(self.user)

    def _forms(self, url):
        html = self.client.get(url).content.decode()
        return re.findall(r'<form class="add-to-cart-form".*?</form>', html, re.S)

    def test_home_cards_add_in_place_and_buy_now_stays_a_normal_post(self):
        forms = self._forms(reverse("home"))
        self.assertGreater(len(forms), 0)
        for form in forms:
            self.assertIn('data-ajax="cart-add" data-once', form)
            self.assertRegex(form, r'<button[^>]*name="buy_now"[^>]*data-no-ajax')
            self.assertNotRegex(form, r'class="add"[^>]*data-no-ajax')

    def test_product_list_cards_add_in_place(self):
        forms = self._forms(reverse("products:product_list"))
        self.assertEqual(len(forms), 2)
        for form in forms:
            self.assertIn('data-ajax="cart-add" data-once', form)

    def test_item_page_adds_in_place_and_buy_now_stays_a_normal_post(self):
        (form,) = self._forms(reverse("products:product_detail", args=["apple"]))
        self.assertIn('data-ajax="cart-add" data-once', form)
        self.assertRegex(form, r'<button[^>]*name="buy_now"[^>]*data-no-ajax')
        # the Add to Cart button next to it is not marked
        add_button = re.search(r'<button[^>]*>Add to Cart</button>', form).group(0)
        self.assertNotIn("data-no-ajax", add_button)
        self.assertIn('name="quantity"', form)  # the quantity is sent along

    def test_wishlist_page_cards_add_in_place(self):
        WishlistItem.objects.create(
            wishlist=Wishlist.objects.create(user=self.user), product=self.apple
        )
        forms = self._forms(reverse("wishlist:wishlist_detail"))
        self.assertEqual(len(forms), 1)
        self.assertIn('data-ajax="cart-add" data-once', forms[0])

    def test_cart_page_suggestions_stay_normal_posts(self):
        forms = self._forms(reverse("cart:cart_detail"))
        self.assertGreater(len(forms), 0)  # the cart is empty, so both products are suggested
        for form in forms:
            self.assertNotIn("data-ajax", form)
            self.assertIn("data-once", form)


class HeaderHooksTests(TestCase):
    """What common.js needs from base.html: both badges and the message box, always there."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", email="alice@example.com", password="pass12345"
        )
        category = Category.objects.create(name="Fruits", slug="fruits")
        self.apple = Product.objects.create(
            category=category, name="Apple", slug="apple", price=100, stock=5
        )

    def test_cart_badge_is_hidden_at_zero(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse("home"))
        self.assertContains(
            res, '<span class="cart-badge" id="cartBadge" data-cart-badge hidden></span>', html=True
        )

    def test_cart_badge_is_hidden_when_logged_out(self):
        res = self.client.get(reverse("home"))
        self.assertContains(
            res, '<span class="cart-badge" id="cartBadge" data-cart-badge hidden></span>', html=True
        )

    def test_cart_badge_shows_the_total_quantity(self):
        CartItem.objects.create(
            cart=Cart.objects.create(user=self.user), product=self.apple, quantity=3
        )
        self.client.force_login(self.user)
        res = self.client.get(reverse("home"))
        self.assertContains(
            res, '<span class="cart-badge" id="cartBadge" data-cart-badge>3</span>', html=True
        )

    def test_message_box_is_in_the_page_even_when_empty(self):
        res = self.client.get(reverse("home"))
        self.assertContains(res, '<div class="messages" role="status" aria-live="polite">')
        self.assertNotContains(res, 'class="message ')  # no message inside it

    def test_flash_message_still_shows_in_the_box(self):
        self.client.force_login(self.user)
        res = self.client.post(
            reverse("cart:add_to_cart"), {"product_id": self.apple.id, "next": "/"}, follow=True
        )
        self.assertContains(res, '<div class="message success">')
        self.assertContains(res, "Apple added to your cart.")


class AdminSkipsStorefrontLookupsTests(TestCase):
    """The header's cart and wishlist badges don't exist in the admin, so no queries there."""

    def setUp(self):
        self.boss = User.objects.create_superuser(
            username="boss", email="boss@example.com", password="pass12345"
        )
        category = Category.objects.create(name="Fruits", slug="fruits")
        self.apple = Product.objects.create(
            category=category, name="Apple", slug="apple", price=100, stock=10
        )
        cart = Cart.objects.create(user=self.boss)
        CartItem.objects.create(cart=cart, product=self.apple, quantity=2)
        WishlistItem.objects.create(wishlist=Wishlist.objects.create(user=self.boss), product=self.apple)
        self.client.force_login(self.boss)

    def test_admin_pages_make_no_cart_or_wishlist_queries(self):
        urls = [
            reverse("admin:index"),
            reverse("admin:orders_order_changelist"),
            reverse("admin:products_product_changelist"),
            reverse("admin:accounts_user_changelist"),
            reverse("admin:accounts_user_change", args=[self.boss.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                with CaptureQueriesContext(connection) as queries:
                    self.assertEqual(self.client.get(url).status_code, 200)
                sql = " ".join(q["sql"] for q in queries.captured_queries)
                self.assertNotIn("cart_cartitem", sql)
                self.assertNotIn("wishlist_wishlistitem", sql)

    def test_the_shop_still_shows_the_cart_and_wishlist_counts(self):
        response = self.client.get(reverse("cart:cart_detail"))
        self.assertEqual(response.context["cart_count"], 2)
        self.assertEqual(response.context["wishlist_count"], 1)
        self.assertEqual(response.context["wishlist_ids"], {self.apple.pk})
        self.assertContains(response, 'id="cartBadge"')
