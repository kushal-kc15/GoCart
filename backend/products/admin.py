from django.contrib import admin
from django.db.models import Count, F, Prefetch
from django.utils import timezone
from django.utils.html import format_html
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import display

from .models import LOW_STOCK_LIMIT, Category, Product, ProductImage, Review
# Register your models here.


class StockFilter(admin.SimpleListFilter):
    # Lets staff quickly find products that need restocking.
    title = "stock status"
    parameter_name = "stock_status"

    def lookups(self, request, model_admin):
        return (
            ("low", f"Low stock (under {LOW_STOCK_LIMIT})"),
            ("out", "Out of stock"),
        )

    def queryset(self, request, queryset):
        if self.value() == "low":
            return queryset.filter(stock__gt=0, stock__lt=LOW_STOCK_LIMIT)
        if self.value() == "out":
            return queryset.filter(stock=0)
        return queryset


@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ('name', 'slug', 'department', 'product_count', 'created_at')
    list_filter = ('parent',)
    # parent can be empty, so Django doesn't join it by itself: without this
    # the list asks the database for every row's parent separately.
    list_select_related = ('parent',)
    prepopulated_fields = {'slug': ('name',)}

    def get_queryset(self, request):
        # Products sit in subcategories, so a department counts its own products
        # plus those of its subcategories. distinct=True because both counts
        # join a products table.
        return super().get_queryset(request).annotate(
            _own_products=Count("products", distinct=True),
            _sub_products=Count("subcategories__products", distinct=True),
        ).annotate(_product_count=F("_own_products") + F("_sub_products"))

    @admin.display(description="Department", ordering="parent__name")
    def department(self, obj):
        return obj.parent.name if obj.parent else "-"

    @admin.display(description="Products", ordering="_product_count")
    def product_count(self, obj):
        return obj._product_count


class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "alt_text", "sort_order")


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = (
        'thumbnail', 'name', 'category', 'price', 'stock', 'stock_badge',
        'is_available', 'is_featured', 'updated_at',
    )
    list_display_links = ('name',)
    list_editable = ('price', 'stock', 'is_available')
    list_filter = ('is_available', 'is_featured', 'category', StockFilter)
    list_select_related = ('category',)
    search_fields = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [ProductImageInline]
    actions = ['show_on_site', 'hide_from_site']

    def get_queryset(self, request):
        # All images for the page in one query (the same order the shop uses),
        # so the thumbnail column costs nothing per row.
        images = Prefetch("images", queryset=ProductImage.objects.order_by("sort_order", "id"))
        return super().get_queryset(request).prefetch_related(images)

    @admin.display(description="Image")
    def thumbnail(self, obj):
        image = next(iter(obj.images.all()), None)
        if image is None:
            return "-"
        return format_html(
            '<img src="{}" alt="" width="40" height="40" style="object-fit: cover; border-radius: 4px;">',
            image.image.url,
        )

    @display(description="Stock status", label={"out": "danger", "low": "warning"})
    def stock_badge(self, obj):
        # Nothing when stock is fine: only the problems stand out.
        if obj.stock == 0:
            return "out", "Out of stock"
        if obj.stock < LOW_STOCK_LIMIT:
            return "low", "Low"
        return None

    @admin.action(description="Show selected products on the site", permissions=["change"])
    def show_on_site(self, request, queryset):
        updated = queryset.update(is_available=True, updated_at=timezone.now())
        self.message_user(request, f"{updated} product(s) now shown on the site.")

    @admin.action(description="Hide selected products from the site", permissions=["change"])
    def hide_from_site(self, request, queryset):
        updated = queryset.update(is_available=False, updated_at=timezone.now())
        self.message_user(request, f"{updated} product(s) now hidden from the site.")


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
