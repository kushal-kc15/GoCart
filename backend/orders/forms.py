from django import forms

from accounts.models import Address


class AddressForm(forms.ModelForm):
    """Delivery address collected at checkout."""

    class Meta:
        model = Address
        fields = ["recipient_name", "phone", "address_line", "city", "area"]
        # autocomplete lets the browser fill saved details; inputmode="tel"
        # opens the number keypad on phones.
        widgets = {
            "recipient_name": forms.TextInput(attrs={
                "placeholder": "Full name", "autocomplete": "name",
            }),
            "phone": forms.TextInput(attrs={
                "placeholder": "98XXXXXXXX", "autocomplete": "tel", "inputmode": "tel",
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
