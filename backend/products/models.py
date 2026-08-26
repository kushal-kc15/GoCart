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
    price=models.DecimalField(max_digits=10, decimal_places=2)
    unit=models.CharField(max_length=50, blank=True, null=True)
    stock=models.PositiveIntegerField(default=0)
    image=models.ImageField(upload_to='products', blank=True, null=True)
    is_available=models.BooleanField(default=True)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        ordering=['name']

    def __str__(self):
        return self.name