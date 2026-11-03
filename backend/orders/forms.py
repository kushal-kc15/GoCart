from decimal import Decimal

from django import forms

from accounts.validators import normalize_nepali_phone
from .models import Order

# A box around Nepal. It also covers some border areas of India and China,
# which is fine for catching a pin dropped in the wrong country.
NEPAL_LATITUDE = (26.3, 30.5)
NEPAL_LONGITUDE = (80.0, 88.3)


def is_in_nepal(lat, lng):
    return (NEPAL_LATITUDE[0] <= lat <= NEPAL_LATITUDE[1]
            and NEPAL_LONGITUDE[0] <= lng <= NEPAL_LONGITUDE[1])


class CheckoutForm(forms.Form):
    delivery_method = forms.ChoiceField(
        choices=Order.DeliveryMethod.choices, initial=Order.DeliveryMethod.DELIVERY,
    )
    # The name on the order is the account's name. Only an account without one gets
    # this field (see __init__); the view saves it to the account.
    full_name = forms.CharField(
        max_length=150, label="Full name",
        widget=forms.TextInput(attrs={"autocomplete": "name", "placeholder": "e.g. Asha Sharma"}),
    )
    # Longer than the 10 stored digits, so "+977 981 234 5678" reaches clean_phone.
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            "placeholder": "98XXXXXXXX", "autocomplete": "tel", "inputmode": "tel",
        }),
    )
    address_line = forms.CharField(
        max_length=150, required=False, label="Street, tole, house number and city",
        widget=forms.TextInput(attrs={
            "placeholder": "e.g. Lakeside Road, Ward 6, Pokhara", "autocomplete": "street-address",
        }),
    )
    landmark = forms.CharField(
        max_length=150, required=False, label="Landmark or instructions (optional)",
        widget=forms.TextInput(attrs={"placeholder": "Near the blue gate, call on arrival"}),
    )
    # Filled in only by "Confirm this location" on the map.
    lat = forms.FloatField(required=False, widget=forms.HiddenInput)
    lng = forms.FloatField(required=False, widget=forms.HiddenInput)
    # Filled in by checkout.js from the map lookup; only used with a confirmed pin (see clean).
    city = forms.CharField(max_length=100, required=False, widget=forms.HiddenInput)
    # The area and town the map lookup found, e.g. "Pokhara". The order's address when a
    # confirmed pin comes with only a landmark.
    area = forms.CharField(max_length=150, required=False, widget=forms.HiddenInput)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None and user.get_full_name():
            del self.fields["full_name"]

    def _is_a_street(self, street, full_name):
        """False for an empty street, the customer's own name, or the "Pinned location (...)"
        text an older checkout page filled in when the map found no street."""
        street = street.strip().lower()
        names = [full_name]
        if self.user is not None:
            names.append(self.user.get_full_name())
        if street in [name.strip().lower() for name in names if name]:
            return False
        return bool(street) and not street.startswith("pinned location")

    def clean_phone(self):
        # Same Nepali mobile check as the profile; stores just the 10 digits.
        return normalize_nepali_phone(self.cleaned_data["phone"])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("delivery_method") != Order.DeliveryMethod.DELIVERY:
            return cleaned  # pickup: the address fields are ignored

        lat, lng = cleaned.get("lat"), cleaned.get("lng")
        street = cleaned.get("address_line")  # None if it already has an error (too long)
        if street is not None and not self._is_a_street(street, cleaned.get("full_name", "")):
            cleaned["address_line"] = ""  # never the name or "Pinned location (...)"
            if lat is None:
                self.add_error("address_line", "Enter your street, tole or house number.")
            elif not cleaned.get("landmark"):
                # "Pin on map" sends a confirmed pin. The pin says where; a street or a landmark
                # helps the rider find the door. The pin stays on the page.
                self.add_error("address_line", "Add your street or a landmark so the rider can find you")
                self.add_error("landmark", "Add your house number, landmark or delivery instructions so the rider can find you.")

        if (lat is None) != (lng is None):
            self.add_error(None, "The map location was incomplete. Please confirm it again.")
        elif lat is not None:
            if not is_in_nepal(lat, lng):
                self.add_error(None, "The map pin must be inside Nepal. Please move it and confirm again.")
            else:
                # 6 decimal places (about 10 cm), the size of the database fields.
                cleaned["lat"] = Decimal(f"{lat:.6f}")
                cleaned["lng"] = Decimal(f"{lng:.6f}")

        # The city and area come from the map lookup, so they only count with a confirmed pin.
        if lat is None:
            cleaned["city"] = ""
            cleaned["area"] = ""
        return cleaned
