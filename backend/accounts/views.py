from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views import View

from .forms import SignUpForm


class SignupView(View):
    """Display and process the registration form."""

    def get(self, request):
        form = SignUpForm()
        return render(request, "dev/signup.html", {"form": form})

    def post(self, request):
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("home")
        return render(request, "dev/signup.html", {"form": form})


class LoginView(View):
    """Display and process the login form."""

    def get(self, request):
        return render(request, "dev/login.html", {"next": request.GET.get("next", "")})

    def post(self, request):
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            next_url = request.POST.get("next") or "/"
            return redirect(next_url)
        return render(request, "dev/login.html", {
            "error": "Invalid email or password.",
            "next": request.POST.get("next", ""),
        })


def logout_view(request):
    """Log the user out and redirect to home."""
    logout(request)
    return redirect("home")
