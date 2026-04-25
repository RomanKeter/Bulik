"""
Формы интерфейса для CRUD-операций и импорта данных.
"""

from django import forms

from .models import Bull, BullHealthRecord, DepartureEvent, SectionMovement


class ExcelImportForm(forms.Form):
    """
    Форма загрузки Excel-файла с двумя колонками веса.

    Поля даты задаются явно, потому что в вашем рабочем файле обычно
    присутствуют только значения веса (без дат внутри таблицы).
    """

    excel_file = forms.FileField(label="Файл Excel (.xlsx)")
    previous_weighing_date = forms.DateField(label="Дата прошлого взвешивания")
    current_weighing_date = forms.DateField(label="Дата текущего взвешивания")


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


class BullHealthRecordForm(forms.ModelForm):
    """
    Форма добавления записи о состоянии/лечении в карточке быка.
    """

    class Meta:
        model = BullHealthRecord
        fields = ["record_date", "status_text", "treatment_text", "comment"]
