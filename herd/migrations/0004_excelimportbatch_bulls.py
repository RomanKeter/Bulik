from datetime import datetime

from django.db import migrations, models


def backfill_import_batch_bulls(apps, schema_editor):
    ExcelImportBatch = apps.get_model("herd", "ExcelImportBatch")
    Bull = apps.get_model("herd", "Bull")

    for batch in ExcelImportBatch.objects.all():
        bull_ids = set(batch.bulls.values_list("pk", flat=True))
        bull_ids.update(
            batch.pending_items.filter(is_resolved=True, resolved_to_id__isnull=False).values_list(
                "resolved_to_id", flat=True
            )
        )
        dates = [datetime.strptime(date_text, "%Y-%m-%d").date() for date_text in batch.weighing_dates]
        if dates:
            bull_ids.update(
                Bull.objects.filter(
                    weight_records__weighing_date__in=dates,
                    weight_records__source="excel",
                ).values_list("pk", flat=True)
            )
        if bull_ids:
            batch.bulls.set(Bull.objects.filter(pk__in=bull_ids))


class Migration(migrations.Migration):
    dependencies = [
        ("herd", "0003_arrivalevent_excel_multidate_import"),
    ]

    operations = [
        migrations.AddField(
            model_name="excelimportbatch",
            name="bulls",
            field=models.ManyToManyField(
                blank=True,
                help_text="Быки, для которых из этого Excel применены веса.",
                related_name="excel_import_batches",
                to="herd.bull",
                verbose_name="Быки из файла",
            ),
        ),
        migrations.RunPython(backfill_import_batch_bulls, migrations.RunPython.noop),
    ]
