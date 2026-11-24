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
