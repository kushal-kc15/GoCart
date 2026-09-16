from django.shortcuts import get_object_or_404, render
from .models import Category, Product, ProductImage


def category_list(request):
    categories = Category.objects.all()
    return render(request, 'dev/category_test.html', {'categories': categories})


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug)
    products = category.products.filter(
        is_available=True,
        stock__gt=0,
    ).prefetch_related("images")
    return render(
        request,
        "dev/category_detail_test.html",
        {"category": category, "products": products},
    )


def product_list(request):
    products = Product.objects.select_related("category").prefetch_related("images")
    return render(request, "dev/product_test.html", {"products": products})


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category").prefetch_related("images"),
        slug=slug,
    )
    return render(request, "dev/product_detail_test.html", {"product": product})


def product_images(request):
    product_images = ProductImage.objects.select_related("product")
    return render(
        request,
        "dev/product_image_test.html",
        {"product_images": product_images},
    )
