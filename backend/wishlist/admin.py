from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Wishlist, WishlistItem


class WishlistItemInline(TabularInline):
    model = WishlistItem
    extra = 0
    readonly_fields = ("product", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Wishlist)
class WishlistAdmin(ModelAdmin):
    list_display = ("id", "user", "created_at")
    search_fields = ("user__email",)
    list_select_related = ("user",)
    inlines = [WishlistItemInline]
