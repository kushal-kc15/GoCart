from datetime import timedelta

import importlib

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.models import ProtectedError
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from orders.models import Order, OrderItem, Payment
from products.models import Category, Product, Review
from wishlist.models import Wishlist, WishlistItem
from .admin import phone_search_digits
from .models import Address
from .validators import normalize_nepali_phone

User = get_user_model()

STRONG_PASSWORD = "Fresh-Basket-2026"


def signup_data(**overrides):
    data = {
        "first_name": "Asha",
        "last_name": "Sharma",
        "email": "asha@example.com",
        "phone": "9800000000",
        "password1": STRONG_PASSWORD,
        "password2": STRONG_PASSWORD,
    }
    data.update(overrides)
    return data


class AuthPageStylesTests(TestCase):
    def test_auth_base_styles_load_before_page_styles(self):
        for name in ("signup", "login"):
            html = self.client.get(reverse(f"accounts:{name}")).content.decode()
            self.assertLess(html.index("css/dev/auth.css"), html.index(f"css/dev/{name}.css"))


class SignupTests(TestCase):
    url = reverse("accounts:signup")

    def test_form_renders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dev/signup.html")

    def test_success_creates_user_logs_in_and_redirects_home(self):
        response = self.client.post(self.url, signup_data(), follow=True)
        self.assertRedirects(response, reverse("home"))
        user = User.objects.get(email="asha@example.com")
        self.assertTrue(user.check_password(STRONG_PASSWORD))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        self.assertContains(response, "Welcome to GoCart, Asha!")

    def test_email_is_normalised_to_lowercase(self):
        self.client.post(self.url, signup_data(email="Asha@Example.COM"))
        self.assertTrue(User.objects.filter(email="asha@example.com").exists())

    def test_usernames_stay_unique_for_similar_emails(self):
        self.client.post(self.url, signup_data(email="asha@example.com"))
        self.client.logout()
        self.client.post(self.url, signup_data(email="asha@example.org"))
        self.assertEqual(User.objects.count(), 2)

    def test_duplicate_email_error_shown_next_to_email_field(self):
        User.objects.create_user(username="x", email="asha@example.com", password=STRONG_PASSWORD)
        response = self.client.post(self.url, signup_data(email="ASHA@example.com"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("email", response.context["form"].errors)
        self.assertContains(response, "An account with this email already exists.")
        self.assertEqual(User.objects.count(), 1)

    def test_weak_password_error_is_reported(self):
        response = self.client.post(self.url, signup_data(password1="12345678", password2="12345678"))
        self.assertIn("password2", response.context["form"].errors)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(User.objects.exists())

    def test_mismatched_passwords_error_shown_on_password2(self):
        response = self.client.post(self.url, signup_data(password2="Different-Pass-2026"))
        self.assertIn("password2", response.context["form"].errors)
        self.assertContains(response, "The two password fields")
        self.assertFalse(User.objects.exists())

    def test_missing_required_fields_are_reported(self):
        response = self.client.post(self.url, signup_data(first_name="", email=""))
        errors = response.context["form"].errors
        self.assertIn("first_name", errors)
        self.assertIn("email", errors)

    def test_phone_with_country_code_is_stored_as_ten_digits(self):
        self.client.post(self.url, signup_data(phone="+977 981 234 5678"))
        self.assertEqual(User.objects.get(email="asha@example.com").phone, "9812345678")

    def test_invalid_phone_is_rejected(self):
        for phone in ("12345", "9612345678", "98123456789"):
            with self.subTest(phone=phone):
                response = self.client.post(self.url, signup_data(phone=phone))
                self.assertIn("phone", response.context["form"].errors)
                self.assertContains(response, "Enter a 10-digit mobile number starting with 97 or 98.")
                self.assertFalse(User.objects.exists())

    def test_phone_is_optional(self):
        self.client.post(self.url, signup_data(phone=""))
        self.assertTrue(User.objects.filter(email="asha@example.com").exists())

    def test_authenticated_user_is_redirected_away(self):
        self.client.post(self.url, signup_data())
        self.assertRedirects(self.client.get(self.url), reverse("home"))


class LoginTests(TestCase):
    url = reverse("accounts:login")

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="asha", email="asha@example.com", password=STRONG_PASSWORD, first_name="Asha",
        )

    def test_form_renders(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dev/login.html")

    def test_login_with_email_redirects_home(self):
        response = self.client.post(self.url, {"email": "asha@example.com", "password": STRONG_PASSWORD})
        self.assertRedirects(response, reverse("home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_email_is_case_insensitive_and_trimmed(self):
        self.client.post(self.url, {"email": "  asha@EXAMPLE.com ", "password": STRONG_PASSWORD})
        self.assertIn("_auth_user_id", self.client.session)

    def test_wrong_password_shows_error_and_keeps_email(self):
        response = self.client.post(self.url, {"email": "asha@example.com", "password": "nope"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Incorrect email or password")
        self.assertContains(response, 'value="asha@example.com"')
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_unknown_email_shows_same_error(self):
        response = self.client.post(self.url, {"email": "ghost@example.com", "password": STRONG_PASSWORD})
        self.assertContains(response, "Incorrect email or password")

    def test_next_parameter_is_followed(self):
        response = self.client.post(self.url, {
            "email": "asha@example.com", "password": STRONG_PASSWORD, "next": reverse("cart:cart_detail"),
        })
        self.assertRedirects(response, reverse("cart:cart_detail"), fetch_redirect_response=False)

    def test_next_is_carried_through_the_form(self):
        response = self.client.get(self.url, {"next": "/cart/"})
        self.assertContains(response, 'name="next" value="/cart/"')

    def test_external_next_is_ignored(self):
        response = self.client.post(self.url, {
            "email": "asha@example.com", "password": STRONG_PASSWORD, "next": "https://evil.example/",
        })
        self.assertRedirects(response, reverse("home"))

    def test_without_remember_me_session_ends_with_browser(self):
        self.client.post(self.url, {"email": "asha@example.com", "password": STRONG_PASSWORD})
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_remember_me_keeps_session_for_30_days(self):
        self.client.post(self.url, {"email": "asha@example.com", "password": STRONG_PASSWORD, "remember": "on"})
        self.assertFalse(self.client.session.get_expire_at_browser_close())
        self.assertEqual(self.client.session.get_expiry_age(), 60 * 60 * 24 * 30)

    def test_password_toggle_markup_is_present(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'data-target="password"')
        self.assertContains(response, 'id="password"')


class LogoutTests(TestCase):
    url = reverse("accounts:logout")

    def setUp(self):
        User.objects.create_user(username="asha", email="asha@example.com", password=STRONG_PASSWORD)
        self.client.login(username="asha@example.com", password=STRONG_PASSWORD)

    def test_get_is_not_allowed_and_keeps_user_logged_in(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_post_logs_out_and_shows_confirmation(self):
        response = self.client.post(self.url, follow=True)
        self.assertRedirects(response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(response, "You have been logged out.")

    def test_navbar_logout_is_a_post_form(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'<form method="POST" action="{self.url}"')


class HeaderAccountMenuTests(TestCase):
    def test_menu_shows_initials_and_first_name_but_not_email(self):
        user = User.objects.create_user(
            username="asha", email="asha@example.com", password=STRONG_PASSWORD,
            first_name="Asha", last_name="Sharma",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertContains(response, '<span class="account-avatar" aria-hidden="true">AS</span>', html=True)
        self.assertContains(response, "Hi, Asha")
        self.assertNotContains(response, "asha@example.com")

    def test_menu_links_and_logout_form(self):
        user = User.objects.create_user(username="asha", email="asha@example.com", password=STRONG_PASSWORD)
        self.client.force_login(user)
        html = self.client.get(reverse("home")).content.decode()
        menu = html.split('<details class="account-menu">', 1)[1].split("</details>", 1)[0]
        profile = reverse("accounts:profile")
        for href in (profile, reverse("orders:order_list"), reverse("wishlist:wishlist_detail")):
            self.assertIn(f'href="{href}"', menu)
        self.assertIn(f'<form method="POST" action="{reverse("accounts:logout")}"', menu)
        self.assertIn('name="csrfmiddlewaretoken"', menu)
        self.assertIn(">A</span>", menu)        # no first name: initial from the email
        self.assertIn("Hi, there", menu)

    def test_logged_out_header_keeps_login_link(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("accounts:login")}" class="user-chip"')
        self.assertNotContains(response, "account-menu")


class ProfileTests(TestCase):
    url = reverse("accounts:profile")

    def test_anonymous_user_is_redirected_to_login_with_next(self):
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}")

    def test_logged_in_user_sees_name_email_and_orders_placeholder(self):
        User.objects.create_user(
            username="asha", email="asha@example.com", password=STRONG_PASSWORD,
            first_name="Asha", last_name="Sharma", phone="9800000000",
        )
        self.client.login(username="asha@example.com", password=STRONG_PASSWORD)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dev/profile.html")
        self.assertContains(response, "Asha Sharma")
        self.assertContains(response, "asha@example.com")
        self.assertContains(response, "9800000000")
        self.assertContains(response, "You haven't placed any orders yet.")

    def test_login_then_next_lands_on_profile(self):
        User.objects.create_user(username="asha", email="asha@example.com", password=STRONG_PASSWORD)
        response = self.client.post(
            f"{reverse('accounts:login')}?next={self.url}",
            {"email": "asha@example.com", "password": STRONG_PASSWORD, "next": self.url},
        )
        self.assertRedirects(response, self.url)


class ProfileOrdersTests(TestCase):
    url = reverse("accounts:profile")

    def setUp(self):
        self.user = User.objects.create_user(
            username="asha", email="asha@example.com", password=STRONG_PASSWORD,
        )
        self.other = User.objects.create_user(
            username="bob", email="bob@example.com", password=STRONG_PASSWORD,
        )
        category = Category.objects.create(name="Fruits", slug="fruits")
        self.product = Product.objects.create(
            category=category, name="Apple", slug="apple", price=100, stock=50,
        )
        self.client.force_login(self.user)

    def _order(self, user, total, status=Order.Status.PENDING, items=1):
        order = Order.objects.create(user=user, status=status, total=total, address="Kathmandu")
        for _ in range(items):
            OrderItem.objects.create(order=order, product=self.product, quantity=1, price=100)
        return order

    def _order_link(self, order):
        return f'href="{reverse("orders:order_detail", args=[order.pk])}"'

    def test_shows_only_own_orders_each_linking_to_its_page(self):
        mine = self._order(self.user, 300)
        theirs = self._order(self.other, 500)
        response = self.client.get(self.url)
        self.assertContains(response, self._order_link(mine))
        self.assertNotContains(response, self._order_link(theirs))
        self.assertNotContains(response, "You haven't placed any orders yet.")

    def test_only_the_latest_three_with_a_link_to_all_orders(self):
        oldest = self._order(self.user, 100)
        Order.objects.filter(pk=oldest.pk).update(created_at=timezone.now() - timedelta(days=2))
        newer = [self._order(self.user, 200) for _ in range(3)]
        response = self.client.get(self.url)
        for order in newer:
            self.assertContains(response, self._order_link(order))
        self.assertNotContains(response, self._order_link(oldest))
        self.assertContains(
            response, f'<a href="{reverse("orders:order_list")}" class="pf-link">View all orders ›</a>', html=True
        )

    def test_newest_order_first(self):
        old = self._order(self.user, 100)
        Order.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=2))
        new = self._order(self.user, 200)
        html = self.client.get(self.url).content.decode()
        self.assertLess(html.index(self._order_link(new)), html.index(self._order_link(old)))

    def test_status_badge_colours_and_item_count(self):
        self._order(self.user, 300, status=Order.Status.DELIVERED, items=2)
        self._order(self.user, 200, status=Order.Status.CANCELLED)
        response = self.client.get(self.url)
        self.assertContains(response, "gc-badge--success")
        self.assertContains(response, "gc-badge--danger")
        self.assertContains(response, "2 items")
        self.assertRegex(response.content.decode(), r"\b1 item\b(?!s)")  # singular

    def _save_to_wishlist(self, count):
        wishlist, _ = Wishlist.objects.get_or_create(user=self.user)
        start = Product.objects.count()  # unique slugs across calls
        for i in range(start, start + count):
            product = Product.objects.create(
                category=self.product.category, name=f"Saved {i}", slug=f"saved-{i}", price=10, stock=5,
            )
            WishlistItem.objects.create(wishlist=wishlist, product=product)

    def _tiles(self, response):
        html = response.content.decode()
        return html.split('<div class="pf-tiles">', 1)[1].split("<!-- Recent orders", 1)[0]

    def test_tiles_show_order_and_wishlist_counts(self):
        self._order(self.user, 300)
        self._order(self.user, 200, status=Order.Status.DELIVERED)
        self._order(self.user, 1000, status=Order.Status.CANCELLED)  # still an order
        self._save_to_wishlist(2)
        tiles = self._tiles(self.client.get(self.url))
        self.assertIn(f'<a href="{reverse("orders:order_list")}" class="pf-tile">', tiles)
        self.assertIn(f'<a href="{reverse("wishlist:wishlist_detail")}" class="pf-tile">', tiles)
        self.assertIn("<span>3 orders</span>", tiles)
        self.assertIn("<span>2 items</span>", tiles)

    def test_tile_counts_are_singular_for_one(self):
        self._order(self.user, 300)
        self._save_to_wishlist(1)
        tiles = self._tiles(self.client.get(self.url))
        self.assertIn("<span>1 order</span>", tiles)
        self.assertIn("<span>1 item</span>", tiles)

    def test_template_parts_are_gone(self):
        response = self.client.get(self.url)
        for text in ("Change Password", "Upload Photo", "About Me", "Coming soon",
                     "pf-hero", "pf-stats", "pf-banner", "Total Spent"):
            self.assertNotContains(response, text)
        self.assertContains(
            response, f'<a href="{reverse("accounts:edit_profile")}" class="pf-btn">Edit profile</a>', html=True,
        )

    def test_help_line_has_shop_phone_link(self):
        html = self.client.get(self.url).content.decode()
        help_line = html.split('<p class="pf-help">', 1)[1].split("</p>", 1)[0]
        self.assertIn('<a href="tel:+9779707046738">+9779707046738</a>', help_line)

    def test_no_extra_queries_per_order_or_wishlist_item(self):
        self._order(self.user, 100, items=2)
        self._save_to_wishlist(1)
        with CaptureQueriesContext(connection) as small:
            self.client.get(self.url)
        for _ in range(4):
            self._order(self.user, 100, items=2)
        Wishlist.objects.all().delete()
        self._save_to_wishlist(5)
        with CaptureQueriesContext(connection) as large:
            self.client.get(self.url)
        self.assertEqual(len(large), len(small))


class AccountSidebarTests(TestCase):
    """The shared sidebar (dev/_account_sidebar.html) highlights the current page."""

    def setUp(self):
        user = User.objects.create_user(
            username="asha", email="asha@example.com", password=STRONG_PASSWORD, first_name="Asha",
        )
        self.client.force_login(user)
        self.links = {
            "account": reverse("accounts:profile"),
            "orders": reverse("orders:order_list"),
        }

    def _sidebar(self, url):
        html = self.client.get(url).content.decode()
        return html.split('<aside class="pf-sidebar">', 1)[1].split("</aside>", 1)[0]

    def test_only_the_current_page_is_active(self):
        for page, url in self.links.items():
            with self.subTest(page=page):
                sidebar = self._sidebar(url)
                self.assertEqual(sidebar.count('class="active"'), 1)
                self.assertIn(f'<a href="{url}" class="active" aria-current="page">', sidebar)

    def test_links_and_logout_form(self):
        sidebar = self._sidebar(self.links["orders"])
        for url in self.links.values():
            self.assertIn(f'href="{url}"', sidebar)
        self.assertIn(f'<form method="POST" action="{reverse("accounts:logout")}" class="pf-logout">', sidebar)
        self.assertIn('name="csrfmiddlewaretoken"', sidebar)
        self.assertIn("Log out", sidebar)

    def test_removed_items_and_emoji_are_gone(self):
        sidebar = self._sidebar(self.links["account"])
        for text in ("Wishlist", "Addresses", "Notifications", "Settings", "Coming soon",
                     "pf-social", "👤", "📦", "📷"):
            self.assertNotIn(text, sidebar)

    def test_wishlist_page_has_no_account_sidebar(self):
        response = self.client.get(reverse("wishlist:wishlist_detail"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "pf-sidebar")


class PhoneValidatorTests(TestCase):
    """accounts/validators.py: shared by the profile and checkout forms."""

    def test_accepted_numbers_are_stored_as_ten_digits(self):
        cases = {
            "9812345678": "9812345678",
            "9712345678": "9712345678",
            "98 1234 5678": "9812345678",
            "+9779812345678": "9812345678",
            "+977 981 234 5678": "9812345678",
            "9779812345678": "9812345678",
            "977 9812345678": "9812345678",
            "9771234567": "9771234567",  # a real 97 number, not a country code
        }
        for raw, stored in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_nepali_phone(raw), stored)

    def test_rejected_numbers(self):
        for raw in ("12345", "9612345678", "98123456789", "981234567", "98123abc78",
                    "", "+977", "+1 9812345678", "+977 96 1234 5678", "९८१२३४५६७८"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValidationError):
                    normalize_nepali_phone(raw)


class EditProfileTests(TestCase):
    url = reverse("accounts:edit_profile")

    def setUp(self):
        self.user = User.objects.create_user(
            username="asha", email="asha@example.com", password=STRONG_PASSWORD,
            first_name="Asha", last_name="Sharma", phone="9800000000",
        )
        self.client.force_login(self.user)

    def _post(self, **overrides):
        data = {"first_name": "Asha", "last_name": "Karki", "phone": "9812345678"}
        data.update(overrides)
        return self.client.post(self.url, data)

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}")

    def test_form_is_filled_in_with_csrf_and_data_once(self):
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "dev/profile_edit.html")
        self.assertContains(response, 'value="Asha"')
        self.assertContains(response, 'value="9800000000"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, "data-once")
        # Email is shown read-only and has no name, so it is never sent
        self.assertContains(response, 'value="asha@example.com" readonly')
        self.assertNotContains(response, 'name="email"')

    def test_valid_change_is_saved_with_a_message(self):
        response = self.client.post(
            self.url, {"first_name": "Asha", "last_name": "Karki", "phone": "+977 981 234 5678"}, follow=True,
        )
        self.assertRedirects(response, reverse("accounts:profile"))
        self.assertContains(response, "Your profile has been updated.")
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_name, "Karki")
        self.assertEqual(self.user.phone, "9812345678")  # only the 10 digits

    def test_phone_is_optional(self):
        self._post(phone="")
        self.user.refresh_from_db()
        self.assertFalse(self.user.phone)

    def test_invalid_phone_is_rejected_and_nothing_saved(self):
        for phone in ("12345", "9612345678", "98123456789"):
            with self.subTest(phone=phone):
                response = self._post(phone=phone)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Enter a 10-digit mobile number starting with 97 or 98.")
                self.user.refresh_from_db()
                self.assertEqual(self.user.phone, "9800000000")
                self.assertEqual(self.user.last_name, "Sharma")

    def test_names_are_required(self):
        response = self._post(first_name="")
        self.assertIn("first_name", response.context["form"].errors)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Asha")

    def test_email_cannot_be_changed(self):
        self._post(email="new@example.com")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "asha@example.com")

    def test_post_without_csrf_token_is_refused(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post(self.url, {"first_name": "X", "last_name": "Y", "phone": ""})
        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Asha")


class CustomerAdminTests(TestCase):
    url = reverse("admin:accounts_user_changelist")

    def setUp(self):
        self.boss = User.objects.create_superuser(
            username="boss", email="boss@example.com", password="pass12345"
        )
        self.client.force_login(self.boss)

    def _customer(self, n, phone=None, first="", last=""):
        return User.objects.create_user(
            username=f"c{n}", email=f"c{n}@example.com", password="pass12345",
            first_name=first, last_name=last, phone=phone,
        )

    def _address(self, user, phone):
        return Address.objects.create(
            user=user, recipient_name="Receiver", phone=phone,
            address_line="12 Market Rd", city="Kathmandu",
        )

    def _order(self, user, total=100, status=Order.Status.PENDING, created_at=None):
        order = Order.objects.create(user=user, status=status, total=total, address="Kathmandu")
        if created_at:
            Order.objects.filter(pk=order.pk).update(created_at=created_at)
        return order

    def _listed(self, **params):
        res = self.client.get(self.url, params)
        self.assertEqual(res.status_code, 200)
        return {user.email: user for user in res.context["cl"].result_list}

    def _queries(self):
        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.url)
        return len(queries)

    # ---- list columns ----
    def test_order_count_total_spent_and_last_order(self):
        asha = self._customer(1, first="Asha", last="Sharma")
        last = timezone.now() - timedelta(days=2)
        self._order(asha, 300, Order.Status.DELIVERED, created_at=last - timedelta(days=5))
        self._order(asha, 200, created_at=last)
        self._order(asha, 1000, Order.Status.CANCELLED, created_at=timezone.now() - timedelta(days=9))
        self._customer(2)  # no orders

        listed = self._listed()
        shown = listed["c1@example.com"]
        self.assertEqual(shown._order_count, 3)    # every order is counted...
        self.assertEqual(shown._total_spent, 500)  # ...but cancelled money is not
        self.assertEqual(shown._last_order, last)
        quiet = listed["c2@example.com"]
        self.assertEqual((quiet._order_count, quiet._total_spent, quiet._last_order), (0, None, None))

        res = self.client.get(self.url)
        self.assertContains(res, "Asha Sharma")
        self.assertContains(res, "Rs. 500")
        self.assertContains(res, "Rs. 0")
        self.assertContains(res, date_format(timezone.localtime(last), "j M Y"))

    def test_phone_column_is_the_profile_phone_or_the_newest_address_phone(self):
        profile = self._customer(1, phone="9811111111")
        self._address(profile, "9822222222")
        address_only = self._customer(2)
        self._address(address_only, "9833333333")
        self._address(address_only, "9844444444")  # the newest one
        self._customer(3)  # no phone anywhere
        listed = self._listed()
        self.assertEqual(listed["c2@example.com"]._address_phone, "9844444444")
        self.assertIsNone(listed["c3@example.com"]._address_phone)
        res = self.client.get(self.url)
        self.assertContains(res, "9811111111")  # profile phone wins over its address phone
        self.assertContains(res, "9844444444")
        self.assertNotContains(res, "9822222222")
        self.assertNotContains(res, "9833333333")

    def test_query_count_does_not_grow_with_customers(self):
        asha = self._customer(1)
        self._order(asha)
        self._address(asha, "9811111111")
        small = self._queries()
        for n in range(2, 22):
            customer = self._customer(n)
            self._order(customer)
            self._order(customer, 50)
            self._address(customer, f"98{n:08d}")
        self.assertEqual(self._queries(), small)

    # ---- filter ----
    def test_account_type_filter(self):
        self._customer(1)
        staff = self._customer(2)
        staff.is_staff = True
        staff.save()
        self.assertEqual(set(self._listed(account_type="customers")), {"c1@example.com"})
        self.assertEqual(
            set(self._listed(account_type="staff")), {"c2@example.com", "boss@example.com"}
        )
        self.assertEqual(len(self._listed()), 3)
        self.assertContains(self.client.get(self.url), "Customers only")

    # ---- search by phone ----
    def test_phone_search_digits(self):
        cases = {
            "9865472537": "9865472537",
            "+9779865472537": "9865472537",
            "+977 986-5472537": "9865472537",
            "9779865472537": "9865472537",
            " 986 547 2537 ": "9865472537",
            "9771234567": "9771234567",  # a real 10-digit number starting 977 is left alone
            "98654": "98654",
            "98": "",  # too short: an ordinary search
            "Sharma": "",
            "asha@example.com": "",
            "98a65472537": "",
            "": "",
        }
        for term, digits in cases.items():
            with self.subTest(term=term):
                self.assertEqual(phone_search_digits(term), digits)

    def test_search_with_plus977_finds_a_phone_saved_as_10_digits(self):
        profile = self._customer(1, phone="9865472537")
        by_address = self._customer(2)
        self._address(by_address, "9865472537")
        self._customer(3, phone="9811111111")
        self._address(self._customer(4), "9822222222")
        for term in ("+9779865472537", "+977 986-5472537", "+977 986 547 2537", "9779865472537"):
            with self.subTest(term=term):
                self.assertEqual(set(self._listed(q=term)), {profile.email, by_address.email})

    def test_search_without_the_country_code_finds_a_phone_saved_with_plus977(self):
        profile = self._customer(1, phone="+9779865472537")
        by_address = self._customer(2)
        self._address(by_address, "+9779865472537")
        self._customer(3, phone="9811111111")
        self._address(self._customer(4), "+9779822222222")
        for term in ("9865472537", "986 547 2537", "986-5472537", "98654"):
            with self.subTest(term=term):
                self.assertEqual(set(self._listed(q=term)), {profile.email, by_address.email})

    def test_both_saved_formats_are_found_by_either_search(self):
        old = self._customer(1, phone="9865472537")
        new = self._customer(2, phone="+9779865472537")
        for term in ("9865472537", "+9779865472537"):
            with self.subTest(term=term):
                self.assertEqual(set(self._listed(q=term)), {old.email, new.email})

    def test_two_matching_addresses_list_the_customer_once_with_the_right_totals(self):
        asha = self._customer(1)
        self._address(asha, "9865472537")
        self._address(asha, "+9779865472537")
        self._order(asha, 100)
        self._order(asha, 200)
        res = self.client.get(self.url, {"q": "9865472537"})
        users = list(res.context["cl"].result_list)
        self.assertEqual([u.email for u in users], ["c1@example.com"])
        self.assertEqual((users[0]._order_count, users[0]._total_spent), (2, 300))

    def test_name_and_email_search_still_work(self):
        self._customer(1, first="Asha", last="Sharma")
        self._customer(12)
        self.assertEqual(set(self._listed(q="Sharma")), {"c1@example.com"})
        self.assertEqual(set(self._listed(q="c12@")), {"c12@example.com"})
        self.assertEqual(set(self._listed(q="12")), {"c12@example.com"})  # too short for a phone search

    def test_phone_search_changes_no_saved_data(self):
        customer = self._customer(1, phone="+9779865472537")
        address = self._address(customer, "9865472537")
        self._listed(q="+977 986 547 2537")
        customer.refresh_from_db()
        address.refresh_from_db()
        self.assertEqual((customer.phone, address.phone), ("+9779865472537", "9865472537"))

    # ---- customer page ----
    def _change_url(self, user):
        return reverse("admin:accounts_user_change", args=[user.pk])

    def _delete_url(self, user):
        return reverse("admin:accounts_user_delete", args=[user.pk])

    def test_page_lists_the_ten_newest_orders_with_links(self):
        asha = self._customer(1)
        now = timezone.now()
        orders = [self._order(asha, 100 + n, created_at=now - timedelta(days=12 - n)) for n in range(12)]
        res = self.client.get(self._change_url(asha))
        self.assertEqual(res.status_code, 200)
        for order in orders[2:]:  # the newest ten
            self.assertContains(res, reverse("admin:orders_order_change", args=[order.pk]))
        for order in orders[:2]:
            self.assertNotContains(res, reverse("admin:orders_order_change", args=[order.pk]))
        self.assertContains(res, "Pending")
        self.assertContains(res, f"{reverse('admin:orders_order_changelist')}?q=c1%40example.com")
        # Newest first.
        html = res.content.decode()
        newest, older = orders[-1], orders[-2]
        self.assertLess(
            html.index(reverse("admin:orders_order_change", args=[newest.pk])),
            html.index(reverse("admin:orders_order_change", args=[older.pk])),
        )

    def test_customer_with_orders_cannot_be_deleted_and_the_page_says_to_deactivate(self):
        asha = self._customer(1)
        self._order(asha)
        res = self.client.get(self._change_url(asha))
        self.assertContains(res, "This customer has orders, so the account can't be deleted.")
        self.assertContains(res, "untick")
        self.assertNotContains(res, self._delete_url(asha))
        self.assertEqual(self.client.get(self._delete_url(asha)).status_code, 403)
        self.assertEqual(self.client.post(self._delete_url(asha), {"post": "yes"}).status_code, 403)
        # The bulk "delete selected" action doesn't delete them either.
        self.client.post(self.url, {
            "action": "delete_selected", "_selected_action": [asha.pk], "post": "yes",
        })
        self.assertTrue(User.objects.filter(pk=asha.pk).exists())

    def test_deactivating_a_customer_with_orders_works(self):
        asha = self._customer(1)
        self._order(asha)
        asha.is_active = False
        asha.save()
        self.assertFalse(Client().login(email="c1@example.com", password="pass12345"))
        self.assertEqual(Order.objects.filter(user=asha).count(), 1)

    def test_customer_without_orders_can_still_be_deleted(self):
        asha = self._customer(1)
        res = self.client.get(self._change_url(asha))
        self.assertContains(res, "No orders yet.")
        self.assertNotContains(res, "This customer has orders")
        self.assertContains(res, self._delete_url(asha))
        self.client.post(self._delete_url(asha), {"post": "yes"})
        self.assertFalse(User.objects.filter(pk=asha.pk).exists())

    def test_add_page_still_works(self):
        res = self.client.get(reverse("admin:accounts_user_add"))
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "Recent orders")


# ---- Phase 5: staff roles ----
# The permissions each role must have, listed out in full on purpose: if the
# migration (or a hand edit) changes them, these tests say so.
ORDER_STAFF_PERMISSIONS = {
    "orders.view_order", "orders.change_order", "orders.view_orderitem",
    "orders.view_payment", "orders.view_orderstatuschange",
    "products.view_product", "products.view_productimage",
    "accounts.view_user",
}
MANAGER_PERMISSIONS = ORDER_STAFF_PERMISSIONS | {
    "orders.view_money_totals",
    "products.add_product", "products.change_product", "products.delete_product",
    "products.add_productimage", "products.change_productimage", "products.delete_productimage",
    "products.view_category", "products.add_category", "products.change_category",
    "products.delete_category",
    "products.view_review", "products.change_review", "products.delete_review",
    "accounts.change_user", "accounts.delete_user",
    "accounts.view_address", "accounts.change_address",
}


def make_staff(group_name, n=1, **extra):
    """A staff login in one of the two groups made by the data migration."""
    user = User.objects.create_user(
        username=f"staff{n}", email=f"staff{n}@shop.com", password="pass12345",
        is_staff=True, **extra,
    )
    user.groups.add(Group.objects.get(name=group_name))
    return user


def permissions_of(group):
    return {f"{p.content_type.app_label}.{p.codename}" for p in group.permissions.all()}


class StaffGroupsMigrationTests(TestCase):
    def test_order_staff_group(self):
        self.assertEqual(permissions_of(Group.objects.get(name="Order staff")), ORDER_STAFF_PERMISSIONS)

    def test_managers_group(self):
        self.assertEqual(permissions_of(Group.objects.get(name="Managers")), MANAGER_PERMISSIONS)

    def test_managers_get_nothing_about_access_or_adding_and_deleting_orders(self):
        managers = permissions_of(Group.objects.get(name="Managers"))
        for codename in (
            "accounts.add_user", "orders.add_order", "orders.delete_order",
            "orders.add_payment", "orders.delete_payment", "orders.add_review",
        ):
            self.assertNotIn(codename, managers)
        self.assertFalse([p for p in managers if p.startswith(("auth.", "contenttypes.", "admin."))])

    def test_running_the_migration_function_again_changes_nothing(self):
        migration = importlib.import_module("accounts.migrations.0002_staff_groups")
        Group.objects.get(name="Managers").permissions.clear()
        migration.create_groups(django_apps, None)
        migration.create_groups(django_apps, None)
        self.assertEqual(Group.objects.filter(name__in=["Order staff", "Managers"]).count(), 2)
        self.assertEqual(permissions_of(Group.objects.get(name="Managers")), MANAGER_PERMISSIONS)
        self.assertEqual(permissions_of(Group.objects.get(name="Order staff")), ORDER_STAFF_PERMISSIONS)
        # It must leave Django's own app list alone.
        self.assertIsNotNone(django_apps.get_app_config("orders").models_module)


class RoleTestBase(TestCase):
    """A superuser, a customer with one order, a product, a review and the two groups."""

    def setUp(self):
        self.boss = User.objects.create_superuser(
            username="boss", email="boss@example.com", password="pass12345"
        )
        self.customer = User.objects.create_user(
            username="asha", email="asha@example.com", password="pass12345",
            first_name="Asha", last_name="Sharma",
        )
        self.category = Category.objects.create(name="Fruits", slug="fruits")
        self.product = Product.objects.create(
            category=self.category, name="Apple", slug="apple", price=100, stock=3
        )
        self.order = self._order()
        self.review = Review.objects.create(
            user=self.customer, product=self.product, rating=5, comment="Nice"
        )

    def _order(self, status=Order.Status.PENDING, user=None):
        order = Order.objects.create(
            user=user or self.customer, status=status, subtotal=200, shipping_fee=100,
            total=300, address="Asha, Kathmandu",
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name="Apple", quantity=2, price=100
        )
        Payment.objects.create(order=order, method=Payment.Method.COD, amount=300)
        return order

    def _plain_customer(self, n=2):
        """A customer with no orders (so they can be deleted)."""
        return User.objects.create_user(
            username=f"plain{n}", email=f"plain{n}@example.com", password="pass12345"
        )

    def login(self, user):
        self.client.force_login(user)

    # ---- addresses ----
    def url(self, name, *args):
        return reverse(f"admin:{name}", args=args)

    def order_url(self, order=None):
        return self.url("orders_order_change", (order or self.order).pk)

    def status_url(self, order=None):
        return self.url("orders_order_status", (order or self.order).pk)

    def customer_url(self, user=None):
        return self.url("accounts_user_change", (user or self.customer).pk)

    def links_on_home_page(self):
        return self.client.get(self.url("index")).content.decode()


class OrderStaffTests(RoleTestBase):
    def setUp(self):
        super().setUp()
        self.staff = make_staff("Order staff")
        self.login(self.staff)

    # ---- what they see ----
    def test_sidebar_and_dashboard_show_only_what_they_can_use(self):
        html = self.links_on_home_page()
        for name in ("orders_order_changelist", "products_product_changelist", "accounts_user_changelist"):
            self.assertIn(f'href="{self.url(name)}"', html)
        for name in ("products_category_changelist", "products_review_changelist", "auth_group_changelist"):
            self.assertNotIn(f'href="{self.url(name)}"', html)
        self.assertNotIn("account_type=staff", html)
        self.assertIn("Needs doing now", html)
        self.assertIn("Low stock", html)

    def test_no_money_totals_anywhere(self):
        html = self.links_on_home_page()
        for text in ("Orders and cash", "Orders today", "Orders this week", "Cash collected today"):
            self.assertNotIn(text, html)
        # The order list has no "N orders · Rs. X" line, with or without a filter.
        today = timezone.localdate().isoformat()
        for params in ({}, {"created_at_from": today, "created_at_to": today}, {"q": "asha"}):
            res = self.client.get(self.url("orders_order_changelist"), params)
            self.assertEqual(res.status_code, 200)
            self.assertNotRegex(res.content.decode(), r"\d+ orders? · Rs\.")
        # Each order's own total is still listed: they need it to collect the cash.
        self.assertContains(self.client.get(self.url("orders_order_changelist")), "300")
        # The customer list has no "Total spent" column.
        self.assertNotContains(self.client.get(self.url("accounts_user_changelist")), "Total spent")

    def test_can_open_the_pages_they_need(self):
        self.order.change_status(Order.Status.CONFIRMED, changed_by=self.boss, note="Called")
        pages = [
            self.url("index"), self.url("orders_order_changelist"), self.order_url(),
            self.url("products_product_changelist"),
            self.url("products_product_change", self.product.pk),
            self.url("accounts_user_changelist"), self.customer_url(),
            self.url("orders_order_packing_slip", self.order.pk),
        ]
        for page in pages:
            with self.subTest(page=page):
                self.assertEqual(self.client.get(page).status_code, 200)
        order_page = self.client.get(self.order_url())
        for text in ("Apple", "Status history", "Called", "Cash collected by", "Order status"):
            self.assertContains(order_page, text)

    def test_customer_page_is_read_only_and_has_no_password_hash(self):
        res = self.client.get(self.customer_url())
        self.assertContains(res, "Sharma")
        for text in ("pbkdf2", 'name="first_name"', 'name="is_staff"', 'name="groups"'):
            self.assertNotContains(res, text)

    # ---- what they can do ----
    def test_can_take_an_order_all_the_way_and_record_the_cash(self):
        for status in ("confirmed", "packed", "out_for_delivery", "delivered"):
            res = self.client.post(self.status_url(), {"status": status})
            self.assertEqual(res.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DELIVERED)
        self.assertEqual(self.order.status_changes.last().changed_by, self.staff)

        self.client.post(self.url("orders_order_cash_collected", self.order.pk))
        payment = Payment.objects.get(order=self.order)
        self.assertEqual((payment.status, payment.collected_by), (Payment.Status.PAID, self.staff))

        self.assertContains(self.client.get(self.order_url()), "Cash collected by staff1@shop.com")
        self.assertContains(
            self.client.get(self.url("orders_order_packing_slip", self.order.pk)),
            "collected by staff1@shop.com",
        )

    def test_can_cancel_with_a_note_and_use_the_bulk_actions(self):
        other = self._order()
        self.client.post(self.status_url(other), {"status": "cancelled", "note": "Customer refused"})
        other.refresh_from_db()
        self.assertEqual(other.status, Order.Status.CANCELLED)

        self.client.post(self.url("orders_order_changelist"), {
            "action": "mark_confirmed", "_selected_action": [self.order.pk],
        })
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)

    # ---- what they can't ----
    def test_cannot_open_catalogue_review_or_role_pages(self):
        for name in (
            "products_category_changelist", "products_category_add", "products_review_changelist",
            "auth_group_changelist", "auth_group_add", "accounts_user_add", "orders_order_add",
        ):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(self.url(name)).status_code, 403)

    def test_cannot_edit_products(self):
        res = self.client.get(self.url("products_product_changelist"))
        for text in ("hide_from_site", "show_on_site", "delete_selected"):
            self.assertNotContains(res, text)
        # Quick editing in the list and the product page are both refused.
        res = self.client.post(self.url("products_product_changelist"), {
            "form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "1",
            "form-0-id": self.product.pk, "form-0-price": "1.00", "form-0-stock": "999",
            "form-0-is_available": "on", "_save": "Save",
        })
        self.assertEqual(res.status_code, 403)
        res = self.client.post(self.url("products_product_change", self.product.pk), {"name": "Hacked"})
        self.assertEqual(res.status_code, 403)
        res = self.client.post(self.url("products_product_changelist"), {
            "action": "hide_from_site", "_selected_action": [self.product.pk],
        })
        self.assertEqual(res.status_code, 200)  # the action isn't available: nothing runs
        self.product.refresh_from_db()
        self.assertEqual((self.product.price, self.product.stock, self.product.is_available), (100, 3, True))

    def test_cannot_edit_or_delete_customers_orders_or_the_order_page(self):
        plain = self._plain_customer()
        res = self.client.post(self.customer_url(), {"first_name": "Hacked", "is_active": "on"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.client.post(self.url("accounts_user_delete", plain.pk), {"post": "yes"}).status_code, 403)
        self.assertTrue(User.objects.filter(pk=plain.pk).exists())
        self.assertEqual(self.client.post(self.order_url(), {"total": "1"}).status_code, 403)
        self.assertEqual(
            self.client.post(self.url("orders_order_delete", self.order.pk), {"post": "yes"}).status_code, 403
        )
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, "Asha")
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())


