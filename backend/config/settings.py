
from pathlib import Path

from django.urls import reverse, reverse_lazy


BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = 'django-insecure-local-development-only'

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver', '*']


# Application definition

INSTALLED_APPS = [
    'unfold',                   # must come before django.contrib.admin
    'unfold.contrib.filters',   # styled list filters
    'unfold.contrib.forms',     # styled form widgets
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'products',
    'cart',
    'wishlist',
    'orders',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR.parent / 'frontend' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'cart.context_processors.cart_count',
                'wishlist.context_processors.wishlist',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

# Dates are stored in UTC (USE_TZ) and shown in Nepal time.
TIME_ZONE = 'Asia/Kathmandu'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR.parent / 'frontend' / 'static']

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/"

# Shop details printed on the packing slip.
# TODO: fill these in with the real shop name, address and phone.
SHOP_INFO = {
    "name": "SHOP NAME (fill in config/settings.py)",
    "address": "SHOP ADDRESS (fill in config/settings.py)",
    "phone": "SHOP PHONE (fill in config/settings.py)",
}


# django-unfold admin theme
UNFOLD = {
    "SITE_TITLE": "GoCart Admin",
    "SITE_HEADER": "GoCart Admin",
    # Fills the admin home page (the dashboard) with today's work.
    "DASHBOARD_CALLBACK": "orders.dashboard.dashboard_callback",
    # Each link shows only to people who can use it. This only tidies the menu:
    # the real checks are on the pages themselves.
    "SIDEBAR": {
        "show_search": True,
        "navigation": [
            {
                "title": "Shop",
                "items": [
                    {"title": "Dashboard", "link": reverse_lazy("admin:index")},
                    {
                        "title": "Orders",
                        "link": reverse_lazy("admin:orders_order_changelist"),
                        "permission": lambda request: request.user.has_perm("orders.view_order"),
                    },
                    {
                        "title": "Products",
                        "link": reverse_lazy("admin:products_product_changelist"),
                        "permission": lambda request: request.user.has_perm("products.view_product"),
                    },
                    {
                        "title": "Categories",
                        "link": reverse_lazy("admin:products_category_changelist"),
                        "permission": lambda request: request.user.has_perm("products.view_category"),
                    },
                    {
                        "title": "Reviews",
                        "link": reverse_lazy("admin:products_review_changelist"),
                        "permission": lambda request: request.user.has_perm("products.view_review"),
                    },
                    {
                        "title": "Customers",
                        "link": reverse_lazy("admin:accounts_user_changelist"),
                        "permission": lambda request: request.user.has_perm("accounts.view_user"),
                    },
                ],
            },
            {
                # Superusers only: who can log in, and what each role may do.
                "title": "Admin",
                "items": [
                    {
                        "title": "Staff accounts",
                        "link": lambda request: reverse("admin:accounts_user_changelist") + "?account_type=staff",
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": "Roles",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
        ],
    },
}
