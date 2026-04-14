from django.contrib import admin
from django.urls import include, path

from .views import health_view, readiness_view


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/driller-portal/", include("driller_core.apps.fieldlogs.driller_portal_urls")),
    path("api/driller-portal/", include("driller_core.apps.network.driller_portal_urls")),
    path("api/employee-portal/", include("driller_core.apps.fieldlogs.employee_portal_urls")),
    path("api/internal/", include("driller_core.apps.fieldlogs.internal_urls")),
    path("api/network/", include("driller_core.apps.network.urls")),
    path("health/", health_view, name="health"),
    path("ready/", readiness_view, name="ready"),
]
