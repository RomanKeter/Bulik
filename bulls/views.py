"""Views for bull yard web interface.

The views are intentionally explicit and verbose to serve as learning material.
"""

from datetime import datetime

from django.contrib import messages
from django.db.models import OuterRef, Subquery
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .forms import (
    BullSearchForm,
    BulkSectionTransferForm,
    DepartureForm,
    ExcelImportForm,
    HealthRecordForm,
    ResolveImportIssueForm,
    WeightRecordForm,
)
from .models import Bull, ImportIssue, WeightRecord
from .services import (
    apply_bulk_section_transfer,
    build_bulls_ranking,
    calculate_bull_days,
    default_report_period,
    import_weights_from_excel,
    resolve_import_issue,
    section_summary_snapshot,
)


def dashboard_view(request):
    """Shows key metrics useful for daily operational control."""
    sections_summary = section_summary_snapshot()
    active_bulls_count = Bull.objects.filter(status=Bull.Status.ACTIVE).count()
    departed_bulls_count = Bull.objects.filter(status=Bull.Status.DEPARTED).count()
    context = {
        "active_bulls_count": active_bulls_count,
        "departed_bulls_count": departed_bulls_count,
        "sections_summary": sections_summary,
    }
    return render(request, "bulls/dashboard.html", context)


def bull_list_view(request):
    """List page with search and weight sorting.

    Sorting by current weight is implemented via subquery to the latest record.
    """
    latest_weight_subquery = WeightRecord.objects.filter(bull=OuterRef("pk")).order_by("-weighing_date")
    bulls_qs = Bull.objects.filter(status=Bull.Status.ACTIVE).select_related("current_section").annotate(
        latest_weight_kg=Subquery(latest_weight_subquery.values("weight_kg")[:1])
    )

    form = BullSearchForm(request.GET or None)
    if form.is_valid():
        query = form.cleaned_data.get("query")
        section = form.cleaned_data.get("section")
        sort_weight = form.cleaned_data.get("sort_weight")
        if query:
            bulls_qs = bulls_qs.filter(bull_number__icontains=query.strip())
        if section:
            bulls_qs = bulls_qs.filter(current_section=section)
        if sort_weight == "asc":
            bulls_qs = bulls_qs.order_by("latest_weight_kg", "bull_number")
        elif sort_weight == "desc":
            bulls_qs = bulls_qs.order_by("-latest_weight_kg", "bull_number")
        else:
            bulls_qs = bulls_qs.order_by("bull_number")

    date_headers = list(
        WeightRecord.objects.values_list("weighing_date", flat=True).distinct().order_by("-weighing_date")[:6]
    )
    date_headers = list(reversed(date_headers))

    bulls = list(bulls_qs)
    bulls_table_rows = []
    for bull in bulls:
        weight_by_date = {
            record.weighing_date: record.weight_kg
            for record in bull.weight_records.filter(weighing_date__in=date_headers)
        }
        bulls_table_rows.append(
            {
                "bull": bull,
                "weights": [weight_by_date.get(weighing_date) for weighing_date in date_headers],
            }
        )

    context = {
        "form": form,
        "bulls_table_rows": bulls_table_rows,
        "date_headers": date_headers,
    }
    return render(request, "bulls/bull_list.html", context)


def bull_detail_view(request, bull_id: int):
    """Card page with history, health records and manual forms."""
    bull = get_object_or_404(Bull.objects.select_related("current_section"), pk=bull_id)
    weight_form = WeightRecordForm(initial={"weighing_date": timezone.localdate()})
    health_form = HealthRecordForm(initial={"record_date": timezone.localdate()})
    departure_form = DepartureForm(initial={"departure_date": timezone.localdate()})

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_weight":
            weight_form = WeightRecordForm(request.POST)
            if weight_form.is_valid():
                record = weight_form.save(commit=False)
                record.bull = bull
                record.source = WeightRecord.Source.MANUAL
                record.save()
                messages.success(request, "Запись о взвешивании сохранена.")
                return redirect("bulls:bull_detail", bull_id=bull.id)
        elif action == "add_health":
            health_form = HealthRecordForm(request.POST)
            if health_form.is_valid():
                record = health_form.save(commit=False)
                record.bull = bull
                record.save()
                messages.success(request, "Запись о здоровье добавлена.")
                return redirect("bulls:bull_detail", bull_id=bull.id)
        elif action == "mark_departure":
            departure_form = DepartureForm(request.POST)
            if departure_form.is_valid():
                departure = departure_form.save(commit=False)
                departure.bull = bull
                departure.save()
                bull.status = Bull.Status.DEPARTED
                bull.current_section = None
                bull.save(update_fields=["status", "current_section", "updated_at"])
                messages.success(request, "Бык отмечен как выбывший.")
                return redirect("bulls:bull_detail", bull_id=bull.id)

    context = {
        "bull": bull,
        "weights": bull.weight_records.all(),
        "health_records": bull.health_records.all(),
        "weight_form": weight_form,
        "health_form": health_form,
        "departure_form": departure_form,
    }
    return render(request, "bulls/bull_detail.html", context)


