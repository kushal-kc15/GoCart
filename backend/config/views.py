from django.shortcuts import render

from products.models import Category, Product


def home(request):
    categories = Category.objects.all()
    featured_products = Product.objects.filter(
        is_available=True,
        stock__gt=0,
        is_featured=True,
    ).select_related("category").prefetch_related("images")

    return render(
        request,
        "dev/home.html",
        {
            "categories": categories,
            "featured_products": featured_products,
        },
    )
