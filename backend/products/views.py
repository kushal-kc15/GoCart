from django.shortcuts import render

from .models import Category, Product, ProductImage


def category_test(request):
    categories = Category.objects.all()
    return render(request, 'dev/category_test.html', {'categories': categories})


def product_test(request):
    products = Product.objects.select_related("category").prefetch_related("images")
    return render(request, "dev/product_test.html", {"products": products})


def product_image_test(request):
    product_images = ProductImage.objects.select_related("product").all()
    return render(
        request,
        "dev/product_image_test.html",
        {"product_images": product_images},
    )
