import os
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.core.files import File
from django.utils.text import slugify

from products.models import Category, Product, ProductImage


STATIC_IMAGES = Path(__file__).resolve().parent.parent / "frontend" / "static" / "images"

CATEGORY_IMAGES = {
    "Packaged & Instant Food": "cup_noodles.jpg",
    "Rice, Atta & Flour": "aata.jpg",
    "Sauces & Spreads": "tomato_sauce.jpg",
    "Tea, Coffee & Health Drink": "green_tea.jpg",
    "Cold Drinks & Juice": "sprite.jpg",
}

PRODUCT_IMAGES = {
    "Wai Wai Chicken Noodles 75g": "cup_noodles.jpg",
    "Gyan Chakki Atta 2kg": "aata.jpg",
    "Tomato Ketchup 500g": "tomato_sauce.jpg",
    "Organic Green Tea 100g": "green_tea.jpg",
    "Sprite 1.5L": "sprite.jpg",
}

FEATURED_PRODUCTS = {
    "Fresh Milk 1L",
    "Wai Wai Chicken Noodles 75g",
    "Current Hot & Spicy Noodles 100g",
    "Gyan Chakki Atta 2kg",
    "Hulas Premium Basmati 5kg",
    "Fortune Sunflower Oil 1L",
    "Tomato Ketchup 500g",
    "Organic Green Tea 100g",
    "Dairy Milk Chocolate 120g",
    "Coca Cola 1.5L",
    "Sprite 1.5L",
}

