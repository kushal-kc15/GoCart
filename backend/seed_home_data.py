import os
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.core.files import File
from django.utils.text import slugify

from products.models import Category, Product, ProductImage


STATIC_IMAGES = Path(__file__).resolve().parent.parent / "frontend" / "static" / "images"


def add_category_image(category, filename):
    if category.image:
        return

    image_path = STATIC_IMAGES / filename
    if image_path.exists():
        with image_path.open("rb") as image_file:
            category.image.save(filename, File(image_file), save=True)


def add_product_image(product, filename):
    if product.images.exists():
        return

    image_path = STATIC_IMAGES / filename
    if image_path.exists():
        product_image = ProductImage(product=product, alt_text=product.name)
        with image_path.open("rb") as image_file:
            product_image.image.save(filename, File(image_file), save=True)


def seed_home_data():
    category_data = {
        "Fruits": "fruits.jpg",
        "Vegetables": "fruits and vegetables.jpg",
        "Dairy": None,
        "Drinks": "sprite.jpg",
    }
    categories = {}

    for name, image_filename in category_data.items():
        category, _ = Category.objects.get_or_create(name=name, defaults={"slug": slugify(name)})
        categories[name] = category
        if image_filename:
            add_category_image(category, image_filename)

    product_data = [
        ("Apple 1kg", "Fruits", "1 kg", "220.00", 30, True, "fruits.jpg"),
        ("Banana 1 Dozen", "Fruits", "1 dozen", "140.00", 25, True, "fruits.jpg"),
        ("Potato 1kg", "Vegetables", "1 kg", "80.00", 40, True, "potato.jpg"),
        ("Milk 1L", "Dairy", "1 L", "110.00", 20, False, None),
        ("Orange Juice 1L", "Drinks", "1 L", "260.00", 15, False, None),
        ("Coca Cola 1.5L", "Drinks", "1.5 L", "180.00", 18, False, None),
    ]

    for name, category_name, unit, price, stock, is_featured, image_filename in product_data:
        product, _ = Product.objects.update_or_create(
            slug=slugify(name),
            defaults={
                "category": categories[category_name],
                "name": name,
                "price": price,
                "unit": unit,
                "stock": stock,
                "is_available": True,
                "is_featured": is_featured,
            },
        )
        if image_filename:
            add_product_image(product, image_filename)

    print("Home data is ready.")


if __name__ == "__main__":
    seed_home_data()
