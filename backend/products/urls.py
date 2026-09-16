from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("categories/", views.category_list, name="category_list"),
    path(
        "categories/<slug:slug>/",
        views.category_detail,
        name="category_detail",
    ),
    path("products/", views.product_list, name="product_list"),
    path(
        "products/<slug:slug>/",
        views.product_detail,
        name="product_detail",
    ),
    path("product-images/", views.product_images, name="product_images"),
]
