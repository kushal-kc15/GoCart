from django.db.models import Prefetch, Q, Sum

from orders.models import Order
from .models import Product, ProductImage

POPULAR_LIMIT = 8


def popular_products(exclude_ids=()):
    """Best sellers (cancelled orders don't count), else featured, else newest."""
    in_stock = Product.objects.filter(
        is_available=True,
        stock__gt=0,
    ).exclude(
        id__in=exclude_ids,
    ).select_related("category").prefetch_related(
        Prefetch("images", queryset=ProductImage.objects.order_by("sort_order", "id"))
    )

    popular = list(
        in_stock.annotate(
            sold=Sum(
                "orderitem__quantity",
                filter=~Q(orderitem__order__status=Order.Status.CANCELLED),
            ),
        ).filter(sold__gt=0).order_by("-sold", "name")[:POPULAR_LIMIT]
    )
    if not popular:
        popular = list(in_stock.filter(is_featured=True)[:POPULAR_LIMIT])
    if not popular:
        popular = list(in_stock.order_by("-created_at", "-id")[:POPULAR_LIMIT])
    return popular
