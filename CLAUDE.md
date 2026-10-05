# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All Django commands run from [backend/](backend/) with the project's virtualenv active. On Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
cd backend
python manage.py runserver          # dev server at http://127.0.0.1:8000/
python manage.py migrate            # apply migrations
python manage.py makemigrations     # after model changes
python manage.py createsuperuser    # admin login (uses email as USERNAME_FIELD)
python manage.py test               # run all app tests
python manage.py test orders.tests  # run one app's tests
python seed_catalog_data.py         # populate Category/Product from CATALOG dict; safe to re-run (uses update_or_create)
python seed_reviews.py              # LOCAL ONLY: demo customers + sample reviews; safe to re-run, refuses if DEBUG is off
```

`seed_catalog_data.py` calls `django.setup()` itself, so run it as a plain script from `backend/`, not via `manage.py`.

## Architecture

Django 6.0 project split between a Django backend and template/static assets that live outside the Python package.

### Layout
- [backend/config/](backend/config/) — project settings, root URLconf, and the `home` view. `TEMPLATES.DIRS` and `STATICFILES_DIRS` point *up and over* to [frontend/templates/](frontend/templates/) and [frontend/static/](frontend/static/), so template/static changes belong in `frontend/`, not inside any app.
- Apps: `accounts`, `products`, `cart`, `wishlist`, `orders`. Each is mounted under its own URL prefix in [backend/config/urls.py](backend/config/urls.py) and uses `app_name` namespacing (e.g. `cart:cart_detail`).
- SQLite (`backend/db.sqlite3`), `DEBUG=True`, and a hardcoded `SECRET_KEY` — configured for local dev only.

### Custom user model
`accounts.User` (see [backend/accounts/models.py](backend/accounts/models.py)) inherits `AbstractUser`, sets `USERNAME_FIELD = 'email'`, and is wired via `AUTH_USER_MODEL = 'accounts.User'`. Any FK to a user must use `settings.AUTH_USER_MODEL`, not `User` directly, to avoid circular imports (see how `products.Review`, `cart.Cart`, and `orders.Order` do it). Login authenticates by email; the custom `LoginView` in [backend/accounts/views.py](backend/accounts/views.py) passes the email as `username` to `authenticate()`.

### Catalog shape
`products.Category` is self-referential via `parent`. The codebase treats top-level rows (`parent__isnull=True`) as departments and their children as subcategories — see [backend/products/views.py](backend/products/views.py) and the `CATALOG` dict in [backend/seed_catalog_data.py](backend/seed_catalog_data.py). Product queries generally filter by `category__parent=<top_level>` to fetch everything within a department. Products with `is_featured=True` surface on the home page.

### Cart → Order flow
- `cart.Cart` is a `OneToOneField` to the user; `cart_detail`/`add_to_cart` use `get_or_create` so a cart always exists post-login.
- Checkout ([backend/orders/views.py](backend/orders/views.py)) runs inside `@transaction.atomic`: it re-validates stock per line, uses `transaction.set_rollback(True)` on any shortfall, then creates `Order` + `OrderItem` rows, decrements `product.stock` with `save(update_fields=['stock'])`, and clears the cart. Shipping is a flat 100 when the cart is non-empty; there is no address form yet, so `Order.address` is stubbed to `"To be provided"`.
- `orders.Payment` supports COD and eSewa (fields for `transaction_uuid`/`transaction_code`/`product_code`) but no payment flow is wired in yet — checkout currently creates the Order without a Payment row.

### DRF and CORS
`djangorestframework` and `django-cors-headers` are listed in [backend/requirements.txt](backend/requirements.txt) but not installed in `INSTALLED_APPS` or `MIDDLEWARE`. The app is server-rendered Django templates today; add them explicitly to settings when introducing API endpoints.

## Frontend conversion rules
- The frontend team's files (everything in frontend/templates and
  frontend/static outside dev/) are the design reference. NEVER edit or
  delete them.
- For each page, write a Django version in frontend/templates/dev/, and
  put its CSS, JS and images in css/dev/, js/dev/ and images/dev/.
- dev/ templates must load only dev/ assets, so copy any asset a page
  needs into the matching dev/ folder.
- Use {% static %}, {% url %} and template tags, but keep the design
  identical to the original.
- One page at a time. Keep code simple and beginner-friendly.
- At the end of the project, files outside dev/ are deleted and dev/ stays.
- Views render templates from dev/. Until a page is converted, its view
  will fail with TemplateDoesNotExist. That is expected during the rebuild.

## Scope
- Current scope is Phase 1: complete shopping journey with cash on delivery.
- Do NOT add: eSewa/online payment, email/SMS, coupons, caching, deployment
  config, or DRF APIs unless asked.
- Work on one feature at a time and commit small.

## Code style
- Keep code simple and readable. This is an internship project with beginners.
- Prefer Django's built-in features (generic views, ModelForm, messages,
  login_required) over custom solutions.
- No extra abstractions, service layers, custom decorators, signals, or
  clever one-liners. Plain functions and clear names are fine.
- Add short comments only where the reason isn't obvious.
- Optimizations, refactors and advanced features wait for the final phase.

## Later (final phase)
- Product detail: make page wider/larger image, shrink SHOP banner,
  clickable breadcrumb, bigger qty/Buy Now/Add to Cart controls.
- Review likes: buttons are disabled ("Coming soon"); needs a like model + view.
- Reviews: product page shows the newest 10; add a "Show all" page.
- Product cards: average rating + count (annotate on the list; home "Most Popular"
  already sums order items, so use a Subquery there to avoid inflated sums).
- Product list: frontend team to polish styling; search is scoped to one department.
- Home page: Most Popular is static; footer SHOP links are placeholders.
- Header: cart count badge is empty; wishlist link is "#".
- Header search dropdown uses a hardcoded name list.
- Slider: resizing the window can leave the index past the end until Prev is clicked.
- Old accounts with mixed-case emails can't log in (login lowercases the email).