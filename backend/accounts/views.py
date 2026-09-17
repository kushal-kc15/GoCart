from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages
from .forms import SignUpForm,LoginForm
from .models import Address

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome to GoCart, {user.first_name or "there"}! Your account has been created.')
            return redirect('home')
    else:
        form = SignUpForm()
    return render(request, 'signup.html', {'form': form})


def login_view(request):
    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        password = form.cleaned_data["password"]
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)

            
            return redirect("home")
        messages.error(request, "Invalid email or password.")
    return render(request, "login.html", {"form": form})

def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out successfully.')
    return redirect('home')

def address_list(request):
    addresses = Address.objects.select_related("user").all()
    return render(request, "dev/address_test.html", {"addresses": addresses})
