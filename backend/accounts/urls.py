from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"

urlpatterns = [
    path("signup/", views.SignupView.as_view(), name="signup"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("verify-email/", views.verify_email, name="verify_email"),
    path("verify-email/resend/", views.resend_code, name="resend_code"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),

    # Password reset: Django's own views and tokens, with our templates.
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="dev/password_reset_form.html",
            email_template_name="dev/password_reset_email.txt",
            subject_template_name="dev/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
            # The email's link uses site_domain, not the request's Host header.
            extra_email_context={
                "shop_name": settings.SHOP_INFO["name"],
                "site_domain": settings.SITE_DOMAIN,
            },
        ),
        name="password_reset",
    ),
    path(
        "password-reset/sent/",
        auth_views.PasswordResetDoneView.as_view(template_name="dev/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="dev/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(template_name="dev/password_reset_complete.html"),
        name="password_reset_complete",
    ),
]
