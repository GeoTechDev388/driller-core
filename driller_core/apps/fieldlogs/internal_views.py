from __future__ import annotations

import hmac

from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.views.decorators.http import require_GET

from .models import DrillingInputRecord, FieldExecution
from .pdf import field_log_pdf_display_name
from .services import accepted_field_log_payload


def _internal_secret_valid(request) -> bool:
    expected = settings.DRILLER_CORE_INTERNAL_SHARED_SECRET
    provided = (request.headers.get("X-Internal-Service-Secret") or "").strip()
    return bool(expected) and bool(provided) and hmac.compare_digest(provided, expected)


@require_GET
def internal_accepted_drilling_input_view(request, external_project_id: str):
    if not _internal_secret_valid(request):
        return JsonResponse({"detail": "Internal service authentication failed."}, status=403)

    execution = FieldExecution.objects.filter(external_project_id=(external_project_id or "").strip()).first()
    if execution is None:
        return JsonResponse({"detail": "Field execution not found."}, status=404)
    return JsonResponse(accepted_field_log_payload(execution))


@require_GET
def internal_accepted_drilling_input_artifact_view(request, external_project_id: str):
    if not _internal_secret_valid(request):
        return JsonResponse({"detail": "Internal service authentication failed."}, status=403)

    execution = FieldExecution.objects.filter(external_project_id=(external_project_id or "").strip()).first()
    if execution is None:
        return JsonResponse({"detail": "Field execution not found."}, status=404)

    record = (
        execution.drilling_input_records.select_related("pdf_artifact")
        .filter(status=DrillingInputRecord.Status.ACCEPTED)
        .order_by("-accepted_at", "-updated_at", "-id")
        .first()
    )
    if record is None:
        return JsonResponse({"detail": "Accepted field log not found."}, status=404)

    artifact = getattr(record, "pdf_artifact", None)
    if artifact is None or not artifact.file:
        return JsonResponse({"detail": "Accepted field-log artifact is not available."}, status=404)

    response = FileResponse(artifact.file.open("rb"), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{field_log_pdf_display_name(record)}"'
    response["Cache-Control"] = "private, no-store"
    return response
