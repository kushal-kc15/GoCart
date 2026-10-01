from django import forms

from accounts.models import Address


class AddressForm(forms.ModelForm):
    """Delivery address collected at checkout."""

    class Meta:
        model = Address
        fields = ["recipient_name", "phone", "address_line", "city", "area"]
        widgets = {
            "recipient_name": forms.TextInput(attrs={"placeholder": "Full name"}),
            "phone": forms.TextInput(attrs={"placeholder": "98XXXXXXXX"}),
            "address_line": forms.TextInput(attrs={"placeholder": "Street, house no."}),
            "city": forms.TextInput(attrs={"placeholder": "City"}),
            "area": forms.TextInput(attrs={"placeholder": "Area / tole (optional)"}),
        }
