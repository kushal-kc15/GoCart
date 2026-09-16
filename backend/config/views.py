from django.shortcuts import render

from products.models import Category, Product


def home(request):

    return render(request, 'home.html')


def dev_index(request):
    query = request.GET.get("q", "")
    categories = Category.objects.all()
    products = Product.objects.filter(
        is_available=True,
        stock__gt=0,
    ).prefetch_related("images")
    featured_products = products.filter(is_featured=True)

    if query:
        products = products.filter(name__icontains=query)

    return render(
        request,
        "dev/home_test.html",
        {
            "categories": categories,
            "products": products,
            "featured_products": featured_products,
            "query": query,
        },
    )
