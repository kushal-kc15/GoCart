import re
from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db import connection
from django.db.models import ProtectedError
from django.test import Client, RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth import get_user_model

from products.models import Category, Product, ProductImage
from cart.models import Cart, CartItem
from accounts.models import Address
from .admin import OrderAdmin
from .forms import AddressForm
from .models import Order, OrderItem, OrderStatusChange, Payment

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

    def test_checkout_records_order_placed_in_history(self):
        self.client.force_login(self.user)
        self._fill_cart(quantity=1)
        self._post()
        order = Order.objects.get(user=self.user)
        change = order.status_changes.get()
        self.assertEqual(change.from_status, "")
        self.assertEqual(change.to_status, Order.Status.PENDING)
        self.assertEqual(change.changed_by, self.user)
        self.assertEqual(change.note, "Order placed")

    def test_failed_checkout_records_no_history(self):
        self.client.force_login(self.user)
        self._fill_cart(quantity=10)  # more than in stock
        self._post()
        self.assertFalse(OrderStatusChange.objects.exists())

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

    # ---- phone check (shared with the profile: accounts/validators.py) ----
    def test_invalid_phone_creates_no_order(self):
        self.client.force_login(self.user)
        self._fill_cart(quantity=1)
        for phone in ("12345", "9612345678", "98123456789"):
            with self.subTest(phone=phone):
                res = self._post(phone=phone)
                self.assertEqual(res.status_code, 200)
                self.assertIn("phone", res.context["form"].errors)
                self.assertContains(res, "Enter a 10-digit mobile number starting with 97 or 98.")
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Address.objects.exists())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)

    def test_phone_with_country_code_is_stored_as_ten_digits(self):
        self.client.force_login(self.user)
        self._fill_cart(quantity=1)
        self._post(phone="+977 981 234 5678")
        order = Order.objects.get(user=self.user)
        self.assertEqual(order.shipping_address.phone, "9812345678")
        self.assertTrue(order.address.endswith("9812345678"))

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
        # Links on to the order detail / tracking page.
        self.assertContains(res, reverse("orders:order_detail", args=[self.order.pk]))

    def test_other_user_gets_404(self):
        self.client.force_login(self.other)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 404)


class OrderDetailTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="asha", email="asha@example.com", password="pass12345"
        )
        self.other = User.objects.create_user(
            username="bob", email="bob@example.com", password="pass12345"
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
            order=self.order, product=self.product, product_name="Apple", quantity=2, price=100
        )
        self.payment = Payment.objects.create(
            order=self.order, method=Payment.Method.COD,
            status=Payment.Status.PENDING, amount=300,
        )
        self.url = reverse("orders:order_detail", args=[self.order.pk])
        self.cancel_url = reverse("orders:cancel_order", args=[self.order.pk])

    def _set_status(self, status):
        Order.objects.filter(pk=self.order.pk).update(status=status)

    # ---- access ----
    def test_login_required(self):
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/accounts/login", res.url)

    def test_other_user_gets_404(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.cancel_url).status_code, 404)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)

    def test_owner_sees_order_details(self):
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, f"ORDER #{self.order.pk}")
        self.assertContains(res, '<span class="s-price">Rs. 200</span>')
        self.assertContains(res, "Cash on Delivery")
        self.assertContains(res, "Asha, Kathmandu")

    # ---- tracker ----
    def test_tracker_shows_the_right_step(self):
        self.client.force_login(self.user)
        expected = {
            Order.Status.PENDING: "Pending",
            Order.Status.CONFIRMED: "Confirmed",
            Order.Status.PACKED: "Packed",
            Order.Status.OUT_FOR_DELIVERY: "Out for delivery",
            Order.Status.DELIVERED: "Delivered",
        }
        for status, label in expected.items():
            with self.subTest(status=status):
                self._set_status(status)
                steps = self.client.get(self.url).context["steps"]
                self.assertEqual(
                    [s["label"] for s in steps],
                    ["Pending", "Confirmed", "Packed", "Out for delivery", "Delivered"],
                )
                self.assertEqual([s["label"] for s in steps if s["current"]], [label])
                # Every step up to the current one is done, none after it.
                done = [s["done"] for s in steps]
                current = done.count(True) - 1
                self.assertEqual(steps[current]["label"], label)
                self.assertNotIn(True, done[current + 1:])

    def test_pickup_tracker_has_pickup_steps(self):
        Order.objects.filter(pk=self.order.pk).update(
            delivery_method=Order.DeliveryMethod.PICKUP, status=Order.Status.READY_FOR_PICKUP
        )
        self.client.force_login(self.user)
        steps = self.client.get(self.url).context["steps"]
        self.assertEqual(
            [s["label"] for s in steps],
            ["Pending", "Confirmed", "Packed", "Ready for pickup", "Picked up"],
        )
        self.assertEqual([s["label"] for s in steps if s["current"]], ["Ready for pickup"])

    def test_status_history_is_not_shown_to_customers(self):
        staff = User.objects.create_user(
            username="staff", email="staff@example.com", password="pass12345", is_staff=True
        )
        self.order.change_status(Order.Status.CONFIRMED, changed_by=staff, note="Called the customer")
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertNotContains(res, "Called the customer")
        self.assertNotContains(res, "staff@example.com")

    def test_cancelled_order_shows_cancelled_state(self):
        self._set_status(Order.Status.CANCELLED)
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertContains(res, "track-cancelled")
        self.assertNotContains(res, 'class="tracker"')
        self.assertNotContains(res, self.cancel_url)

    # ---- cancel ----
    def test_cancel_button_only_while_pending(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url), self.cancel_url)
        self._set_status(Order.Status.CONFIRMED)
        self.assertNotContains(self.client.get(self.url), self.cancel_url)

    def test_cancel_pending_order_restores_stock(self):
        self.client.force_login(self.user)
        res = self.client.post(self.cancel_url)
        self.assertRedirects(res, self.url)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 5)  # 3 + 2 restored
        self.assertEqual(self.payment.status, Payment.Status.FAILED)
        # Recorded in the history with the customer and the automatic note.
        change = self.order.status_changes.get()
        self.assertEqual(
            (change.from_status, change.to_status, change.changed_by, change.note),
            (Order.Status.PENDING, Order.Status.CANCELLED, self.user, "Cancelled by customer"),
        )

    def test_cancel_twice_restores_stock_once(self):
        self.client.force_login(self.user)
        self.client.post(self.cancel_url)
        self.client.post(self.cancel_url)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)  # not 7

    def test_cannot_cancel_after_confirmed(self):
        self._set_status(Order.Status.CONFIRMED)
        self.client.force_login(self.user)
        self.client.post(self.cancel_url)
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        self.assertEqual(self.product.stock, 3)

    def test_cancel_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.cancel_url).status_code, 405)


