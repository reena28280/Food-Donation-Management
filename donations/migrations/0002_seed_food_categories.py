from django.db import migrations


DEFAULT_CATEGORIES = [
    'Prepared meals',
    'Bakery and bread',
    'Fresh produce',
    'Dairy and eggs',
    'Pantry staples',
    'Snacks and desserts',
    'Beverages',
    'Other',
]


def seed_categories(apps, schema_editor):
    FoodCategory = apps.get_model('donations', 'FoodCategory')
    for category_name in DEFAULT_CATEGORIES:
        FoodCategory.objects.get_or_create(category_name=category_name)


class Migration(migrations.Migration):
    dependencies = [
        ('donations', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_categories, migrations.RunPython.noop),
    ]