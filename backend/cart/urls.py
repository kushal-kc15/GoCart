from django.urls import path

from . import views

app_name = "cart"

urlpatterns = [
    path("", views.cart_detail, name="cart_detail"),
    path("add/", views.add_to_cart, name="add_to_cart"),
    path("update/", views.update_quantity, name="update_quantity"),
    path("remove/", views.remove_from_cart, name="remove_from_cart"),
]
