from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from config import views

# The admin home page is our dashboard (orders/templates/admin/dashboard.html,
# data from orders/dashboard.py). A different name from unfold's own
# admin/index.html, so the dashboard can extend it.
admin.site.index_template = "admin/dashboard.html"


urlpatterns = [
    path("", views.home, name="home"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("products/", include("products.urls")),
    path("cart/", include("cart.urls")),
    path("orders/", include("orders.urls")),
    path("wishlist/", include("wishlist.urls")),
]

handler404 = "config.views.page_not_found"
handler500 = "config.views.server_error"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
