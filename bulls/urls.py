"""URL routes for bulls application pages."""

from django.urls import path

from . import views

app_name = "bulls"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("bulls/", views.bull_list_view, name="bull_list"),
    path("bulls/<int:bull_id>/", views.bull_detail_view, name="bull_detail"),
    path("import/", views.excel_import_view, name="excel_import"),
    path("import/issue/<int:issue_id>/resolve/", views.resolve_import_issue_view, name="resolve_import_issue"),
    path("bulk-transfer/", views.bulk_transfer_view, name="bulk_transfer"),
    path("reports/", views.reports_view, name="reports"),
    path("reports/export/excel/", views.reports_export_excel_view, name="reports_export_excel"),
    path("reports/export/pdf/", views.reports_export_pdf_view, name="reports_export_pdf"),
]
