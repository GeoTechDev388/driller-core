from django.urls import path

from .internal_views import (
    internal_accepted_drilling_input_artifact_view,
    internal_accepted_drilling_input_view,
)


urlpatterns = [
    path("drilling-input/<str:external_project_id>/", internal_accepted_drilling_input_view, name="internal-accepted-drilling-input"),
    path(
        "drilling-input/<str:external_project_id>/artifact/",
        internal_accepted_drilling_input_artifact_view,
        name="internal-accepted-drilling-input-artifact",
    ),
]
