from django.test import TestCase
from django.urls import reverse

from .models import Category, Product


class CategoryTestPageTests(TestCase):
    def test_category_page_displays_categories(self):
        category = Category.objects.create(
            name="Fresh Produce",
            slug="fresh-produce",
            description="Fresh fruit and vegetables.",
        )

        response = self.client.get(reverse("products:category_test"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("categories", response.context)
        self.assertIn(category, response.context["categories"])
        self.assertContains(response, category.name)


class ProductTestPageTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Fresh Produce",
            slug="fresh-produce",
        )

    def test_product_page_displays_product_and_category(self):
        product = Product.objects.create(
            category=self.category,
            name="Red Apples",
            slug="red-apples",
            price="150.00",
            unit="kg",
            stock=10,
        )

        response = self.client.get(reverse("products:product_test"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(product, response.context["products"])
        self.assertContains(response, product.name)
        self.assertContains(response, self.category.name)
        self.assertContains(response, "In Stock")

    def test_product_page_shows_out_of_stock(self):
        Product.objects.create(
            category=self.category,
            name="Green Grapes",
            slug="green-grapes",
            price="200.00",
            unit="kg",
            stock=0,
        )

        response = self.client.get(reverse("products:product_test"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Out of Stock")
