from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.template.defaultfilters import floatformat
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.urls import reverse
from django.utils.http import urlencode

from accounts.views import _safe_next_url
from products.models import Product
from products.popular import popular_products
from wishlist.context_processors import wishlist as wishlist_counts
from .context_processors import cart_count as cart_counts
from .models import Cart, CartItem


def _wants_json(request):
    """True for the in-place requests sent by common.js."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _json_reply(request, message, level="success", ok=True, **extra):
    # No flash message here, or it would show again on the next page load.
    return JsonResponse({
        "ok": ok,
        "level": level,
        "message": message,
        # Same functions as the header, so the badges can't disagree.
        "cart_count": cart_counts(request)["cart_count"],
        "wishlist_count": wishlist_counts(request)["wishlist_count"],
        **extra,
    })


def _safe_next(request, fallback="cart:cart_detail"):
    """The POSTed 'next' URL if it points back into this site, else the fallback page."""
    return _safe_next_url(request, request.POST.get("next")) or reverse(fallback)


def _login_redirect(request, message="Please log in to add items to your cart."):
    """Send a logged-out user to login, then back to the page they were on."""
    messages.info(request, message)
    query = urlencode({"next": _safe_next(request, "home")})
    login_url = f"{reverse('accounts:login')}?{query}"
    if _wants_json(request):
        # fetch would follow a redirect and use up the message, so send the URL instead.
        return JsonResponse({"ok": False, "redirect": login_url}, status=401)
    return redirect(login_url)


def _cart_totals(cart_items):
    """Sub-total, flat home delivery shipping and grand total."""
    subtotal = sum(item.line_total for item in cart_items)
    shipping = 100 if cart_items else 0
    return subtotal, shipping, subtotal + shipping


def _cart_summary(user):
    """The cart page numbers as text, in the same format as the template."""
    cart_items = CartItem.objects.filter(cart__user=user).select_related("product")
    subtotal, shipping, grand_total = _cart_totals(cart_items)
    return {
        "product_count": len(cart_items),
        "subtotal": f"Rs. {floatformat(subtotal, '-2')}",
        "shipping": f"Rs. {shipping}" if shipping else "Free",
        "grand_total": f"Rs. {floatformat(grand_total, '-2')}",
    }


@login_required
def cart_detail(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.select_related("product").prefetch_related("product__images")

    subtotal, shipping, grand_total = _cart_totals(cart_items)

    context = {
        "cart_items": cart_items,
        "subtotal": subtotal,
        "shipping": shipping,
        "grand_total": grand_total,
        # "You may also like": best sellers not already in the cart.
        "recommended_products": popular_products(
            exclude_ids=[item.product_id for item in cart_items]
        ),
    }
    return render(request, "dev/cart.html", context)


@require_POST
def add_to_cart(request):
    # Not @login_required: its redirect would land on this POST-only URL (405).
    if not request.user.is_authenticated:
        return _login_redirect(request)

    product_id = request.POST.get("product_id")
    product = get_object_or_404(Product, id=product_id)

    # A long-open page can show a product that has since sold out or been hidden.
    problem = None
    if not product.is_available:
        problem = f"{product.name} is no longer available."
    elif product.stock <= 0:
        problem = f"{product.name} is out of stock."
    if problem:
        if _wants_json(request):
            return _json_reply(request, problem, "error", ok=False)
        messages.error(request, problem)
        return redirect(_safe_next(request))

    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)

    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_item, created = CartItem.objects.get_or_create(cart=cart, product=product)

    wanted = quantity if created else cart_item.quantity + quantity
    # Never hold more than what is in stock.
    cart_item.quantity = min(wanted, product.stock)
    cart_item.save()

    if wanted > product.stock:
        message = f"Only {product.stock} of {product.name} in stock."
        level = "info"
    else:
        message = f"{product.name} added to your cart."
        level = "success"

    buy_now = request.POST.get("buy_now")
    if _wants_json(request) and not buy_now:
        return _json_reply(request, message, level, quantity=cart_item.quantity)

    if level == "success":
        messages.success(request, message)
    elif level == "info":
        messages.info(request, message)
    elif level == "error":
        messages.error(request, message)

    # Buy Now goes straight to checkout; Add to Cart returns to the page.
    if buy_now:
        return redirect("orders:checkout")
    return redirect(_safe_next(request))


@require_POST
@login_required
def update_quantity(request):
    item = get_object_or_404(
        CartItem, id=request.POST.get("item_id"), cart__user=request.user
    )
    action = request.POST.get("action")
    message = ""

    if action == "inc":
        if item.product.stock <= 0 or item.quantity < item.product.stock:
            item.quantity += 1
            item.save()
        else:
            message = f"Only {item.product.stock} of {item.product.name} in stock."
    elif action == "dec":
        if item.quantity > 1:
            item.quantity -= 1
            item.save()

    if _wants_json(request):
        return _json_reply(
            request, message, "info", item_id=item.id, quantity=item.quantity,
            **_cart_summary(request.user),
        )
    if message:
        messages.info(request, message)
    return redirect(_safe_next(request))


@require_POST
@login_required
def remove_from_cart(request):
    item = get_object_or_404(
        CartItem, id=request.POST.get("item_id"), cart__user=request.user
    )
    product_name = item.product.name
    item_id = item.id
    item.delete()

    message = f"{product_name} removed from your cart."
    if _wants_json(request):
        summary = _cart_summary(request.user)
        return _json_reply(
            request, message, item_id=item_id, cart_empty=summary["product_count"] == 0,
            **summary,
        )
    messages.success(request, message)
    return redirect(_safe_next(request))