class ManagerTests(RoleTestBase):
    def setUp(self):
        super().setUp()
        self.manager = make_staff("Managers")
        self.login(self.manager)

    def test_sidebar_and_dashboard(self):
        html = self.links_on_home_page()
        for name in (
            "orders_order_changelist", "products_product_changelist", "products_category_changelist",
            "products_review_changelist", "accounts_user_changelist",
        ):
            self.assertIn(f'href="{self.url(name)}"', html)
        for name in ("auth_group_changelist",):
            self.assertNotIn(f'href="{self.url(name)}"', html)
        self.assertNotIn("account_type=staff", html)
        for text in ("Needs doing now", "Orders and cash", "Orders today", "Low stock"):
            self.assertIn(text, html)

    def test_money_totals_are_shown(self):
        res = self.client.get(self.url("orders_order_changelist"))
        self.assertRegex(res.content.decode(), r"\d+ orders? · Rs\.")
        self.assertContains(self.client.get(self.url("accounts_user_changelist")), "Total spent")

    def test_can_run_the_catalogue(self):
        res = self.client.post(self.url("products_category_add"), {"name": "Snacks", "slug": "snacks", "parent": ""})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Category.objects.filter(slug="snacks").exists())

        res = self.client.post(self.url("products_product_add"), {
            "category": self.category.pk, "name": "Pear", "slug": "pear", "price": "50", "stock": "9",
            "is_available": "on", "images-TOTAL_FORMS": "0", "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "1000",
        })
        self.assertEqual(res.status_code, 302)
        pear = Product.objects.get(slug="pear")

        self.client.post(self.url("products_product_changelist"), {
            "action": "hide_from_site", "_selected_action": [pear.pk],
        })
        pear.refresh_from_db()
        self.assertFalse(pear.is_available)

        self.assertEqual(self.client.get(self.url("products_product_change", pear.pk)).status_code, 200)
        self.client.post(self.url("products_product_delete", pear.pk), {"post": "yes"})
        self.assertFalse(Product.objects.filter(pk=pear.pk).exists())

    def test_can_manage_reviews(self):
        self.client.post(self.url("products_review_changelist"), {
            "action": "hide_reviews", "_selected_action": [self.review.pk],
        })
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_visible)
        self.client.post(self.url("products_review_delete", self.review.pk), {"post": "yes"})
        self.assertFalse(Review.objects.filter(pk=self.review.pk).exists())

    def test_can_edit_a_customers_name_and_active_box_only(self):
        res = self.client.get(self.customer_url())
        for text in ('name="first_name"', 'name="last_name"', 'name="is_active"', "asha@example.com"):
            self.assertContains(res, text)
        for text in ('name="email"', 'name="is_staff"', 'name="is_superuser"', 'name="groups"',
                     'name="user_permissions"', 'name="username"', "pbkdf2"):
            self.assertNotContains(res, text)
        res = self.client.post(self.customer_url(), {
            "first_name": "Asha2", "last_name": "Sharma2",  # is_active unticked
        })
        self.assertEqual(res.status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.first_name, self.customer.last_name), ("Asha2", "Sharma2"))
        self.assertFalse(self.customer.is_active)
        self.assertFalse(Client().login(username="asha@example.com", password="pass12345"))

    def test_deleting_customers(self):
        plain = self._plain_customer()
        self.client.post(self.url("accounts_user_delete", plain.pk), {"post": "yes"})
        self.assertFalse(User.objects.filter(pk=plain.pk).exists())
        # One with orders is refused, and the page says to untick Active.
        self.assertContains(self.client.get(self.customer_url()), "untick")
        self.assertEqual(self.client.get(self.url("accounts_user_delete", self.customer.pk)).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.customer.pk).exists())

    def test_staff_accounts_are_out_of_reach(self):
        listed = {u.email for u in self.client.get(self.url("accounts_user_changelist")).context["cl"].result_list}
        self.assertEqual(listed, {"asha@example.com"})
        for name in ("accounts_user_change", "accounts_user_delete"):
            for staff in (self.boss, self.manager):  # a superuser, and their own page
                with self.subTest(page=name, user=staff.email):
                    # As for a page that doesn't exist: sent back to the admin home.
                    res = self.client.get(self.url(name, staff.pk))
                    self.assertRedirects(res, self.url("index"))
        self.assertEqual(self.client.get(self.url("accounts_user_add")).status_code, 403)
        for name in ("auth_group_changelist", "auth_group_add"):
            self.assertEqual(self.client.get(self.url(name)).status_code, 403)

    def test_cannot_reset_a_password(self):
        url = self.url("auth_user_password_change", self.customer.pk)
        self.assertEqual(self.client.get(url).status_code, 403)
        res = self.client.post(url, {"password1": "Hacked-Pass-2026", "password2": "Hacked-Pass-2026"})
        self.assertEqual(res.status_code, 403)
        self.assertTrue(Client().login(username="asha@example.com", password="pass12345"))


