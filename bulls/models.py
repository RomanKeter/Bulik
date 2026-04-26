"""Models for bull yard accounting domain.

The project is intentionally educational, so every model has a verbose docstring
that explains:
- why the model exists;
- what business rule it stores;
- how it is expected to be used in views and reports.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Section(models.Model):
    """Represents one physical section (pen) in the yard.

    Business context:
    - There are exactly 8 sections.
    - Sections are arranged as two rows: 4 on the left and 4 on the right.
    - A section can contain up to 150 bulls.

    We store side and position to reflect the real layout. It is useful for
    future UI plans, for example drawing a scheme of the yard.
    """

    class Side(models.TextChoices):
        """Allowed side values to avoid typo-like data errors."""

        LEFT = "LEFT", "Левая сторона"
        RIGHT = "RIGHT", "Правая сторона"

    number = models.PositiveSmallIntegerField(unique=True)
    side = models.CharField(max_length=5, choices=Side.choices)
    position_in_row = models.PositiveSmallIntegerField()
    capacity = models.PositiveIntegerField(default=150)

    class Meta:
        ordering = ["number"]
        verbose_name = "Секция"
        verbose_name_plural = "Секции"

    def __str__(self) -> str:
        """Human-friendly representation used in dropdowns and admin."""
        return f"Секция {self.number}"


class Bull(models.Model):
    """Main entity representing a single bull tracked forever by number.

    Identification rules from requirements:
    - Full number is made from `bivayka` (8 chars) + `bull_number` (6 chars).
    - Pair (`bivayka`, `bull_number`) is unique forever.
    - No registration/user ownership logic is required.

    We keep denormalized `full_code` because:
    - it simplifies quick search;
    - it helps with import diagnostics;
    - it preserves exact incoming code style.
    """

    class Status(models.TextChoices):
        """Current lifecycle state of the bull on the yard."""

        ACTIVE = "ACTIVE", "На площадке"
        DEPARTED = "DEPARTED", "Выбыл"

    bivayka = models.CharField(max_length=8)
    bull_number = models.CharField(max_length=6)
    full_code = models.CharField(max_length=14, unique=True, blank=True)
    current_section = models.ForeignKey(
        Section,
        on_delete=models.PROTECT,
        related_name="bulls",
        null=True,
        blank=True,
    )
    arrival_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["bull_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["bivayka", "bull_number"], name="unique_bivayka_and_bull_number"
            )
        ]
        verbose_name = "Бык"
        verbose_name_plural = "Быки"

    def __str__(self) -> str:
        """Used in admin and relation fields."""
        return f"{self.bivayka}-{self.bull_number}"

    def clean(self) -> None:
        """Validates strict length and keeps `full_code` synchronized.

        This project must be beginner-friendly and robust. Explicit validation
        gives clear errors in admin/forms instead of silent bad data.
        """
        if len(self.bivayka or "") != 8:
            raise ValidationError({"bivayka": "Бивайка должна содержать ровно 8 символов."})
        if len(self.bull_number or "") != 6:
            raise ValidationError({"bull_number": "Номер быка должен содержать ровно 6 символов."})
        self.full_code = f"{self.bivayka}{self.bull_number}"

    def save(self, *args, **kwargs):
        """Ensures validation always runs before storing a bull."""
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def latest_weight(self):
        """Returns the newest weight record object or None.

        This property is handy in templates where we want to display current
        weight without repeating ORM logic in many places.
        """
        return self.weight_records.order_by("-weighing_date").first()


class WeightRecord(models.Model):
    """Stores one weighing event for one bull at exact date.

    A bull can have many weighings. Dates are irregular (for example 27 or
    30 days interval), so we always store the exact date from input.
    """

    class Source(models.TextChoices):
        """How a record appeared in system."""

        MANUAL = "MANUAL", "Ручной ввод"
        EXCEL = "EXCEL", "Импорт Excel"

    bull = models.ForeignKey(Bull, on_delete=models.CASCADE, related_name="weight_records")
    weighing_date = models.DateField()
    weight_kg = models.PositiveIntegerField()
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-weighing_date", "bull__bull_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["bull", "weighing_date"], name="unique_bull_weighing_per_date"
            )
        ]
        verbose_name = "Запись взвешивания"
        verbose_name_plural = "Записи взвешивания"

    def __str__(self) -> str:
        """Compact representation used in admin list."""
        return f"{self.bull} / {self.weighing_date} / {self.weight_kg} кг"


class SectionTransfer(models.Model):
    """Stores movement of a bull from one section to another.

    Important requirement:
    - Transfer may happen on any date, not tied to weighing date.
    """

    bull = models.ForeignKey(Bull, on_delete=models.CASCADE, related_name="transfers")
    from_section = models.ForeignKey(
        Section, on_delete=models.PROTECT, related_name="outgoing_transfers"
    )
    to_section = models.ForeignKey(Section, on_delete=models.PROTECT, related_name="incoming_transfers")
    transfer_date = models.DateField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-transfer_date", "bull__bull_number"]
        verbose_name = "Перевод между секциями"
        verbose_name_plural = "Переводы между секциями"

    def __str__(self) -> str:
        """Readable label for admin/history."""
        return f"{self.bull} {self.from_section} -> {self.to_section} ({self.transfer_date})"

    def clean(self) -> None:
        """Blocks no-op transfers to the same section."""
        if self.from_section_id == self.to_section_id:
            raise ValidationError("Секция отправления и назначения не могут совпадать.")


class DepartureRecord(models.Model):
    """Stores final departure from the yard and departure marker.

    Marker is required by the business to differentiate statistics:
    - healthy mass departure to meat plant;
    - urgent single departure due to health problem;
    - other cases.

    We also store weight on departure date to support correct period analytics.
    """

    class Marker(models.TextChoices):
        """Controlled list of departure reasons for stable reporting."""

        MEAT_PLANT = "MEAT_PLANT", "На мясокомбинат"
        URGENT_SLAUGHTER = "URGENT_SLAUGHTER", "Срочная отправка на убой"
        OTHER = "OTHER", "Другое"

    bull = models.OneToOneField(Bull, on_delete=models.CASCADE, related_name="departure")
    departure_date = models.DateField()
    weight_kg = models.PositiveIntegerField()
    marker = models.CharField(max_length=20, choices=Marker.choices)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-departure_date", "bull__bull_number"]
        verbose_name = "Выбытие"
        verbose_name_plural = "Выбытия"

    def __str__(self) -> str:
        """Simple textual summary for admin and templates."""
        return f"{self.bull} выбыл {self.departure_date} ({self.get_marker_display()})"


class HealthRecord(models.Model):
    """Medical and health state notes linked to a bull card.

    This model supports requirement to record injections, illness notes, and
    observations that later can be viewed from any place through bull card.
    """

    class RecordType(models.TextChoices):
        """Semantic type of note for filtering and readability."""

        INJECTION = "INJECTION", "Укол"
        ILLNESS = "ILLNESS", "Болезнь"
        OBSERVATION = "OBSERVATION", "Наблюдение"

    bull = models.ForeignKey(Bull, on_delete=models.CASCADE, related_name="health_records")
    record_date = models.DateField(default=timezone.localdate)
    record_type = models.CharField(max_length=20, choices=RecordType.choices)
    description = models.TextField()
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-record_date", "-created_at"]
        verbose_name = "Запись о здоровье"
        verbose_name_plural = "Записи о здоровье"

    def __str__(self) -> str:
        """Friendly short title for list tables."""
        return f"{self.bull} / {self.get_record_type_display()} / {self.record_date}"


class ImportSession(models.Model):
    """Stores metadata about one Excel import operation.

    Keeping import sessions helps in learning/debugging:
    - how many rows were processed;
    - how many records were created/updated;
    - which issues were found.
    """

    uploaded_at = models.DateTimeField(auto_now_add=True)
    file_name = models.CharField(max_length=255)
    processed_rows = models.PositiveIntegerField(default=0)
    created_records = models.PositiveIntegerField(default=0)
    updated_records = models.PositiveIntegerField(default=0)
    unresolved_rows = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Сессия импорта"
        verbose_name_plural = "Сессии импорта"

    def __str__(self) -> str:
        """Displays file and timestamp."""
        return f"{self.file_name} ({self.uploaded_at:%d.%m.%Y %H:%M})"


class ImportIssue(models.Model):
    """Represents one unresolved row from Excel import.

    Main use case:
    - an incoming bull number is unknown;
    - system suggests similar known numbers;
    - admin selects correct number and confirms fix.
    """

    session = models.ForeignKey(ImportSession, on_delete=models.CASCADE, related_name="issues")
    incoming_bivayka = models.CharField(max_length=8)
    incoming_bull_number = models.CharField(max_length=6)
    incoming_full_code = models.CharField(max_length=14)
    weighing_date = models.DateField()
    weight_kg = models.PositiveIntegerField()
    suggested_full_codes = models.JSONField(default=list, blank=True)
    resolved_bull = models.ForeignKey(
        Bull, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_import_issues"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Проблема импорта"
        verbose_name_plural = "Проблемы импорта"

    def __str__(self) -> str:
        """Displays unresolved incoming number."""
        return f"Не найден: {self.incoming_full_code} ({self.weighing_date})"
