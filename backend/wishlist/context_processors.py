from django.urls import reverse

from .models import WishlistItem


def wishlist(request):
    """Product ids in the user's wishlist: fills the hearts and the header badge.
    One query per page, so cards don't each ask the database."""
    # The admin has no hearts or badge, so don't spend a query on it.
    if request.path.startswith(reverse("admin:index")):
        return {"wishlist_ids": set(), "wishlist_count": 0}

    if not request.user.is_authenticated:
        return {"wishlist_ids": set(), "wishlist_count": 0}

    ids = set(
        WishlistItem.objects.filter(
            wishlist__user=request.user, product__is_available=True
        ).values_list("product_id", flat=True)
    )
    return {"wishlist_ids": ids, "wishlist_count": len(ids)}
