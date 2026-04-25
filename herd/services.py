"""
Сервисные функции для импорта Excel и расчетов отчетов.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from decimal import Decimal

from openpyxl import load_workbook

from django.db import transaction
from django.db.models import Avg, Count

from .models import Bull, ExcelImportBatch, ExcelImportPendingRow, WeightRecord


def split_external_id(external_id: str) -> tuple[str, str]:
    """
    Делит полный номер из файла на две части:
    - первые 8 символов (бивайка),
    - последние 6 символов (номер быка).
    """

    normalized = (external_id or "").strip()
    if len(normalized) < 14:
        return normalized[:8], normalized[-6:]
    return normalized[:8], normalized[-6:]


def get_similar_ids(raw_external_id: str, limit: int = 5) -> list[str]:
    """
    Возвращает список похожих номеров быков для исправления опечаток.

    Используется стандартный `difflib`, которого достаточно для учебного
    проекта и коротких строковых идентификаторов.
    """

    all_ids = list(Bull.objects.values_list("external_id", flat=True))
    if not all_ids:
        return []
    return difflib.get_close_matches(raw_external_id, all_ids, n=limit, cutoff=0.55)


@dataclass
class ImportResult:
    """
    Результат выполнения импорта Excel.
    """

    batch: ExcelImportBatch
    applied_rows: int
    pending_rows: int


@transaction.atomic
def import_weights_excel(file_obj, previous_date, current_date) -> ImportResult:
    """
    Импортирует данные из Excel:
    - колонка A: полный номер быка;
    - колонка B: вес на предыдущую дату;
    - колонка C: вес на текущую дату.

    Если номер не найден:
    - при наличии похожих номеров строка уходит в ручное сопоставление;
    - если похожих номеров нет, создается новый бык (новое поступление).
    """

    wb = load_workbook(file_obj, data_only=True)
    ws = wb.active

    batch = ExcelImportBatch.objects.create(
        previous_weighing_date=previous_date,
        current_weighing_date=current_date,
    )

    applied = 0
    pending = 0
    total = 0

    for row_idx in range(2, ws.max_row + 1):
        raw_external_id = str(ws.cell(row=row_idx, column=1).value or "").strip()
        prev_weight = ws.cell(row=row_idx, column=2).value
        curr_weight = ws.cell(row=row_idx, column=3).value

        if not raw_external_id:
            continue

        total += 1
        bull = Bull.objects.filter(external_id=raw_external_id).first()

        if bull:
            _apply_weight_pair(bull, previous_date, current_date, prev_weight, curr_weight)
            applied += 1
            continue

        suggested = get_similar_ids(raw_external_id)
        if not suggested:
            bull = Bull.objects.create(external_id=raw_external_id)
            _apply_weight_pair(bull, previous_date, current_date, prev_weight, curr_weight)
            applied += 1
        else:
            ExcelImportPendingRow.objects.create(
                batch=batch,
                raw_external_id=raw_external_id,
                previous_weight_kg=_as_decimal(prev_weight),
                current_weight_kg=_as_decimal(curr_weight),
                suggested_ids=suggested,
            )
            pending += 1

    batch.total_rows = total
    batch.applied_rows = applied
    batch.pending_rows = pending
    batch.save(update_fields=["total_rows", "applied_rows", "pending_rows"])

    return ImportResult(batch=batch, applied_rows=applied, pending_rows=pending)


def _as_decimal(value) -> Decimal:
    """
    Приводит значение из Excel к Decimal.
    """

    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def _apply_weight_pair(bull, previous_date, current_date, prev_weight, curr_weight) -> None:
    """
    Создает или обновляет пару записей веса (прошлая и текущая дата).
    """

    WeightRecord.objects.update_or_create(
        bull=bull,
        weighing_date=previous_date,
        source="excel",
        defaults={"weight_kg": _as_decimal(prev_weight), "note": "Импорт: предыдущий вес"},
    )
    WeightRecord.objects.update_or_create(
        bull=bull,
        weighing_date=current_date,
        source="excel",
        defaults={"weight_kg": _as_decimal(curr_weight), "note": "Импорт: текущий вес"},
    )


@transaction.atomic
def resolve_pending_row(pending_row: ExcelImportPendingRow, bull: Bull) -> None:
    """
    Применяет проблемную строку импорта к выбранному быку.
    """

    if pending_row.is_resolved:
        return

    batch = pending_row.batch
    _apply_weight_pair(
        bull=bull,
        previous_date=batch.previous_weighing_date,
        current_date=batch.current_weighing_date,
        prev_weight=pending_row.previous_weight_kg,
        curr_weight=pending_row.current_weight_kg,
    )

    pending_row.is_resolved = True
    pending_row.resolved_to = bull
    pending_row.save(update_fields=["is_resolved", "resolved_to"])

    batch.applied_rows += 1
    batch.pending_rows = max(batch.pending_rows - 1, 0)
    batch.save(update_fields=["applied_rows", "pending_rows"])


def build_dashboard_stats() -> dict:
    """
    Собирает агрегаты для главной панели и простых отчетов.
    """

    section_counts = (
        Bull.objects.filter(is_active=True, section__isnull=False)
        .values("section__name")
        .annotate(total=Count("id"), avg_weight=Avg("weight_records__weight_kg"))
        .order_by("section__name")
    )

    return {
        "total_active_bulls": Bull.objects.filter(is_active=True).count(),
        "section_counts": list(section_counts),
    }


def build_growth_rating(limit: int = 10) -> dict:
    """
    Формирует рейтинги слабого и лучшего набора веса.

    Метрики:
    - абсолютный привес = последний вес - первый вес;
    - среднесуточный привес = абсолютный / количество дней между замерами.
    """

    bulls_data = []
    for bull in Bull.objects.filter(is_active=True).prefetch_related("weight_records"):
        records = list(bull.weight_records.order_by("weighing_date"))
        if len(records) < 2:
            continue

        first = records[0]
        last = records[-1]
        days = (last.weighing_date - first.weighing_date).days or 1
        absolute_gain = Decimal(last.weight_kg) - Decimal(first.weight_kg)
        daily_gain = absolute_gain / Decimal(days)

        bulls_data.append(
            {
                "bull": bull,
                "absolute_gain": absolute_gain,
                "daily_gain": daily_gain,
                "days": days,
                "first_weight": first.weight_kg,
                "last_weight": last.weight_kg,
            }
        )

    by_absolute = sorted(bulls_data, key=lambda x: x["absolute_gain"])
    by_daily = sorted(bulls_data, key=lambda x: x["daily_gain"])

    return {
        "weak_absolute": by_absolute[:limit],
        "best_absolute": list(reversed(by_absolute[-limit:])),
        "weak_daily": by_daily[:limit],
        "best_daily": list(reversed(by_daily[-limit:])),
    }
