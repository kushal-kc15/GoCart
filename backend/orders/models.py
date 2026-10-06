from django.db import models, transaction
from django.db.models import F
from django.conf import settings
from django.utils import timezone
from accounts.models import Address
from products.models import Product
# Create your models here.
class Order(models.Model):
    # Delivery orders: Pending > Confirmed > Packed > Out for delivery > Delivered
    # Pickup orders:   Pending > Confirmed > Packed > Ready for pickup > Delivered ("Picked up")
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        PACKED = 'packed', 'Packed'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for delivery'
        READY_FOR_PICKUP = 'ready_for_pickup', 'Ready for pickup'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'

    class DeliveryMethod(models.TextChoices):
        DELIVERY = 'delivery', 'Delivery'
        PICKUP = 'pickup', 'Pickup'

    # PROTECT: a customer with orders can't be deleted (that would delete their
    # orders too). Staff deactivate the account instead.
    user=models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    shipping_address=models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True)
    delivery_method=models.CharField(max_length=20, choices=DeliveryMethod.choices, default=DeliveryMethod.DELIVERY)
    status=models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    subtotal=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_fee=models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total=models.DecimalField(max_digits=10, decimal_places=2)
    address=models.CharField(max_length=255)
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    class Meta:
        ordering=['-created_at']
        # Rupee sums (dashboard, order list line, customer "total spent") are only
        # for Managers and superusers, not for packers and riders.
        permissions = [('view_money_totals', 'Can see order money totals')]

    def __str__(self):
        return f'Order #{self.pk} - {self.user.email}'

    # The steps an order may take next. One step forward at a time, never back.
    # Packed is handled in allowed_next_statuses(), because its next step
    # depends on the delivery method.
    NEXT_STATUSES = {
        Status.PENDING: [Status.CONFIRMED, Status.CANCELLED],
        Status.CONFIRMED: [Status.PACKED, Status.CANCELLED],
        Status.OUT_FOR_DELIVERY: [Status.DELIVERED, Status.CANCELLED],
        Status.READY_FOR_PICKUP: [Status.DELIVERED, Status.CANCELLED],
        Status.DELIVERED: [],
        Status.CANCELLED: [],
    }

    @property
    def is_pickup(self):
        return self.delivery_method == Order.DeliveryMethod.PICKUP

    def allowed_next_statuses(self):
        if self.status == Order.Status.PACKED:
            if self.is_pickup:
                return [Order.Status.READY_FOR_PICKUP, Order.Status.CANCELLED]
            return [Order.Status.OUT_FOR_DELIVERY, Order.Status.CANCELLED]
        return Order.NEXT_STATUSES.get(self.status, [])

    @property
    def status_label(self):
        """The status as customers read it: a delivered pickup order shows as "Picked up"."""
        if self.status == Order.Status.DELIVERED and self.is_pickup:
            return 'Picked up'
        return self.get_status_display()

    def tracker_steps(self):
        """The steps for the customer's order tracker, marking which are done."""
        if self.is_pickup:
            path = [Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PACKED,
                    Order.Status.READY_FOR_PICKUP, Order.Status.DELIVERED]
        else:
            path = [Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PACKED,
                    Order.Status.OUT_FOR_DELIVERY, Order.Status.DELIVERED]
        # A cancelled order isn't on the path; the page hides the tracker for it.
        current = path.index(self.status) if self.status in path else 0

        steps = []
        for i, status in enumerate(path):
            label = status.label
            if status == Order.Status.DELIVERED and self.is_pickup:
                label = 'Picked up'
            steps.append({'label': label, 'done': i <= current, 'current': i == current})
        return steps

    def change_status(self, new_status, changed_by=None, note=''):
        """The only way to change an order's status. Returns True if it changed.

        Refuses a step that isn't allowed from the current status, and a cancel
        without a note. Cancelling puts the stock back and marks the payment failed.
        Every change is saved in the status history.
        """
        note = note.strip()
        if new_status not in self.allowed_next_statuses():
            return False
        if new_status == Order.Status.CANCELLED and not note:
            return False

        old_status = self.status
        now = timezone.now()
        with transaction.atomic():
            # Only matches if nobody changed the order since we loaded it, so two
            # clicks (or two staff) can never apply the same step twice.
            changed = Order.objects.filter(pk=self.pk, status=old_status).update(
                status=new_status, updated_at=now
            )
            if not changed:
                return False
            if new_status == Order.Status.CANCELLED:
                for item in self.items.all():
                    Product.objects.filter(pk=item.product_id).update(
                        stock=F('stock') + item.quantity
                    )
                Payment.objects.filter(order=self).update(status=Payment.Status.FAILED)
            OrderStatusChange.objects.create(
                order=self, from_status=old_status, to_status=new_status,
                changed_by=changed_by, note=note,
            )
        self.status = new_status
        self.updated_at = now
        return True


