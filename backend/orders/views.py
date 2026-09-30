from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db import transaction

from cart.models import Cart
from .models import Order, OrderItem

class CheckoutView(LoginRequiredMixin, View):
    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart_items = cart.items.select_related("product").all()
        
        if not cart_items:
            messages.info(request, "Your cart is empty. Add some items before checkout.")
            return redirect("cart:cart_detail")
            
        subtotal = sum(item.product.price * item.quantity for item in cart_items)
        shipping = 100 if cart_items else 0
        grand_total = subtotal + shipping
        
        context = {
            "cart_items": cart_items,
            "subtotal": subtotal,
            "shipping": shipping,
            "grand_total": grand_total,
        }
        return render(request, "dev/checkout.html", context)

    @transaction.atomic
    def post(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart_items = cart.items.select_related("product").all()
        
        if not cart_items:
            messages.error(request, "Your cart is empty.")
            return redirect("cart:cart_detail")

        # Validation Loop
        for item in cart_items:
            if item.product.stock < item.quantity:
                messages.error(request, f"Sorry, '{item.product.name}' only has {item.product.stock} items in stock.")
                transaction.set_rollback(True)
                return redirect("orders:checkout")
        
        subtotal = sum(item.product.price * item.quantity for item in cart_items)
        shipping = 100 if cart_items else 0
        grand_total = subtotal + shipping
        delivery_method = request.POST.get("delivery_method", Order.DeliveryMethod.DELIVERY)
        
        # Create Order
        order = Order.objects.create(
            user=request.user,
            status=Order.Status.PENDING,
            delivery_method=delivery_method,
            subtotal=subtotal,
            shipping_fee=shipping,
            total=grand_total,
            address="To be provided"  # Default since no address form exists yet
        )
        
        # Create OrderItems and Update Stock
        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item.product,
                product_name=item.product.name,
                quantity=item.quantity,
                price=item.product.price
            )
            # Deduct stock
            item.product.stock -= item.quantity
            item.product.save(update_fields=['stock'])
            
        # Clear Cart
        cart_items.delete()
        
        messages.success(request, "Order placed successfully!")
        return redirect("home")
