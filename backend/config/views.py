from django.shortcuts import render


def home(request):

    return render(request, 'home.html')


def dev_index(request):
    return render(request, 'dev/index.html')
