from django import forms

from .models import Review


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
