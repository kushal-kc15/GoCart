from django.db import models
from django.conf import settings
from accounts.models import Address
from products.models import Product
# Create your models here.
class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PROCESSING = 'processing', 'Processing'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    class DeliveryMethod(models.TextChoices):
        DELIVERY = 'delivery', 'Delivery'
        PICKUP = 'pickup', 'Pickup'

    user=models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='orders')
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

    def __str__(self):
        return f'Order #{self.pk} - {self.user.email}'  

class OrderItem(models.Model):
    order=models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product=models.ForeignKey(Product, on_delete=models.PROTECT)
    product_name=models.CharField(max_length=200, blank=True)
    quantity=models.PositiveIntegerField(default=1)
    price=models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self):
        return f'{self.quantity} x {self.product.name} in Order #{self.order.pk}'


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
    created_at=models.DateTimeField(auto_now_add=True)
    updated_at=models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Payment for Order #{self.order.pk}'
