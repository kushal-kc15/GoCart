from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from orders.models import Order, OrderItem
from .forms import ReviewForm
from .models import Category, Product, Review, star_text

PRODUCTS_PER_PAGE = 20
SUGGESTION_LIMIT = 6
REVIEWS_SHOWN = 10


def product_list(request):
    category_slug = request.GET.get("category", "").strip()
    subcategory_slug = request.GET.get("sub", "").strip()
    sort = request.GET.get("sort", "").strip()
    query = request.GET.get("q", "").strip()

    categories = Category.objects.filter(parent__isnull=True)
    selected_category = None
    selected_subcategory = None
    subcategories = Category.objects.none()
    products = Product.objects.filter(
        is_available=True,
        stock__gt=0,
    ).select_related("category__parent").prefetch_related("images")

    if query:
        # Store-wide search; category and sub are ignored.
        products = products.filter(
            Q(name__icontains=query)
            | Q(category__name__icontains=query)
            | Q(category__parent__name__icontains=query)
        )
    else:
        if category_slug:
            selected_category = get_object_or_404(categories, slug=category_slug)
        else:
            selected_category = categories.first()

        if selected_category:
            subcategories = selected_category.subcategories.all()
            products = products.filter(category__parent=selected_category)
        else:
            products = Product.objects.none()

        if subcategory_slug:
            selected_subcategory = get_object_or_404(subcategories, slug=subcategory_slug)
            products = products.filter(category=selected_subcategory)

    # "id" breaks ties so items don't repeat or vanish between pages.
    if sort == "price_low":
        products = products.order_by("price", "id")
    elif sort == "price_high":
        products = products.order_by("-price", "id")
    else:
        products = products.order_by("name", "id")
        if sort != "name":
            sort = ""

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
    """Product names for the header search dropdown."""
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

    related_products = Product.objects.filter(
        category__parent=product.category.parent,
        is_available=True,
        stock__gt=0,
    ).exclude(pk=product.pk).select_related("category").prefetch_related("images")[:4]

    # {stars: count}; order_by() clears Review's default ordering, which would break the GROUP BY.
    visible = product.reviews.filter(is_visible=True)
    counts = dict(visible.values_list("rating").annotate(n=Count("id")).order_by())
    total = sum(counts.values())
    average = 0
    if total:
        average = sum(rating * n for rating, n in counts.items()) / total
    bars = []
    for stars in (5, 4, 3, 2, 1):
        count = counts.get(stars, 0)
        percent = round(count * 100 / total) if total else 0
        bars.append({"stars": stars, "count": count, "percent": percent})

    my_review = None
    if request.user.is_authenticated:
        my_review = Review.objects.filter(user=request.user, product=product).first()

    return render(
        request,
        "dev/item.html",
        {
            "product": product,
            "related_products": related_products,
            "reviews": visible.select_related("user")[:REVIEWS_SHOWN],
            "review_total": total,
            "review_average": average,
            "average_stars": star_text(int(average + 0.5)),  # 4.5 -> 5 stars (round() would give 4)
            "rating_bars": bars,
            "can_review": _can_review(request.user, product),
            "my_review": my_review,
            "review_form": ReviewForm(instance=my_review),
        },
    )


def _can_review(user, product):
    """Only customers who have received this product can review it."""
    return user.is_authenticated and OrderItem.objects.filter(
        order__user=user,
        product=product,
        order__status=Order.Status.DELIVERED,
    ).exists()


def _reviews_url(product):
    return reverse("products:product_detail", args=[product.slug]) + "#reviews"


@require_POST
@login_required
def submit_review(request, slug):
    """Create the user's review, or update the one they wrote before."""
    product = get_object_or_404(Product, slug=slug, is_available=True)
    if not _can_review(request.user, product):
        messages.error(request, "You can review this after it's delivered.")
        return redirect(_reviews_url(product))

    my_review = Review.objects.filter(user=request.user, product=product).first()
    form = ReviewForm(request.POST, instance=my_review)
    if form.is_valid():
        review = form.save(commit=False)
        review.user = request.user
        review.product = product
        review.save()  # is_visible isn't in the form, so a hidden review stays hidden
        if my_review:
            messages.success(request, "Your review is updated.")
        else:
            messages.success(request, "Thanks, your review is posted.")
    else:
        messages.error(request, "Please pick 1 to 5 stars and write a short comment.")
    return redirect(_reviews_url(product))


@require_POST
@login_required
def delete_review(request, slug):
    product = get_object_or_404(Product, slug=slug)
    Review.objects.filter(user=request.user, product=product).delete()
    messages.success(request, "Your review is deleted.")
    return redirect(_reviews_url(product))
