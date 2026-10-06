from django.contrib.auth.management import create_permissions
from django.db import migrations

# Permissions as (app, codename). Order staff are packers, riders and counter staff.
ORDER_STAFF = [
    # Orders: see them, use the status panel, mark cash collected, print slips.
    ('orders', 'view_order'),
    ('orders', 'change_order'),
    ('orders', 'view_orderitem'),
    ('orders', 'view_payment'),
    ('orders', 'view_orderstatuschange'),
    # Look at products (stock) and customers (to call them), but not edit them.
    ('products', 'view_product'),
    ('products', 'view_productimage'),
    ('accounts', 'view_user'),
]

# Managers can do everything Order staff can, plus run the catalogue, reviews and customers.
# They never get: adding users, anything about groups and permissions, or adding or
# deleting orders (the admin doesn't allow those for anyone).
MANAGERS = ORDER_STAFF + [
    ('orders', 'view_money_totals'),
    ('products', 'add_product'),
    ('products', 'change_product'),
    ('products', 'delete_product'),
    ('products', 'add_productimage'),
    ('products', 'change_productimage'),
    ('products', 'delete_productimage'),
    ('products', 'view_category'),
    ('products', 'add_category'),
    ('products', 'change_category'),
    ('products', 'delete_category'),
    ('products', 'view_review'),
    ('products', 'change_review'),
    ('products', 'delete_review'),
    ('accounts', 'change_user'),
    ('accounts', 'delete_user'),
    ('accounts', 'view_address'),
    ('accounts', 'change_address'),
]

ROLES = {'Order staff': ORDER_STAFF, 'Managers': MANAGERS}


def create_groups(apps, schema_editor):
    # Django creates permissions only after all migrations have run, so on a new
    # database they don't exist yet. Create them now.
    for label in ('accounts', 'orders', 'products'):
        app_config = apps.get_app_config(label)
        original = getattr(app_config, 'models_module', None)
        app_config.models_module = True  # create_permissions skips apps without it
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = original

    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    for name, codenames in ROLES.items():
        group, _ = Group.objects.get_or_create(name=name)
        permissions = [
            Permission.objects.get(content_type__app_label=app, codename=codename)
            for app, codename in codenames
        ]
        group.permissions.set(permissions)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('orders', '0006_payment_collected_by'),  # has the money-totals permission
        ('products', '0006_alter_review_options_review_is_visible_and_more'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        # Going back leaves the groups alone: superusers may have edited them.
        migrations.RunPython(create_groups, migrations.RunPython.noop),
    ]
