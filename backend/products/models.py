from django.conf import settings
from django.db import models

# A product with stock under this counts as "low stock" (admin filter and dashboard).
LOW_STOCK_LIMIT = 10

# Create your models here.
class Category(models.Model):
    name=models.CharField(max_length=200)
    slug=models.SlugField(max_length=200, unique=True)
    image=models.ImageField(upload_to='category', blank=True, null=True)
    description=models.TextField(blank=True, null=True)
    created_at=models.DateTimeField(auto_now_add=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="subcategories",
    )

    class Meta:
        verbose_name_plural='Categories'
        ordering=['name']

    def __str__(self):
        return self.name

class Product(models.Model):
    category=models.ForeignKey(Category,on_delete=models.CASCADE, related_name='products')
    name=models.CharField(max_length=200)
    slug=models.SlugField(max_length=200, unique=True)
    description=models.TextField(blank=True, null=True)
    price=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit=models.CharField(max_length=50, blank=True, null=True)
    stock=models.PositiveIntegerField(default=0)
    is_available=models.BooleanField(default=True)
    is_featured=models.BooleanField(default=False)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        ordering=['name']

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/gallery")
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Image for {self.product.name}"


def star_text(rating):
    """Rating as stars, e.g. 4 -> "★★★★☆"."""
    return "★" * rating + "☆" * (5 - rating)


class Review(models.Model):
    class Rating(models.IntegerChoices):
        ONE_STAR = 1, "1 star"
        TWO_STARS = 2, "2 stars"
        THREE_STARS = 3, "3 stars"
        FOUR_STARS = 4, "4 stars"
        FIVE_STARS = 5, "5 stars"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(choices=Rating.choices)
    comment = models.TextField(max_length=1000)
    # Staff can hide a review in the admin; reviews show straight away otherwise.
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_user_product_review",
            ),
            # Choices are only checked by forms; this guards the database too.
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="review_rating_1_to_5",
            ),
        ]

    def __str__(self):
        return f"Review by {self.user} for {self.product}"

    @property
    def reviewer_name(self):
        """First name and last initial, e.g. "Asha S." (never the email)."""
        first = self.user.first_name or "GoCart customer"
        last = self.user.last_name[:1]
        return f"{first} {last}." if last else first

    @property
    def stars(self):
        return star_text(self.rating)