class OrderListTests(TestCase):
    url = reverse("orders:order_list")

    def setUp(self):
        self.user = User.objects.create_user(
            username="asha", email="asha@example.com", password="pass12345"
        )
        self.other = User.objects.create_user(
            username="bob", email="bob@example.com", password="pass12345"
        )
        category = Category.objects.create(name="Fruits", slug="fruits")
        self.products = []
        for i in range(5):
            product = Product.objects.create(
                category=category, name=f"Fruit {i}", slug=f"fruit-{i}", price=100, stock=50
            )
            ProductImage.objects.create(product=product, image=f"products/gallery/fruit-{i}.jpg")
            self.products.append(product)
        self.client.force_login(self.user)

    def _order(self, user=None, status=Order.Status.PENDING, items=1):
        order = Order.objects.create(
            user=user or self.user, status=status, total=100 * items, address="Kathmandu"
        )
        for product in self.products[:items]:
            OrderItem.objects.create(
                order=order, product=product, product_name=product.name, quantity=1, price=100
            )
        return order

    def _shown(self, response):
        return [order.pk for order in response.context["page_obj"]]

    # ---- access and order ----
    def test_login_required(self):
        self.client.logout()
        res = self.client.get(self.url)
        self.assertRedirects(res, f"{reverse('accounts:login')}?next={self.url}")

    def test_only_own_orders_newest_first(self):
        old = self._order()
        Order.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=2))
        new = self._order()
        theirs = self._order(user=self.other)
        res = self.client.get(self.url)
        self.assertEqual(self._shown(res), [new.pk, old.pk])
        self.assertContains(res, f'href="{reverse("orders:order_detail", args=[new.pk])}"')
        self.assertNotContains(res, f'href="{reverse("orders:order_detail", args=[theirs.pk])}"')

    # ---- tabs ----
    def test_status_tabs_filter_orders(self):
        orders = {status: self._order(status=status).pk for status in Order.Status.values}
        active = {
            orders[s]
            for s in ("pending", "confirmed", "packed", "out_for_delivery", "ready_for_pickup")
        }
        expected = {
            "active": active,
            "delivered": {orders["delivered"]},
            "cancelled": {orders["cancelled"]},
            "all": set(orders.values()),
            "nonsense": set(orders.values()),  # unknown tab shows everything
        }
        for tab, pks in expected.items():
            with self.subTest(tab=tab):
                res = self.client.get(self.url, {"status": tab})
                self.assertEqual(set(self._shown(res)), pks)

    def test_badge_colour_and_text(self):
        expected = {
            Order.Status.PENDING: ("gc-badge--warning", "Pending"),
            Order.Status.PACKED: ("gc-badge--warning", "Packed"),
            Order.Status.READY_FOR_PICKUP: ("gc-badge--warning", "Ready for pickup"),
            Order.Status.DELIVERED: ("gc-badge--success", "Delivered"),
            Order.Status.CANCELLED: ("gc-badge--danger", "Cancelled"),
        }
        for status, (css, text) in expected.items():
            with self.subTest(status=status):
                Order.objects.all().delete()
                self._order(status=status)
                self.assertContains(
                    self.client.get(self.url), f'<span class="gc-badge {css}">{text}</span>', html=True
                )

    def test_badge_shows_picked_up_for_a_collected_pickup_order(self):
        order = self._order(status=Order.Status.DELIVERED)
        Order.objects.filter(pk=order.pk).update(delivery_method=Order.DeliveryMethod.PICKUP)
        self.assertContains(
            self.client.get(self.url), '<span class="gc-badge gc-badge--success">Picked up</span>', html=True
        )

    def test_current_tab_is_marked(self):
        res = self.client.get(self.url, {"status": "delivered"})
        self.assertContains(
            res, f'<a href="{self.url}?status=delivered" class="active" aria-current="page">Delivered</a>',
            html=True,
        )

    def test_empty_state_per_tab(self):
        expected = {
            "all": "You haven't placed any orders yet.",
            "active": "You have no active orders.",
            "delivered": "No delivered orders yet.",
            "cancelled": "No cancelled orders.",
        }
        for tab, text in expected.items():
            with self.subTest(tab=tab):
                self.assertContains(self.client.get(self.url, {"status": tab}), text)

    # ---- pagination ----
    def test_ten_per_page_and_page_links_keep_the_tab(self):
        for _ in range(12):
            self._order(status=Order.Status.DELIVERED)
        first = self.client.get(self.url, {"status": "delivered"})
        self.assertEqual(len(first.context["page_obj"]), 10)
        nav = first.content.decode().split('class="ol-pagination"', 1)[1].split("</nav>", 1)[0]
        self.assertRegex(nav, r'href="\?status=delivered&(amp;)?page=2"')
        second = self.client.get(self.url, {"status": "delivered", "page": 2})
        self.assertEqual(len(second.context["page_obj"]), 2)

    # ---- order cards ----
    def test_up_to_three_thumbnails_and_more_count(self):
        self._order(items=5)
        res = self.client.get(self.url)
        self.assertEqual(res.content.decode().count('class="ol-thumb"'), 3)
        self.assertContains(res, "/media/products/gallery/fruit-0.jpg")
        self.assertContains(res, "+2 more")
        self.assertContains(res, "5 items")

    def test_single_item_order_has_no_more_label(self):
        self._order(items=1)
        html = self.client.get(self.url).content.decode()
        self.assertRegex(html, r"\b1 item\b(?!s)")
        self.assertNotIn("more</span>", html)

    def test_no_extra_queries_per_order(self):
        self._order(items=3)
        with CaptureQueriesContext(connection) as one_order:
            self.client.get(self.url)
        for _ in range(4):
            self._order(items=3)
        with CaptureQueriesContext(connection) as five_orders:
            res = self.client.get(self.url)
        self.assertEqual(len(res.context["page_obj"]), 5)
        self.assertEqual(len(five_orders), len(one_order))

    # ---- cancel from the list ----
    def test_cancel_button_only_for_pending_orders(self):
        pending = self._order(status=Order.Status.PENDING)
        confirmed = self._order(status=Order.Status.CONFIRMED)
        res = self.client.get(self.url)
        self.assertContains(res, reverse("orders:cancel_order", args=[pending.pk]))
        self.assertNotContains(res, reverse("orders:cancel_order", args=[confirmed.pk]))

    def test_cancel_from_the_list_comes_back_to_it(self):
        order = self._order()
        next_url = f"{self.url}?status=active"
        res = self.client.post(reverse("orders:cancel_order", args=[order.pk]), {"next": next_url})
        self.assertRedirects(res, next_url)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_cancel_ignores_an_outside_next(self):
        order = self._order()
        res = self.client.post(
            reverse("orders:cancel_order", args=[order.pk]), {"next": "https://evil.example/"}
        )
        self.assertRedirects(res, reverse("orders:order_detail", args=[order.pk]))

    # ---- links to the list ----
    def test_order_detail_and_success_link_to_the_list(self):
        order = self._order()
        detail = self.client.get(reverse("orders:order_detail", args=[order.pk]))
        self.assertContains(
            detail, f'<a href="{self.url}" class="btn-line btn-ghost">Back to my orders</a>', html=True
        )
        success = self.client.get(reverse("orders:order_success", args=[order.pk]))
        self.assertContains(success, f'<a href="{self.url}">My orders</a>', html=True)


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

    def _messages(self, request):
        return [str(m) for m in request._messages]

    def test_only_forward_bulk_actions(self):
        # Cancel and Delivered are done one order at a time, from the order page.
        self.assertEqual(self.admin.actions, ["mark_confirmed", "mark_packed", "mark_out_for_delivery"])

    def test_status_actions_step_through_the_flow(self):
        qs = Order.objects.filter(pk=self.order.pk)
        steps = [
            (self.admin.mark_confirmed, Order.Status.CONFIRMED),
            (self.admin.mark_packed, Order.Status.PACKED),
            (self.admin.mark_out_for_delivery, Order.Status.OUT_FOR_DELIVERY),
        ]
        for action, status in steps:
            request = self._request()
            action(request, qs)
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, status)
            self.assertEqual(self._messages(request), [f"1 order(s) marked as {status.label.lower()}."])
        # Each step is in the history, made by the staff user.
        self.assertEqual(
            [(c.to_status, c.changed_by) for c in self.order.status_changes.order_by("id")],
            [(s, self.user) for _, s in steps],
        )

    def test_actions_skip_orders_that_cannot_take_the_step(self):
        pickup = Order.objects.create(
            user=self.user, status=Order.Status.PACKED,
            delivery_method=Order.DeliveryMethod.PICKUP, total=100, address="Kathmandu",
        )
        request = self._request()
        # The pending order would skip Confirmed/Packed; the pickup order isn't delivered.
        self.admin.mark_out_for_delivery(request, Order.objects.filter(pk__in=[self.order.pk, pickup.pk]))
        self.assertEqual(
            self._messages(request),
            ["0 order(s) marked as out for delivery. 2 skipped (not allowed from their current status)."],
        )
        self.order.refresh_from_db()
        pickup.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(pickup.status, Order.Status.PACKED)
        self.assertFalse(OrderStatusChange.objects.exists())

    def test_cancelled_order_cannot_be_confirmed_again(self):
        self.order.change_status(Order.Status.CANCELLED, changed_by=self.user, note="Out of stock")
        self.admin.mark_confirmed(self._request(), Order.objects.filter(pk=self.order.pk))
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 5)  # restored once, and the order stays cancelled


