from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.utils.text import slugify

from .validators import normalize_nepali_phone

User = get_user_model()


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    # Longer than the 10 stored digits, so "+977 981 234 5678" reaches clean_phone.
    phone = forms.CharField(max_length=20, required=False)

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone",
        )

    field_attrs = {
        "first_name": {"placeholder": "Jane", "autocomplete": "given-name"},
        "last_name": {"placeholder": "Doe", "autocomplete": "family-name"},
        "email": {"placeholder": "you@example.com", "autocomplete": "email"},
        "phone": {"placeholder": "98XXXXXXXX", "autocomplete": "tel"},
        "password1": {"placeholder": "Create a password", "autocomplete": "new-password"},
        "password2": {"placeholder": "Re-enter your password", "autocomplete": "new-password"},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, attrs in self.field_attrs.items():
            self.fields[name].widget.attrs.update({"class": "form-control", **attrs})

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        # When an unverified account is being replaced, it is self.instance: skip it.
        others = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if others.exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        if not phone:
            return phone
        return normalize_nepali_phone(phone)

    # username is unused but AbstractUser needs a unique value.
    def _unique_username(self, email):
        base = (slugify(email.split("@")[0]) or "user")[:140]
        candidate, suffix = base, 1
        while User.objects.filter(username__iexact=candidate).exists():
            suffix += 1
            candidate = f"{base}{suffix}"
        return candidate

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if not user.username:  # a replaced account keeps its username
            user.username = self._unique_username(user.email)
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "gc-input", "autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "gc-input", "autocomplete": "family-name"}),
    )
    # Longer than the 10 stored digits, so "+977 981 234 5678" reaches clean_phone.
    phone = forms.CharField(
        max_length=20,
        required=False,
        label="Phone (optional)",
        widget=forms.TextInput(attrs={
            "class": "gc-input", "placeholder": "98XXXXXXXX",
            "autocomplete": "tel", "inputmode": "tel",
        }),
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "phone")

    def clean_phone(self):
        phone = self.cleaned_data["phone"]
        if not phone:
            return phone
        return normalize_nepali_phone(phone)
