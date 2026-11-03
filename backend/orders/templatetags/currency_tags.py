from django import template
from config.currency import format_nepali

register = template.Library()


@register.filter(name="nepali_comma")
def nepali_comma(value, decimals=None):
    """
    Format a number with commas in South Asian / Nepali style (e.g. 6,000 or 6,00,000).
    Usage:
        {{ order.total|nepali_comma }}
        {{ order.total|nepali_comma:"-2" }}
        {{ order.total|nepali_comma:2 }}
    """
    if decimals is not None and decimals != "-2":
        try:
            decimals = int(decimals)
        except (ValueError, TypeError):
            pass
    return format_nepali(value, decimals)


@register.filter(name="rupees")
def rupees(value, decimals="-2"):
    """
    Format a number with Rs. prefix and South Asian / Nepali commas (e.g. Rs. 6,000 or Rs. 6,00,000).
    Usage:
        {{ order.total|rupees }}
        {{ order.total|rupees:2 }}
    """
    formatted = nepali_comma(value, decimals)
    if not formatted:
        return ""
    return f"Rs. {formatted}"
