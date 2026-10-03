from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from config.views import server_error
from products.models import Category, Product


class HomePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Category.objects.create(name="Fruits & Veg", slug="fruits-veg")
        sub = Category.objects.create(name="Fruits", slug="fruits", parent=cls.dept)
        Product.objects.create(
            category=sub, name="Sweet Mango", slug="sweet-mango", price=120, unit="1 kg", stock=5, is_featured=True,
        )
        Product.objects.create(category=sub, name="Plain Apple", slug="plain-apple", price=90, stock=5)
        Product.objects.create(
            category=sub, name="Sold Out Pear", slug="sold-out-pear", price=80, stock=0, is_featured=True,
        )
        Product.objects.create(
            category=sub, name="Hidden Kiwi", slug="hidden-kiwi", price=80, stock=4,
            is_featured=True, is_available=False,
        )

    def test_categories_and_featured_products_render_from_database(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fruits &amp; Veg")
        self.assertContains(response, "Sweet Mango")
        self.assertContains(response, "rs. 120")
        self.assertEqual(list(response.context["categories"]), [self.dept])  # only top-level departments

    def test_non_featured_out_of_stock_and_unavailable_products_are_hidden(self):
        response = self.client.get(reverse("home"))
        for name in ("Plain Apple", "Sold Out Pear", "Hidden Kiwi"):
            self.assertNotContains(response, name)

    def test_empty_states(self):
        Product.objects.all().delete()
        Category.objects.all().delete()
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No categories yet.")
        self.assertContains(response, "No featured products yet.")


# The test runner already uses DEBUG=False; it is explicit here because
# with DEBUG=True Django shows its own debug 404 page instead of ours.
@override_settings(DEBUG=False)
class ErrorPageTests(TestCase):
    def test_unknown_url_uses_custom_404(self):
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "dev/404.html")
        self.assertContains(response, "Page not found", status_code=404)
        self.assertContains(response, reverse("products:product_list"), status_code=404)

    def test_missing_product_uses_custom_404(self):
        # get_object_or_404 in the product detail view goes through the same handler
        response = self.client.get(reverse("products:product_detail", args=["nope"]))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, "dev/404.html")

    def test_500_page_is_standalone_and_uses_no_queries(self):
        # Call the handler directly: the test client re-raises real errors.
        request = RequestFactory().get("/")
        with self.assertNumQueries(0):
            response = server_error(request)
        self.assertEqual(response.status_code, 500)
        self.assertContains(response, 'href="/"', status_code=500)
        self.assertNotIn("<header", response.content.decode())  # does not use base.html
