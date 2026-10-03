from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db.models import Count
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm

from .models import Address, User
# Register your models here.


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    # Unfold's themed auth forms so add/change/password pages match the theme.
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm

    list_display = ("email", "first_name", "last_name", "role", "order_count", "is_active")
    ordering = ("email",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_order_count=Count("orders"))

    @admin.display(description="Orders", ordering="_order_count")
    def order_count(self, obj):
        return obj._order_count


@admin.register(Address)
class AddressAdmin(ModelAdmin):
    list_display = ("user", "city", "area", "is_default", "created_at")
    ordering = ("user",)
