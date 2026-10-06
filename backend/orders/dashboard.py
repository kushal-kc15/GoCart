"""The admin home page: what needs doing now.

Unfold calls dashboard_callback (see UNFOLD["DASHBOARD_CALLBACK"] in settings)
before showing admin/dashboard.html. All times are Nepal time (settings.TIME_ZONE).
"""
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.urls import reverse
from django.utils import timezone

from products.models import LOW_STOCK_LIMIT, Product
from .admin import STATUS_COLOURS
from .models import Order, Payment

LOW_STOCK_SHOWN = 15
LATEST_ORDERS_SHOWN = 10


def day_and_week_start():
    """Midnight today and midnight last Sunday (the week starts on Sunday), Nepal time."""
    today_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    # weekday(): Monday is 0 ... Sunday is 6, so this counts the days back to Sunday.
    week_start = today_start - timedelta(days=(today_start.weekday() + 1) % 7)
    return today_start, week_start


def dashboard_callback(request, context):
    today_start, week_start = day_and_week_start()
    orders_url = reverse("admin:orders_order_changelist")

    if request.user.has_perm("orders.view_order"):
        cash_due = Q(
            status=Order.Status.DELIVERED,
            payment__method=Payment.Method.COD,
            payment__status=Payment.Status.PENDING,
        )
        # Rupee totals for today and this week are only for Managers and superusers.
        # For anyone else they are not even worked out.
        show_totals = request.user.has_perm("orders.view_money_totals")

        # Query 1: every order number on the page.
        wanted = {
            "pending": Count("id", filter=Q(status=Order.Status.PENDING)),
            "confirmed": Count("id", filter=Q(status=Order.Status.CONFIRMED)),
            "packed": Count("id", filter=Q(status=Order.Status.PACKED)),
            "out_for_delivery": Count("id", filter=Q(status=Order.Status.OUT_FOR_DELIVERY)),
            "ready_for_pickup": Count("id", filter=Q(status=Order.Status.READY_FOR_PICKUP)),
            "cash_due_count": Count("id", filter=cash_due),
            "cash_due_total": Sum("total", filter=cash_due),
        }
        if show_totals:
            not_cancelled = ~Q(status=Order.Status.CANCELLED)
            today = not_cancelled & Q(created_at__gte=today_start)
            week = not_cancelled & Q(created_at__gte=week_start)
            wanted.update(
                today_count=Count("id", filter=today),
                today_total=Sum("total", filter=today),
                week_count=Count("id", filter=week),
                week_total=Sum("total", filter=week),
            )
        numbers = Order.objects.aggregate(**wanted)

        # Each card links to the order list with the matching filter.
        context["action_cards"] = [
            {"title": "Pending", "hint": "To confirm", "count": numbers["pending"],
             "url": f"{orders_url}?status__exact=pending"},
            {"title": "Confirmed", "hint": "To pack", "count": numbers["confirmed"],
             "url": f"{orders_url}?status__exact=confirmed"},
            {"title": "Packed", "hint": "Waiting for rider or pickup", "count": numbers["packed"],
             "url": f"{orders_url}?status__exact=packed"},
            {"title": "Out for delivery", "hint": "With the rider", "count": numbers["out_for_delivery"],
             "url": f"{orders_url}?status__exact=out_for_delivery"},
            {"title": "Ready for pickup", "hint": "Waiting for the customer",
             "count": numbers["ready_for_pickup"],
             "url": f"{orders_url}?status__exact=ready_for_pickup"},
            {"title": "Delivered, cash not collected", "hint": "Cash on delivery still to record",
             "count": numbers["cash_due_count"], "amount": numbers["cash_due_total"] or 0,
             "url": f"{orders_url}?status__exact=delivered&payment=pending"},
        ]
        if show_totals:
            # Query 2: cash received today.
            cash_today = Payment.objects.filter(
                method=Payment.Method.COD,
                status=Payment.Status.PAID,
                paid_at__gte=today_start,
            ).aggregate(count=Count("id"), total=Sum("amount"))
            # The order list's date filter and totals line match these cards
            # (cancelled orders are left out of both).
            context["order_cards"] = [
                {"title": "Orders today", "hint": "Placed today, cancelled not counted",
                 "count": numbers["today_count"], "amount": numbers["today_total"] or 0,
                 "url": f"{orders_url}?created_at_from={today_start.date()}&created_at_to={today_start.date()}"},
                {"title": "Orders this week", "hint": "Placed since Sunday, cancelled not counted",
                 "count": numbers["week_count"], "amount": numbers["week_total"] or 0,
                 "url": f"{orders_url}?created_at_from={week_start.date()}"},
                {"title": "Cash collected today", "hint": "Cash on delivery recorded as paid today",
                 "count": cash_today["count"], "amount": cash_today["total"] or 0},
            ]

        # Query 3: the latest orders, with the badge colour for each.
        latest = Order.objects.select_related("user").order_by("-created_at")[:LATEST_ORDERS_SHOWN]
        context["latest_orders"] = [
            {"order": order, "colour": STATUS_COLOURS.get(order.status)} for order in latest
        ]

    if request.user.has_perm("products.view_product"):
        # Query 4: low stock, out of stock first.
        context["low_stock"] = list(
            Product.objects.filter(is_available=True, stock__lt=LOW_STOCK_LIMIT)
            .order_by("stock", "name")[:LOW_STOCK_SHOWN]
        )
        products_url = reverse("admin:products_product_changelist")
        context["low_stock_hint"] = (
            f"Available products with stock under {LOW_STOCK_LIMIT}, out of stock first"
        )
        context["out_of_stock_url"] = f"{products_url}?is_available__exact=1&stock_status=out"
        context["low_stock_url"] = f"{products_url}?is_available__exact=1&stock_status=low"

    return context
