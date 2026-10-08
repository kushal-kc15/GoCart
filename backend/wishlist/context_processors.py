from django.urls import reverse

from .models import WishlistItem


def wishlist(request):
    """Wishlisted product ids for the hearts and header badge, in one query per page."""
    # The admin has no hearts or badge, so skip the query.
    if request.path.startswith(reverse("admin:index")) or not request.user.is_authenticated:
        return {"wishlist_ids": set(), "wishlist_count": 0}

    ids = set(
        WishlistItem.objects.filter(
            wishlist__user=request.user, product__is_available=True
        ).values_list("product_id", flat=True)
    )
    return {"wishlist_ids": ids, "wishlist_count": len(ids)}
