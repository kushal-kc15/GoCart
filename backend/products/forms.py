from django import forms

from .models import Product, Review


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "category", "price", "stock", "description", "is_available", "is_featured"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Fresh Spinach 500g"}),
            "price": forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 120", "min": "0", "step": "0.01"}),
            "stock": forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 50", "min": "0"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Describe the product..."}),
            "is_available": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch", "style": "width:2.6em;height:1.3em"}),
            "is_featured": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch", "style": "width:2.6em;height:1.3em"}),
        }


class ReviewForm(forms.ModelForm):
    """Stars (1-5) and a short comment, on the product page."""

    # Radio buttons need no JavaScript; 5 first, like most star pickers.
    rating = forms.TypedChoiceField(
        choices=[(n, f"{n} ★") for n in (5, 4, 3, 2, 1)],
        coerce=int,
        widget=forms.RadioSelect,
    )

    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "comment": forms.Textarea(attrs={
                "rows": 3, "placeholder": "What did you like or dislike?",
            }),
        }
