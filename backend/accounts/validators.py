import re

from django.core.exceptions import ValidationError

PHONE_ERROR = "Enter a 10-digit mobile number starting with 97 or 98."


def normalize_nepali_phone(value):
    """Return a Nepali mobile number as 10 digits, or raise ValidationError."""
    number = "".join(str(value).split())  # drop all spaces
    if number.startswith("+977"):
        number = number[4:]
    elif number.startswith("977") and len(number) == 13:
        # Only strip a bare 977 when 10 digits follow, so 9771234567 is left alone.
        number = number[3:]

    # [0-9], not \d: \d also accepts Devanagari digits.
    if not re.fullmatch(r"9[78][0-9]{8}", number):
        raise ValidationError(PHONE_ERROR)
    return number
