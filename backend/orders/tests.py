from django.contrib import admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from products.models import Category, Product
from cart.models import Cart, CartItem
from accounts.models import Address
from .admin import OrderAdmin
from .forms import AddressForm
from .models import Order, OrderItem, Payment

User = get_user_model()

VALID_ADDRESS = {
    "recipient_name": "Asha Sharma",
    "phone": "9800000000",
    "address_line": "12 Market Rd",
    "city": "Kathmandu",
    "area": "Thamel",
}


class CheckoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="asha", email="asha@example.com", password="pass12345"
        )
        self.category = Category.objects.create(name="Fruits", slug="fruits")
        self.product = Product.objects.create(
            category=self.category, name="Apple", slug="apple", price=100, stock=5
        )
        self.url = reverse("orders:checkout")

    def _fill_cart(self, quantity=2):
        cart, _ = Cart.objects.get_or_create(user=self.user)
        return CartItem.objects.create(cart=cart, product=self.product, quantity=quantity)

    def _post(self, **overrides):
        data = {**VALID_ADDRESS, "delivery_method": "delivery", "payment_method": "cod"}
        data.update(overrides)
        return self.client.post(self.url, data)

    # ---- happy path ----
    def test_valid_order_is_created(self):
        self.client.force_login(self.user)
        self._fill_cart(quantity=2)

        res = self._post()

        order = Order.objects.get(user=self.user)
        self.assertRedirects(res, reverse("orders:order_success", args=[order.pk]))
        # Address saved and linked
        self.assertTrue(Address.objects.filter(user=self.user, recipient_name="Asha Sharma").exists())
        self.assertEqual(order.shipping_address.city, "Kathmandu")
        self.assertIn("Asha Sharma", order.address)
        # Items + totals
        self.assertEqual(OrderItem.objects.filter(order=order).count(), 1)
        self.assertEqual(order.subtotal, 200)
        self.assertEqual(order.shipping_fee, 100)
        self.assertEqual(order.total, 300)
        # Stock decreased
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        # COD payment
        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.method, Payment.Method.COD)
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.amount, 300)
        # Cart emptied
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 0)

    # ---- invalid address ----
    def test_invalid_address_creates_no_order(self):
        self.client.force_login(self.user)
        self._fill_cart(quantity=2)

        res = self._post(recipient_name="", address_line="", city="")

        self.assertEqual(res.status_code, 200)  # re-rendered with errors
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Payment.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(CartItem.objects.filter(cart__user=self.user).count(), 1)

    # ---- stock shortfall rolls back ----
    def test_stock_shortfall_creates_no_order(self):
        self.client.force_login(self.user)
        self._fill_cart(quantity=10)  # more than the 5 in stock

        res = self._post()

        self.assertRedirects(res, self.url)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Address.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)

    # ---- shipping by delivery method ----
    def test_pickup_has_no_shipping(self):
        self.client.force_login(self.user)
        self._fill_cart(quantity=1)
        self._post(delivery_method="pickup")
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.shipping_fee, 0)
        self.assertEqual(order.total, 100)

    def test_delivery_has_shipping(self):
        self.client.force_login(self.user)
        self._fill_cart(quantity=1)
        self._post(delivery_method="delivery")
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.shipping_fee, 100)
        self.assertEqual(order.total, 200)

    # ---- line totals on the summaries ----
    def test_checkout_summary_shows_line_total(self):
        self.client.force_login(self.user)
        self._fill_cart(quantity=2)
        res = self.client.get(self.url)
        self.assertContains(res, '<span class="s-price">Rs. 200</span>')  # 2 x Rs. 100

    def test_order_success_shows_line_total(self):
        self.client.force_login(self.user)
        self._fill_cart(quantity=2)
        res = self._post()
        res = self.client.get(res.url)
        self.assertContains(res, '<span class="s-price">Rs. 200</span>')

    # ---- empty cart ----
    def test_checkout_get_with_empty_cart_redirects_to_cart(self):
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertRedirects(res, reverse("cart:cart_detail"))


