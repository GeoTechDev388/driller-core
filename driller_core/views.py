from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def health_view(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": settings.CORE_DISPLAY_NAME,
            "platform": settings.PLATFORM_NAME,
            "company_display_name": settings.COMPANY_DISPLAY_NAME,
        }
    )


def readiness_view(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:
        return JsonResponse(
            {
                "status": "error",
                "service": settings.CORE_DISPLAY_NAME,
                "detail": str(exc),
            },
            status=503,
        )

    return JsonResponse(
        {
            "status": "ready",
            "service": settings.CORE_DISPLAY_NAME,
        }
    )
