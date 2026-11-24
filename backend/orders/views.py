from config.currency import format_nepali
import logging

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
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from accounts.models import Address
from accounts.views import _safe_next_url
from cart.models import Cart
from products.models import Product, ProductImage
from .forms import CheckoutForm, is_in_nepal
from .models import Order, OrderItem, OrderStatusChange, Payment

logger = logging.getLogger(__name__)

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
    return f"Rs. {format_nepali(amount, '-2')}"


def _account_name(user):
    # The name orders use: the account's full name. Never the email; checkout asks
    # an account without a name for one (CheckoutForm.full_name).
    return user.get_full_name()


def _delivery_details(form, user):
    """What the order saves about where it goes: (fields for Order)."""
    data = form.cleaned_data
    details = {"landmark": "", "latitude": None, "longitude": None}

    if data["delivery_method"] == Order.DeliveryMethod.PICKUP:
        where = f"Pick up at {settings.SHOP_INFO['name']}"
    else:
        # The city and area come from the map lookup (CheckoutForm.clean).
        street, city = data["address_line"], data["city"]
        if not street:
            # Only on the map, with a landmark: the area the map found (e.g. "Pokhara") stands
            # in for the street and already names the city. Without a lookup, the landmark does.
            street, city = data["area"] or data["landmark"], ""
        where = ", ".join(part for part in (street, city) if part)
        details.update(landmark=data["landmark"], latitude=data["lat"], longitude=data["lng"])

    # Only where it goes (street, area, city), cut to fit the column. The name comes
    # from the account and the phone has its own field. Older orders still have
    # "Name, address — phone" here.
    details["address"] = where[:255]
    return details