def excel_import_view(request):
    """Upload and process Excel file with wide weighing table."""
    form = ExcelImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        form = ExcelImportForm(request.POST, request.FILES)
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            messages.error(request, "Файл не выбран. Нажмите 'Выберите файл' и загрузите Excel.")
            return redirect("bulls:excel_import")
        if not form.is_valid():
            messages.error(request, "Проверьте заполнение формы импорта.")
            return redirect("bulls:excel_import")
        try:
            session = import_weights_from_excel(
                uploaded_file,
                manual_dates=form.cleaned_data.get("manual_dates", ""),
                auto_create_missing_bulls=form.cleaned_data.get("auto_create_missing_bulls", True),
            )
            messages.success(
                request,
                (
                    "Импорт завершен: "
                    f"обработано {session.processed_rows}, "
                    f"создано {session.created_records}, "
                    f"обновлено {session.updated_records}, "
                    f"проблемных строк {session.unresolved_rows}."
                ),
            )
        except ValueError as error:
            messages.error(request, str(error))
        except Exception:
            messages.error(
                request,
                "Не удалось прочитать файл. Проверьте, что это Excel и что файл не поврежден.",
            )
        return redirect("bulls:excel_import")

    unresolved_issues = ImportIssue.objects.filter(resolved_bull__isnull=True).select_related("session")[:200]
    issue_forms = []
    for issue in unresolved_issues:
        suggested_bulls = Bull.objects.filter(full_code__in=issue.suggested_full_codes)
        issue_forms.append((issue, ResolveImportIssueForm(bulls_queryset=suggested_bulls)))

    return render(
        request,
        "bulls/excel_import.html",
        {"form": form, "issue_forms": issue_forms},
    )


def bulk_transfer_view(request):
    """Handles checkbox-based mass transfer to another section."""
    selected_ids = request.POST.getlist("selected_bulls") or request.GET.getlist("selected_bulls")
    form = BulkSectionTransferForm(request.POST or None, bull_ids=selected_ids)
    if request.method == "POST" and form.is_valid():
        bull_ids = [int(value) for value in form.cleaned_data["bull_ids"]]
        bulls = list(Bull.objects.filter(id__in=bull_ids).select_related("current_section"))
        try:
            moved = apply_bulk_section_transfer(
                bulls=bulls,
                target_section=form.cleaned_data["target_section"],
                transfer_date=form.cleaned_data["transfer_date"],
                comment=form.cleaned_data["comment"],
            )
        except ValueError as error:
            messages.error(request, str(error))
            return redirect("bulls:bulk_transfer")
        messages.success(request, f"Переведено быков: {moved}.")
        return redirect("bulls:bull_list")
    return render(request, "bulls/bulk_transfer.html", {"form": form, "selected_ids": selected_ids})


def reports_view(request):
    """Shows rankings and bull-day metrics for selected period."""
    default_start, default_end = default_report_period()
    start_raw = request.GET.get("start_date")
    end_raw = request.GET.get("end_date")
    try:
        period_start = datetime.strptime(start_raw, "%Y-%m-%d").date() if start_raw else default_start
    except ValueError:
        period_start = default_start
    try:
        period_end = datetime.strptime(end_raw, "%Y-%m-%d").date() if end_raw else default_end
    except ValueError:
        period_end = default_end
    if period_end < period_start:
        period_start, period_end = period_end, period_start

    ranking = build_bulls_ranking(period_start=period_start, period_end=period_end)
    bull_days = calculate_bull_days(period_start=period_start, period_end=period_end)
    context = {
        "period_start": period_start,
        "period_end": period_end,
        "ranking": ranking,
        "bull_days": bull_days,
    }
    return render(request, "bulls/reports.html", context)


def reports_export_excel_view(request):
    """Exports a simple period ranking report to XLSX."""
    from openpyxl import Workbook

    default_start, default_end = default_report_period()
    period_start = default_start
    period_end = default_end
    ranking = build_bulls_ranking(period_start=period_start, period_end=period_end)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Рейтинг привеса"
    worksheet.append(["Категория", "Бивайка", "Номер", "Привес кг", "Среднесуточный кг/день"])
    for category, rows in ranking.items():
        for row in rows:
            worksheet.append(
                [
                    category,
                    row["bull"].bivayka,
                    row["bull"].bull_number,
                    row["gain_kg"],
                    round(row["daily_gain"], 3),
                ]
            )

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="ranking_report.xlsx"'
    workbook.save(response)
    return response


def reports_export_pdf_view(request):
    """Exports compact PDF summary suitable for quick print."""
    default_start, default_end = default_report_period()
    ranking = build_bulls_ranking(period_start=default_start, period_end=default_end)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="summary_report.pdf"'
    pdf = canvas.Canvas(response, pagesize=A4)
    pdf.setTitle("Сводный отчет")
    y = 800
    pdf.drawString(40, y, "Сводный отчет по привесу")
    y -= 20
    pdf.drawString(40, y, f"Период: {default_start:%d.%m.%Y} - {default_end:%d.%m.%Y}")
    y -= 30
    pdf.drawString(40, y, "Лучшие по среднесуточному привесу:")
    y -= 20
    for row in ranking["strongest_by_daily_gain"][:10]:
        pdf.drawString(
            50,
            y,
            f"{row['bull'].bivayka}-{row['bull'].bull_number}: {row['daily_gain']:.3f} кг/день",
        )
        y -= 16
        if y < 80:
            pdf.showPage()
            y = 800
    pdf.save()
    return response


def resolve_import_issue_view(request, issue_id: int):
    """Handles admin choice when fixing an unknown Excel number."""
    issue = get_object_or_404(ImportIssue, pk=issue_id, resolved_bull__isnull=True)
    suggested_bulls = Bull.objects.filter(full_code__in=issue.suggested_full_codes)
    form = ResolveImportIssueForm(request.POST or None, bulls_queryset=suggested_bulls)
    if request.method == "POST" and form.is_valid():
        resolve_import_issue(issue, form.cleaned_data["selected_bull"])
        messages.success(request, f"Проблема по номеру {issue.incoming_full_code} решена.")
    else:
        messages.error(request, "Не удалось применить исправление. Проверьте выбранного быка.")
    return redirect("bulls:excel_import")
