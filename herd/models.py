"""
Модели предметной области бычатника.

Модуль описывает основные сущности учета:
- секции площадки;
- карточку быка;
- историю взвешиваний;
- перемещения между секциями;
- выбытия с площадки;
- загрузки Excel и строки, требующие ручного сопоставления.
"""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Section(models.Model):
    """
    Секция, в которой содержатся быки.

    Принято, что в хозяйстве есть 8 секций: 4 слева и 4 справа.
    Для простоты данные секции задаются как записи в базе.
    """

    side = models.CharField(
        "Сторона",
        max_length=5,
        choices=(("LEFT", "Левая"), ("RIGHT", "Правая")),
    )
    order = models.PositiveSmallIntegerField("Порядковый номер в ряду")
    name = models.CharField("Название секции", max_length=32, unique=True)
    capacity = models.PositiveSmallIntegerField(
        "Вместимость",
        default=150,
        validators=[MinValueValidator(1)],
    )

    class Meta:
        ordering = ["side", "order"]
        constraints = [
            models.UniqueConstraint(fields=["side", "order"], name="unique_side_order"),
        ]

    def __str__(self) -> str:
        return self.name


class Bull(models.Model):
    """
    Карточка быка.

    `external_id` хранит исходный номер из файла (например, by000160474233).
    Для удобства дополнительно сохраняются:
    - `biavka_part`: первые 8 символов;
    - `bull_number`: последние 6 символов (основной номер животного).
    """

    external_id = models.CharField("Полный номер", max_length=32, unique=True)
    biavka_part = models.CharField("Бивайка (первые 8 символов)", max_length=8)
    bull_number = models.CharField("Номер быка (последние 6 символов)", max_length=6)
    section = models.ForeignKey(
        Section,
        verbose_name="Текущая секция",
        on_delete=models.PROTECT,
        related_name="bulls",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(
        "На площадке",
        default=True,
        help_text="Если выключено, бык считается выбывшим.",
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        ordering = ["bull_number"]

    def __str__(self) -> str:
        return self.external_id

    def save(self, *args, **kwargs):
        """
        Перед сохранением автоматически заполняет части номера.
        """
        normalized = (self.external_id or "").strip()
        self.biavka_part = normalized[:8]
        self.bull_number = normalized[-6:] if len(normalized) >= 6 else normalized
        super().save(*args, **kwargs)

    @property
    def current_weight(self):
        """
        Возвращает последний зафиксированный вес быка или None, если данных нет.
        """
        latest = self.weight_records.order_by("-weighing_date", "-id").first()
        return latest.weight_kg if latest else None


class WeightRecord(models.Model):
    """
    История взвешиваний быка.

    Данные могут поступать из Excel или через ручной ввод.
    """

    SOURCE_CHOICES = (
        ("excel", "Excel"),
        ("manual", "Ручной ввод"),
    )

    bull = models.ForeignKey(
        Bull,
        verbose_name="Бык",
        on_delete=models.CASCADE,
        related_name="weight_records",
    )
    weighing_date = models.DateField("Дата взвешивания")
    weight_kg = models.DecimalField(
        "Вес, кг",
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    source = models.CharField("Источник", max_length=16, choices=SOURCE_CHOICES, default="manual")
    note = models.CharField("Комментарий", max_length=255, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["-weighing_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["bull", "weighing_date", "source"],
                name="unique_weight_for_bull_date_source",
            )
        ]

    def __str__(self) -> str:
        return f"{self.bull.external_id} - {self.weighing_date} - {self.weight_kg} кг"


class SectionMovement(models.Model):
    """
    Перемещение быка между секциями.

    Событие создается в любую дату, независимо от даты перевески.
    """

    bull = models.ForeignKey(
        Bull,
        verbose_name="Бык",
        on_delete=models.CASCADE,
        related_name="movements",
    )
    moved_at = models.DateField("Дата перемещения", default=timezone.localdate)
    from_section = models.ForeignKey(
        Section,
        verbose_name="Из секции",
        on_delete=models.PROTECT,
        related_name="movements_from",
    )
    to_section = models.ForeignKey(
        Section,
        verbose_name="В секцию",
        on_delete=models.PROTECT,
        related_name="movements_to",
    )
    note = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        ordering = ["-moved_at", "-id"]

    def __str__(self) -> str:
        return f"{self.bull.external_id}: {self.from_section} -> {self.to_section}"


class DepartureEvent(models.Model):
    """
    Выбытие быка с площадки.

    Маркер выбытия нужен для статистики: сколько выбыло планово,
    сколько по срочной отправке.
    """

    REASON_CHOICES = (
        ("MEAT_PLANNED", "Планово на мясокомбинат"),
        ("EMERGENCY_SLAUGHTER", "Срочно на убой"),
        ("OTHER", "Другое"),
    )

    bull = models.OneToOneField(
        Bull,
        verbose_name="Бык",
        on_delete=models.CASCADE,
        related_name="departure",
    )
    departed_at = models.DateField("Дата выбытия", default=timezone.localdate)
    departure_weight_kg = models.DecimalField(
        "Вес на дату выбытия, кг",
        max_digits=7,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    reason = models.CharField("Маркер выбытия", max_length=32, choices=REASON_CHOICES)
    comment = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        ordering = ["-departed_at", "-id"]

    def __str__(self) -> str:
        return f"{self.bull.external_id}: {self.get_reason_display()}"


class BullHealthRecord(models.Model):
    """
    Запись о здоровье быка и проведенном лечении.

    Нужна для фиксации симптомов, уколов и динамики состояния животного.
    """

    bull = models.ForeignKey(
        Bull,
        verbose_name="Бык",
        on_delete=models.CASCADE,
        related_name="health_records",
    )
    record_date = models.DateField("Дата записи", default=timezone.localdate)
    status_text = models.CharField("Состояние", max_length=255)
    treatment_text = models.CharField("Лечение/уколы", max_length=255, blank=True)
    comment = models.CharField("Комментарий", max_length=255, blank=True)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["-record_date", "-id"]

    def __str__(self) -> str:
        return f"{self.bull.external_id}: {self.record_date} - {self.status_text}"


class ExcelImportBatch(models.Model):
    """
    Пакет импорта Excel.

    Один пакет соответствует одной загруженной таблице с двумя колонками веса:
    - прошлое взвешивание;
    - текущее взвешивание.
    """

    created_at = models.DateTimeField("Загружено", auto_now_add=True)
    previous_weighing_date = models.DateField("Дата предыдущего взвешивания")
    current_weighing_date = models.DateField("Дата текущего взвешивания")
    total_rows = models.PositiveIntegerField("Строк в файле", default=0)
    applied_rows = models.PositiveIntegerField("Применено строк", default=0)
    pending_rows = models.PositiveIntegerField("Требуют сопоставления", default=0)

    def __str__(self) -> str:
        return f"Импорт #{self.pk} от {self.created_at:%d.%m.%Y %H:%M}"


class ExcelImportPendingRow(models.Model):
    """
    Строка импорта, где не найден номер быка.

    Админ выбирает корректный номер из предложенных похожих значений,
    после чего строка может быть применена.
    """

    batch = models.ForeignKey(
        ExcelImportBatch,
        verbose_name="Пакет импорта",
        on_delete=models.CASCADE,
        related_name="pending_items",
    )
    raw_external_id = models.CharField("Номер из файла", max_length=32)
    previous_weight_kg = models.DecimalField("Предыдущий вес, кг", max_digits=7, decimal_places=2)
    current_weight_kg = models.DecimalField("Текущий вес, кг", max_digits=7, decimal_places=2)
    suggested_ids = models.JSONField(
        "Похожие номера",
        default=list,
        help_text="Список предложенных системой совпадений.",
    )
    is_resolved = models.BooleanField("Сопоставлено", default=False)
    resolved_to = models.ForeignKey(
        Bull,
        verbose_name="Выбранный бык",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_import_rows",
    )
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        ordering = ["is_resolved", "id"]

    def __str__(self) -> str:
        return f"Проблемная строка {self.raw_external_id} (импорт #{self.batch_id})"
