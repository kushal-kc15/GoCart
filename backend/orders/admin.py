from django.contrib import admin
from unfold.admin import ModelAdmin, StackedInline, TabularInline

from .models import Order, OrderItem, Payment
# Register your models here.


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ('product', 'product_name', 'quantity', 'price')

    def has_add_permission(self, request, obj=None):
        return False


class PaymentInline(StackedInline):
    model = Payment
    extra = 0
    can_delete = False
    readonly_fields = (
        'method', 'status', 'amount', 'transaction_uuid', 'transaction_code',
        'product_code', 'provider_status', 'paid_at', 'created_at', 'updated_at',
    )

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ('id', 'customer_email', 'status', 'delivery_method', 'total', 'created_at')
    list_filter = ('status', 'delivery_method', 'created_at')
    search_fields = ('id', 'user__email', 'address')
    ordering = ('-created_at',)
    list_select_related = ('user',)
    inlines = [OrderItemInline, PaymentInline]
    actions = ['mark_confirmed', 'mark_out_for_delivery', 'mark_delivered', 'mark_cancelled']

    @admin.display(description="Customer", ordering="user__email")
    def customer_email(self, obj):
        return obj.user.email

    @admin.action(description="Mark selected orders as confirmed")
    def mark_confirmed(self, request, queryset):
        updated = queryset.update(status=Order.Status.CONFIRMED)
        self.message_user(request, f"{updated} order(s) marked as confirmed.")

    @admin.action(description="Mark selected orders as out for delivery")
    def mark_out_for_delivery(self, request, queryset):
        updated = queryset.update(status=Order.Status.OUT_FOR_DELIVERY)
        self.message_user(request, f"{updated} order(s) marked as out for delivery.")

    @admin.action(description="Mark selected orders as delivered")
    def mark_delivered(self, request, queryset):
        updated = queryset.update(status=Order.Status.DELIVERED)
        self.message_user(request, f"{updated} order(s) marked as delivered.")

    @admin.action(description="Mark selected orders as cancelled (restores stock)")
    def mark_cancelled(self, request, queryset):
        # Order.cancel() skips orders already cancelled, so stock is never restored twice.
        count = 0
        for order in queryset:
            if order.cancel():
                count += 1
        self.message_user(request, f"{count} order(s) cancelled and stock restored.")


@admin.register(OrderItem)
class OrderItemAdmin(ModelAdmin):
    list_display = ('id', 'order', 'product', 'quantity', 'price')
    list_filter = ('order', 'product')
    search_fields = ('order__id', 'product__name')
    ordering = ('-order__created_at',)
