from django.urls import path

from . import views


app_name = "products"

urlpatterns = [
    path("", views.product_list, name="product_list"),
    # Must stay above the slug route, or these are treated as product slugs.
    path("suggest/", views.search_suggest, name="search_suggest"),
    path("add/", views.add_product, name="add_product"),
    path("<slug:slug>/", views.product_detail, name="product_detail"),
    path("<slug:slug>/review/", views.submit_review, name="submit_review"),
    path("<slug:slug>/review/delete/", views.delete_review, name="delete_review"),
]
