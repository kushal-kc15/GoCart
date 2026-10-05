from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from orders.models import Order, OrderItem
from products.models import Category, Product

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
        self.assertContains(response, "order history will appear here")

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
        return f'href="{reverse("orders:order_success", args=[order.pk])}"'

    def test_shows_only_own_orders_each_linking_to_its_page(self):
        mine = self._order(self.user, 300)
        theirs = self._order(self.other, 500)
        response = self.client.get(self.url)
        self.assertContains(response, self._order_link(mine))
        self.assertNotContains(response, self._order_link(theirs))
        self.assertNotContains(response, "order history will appear here")

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

    def test_quick_stats_skip_cancelled_orders(self):
        self._order(self.user, 300)
        self._order(self.user, 200, status=Order.Status.DELIVERED)
        self._order(self.user, 1000, status=Order.Status.CANCELLED)
        response = self.client.get(self.url)
        self.assertContains(response, "Rs. 500")   # 300 + 200, not the cancelled 1000
        self.assertEqual(len(response.context["orders"]), 3)

    def test_coming_soon_items_are_kept_and_disabled(self):
        response = self.client.get(self.url)
        for label in ("Wishlist", "Addresses", "Change Password", "Upload Photo", "Edit Profile"):
            self.assertContains(response, label)
        self.assertContains(
            response, '<button type="button" class="pf-btn" disabled title="Coming soon">✎ Edit Profile</button>',
            html=True,
        )
