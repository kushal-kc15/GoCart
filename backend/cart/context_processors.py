from django.db.models import Sum
from django.urls import reverse

from .models import CartItem


def cart_count(request):
    """Total number of items in the signed-in user's cart, for the header badge."""
    # The admin has no cart badge, so don't spend a query on it.
    if request.path.startswith(reverse("admin:index")):
        return {"cart_count": 0}

    if not request.user.is_authenticated:
        return {"cart_count": 0}

    total = CartItem.objects.filter(cart__user=request.user).aggregate(
        total=Sum("quantity")
    )["total"]
    return {"cart_count": total or 0}
