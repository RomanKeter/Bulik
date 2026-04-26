import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("herd", "0002_departureevent_departure_weight_kg_bullhealthrecord"),
    ]

    operations = [
        migrations.CreateModel(
            name="ArrivalEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("arrived_at", models.DateField(default=django.utils.timezone.localdate, verbose_name="Дата поступления")),
                (
                    "arrival_weight_kg",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=7,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name="Вес при поступлении, кг",
                    ),
                ),
                ("comment", models.CharField(blank=True, max_length=255, verbose_name="Комментарий")),
                (
                    "bull",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="arrival",
                        to="herd.bull",
                        verbose_name="Бык",
                    ),
                ),
                (
                    "section",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="arrivals",
                        to="herd.section",
                        verbose_name="Секция поступления",
                    ),
                ),
            ],
            options={"ordering": ["-arrived_at", "-id"]},
        ),
        migrations.AddField(
            model_name="excelimportbatch",
            name="weighing_dates",
            field=models.JSONField(
                default=list,
                help_text="Список дат из заголовков колонок B, C, D ... в формате YYYY-MM-DD.",
                verbose_name="Даты взвешиваний из Excel",
            ),
        ),
        migrations.AddField(
            model_name="excelimportpendingrow",
            name="weights_by_date",
            field=models.JSONField(
                default=dict,
                help_text="Все веса строки Excel: ключ - дата YYYY-MM-DD, значение - вес.",
                verbose_name="Веса по датам",
            ),
        ),
    ]
