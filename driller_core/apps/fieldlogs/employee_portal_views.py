from __future__ import annotations

import hmac
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import DrillingInputRecord, FieldExecution
from .services import (
    complete_drilling_input_record,
    ensure_editable_record_seeded,
    FieldLogValidationError,
    field_execution_payload,
    field_log_artifact_payload,
    start_drilling_input,
    update_drilling_input_record,
)

logger = logging.getLogger(__name__)


def _internal_secret_valid(request) -> bool:
    expected = settings.DRILLER_CORE_INTERNAL_SHARED_SECRET
    provided = (request.headers.get("X-Internal-Service-Secret") or "").strip()
    return bool(expected) and bool(provided) and hmac.compare_digest(provided, expected)


def _load_json_body(request):
    try:
        return json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return None


def _employee_actor(payload: dict) -> dict:
    return {
        "display_name": (payload.get("actor_name") or "").strip(),
        "email": (payload.get("actor_email") or "").strip(),
    }


def _execution_by_external_project_id(external_project_id: str) -> FieldExecution | None:
    return FieldExecution.objects.select_related("assigned_driller").filter(external_project_id=(external_project_id or "").strip()).first()


def _record_by_identifier(identifier: str) -> DrillingInputRecord | None:
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    if identifier.isdigit():
        return DrillingInputRecord.objects.select_related("field_execution__assigned_driller").filter(pk=int(identifier)).first()
    return DrillingInputRecord.objects.select_related("field_execution__assigned_driller").filter(shared_uuid=identifier).first()


def _employee_portal_error():
    return JsonResponse({"detail": "Internal service authentication failed."}, status=403)


def _unexpected_error_response(action: str):
    return JsonResponse(
        {"detail": f"Field log {action} failed before driller-core returned a structured response."},
        status=500,
    )


@require_GET
def employee_field_execution_detail_view(request, external_project_id: str):
    if not _internal_secret_valid(request):
        return _employee_portal_error()

    try:
        execution = _execution_by_external_project_id(external_project_id)
        if execution is None:
            return JsonResponse({"detail": "Field execution not found."}, status=404)
        ensure_editable_record_seeded(execution)
        return JsonResponse(field_execution_payload(execution))
    except Exception:
        logger.exception("Employee field-log load failed for execution %s", external_project_id)
        return _unexpected_error_response("load")


@csrf_exempt
@require_POST
def employee_drilling_input_create_view(request):
    if not _internal_secret_valid(request):
        return _employee_portal_error()

    payload = _load_json_body(request)
    if payload is None:
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    execution = _execution_by_external_project_id(str(payload.get("external_project_id") or ""))
    if execution is None:
        return JsonResponse({"detail": "Field execution not found."}, status=404)

    entry_method = (payload.get("entry_method") or "").strip() or DrillingInputRecord.EntryMethod.EMPLOYEE_FROM_PAPER
    try:
        record = start_drilling_input(
            execution,
            actor=_employee_actor(payload),
            entry_method=entry_method,
        )
        if payload.get("borings") or payload.get("notes"):
            update_drilling_input_record(record, payload=payload, actor=_employee_actor(payload))
    except FieldLogValidationError as exc:
        return JsonResponse({"detail": exc.detail, "field_errors": exc.field_errors}, status=400)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    except Exception:
        logger.exception("Employee field-log create failed for execution %s", execution.external_project_id)
        return _unexpected_error_response("creation")

    return JsonResponse({"execution": field_execution_payload(execution)})


@csrf_exempt
@require_http_methods(["PATCH"])
def employee_drilling_input_update_view(request, identifier: str):
    if not _internal_secret_valid(request):
        return _employee_portal_error()

    payload = _load_json_body(request)
    if payload is None:
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    record = _record_by_identifier(identifier)
    if record is None:
        return JsonResponse({"detail": "Field log record not found."}, status=404)

    try:
        update_drilling_input_record(
            record,
            payload=payload,
            actor=_employee_actor(payload),
            allow_under_review=True,
        )
    except FieldLogValidationError as exc:
        return JsonResponse({"detail": exc.detail, "field_errors": exc.field_errors}, status=400)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    except Exception:
        logger.exception("Employee field-log update failed for record %s", identifier)
        return _unexpected_error_response("save")

    return JsonResponse({"execution": field_execution_payload(record.field_execution)})


@csrf_exempt
@require_POST
def employee_drilling_input_complete_view(request, identifier: str):
    if not _internal_secret_valid(request):
        return _employee_portal_error()

    payload = _load_json_body(request)
    if payload is None:
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    record = _record_by_identifier(identifier)
    if record is None:
        return JsonResponse({"detail": "Field log record not found."}, status=404)

    try:
        pdf_artifact = complete_drilling_input_record(
            record,
            actor=_employee_actor(payload),
            custody_payload=payload.get("custody"),
        )
    except FieldLogValidationError as exc:
        return JsonResponse({"detail": exc.detail, "field_errors": exc.field_errors}, status=400)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    except Exception:
        logger.exception("Employee field-log completion failed for record %s", identifier)
        return _unexpected_error_response("completion")

    return JsonResponse(
        {
            "execution": field_execution_payload(record.field_execution),
            "pdf": field_log_artifact_payload(record, pdf_artifact),
        }
    )
