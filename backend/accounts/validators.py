import re

from django.core.exceptions import ValidationError

PHONE_ERROR = "Enter a 10-digit mobile number starting with 97 or 98."


def normalize_nepali_phone(value):
    """Return a Nepali mobile number as its 10 digits, e.g. "9812345678".

    Spaces are ignored and a +977 or 977 country code is removed, so
    "+977 981 234 5678" and "9779812345678" both become "9812345678".
    Raises ValidationError if what is left is not 97/98 + 8 digits.
    Used by the profile form and the checkout address form.
    """
    number = "".join(str(value).split())  # drop all spaces
    if number.startswith("+977"):
        number = number[4:]
    elif number.startswith("977") and len(number) == 13:
        # Only strip a bare 977 when a full 10-digit number follows,
        # so a real number like 9771234567 is left alone.
        number = number[3:]

    # [0-9], not \d: \d would also accept other scripts' digits (e.g. Devanagari).
    if not re.fullmatch(r"9[78][0-9]{8}", number):
        raise ValidationError(PHONE_ERROR)
    return number
