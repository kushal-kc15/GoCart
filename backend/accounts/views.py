from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_POST

from orders.models import Order

from .forms import SignUpForm

REMEMBER_ME_SECONDS = 60 * 60 * 24 * 30


def _safe_next_url(request, value):
    """Return `value` if it is a local URL, otherwise an empty string."""
    if value and url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return ""


class SignupView(View):
    """Display and process the registration form."""

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("home")
        return render(request, "dev/signup.html", {"form": SignUpForm()})

    def post(self, request):
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome to GoCart, {user.first_name}! Your account is ready.")
            return redirect("home")
        return render(request, "dev/signup.html", {"form": form})


class LoginView(View):
    """Display and process the login form."""

    def get(self, request):
        next_url = _safe_next_url(request, request.GET.get("next", ""))
        if request.user.is_authenticated:
            return redirect(next_url or "home")
        return render(request, "dev/login.html", {"next": next_url})

    def post(self, request):
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        next_url = _safe_next_url(request, request.POST.get("next", ""))
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            if not request.POST.get("remember"):
                request.session.set_expiry(0)  # end with the browser session
            else:
                request.session.set_expiry(REMEMBER_ME_SECONDS)
            messages.success(request, "You are now logged in.")
            return redirect(next_url or "home")
        return render(request, "dev/login.html", {
            "error": "Incorrect email or password. Please try again.",
            "email": email,
            "next": next_url,
        })


@require_POST
def logout_view(request):
    """Log the user out (POST only) and redirect to home."""
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("home")


@login_required
def profile_view(request):
    """Read-only account overview with the user's order history."""
    # Newest first (Order.Meta.ordering); items prefetched for the item counts.
    orders = request.user.orders.prefetch_related("items")

    # Quick stats: money spent on orders that weren't cancelled.
    total_spent = orders.exclude(status=Order.Status.CANCELLED).aggregate(
        total=Sum("total")
    )["total"] or 0

    # "Location" = city of the default (or most recent) saved address.
    address = request.user.addresses.order_by("-is_default", "-created_at").first()

    # Initials for the avatar circles (no photo upload yet).
    initials = (request.user.first_name[:1] + request.user.last_name[:1]).upper()
    if not initials:
        initials = request.user.email[:1].upper()

    return render(
        request,
        "dev/profile.html",
        {
            "profile_user": request.user,
            "orders": orders,
            "total_spent": total_spent,
            "location": address.city if address else "",
            "initials": initials,
        },
    )
