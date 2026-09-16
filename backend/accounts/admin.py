from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Address
# Register your models here.


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "first_name", "last_name", "role", "is_active")
    ordering = ("email",)

@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "city", "area","is_default", "created_at")
    ordering = ("user",)