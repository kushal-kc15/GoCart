from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("categories/", views.category_test, name="category_test"),
    path("products/", views.product_test, name="product_test"),
]
