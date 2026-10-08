from django.db.models import Sum
from django.urls import reverse

from .models import CartItem


def cart_count(request):
    """Total quantity in the user's cart, for the header badge."""
    # The admin has no badge, so skip the query.
    if request.path.startswith(reverse("admin:index")) or not request.user.is_authenticated:
        return {"cart_count": 0}

    total = CartItem.objects.filter(cart__user=request.user).aggregate(
        total=Sum("quantity")
    )["total"]
    return {"cart_count": total or 0}
