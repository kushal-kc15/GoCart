from django.test import TestCase
from django.urls import reverse

from .models import Category, Product, ProductImage


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
            unit="1 kg",
            stock=10,
        )
        ProductImage.objects.create(
            product=product,
            image="products/gallery/red-apples-side.jpg",
            alt_text="Side view of red apples",
            sort_order=2,
        )
        main_image = ProductImage.objects.create(
            product=product,
            image="products/gallery/red-apples-main.jpg",
            alt_text="Main view of red apples",
            sort_order=1,
        )

        response = self.client.get(reverse("products:product_test"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(product, response.context["products"])
        self.assertContains(response, product.name)
        self.assertContains(response, self.category.name)
        self.assertContains(response, product.unit)
        self.assertContains(response, product.price)
        self.assertContains(response, "In Stock")
        self.assertContains(response, main_image.image.url)
        self.assertContains(response, main_image.alt_text)
        self.assertNotContains(response, "red-apples-side.jpg")

    def test_product_page_shows_out_of_stock(self):
        product = Product.objects.create(
            category=self.category,
            name="Green Grapes",
            slug="green-grapes",
            price="200.00",
            unit="500 g",
            stock=0,
        )

        response = self.client.get(reverse("products:product_test"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Out of Stock")
        self.assertContains(response, "No image")


class ProductImageTestPageTests(TestCase):
    def test_product_image_page_displays_product_image_details(self):
        category = Category.objects.create(
            name="Fresh Produce",
            slug="fresh-produce",
        )
        product = Product.objects.create(
            category=category,
            name="Red Apples",
            slug="red-apples",
        )
        product_image = ProductImage.objects.create(
            product=product,
            image="products/gallery/red-apples.jpg",
            alt_text="Fresh red apples",
            sort_order=1,
        )

        response = self.client.get(reverse("products:product_image_test"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(product_image, response.context["product_images"])
        self.assertContains(response, product.name)
        self.assertContains(response, product_image.alt_text)