class StatusFlowTests(TestCase):
    """Order.change_status: which steps are allowed, and what a cancel does."""

    def setUp(self):
        self.customer = User.objects.create_user(
            username="asha", email="asha@example.com", password="pass12345"
        )
        self.staff = User.objects.create_user(
            username="staff", email="staff@example.com", password="pass12345", is_staff=True
        )
        category = Category.objects.create(name="Fruits", slug="fruits")
        # Stock is 3 as if 2 units were already sold on each order.
        self.product = Product.objects.create(
            category=category, name="Apple", slug="apple", price=100, stock=3
        )

    def _order(self, status=Order.Status.PENDING, method=Order.DeliveryMethod.DELIVERY):
        order = Order.objects.create(
            user=self.customer, status=status, delivery_method=method,
            subtotal=200, total=200, address="Kathmandu",
        )
        OrderItem.objects.create(order=order, product=self.product, product_name="Apple", quantity=2, price=100)
        Payment.objects.create(order=order, method=Payment.Method.COD, amount=200)
        return order

    def _stock(self):
        self.product.refresh_from_db()
        return self.product.stock

    # ---- allowed steps ----
    def test_delivery_order_walks_the_whole_path(self):
        order = self._order()
        for status in (Order.Status.CONFIRMED, Order.Status.PACKED,
                       Order.Status.OUT_FOR_DELIVERY, Order.Status.DELIVERED):
            with self.subTest(status=status):
                self.assertTrue(order.change_status(status, changed_by=self.staff))
                order.refresh_from_db()
                self.assertEqual(order.status, status)
        self.assertEqual(order.allowed_next_statuses(), [])
        self.assertEqual(self._stock(), 3)  # delivering never touches stock

    def test_pickup_order_walks_the_whole_path(self):
        order = self._order(method=Order.DeliveryMethod.PICKUP)
        for status in (Order.Status.CONFIRMED, Order.Status.PACKED,
                       Order.Status.READY_FOR_PICKUP, Order.Status.DELIVERED):
            with self.subTest(status=status):
                self.assertTrue(order.change_status(status, changed_by=self.staff))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DELIVERED)
        self.assertEqual(order.status_label, "Picked up")

    def test_change_updates_updated_at(self):
        order = self._order()
        Order.objects.filter(pk=order.pk).update(updated_at=timezone.now() - timedelta(days=1))
        order.refresh_from_db()
        before = order.updated_at
        order.change_status(Order.Status.CONFIRMED)
        order.refresh_from_db()
        self.assertGreater(order.updated_at, before)

    # ---- refused steps ----
    def test_disallowed_steps_change_nothing(self):
        cases = [
            # (method, current status, attempted status)
            ("delivery", "pending", "packed"),              # skips Confirmed
            ("delivery", "confirmed", "delivered"),         # skips ahead
            ("delivery", "confirmed", "pending"),           # backwards
            ("delivery", "delivered", "pending"),           # final
            ("delivery", "delivered", "cancelled"),         # final
            ("delivery", "cancelled", "confirmed"),         # final
            ("delivery", "packed", "ready_for_pickup"),     # pickup-only step
            ("pickup", "packed", "out_for_delivery"),       # delivery-only step
            ("delivery", "pending", "pending"),             # same status
            ("delivery", "pending", "nonsense"),
        ]
        for method, current, attempted in cases:
            with self.subTest(method=method, current=current, attempted=attempted):
                order = self._order(status=current, method=method)
                self.assertFalse(order.change_status(attempted, changed_by=self.staff, note="Try"))
                self.assertEqual(order.status, current)
                order.refresh_from_db()
                self.assertEqual(order.status, current)
                self.assertFalse(order.status_changes.exists())
                self.assertEqual(self._stock(), 3)

    # ---- cancelling ----
    def test_cancel_from_every_open_status_restores_stock_once(self):
        cases = [
            ("delivery", "pending"), ("delivery", "confirmed"), ("delivery", "packed"),
            ("delivery", "out_for_delivery"), ("pickup", "ready_for_pickup"),
        ]
        for method, status in cases:
            with self.subTest(status=status):
                order = self._order(status=status, method=method)
                stock = self._stock()
                self.assertTrue(order.change_status(Order.Status.CANCELLED, changed_by=self.staff, note="Refused"))
                self.assertEqual(self._stock(), stock + 2)
                self.assertEqual(Payment.objects.get(order=order).status, Payment.Status.FAILED)
                # A second cancel does nothing.
                self.assertFalse(order.change_status(Order.Status.CANCELLED, changed_by=self.staff, note="Again"))
                self.assertEqual(self._stock(), stock + 2)
                self.assertEqual(order.status_changes.count(), 1)

    def test_cancel_needs_a_note(self):
        order = self._order()
        for note in ("", "   "):
            with self.subTest(note=note):
                self.assertFalse(order.change_status(Order.Status.CANCELLED, changed_by=self.staff, note=note))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(self._stock(), 3)
        self.assertEqual(Payment.objects.get(order=order).status, Payment.Status.PENDING)
        self.assertFalse(order.status_changes.exists())

    def test_stale_copy_cannot_cancel_twice(self):
        order = self._order()
        stale = Order.objects.get(pk=order.pk)  # e.g. a second browser tab
        self.assertTrue(order.change_status(Order.Status.CANCELLED, changed_by=self.staff, note="One"))
        self.assertFalse(stale.change_status(Order.Status.CANCELLED, changed_by=self.staff, note="Two"))
        self.assertEqual(self._stock(), 5)  # 3 + 2, not 7
        self.assertEqual(order.status_changes.count(), 1)

    def test_stale_copy_cannot_repeat_a_step(self):
        order = self._order()
        stale = Order.objects.get(pk=order.pk)
        self.assertTrue(order.change_status(Order.Status.CONFIRMED, changed_by=self.staff))
        self.assertFalse(stale.change_status(Order.Status.CONFIRMED, changed_by=self.staff))
        self.assertEqual(order.status_changes.count(), 1)

    # ---- history ----
    def test_every_change_is_recorded(self):
        order = self._order()
        order.change_status(Order.Status.CONFIRMED, changed_by=self.staff)
        order.change_status(Order.Status.PACKED, changed_by=self.staff, note="  Two bags  ")
        order.change_status(Order.Status.CANCELLED, changed_by=self.staff, note="Customer refused")
        rows = [
            (c.from_status, c.to_status, c.changed_by, c.note)
            for c in order.status_changes.order_by("id")
        ]
        self.assertEqual(rows, [
            ("pending", "confirmed", self.staff, ""),
            ("confirmed", "packed", self.staff, "Two bags"),
            ("packed", "cancelled", self.staff, "Customer refused"),
        ])
        # Newest first by default.
        self.assertEqual(order.status_changes.first().to_status, Order.Status.CANCELLED)

    def test_history_keeps_rows_when_the_staff_user_is_deleted(self):
        order = self._order()
        order.change_status(Order.Status.CONFIRMED, changed_by=self.staff)
        self.staff.delete()
        change = order.status_changes.get()
        self.assertIsNone(change.changed_by)
        self.assertEqual(change.to_status, Order.Status.CONFIRMED)


