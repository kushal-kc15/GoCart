from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.template.defaultfilters import floatformat
from django.urls import reverse
from django.views import View
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, Prefetch
from django.views.decorators.http import require_POST

from accounts.models import Address
from accounts.views import _safe_next_url
from cart.models import Cart
from products.models import Product, ProductImage
from .forms import CheckoutForm
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


def _rupees(amount):
    return f"Rs. {floatformat(amount, '-2')}"


def _account_name(user):
    # The name orders use for now: the account's full name, else its email.
    return user.get_full_name() or user.email


def _delivery_details(form, user):
    """What the order saves about where it goes: (saved Address or None, fields for Order)."""
    data = form.cleaned_data
    name = _account_name(user)
    details = {"landmark": "", "latitude": None, "longitude": None}
    address = None

    if data["delivery_method"] == Order.DeliveryMethod.PICKUP:
        where = f"Pick up at {settings.SHOP_INFO['name']}"
    elif data["saved_address"]:
        address = data["saved_address"]
        where = ", ".join(part for part in (address.address_line, address.area, address.city) if part)
        details.update(landmark=address.landmark, latitude=address.latitude, longitude=address.longitude)
    else:
        where = data["address_line"]
        details.update(landmark=data["landmark"], latitude=data["lat"], longitude=data["lng"])
        if data["save_address"]:
            address = Address.objects.create(
                user=user, recipient_name=name, phone=data["phone"],
                address_line=data["address_line"], landmark=data["landmark"],
                latitude=data["lat"], longitude=data["lng"],
            )

    # Same "Name, address — phone" text as before, cut to fit the column.
    details["address"] = f"{name}, {where} — {data['phone']}"[:255]
    return address, details


class CheckoutView(LoginRequiredMixin, View):
    def _cart_items(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        return cart.items.select_related("product").all()

    def _render(self, request, form, cart_items):
        method = form["delivery_method"].value()
        if method not in Order.DeliveryMethod.values:
            method = Order.DeliveryMethod.DELIVERY
        subtotal, shipping, grand_total = _checkout_totals(cart_items, method)

        # Totals for both methods, worked out here. The page's JavaScript only
        # swaps which one is shown; it never calculates a price.
        totals = {}
        for choice in Order.DeliveryMethod.values:
            _, choice_shipping, choice_total = _checkout_totals(cart_items, choice)
            totals[choice] = {
                "shipping": _rupees(choice_shipping) if choice_shipping else "Free",
                "total": _rupees(choice_total),
            }

        addresses = request.user.addresses.order_by("-is_default", "-created_at")
        try:
            selected_address_id = int(form["address_id"].value())
        except (TypeError, ValueError):
            selected_address_id = None  # "Add new address"

        store = {"name": settings.SHOP_INFO["name"], "address": settings.SHOP_INFO["address"]}
        page_data = {
            "totals": totals,
            "store": store,
            "addresses": [
                {"id": a.pk, "lat": a.latitude, "lng": a.longitude}
                for a in addresses if a.latitude is not None
            ],
            "urls": {"reverse": reverse("geocode_reverse"), "search": reverse("geocode_search")},
        }
        return render(request, "dev/checkout.html", {
            "form": form,
            "method": method,
            "account_name": _account_name(request.user),
            "cart_items": cart_items,
            "subtotal": subtotal,
            "shipping": shipping,
            "grand_total": grand_total,
            "totals": totals,
            "saved_addresses": addresses,
            "selected_address_id": selected_address_id,
            "store": store,
            "page_data": page_data,
        })

    def get(self, request):
        cart_items = self._cart_items(request)
        if not cart_items:
            messages.info(request, "Your cart is empty. Add some items before checkout.")
            return redirect("cart:cart_detail")

        newest = request.user.addresses.order_by("-is_default", "-created_at").first()
        form = CheckoutForm(user=request.user, initial={
            "phone": request.user.phone or "",
            "address_id": newest.pk if newest else None,
        })
        return self._render(request, form, cart_items)

    @transaction.atomic
    def post(self, request):
        cart_items = self._cart_items(request)
        if not cart_items:
            messages.error(request, "Your cart is empty.")
            return redirect("cart:cart_detail")

        form = CheckoutForm(request.POST, user=request.user)
        if not form.is_valid():
            return self._render(request, form, cart_items)

        # Take the stock now. The filter only matches if enough is left, so two
        # shoppers can't both buy the last one; any shortfall undoes everything.
        for item in cart_items:
            taken = Product.objects.filter(pk=item.product_id, stock__gte=item.quantity).update(
                stock=F("stock") - item.quantity
            )
            if not taken:
                item.product.refresh_from_db(fields=["stock"])  # before the rollback: no queries after it
                messages.error(
                    request,
                    f"Sorry, '{item.product.name}' only has {item.product.stock} items in stock.",
                )
                transaction.set_rollback(True)
                return redirect("orders:checkout")

        method = form.cleaned_data["delivery_method"]
        subtotal, shipping, grand_total = _checkout_totals(cart_items, method)
        address, details = _delivery_details(form, request.user)

        order = Order.objects.create(
            user=request.user,
            shipping_address=address,
            status=Order.Status.PENDING,
            delivery_method=method,
            subtotal=subtotal,
            shipping_fee=shipping,
            total=grand_total,
            phone=form.cleaned_data["phone"],
            **details,
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
