"""
Формы интерфейса для CRUD-операций и импорта данных.
"""

from django import forms

from .models import Bull, BullHealthRecord, DepartureEvent, SectionMovement


class ExcelImportForm(forms.Form):
    """
    Форма загрузки Excel-файла с весами.

    По промту даты находятся прямо в заголовках колонок Excel:
    - A: полный номер быка;
    - B, C, D ...: даты взвешиваний;
    - строки ниже: веса конкретного быка на эти даты.
    """

    excel_file = forms.FileField(label="Файл Excel (.xlsx)")


class ArrivalForm(forms.Form):
    """
    Форма поступления нового быка на площадку.

    Номер вводится полностью: первые 8 символов станут "бивайкой",
    последние 6 символов - рабочим номером быка.
    """

    external_id = forms.CharField(label="Полный номер быка", max_length=32)
    arrived_at = forms.DateField(label="Дата поступления")
    section = forms.ModelChoiceField(queryset=None, label="Секция поступления")
    arrival_weight_kg = forms.DecimalField(
        label="Вес при поступлении, кг",
        max_digits=7,
        decimal_places=2,
        min_value=0,
        required=False,
    )
    comment = forms.CharField(label="Комментарий", required=False)

    def __init__(self, *args, **kwargs):
        from .models import Section

        super().__init__(*args, **kwargs)
        self.fields["section"].queryset = Section.objects.order_by("side", "order")

    def clean_external_id(self):
        external_id = (self.cleaned_data["external_id"] or "").strip()
        if Bull.objects.filter(external_id=external_id).exists():
            raise forms.ValidationError("Бык с таким номером уже есть в базе.")
        return external_id


class ResolveImportRowForm(forms.Form):
    """
    Форма сопоставления проблемной строки импорта с существующим быком.
    """

    selected_bull = forms.ModelChoiceField(
        queryset=Bull.objects.none(),
        label="Выберите правильный номер быка",
    )


class ManualWeightForm(forms.Form):
    """
    Ручной ввод одного результата взвешивания.
    """

    bull = forms.ModelChoiceField(queryset=Bull.objects.none(), label="Бык")
    weighing_date = forms.DateField(label="Дата взвешивания")
    weight_kg = forms.DecimalField(label="Вес, кг", max_digits=7, decimal_places=2, min_value=0)
    note = forms.CharField(label="Комментарий", required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bull"].queryset = Bull.objects.filter(is_active=True)


class MovementForm(forms.ModelForm):
    """
    Форма перемещения быка между секциями.
    """

    class Meta:
        model = SectionMovement
        fields = ["bull", "moved_at", "from_section", "to_section", "note"]


class DepartureForm(forms.ModelForm):
    """
    Форма фиксации выбытия быка с площадки.
    """

    class Meta:
        model = DepartureEvent
        fields = ["bull", "departed_at", "departure_weight_kg", "reason", "comment"]


class PendingRowCreateBullForm(forms.Form):
    """
    Форма создания нового быка из проблемной строки импорта.

    Используется, когда номер в Excel не найден в базе и пользователь
    понимает, что это не опечатка, а реально новый бык.
    """

    arrived_at = forms.DateField(label="Дата поступления")
    section = forms.ModelChoiceField(queryset=None, label="Секция поступления")
    comment = forms.CharField(label="Комментарий", required=False)

    def __init__(self, *args, **kwargs):
        from .models import Section

        super().__init__(*args, **kwargs)
        self.fields["section"].queryset = Section.objects.order_by("side", "order")


class BullHealthRecordForm(forms.ModelForm):
    """
    Форма добавления записи о состоянии/лечении в карточке быка.
    """

    class Meta:
        model = BullHealthRecord
        fields = ["record_date", "status_text", "treatment_text", "comment"]