class AdminTestData:
    """Shared setup for the admin tests: a superuser, a customer and one order."""

    def setUp(self):
        self.boss = User.objects.create_superuser(
            username="boss", email="boss@example.com", password="pass12345"
        )
        self.customer = User.objects.create_user(
            username="asha", email="asha@example.com", password="pass12345",
            first_name="Asha", last_name="Sharma",
        )
        category = Category.objects.create(name="Fruits", slug="fruits")
        # Stock is 3 as if 2 units were already sold on the order.
        self.product = Product.objects.create(
            category=category, name="Apple", slug="apple", price=100, stock=3
        )
        self.order = self._order(phone="9800000001")
        self.client.force_login(self.boss)

    def _order(self, user=None, status=Order.Status.PENDING,
               method=Order.DeliveryMethod.DELIVERY, phone="9800000001", total=300):
        user = user or self.customer
        address = Address.objects.create(
            user=user, recipient_name=user.get_full_name(), phone=phone,
            address_line="12 Market Rd", city="Kathmandu",
        )
        order = Order.objects.create(
            user=user, shipping_address=address, status=status, delivery_method=method,
            subtotal=total - 100, shipping_fee=100, total=total,
            address=f"{user.get_full_name()}, 12 Market Rd, Kathmandu, {phone}",
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name="Apple", quantity=2, price=100
        )
        Payment.objects.create(order=order, method=Payment.Method.COD, amount=total)
        return order

    def _change_url(self, order=None):
        return reverse("admin:orders_order_change", args=[(order or self.order).pk])

    def _status_url(self, order=None):
        return reverse("admin:orders_order_status", args=[(order or self.order).pk])

    def _messages(self, response):
        return [str(m) for m in get_messages(response.wsgi_request)]


