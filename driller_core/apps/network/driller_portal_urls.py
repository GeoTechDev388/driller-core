from django.urls import path

from .driller_portal_views import (
    driller_availability_settings_update_view,
    driller_blackout_detail_view,
    driller_blackouts_view,
    driller_coverage_settings_update_view,
    driller_pricing_settings_update_view,
    driller_settings_view,
)


urlpatterns = [
    path("settings/", driller_settings_view, name="driller-portal-settings"),
    path(
        "settings/coverage/",
        driller_coverage_settings_update_view,
        name="driller-portal-settings-coverage",
    ),
    path(
        "settings/availability/",
        driller_availability_settings_update_view,
        name="driller-portal-settings-availability",
    ),
    path("blackouts/", driller_blackouts_view, name="driller-portal-blackouts"),
    path("blackouts/<int:blackout_id>/", driller_blackout_detail_view, name="driller-portal-blackout-detail"),
    path(
        "settings/pricing/",
        driller_pricing_settings_update_view,
        name="driller-portal-settings-pricing",
    ),
]
