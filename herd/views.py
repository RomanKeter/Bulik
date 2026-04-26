"""
Представления (страницы) пользовательского интерфейса.
"""

from django.contrib import messages
from django.db.models import DecimalField, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from .forms import (
    ArrivalForm,
    BullHealthRecordForm,
    DepartureForm,
    ExcelImportForm,
    ManualWeightForm,
    MovementForm,
    PendingRowCreateBullForm,
    ResolveImportRowForm,
)
from .models import ArrivalEvent, Bull, ExcelImportBatch, ExcelImportPendingRow, WeightRecord
from .services import (
    build_dashboard_stats,
    build_growth_rating,
    create_bull_from_pending_row,
    import_weights_excel,
    resolve_pending_row,
)


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
        search_query = (request.GET.get("q") or "").strip()
        sort_weight = (request.GET.get("sort_weight") or "").strip()

        latest_weight_sq = WeightRecord.objects.filter(bull=OuterRef("pk")).order_by("-weighing_date", "-id")
        bulls = Bull.objects.select_related("section").annotate(
            latest_weight=Subquery(
                latest_weight_sq.values("weight_kg")[:1],
                output_field=DecimalField(max_digits=7, decimal_places=2),
            )
        )

        if search_query:
            bulls = bulls.filter(
                Q(bull_number__icontains=search_query)
                | Q(biavka_part__icontains=search_query)
                | Q(external_id__icontains=search_query)
            )

        if sort_weight == "asc":
            bulls = bulls.order_by("latest_weight", "bull_number")
        elif sort_weight == "desc":
            bulls = bulls.order_by("-latest_weight", "bull_number")
        else:
            bulls = bulls.order_by("bull_number")

        return render(
            request,
            self.template_name,
            {"bulls": bulls, "search_query": search_query, "sort_weight": sort_weight},
        )


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
                "arrival": getattr(bull, "arrival", None),
                "departure": getattr(bull, "departure", None),
                "health_records": bull.health_records.order_by("-record_date", "-id"),
                "health_form": BullHealthRecordForm(),
            },
        )

    def post(self, request, bull_id):
        bull = get_object_or_404(Bull.objects.select_related("section"), pk=bull_id)
        form = BullHealthRecordForm(request.POST)
        if form.is_valid():
            rec = form.save(commit=False)
            rec.bull = bull
            rec.save()
            messages.success(request, "Запись о здоровье сохранена.")
            return redirect("herd:bull-detail", bull_id=bull_id)

        return render(
            request,
            self.template_name,
            {
                "bull": bull,
                "weights": bull.weight_records.order_by("-weighing_date"),
                "movements": bull.movements.select_related("from_section", "to_section").order_by("-moved_at"),
                "arrival": getattr(bull, "arrival", None),
                "departure": getattr(bull, "departure", None),
                "health_records": bull.health_records.order_by("-record_date", "-id"),
                "health_form": form,
            },
        )


class ImportExcelView(View):
    """
    Загрузка Excel и создание пакета импорта.
    """

    template_name = "herd/import_excel.html"

    def get(self, request):
        recent_batches = ExcelImportBatch.objects.order_by("-created_at")[:10]
        return render(request, self.template_name, {"form": ExcelImportForm(), "recent_batches": recent_batches})

    def post(self, request):
        form = ExcelImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                result = import_weights_excel(file_obj=form.cleaned_data["excel_file"])
            except ValueError as exc:
                messages.error(request, str(exc))
                recent_batches = ExcelImportBatch.objects.order_by("-created_at")[:10]
                return render(request, self.template_name, {"form": form, "recent_batches": recent_batches})

            messages.success(
                request,
                f"Импорт завершен: применено {result.applied_rows}, требуют проверки {result.pending_rows}.",
            )
            return redirect("herd:import-batch-detail", batch_id=result.batch.id)

        recent_batches = ExcelImportBatch.objects.order_by("-created_at")[:10]
        return render(request, self.template_name, {"form": form, "recent_batches": recent_batches})


class ImportHistoryView(View):
    """
    История загруженных пакетов Excel.
    """

    template_name = "herd/import_history.html"

    def get(self, request):
        batches = ExcelImportBatch.objects.order_by("-created_at")
        return render(request, self.template_name, {"batches": batches})


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
        create_form = PendingRowCreateBullForm()
        if row.suggested_ids:
            form.fields["selected_bull"].queryset = Bull.objects.filter(external_id__in=row.suggested_ids)
        else:
            form.fields["selected_bull"].queryset = Bull.objects.filter(is_active=True)
        return render(request, self.template_name, {"row": row, "form": form, "create_form": create_form})

    def post(self, request, row_id):
        row = get_object_or_404(ExcelImportPendingRow, pk=row_id)
        form = ResolveImportRowForm(request.POST)
        form.fields["selected_bull"].queryset = Bull.objects.all()
        if form.is_valid():
            resolve_pending_row(row, form.cleaned_data["selected_bull"])
            messages.success(request, "Строка успешно сопоставлена и применена.")
            return redirect("herd:import-batch-detail", batch_id=row.batch_id)
        create_form = PendingRowCreateBullForm()
        return render(request, self.template_name, {"row": row, "form": form, "create_form": create_form})


class CreateBullFromPendingRowView(View):
    """
    Создание нового быка из неизвестного номера Excel.

    Это отдельное действие нужно потому, что по промту неизвестный номер
    сначала должен привлечь внимание пользователя, а не создаваться молча.
    """

    def post(self, request, row_id):
        row = get_object_or_404(ExcelImportPendingRow, pk=row_id)
        form = PendingRowCreateBullForm(request.POST)
        if form.is_valid():
            bull = create_bull_from_pending_row(
                pending_row=row,
                arrived_at=form.cleaned_data["arrived_at"],
                section=form.cleaned_data["section"],
                comment=form.cleaned_data["comment"],
            )
            messages.success(request, f"Создан новый бык {bull.bull_number} из строки импорта.")
            return redirect("herd:bull-detail", bull_id=bull.id)

        resolve_form = ResolveImportRowForm()
        resolve_form.fields["selected_bull"].queryset = Bull.objects.all()
        return render(request, "herd/resolve_pending_row.html", {"row": row, "form": resolve_form, "create_form": form})


class ArrivalCreateView(View):
    """
    Ручная регистрация поступления нового быка на площадку.
    """

    template_name = "herd/arrival_form.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ArrivalForm()})

    def post(self, request):
        form = ArrivalForm(request.POST)
        if form.is_valid():
            section = form.cleaned_data["section"]
            bull = Bull.objects.create(external_id=form.cleaned_data["external_id"], section=section)
            ArrivalEvent.objects.create(
                bull=bull,
                arrived_at=form.cleaned_data["arrived_at"],
                section=section,
                arrival_weight_kg=form.cleaned_data["arrival_weight_kg"],
                comment=form.cleaned_data["comment"],
            )
            if form.cleaned_data["arrival_weight_kg"] is not None:
                WeightRecord.objects.create(
                    bull=bull,
                    weighing_date=form.cleaned_data["arrived_at"],
                    weight_kg=form.cleaned_data["arrival_weight_kg"],
                    source="manual",
                    note="Вес при поступлении",
                )
            messages.success(request, "Поступление быка зарегистрировано.")
            return redirect("herd:bull-detail", bull_id=bull.id)
        return render(request, self.template_name, {"form": form})


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
