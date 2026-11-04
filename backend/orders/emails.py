import logging
import smtplib

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from .models import Order

logger = logging.getLogger(__name__)

# Tracker: four steps shown in every order email, newest completed step gets the ring.
_TRACKER_STEPS = [
    (Order.Status.CONFIRMED, "Confirmed"),
    (Order.Status.PACKED, "Packed"),
    (Order.Status.OUT_FOR_DELIVERY, "On the way"),
    (Order.Status.DELIVERED, "Delivered"),
]


def _tracker(steps_done):
    """Return a list of step dicts for the email tracker. steps_done is 1-4."""
    return [
        {
            "label": label,
            "done": i < steps_done,
            "current": i == steps_done - 1,
        }
        for i, (_, label) in enumerate(_TRACKER_STEPS)
    ]


def _order_url(order):
    return f"http://{settings.SITE_DOMAIN}{reverse('orders:order_detail', args=[order.pk])}"


def _base_context(order):
    items = order.items.select_related("product").all()
    return {
        "order": order,
        "items": items,
        "shop_name": settings.SHOP_INFO["name"],
        "shop_phone": settings.SHOP_INFO["phone"],
        "order_date": date_format(timezone.localtime(order.created_at), "j F Y"),
        "order_url": _order_url(order),
    }


def _send(subject, to_email, template, context):
    html = render_to_string(template, context)
    msg = EmailMultiAlternatives(subject, "", None, [to_email])
    msg.attach_alternative(html, "text/html")
    try:
        msg.send()
    except (smtplib.SMTPException, OSError):
        logger.exception("Couldn't send '%s' to %s", subject, to_email)


def send_welcome_email(user):
    context = {
        "user": user,
        "shop_name": settings.SHOP_INFO["name"],
        "shop_phone": settings.SHOP_INFO["phone"],
        "site_domain": settings.SITE_DOMAIN,
    }
    _send(
        f"Welcome to {settings.SHOP_INFO['name']}!",
        user.email,
        "dev/email/welcome.html",
        context,
    )


def send_order_confirmed_email(order):
    ctx = _base_context(order)
    ctx["tracker_steps"] = _tracker(1)
    _send(
        f"Your GoCart order #{order.pk} is confirmed",
        order.user.email,
        "dev/email/order_confirmed.html",
        ctx,
    )


_STATUS_EMAIL = {
    Order.Status.PACKED: (
        "dev/email/order_status.html",
        "Order #{pk} is packed and ready to go",
    ),
    Order.Status.OUT_FOR_DELIVERY: (
        "dev/email/order_out_for_delivery.html",
        "Order #{pk} is on the way",
    ),
    Order.Status.DELIVERED: (
        "dev/email/order_delivered.html",
        "Order #{pk} has been delivered",
    ),
}

_STEPS_FOR_STATUS = {
    Order.Status.PACKED: 2,
    Order.Status.OUT_FOR_DELIVERY: 3,
    Order.Status.DELIVERED: 4,
}


def send_order_status_email(order):
    entry = _STATUS_EMAIL.get(order.status)
    if not entry:
        return
    template, subject_tpl = entry
    ctx = _base_context(order)
    ctx["tracker_steps"] = _tracker(_STEPS_FOR_STATUS[order.status])
    ctx["status_history"] = order.status_changes.order_by("-created_at")
    _send(subject_tpl.format(pk=order.pk), order.user.email, template, ctx)
