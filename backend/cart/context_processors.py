from django.db.models import Sum

from .models import CartItem


def cart_count(request):
    """Total number of items in the signed-in user's cart, for the header badge."""
    if not request.user.is_authenticated:
        return {"cart_count": 0}

    total = CartItem.objects.filter(cart__user=request.user).aggregate(
        total=Sum("quantity")
    )["total"]
    return {"cart_count": total or 0}
