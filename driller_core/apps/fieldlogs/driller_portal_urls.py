from django.urls import path

from .driller_portal_views import (
    driller_coverage_collection_view,
    driller_coverage_detail_view,
    driller_dashboard_view,
    driller_field_execution_detail_view,
    driller_field_execution_list_view,
    driller_input_artifact_view,
    driller_input_start_view,
    driller_input_submit_view,
    driller_input_update_view,
    driller_login_view,
    driller_me_view,
)


urlpatterns = [
    path("auth/login/", driller_login_view, name="driller-portal-login"),
    path("auth/me/", driller_me_view, name="driller-portal-me"),
    path("dashboard/", driller_dashboard_view, name="driller-portal-dashboard"),
    path("coverage/", driller_coverage_collection_view, name="driller-portal-coverage-collection"),
    path("coverage/<int:coverage_id>/", driller_coverage_detail_view, name="driller-portal-coverage-detail"),
    path("field-executions/", driller_field_execution_list_view, name="driller-portal-field-execution-list"),
    path("field-executions/<str:identifier>/", driller_field_execution_detail_view, name="driller-portal-field-execution-detail"),
    path("drilling-input/start/", driller_input_start_view, name="driller-portal-drilling-input-start"),
    path("drilling-input/<str:identifier>/", driller_input_update_view, name="driller-portal-drilling-input-update"),
    path("drilling-input/<str:identifier>/artifact/", driller_input_artifact_view, name="driller-portal-drilling-input-artifact"),
    path("drilling-input/<str:identifier>/submit/", driller_input_submit_view, name="driller-portal-drilling-input-submit"),
]
