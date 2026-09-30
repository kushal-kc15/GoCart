from django.shortcuts import render

from products.models import Category, Product


def home(request):
    categories = Category.objects.filter(
        parent__isnull=True
    ).select_related("parent")  # defensive; parent IS null but avoids deferred load

    featured_products = Product.objects.filter(
        is_available=True,
        stock__gt=0,
        is_featured=True,
    ).select_related("category").prefetch_related("images")

    return render(
        request,
        "dev/home.html",   # switched from home.html to the new dynamic template
        {
            "categories": categories,
            "featured_products": featured_products,
        },
    )
