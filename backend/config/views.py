from django.shortcuts import render

from django.db.models import Prefetch
from django.views import defaults

from products.models import Category, Product, ProductImage
from products.popular import popular_products


def home(request):
    categories = Category.objects.filter(parent__isnull=True).select_related("parent")

    in_stock = Product.objects.filter(
        is_available=True,
        stock__gt=0,
    ).select_related("category").prefetch_related(
        Prefetch("images", queryset=ProductImage.objects.order_by("sort_order", "id"))
    )

    featured_products = in_stock.filter(is_featured=True)

    return render(
        request,
        "dev/home.html",
        {
            "categories": categories,
            "featured_products": featured_products,
            "popular_products": popular_products(),
        },
    )


# Our 404/500 pages live in dev/, so name them.
def page_not_found(request, exception):
    return defaults.page_not_found(request, exception, template_name="dev/404.html")


def server_error(request):
    # server_error uses no context processors, so it works even if the database is down.
    return defaults.server_error(request, template_name="dev/500.html")