CATALOG = {
    "Dairy, Bread & Eggs": {
        "Breads & Buns": [
            ("Daily Fresh White Bread 400g", "400 g", "85.00"),
            ("Whole Wheat Brown Bread 400g", "400 g", "110.00"),
        ],
        "Butter & More": [
            ("Amul Butter 500g", "500 g", "640.00"),
            ("Salted Table Butter 200g", "200 g", "285.00"),
        ],
        "Cheese": [
            ("Amul Cheese Slices 200g", "200 g", "360.00"),
            ("Mozzarella Cheese 200g", "200 g", "420.00"),
        ],
        "Cream & Whitener": [
            ("Nestle Cream 250ml", "250 ml", "235.00"),
            ("Everyday Dairy Whitener 400g", "400 g", "525.00"),
        ],
        "Eggs": [
            ("Farm Fresh Eggs 12 Pack", "12 pieces", "240.00"),
            ("Omega Eggs 6 Pack", "6 pieces", "175.00"),
        ],
        "Flakes & Kids Cereals": [
            ("Kellogg Corn Flakes 475g", "475 g", "510.00"),
            ("Chocos Cereal 385g", "385 g", "495.00"),
        ],
        "Milk & Curd": [
            ("Fresh Milk 1L", "1 L", "120.00"),
            ("Plain Yogurt 500g", "500 g", "145.00"),
        ],
    },
    "Packaged & Instant Food": {
        "Noodles": [
            ("Wai Wai Chicken Noodles 75g", "75 g", "25.00"),
            ("Current Hot & Spicy Noodles 100g", "100 g", "55.00"),
            ("Rara Chicken Noodles 75g", "75 g", "25.00"),
            ("2PM Noodles 100g", "100 g", "50.00"),
        ],
        "Pasta": [
            ("Penne Pasta 500g", "500 g", "190.00"),
            ("Spaghetti Pasta 500g", "500 g", "210.00"),
        ],
        "Instant Soup": [
            ("Chicken Instant Soup 45g", "45 g", "65.00"),
            ("Mixed Vegetable Soup 45g", "45 g", "60.00"),
        ],
        "Ready to Eat": [
            ("Ready to Eat Dal Makhani 300g", "300 g", "230.00"),
            ("Ready to Eat Paneer Curry 300g", "300 g", "285.00"),
        ],
        "Instant Snacks": [
            ("Instant Cup Noodles 70g", "70 g", "75.00"),
            ("Masala Oats Cup 50g", "50 g", "90.00"),
        ],
        "Breakfast Food": [
            ("Classic Oats 1kg", "1 kg", "390.00"),
            ("Instant Poha Mix 200g", "200 g", "155.00"),
        ],
    },
    "Rice, Atta & Flour": {
        "Atta": [
            ("Gyan Chakki Atta 2kg", "2 kg", "260.00"),
            ("Hulas Atta 5kg", "5 kg", "590.00"),
            ("Aashirvaad Atta 5kg", "5 kg", "720.00"),
        ],
        "Basmati Rice": [
            ("Hulas Premium Basmati 5kg", "5 kg", "1150.00"),
            ("India Gate Basmati 5kg", "5 kg", "1750.00"),
            ("Goodluck Basmati Rice 5kg", "5 kg", "1280.00"),
        ],
        "Besan, Sooji & Maida": [
            ("Gram Flour Besan 1kg", "1 kg", "210.00"),
            ("Fine Sooji 500g", "500 g", "95.00"),
        ],
        "Chiura & Other": [
            ("Thick Beaten Rice Chiura 1kg", "1 kg", "175.00"),
            ("Taichin Chiura 1kg", "1 kg", "225.00"),
        ],
        "Rice": [
            ("Sona Mansuli Rice 5kg", "5 kg", "690.00"),
            ("Jeera Masino Rice 5kg", "5 kg", "825.00"),
        ],
        "Satu": [
            ("Roasted Chana Satu 500g", "500 g", "180.00"),
        ],
    },
    "Dals & Pulses": {
        "Lentils": [
            ("Masoor Dal 1kg", "1 kg", "245.00"),
            ("Moong Dal 1kg", "1 kg", "285.00"),
        ],
        "Beans": [
            ("Rajma Red Beans 1kg", "1 kg", "320.00"),
            ("Black Beans 500g", "500 g", "190.00"),
        ],
        "Chickpeas": [
            ("Kabuli Chana 1kg", "1 kg", "295.00"),
            ("Black Chickpeas 1kg", "1 kg", "235.00"),
        ],
        "Peas": [
            ("Dried Green Peas 1kg", "1 kg", "220.00"),
            ("White Peas 1kg", "1 kg", "205.00"),
        ],
    },
    "Oil, Ghee & More": {
        "Cooking Oil": [
            ("Fortune Sunflower Oil 1L", "1 L", "285.00"),
            ("Soybean Cooking Oil 1L", "1 L", "260.00"),
        ],
        "Mustard Oil": [
            ("Dhara Mustard Oil 1L", "1 L", "340.00"),
            ("Cold Pressed Mustard Oil 1L", "1 L", "410.00"),
        ],
        "Ghee": [
            ("Pure Cow Ghee 500ml", "500 ml", "720.00"),
            ("Buffalo Ghee 1L", "1 L", "1320.00"),
        ],
        "Olive Oil": [
            ("Extra Virgin Olive Oil 500ml", "500 ml", "890.00"),
            ("Light Olive Oil 1L", "1 L", "1380.00"),
        ],
    },
    "Masala, Dry Fruits & More": {
        "Powder Spices": [
            ("Turmeric Powder 200g", "200 g", "95.00"),
            ("Kashmiri Chilli Powder 200g", "200 g", "165.00"),
        ],
        "Whole Spices": [
            ("Cumin Seeds 200g", "200 g", "155.00"),
            ("Whole Coriander 200g", "200 g", "105.00"),
        ],
        "Dry Fruits": [
            ("California Almonds 500g", "500 g", "760.00"),
            ("Cashew Nuts 500g", "500 g", "895.00"),
        ],
        "Salt": [
            ("Iodized Salt 1kg", "1 kg", "35.00"),
            ("Himalayan Pink Salt 500g", "500 g", "130.00"),
        ],
    },
    "Sauces & Spreads": {
        "Ketchup": [
            ("Tomato Ketchup 500g", "500 g", "185.00"),
            ("Hot and Sweet Ketchup 500g", "500 g", "205.00"),
        ],
        "Mayonnaise": [
            ("Classic Mayonnaise 500g", "500 g", "290.00"),
            ("Eggless Mayonnaise 500g", "500 g", "275.00"),
        ],
        "Jam": [
            ("Mixed Fruit Jam 500g", "500 g", "260.00"),
            ("Strawberry Jam 500g", "500 g", "285.00"),
        ],
        "Peanut Butter": [
            ("Creamy Peanut Butter 340g", "340 g", "395.00"),
            ("Crunchy Peanut Butter 340g", "340 g", "410.00"),
        ],
        "Chutney": [
            ("Mint Chutney 250g", "250 g", "145.00"),
            ("Tamarind Chutney 250g", "250 g", "155.00"),
        ],
    },
    "Tea, Coffee & Health Drink": {
        "Tea": [
            ("CTC Black Tea 500g", "500 g", "360.00"),
            ("Masala Tea 250g", "250 g", "245.00"),
        ],
        "Coffee": [
            ("Classic Instant Coffee 100g", "100 g", "385.00"),
            ("Premium Ground Coffee 250g", "250 g", "520.00"),
        ],
        "Green Tea": [
            ("Organic Green Tea 100g", "100 g", "295.00"),
            ("Lemon Green Tea 25 Bags", "25 bags", "230.00"),
        ],
        "Malt Drinks": [
            ("Chocolate Malt Drink 500g", "500 g", "485.00"),
            ("Classic Health Malt 500g", "500 g", "510.00"),
        ],
    },
    "Sweet Tooth": {
        "Chocolates": [
            ("Dairy Milk Chocolate 120g", "120 g", "190.00"),
            ("Dark Chocolate 100g", "100 g", "260.00"),
        ],
        "Candy": [
            ("Assorted Fruit Candy 200g", "200 g", "145.00"),
            ("Mint Candy 150g", "150 g", "120.00"),
        ],
        "Desserts": [
            ("Gulab Jamun Mix 200g", "200 g", "175.00"),
        ],
    },
    "Snacks & Munchies": {
        "Chips": [
            ("Classic Salted Potato Chips 100g", "100 g", "95.00"),
            ("Spicy Masala Chips 100g", "100 g", "100.00"),
        ],
        "Namkeen": [
            ("Bombay Mix Namkeen 400g", "400 g", "225.00"),
            ("Aloo Bhujia 400g", "400 g", "240.00"),
        ],
        "Popcorn": [
            ("Butter Popcorn 90g", "90 g", "85.00"),
            ("Caramel Popcorn 100g", "100 g", "130.00"),
        ],
        "Crackers": [
            ("Salted Crackers 200g", "200 g", "135.00"),
            ("Cheese Crackers 200g", "200 g", "165.00"),
        ],
    },
    "Cold Drinks & Juice": {
        "Soft Drinks": [
            ("Coca Cola 1.5L", "1.5 L", "180.00"),
            ("Sprite 1.5L", "1.5 L", "180.00"),
            ("Fanta Orange 1.5L", "1.5 L", "180.00"),
        ],
        "Fruit Juice": [
            ("Orange Juice 1L", "1 L", "275.00"),
            ("Mixed Fruit Juice 1L", "1 L", "285.00"),
        ],
        "Energy Drinks": [
            ("Red Bull Energy Drink 250ml", "250 ml", "210.00"),
            ("Strong Energy Drink 250ml", "250 ml", "145.00"),
        ],
        "Water": [
            ("Mineral Water 1L", "1 L", "30.00"),
        ],
    },
    "Cleaning Essentials": {
        "Laundry": [
            ("Laundry Detergent Powder 1kg", "1 kg", "260.00"),
            ("Liquid Laundry Detergent 1L", "1 L", "390.00"),
        ],
        "Dishwash": [
            ("Dishwash Bar 200g", "200 g", "55.00"),
            ("Dishwash Liquid 500ml", "500 ml", "165.00"),
        ],
        "Floor Cleaner": [
            ("Lemon Floor Cleaner 1L", "1 L", "245.00"),
            ("Disinfectant Floor Cleaner 1L", "1 L", "285.00"),
        ],
        "Toilet Cleaner": [
            ("Power Toilet Cleaner 500ml", "500 ml", "175.00"),
            ("Bathroom Cleaner 500ml", "500 ml", "195.00"),
        ],
    },
    "Personal Care": {
        "Soap": [
            ("Moisturizing Bath Soap 125g", "125 g", "95.00"),
            ("Neem Herbal Soap 100g", "100 g", "75.00"),
        ],
        "Shampoo": [
            ("Anti Dandruff Shampoo 340ml", "340 ml", "425.00"),
            ("Daily Care Shampoo 340ml", "340 ml", "390.00"),
        ],
        "Toothpaste": [
            ("Complete Care Toothpaste 200g", "200 g", "195.00"),
            ("Herbal Toothpaste 200g", "200 g", "185.00"),
        ],
        "Skin Care": [
            ("Moisturizing Body Lotion 400ml", "400 ml", "485.00"),
            ("Aloe Vera Face Wash 150ml", "150 ml", "285.00"),
        ],
    },
}


