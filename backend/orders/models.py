from django.db import models, transaction
from django.db.models import F
from django.conf import settings
from django.utils import timezone
from accounts.models import Address
from products.models import Product


class Order(models.Model):
    # Pickup orders go Packed > Ready for pickup instead of Out for delivery.
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

    # PROTECT: an account with orders is deactivated, not deleted.
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
        # Rupee totals are hidden from Order staff.
        permissions = [('view_money_totals', 'Can see order money totals')]

    def __str__(self):
        return f'Order #{self.pk} - {self.user.email}'

    # Packed is left out: its next step depends on the delivery method.
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
        if self.status == Order.Status.DELIVERED and self.is_pickup:
            return 'Picked up'
        return self.get_status_display()

    def tracker_steps(self):
        middle = Order.Status.READY_FOR_PICKUP if self.is_pickup else Order.Status.OUT_FOR_DELIVERY
        path = [Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PACKED,
                middle, Order.Status.DELIVERED]
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
        """The only way to change an order's status. Returns True if it changed."""
        note = note.strip()
        if new_status not in self.allowed_next_statuses():
            return False
        if new_status == Order.Status.CANCELLED and not note:
            return False

        old_status = self.status
        now = timezone.now()
        with transaction.atomic():
            # Matches only if the status is unchanged, so a step (and stock restore) can't apply twice.
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
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_changes')
    # Blank for the "Order placed" row.
    from_status = models.CharField(max_length=20, choices=Order.Status.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=Order.Status.choices)
    # PROTECT: keeps who made each change.
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
        # The name saved at checkout, so a later rename doesn't change it.
        return f'{self.quantity} x {self.product_name or self.product.name} in Order #{self.order_id}'

    @property
    def line_total(self):
        """Uses the price saved at checkout."""
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
    # PROTECT: a staff account that collected cash is deactivated, not deleted.
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
        """Record the cash for a delivered COD order. Returns False if not allowed or already done."""
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