class AdminOrderPageTests(AdminTestData, TestCase):
    # ---- read-only page ----
    def test_page_shows_the_order_read_only(self):
        res = self.client.get(self._change_url())
        self.assertEqual(res.status_code, 200)
        for text in ("Asha Sharma", "asha@example.com", "9800000001", "12 Market Rd", "Apple"):
            self.assertContains(res, text)
        # No editable status, totals, address or customer, and no Save buttons.
        for html in ('id="id_status"', 'id="id_total"', 'id="id_address"', 'id="id_user"', 'name="_save"'):
            self.assertNotContains(res, html)
        # The status field is a badge, not the raw (value, text) pair.
        self.assertNotContains(res, "(&#x27;pending&#x27;")
        self.assertNotContains(res, "('pending'")

    def test_saving_the_order_page_is_refused(self):
        res = self.client.post(self._change_url(), {"status": "delivered", "total": "1"})
        self.assertEqual(res.status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual((self.order.status, self.order.total), (Order.Status.PENDING, 300))

    def test_items_show_the_saved_name_and_price(self):
        self.product.name = "Green Apple"
        self.product.price = 175
        self.product.save()
        res = self.client.get(self._change_url())
        self.assertContains(res, "Apple")
        self.assertNotContains(res, "Green Apple")
        self.assertNotContains(res, "175")
        self.assertContains(res, "200.00")  # line total: 2 x the saved 100

    def test_history_is_shown(self):
        self.order.change_status(Order.Status.CONFIRMED, changed_by=self.boss, note="Called the customer")
        res = self.client.get(self._change_url())
        self.assertContains(res, "Status history")
        self.assertContains(res, "Called the customer")

    def test_no_add_and_no_delete(self):
        self.assertEqual(self.client.get(reverse("admin:orders_order_add")).status_code, 403)
        delete_url = reverse("admin:orders_order_delete", args=[self.order.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 403)
        self.client.post(delete_url, {"post": "yes"})
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
        changelist = self.client.get(reverse("admin:orders_order_changelist"))
        self.assertNotContains(changelist, 'value="delete_selected"')

    def test_items_and_history_have_no_admin_of_their_own(self):
        self.assertFalse(admin.site.is_registered(OrderItem))
        self.assertFalse(admin.site.is_registered(OrderStatusChange))

    # ---- status panel buttons ----
    def test_only_the_allowed_buttons_appear(self):
        cases = [
            # (method, status, buttons shown, buttons not shown)
            ("delivery", "pending", ["Confirm order", "Cancel order"], ["Mark as packed"]),
            ("delivery", "confirmed", ["Mark as packed", "Cancel order"], ["Confirm order"]),
            ("delivery", "packed", ["Mark out for delivery", "Cancel order"], ["Mark ready for pickup"]),
            ("pickup", "packed", ["Mark ready for pickup", "Cancel order"], ["Mark out for delivery"]),
            ("delivery", "out_for_delivery", ["Mark as delivered", "Cancel order"], ["Mark as picked up"]),
            ("pickup", "ready_for_pickup", ["Mark as picked up", "Cancel order"], ["Mark as delivered"]),
            ("delivery", "delivered", ["Mark cash collected"], ["Cancel order", "Mark as delivered"]),
            ("delivery", "cancelled", ["This order is finished"], ["Cancel order", "Confirm order"]),
        ]
        for method, status, shown, hidden in cases:
            with self.subTest(method=method, status=status):
                order = self._order(status=status, method=method)
                res = self.client.get(self._change_url(order))
                for text in shown:
                    self.assertContains(res, text)
                for text in hidden:
                    self.assertNotContains(res, text)

    def test_staff_without_change_permission_sees_no_buttons(self):
        viewer = User.objects.create_user(
            username="viewer", email="viewer@example.com", password="pass12345", is_staff=True
        )
        viewer.user_permissions.add(Permission.objects.get(codename="view_order"))
        self.client.force_login(viewer)
        res = self.client.get(self._change_url())
        self.assertContains(res, "You can view this order but not change it.")
        self.assertNotContains(res, "Confirm order")
        res = self.client.post(self._status_url(), {"status": "confirmed"})
        self.assertEqual(res.status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    # ---- status panel posts ----
    def test_step_changes_status_and_records_the_staff_user(self):
        res = self.client.post(self._status_url(), {"status": "confirmed", "note": "Called the customer"})
        self.assertRedirects(res, self._change_url())
        self.assertEqual(self._messages(res), [f"Order #{self.order.pk} is now confirmed."])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        change = self.order.status_changes.get()
        self.assertEqual((change.changed_by, change.note), (self.boss, "Called the customer"))

    def test_picked_up_message_for_pickup_orders(self):
        order = self._order(status=Order.Status.READY_FOR_PICKUP, method=Order.DeliveryMethod.PICKUP)
        res = self.client.post(self._status_url(order), {"status": "delivered"})
        self.assertEqual(self._messages(res), [f"Order #{order.pk} is now picked up."])

    def test_disallowed_step_shows_an_error_and_changes_nothing(self):
        for status in ("delivered", "packed", "pending", "nonsense", ""):
            with self.subTest(status=status):
                res = self.client.post(self._status_url(), {"status": status})
                self.assertRedirects(res, self._change_url())
                self.assertIn("Nothing was changed.", self._messages(res)[-1])
                self.order.refresh_from_db()
                self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertFalse(self.order.status_changes.exists())

    def test_cancel_with_a_blank_note_is_refused(self):
        for note in ("", "   "):
            with self.subTest(note=note):
                res = self.client.post(self._status_url(), {"status": "cancelled", "note": note})
                self.assertEqual(
                    self._messages(res)[-1], "Please write why the order is cancelled. Nothing was changed."
                )
        self.order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)
        self.assertEqual(self.product.stock, 3)
        self.assertFalse(self.order.status_changes.exists())

    def test_cancel_with_a_note_restores_stock(self):
        order = self._order(status=Order.Status.OUT_FOR_DELIVERY)
        res = self.client.post(self._status_url(order), {"status": "cancelled", "note": "Customer refused"})
        self.assertEqual(self._messages(res), [f"Order #{order.pk} is now cancelled."])
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertEqual(self.product.stock, 5)  # 3 + 2
        self.assertEqual(order.payment.status, Payment.Status.FAILED)
        self.assertEqual(order.status_changes.get().note, "Customer refused")

    # ---- access ----
    def test_customers_are_sent_to_the_admin_login(self):
        self.client.force_login(self.customer)
        for url in (self._change_url(), self._status_url()):
            with self.subTest(url=url):
                res = self.client.post(url, {"status": "confirmed"})
                self.assertEqual(res.status_code, 302)
                self.assertIn(reverse("admin:login"), res.url)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_status_post_needs_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.boss)
        res = client.post(self._status_url(), {"status": "confirmed"})
        self.assertEqual(res.status_code, 403)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PENDING)

    def test_status_url_only_accepts_post(self):
        self.assertEqual(self.client.get(self._status_url()).status_code, 405)


