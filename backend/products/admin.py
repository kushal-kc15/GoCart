from django.contrib import admin
from django.db.models import Count
from unfold.admin import ModelAdmin, TabularInline

from .models import Category, Product, ProductImage
# Register your models here.


class StockFilter(admin.SimpleListFilter):
    # Lets staff quickly find products that need restocking.
    title = "stock status"
    parameter_name = "stock_status"

    def lookups(self, request, model_admin):
        return (
            ("low", "Low stock (under 10)"),
            ("out", "Out of stock"),
        )

    def queryset(self, request, queryset):
        if self.value() == "low":
            return queryset.filter(stock__gt=0, stock__lt=10)
        if self.value() == "out":
            return queryset.filter(stock=0)
        return queryset


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'slug', 'parent', 'product_count', 'created_at')
    list_filter = ('parent',)
    prepopulated_fields = {'slug': ('name',)}

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_product_count=Count("products"))

    @admin.display(description="Products", ordering="_product_count")
    def product_count(self, obj):
        return obj._product_count


class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt_text", "sort_order")


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock', 'is_available', 'is_featured', 'updated_at')
    list_editable = ('price', 'stock', 'is_available')
    list_filter = ('is_available', 'is_featured', 'category', StockFilter)
    list_select_related = ('category',)
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductImageInline]