class CheckoutView(LoginRequiredMixin, View):
    def _cart_items(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        # Images for the summary's thumbnails, in one query.
        return cart.items.select_related("product").prefetch_related("product__images")

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

        shop = settings.SHOP_INFO
        store = {
            "name": shop["name"], "address": shop["address"],
            "lat": shop.get("latitude"), "lng": shop.get("longitude"),
        }
        page_data = {
            "totals": totals,
            "store": store,
            "center": {"lat": 28.2096, "lng": 83.9856},
            "urls": {"reverse": reverse("geocode_reverse"), "search": reverse("geocode_search")},
        }
        return render(request, "dev/checkoutpage.html", {
            "form": form,
            "method": method,
            "account_name": _account_name(request.user),
            "needs_name": "full_name" in form.fields,
            "cart_items": cart_items,
            "subtotal": subtotal,
            "shipping": shipping,
            "grand_total": grand_total,
            "totals": totals,
            "store": store,
            "page_data": page_data,
        })

    def _cancel_abandoned_esewa_orders(self, user):
        """Cancel any pending eSewa orders where the user never completed payment."""
        abandoned = Order.objects.filter(
            user=user,
            status=Order.Status.PENDING,
            payment__method=Payment.Method.ESEWA,
            payment__status=Payment.Status.PENDING,
        )
        for order in abandoned:
            order.change_status(
                Order.Status.CANCELLED,
                note="Abandoned eSewa payment",
            )

    def get(self, request):
        cart_items = self._cart_items(request)
        if not cart_items:
            messages.info(request, "Your cart is empty. Add some items before checkout.")
            return redirect("cart:cart_detail")

        self._cancel_abandoned_esewa_orders(request.user)

        form = CheckoutForm(user=request.user, initial={
            "phone": request.user.phone or "",
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

        # An account without a name gives one here. It is kept for next time
        # (and the header's "Hi, ..."): the first word is the first name.
        full_name = form.cleaned_data.get("full_name")
        if full_name:
            names = full_name.split(maxsplit=1)
            request.user.first_name = names[0]
            request.user.last_name = names[1] if len(names) > 1 else ""
            request.user.save(update_fields=["first_name", "last_name"])

        method = form.cleaned_data["delivery_method"]
        subtotal, shipping, grand_total = _checkout_totals(cart_items, method)
        details = _delivery_details(form, request.user)

        order = Order.objects.create(
            user=request.user,
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

        payment_method = form.cleaned_data["payment_method"]

        if payment_method == Payment.Method.ESEWA:
            from orders.esewa import build_payment_form
            esewa_data = build_payment_form(order)

            Payment.objects.create(
                order=order,
                method=Payment.Method.ESEWA,
                status=Payment.Status.PENDING,
                amount=grand_total,
                transaction_uuid=esewa_data["transaction_uuid"],
                product_code=esewa_data["product_code"],
            )
            cart_items.delete()

            return render(request, "dev/esewa_redirect.html", {
                "esewa_url": settings.ESEWA_PAYMENT_URL,
                "esewa_data": esewa_data,
            })
        else:
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
        Order.objects.select_related("payment").prefetch_related("items"),
        pk=pk, user=request.user,
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


@login_required
def esewa_success(request):
    """eSewa redirects here after a successful payment."""
    encoded_data = request.GET.get("data")
    if not encoded_data:
        messages.error(request, "Invalid payment response.")
        return redirect("cart:cart_detail")

    from orders.esewa import decode_callback, verify_transaction

    callback = decode_callback(encoded_data)
    if not callback:
        messages.error(request, "Could not read payment response.")
        return redirect("cart:cart_detail")

    transaction_uuid = callback.get("transaction_uuid", "")
    total_amount = callback.get("total_amount", "")
    transaction_code = callback.get("transaction_code", "")
    product_code = settings.ESEWA_PRODUCT_CODE

    try:
        payment = Payment.objects.select_related("order").get(
            transaction_uuid=transaction_uuid,
            method=Payment.Method.ESEWA,
        )
    except Payment.DoesNotExist:
        messages.error(request, "Payment not found.")
        return redirect("cart:cart_detail")

    order = payment.order

    if payment.status != Payment.Status.PENDING:
        return redirect("orders:order_detail", pk=order.pk)

    verification = verify_transaction(product_code, total_amount, transaction_uuid)

    if verification and verification.get("status") == "COMPLETE":
        payment.status = Payment.Status.PAID
        payment.transaction_code = transaction_code
        payment.provider_status = verification.get("status", "")
        payment.paid_at = timezone.now()
        payment.save(update_fields=[
            "status", "transaction_code", "provider_status", "paid_at", "updated_at",
        ])
        messages.success(request, "Payment successful! Your order has been placed.")
        return redirect("orders:order_success", pk=order.pk)
    else:
        payment.status = Payment.Status.FAILED
        payment.provider_status = (verification or {}).get("status", "UNVERIFIED")
        payment.save(update_fields=["status", "provider_status", "updated_at"])
        order.change_status(
            Order.Status.CANCELLED,
            note="eSewa payment verification failed",
        )
        messages.error(request, "Payment could not be verified. Your order has been cancelled.")
        return redirect("orders:order_list")


@login_required
def esewa_failure(request):
    """eSewa redirects here when the customer cancels or payment fails."""
    encoded_data = request.GET.get("data")
    transaction_uuid = None

    if encoded_data:
        from orders.esewa import decode_callback
        callback = decode_callback(encoded_data)
        if callback:
            transaction_uuid = callback.get("transaction_uuid")

    if transaction_uuid:
        try:
            payment = Payment.objects.select_related("order").get(
                transaction_uuid=transaction_uuid,
                method=Payment.Method.ESEWA,
            )
            if payment.status == Payment.Status.PENDING:
                payment.status = Payment.Status.FAILED
                payment.save(update_fields=["status", "updated_at"])
                payment.order.change_status(
                    Order.Status.CANCELLED,
                    note="eSewa payment cancelled or failed",
                )
        except Payment.DoesNotExist:
            pass

    messages.info(request, "Payment was cancelled.")
    return redirect("cart:cart_detail")

