from django.urls import path

from .employee_portal_views import (
    employee_drilling_input_complete_view,
    employee_drilling_input_create_view,
    employee_drilling_input_update_view,
    employee_field_execution_detail_view,
)


urlpatterns = [
    path("field-executions/<str:external_project_id>/", employee_field_execution_detail_view, name="employee-field-execution-detail"),
    path("drilling-input/create/", employee_drilling_input_create_view, name="employee-drilling-input-create"),
    path("drilling-input/<str:identifier>/", employee_drilling_input_update_view, name="employee-drilling-input-update"),
    path("drilling-input/<str:identifier>/complete/", employee_drilling_input_complete_view, name="employee-drilling-input-complete"),
]
