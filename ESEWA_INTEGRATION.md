# eSewa Payment Integration — Step by Step

This guide walks through adding eSewa online payment to GoCart's checkout,
one step at a time. Each step is small enough to test before moving on.

## How eSewa works (overview)

```
Customer clicks "Pay with eSewa"
        |
        v
Our server creates a signed payment form (HMAC-SHA256)
        |
        v
Customer is redirected to eSewa's payment page
        |
        v
Customer pays on eSewa
        |
        v
eSewa redirects back to our success/failure URL with a Base64 response
        |
        v
Our server decodes the response, calls eSewa's verification API
        |
        v
If verified: mark Payment as PAID, confirm the order
If failed: mark Payment as FAILED, restore stock
```

## What we already have

- `Payment` model with `method` choices: COD and ESEWA
- `Payment` model with eSewa fields: `transaction_uuid`, `transaction_code`,
  `product_code`, `provider_status`
- `Payment.Status` choices: PENDING, PAID, FAILED, REFUNDED
- Checkout creates an `Order` + `Payment(method=COD)` inside a transaction
- `Order.change_status()` handles stock restoration on cancel

## eSewa test credentials

```
Merchant Code (product_code): EPAYTEST
Secret Key: 8gBm/:&EnhH.1/q
Test payment URL: https://rc-epay.esewa.com.np/api/epay/main/v2/form
Test verification URL: https://uat.esewa.com.np/api/epay/transaction/status/
Test eSewa login: 9806800001 / Nepal@123 (or 9806800002, 9806800003, 9806800004)
```

---

## Step 1: Add eSewa settings

**File:** `backend/config/settings.py`

Add at the bottom of the file:

```python
# eSewa payment gateway (test environment).
# Switch to production URLs and a real merchant code before going live.
ESEWA_SECRET_KEY = os.environ.get("ESEWA_SECRET_KEY", "8gBm/:&EnhH.1/q")
ESEWA_PRODUCT_CODE = os.environ.get("ESEWA_PRODUCT_CODE", "EPAYTEST")
ESEWA_PAYMENT_URL = "https://rc-epay.esewa.com.np/api/epay/main/v2/form"
ESEWA_VERIFICATION_URL = "https://uat.esewa.com.np/api/epay/transaction/status/"
```

**File:** `backend/.env.example`

Add:

```
# eSewa payment gateway. Leave defaults for the test environment.
ESEWA_SECRET_KEY=8gBm/:&EnhH.1/q
ESEWA_PRODUCT_CODE=EPAYTEST
```

**Test:** Run `python manage.py shell` and check `from django.conf import settings; print(settings.ESEWA_PRODUCT_CODE)` prints `EPAYTEST`.

---

## Step 2: Create the eSewa helper module

**File:** `backend/orders/esewa.py` (new file)

This module handles:
1. Generating the HMAC-SHA256 signature
2. Building the payment form data
3. Decoding eSewa's Base64 callback response
4. Calling eSewa's verification API

```python
import base64
import hashlib
import hmac
import json
import uuid
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def generate_signature(message):
    """HMAC-SHA256 signature using the eSewa secret key."""
    key = settings.ESEWA_SECRET_KEY.encode("utf-8")
    msg = message.encode("utf-8")
    signature = hmac.new(key, msg, hashlib.sha256).digest()
    return base64.b64encode(signature).decode("utf-8")


def build_payment_form(order):
    """
    Return a dict of form fields to POST to eSewa's payment page.
    The order must already exist with a Payment row.
    """
    transaction_uuid = f"GOCART-{order.pk}-{uuid.uuid4().hex[:8]}"
    amount = str(order.total)
    product_code = settings.ESEWA_PRODUCT_CODE

    # The signature signs: total_amount,transaction_uuid,product_code
    message = f"total_amount={amount},transaction_uuid={transaction_uuid},product_code={product_code}"
    signature = generate_signature(message)

    return {
        "amount": amount,
        "tax_amount": "0",
        "total_amount": amount,
        "transaction_uuid": transaction_uuid,
        "product_code": product_code,
        "product_service_charge": "0",
        "product_delivery_charge": "0",
        "signed_field_names": "total_amount,transaction_uuid,product_code",
        "signature": signature,
    }


def decode_callback(encoded_data):
    """Decode the Base64 JSON response eSewa sends back."""
    try:
        decoded = base64.b64decode(encoded_data)
        return json.loads(decoded)
    except Exception:
        logger.exception("Failed to decode eSewa callback data")
        return None


def verify_transaction(product_code, total_amount, transaction_uuid):
    """
    Call eSewa's server to verify the payment is real.
    Returns the response dict or None on failure.
    """
    try:
        response = requests.get(
            settings.ESEWA_VERIFICATION_URL,
            params={
                "product_code": product_code,
                "total_amount": total_amount,
                "transaction_uuid": transaction_uuid,
            },
            timeout=15,
        )
        response.raise_for_status()
        return response.json()
    except Exception:
        logger.exception("eSewa verification request failed")
        return None
```

**Test:** `python manage.py shell`, then:
```python
from orders.esewa import generate_signature
print(generate_signature("total_amount=100,transaction_uuid=test123,product_code=EPAYTEST"))
# Should print a Base64 string without errors
```

---

## Step 3: Add payment method to the checkout form

**File:** `backend/orders/forms.py`

Add a `payment_method` field to `CheckoutForm`:

```python
payment_method = forms.ChoiceField(
    choices=Payment.Method.choices,
    initial=Payment.Method.COD,
    widget=forms.RadioSelect,
)
```

