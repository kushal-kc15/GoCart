from django import forms

from accounts.models import Address
from accounts.validators import normalize_nepali_phone


class AddressForm(forms.ModelForm):
    """Delivery address collected at checkout."""

    # Longer than the 10 digits we store, so "+977 981 234 5678" reaches clean_phone.
    # inputmode="tel" opens the number keypad on phones.
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            "placeholder": "98XXXXXXXX", "autocomplete": "tel", "inputmode": "tel",
        }),
    )

    class Meta:
        model = Address
        fields = ["recipient_name", "phone", "address_line", "city", "area"]
        # autocomplete lets the browser fill saved details.
        widgets = {
            "recipient_name": forms.TextInput(attrs={
                "placeholder": "Full name", "autocomplete": "name",
            }),
            "address_line": forms.TextInput(attrs={
                "placeholder": "Street, house no.", "autocomplete": "address-line1",
            }),
            "city": forms.TextInput(attrs={
                "placeholder": "City", "autocomplete": "address-level2",
            }),
            "area": forms.TextInput(attrs={
                "placeholder": "Area / tole (optional)", "autocomplete": "address-line2",
            }),
        }

    def clean_phone(self):
        # Same Nepali mobile check as the profile; stores just the 10 digits.
        return normalize_nepali_phone(self.cleaned_data["phone"])
