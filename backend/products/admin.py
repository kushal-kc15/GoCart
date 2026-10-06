from django.contrib import admin
from django.db.models import Count
from unfold.admin import ModelAdmin, TabularInline

from .models import Category, Product, ProductImage, Review
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


@admin.register(Review)
class ReviewAdmin(ModelAdmin):
    list_display = ('product', 'reviewer_email', 'rating', 'is_visible', 'created_at')
    # Product filter lists only products that have reviews.
    list_filter = ('rating', 'is_visible', ('product', admin.RelatedOnlyFieldListFilter))
    search_fields = ('product__name', 'user__email', 'comment')
    list_select_related = ('product', 'user')
    # Staff can hide a review but not change what the customer wrote.
    readonly_fields = ('user', 'product', 'rating', 'comment', 'created_at', 'updated_at')
    actions = ['hide_reviews', 'show_reviews']

    @admin.display(description="Customer", ordering="user__email")
    def reviewer_email(self, obj):
        return obj.user.email

    @admin.action(description="Hide selected reviews")
    def hide_reviews(self, request, queryset):
        updated = queryset.update(is_visible=False)
        self.message_user(request, f"{updated} review(s) hidden.")

    @admin.action(description="Show selected reviews")
    def show_reviews(self, request, queryset):
        updated = queryset.update(is_visible=True)
        self.message_user(request, f"{updated} review(s) shown.")
