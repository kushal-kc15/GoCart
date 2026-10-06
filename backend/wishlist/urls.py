from django.urls import path

from . import views

app_name = "wishlist"

urlpatterns = [
    path("", views.wishlist_detail, name="wishlist_detail"),
    path("toggle/", views.toggle_wishlist, name="toggle"),
]
