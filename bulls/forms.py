"""Forms for interactive data input in the web interface.

The forms layer keeps validation close to user input and provides clear error
messages for educational purposes.
"""

from django import forms
from django.utils import timezone

from .models import Bull, DepartureRecord, HealthRecord, Section, WeightRecord


class BullSearchForm(forms.Form):
    """Search form for quick lookup by 6-digit bull number."""

    query = forms.CharField(
        label="Номер быка",
        max_length=6,
        required=False,
        help_text="Введите 6 символов номера быка.",
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.all(),
        label="Секция",
        required=False,
        empty_label="Все секции",
    )
    sort_weight = forms.ChoiceField(
        label="Сортировка по весу",
        required=False,
        choices=(
            ("", "Без сортировки"),
            ("asc", "Вес по возрастанию"),
            ("desc", "Вес по убыванию"),
        ),
    )


class WeightRecordForm(forms.ModelForm):
    """Manual input form to add or correct one weighing."""

    class Meta:
        model = WeightRecord
        fields = ("weighing_date", "weight_kg", "comment")
        widgets = {
            "weighing_date": forms.DateInput(attrs={"type": "date"}),
        }


class ExcelImportForm(forms.Form):
    """Upload form for wide-format Excel file.

    Supported formats:
    1) Header format:
       - A: "бивайка"
       - B: "номер быка"
       - C, D, E...: dates of weighing (dd.mm.yyyy)
    2) Compact format (as in user screenshot):
       - A: full code (8 + 6 symbols)
       - B, C, D...: integer weights
       - dates are entered manually in the form.
    """

    file = forms.FileField(label="Excel файл", required=False)
    manual_dates = forms.CharField(
        label="Даты для колонок веса (для формата без заголовков)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "01.04.2026, 28.04.2026"}),
        help_text=(
            "Если в файле только полный номер в колонке A, а в B/C/D... только веса, "
            "можно указать даты через запятую в порядке колонок: B, C, D... "
            "Если оставить пустым, система подставит даты автоматически."
        ),
    )
    auto_create_missing_bulls = forms.BooleanField(
        label="Автоматически создавать новых быков, если номер не найден",
        required=False,
        initial=True,
        help_text=(
            "Включено: новые номера из файла сразу добавляются в базу как активные быки. "
            "Выключено: неизвестные номера попадают в список проблем импорта."
        ),
    )


class BulkSectionTransferForm(forms.Form):
    """Mass transfer form used from bulls list with checkboxes."""

    bull_ids = forms.MultipleChoiceField(
        required=True,
        widget=forms.MultipleHiddenInput,
    )
    target_section = forms.ModelChoiceField(
        queryset=Section.objects.all(),
        label="Новая секция",
    )
    transfer_date = forms.DateField(
        label="Дата перевода",
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    comment = forms.CharField(
        label="Комментарий",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        """Populates choices dynamically from incoming checkbox values."""
        bull_ids = kwargs.pop("bull_ids", [])
        super().__init__(*args, **kwargs)
        choices = [(str(bull_id), str(bull_id)) for bull_id in bull_ids]
        self.fields["bull_ids"].choices = choices


class HealthRecordForm(forms.ModelForm):
    """Form for treatment and health status notes in bull card."""

    class Meta:
        model = HealthRecord
        fields = ("record_date", "record_type", "description", "resolved")
        widgets = {
            "record_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }


class DepartureForm(forms.ModelForm):
    """Form to mark a bull as departed with marker and weight."""

    class Meta:
        model = DepartureRecord
        fields = ("departure_date", "weight_kg", "marker", "comment")
        widgets = {
            "departure_date": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.Textarea(attrs={"rows": 2}),
        }


class ResolveImportIssueForm(forms.Form):
    """Form to resolve one import issue by selecting real bull.

    We keep this form dynamic because suggested options differ per issue.
    """

    selected_bull = forms.ModelChoiceField(queryset=Bull.objects.none(), label="Правильный бык")

    def __init__(self, *args, **kwargs):
        """Injects queryset from view to match suggested numbers."""
        bulls_queryset = kwargs.pop("bulls_queryset")
        super().__init__(*args, **kwargs)
        self.fields["selected_bull"].queryset = bulls_queryset

