"""Material types become owner-managed categories; the tibebe library is removed."""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

# The fixed types materials had before, with their Amharic names.
OLD_TYPES = {
    "fabric": ("Fabric", "ጨርቅ"),
    "thread": ("Thread", "ክር"),
    "buttons": ("Buttons", "ቁልፍ"),
    "embroidery": ("Embroidery", "ጥልፍ"),
    "lace": ("Lace", "ዳንቴል"),
    "other": ("Other", "ሌላ"),
}


def types_to_categories(apps, schema_editor):
    Material = apps.get_model("shop", "Material")
    MaterialCategory = apps.get_model("shop", "MaterialCategory")
    for value in Material.objects.values_list("material_type", flat=True).distinct():
        name, name_am = OLD_TYPES.get(value, (value.title(), ""))
        category, _ = MaterialCategory.objects.get_or_create(name=name, defaults={"name_am": name_am})
        Material.objects.filter(material_type=value).update(category=category)


def categories_to_types(apps, schema_editor):
    Material = apps.get_model("shop", "Material")
    by_name = {name: value for value, (name, _) in OLD_TYPES.items()}
    for material in Material.objects.select_related("category"):
        material.material_type = by_name.get(material.category.name, "other") if material.category else "other"
        material.save(update_fields=["material_type"])


class Migration(migrations.Migration):

    dependencies = [
        ("shop", "0005_readymade_details"),
    ]

    operations = [
        migrations.CreateModel(
            name="MaterialCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=60, verbose_name="Name (English)")),
                ("name_am", models.CharField(blank=True, max_length=60, verbose_name="Name (Amharic)")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={"ordering": ["name"], "verbose_name_plural": "material categories"},
        ),
        migrations.AddField(
            model_name="material",
            name="category",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="materials", to="shop.materialcategory", verbose_name="Category"),
        ),
        migrations.RunPython(types_to_categories, categories_to_types),
        migrations.RemoveField(model_name="material", name="material_type"),
        migrations.DeleteModel(name="Tibebe"),
    ]