class EscalationTests(RoleTestBase):
    """Everyone below a superuser tries to get more access. Nothing may change."""

    def assertRefused(self, res):
        """Not allowed: a 403, or treated as "doesn't exist" and sent to the admin home."""
        if res.status_code == 302:
            self.assertEqual(res.url, self.url("index"))
        else:
            self.assertEqual(res.status_code, 403)

    def _snapshot(self):
        users = {
            u.email: (u.is_staff, u.is_superuser, u.is_active, u.email, u.username, u.password,
                      sorted(g.pk for g in u.groups.all()),
                      sorted(p.pk for p in u.user_permissions.all()))
            for u in User.objects.all()
        }
        groups = {g.name: permissions_of(g) for g in Group.objects.all()}
        return users, groups

    def test_attempts_by_each_role(self):
        managers = Group.objects.get(name="Managers")
        some_permission = Permission.objects.get(codename="delete_order")
        for n, role in enumerate(("Order staff", "Managers"), start=1):
            with self.subTest(role=role):
                staff = make_staff(role, n=n)
                self.login(staff)
                before = self._snapshot()

                # 1. Raise a customer's access (and change their email) through the user form.
                self.client.post(self.customer_url(), {
                    "first_name": "New", "last_name": "Name", "is_active": "on",
                    "email": "evil@example.com", "username": "hacked",
                    "is_staff": "on", "is_superuser": "on",
                    "groups": [managers.pk], "user_permissions": [some_permission.pk],
                    "password": "x", "password1": "x", "password2": "x",
                })
                customer = User.objects.get(pk=self.customer.pk)
                self.assertEqual(customer.email, "asha@example.com")
                self.assertEqual(customer.username, "asha")
                self.assertEqual((customer.is_staff, customer.is_superuser), (False, False))
                self.assertFalse(customer.groups.exists())
                self.assertFalse(customer.user_permissions.exists())

                # 2. Raise their own access, or open a staff account's page.
                for target in (staff, self.boss):
                    for name in ("accounts_user_change", "accounts_user_delete"):
                        for method in (self.client.get, self.client.post):
                            res = method(self.url(name, target.pk), {"is_superuser": "on", "is_staff": "on"})
                            self.assertRefused(res)
                    res = self.client.post(
                        self.url("auth_user_password_change", target.pk),
                        {"password1": "Hacked-Pass-2026", "password2": "Hacked-Pass-2026"},
                    )
                    self.assertEqual(res.status_code, 403)

                # 3. Make a new account, or delete staff with "delete selected".
                res = self.client.post(self.url("accounts_user_add"), {
                    "username": "newboss", "email": "newboss@example.com",
                    "password1": STRONG_PASSWORD, "password2": STRONG_PASSWORD,
                })
                self.assertEqual(res.status_code, 403)
                self.client.post(self.url("accounts_user_changelist"), {
                    "action": "delete_selected", "post": "yes",
                    "_selected_action": [self.boss.pk, staff.pk],
                })

                # 4. Edit the roles themselves.
                self.assertEqual(self.client.post(self.url("auth_group_add"), {"name": "Evil"}).status_code, 403)
                res = self.client.post(
                    self.url("auth_group_change", managers.pk),
                    {"name": "Managers", "permissions": [some_permission.pk]},
                )
                self.assertEqual(res.status_code, 403)

                after = self._snapshot()
                # Only the staff account itself changed nothing; the customer's name may differ for Managers.
                self.assertEqual(before[1], after[1])
                self.assertEqual(set(before[0]), set(after[0]))
                for email, record in before[0].items():
                    self.assertEqual(record, after[0][email], email)

    def test_a_manager_changing_the_email_leaves_it_unchanged(self):
        self.login(make_staff("Managers"))
        res = self.client.post(self.customer_url(), {
            "first_name": "Asha", "last_name": "Sharma", "is_active": "on",
            "email": "takeover@example.com",
        })
        self.assertEqual(res.status_code, 302)  # the allowed fields saved fine
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.email, "asha@example.com")
        self.assertFalse(User.objects.filter(email="takeover@example.com").exists())


