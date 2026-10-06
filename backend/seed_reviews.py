# Local demo data only. Never run on production.
#
# Adds sample customers and product reviews so the product page's ratings
# section can be tested. Run from backend/:  python seed_reviews.py
# Safe to re-run: it updates the same rows instead of adding duplicates.
import os
import sys
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from products.models import Product, Review

if not settings.DEBUG:
    sys.exit("Refusing to run: DEBUG is off. This script is for local demo data only.")

User = get_user_model()

# Six customers, so a product can have up to six reviews (one per customer).
CUSTOMERS = [
    ("demo1", "Aarati", "Shrestha"),
    ("demo2", "Bikash", "Gurung"),
    ("demo3", "Sita", "Thapa"),
    ("demo4", "Ramesh", "Karki"),
    ("demo5", "Pooja", "Adhikari"),
    ("demo6", "Suman", "Rai"),
]

# Taken in turn, so every run gives the same data. Mostly 4-5 stars, a few low ones.
SAMPLE_REVIEWS = [
    (5, "Fresh and well packed. Delivery was on time."),
    (4, "Good quality for the price. Will order again."),
    (5, "Exactly as shown. My family loved it."),
    (2, "The pack was a little damaged when it arrived."),
    (4, "Tastes good, though I wish there was a bigger size."),
    (5, "Better than what I get at the local shop."),
    (3, "Okay, nothing special. Does the job."),
    (5, "Quick delivery to Lalitpur and great quality."),
    (4, "Good value. The rider was very polite."),
    (1, "Arrived close to the expiry date. Not happy."),
    (5, "Always fresh. This is now a regular in our kitchen."),
    (4, "Nice product, packaging could be better."),
    (5, "Perfect for Dashain cooking. Highly recommended."),
    (3, "Fine, but a bit pricey compared to last month."),
]

# Reviews per product for the first nine products; the rest stay empty (empty state).
REVIEW_COUNTS = [2, 3, 4, 5, 6, 3, 4, 2, 5]


def main():
    customers = []
    new_customers = 0
    for username, first, last in CUSTOMERS:
        user, created = User.objects.get_or_create(
            email=f"{username}@gocart.test",
            defaults={"username": username},
        )
        user.first_name = first
        user.last_name = last
        user.set_unusable_password()  # nobody can log in as a demo customer
        user.save()
        customers.append(user)
        new_customers += created

    products = list(Product.objects.filter(is_available=True).order_by("name")[: len(REVIEW_COUNTS)])
    now = timezone.now()
    next_sample = 0
    new_reviews = updated_reviews = 0

    for product, count in zip(products, REVIEW_COUNTS):
        for i, customer in enumerate(customers[:count]):
            rating, comment = SAMPLE_REVIEWS[next_sample % len(SAMPLE_REVIEWS)]
            next_sample += 1
            review, created = Review.objects.update_or_create(
                user=customer,
                product=product,
                defaults={"rating": rating, "comment": comment, "is_visible": True},
            )
            # Spread the dates out so "newest first" is visible on the page.
            Review.objects.filter(pk=review.pk).update(created_at=now - timedelta(days=3 + i * 9))
            if created:
                new_reviews += 1
            else:
                updated_reviews += 1

    total = Product.objects.count()
    print(
        f"Customers: {len(customers)} ({new_customers} new) | "
        f"Reviews: {new_reviews + updated_reviews} on {len(products)} products "
        f"({new_reviews} new, {updated_reviews} updated) | "
        f"Products with no reviews: {total - Product.objects.filter(reviews__isnull=False).distinct().count()}"
    )


if __name__ == "__main__":
    main()
