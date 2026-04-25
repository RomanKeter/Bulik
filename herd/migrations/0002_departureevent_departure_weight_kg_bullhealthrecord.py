import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("herd", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="departureevent",
            name="departure_weight_kg",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=7,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="Вес на дату выбытия, кг",
                default=0,
            ),
            preserve_default=False,
        ),
        migrations.CreateModel(
            name="BullHealthRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("record_date", models.DateField(default=django.utils.timezone.localdate, verbose_name="Дата записи")),
                ("status_text", models.CharField(max_length=255, verbose_name="Состояние")),
                ("treatment_text", models.CharField(blank=True, max_length=255, verbose_name="Лечение/уколы")),
                ("comment", models.CharField(blank=True, max_length=255, verbose_name="Комментарий")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                (
                    "bull",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="health_records",
                        to="herd.bull",
                        verbose_name="Бык",
                    ),
                ),
            ],
            options={"ordering": ["-record_date", "-id"]},
        ),
    ]
