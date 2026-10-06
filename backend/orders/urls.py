from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.order_list, name="order_list"),
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path("success/<int:pk>/", views.order_success, name="order_success"),
    path("<int:pk>/", views.order_detail, name="order_detail"),
    path("<int:pk>/cancel/", views.cancel_order, name="cancel_order"),
]
