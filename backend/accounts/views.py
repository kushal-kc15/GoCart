import logging
import math
import re
import smtplib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST

from .forms import ProfileForm, SignUpForm
from .models import CODE_LIFETIME, EmailVerification, User, make_code

logger = logging.getLogger(__name__)

REMEMBER_ME_SECONDS = 60 * 60 * 24 * 30

# What this browser session remembers while the user confirms their email.
VERIFY_SESSION_KEYS = ("verify_user_id", "verify_token", "verify_next", "verify_remember")

CODE_ERRORS = {
    "wrong": "That code isn't right. Please check the email and try again.",
    "locked": "Too many wrong tries. Please click Resend code to get a new one.",
    "expired": "This code has expired. Please click Resend code to get a new one.",
}


def _safe_next_url(request, value):
    """`value` if it is a URL on this site, else ""."""
    if value and url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return ""


def _set_session_length(request, remember):
    if remember:
        request.session.set_expiry(REMEMBER_ME_SECONDS)
    else:
        request.session.set_expiry(0)  # ends with the browser session


# ---- emailed sign-up code ----
def _send_code(verification):
    """Email a new code to the user. Returns False if the email couldn't be sent."""
    user = verification.user
    code = make_code()
    shop = settings.SHOP_INFO["name"]
    minutes = int(CODE_LIFETIME.total_seconds() // 60)
    expires = date_format(timezone.localtime(timezone.now() + CODE_LIFETIME), "g:i A")
    body = (
        f"Hi {user.first_name or 'there'},\n\n"
        f"Your {shop} verification code is: {code}\n\n"
        f"It expires in {minutes} minutes (at {expires}). "
        "If you didn't create an account, you can ignore this email.\n\n"
        f"- {shop}\n"
    )
    try:
        send_mail(f"Your {shop} verification code", body, None, [user.email])
    except (smtplib.SMTPException, OSError):  # OSError: no connection, timeout
        logger.exception("Couldn't send the verification code to %s", user.email)
        return False
    # Saved only after sending, so a failed send doesn't use up the resend limits.
    verification.save_sent_code(code)
    return True


def _send_code_if_allowed(request, verification):
    wait = verification.seconds_until_resend()
    if wait > 60:
        messages.error(request, f"Too many codes asked for. Please try again in {math.ceil(wait / 60)} minutes.")
    elif wait:
        messages.info(request, f"A code was sent recently. You can ask for a new one in {wait} seconds.")
    elif _send_code(verification):
        messages.success(request, f"We sent a 6-digit code to {verification.user.email}.")
    else:
        messages.error(request, "We couldn't send the code right now. Please try Resend.")


def _start_verification(request, user, next_url="", remember=None):
    """Let this browser session confirm the user's email, send a code and show the verify page."""
    verification = EmailVerification.claim(user)
    request.session["verify_user_id"] = user.pk
    request.session["verify_token"] = verification.session_token
    request.session["verify_next"] = next_url
    request.session["verify_remember"] = remember  # None after signup: keep the normal session length
    _send_code_if_allowed(request, verification)
    return redirect("accounts:verify_email")


def _forget_verification(request):
    for key in VERIFY_SESSION_KEYS:
        request.session.pop(key, None)


def _session_verification(request):
    """The code this browser session may use, or None if another session has taken it over."""
    verification = (
        EmailVerification.objects.select_related("user")
        .filter(user_id=request.session.get("verify_user_id"), user__is_active=True)
        .first()
    )
    if verification and verification.token_matches(request.session.get("verify_token")):
        return verification
    return None


def _verification_gone(request):
    user = User.objects.filter(pk=request.session.get("verify_user_id")).first()
    _forget_verification(request)
    if user and user.email_verified:
        messages.info(request, "Your email is already confirmed. Please log in.")
        return redirect("accounts:login")
    messages.error(request, "This sign-up was replaced. Please sign up again.")
    return redirect("accounts:signup")


def _replaceable_account(email):
    """An unverified customer account with this email. A new sign-up may take its place."""
    email = email.strip().lower()
    if not email:
        return None
    return User.objects.filter(
        email__iexact=email, email_verified=False, is_active=True,
        is_staff=False, is_superuser=False, orders__isnull=True,
    ).first()


class SignupView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("home")
        return render(request, "dev/signup.html", {"form": SignUpForm()})

    def post(self, request):
        # An unverified account with this email is overwritten, not reported as taken.
        existing = _replaceable_account(request.POST.get("email", ""))
        form = SignUpForm(request.POST, instance=existing)
        if form.is_valid():
            user = form.save()
            return _start_verification(request, user)
        return render(request, "dev/signup.html", {"form": form})


def verify_email(request):
    if "verify_user_id" not in request.session:
        return redirect("accounts:login")
    verification = _session_verification(request)
    if verification is None:
        return _verification_gone(request)

    error = ""
    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        # [0-9], not \d: \d also accepts other scripts' digits.
        if not re.fullmatch(r"[0-9]{6}", code):
            error = "Enter the 6-digit code from the email."
        else:
            result = verification.check_code(code)
            if result == "ok":
                return _finish_verification(request, verification)
            error = CODE_ERRORS[result]
    return render(request, "dev/verify_email.html", {"email": verification.user.email, "error": error})


def _finish_verification(request, verification):
    user = verification.user
    next_url = _safe_next_url(request, request.session.get("verify_next", ""))
    remember = request.session.get("verify_remember")
    user.email_verified = True
    user.save(update_fields=["email_verified"])
    verification.delete()
    _forget_verification(request)
    login(request, user)
    if remember is not None:  # came from the login page
        _set_session_length(request, remember)
    messages.success(request, f"Welcome to GoCart, {user.first_name}! Your account is ready.")
    return redirect(next_url or "home")


@require_POST
def resend_code(request):
    if "verify_user_id" not in request.session:
        return redirect("accounts:login")
    verification = _session_verification(request)
    if verification is None:
        return _verification_gone(request)
    _send_code_if_allowed(request, verification)
    return redirect("accounts:verify_email")


class LoginView(View):
    def get(self, request):
        next_url = _safe_next_url(request, request.GET.get("next", ""))
        if request.user.is_authenticated:
            return redirect(next_url or "home")
        return render(request, "dev/login.html", {"next": next_url})

    def post(self, request):
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        next_url = _safe_next_url(request, request.POST.get("next", ""))
        remember = bool(request.POST.get("remember"))
        user = authenticate(request, username=email, password=password)
        if user is not None and not user.email_verified:
            # Right password, but the email was never confirmed: send a code instead.
            return _start_verification(request, user, next_url, remember)
        if user is not None:
            login(request, user)
            _set_session_length(request, remember)
            messages.success(request, "You are now logged in.")
            return redirect(next_url or "home")
        return render(request, "dev/login.html", {
            "error": "Incorrect email or password. Please try again.",
            "email": email,
            "next": next_url,
        })


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("home")


@login_required
def profile_view(request):
    orders = request.user.orders
    recent_orders = orders.prefetch_related("items")[:3]

    initials = (request.user.first_name[:1] + request.user.last_name[:1]).upper()
    if not initials:
        initials = request.user.email[:1].upper()

    return render(
        request,
        "dev/profile.html",
        {
            "profile_user": request.user,
            "recent_orders": recent_orders,
            "order_count": orders.count(),
            "initials": initials,
        },
    )


@login_required
def edit_profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated.")
            return redirect("accounts:profile")
        # Not saved: undo the typed values the form put on request.user.
        request.user.refresh_from_db()
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "dev/profile_edit.html", {"form": form})