def save_category_image(category, filename):
    if category.image:
        return

    image_path = STATIC_IMAGES / filename
    if image_path.exists():
        with image_path.open("rb") as image_file:
            category.image.save(filename, File(image_file), save=True)


def save_product_image(product, filename):
    if product.images.exists():
        return

    image_path = STATIC_IMAGES / filename
    if image_path.exists():
        product_image = ProductImage(product=product, alt_text=product.name)
        with image_path.open("rb") as image_file:
            product_image.image.save(filename, File(image_file), save=True)


def seed_catalog_data():
    stock_values = [5, 10, 15, 20, 25, 30]
    product_number = 0

    for parent_name, subcategories in CATALOG.items():
        parent, _ = Category.objects.update_or_create(
            slug=slugify(parent_name),
            defaults={
                "name": parent_name,
                "description": f"Browse {parent_name.lower()} products.",
                "parent": None,
            },
        )

        category_image = CATEGORY_IMAGES.get(parent_name)
        if category_image:
            save_category_image(parent, category_image)

        for subcategory_name, products in subcategories.items():
            subcategory, _ = Category.objects.update_or_create(
                slug=slugify(subcategory_name),
                defaults={
                    "name": subcategory_name,
                    "description": f"Shop products from {subcategory_name}.",
                    "parent": parent,
                },
            )

            for name, unit, price in products:
                stock = stock_values[product_number % len(stock_values)]
                product_number += 1
                product, _ = Product.objects.update_or_create(
                    slug=slugify(name),
                    defaults={
                        "category": subcategory,
                        "name": name,
                        "description": f"{name} for your everyday grocery needs.",
                        "price": price,
                        "unit": unit,
                        "stock": stock,
                        "is_available": True,
                        "is_featured": name in FEATURED_PRODUCTS,
                    },
                )

                product_image = PRODUCT_IMAGES.get(name)
                if product_image:
                    save_product_image(product, product_image)

    print("Catalog data is ready.")


if __name__ == "__main__":
    seed_catalog_data()
