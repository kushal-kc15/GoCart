from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode

from products.models import Product
from .models import Cart, CartItem


def _safe_next(request, fallback="cart:cart_detail"):
    """Return the POSTed 'next' URL only if it points back into this site."""
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return redirect(fallback).url


def _login_redirect(request):
    """Send a logged-out user to login, then back to the page they were on."""
    messages.info(request, "Please log in to add items to your cart.")
    query = urlencode({"next": _safe_next(request, "home")})
    return redirect(f"{reverse('accounts:login')}?{query}")


@login_required
def cart_detail(request):
    """View the current user's cart."""
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.select_related("product").prefetch_related("product__images")

    subtotal = sum(item.product.price * item.quantity for item in cart_items)
    shipping = 100 if cart_items else 0
    grand_total = subtotal + shipping

    context = {
        "cart_items": cart_items,
        "subtotal": subtotal,
        "shipping": shipping,
        "grand_total": grand_total,
    }
    return render(request, "dev/cart.html", context)


@require_POST
def add_to_cart(request):
    """Add a product to the cart, honouring a requested quantity (capped at stock)."""
    # Not @login_required: its redirect would send the user back to this POST-only URL (405).
    if not request.user.is_authenticated:
        return _login_redirect(request)

    product_id = request.POST.get("product_id")
    product = get_object_or_404(Product, id=product_id)

    # Parse the requested quantity; default to 1 on anything invalid.
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)

    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)

    new_quantity = quantity if created else cart_item.quantity + quantity
    # Never let the cart hold more than what is in stock.
    if product.stock > 0:
        new_quantity = min(new_quantity, product.stock)
    cart_item.quantity = new_quantity
    cart_item.save()

    messages.success(request, f"{product.name} added to your cart.")
    # Buy Now goes straight to checkout; Add to Cart returns to the page.
    if request.POST.get("buy_now"):
        return redirect("orders:checkout")
    return redirect(_safe_next(request))


@require_POST
@login_required
def update_quantity(request):
    """Increase or decrease a cart item's quantity by one."""
    item = get_object_or_404(
        CartItem, id=request.POST.get("item_id"), cart__user=request.user
    )
    action = request.POST.get("action")

    if action == "inc":
        if item.product.stock <= 0 or item.quantity < item.product.stock:
            item.quantity += 1
            item.save()
        else:
            messages.info(request, f"Only {item.product.stock} of {item.product.name} in stock.")
    elif action == "dec":
        if item.quantity > 1:
            item.quantity -= 1
            item.save()

    return redirect(_safe_next(request))


@require_POST
@login_required
def remove_from_cart(request):
    """Remove a cart item entirely."""
    item = get_object_or_404(
        CartItem, id=request.POST.get("item_id"), cart__user=request.user
    )
    product_name = item.product.name
    item.delete()

    messages.success(request, f"{product_name} removed from your cart.")
    return redirect(_safe_next(request))
