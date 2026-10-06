from django.shortcuts import render

from django.db.models import Prefetch
from django.views import defaults

from products.models import Category, Product, ProductImage
from products.popular import popular_products


def home(request):
    categories = Category.objects.filter(
        parent__isnull=True
    ).select_related("parent")  # defensive; parent IS null but avoids deferred load

    # Products a customer can actually buy, with images in display order.
    in_stock = Product.objects.filter(
        is_available=True,
        stock__gt=0,
    ).select_related("category").prefetch_related(
        Prefetch("images", queryset=ProductImage.objects.order_by("sort_order", "id"))
    )

    featured_products = in_stock.filter(is_featured=True)

    return render(
        request,
        "dev/home.html",   # switched from home.html to the new dynamic template
        {
            "categories": categories,
            "featured_products": featured_products,
            # Best sellers; the query is shared with the cart page (products/popular.py)
            "popular_products": popular_products(),
        },
    )


# Django looks for 404.html / 500.html at the template root by default.
# Our pages live in dev/, so these handlers name them explicitly.
def page_not_found(request, exception):
    return defaults.page_not_found(request, exception, template_name="dev/404.html")


def server_error(request):
    # Django's server_error renders with no context processors, so it is safe
    # even if the error came from the database or a context processor.
    return defaults.server_error(request, template_name="dev/500.html")
