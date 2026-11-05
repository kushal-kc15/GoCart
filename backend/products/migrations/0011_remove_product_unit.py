from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0010_remove_review_weight'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='product',
            name='unit',
        ),
    ]
