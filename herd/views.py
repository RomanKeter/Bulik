"""
Представления (страницы) пользовательского интерфейса.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .forms import DepartureForm, ExcelImportForm, ManualWeightForm, MovementForm, ResolveImportRowForm
from .models import Bull, ExcelImportBatch, ExcelImportPendingRow, WeightRecord
from .services import build_dashboard_stats, build_growth_rating, import_weights_excel, resolve_pending_row


class DashboardView(View):
    """
    Главная страница с оперативной сводкой и рейтингами привеса.
    """

    template_name = "herd/dashboard.html"

    def get(self, request):
        context = {
            "stats": build_dashboard_stats(),
            "rating": build_growth_rating(),
        }
        return render(request, self.template_name, context)


class BullListView(View):
    """
    Список быков с текущими данными.
    """

    template_name = "herd/bull_list.html"

    def get(self, request):
        bulls = Bull.objects.select_related("section").order_by("bull_number")
        return render(request, self.template_name, {"bulls": bulls})


class BullDetailView(View):
    """
    Карточка быка с историей взвешиваний и перемещений.
    """

    template_name = "herd/bull_detail.html"

    def get(self, request, bull_id):
        bull = get_object_or_404(Bull.objects.select_related("section"), pk=bull_id)
        return render(
            request,
            self.template_name,
            {
                "bull": bull,
                "weights": bull.weight_records.order_by("-weighing_date"),
                "movements": bull.movements.select_related("from_section", "to_section").order_by("-moved_at"),
                "departure": getattr(bull, "departure", None),
            },
        )


class ImportExcelView(View):
    """
    Загрузка Excel и создание пакета импорта.
    """

    template_name = "herd/import_excel.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ExcelImportForm()})

    def post(self, request):
        form = ExcelImportForm(request.POST, request.FILES)
        if form.is_valid():
            result = import_weights_excel(
                file_obj=form.cleaned_data["excel_file"],
                previous_date=form.cleaned_data["previous_weighing_date"],
                current_date=form.cleaned_data["current_weighing_date"],
            )
            messages.success(
                request,
                f"Импорт завершен: применено {result.applied_rows}, требуют проверки {result.pending_rows}.",
            )
            return redirect("herd:import-batch-detail", batch_id=result.batch.id)

        return render(request, self.template_name, {"form": form})


class ImportBatchDetailView(View):
    """
    Детальная страница пакета импорта с проблемными строками.
    """

    template_name = "herd/import_batch_detail.html"

    def get(self, request, batch_id):
        batch = get_object_or_404(ExcelImportBatch, pk=batch_id)
        unresolved_qs = ExcelImportPendingRow.objects.filter(batch=batch, is_resolved=False).order_by("id")
        return render(
            request,
            self.template_name,
            {
                "batch": batch,
                "unresolved_qs": unresolved_qs,
            },
        )


class ResolveImportRowView(View):
    """
    Ручное сопоставление неизвестного номера с существующим быком.
    """

    template_name = "herd/resolve_pending_row.html"

    def get(self, request, row_id):
        row = get_object_or_404(ExcelImportPendingRow, pk=row_id)
        form = ResolveImportRowForm()
        if row.suggested_ids:
            form.fields["selected_bull"].queryset = Bull.objects.filter(external_id__in=row.suggested_ids)
        else:
            form.fields["selected_bull"].queryset = Bull.objects.filter(is_active=True)
        return render(request, self.template_name, {"row": row, "form": form})

    def post(self, request, row_id):
        row = get_object_or_404(ExcelImportPendingRow, pk=row_id)
        form = ResolveImportRowForm(request.POST)
        form.fields["selected_bull"].queryset = Bull.objects.all()
        if form.is_valid():
            resolve_pending_row(row, form.cleaned_data["selected_bull"])
            messages.success(request, "Строка успешно сопоставлена и применена.")
            return redirect("herd:import-batch-detail", batch_id=row.batch_id)
        return render(request, self.template_name, {"row": row, "form": form})


class ManualWeightCreateView(View):
    """
    Ручной ввод веса для одного быка.
    """

    template_name = "herd/manual_weight.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ManualWeightForm()})

    def post(self, request):
        form = ManualWeightForm(request.POST)
        if form.is_valid():
            WeightRecord.objects.create(
                bull=form.cleaned_data["bull"],
                weighing_date=form.cleaned_data["weighing_date"],
                weight_kg=form.cleaned_data["weight_kg"],
                source="manual",
                note=form.cleaned_data["note"],
            )
            messages.success(request, "Ручная перевеска сохранена.")
            return redirect("herd:bull-detail", bull_id=form.cleaned_data["bull"].id)
        return render(request, self.template_name, {"form": form})


class MovementCreateView(View):
    """
    Ввод события перемещения между секциями.
    """

    template_name = "herd/movement_form.html"

    def get(self, request):
        return render(request, self.template_name, {"form": MovementForm()})

    def post(self, request):
        form = MovementForm(request.POST)
        if form.is_valid():
            movement = form.save()
            bull = movement.bull
            bull.section = movement.to_section
            bull.save(update_fields=["section", "updated_at"])
            messages.success(request, "Перемещение сохранено.")
            return redirect("herd:bull-detail", bull_id=bull.id)
        return render(request, self.template_name, {"form": form})


class DepartureCreateView(View):
    """
    Фиксация выбытия быка с указанием причины (маркера).
    """

    template_name = "herd/departure_form.html"

    def get(self, request):
        form = DepartureForm()
        form.fields["bull"].queryset = Bull.objects.filter(is_active=True)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        form = DepartureForm(request.POST)
        form.fields["bull"].queryset = Bull.objects.filter(is_active=True)
        if form.is_valid():
            departure = form.save()
            departure.bull.is_active = False
            departure.bull.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Выбытие зарегистрировано.")
            return redirect("herd:bull-detail", bull_id=departure.bull_id)
        return render(request, self.template_name, {"form": form})
