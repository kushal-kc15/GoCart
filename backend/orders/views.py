from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Prefetch
from django.views.decorators.http import require_POST

from accounts.views import _safe_next_url
from cart.models import Cart
from products.models import ProductImage
from .forms import AddressForm
from .models import Order, OrderItem, OrderStatusChange, Payment

SHIPPING_FEE = 100
ORDERS_PER_PAGE = 10

# My Orders tabs, picked with ?status=<key>; anything unknown shows all.
ORDER_TABS = [
    ("all", "All"),
    ("active", "Active"),
    ("delivered", "Delivered"),
    ("cancelled", "Cancelled"),
]
STATUSES_FOR_TAB = {
    "active": [
        Order.Status.PENDING,
        Order.Status.CONFIRMED,
        Order.Status.PACKED,
        Order.Status.OUT_FOR_DELIVERY,
        Order.Status.READY_FOR_PICKUP,
    ],
    "delivered": [Order.Status.DELIVERED],
    "cancelled": [Order.Status.CANCELLED],
}


def _checkout_totals(cart_items, delivery_method):
    """Sub-total, shipping (flat fee, pickup is free) and grand total."""
    subtotal = sum(item.line_total for item in cart_items)
    shipping = 0 if delivery_method == Order.DeliveryMethod.PICKUP else SHIPPING_FEE
    return subtotal, shipping, subtotal + shipping


class CheckoutView(LoginRequiredMixin, View):
    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart_items = cart.items.select_related("product").all()

        if not cart_items:
            messages.info(request, "Your cart is empty. Add some items before checkout.")
            return redirect("cart:cart_detail")

        subtotal, shipping, grand_total = _checkout_totals(cart_items, Order.DeliveryMethod.DELIVERY)

        context = {
            "form": AddressForm(),
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

        form = AddressForm(request.POST)
        delivery_method = request.POST.get("delivery_method", Order.DeliveryMethod.DELIVERY)
        if delivery_method not in Order.DeliveryMethod.values:
            delivery_method = Order.DeliveryMethod.DELIVERY

        subtotal, shipping, grand_total = _checkout_totals(cart_items, delivery_method)

        if not form.is_valid():
            context = {
                "form": form,
                "cart_items": cart_items,
                "subtotal": subtotal,
                "shipping": shipping,
                "grand_total": grand_total,
            }
            return render(request, "dev/checkout.html", context)

        # Re-validate stock inside the transaction; roll back on any shortfall.
        for item in cart_items:
            if item.product.stock < item.quantity:
                messages.error(
                    request,
                    f"Sorry, '{item.product.name}' only has {item.product.stock} items in stock.",
                )
                transaction.set_rollback(True)
                return redirect("orders:checkout")

        address = form.save(commit=False)
        address.user = request.user
        address.save()
        address_line = f"{address.recipient_name}, {address.address_line}"
        if address.area:
            address_line += f", {address.area}"
        address_line += f", {address.city} — {address.phone}"

        order = Order.objects.create(
            user=request.user,
            shipping_address=address,
            status=Order.Status.PENDING,
            delivery_method=delivery_method,
            subtotal=subtotal,
            shipping_fee=shipping,
            total=grand_total,
            address=address_line,
        )
        # First status history row (no "from" status).
        OrderStatusChange.objects.create(
            order=order, to_status=Order.Status.PENDING,
            changed_by=request.user, note="Order placed",
        )

        for item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=item.product,
                product_name=item.product.name,
                quantity=item.quantity,
                price=item.product.price,
            )
            item.product.stock -= item.quantity
            item.product.save(update_fields=["stock"])

        # Pending until the courier collects the cash.
        Payment.objects.create(
            order=order,
            method=Payment.Method.COD,
            status=Payment.Status.PENDING,
            amount=grand_total,
        )

        cart_items.delete()

        messages.success(request, "Order placed successfully!")
        return redirect("orders:order_success", pk=order.pk)


@login_required
def order_list(request):
    tab = request.GET.get("status", "all")
    if tab not in STATUSES_FOR_TAB:
        tab = "all"

    # Items, products and images load in 3 queries for the whole page.
    orders = request.user.orders.prefetch_related(
        Prefetch(
            "items__product__images",
            queryset=ProductImage.objects.order_by("sort_order", "id"),
        )
    )
    if tab != "all":
        orders = orders.filter(status__in=STATUSES_FOR_TAB[tab])

    paginator = Paginator(orders, ORDERS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    page_range = paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1)

    return render(request, "dev/order_list.html", {
        "page_obj": page_obj,
        "page_range": page_range,
        "tabs": ORDER_TABS,
        "tab": tab,
    })


@login_required
def order_success(request, pk):
    order = get_object_or_404(
        Order.objects.prefetch_related("items"), pk=pk, user=request.user
    )
    return render(request, "dev/order_success.html", {"order": order})


@login_required
def order_detail(request, pk):
    order = get_object_or_404(
        Order.objects.select_related("payment").prefetch_related("items"),
        pk=pk, user=request.user,
    )
    return render(request, "dev/order_detail.html", {
        "order": order,
        "steps": order.tracker_steps(),
    })


@require_POST
@login_required
def cancel_order(request, pk):
    order = get_object_or_404(Order, pk=pk, user=request.user)
    # Staff may cancel later in the flow, but customers only while pending.
    if order.status == Order.Status.PENDING and order.change_status(
        Order.Status.CANCELLED, changed_by=request.user, note="Cancelled by customer"
    ):
        messages.success(request, f"Order #{order.pk} has been cancelled.")
    else:
        messages.error(request, "This order can no longer be cancelled.")

    # From My Orders, go back to the same tab and page.
    next_url = _safe_next_url(request, request.POST.get("next"))
    if next_url:
        return redirect(next_url)
    return redirect("orders:order_detail", pk=order.pk)
