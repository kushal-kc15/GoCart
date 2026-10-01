from django.test import TestCase
from django.urls import reverse

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
        self.assertContains(response, "No categories available.")
        self.assertContains(response, "No featured products at the moment.")

    def test_backend_stylesheet_is_loaded_after_home_css(self):
        html = self.client.get(reverse("home")).content.decode()
        self.assertLess(html.index("css/dev/home.css"), html.index("css/dev/backend.css"))
