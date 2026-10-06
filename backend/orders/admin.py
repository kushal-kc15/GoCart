from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Sum
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.formats import date_format
from unfold.admin import ModelAdmin, StackedInline, TabularInline
from unfold.contrib.filters.admin import ChoicesDropdownFilter, RangeDateFilter
from unfold.decorators import action, display
from unfold.utils import parse_date_str

from .models import Order, OrderItem, OrderStatusChange, Payment
# Register your models here.


# Badge colours (unfold label types) for the order list and order page.
STATUS_COLOURS = {
    Order.Status.PENDING: "warning",
    Order.Status.CONFIRMED: "info",
    Order.Status.PACKED: "info",
    Order.Status.OUT_FOR_DELIVERY: "primary",
    Order.Status.READY_FOR_PICKUP: "primary",
    Order.Status.DELIVERED: "success",
    Order.Status.CANCELLED: "danger",
}
PAYMENT_COLOURS = {
    Payment.Status.PENDING: "warning",
    Payment.Status.PAID: "success",
    Payment.Status.FAILED: "danger",
    Payment.Status.REFUNDED: "info",
}

# Text on the status panel buttons, by the status the button moves the order to.
BUTTON_LABELS = {
    Order.Status.CONFIRMED: "Confirm order",
    Order.Status.PACKED: "Mark as packed",
    Order.Status.OUT_FOR_DELIVERY: "Mark out for delivery",
    Order.Status.READY_FOR_PICKUP: "Mark ready for pickup",
    Order.Status.DELIVERED: "Mark as delivered",
}


class PlacedDateFilter(RangeDateFilter):
    """Unfold's date range filter, comparing only the date (in Nepal time).
    The original compares a datetime with a date, which leaves out orders
    placed during the "to" day."""

    def queryset(self, request, queryset):
        # parse_date_str gives None for a blank or badly typed date: that side is ignored.
        date_from = parse_date_str(self.used_parameters.get(f"{self.parameter_name}_from", ""))
        date_to = parse_date_str(self.used_parameters.get(f"{self.parameter_name}_to", ""))
        if date_from:
            queryset = queryset.filter(**{f"{self.parameter_name}__date__gte": date_from})
        if date_to:
            queryset = queryset.filter(**{f"{self.parameter_name}__date__lte": date_to})
        return queryset


class PaymentStatusFilter(admin.SimpleListFilter):
    title = "payment"
    parameter_name = "payment"

    def lookups(self, request, model_admin):
        return Payment.Status.choices

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(payment__status=self.value())
        return queryset


# The order page is read-only, so the inlines only show data.
class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ('item_name', 'quantity', 'price', 'line_total')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Product")
    def item_name(self, obj):
        # The name saved at checkout; older rows may not have one.
        return obj.product_name or obj.product.name


class PaymentInline(StackedInline):
    model = Payment
    extra = 0
    can_delete = False
    fields = ('method', 'status', 'amount', 'paid_at', 'cash_collected_by')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Cash collected by")
    def cash_collected_by(self, obj):
        # Plain text, not a link: staff accounts are for superusers to open.
        return obj.collector_name if obj.status == Payment.Status.PAID else "-"


