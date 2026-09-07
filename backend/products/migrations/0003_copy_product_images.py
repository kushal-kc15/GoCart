from django.db import migrations


def copy_product_images(apps, schema_editor):
    Product = apps.get_model("products", "Product")
    ProductImage = apps.get_model("products", "ProductImage")

    products_with_images = Product.objects.exclude(image="").exclude(image__isnull=True)

    for product in products_with_images.iterator():
        image_path = product.image.name
        image_exists = ProductImage.objects.filter(
            product_id=product.pk,
            image=image_path,
        ).exists()

        if not image_exists:
            ProductImage.objects.create(
                product_id=product.pk,
                image=image_path,
                alt_text=product.name,
                sort_order=0,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0002_alter_product_price"),
    ]

    operations = [
        migrations.RunPython(copy_product_images, migrations.RunPython.noop),
    ]
