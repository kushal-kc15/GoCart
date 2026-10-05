from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from .models import Category, Product

PRODUCTS_PER_PAGE = 20
SUGGESTION_LIMIT = 6


def product_list(request):
    category_slug = request.GET.get("category", "").strip()
    subcategory_slug = request.GET.get("sub", "").strip()
    sort = request.GET.get("sort", "").strip()
    query = request.GET.get("q", "").strip()

    categories = Category.objects.filter(parent__isnull=True)
    selected_subcategory = None

    if query:
        # Store-wide search: product name, subcategory or department name.
        # category and sub are ignored here; sort and page still apply.
        selected_category = None
        subcategories = Category.objects.none()
        products = Product.objects.filter(
            Q(name__icontains=query)
            | Q(category__name__icontains=query)
            | Q(category__parent__name__icontains=query),
            is_available=True,
            stock__gt=0,
        ).select_related("category").prefetch_related("images")
    else:
        if category_slug:
            selected_category = get_object_or_404(categories, slug=category_slug)
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

        if subcategory_slug:
            selected_subcategory = get_object_or_404(subcategories, slug=subcategory_slug)
            products = products.filter(category=selected_subcategory)

    # "id" breaks ties so products with the same price/name keep a stable
    # order, otherwise items can repeat or go missing between pages.
    if sort == "price_low":
        products = products.order_by("price", "id")
    elif sort == "price_high":
        products = products.order_by("-price", "id")
    else:
        products = products.order_by("name", "id")
        if sort != "name":
            sort = ""

    # get_page shows page 1 for a bad value and the last page if too large.
    paginator = Paginator(products, PRODUCTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    page_range = paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1)

    return render(
        request,
        "dev/product_list.html",
        {
            "categories": categories,
            "selected_category": selected_category,
            "subcategories": subcategories,
            "selected_subcategory": selected_subcategory,
            "page_obj": page_obj,
            "page_range": page_range,
            "selected_sort": sort,
            "query": query,
        },
    )


def search_suggest(request):
    """Up to 6 product names for the header search dropdown."""
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    names = Product.objects.filter(
        is_available=True,
        stock__gt=0,
        name__icontains=query,
    ).order_by("name").values_list("name", flat=True)[:SUGGESTION_LIMIT]
    return JsonResponse({"results": list(names)})


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
