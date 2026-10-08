from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from cart.views import _json_reply, _login_redirect, _safe_next, _wants_json
from products.models import Product
from .models import Wishlist, WishlistItem


@login_required
def wishlist_detail(request):
    items = (
        WishlistItem.objects.filter(wishlist__user=request.user, product__is_available=True)
        .select_related("product__category")
        .prefetch_related("product__images")
        .order_by("-created_at")
    )
    return render(request, "dev/wishlist.html", {"items": items})


@require_POST
def toggle_wishlist(request):
    # Not @login_required: its redirect would land on this POST-only URL (405).
    if not request.user.is_authenticated:
        return _login_redirect(request, "Please log in to save items to your wishlist.")

    product = get_object_or_404(Product, id=request.POST.get("product_id"))
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)

    # The form says which way to go, so a double click or an old tab can't flip it back.
    if request.POST.get("action") == "remove":
        WishlistItem.objects.filter(wishlist=wishlist, product=product).delete()
        saved = False
        message = f"{product.name} removed from your wishlist."
    else:
        WishlistItem.objects.get_or_create(wishlist=wishlist, product=product)
        saved = True
        message = f"{product.name} saved to your wishlist."

    if _wants_json(request):
        return _json_reply(request, message, product_id=product.id, saved=saved)
    messages.success(request, message)
    return redirect(_safe_next(request, "wishlist:wishlist_detail"))
