# Generated manually for initial section setup.

from django.db import migrations


def seed_sections(apps, schema_editor):
    """Creates all 8 predefined sections if missing."""
    Section = apps.get_model("bulls", "Section")
    setup = [
        (1, "LEFT", 1),
        (2, "LEFT", 2),
        (3, "LEFT", 3),
        (4, "LEFT", 4),
        (5, "RIGHT", 1),
        (6, "RIGHT", 2),
        (7, "RIGHT", 3),
        (8, "RIGHT", 4),
    ]
    for number, side, position in setup:
        Section.objects.get_or_create(
            number=number,
            defaults={"side": side, "position_in_row": position, "capacity": 150},
        )


def unseed_sections(apps, schema_editor):
    """Deletes prefilled sections during migration rollback."""
    Section = apps.get_model("bulls", "Section")
    Section.objects.filter(number__in=[1, 2, 3, 4, 5, 6, 7, 8]).delete()


class Migration(migrations.Migration):
    """Data migration with fixed yard layout."""

    dependencies = [
        ("bulls", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_sections, unseed_sections),
    ]