class AdminOrderListTests(AdminTestData, TestCase):
    url = reverse("admin:orders_order_changelist")

    def _shown(self, **params):
        res = self.client.get(self.url, params)
        self.assertEqual(res.status_code, 200)
        return {order.pk for order in res.context["cl"].result_list}

    def test_columns_and_badges(self):
        self.order.change_status(Order.Status.CONFIRMED, changed_by=self.boss)
        res = self.client.get(self.url)
        self.assertContains(res, f"#{self.order.pk}")
        self.assertContains(res, "Asha Sharma")
        self.assertContains(res, "9800000001")
        self.assertContains(res, "bg-blue-100")  # the "info" colour of the Confirmed badge
        self.assertContains(res, "COD pending")

    def test_order_number_links_to_each_order_page(self):
        orders = [
            self.order,
            self._order(status=Order.Status.CONFIRMED),
            self._order(status=Order.Status.DELIVERED, method=Order.DeliveryMethod.PICKUP),
        ]
        html = self.client.get(self.url).content.decode()
        for order in orders:
            with self.subTest(order=order.pk):
                change_url = reverse("admin:orders_order_change", args=[order.pk])
                # The "Order" column is a plain link to the order page...
                self.assertRegex(html, rf'<a href="{re.escape(change_url)}"[^>]*>#{order.pk}</a>')
                # ...and the row still has its checkbox for the bulk actions.
                self.assertRegex(html, rf'name="_selected_action" value="{order.pk}"')
        # With a search, the link keeps the search so "back" returns to it.
        html = self.client.get(self.url, {"q": f"#{self.order.pk}"}).content.decode()
        change_url = reverse("admin:orders_order_change", args=[self.order.pk])
        self.assertRegex(
            html, rf'<a href="{re.escape(change_url)}\?_changelist_filters=[^"]*"[^>]*>#{self.order.pk}</a>'
        )

    def test_search(self):
        bina = User.objects.create_user(
            username="bina", email="bina@example.com", password="pass12345",
            first_name="Bina", last_name="Rai",
        )
        theirs = self._order(user=bina, phone="9811111111")
        mine = self.order
        self.assertEqual(self._shown(q=f"#{theirs.pk}"), {theirs.pk})
        self.assertEqual(self._shown(q=f"  #{mine.pk} "), {mine.pk})
        self.assertIn(theirs.pk, self._shown(q=str(theirs.pk)))
        self.assertEqual(self._shown(q="Sharma"), {mine.pk})
        self.assertEqual(self._shown(q="bina@example"), {theirs.pk})
        self.assertEqual(self._shown(q="9811111111"), {theirs.pk})

    def test_filters(self):
        pickup = self._order(status=Order.Status.PACKED, method=Order.DeliveryMethod.PICKUP)
        old = self._order()
        Order.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=3))
        Payment.objects.filter(order=pickup).update(status=Payment.Status.PAID)
        today = timezone.localdate()

        self.assertEqual(self._shown(status__exact="packed"), {pickup.pk})
        self.assertEqual(self._shown(delivery_method__exact="pickup"), {pickup.pk})
        self.assertEqual(self._shown(payment="paid"), {pickup.pk})
        # "From today to today" includes orders placed during today.
        self.assertEqual(
            self._shown(created_at_from=today.isoformat(), created_at_to=today.isoformat()),
            {self.order.pk, pickup.pk},
        )
        yesterday = (today - timedelta(days=1)).isoformat()
        self.assertEqual(self._shown(created_at_to=yesterday), {old.pk})

    def test_totals_line_leaves_out_cancelled_orders(self):
        self._order(total=500)
        cancelled = self._order(total=1000)
        cancelled.change_status(Order.Status.CANCELLED, changed_by=self.boss, note="Test")
        res = self.client.get(self.url)
        self.assertContains(res, "2 orders · Rs. 800")  # 300 + 500
        # The line follows the search and filters too.
        res = self.client.get(self.url, {"q": f"#{self.order.pk}"})
        self.assertContains(res, "1 order · Rs. 300")

    def test_no_extra_queries_per_order(self):
        with CaptureQueriesContext(connection) as one_order:
            self.client.get(self.url)
        for _ in range(5):
            self._order()
        with CaptureQueriesContext(connection) as six_orders:
            res = self.client.get(self.url)
        self.assertEqual(len(res.context["cl"].result_list), 6)
        self.assertEqual(len(six_orders), len(one_order))