class LineTotalAndFormTests(TestCase):
    def test_order_item_line_total_uses_saved_price(self):
        user = User.objects.create_user(username="asha", email="asha@example.com", password="pass12345")
        category = Category.objects.create(name="Fruits", slug="fruits")
        product = Product.objects.create(category=category, name="Apple", slug="apple", price=100, stock=5)
        order = Order.objects.create(user=user, total=300, address="Kathmandu")
        item = OrderItem.objects.create(order=order, product=product, quantity=3, price=100)

        # A later price change must not change what the customer paid.
        product.price = 150
        product.save()
        item.refresh_from_db()
        self.assertEqual(item.line_total, 300)

    def test_address_form_has_autofill_and_keyboard_hints(self):
        form = AddressForm()
        self.assertIn('autocomplete="name"', str(form["recipient_name"]))
        self.assertIn('autocomplete="tel"', str(form["phone"]))
        self.assertIn('inputmode="tel"', str(form["phone"]))
        self.assertIn('autocomplete="address-line1"', str(form["address_line"]))
        self.assertIn('autocomplete="address-level2"', str(form["city"]))
        self.assertIn('autocomplete="address-line2"', str(form["area"]))


class OrderSuccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="asha", email="asha@example.com", password="pass12345"
        )
        self.other = User.objects.create_user(
            username="bob", email="bob@example.com", password="pass12345"
        )
        self.order = Order.objects.create(
            user=self.user, status=Order.Status.PENDING,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            subtotal=100, shipping_fee=100, total=200, address="Asha, Kathmandu",
        )
        self.url = reverse("orders:order_success", args=[self.order.pk])

    def test_login_required(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/login", res.url)

    def test_owner_can_view(self):
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, f"#{self.order.pk}")

    def test_other_user_gets_404(self):
        self.client.force_login(self.other)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 404)


class OrderAdminActionTests(TestCase):
    def setUp(self):
        self.admin = OrderAdmin(Order, admin.site)
        self.user = User.objects.create_user(
            username="asha", email="asha@example.com", password="pass12345"
        )
        self.category = Category.objects.create(name="Fruits", slug="fruits")
        # Stock is 3 as if 2 units were already sold on this order.
        self.product = Product.objects.create(
            category=self.category, name="Apple", slug="apple", price=100, stock=3
        )
        self.order = Order.objects.create(
            user=self.user, status=Order.Status.PENDING,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            subtotal=200, shipping_fee=100, total=300, address="Asha, Kathmandu",
        )
        OrderItem.objects.create(
            order=self.order, product=self.product, quantity=2, price=100
        )
        self.payment = Payment.objects.create(
            order=self.order, method=Payment.Method.COD,
            status=Payment.Status.PENDING, amount=300,
        )

    def _request(self):
        # message_user needs a request with a message store attached.
        request = RequestFactory().post("/admin/orders/order/")
        request.user = self.user
        setattr(request, "session", "session")
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_cancel_restores_stock(self):
        self.admin.mark_cancelled(self._request(), Order.objects.filter(pk=self.order.pk))
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 5)  # 3 + 2 restored
        self.assertEqual(self.payment.status, Payment.Status.FAILED)

    def test_cancel_twice_does_not_restore_stock_twice(self):
        qs = Order.objects.filter(pk=self.order.pk)
        self.admin.mark_cancelled(self._request(), qs)
        self.admin.mark_cancelled(self._request(), qs)  # second run is a no-op
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)  # not 7

    def test_status_actions_change_status(self):
        qs = Order.objects.filter(pk=self.order.pk)

        self.admin.mark_confirmed(self._request(), qs)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)

        self.admin.mark_out_for_delivery(self._request(), qs)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.OUT_FOR_DELIVERY)

        self.admin.mark_delivered(self._request(), qs)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
