from django.conf import settings
from django.db import models

# Create your models here.
class Category(models.Model):
    name=models.CharField(max_length=200)
    slug=models.SlugField(max_length=200, unique=True)
    image=models.ImageField(upload_to='category', blank=True, null=True)
    description=models.TextField(blank=True, null=True)
    created_at=models.DateTimeField(auto_now_add=True)

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
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"],
                name="unique_user_product_review",
            ),
        ]

    def __str__(self):
        return f"Review by {self.user} for {self.product}"