class PackingSlipTests(AdminTestData, TestCase):
    def _slip_url(self, order=None):
        return reverse("admin:orders_order_packing_slip", args=[(order or self.order).pk])

    def test_button_on_the_order_page_opens_a_new_tab(self):
        res = self.client.get(self._change_url())
        self.assertContains(res, "Print packing slip")
        html = res.content.decode()
        link = html.split(f'href="{self._slip_url()}"', 1)[1].split(">", 1)[0]
        self.assertIn('target="_blank"', link)

    def test_slip_shows_the_order(self):
        res = self.client.get(self._slip_url())
        self.assertEqual(res.status_code, 200)
        for text in (
            settings.SHOP_INFO["name"], settings.SHOP_INFO["phone"],
            f"Order #{self.order.pk}", "Asha Sharma", "Phone: 9800000001", "Deliver to:",
            "Rs. 100", "Rs. 200",                      # item price and line total
            "Rs. 300",                                 # order total
            "Cash on Delivery: collect Rs. 300",
            "Received by", "not a tax invoice", "window.print()",
        ):
            self.assertContains(res, text)

    def test_slip_uses_the_saved_name_and_price(self):
        self.product.name = "Green Apple"
        self.product.price = 175
        self.product.save()
        res = self.client.get(self._slip_url())
        self.assertContains(res, "<td>Apple</td>", html=True)
        self.assertNotContains(res, "Green Apple")
        self.assertNotContains(res, "175")

    def test_pickup_and_cancelled_slips(self):
        pickup = self._order(method=Order.DeliveryMethod.PICKUP)
        self.assertContains(self.client.get(self._slip_url(pickup)), "Collects the order from the shop.")
        self.order.change_status(Order.Status.CANCELLED, changed_by=self.boss, note="Test")
        res = self.client.get(self._slip_url())
        self.assertContains(res, "This order is cancelled.")
        self.assertNotContains(res, "collect Rs.")

    def test_staff_with_view_permission_can_print(self):
        viewer = User.objects.create_user(
            username="viewer", email="viewer@example.com", password="pass12345", is_staff=True
        )
        viewer.user_permissions.add(Permission.objects.get(codename="view_order"))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self._slip_url()).status_code, 200)

    def test_customers_cannot_see_slips(self):
        self.client.force_login(self.customer)
        res = self.client.get(self._slip_url())
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("admin:login"), res.url)


