from django.shortcuts import render

from .models import Category, Product


def category_test(request):
    categories = Category.objects.all()
    return render(request, 'dev/category_test.html', {'categories': categories})


def product_test(request):
    products = Product.objects.select_related("category").all()
    return render(request, "dev/product_test.html", {"products": products})
