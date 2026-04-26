"""
Регистрация моделей в Django Admin.
"""

from django.contrib import admin

from .models import (
    ArrivalEvent,
    Bull,
    BullHealthRecord,
    DepartureEvent,
    ExcelImportBatch,
    ExcelImportPendingRow,
    Section,
    SectionMovement,
    WeightRecord,
)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("name", "side", "order", "capacity")
    list_filter = ("side",)
    ordering = ("side", "order")


@admin.register(Bull)
class BullAdmin(admin.ModelAdmin):
    list_display = ("external_id", "bull_number", "section", "is_active")
    list_filter = ("is_active", "section")
    search_fields = ("external_id", "bull_number", "biavka_part")


@admin.register(WeightRecord)
class WeightRecordAdmin(admin.ModelAdmin):
    list_display = ("bull", "weighing_date", "weight_kg", "source")
    list_filter = ("source", "weighing_date")
    search_fields = ("bull__external_id",)


@admin.register(ArrivalEvent)
class ArrivalEventAdmin(admin.ModelAdmin):
    list_display = ("bull", "arrived_at", "section", "arrival_weight_kg")
    list_filter = ("arrived_at", "section")
    search_fields = ("bull__external_id", "bull__bull_number")


@admin.register(SectionMovement)
class SectionMovementAdmin(admin.ModelAdmin):
    list_display = ("bull", "moved_at", "from_section", "to_section")
    list_filter = ("moved_at", "from_section", "to_section")


@admin.register(DepartureEvent)
class DepartureEventAdmin(admin.ModelAdmin):
    list_display = ("bull", "departed_at", "departure_weight_kg", "reason")
    list_filter = ("reason", "departed_at")


@admin.register(BullHealthRecord)
class BullHealthRecordAdmin(admin.ModelAdmin):
    list_display = ("bull", "record_date", "status_text", "treatment_text")
    list_filter = ("record_date",)
    search_fields = ("bull__external_id", "bull__bull_number", "status_text", "treatment_text", "comment")


class ExcelImportPendingRowInline(admin.TabularInline):
    model = ExcelImportPendingRow
    extra = 0


@admin.register(ExcelImportBatch)
class ExcelImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "total_rows", "applied_rows", "pending_rows")
    inlines = [ExcelImportPendingRowInline]


@admin.register(ExcelImportPendingRow)
class ExcelImportPendingRowAdmin(admin.ModelAdmin):
    list_display = ("batch", "raw_external_id", "is_resolved", "resolved_to")
    list_filter = ("is_resolved",)
