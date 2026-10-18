import re
from urllib.parse import urlencode

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, OuterRef, Q, Subquery, Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from orders.models import Order
from .models import Address, User

RECENT_ORDERS_SHOWN = 10


def phone_search_digits(term):
    """The digits to search for if the term looks like a phone number, else ""."""
    number = re.sub(r"[\s-]", "", term)
    # [0-9], not \d: \d also accepts other scripts' digits.
    if not re.fullmatch(r"\+?[0-9]+", number):
        return ""
    if number.startswith("+977"):
        number = number[4:]
    elif number.startswith("+"):
        number = number[1:]
    elif number.startswith("977") and len(number) > 10:
        # Only 11+ digits can carry a country code, so 9771234567 is left alone.
        number = number[3:]
    return number if len(number) >= 3 else ""


class AccountTypeFilter(admin.SimpleListFilter):
    title = "account type"
    parameter_name = "account_type"

    def lookups(self, request, model_admin):
        return (("customers", "Customers only"), ("staff", "Staff only"))

    def queryset(self, request, queryset):
        if self.value() == "customers":
            return queryset.filter(is_staff=False)
        if self.value() == "staff":
            return queryset.filter(is_staff=True)
        return queryset


class StaffCreationForm(UserCreationForm):
    def clean_email(self):
        # Lowercase, because login lowercases what is typed.
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        # Made by a superuser, so no emailed code is needed.
        self.instance.email_verified = True
        return super().save(commit)


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = StaffCreationForm
    change_password_form = AdminPasswordChangeForm
    # Django's own layout, plus "Email verified" so a superuser can let in a
    # customer whose code never arrives.
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Permissions", {
            "fields": (
                "is_active", "email_verified", "is_staff", "is_superuser",
                "groups", "user_permissions",
            ),
        }),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": (
                "username", "email", "first_name", "last_name",
                "usable_password", "password1", "password2",
            ),
        }),
    )

    list_display = (
        "customer_name", "email", "phone_number", "order_count", "total_spent",
        "last_order", "is_active",
    )
    list_display_links = ("customer_name", "email")
    search_help_text = "Name, email or phone number (with or without +977)."
    ordering = ("email",)

    # ---- who can see and change what ----
    def get_queryset(self, request):
        newest_address_phone = (
            Address.objects.filter(user=OuterRef("pk"))
            .order_by("-created_at", "-id")
            .values("phone")[:1]
        )
        queryset = super().get_queryset(request).annotate(
            _order_count=Count("orders"),
            _total_spent=Sum("orders__total", filter=~Q(orders__status=Order.Status.CANCELLED)),
            _last_order=Max("orders__created_at"),
            _address_phone=Subquery(newest_address_phone),
        )
        # Non-superusers only ever see customers; this is what keeps them off staff accounts.
        if not request.user.is_superuser:
            queryset = queryset.filter(is_staff=False, is_superuser=False)
        return queryset

    def has_add_permission(self, request):
        return request.user.is_superuser

    def user_change_password(self, request, id, form_url=""):
        # Setting someone's password lets you log in as them.
        if not request.user.is_superuser:
            raise PermissionDenied
        return super().user_change_password(request, id, form_url)

    def get_list_filter(self, request):
        if request.user.is_superuser:
            return (AccountTypeFilter, "is_active", "email_verified", "groups")
        return ("is_active", "email_verified")

    def get_list_display(self, request):
        columns = super().get_list_display(request)
        if request.user.has_perm("orders.view_money_totals"):
            return columns
        return [column for column in columns if column != "total_spent"]

    def get_readonly_fields(self, request, obj=None):
        # The email is the login, so only superusers may change it.
        if request.user.is_superuser:
            return ("recent_orders",)
        return ("recent_orders", "email")

    # ---- search by phone ----
    def get_search_results(self, request, queryset, search_term):
        digits = phone_search_digits(search_term)
        if not digits:
            return super().get_search_results(request, queryset, search_term)
        # Addresses are a subquery, so two matching addresses list a customer once.
        address_users = Address.objects.filter(phone__contains=digits).values("user")
        return queryset.filter(Q(phone__contains=digits) | Q(pk__in=address_users)), False

    # ---- list columns ----
    @admin.display(description="Name", ordering="first_name")
    def customer_name(self, obj):
        return obj.get_full_name() or "-"

    @admin.display(description="Phone")
    def phone_number(self, obj):
        return obj.phone or obj._address_phone or "-"

    @admin.display(description="Orders", ordering="_order_count")
    def order_count(self, obj):
        return obj._order_count

    @admin.display(description="Total spent", ordering="_total_spent")
    def total_spent(self, obj):
        return f"Rs. {obj._total_spent or 0}"

    @admin.display(description="Last order", ordering="_last_order")
    def last_order(self, obj):
        if obj._last_order is None:
            return "-"
        return date_format(timezone.localtime(obj._last_order), "j M Y")

    # ---- customer page ----
    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return super().get_fieldsets(request, obj)  # the add page
        description = self._delete_blocker(obj)
        if description and self.has_change_permission(request, obj):
            description += " To stop this account logging in, untick <strong>Active</strong> below and save."
        orders = ("Orders", {"fields": ("recent_orders",), "description": description})
        if request.user.is_superuser:
            return (orders, *super().get_fieldsets(request, obj))
        return (
            orders,
            ("Personal info", {"fields": ("first_name", "last_name", "email")}),
            ("Account", {"fields": ("is_active",)}),
        )

    @admin.display(description="Recent orders")
    def recent_orders(self, obj):
        orders = list(obj.orders.order_by("-created_at")[:RECENT_ORDERS_SHOWN])
        if not orders:
            return "No orders yet."
        rows = []
        for order in orders:
            rows.append((
                reverse("admin:orders_order_change", args=[order.pk]),
                order.pk,
                order.status_label,
                order.total,
                date_format(timezone.localtime(order.created_at), "j M Y"),
            ))
        rows_html = format_html_join(mark_safe("<br>"), '<a href="{}">#{}</a> · {} · Rs. {} · {}', rows)
        all_orders_url = f'{reverse("admin:orders_order_changelist")}?{urlencode({"q": obj.email})}'
        return format_html('{}<br><a href="{}">See all orders</a>', rows_html, all_orders_url)

    # ---- deleting ----
    def _delete_blocker(self, obj):
        """Why PROTECT stops this account being deleted, or "" if it can be."""
        # Cached on obj: called by get_fieldsets and several times by has_delete_permission.
        if not hasattr(obj, "_blocker"):
            count = getattr(obj, "_order_count", None)  # from get_queryset
            has_orders = obj.orders.exists() if count is None else count > 0
            if has_orders:
                obj._blocker = "This customer has orders, so the account can't be deleted."
            elif obj.collected_payments.exists() or obj.status_changes_made.exists():
                obj._blocker = (
                    "This account has collected cash or changed order statuses, "
                    "so it can't be deleted."
                )
            else:
                obj._blocker = ""
        return obj._blocker

    def has_delete_permission(self, request, obj=None):
        if obj is not None and self._delete_blocker(obj):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Address)
class AddressAdmin(ModelAdmin):
    list_display = ("user", "city", "area", "is_default", "created_at")
    ordering = ("user",)
