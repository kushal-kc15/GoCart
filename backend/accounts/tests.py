from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from orders.models import Order, OrderItem
from products.models import Category, Product
from wishlist.models import Wishlist, WishlistItem
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
