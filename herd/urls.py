"""
Маршруты приложения учета быков.
"""

from django.urls import path

from .views import (
    ArrivalCreateView,
    BullDetailView,
    BullListView,
    CreateBullFromPendingRowView,
    DashboardView,
    DepartureCreateView,
    ImportBatchDetailView,
    ImportExcelView,
    ImportHistoryView,
    ManualWeightCreateView,
    MovementCreateView,
    ResolveImportRowView,
)

app_name = "herd"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("bulls/", BullListView.as_view(), name="bull-list"),
    path("bulls/<int:bull_id>/", BullDetailView.as_view(), name="bull-detail"),
    path("arrivals/new/", ArrivalCreateView.as_view(), name="arrival-create"),
    path("weights/manual/", ManualWeightCreateView.as_view(), name="manual-weight"),
    path("movements/new/", MovementCreateView.as_view(), name="movement-create"),
    path("departures/new/", DepartureCreateView.as_view(), name="departure-create"),
    path("import/excel/", ImportExcelView.as_view(), name="import-excel"),
    path("import/history/", ImportHistoryView.as_view(), name="import-history"),
    path("import/batch/<int:batch_id>/", ImportBatchDetailView.as_view(), name="import-batch-detail"),
    path("import/resolve/<int:row_id>/", ResolveImportRowView.as_view(), name="resolve-import-row"),
    path("import/resolve/<int:row_id>/create-bull/", CreateBullFromPendingRowView.as_view(), name="create-bull-from-pending"),
]