class StatusHistoryInline(TabularInline):
    model = OrderStatusChange
    verbose_name_plural = "Status history"
    extra = 0
    can_delete = False
    fields = ('created_at', 'from_status', 'to_status', 'changed_by', 'note')
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = (
        'order_number', 'customer', 'phone', 'status_badge', 'delivery_method',
        'payment_badge', 'total', 'created_at',
    )
    list_display_links = ('order_number',)
    list_filter = (
        ('status', ChoicesDropdownFilter),
        ('created_at', PlacedDateFilter),
        'delivery_method',
        PaymentStatusFilter,
    )
    list_filter_submit = True  # the date range filter needs a submit button
    search_fields = (
        'user__first_name', 'user__last_name', 'user__email',
        'shipping_address__phone', 'address',
    )
    search_help_text = "Order number (#12 or 12), customer name, email or phone."
    ordering = ('-created_at',)
    list_select_related = ('user', 'shipping_address', 'payment')
    list_before_template = "admin/orders/order/changelist_totals.html"
    change_form_outer_before_template = "admin/orders/order/status_panel.html"

    fieldsets = (
        ("Customer", {"fields": ('customer', 'customer_email', 'phone')}),
        ("Delivery", {"fields": ('delivery_method', 'address')}),
        ("Order", {"fields": ('order_number', 'current_status', 'created_at', 'updated_at')}),
        ("Totals", {"fields": ('subtotal', 'shipping_fee', 'total')}),
    )
    readonly_fields = ('customer', 'customer_email', 'phone', 'order_number', 'current_status')
    inlines = [OrderItemInline, PaymentInline, StatusHistoryInline]

    # Cancel and Delivered are deliberately not bulk actions: they are done
    # one order at a time from the order page.
    actions = ['mark_confirmed', 'mark_packed', 'mark_out_for_delivery']
    # Button at the top of the order page.
    actions_detail = ['packing_slip']

    # ---- permissions ----
    # Orders only come from checkout and are never deleted (cancel instead).
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        # The order page itself is view-only: its status changes only through
        # the buttons in the status panel. The list keeps the normal check,
        # which the bulk actions use.
        if obj is not None:
            return False
        return super().has_change_permission(request)

    def _can_change_status(self, request):
        return request.user.has_perm("orders.change_order")

    # ---- columns and fields ----
    @admin.display(description="Order", ordering="id")
    def order_number(self, obj):
        return f"#{obj.pk}"

    @admin.display(description="Customer", ordering="user__first_name")
    def customer(self, obj):
        return obj.user.get_full_name() or obj.user.email

    @admin.display(description="Email")
    def customer_email(self, obj):
        return obj.user.email

    @admin.display(description="Phone")
    def phone(self, obj):
        return obj.shipping_address.phone if obj.shipping_address else "-"

    @display(description="Status", ordering="status", label=STATUS_COLOURS)
    def status_badge(self, obj):
        # (value, text): the value picks the colour; pickup orders show "Picked up".
        return obj.status, obj.status_label

    # Unfold only draws badges in the list, so the order page shows plain text
    # (the status panel above it has the badge).
    @admin.display(description="Status")
    def current_status(self, obj):
        return obj.status_label

    @display(description="Payment", label=PAYMENT_COLOURS)
    def payment_badge(self, obj):
        payment = getattr(obj, "payment", None)
        if payment is None:
            return "-"
        method = "COD" if payment.method == Payment.Method.COD else payment.get_method_display()
        return payment.status, f"{method} {payment.get_status_display().lower()}"

    # ---- search: "#12" finds order 12 only, "12" also finds it ----
    def get_search_results(self, request, queryset, search_term):
        search_term = search_term.strip()
        if search_term.startswith("#") and search_term[1:].isdigit():
            return queryset.filter(pk=search_term[1:]), False
        results, may_have_duplicates = super().get_search_results(request, queryset, search_term)
        if search_term.isdigit():
            results = results | queryset.filter(pk=search_term)
        return results, may_have_duplicates

    # ---- order list: totals line above the table ----
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        # Not a page (e.g. a redirect after a bulk action): nothing to add.
        if not hasattr(response, "context_data") or "cl" not in response.context_data:
            return response
        # Money sums are only for those allowed to see them: otherwise a date
        # filter would give packers and riders the same numbers as the dashboard.
        if not request.user.has_perm("orders.view_money_totals"):
            return response
        # Same filters and search as the table, without cancelled orders.
        queryset = response.context_data["cl"].queryset
        totals = queryset.exclude(status=Order.Status.CANCELLED).aggregate(
            count=Count("id"), amount=Sum("total")
        )
        response.context_data["order_totals"] = {
            "count": totals["count"],
            "amount": totals["amount"] or 0,
        }
        return response

    # ---- order page: status panel ----
    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        order = Order.objects.filter(pk=object_id).select_related("payment__collected_by").first()
        if order is not None:
            next_steps = []
            for status in order.allowed_next_statuses():
                if status == Order.Status.CANCELLED:
                    continue  # cancel has its own button and note
                label = BUTTON_LABELS[status]
                if status == Order.Status.DELIVERED and order.is_pickup:
                    label = "Mark as picked up"
                next_steps.append({"status": status, "label": label})
            payment = getattr(order, "payment", None)
            extra_context.update({
                "original_status_colour": STATUS_COLOURS.get(order.status),
                "can_change_status": self._can_change_status(request),
                "next_steps": next_steps,
                "can_cancel": Order.Status.CANCELLED in order.allowed_next_statuses(),
                "can_collect_cash": payment is not None and payment.can_collect_cash,
                "cash_receipt": self._cash_receipt(payment),
            })
        return super().change_view(request, object_id, form_url, extra_context)

    def _cash_receipt(self, payment):
        """"Cash collected by X on 5 Oct 2026, 2:06 PM", or "" until the cash is recorded."""
        if payment is None or payment.status != Payment.Status.PAID or payment.paid_at is None:
            return ""
        when = date_format(timezone.localtime(payment.paid_at), "j M Y, g:i A")
        if payment.collected_by is None:
            return f"Cash collected on {when} (who collected it was not recorded)"
        return f"Cash collected by {payment.collector_name} on {when}"

    def get_urls(self):
        custom_urls = [
            path(
                "<int:pk>/status/",
                self.admin_site.admin_view(self.change_status_view),
                name="orders_order_status",
            ),
            path(
                "<int:pk>/cash-collected/",
                self.admin_site.admin_view(self.cash_collected_view),
                name="orders_order_cash_collected",
            ),
        ]
        # Ours first, so they match before the admin's catch-all order URLs.
        return custom_urls + super().get_urls()

    def change_status_view(self, request, pk):
        """POST from the status panel: move the order one step, or cancel it."""
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self._can_change_status(request):
            raise PermissionDenied
        order = get_object_or_404(Order, pk=pk)
        new_status = request.POST.get("status", "")
        note = request.POST.get("note", "").strip()

        if new_status == Order.Status.CANCELLED and not note:
            messages.error(request, "Please write why the order is cancelled. Nothing was changed.")
        elif order.change_status(new_status, changed_by=request.user, note=note):
            messages.success(request, f"Order #{order.pk} is now {order.status_label.lower()}.")
        else:
            messages.error(
                request,
                "That change isn't allowed from the order's current status "
                "(it may have just been changed by someone else). Nothing was changed.",
            )
        return redirect(reverse("admin:orders_order_change", args=[order.pk]))

    def cash_collected_view(self, request, pk):
        """POST from the status panel: the cash for a delivered COD order was received."""
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self._can_change_status(request):
            raise PermissionDenied
        order = get_object_or_404(Order, pk=pk)
        payment = getattr(order, "payment", None)
        if payment is not None and payment.mark_cash_collected(collected_by=request.user):
            messages.success(request, f"Cash collected for order #{order.pk}.")
        else:
            messages.error(
                request, "Cash can only be recorded once, for a delivered cash-on-delivery order."
            )
        return redirect(reverse("admin:orders_order_change", args=[order.pk]))

    # ---- packing slip ----
    @action(
        description="Print packing slip",
        url_path="slip",
        permissions=["view"],
        icon="print",
        attrs={"target": "_blank"},  # opens in a new tab
    )
    def packing_slip(self, request, object_id):
        """A printable page to pack the order with and hand over on delivery."""
        order = get_object_or_404(
            Order.objects.select_related("user", "payment__collected_by").prefetch_related("items__product"),
            pk=object_id,
        )
        return render(request, "admin/orders/order/packing_slip.html", {
            "order": order,
            "payment": getattr(order, "payment", None),
            "shop": settings.SHOP_INFO,
        })

    # ---- bulk actions ----
    def _change_selected(self, request, queryset, new_status):
        """Move each selected order one step on, skipping those that can't take that step."""
        changed = 0
        skipped = 0
        for order in queryset:
            if order.change_status(new_status, changed_by=request.user):
                changed += 1
            else:
                skipped += 1
        label = Order.Status(new_status).label.lower()
        message = f"{changed} order(s) marked as {label}."
        if skipped:
            message += f" {skipped} skipped (not allowed from their current status)."
        self.message_user(request, message)

    @admin.action(description="Mark selected orders as confirmed", permissions=["change"])
    def mark_confirmed(self, request, queryset):
        self._change_selected(request, queryset, Order.Status.CONFIRMED)

    @admin.action(description="Mark selected orders as packed", permissions=["change"])
    def mark_packed(self, request, queryset):
        self._change_selected(request, queryset, Order.Status.PACKED)

    @admin.action(description="Mark selected orders as out for delivery", permissions=["change"])
    def mark_out_for_delivery(self, request, queryset):
        # Pickup orders are skipped: their next step is "Ready for pickup".
        self._change_selected(request, queryset, Order.Status.OUT_FOR_DELIVERY)
