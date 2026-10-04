from django.urls import path

from . import views


app_name = "products"

urlpatterns = [
    path("", views.product_list, name="product_list"),
    # Must stay above the slug route, or "suggest" is treated as a product slug.
    path("suggest/", views.search_suggest, name="search_suggest"),
    path("<slug:slug>/", views.product_detail, name="product_detail"),
]
