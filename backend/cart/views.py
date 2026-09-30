from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages

from products.models import Product
from .models import Cart, CartItem


@login_required
def cart_detail(request):
    """View the current user's cart."""
    cart, _ = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.items.select_related("product").all()
    
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
@login_required
def add_to_cart(request):
    """Add a product to the cart."""
    product_id = request.POST.get("product_id")
    product = get_object_or_404(Product, id=product_id)
    
    cart, _ = Cart.objects.get_or_create(user=request.user)
    
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
    )
    if not created:
        cart_item.quantity += 1
        cart_item.save()
        
    messages.success(request, f"{product.name} added to your cart.")
    return redirect("cart:cart_detail")
