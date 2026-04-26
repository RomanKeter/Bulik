"""Application services for imports, analytics and bulk operations.

Why services module exists:
- keep views thin and readable;
- concentrate business rules in one place;
- make code easier to test in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import get_close_matches

import pandas as pd
from django.db import transaction
from django.db.models import Max, Min
from django.utils import timezone

from .models import Bull, ImportIssue, ImportSession, SectionTransfer, WeightRecord


@dataclass
class ImportStats:
    """Structured result returned after Excel parsing and saving."""

    processed_rows: int
    created_records: int
    updated_records: int
    unresolved_rows: int


def _parse_excel_date(header_value) -> date | None:
    """Converts a column header to `date` if it looks like weigh date.

    Accepted formats:
    - datetime/date objects (already parsed by pandas/openpyxl);
    - strings in `dd.mm.yyyy`.
    """
    if isinstance(header_value, datetime):
        return header_value.date()
    if isinstance(header_value, date):
        return header_value
    if isinstance(header_value, str):
        try:
            return datetime.strptime(header_value.strip(), "%d.%m.%Y").date()
        except ValueError:
            return None
    return None


def suggest_similar_full_codes(incoming_full_code: str, limit: int = 5) -> list[str]:
    """Returns similar known full codes to help resolve import typos.

    Similarity is based on Python `difflib.get_close_matches`, which is simple,
    transparent, and good enough for learning-stage project.
    """
    existing_codes = list(Bull.objects.values_list("full_code", flat=True))
    return get_close_matches(incoming_full_code, existing_codes, n=limit, cutoff=0.5)


def _parse_manual_dates(raw_dates: str) -> list[date]:
    """Parses comma-separated dates in dd.mm.yyyy format."""
    if not raw_dates:
        return []
    result = []
    for chunk in raw_dates.split(","):
        text = chunk.strip()
        if not text:
            continue
        try:
            result.append(datetime.strptime(text, "%d.%m.%Y").date())
        except ValueError as error:
            raise ValueError(f"Неверный формат даты: '{text}'. Используйте ДД.ММ.ГГГГ.") from error
    return result


def _infer_compact_dates(columns_count: int) -> list[date]:
    """Automatically builds dates for compact file when user did not provide them.

    Rule is deterministic and practical for monthly control weighing:
    - if system already has enough weighing dates, use the latest N dates;
    - otherwise generate missing older dates with 30-day step;
    - if there are no weighings at all, generate sequence ending today.
    """
    if columns_count <= 0:
        return []

    existing_dates = list(
        WeightRecord.objects.values_list("weighing_date", flat=True).distinct().order_by("weighing_date")
    )
    if len(existing_dates) >= columns_count:
        return existing_dates[-columns_count:]

    if existing_dates:
        result_dates = existing_dates[:]
        missing = columns_count - len(result_dates)
        anchor = result_dates[0]
        generated = [anchor - timedelta(days=30 * step) for step in range(missing, 0, -1)]
        return generated + result_dates

    today = timezone.localdate()
    return [today - timedelta(days=30 * step) for step in range(columns_count - 1, -1, -1)]


def _process_weight_cell(
    *,
    session: ImportSession,
    bivayka: str,
    bull_number: str,
    weighing_date: date,
    raw_weight,
    stats: ImportStats,
    auto_create_missing_bulls: bool,
) -> None:
    """Processes one weight cell and updates session statistics."""
    if pd.isna(raw_weight):
        return

    stats.processed_rows += 1
    weight_kg = int(raw_weight)
    incoming_full_code = f"{bivayka}{bull_number}"
    bull = Bull.objects.filter(bivayka=bivayka, bull_number=bull_number).first()
    if not bull:
        if auto_create_missing_bulls:
            bull = Bull.objects.create(
                bivayka=bivayka,
                bull_number=bull_number,
                full_code=incoming_full_code,
                arrival_date=weighing_date,
                status=Bull.Status.ACTIVE,
            )
        else:
            ImportIssue.objects.create(
                session=session,
                incoming_bivayka=bivayka,
                incoming_bull_number=bull_number,
                incoming_full_code=incoming_full_code,
                weighing_date=weighing_date,
                weight_kg=weight_kg,
                suggested_full_codes=suggest_similar_full_codes(incoming_full_code),
            )
            stats.unresolved_rows += 1
            return

    _, created = WeightRecord.objects.update_or_create(
        bull=bull,
        weighing_date=weighing_date,
        defaults={"weight_kg": weight_kg, "source": WeightRecord.Source.EXCEL},
    )
    if created:
        stats.created_records += 1
    else:
        stats.updated_records += 1


@transaction.atomic
def import_weights_from_excel(
    uploaded_file,
    manual_dates: str = "",
    auto_create_missing_bulls: bool = True,
) -> ImportSession:
    """Imports weight records from wide-format Excel file.

    Input formats:
    - Column A: "бивайка"
    - Column B: "номер быка"
    - Columns C, D, E...: weigh dates in dd.mm.yyyy format
      and integer weight values in rows.
    OR compact format:
    - Column A: full code (bivayka + bull number)
    - Columns B, C, D...: integer weight values
    - dates for B/C/D are provided manually from UI field.

    Behavior for unknown bull:
    - create `ImportIssue` with similar suggestions;
    - do not auto-create a new bull;
    - admin later resolves it manually by selecting correct bull.
    """
    df = pd.read_excel(uploaded_file)
    normalized_columns = {str(col).strip().lower(): col for col in df.columns}
    session = ImportSession.objects.create(file_name=getattr(uploaded_file, "name", "uploaded.xlsx"))
    stats = ImportStats(0, 0, 0, 0)

    required = {"бивайка", "номер быка"}
    if required.issubset(set(normalized_columns.keys())):
        bivayka_col = normalized_columns["бивайка"]
        number_col = normalized_columns["номер быка"]

        weigh_columns: list[tuple[object, date]] = []
        for column_name in df.columns:
            parsed_date = _parse_excel_date(column_name)
            if parsed_date:
                weigh_columns.append((column_name, parsed_date))

        if not weigh_columns:
            raise ValueError("Не найдены колонки с датами перевески (формат дд.мм.гггг).")

        for _, row in df.iterrows():
            bivayka = str(row[bivayka_col]).strip()
            bull_number = str(row[number_col]).strip()
            if not bivayka or not bull_number or bivayka.lower() == "nan" or bull_number.lower() == "nan":
                continue
            for column_name, weighing_date in weigh_columns:
                _process_weight_cell(
                    session=session,
                    bivayka=bivayka,
                    bull_number=bull_number,
                    weighing_date=weighing_date,
                    raw_weight=row[column_name],
                    stats=stats,
                    auto_create_missing_bulls=auto_create_missing_bulls,
                )
    else:
        uploaded_file.seek(0)
        compact_df = pd.read_excel(uploaded_file, header=None)
        manual_date_list = _parse_manual_dates(manual_dates)
        if not manual_date_list:
            raise ValueError(
                "Для файла без заголовков укажите даты колонок веса в поле 'Даты для колонок веса'."
            )

        weight_column_indices = []
        for column_index in range(1, compact_df.shape[1]):
            if compact_df.iloc[:, column_index].notna().any():
                weight_column_indices.append(column_index)

        if not weight_column_indices:
            raise ValueError("В файле не найдены колонки с весом (B, C, D...).")
        if not manual_date_list:
            manual_date_list = _infer_compact_dates(len(weight_column_indices))
        elif len(manual_date_list) < len(weight_column_indices):
            raise ValueError("Указано меньше дат, чем колонок веса. Добавьте даты для всех колонок B/C/D...")

        for _, row in compact_df.iterrows():
            full_code = str(row[0]).strip()
            if not full_code or full_code.lower() == "nan":
                continue
            if len(full_code) != 14:
                continue

            bivayka = full_code[:8]
            bull_number = full_code[8:]
            for idx, column_index in enumerate(weight_column_indices):
                _process_weight_cell(
                    session=session,
                    bivayka=bivayka,
                    bull_number=bull_number,
                    weighing_date=manual_date_list[idx],
                    raw_weight=row[column_index],
                    stats=stats,
                    auto_create_missing_bulls=auto_create_missing_bulls,
                )

    session.processed_rows = stats.processed_rows
    session.created_records = stats.created_records
    session.updated_records = stats.updated_records
    session.unresolved_rows = stats.unresolved_rows
    session.save(update_fields=["processed_rows", "created_records", "updated_records", "unresolved_rows"])
    return session


@transaction.atomic
def apply_bulk_section_transfer(*, bulls: list[Bull], target_section, transfer_date: date, comment: str) -> int:
    """Moves multiple bulls to one section and writes transfer history.

    Returns count of actually moved bulls. Bulls already in target section are
    skipped silently.
    """
    already_in_target = sum(1 for bull in bulls if bull.current_section == target_section)
    planned_move_count = len(bulls) - already_in_target
    current_occupancy = Bull.objects.filter(current_section=target_section, status=Bull.Status.ACTIVE).count()
    if current_occupancy + planned_move_count > target_section.capacity:
        raise ValueError(
            f"Нельзя перевести: вместимость секции {target_section.number} будет превышена."
        )

    moved_count = 0
    for bull in bulls:
        from_section = bull.current_section
        if from_section == target_section or from_section is None:
            continue
        SectionTransfer.objects.create(
            bull=bull,
            from_section=from_section,
            to_section=target_section,
            transfer_date=transfer_date,
            comment=comment,
        )
        bull.current_section = target_section
        bull.save(update_fields=["current_section", "updated_at"])
        moved_count += 1
    return moved_count


def build_bulls_ranking(period_start: date, period_end: date, limit: int = 10) -> dict[str, list[dict]]:
    """Builds ranking for weakest and strongest gain dynamics.

    Returns both:
    - absolute gain in kilograms;
    - average daily gain in kg/day.

    This function takes first/last available weighing in selected period.
    """
    ranking_rows = []
    active_bulls = Bull.objects.filter(status=Bull.Status.ACTIVE).prefetch_related("weight_records")
    for bull in active_bulls:
        in_period = list(
            bull.weight_records.filter(weighing_date__range=(period_start, period_end)).order_by("weighing_date")
        )
        if len(in_period) < 2:
            continue
        first_record = in_period[0]
        last_record = in_period[-1]
        days = max((last_record.weighing_date - first_record.weighing_date).days, 1)
        gain_kg = last_record.weight_kg - first_record.weight_kg
        ranking_rows.append(
            {
                "bull": bull,
                "gain_kg": gain_kg,
                "daily_gain": gain_kg / days,
                "start_weight": first_record.weight_kg,
                "end_weight": last_record.weight_kg,
            }
        )

    by_gain = sorted(ranking_rows, key=lambda item: item["gain_kg"])
    by_daily_gain = sorted(ranking_rows, key=lambda item: item["daily_gain"])

    return {
        "weakest_by_gain": by_gain[:limit],
        "strongest_by_gain": list(reversed(by_gain[-limit:])),
        "weakest_by_daily_gain": by_daily_gain[:limit],
        "strongest_by_daily_gain": list(reversed(by_daily_gain[-limit:])),
    }


def calculate_bull_days(period_start: date, period_end: date) -> int:
    """Calculates total bull-days for selected period.

    Bull-days are needed for fair daily gain when some bulls leave in the
    middle of control period.
    """
    if period_end < period_start:
        return 0

    total = 0
    total_days = (period_end - period_start).days + 1
    bulls = Bull.objects.select_related("departure")
    for bull in bulls:
        start = max(period_start, bull.arrival_date)
        end = period_end
        if hasattr(bull, "departure"):
            end = min(end, bull.departure.departure_date)
        if end < start:
            continue
        days = (end - start).days + 1
        total += min(days, total_days)
    return total


def section_summary_snapshot() -> list[dict]:
    """Builds per-section overview with count and average latest weight."""
    sections_data = []
    for bull in Bull.objects.select_related("current_section").all():
        if not bull.current_section:
            continue
        section_number = bull.current_section.number
        section_info = next((item for item in sections_data if item["section_number"] == section_number), None)
        if section_info is None:
            section_info = {"section_number": section_number, "bulls_count": 0, "weights": []}
            sections_data.append(section_info)
        section_info["bulls_count"] += 1
        if bull.latest_weight:
            section_info["weights"].append(bull.latest_weight.weight_kg)

    for item in sections_data:
        weights = item.pop("weights")
        item["avg_weight"] = round(sum(weights) / len(weights), 2) if weights else None
    return sorted(sections_data, key=lambda x: x["section_number"])


def default_report_period() -> tuple[date, date]:
    """Returns a practical default period for report screens."""
    latest = WeightRecord.objects.aggregate(latest=Max("weighing_date"), earliest=Min("weighing_date"))
    if latest["latest"] and latest["earliest"]:
        end = latest["latest"]
        start = max(latest["earliest"], end.replace(day=1))
        return start, end
    today = timezone.localdate()
    return today.replace(day=1), today


@transaction.atomic
def resolve_import_issue(issue: ImportIssue, selected_bull: Bull) -> None:
    """Applies admin-selected bull to unresolved import row.

    After resolve:
    - create or update the related weight record;
    - mark issue as resolved and link chosen bull.
    """
    WeightRecord.objects.update_or_create(
        bull=selected_bull,
        weighing_date=issue.weighing_date,
        defaults={"weight_kg": issue.weight_kg, "source": WeightRecord.Source.EXCEL},
    )
    issue.resolved_bull = selected_bull
    issue.resolved_at = timezone.now()
    issue.save(update_fields=["resolved_bull", "resolved_at"])