class SuperuserStaffAccountTests(RoleTestBase):
    def setUp(self):
        super().setUp()
        self.login(self.boss)

    def _create(self, email="Ram.Thapa@Shop.COM ", **extra):
        data = {
            "username": "ramthapa", "email": email, "first_name": "Ram", "last_name": "Thapa",
            "usable_password": "true", "password1": STRONG_PASSWORD, "password2": STRONG_PASSWORD,
        }
        data.update(extra)
        return self.client.post(self.url("accounts_user_add"), data)

    def test_add_page_asks_for_the_email_and_names(self):
        res = self.client.get(self.url("accounts_user_add"))
        for field in ("username", "email", "first_name", "last_name", "password1", "password2"):
            self.assertContains(res, f'name="{field}"')

    def test_create_a_staff_account_and_give_it_the_order_staff_role(self):
        res = self._create()
        new = User.objects.get(username="ramthapa")
        self.assertRedirects(res, self.url("accounts_user_change", new.pk))
        self.assertEqual(new.email, "ram.thapa@shop.com")  # lowercased: the login lowercases it too
        self.assertEqual((new.first_name, new.last_name), ("Ram", "Thapa"))
        self.assertFalse(new.is_staff)  # set on the next page, on purpose

        # The change page has the access boxes for a superuser.
        page = self.client.get(self.url("accounts_user_change", new.pk))
        for field in ("is_staff", "is_superuser", "groups", "user_permissions", "email", "username"):
            self.assertContains(page, f'name="{field}"')

        res = self.client.post(self.url("accounts_user_change", new.pk), {
            "username": "ramthapa", "email": "ram.thapa@shop.com", "first_name": "Ram",
            "last_name": "Thapa", "is_active": "on", "is_staff": "on",
            "groups": [Group.objects.get(name="Order staff").pk],
            "date_joined_0": "2026-10-01", "date_joined_1": "10:00:00",
        })
        self.assertEqual(res.status_code, 302)
        new.refresh_from_db()
        self.assertTrue(new.is_staff)
        self.assertFalse(new.is_superuser)
        self.assertEqual([g.name for g in new.groups.all()], ["Order staff"])

        # They can now log in to the admin and see exactly the Order staff view.
        ram = Client()
        self.assertTrue(ram.login(username="ram.thapa@shop.com", password=STRONG_PASSWORD))
        html = ram.get(self.url("index")).content.decode()
        self.assertIn(f'href="{self.url("orders_order_changelist")}"', html)
        self.assertNotIn(f'href="{self.url("products_category_changelist")}"', html)
        self.assertEqual(ram.get(self.url("products_category_changelist")).status_code, 403)

    def test_a_duplicate_email_is_refused_whatever_the_case(self):
        self._create()
        res = self._create(email="RAM.THAPA@shop.com", username="other")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "An account with this email already exists.")
        self.assertEqual(User.objects.filter(email__iexact="ram.thapa@shop.com").count(), 1)

    def test_the_email_is_required(self):
        res = self._create(email="")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(username="ramthapa").exists())

    def test_superusers_see_the_admin_links_and_can_reset_passwords(self):
        html = self.links_on_home_page()
        self.assertIn(f'{self.url("accounts_user_changelist")}?account_type=staff', html)
        self.assertIn(f'href="{self.url("auth_group_changelist")}"', html)
        self.assertEqual(self.client.get(self.url("auth_group_changelist")).status_code, 200)
        res = self.client.get(self.url("auth_user_password_change", self.customer.pk))
        self.assertEqual(res.status_code, 200)

    # ---- staff who touched orders can't be deleted, only deactivated ----
    def test_staff_who_collected_cash_cannot_be_deleted(self):
        staff = make_staff("Order staff")
        order = self._order(Order.Status.DELIVERED)
        Payment.objects.get(order=order).mark_cash_collected(collected_by=staff)
        page = self.client.get(self.url("accounts_user_change", staff.pk))
        self.assertContains(page, "This account has collected cash or changed order statuses, so it can't be deleted.")
        self.assertContains(page, "untick")
        self.assertNotContains(page, self.url("accounts_user_delete", staff.pk))
        self.assertEqual(self.client.get(self.url("accounts_user_delete", staff.pk)).status_code, 403)
        self.client.post(self.url("accounts_user_changelist"), {
            "action": "delete_selected", "post": "yes", "_selected_action": [staff.pk],
        })
        self.assertTrue(User.objects.filter(pk=staff.pk).exists())
        with self.assertRaises(ProtectedError):
            staff.delete()
        # Deactivating is the way out: they can no longer log in, and the record stays.
        staff.is_active = False
        staff.save()
        self.assertFalse(Client().login(username="staff1@shop.com", password="pass12345"))
        self.assertEqual(Payment.objects.get(order=order).collected_by, staff)

    def test_staff_who_changed_a_status_cannot_be_deleted(self):
        staff = make_staff("Order staff")
        self.order.change_status(Order.Status.CONFIRMED, changed_by=staff)
        self.assertEqual(self.client.get(self.url("accounts_user_delete", staff.pk)).status_code, 403)
        with self.assertRaises(ProtectedError):
            staff.delete()

    def test_staff_with_no_orders_work_behind_them_can_be_deleted(self):
        staff = make_staff("Order staff")
        res = self.client.post(self.url("accounts_user_delete", staff.pk), {"post": "yes"})
        self.assertRedirects(res, self.url("accounts_user_changelist"))
        self.assertFalse(User.objects.filter(pk=staff.pk).exists())


class NoAccessTests(RoleTestBase):
    def test_staff_with_no_group_see_a_message_and_nothing_else(self):
        nobody = User.objects.create_user(
            username="nobody", email="nobody@shop.com", password="pass12345", is_staff=True
        )
        self.login(nobody)
        res = self.client.get(self.url("index"))
        self.assertContains(res, "Your account has no access yet. Ask an administrator.")
        for name in ("orders_order_changelist", "products_product_changelist", "accounts_user_changelist"):
            self.assertNotContains(res, f'href="{self.url(name)}"')
            self.assertEqual(self.client.get(self.url(name)).status_code, 403)

    def test_customers_cannot_open_the_admin(self):
        self.login(self.customer)
        res = self.client.get(self.url("index"))
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("admin:login"), res.url)