You will need to import Payment at the top:

```python
from .models import Order, Payment
```

---

## Step 4: Update the checkout view

**File:** `backend/orders/views.py`

The current checkout always creates a COD payment. We need to:

1. Read `payment_method` from the form
2. If COD: same as now
3. If eSewa: create a PENDING payment with the transaction UUID, then
   redirect the customer to eSewa's payment page instead of order_success

Changes to `CheckoutView.post()`:

After creating the order and order items (line ~213), replace the Payment
creation and redirect block with:

```python
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
```

Also add success/failure URLs to the eSewa form data. In `esewa.py`'s
`build_payment_form`, we need to pass them. We will handle this in Step 5.

---

## Step 5: Create the eSewa redirect template

**File:** `frontend/templates/dev/esewa_redirect.html` (new file)

This is a simple page with a hidden form that auto-submits to eSewa:

```html
<!DOCTYPE html>
<html>
<head><title>Redirecting to eSewa...</title></head>
<body>
  <p>Redirecting to eSewa for payment...</p>
  <form id="esewa-form" method="POST" action="{{ esewa_url }}">
    {% for key, value in esewa_data.items %}
      <input type="hidden" name="{{ key }}" value="{{ value }}">
    {% endfor %}
    <input type="hidden" name="success_url" value="{{ request.scheme }}://{{ request.get_host }}{% url 'orders:esewa_success' %}">
    <input type="hidden" name="failure_url" value="{{ request.scheme }}://{{ request.get_host }}{% url 'orders:esewa_failure' %}">
  </form>
  <script>document.getElementById("esewa-form").submit();</script>
</body>
</html>
```

---

## Step 6: Add the callback views

**File:** `backend/orders/views.py`

Add two new views that eSewa redirects back to:

```python
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
    status = callback.get("status", "")
    product_code = settings.ESEWA_PRODUCT_CODE

    # Find the payment by transaction_uuid
    try:
        payment = Payment.objects.select_related("order").get(
            transaction_uuid=transaction_uuid,
            method=Payment.Method.ESEWA,
        )
    except Payment.DoesNotExist:
        messages.error(request, "Payment not found.")
        return redirect("cart:cart_detail")

    order = payment.order

    # Only process if still pending
    if payment.status != Payment.Status.PENDING:
        return redirect("orders:order_detail", pk=order.pk)

    # Verify with eSewa's server
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
        # Verification failed — cancel the order and restore stock
        payment.status = Payment.Status.FAILED
        payment.provider_status = (verification or {}).get("status", "UNVERIFIED")
        payment.save(update_fields=["status", "provider_status", "updated_at"])
        order.change_status(
            Order.Status.CANCELLED,
            note="eSewa payment verification failed",
        )
        messages.error(request, "Payment could not be verified. Your order has been cancelled.")
        return redirect("orders:order_list")


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
```

---

## Step 7: Add the callback URLs

**File:** `backend/orders/urls.py`

Add two new paths:

```python
path("esewa/success/", views.esewa_success, name="esewa_success"),
path("esewa/failure/", views.esewa_failure, name="esewa_failure"),
```

---

## Step 8: Update the checkout template

**File:** `frontend/templates/dev/checkoutpage.html`

Add payment method radio buttons. Find the line:
```html
<p class="hint pay-note">Pay in cash on delivery, or at the store when you pick up.</p>
```

Replace it with:
```html
<div class="svc-label">Payment method</div>
<label class="opt">
  <input type="radio" name="payment_method" value="cod" checked>
  Cash on Delivery
</label>
<label class="opt">
  <input type="radio" name="payment_method" value="esewa">
  Pay with eSewa
</label>
```

---

## Step 9: Install requests

**File:** `backend/requirements.txt`

Add:
```
requests
```

Then run: `pip install requests`

---

## Step 10: Test the full flow

1. Run `python manage.py runserver`
2. Add items to cart, go to checkout
3. Select "Pay with eSewa" and place order
4. You should be redirected to eSewa's test payment page
5. Log in with test credentials: `9806800001` / `Nepal@123`
6. Complete the payment
7. You should be redirected back and see "Payment successful!"
8. Check the order detail — payment status should be PAID

Test the failure path too:
1. Start a payment, then cancel on eSewa's page
2. Check that the order is cancelled and stock is restored

---

## Implementation order

Do these one at a time, test each step before moving to the next:

- [ ] Step 1: Settings
- [ ] Step 2: esewa.py helper module
- [ ] Step 3: Payment method in checkout form
- [ ] Step 4: Update checkout view
- [ ] Step 5: eSewa redirect template
- [ ] Step 6: Callback views
- [ ] Step 7: Callback URLs
- [ ] Step 8: Update checkout template
- [ ] Step 9: Install requests
- [ ] Step 10: Full test

---

## Notes

- The `@transaction.atomic` on `CheckoutView.post` means the order and
  payment are created together. If the eSewa redirect fails, everything
  rolls back.
- Stock is taken at checkout (before payment), so the item is reserved.
  If payment fails, `change_status(CANCELLED)` restores stock.
- The eSewa callback views do NOT need `@login_required` because eSewa
  redirects the user's browser — they are already logged in from checkout.
  But we look up the payment by `transaction_uuid`, not by user, to be safe.
- In production, switch `ESEWA_PAYMENT_URL` and `ESEWA_VERIFICATION_URL`
  to the live endpoints and use a real merchant code.
