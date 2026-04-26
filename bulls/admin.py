"""Admin registrations for quick manual management in learning phase."""

from django.contrib import admin

from .models import (
    Bull,
    DepartureRecord,
    HealthRecord,
    ImportIssue,
    ImportSession,
    Section,
    SectionTransfer,
    WeightRecord,
)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    """Section configuration with physical layout fields."""

    list_display = ("number", "side", "position_in_row", "capacity")
    list_filter = ("side",)
    search_fields = ("number",)


@admin.register(Bull)
class BullAdmin(admin.ModelAdmin):
    """Bull list admin with search by both code parts."""

    list_display = ("bivayka", "bull_number", "full_code", "status", "current_section", "arrival_date")
    list_filter = ("status", "current_section")
    search_fields = ("full_code", "bivayka", "bull_number")


@admin.register(WeightRecord)
class WeightRecordAdmin(admin.ModelAdmin):
    """Weight records with useful filters for quick corrections."""

    list_display = ("bull", "weighing_date", "weight_kg", "source")
    list_filter = ("source", "weighing_date")
    search_fields = ("bull__full_code", "bull__bull_number")


@admin.register(SectionTransfer)
class SectionTransferAdmin(admin.ModelAdmin):
    """Transfer history for audit and troubleshooting."""

    list_display = ("bull", "from_section", "to_section", "transfer_date")
    list_filter = ("transfer_date", "to_section")
    search_fields = ("bull__full_code",)


@admin.register(DepartureRecord)
class DepartureRecordAdmin(admin.ModelAdmin):
    """Departure with marker-based filtering for statistics."""

    list_display = ("bull", "departure_date", "marker", "weight_kg")
    list_filter = ("marker", "departure_date")
    search_fields = ("bull__full_code",)


@admin.register(HealthRecord)
class HealthRecordAdmin(admin.ModelAdmin):
    """Medical notes and treatment records."""

    list_display = ("bull", "record_date", "record_type", "resolved")
    list_filter = ("record_type", "resolved")
    search_fields = ("bull__full_code", "description")


@admin.register(ImportSession)
class ImportSessionAdmin(admin.ModelAdmin):
    """Import run overview with counters."""

    list_display = (
        "file_name",
        "uploaded_at",
        "processed_rows",
        "created_records",
        "updated_records",
        "unresolved_rows",
    )
    readonly_fields = list_display


@admin.register(ImportIssue)
class ImportIssueAdmin(admin.ModelAdmin):
    """Unresolved import rows with suggested alternatives."""

    list_display = ("incoming_full_code", "weighing_date", "weight_kg", "resolved_bull")
    list_filter = ("weighing_date",)
    search_fields = ("incoming_full_code", "incoming_bull_number")
