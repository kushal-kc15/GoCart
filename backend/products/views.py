from django.shortcuts import get_object_or_404, render

from .models import Category, Product


def product_list(request):
    category_slug = request.GET.get("category", "").strip()
    subcategory_slug = request.GET.get("sub", "").strip()
    sort = request.GET.get("sort", "").strip()
    query = request.GET.get("q", "").strip()

    categories = Category.objects.filter(parent__isnull=True)

    if category_slug:
        selected_category = get_object_or_404(categories, slug=category_slug)
    elif query:
        matching_product = Product.objects.filter(
            category__parent__isnull=False,
            is_available=True,
            stock__gt=0,
            name__icontains=query,
        ).select_related("category__parent").first()
        selected_category = matching_product.category.parent if matching_product else categories.first()
    else:
        selected_category = categories.first()

    if selected_category:
        subcategories = selected_category.subcategories.all()
        products = Product.objects.filter(
            category__parent=selected_category,
            is_available=True,
            stock__gt=0,
        ).select_related(
            "category",
            "category__parent",
        ).prefetch_related("images")
    else:
        subcategories = Category.objects.none()
        products = Product.objects.none()

    selected_subcategory = None
    if subcategory_slug:
        selected_subcategory = get_object_or_404(subcategories, slug=subcategory_slug)
        products = products.filter(category=selected_subcategory)

    if query:
        products = products.filter(name__icontains=query)

    if sort == "price_low":
        products = products.order_by("price")
    elif sort == "price_high":
        products = products.order_by("-price")
    else:
        products = products.order_by("name")
        if sort != "name":
            sort = ""

    return render(
        request,
        "dev/product_list.html",
        {
            "categories": categories,
            "selected_category": selected_category,
            "subcategories": subcategories,
            "selected_subcategory": selected_subcategory,
            "products": products,
            "selected_sort": sort,
            "query": query,
        },
    )


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category__parent").prefetch_related("images"),
        slug=slug,
        is_available=True,
    )

    # Other in-stock products from the same department (excludes this one)
    related_products = Product.objects.filter(
        category__parent=product.category.parent,
        is_available=True,
        stock__gt=0,
    ).exclude(pk=product.pk).select_related("category").prefetch_related("images")[:4]

    return render(
        request,
        "dev/item.html",
        {
            "product": product,
            "related_products": related_products,
        },
    )