class CashCollectedTests(AdminTestData, TestCase):
    def _cash_url(self, order=None):
        return reverse("admin:orders_order_cash_collected", args=[(order or self.order).pk])

    def _payment(self, order=None):
        return Payment.objects.get(order=order or self.order)

    def test_collect_cash_after_delivery(self):
        order = self._order(status=Order.Status.DELIVERED)
        res = self.client.post(self._cash_url(order))
        self.assertRedirects(res, self._change_url(order))
        self.assertEqual(self._messages(res), [f"Cash collected for order #{order.pk}."])
        payment = self._payment(order)
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertIsNotNone(payment.paid_at)
        # The button is gone and the list shows the payment as paid.
        page = self.client.get(self._change_url(order))
        self.assertNotContains(page, "Mark cash collected")
        self.assertContains(page, "This order is finished")
        listing = self.client.get(reverse("admin:orders_order_changelist"))
        self.assertContains(listing, "COD paid")

    def test_second_click_changes_nothing(self):
        order = self._order(status=Order.Status.DELIVERED)
        self.client.post(self._cash_url(order))
        paid_at = self._payment(order).paid_at
        res = self.client.post(self._cash_url(order))
        self.assertIn("Cash can only be recorded once", self._messages(res)[-1])
        self.assertEqual(self._payment(order).paid_at, paid_at)

    def test_refused_before_delivery_and_for_cancelled_orders(self):
        for status in ("pending", "confirmed", "packed", "out_for_delivery", "ready_for_pickup"):
            with self.subTest(status=status):
                order = self._order(status=status)
                self.assertNotContains(self.client.get(self._change_url(order)), "Mark cash collected")
                res = self.client.post(self._cash_url(order))
                self.assertIn("Cash can only be recorded once", self._messages(res)[-1])
                self.assertEqual(self._payment(order).status, Payment.Status.PENDING)
        self.order.change_status(Order.Status.CANCELLED, changed_by=self.boss, note="Test")
        self.client.post(self._cash_url())
        self.assertEqual(self._payment().status, Payment.Status.FAILED)

    def test_model_method(self):
        order = self._order(status=Order.Status.DELIVERED)
        payment = self._payment(order)
        self.assertTrue(payment.can_collect_cash)
        self.assertTrue(payment.mark_cash_collected())
        self.assertEqual(payment.status, Payment.Status.PAID)
        self.assertFalse(payment.can_collect_cash)
        stale = self._payment(order)
        stale.status = Payment.Status.PENDING  # an out-of-date copy
        self.assertFalse(stale.mark_cash_collected())

    def test_needs_change_permission_post_and_csrf(self):
        order = self._order(status=Order.Status.DELIVERED)
        self.assertEqual(self.client.get(self._cash_url(order)).status_code, 405)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.boss)
        self.assertEqual(csrf_client.post(self._cash_url(order)).status_code, 403)

        viewer = User.objects.create_user(
            username="viewer", email="viewer@example.com", password="pass12345", is_staff=True
        )
        viewer.user_permissions.add(Permission.objects.get(codename="view_order"))
        self.client.force_login(viewer)
        self.assertEqual(self.client.post(self._cash_url(order)).status_code, 403)
        self.assertEqual(self._payment(order).status, Payment.Status.PENDING)


class CustomerDeleteTests(AdminTestData, TestCase):
    """Order.user is PROTECT: a customer with orders is deactivated, never deleted."""

    def test_customer_with_orders_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.customer.delete()

        delete_url = reverse("admin:accounts_user_delete", args=[self.customer.pk])
        page = self.client.get(delete_url)
        self.assertContains(page, "Cannot delete")
        self.client.post(delete_url, {"post": "yes"})
        self.assertTrue(User.objects.filter(pk=self.customer.pk).exists())
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())

    def test_customer_without_orders_can_be_deleted(self):
        newcomer = User.objects.create_user(
            username="new", email="new@example.com", password="pass12345"
        )
        Address.objects.create(
            user=newcomer, recipient_name="New", phone="9800000002",
            address_line="1 Road", city="Kathmandu",
        )
        delete_url = reverse("admin:accounts_user_delete", args=[newcomer.pk])
        res = self.client.post(delete_url, {"post": "yes"})
        self.assertRedirects(res, reverse("admin:accounts_user_changelist"))
        self.assertFalse(User.objects.filter(pk=newcomer.pk).exists())
