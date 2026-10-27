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
    # A saved address of this user, or empty for a new address.
    address_id = forms.IntegerField(required=False)
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
    save_address = forms.BooleanField(required=False, initial=True, label="Save this address for next time")

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None and user.get_full_name():
            del self.fields["full_name"]

    def clean_phone(self):
        # Same Nepali mobile check as the profile; stores just the 10 digits.
        return normalize_nepali_phone(self.cleaned_data["phone"])

    def clean(self):
        cleaned = super().clean()
        cleaned["saved_address"] = None
        if cleaned.get("delivery_method") != Order.DeliveryMethod.DELIVERY:
            return cleaned  # pickup: the address fields are ignored

        address_id = cleaned.get("address_id")
        if address_id:
            # Only this user's own addresses.
            address = self.user.addresses.filter(pk=address_id).first()
            if address is None:
                self.add_error("address_id", "Choose one of your saved addresses.")
            cleaned["saved_address"] = address
            return cleaned

        if not cleaned.get("address_line"):
            self.add_error("address_line", "Enter your street, tole or house number.")

        lat, lng = cleaned.get("lat"), cleaned.get("lng")
        if (lat is None) != (lng is None):
            self.add_error(None, "The map location was incomplete. Please confirm it again.")
        elif lat is not None:
            if not is_in_nepal(lat, lng):
                self.add_error(None, "The map pin must be inside Nepal. Please move it and confirm again.")
            else:
                # 6 decimal places (about 10 cm), the size of the database fields.
                cleaned["lat"] = Decimal(f"{lat:.6f}")
                cleaned["lng"] = Decimal(f"{lng:.6f}")
        return cleaned