class OrderStatusChange(models.Model):
    """One row per status change, for the admin. Customers don't see it."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_changes')
    # Blank when the order was just placed.
    from_status = models.CharField(max_length=20, choices=Order.Status.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=Order.Status.choices)
    # PROTECT: staff who changed any order status can't be deleted (they are
    # deactivated instead), so the history always says who did what.
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='status_changes_made',
    )
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'Order #{self.order_id}: {self.from_status or "placed"} -> {self.to_status}'

class OrderItem(models.Model):
    order=models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product=models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name=models.CharField(max_length=200, blank=True)
    quantity=models.PositiveIntegerField(default=1)
    price=models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self):
        # The name saved at checkout, so renaming the product later doesn't change it.
        return f'{self.quantity} x {self.product_name or self.product.name} in Order #{self.order_id}'

    @property
    def line_total(self):
        """Price x quantity, using the price saved when the order was placed."""
        return self.price * self.quantity


class Payment(models.Model):
    class Method(models.TextChoices):
        COD = 'cod', 'Cash on Delivery'
        ESEWA = 'esewa', 'eSewa'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'

    order=models.OneToOneField(Order, on_delete=models.CASCADE, related_name='payment')
    method=models.CharField(max_length=20, choices=Method.choices)
    status=models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    amount=models.DecimalField(max_digits=10, decimal_places=2)
    transaction_uuid=models.CharField(max_length=100, blank=True, null=True)
    transaction_code=models.CharField(max_length=100, blank=True, null=True)
    product_code=models.CharField(max_length=50, blank=True, null=True)
    provider_status=models.CharField(max_length=50, blank=True, null=True)
    paid_at=models.DateTimeField(blank=True, null=True)
    # Who recorded the cash. PROTECT: a staff account that collected cash can't be
    # deleted (it is deactivated instead). Empty for payments made before this existed.
    collected_by=models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='collected_payments',
    )
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Payment for Order #{self.order.pk}'

    @property
    def collector_name(self):
        """Who recorded the cash, as shown in the admin and on the packing slip."""
        if self.collected_by is None:
            return 'Not recorded'
        return self.collected_by.get_full_name() or self.collected_by.email

    @property
    def can_collect_cash(self):
        return (
            self.method == Payment.Method.COD
            and self.status == Payment.Status.PENDING
            and self.order.status == Order.Status.DELIVERED
        )

    def mark_cash_collected(self, collected_by=None):
        """Record that the cash for a delivered COD order was received, and by whom.
        Returns False if it isn't allowed or was already recorded."""
        now = timezone.now()
        # Checked again in the database, so a second click can't record it twice.
        changed = Payment.objects.filter(
            pk=self.pk,
            method=Payment.Method.COD,
            status=Payment.Status.PENDING,
            order__status=Order.Status.DELIVERED,
        ).update(
            status=Payment.Status.PAID, paid_at=now, collected_by=collected_by, updated_at=now
        )
        if not changed:
            return False
        self.status = Payment.Status.PAID
        self.paid_at = now
        self.collected_by = collected_by
        return True
