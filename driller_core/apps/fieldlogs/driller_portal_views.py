from __future__ import annotations

import json
import uuid

from django.contrib.auth import authenticate
from django.http import FileResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from driller_core.apps.network.services import (
    add_driller_coverage,
    coverage_payload,
    deactivate_driller_coverage,
    list_driller_coverages,
)

from .auth import (
    DrillerAuthError,
    build_driller_session_token,
    driller_response_payload,
    get_driller_access_context,
    resolve_driller_session_token,
)
from .models import DrillingInputRecord, FieldExecution
from .pdf import field_log_pdf_display_name
from .services import (
    ensure_editable_record_seeded,
    FieldLogValidationError,
    field_execution_payload,
    start_drilling_input,
    submit_drilling_input_record,
    update_drilling_input_record,
)


def _parse_request_data(request):
    if request.content_type and "application/json" in request.content_type:
        if not request.body:
            return {}
        try:
            return json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid JSON body.") from exc
    return request.POST.dict()


def _bearer_token(request) -> str:
    authorization = (request.headers.get("Authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


def _driller_context_or_response(request):
    token = _bearer_token(request)
    if not token:
        return None, JsonResponse({"detail": "Driller access token is required."}, status=401)
    try:
        return resolve_driller_session_token(token), None
    except DrillerAuthError as exc:
        return None, JsonResponse({"detail": exc.detail, "code": exc.code}, status=401)


def _assigned_jobs_payload(context) -> list[dict]:
    executions = (
        FieldExecution.objects.select_related("assigned_driller")
        .filter(assigned_driller=context.driller)
        .prefetch_related("drilling_input_records")
        .order_by("scheduled_start_date", "project_number", "id")
    )
    return [field_execution_payload(execution, include_records=False) for execution in executions]


def _execution_for_context(context, identifier: str):
    queryset = FieldExecution.objects.select_related("assigned_driller").filter(assigned_driller=context.driller)
    identifier = (identifier or "").strip()
    try:
        execution = queryset.filter(shared_uuid=uuid.UUID(identifier)).first()
        if execution is not None:
            return execution
    except ValueError:
        pass
    if identifier.isdigit():
        execution = queryset.filter(pk=int(identifier)).first()
        if execution is not None:
            return execution
    return queryset.filter(external_project_id=identifier).first()


def _record_for_context(context, identifier: str) -> DrillingInputRecord | None:
    identifier = (identifier or "").strip()
    queryset = DrillingInputRecord.objects.select_related("field_execution__assigned_driller", "pdf_artifact").filter(
        field_execution__assigned_driller=context.driller,
    )
    if not identifier:
        return None
    if identifier.isdigit():
        record = queryset.filter(pk=int(identifier)).first()
        if record is not None:
            return record
    try:
        record = queryset.filter(shared_uuid=uuid.UUID(identifier)).first()
        if record is not None:
            return record
    except ValueError:
        pass
    return None


@csrf_exempt
@require_POST
def driller_login_view(request):
    try:
        payload = _parse_request_data(request)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        return JsonResponse({"detail": "Email and password are required."}, status=400)

    user_account = authenticate(request=request, email=email, password=password)
    if user_account is None:
        return JsonResponse({"detail": "Invalid email or password.", "code": "invalid_credentials"}, status=401)

    try:
        context = get_driller_access_context(user_account)
    except DrillerAuthError as exc:
        return JsonResponse({"detail": exc.detail, "code": exc.code}, status=403)

    response_payload = driller_response_payload(context)
    response_payload["token"] = build_driller_session_token(user_account)
    return JsonResponse(response_payload)


@require_GET
def driller_me_view(request):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    return JsonResponse(
        {
            **driller_response_payload(context),
            "assigned_jobs": _assigned_jobs_payload(context),
        }
    )


@require_GET
def driller_dashboard_view(request):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    return JsonResponse(
        {
            **driller_response_payload(context),
            "assigned_jobs": _assigned_jobs_payload(context),
        }
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def driller_coverage_collection_view(request):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    if request.method == "GET":
        return JsonResponse({"items": list_driller_coverages(context.driller)})

    try:
        payload = _parse_request_data(request)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    try:
        coverage = add_driller_coverage(
            context.driller,
            county_name=payload.get("county_name"),
            state_code=payload.get("state_code") or "TX",
        )
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse({"item": coverage_payload(coverage)}, status=201)


@csrf_exempt
@require_http_methods(["DELETE"])
def driller_coverage_detail_view(request, coverage_id: int):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    coverage = deactivate_driller_coverage(context.driller, coverage_id)
    if coverage is None:
        return JsonResponse({"detail": "Coverage county not found."}, status=404)
    return JsonResponse({"removed_id": coverage_id})


@require_GET
def driller_field_execution_list_view(request):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    executions = FieldExecution.objects.select_related("assigned_driller").filter(
        assigned_driller=context.driller,
    ).prefetch_related("drilling_input_records").order_by("scheduled_start_date", "project_number", "id")
    return JsonResponse({"items": [field_execution_payload(execution, include_records=False) for execution in executions]})


@require_GET
def driller_field_execution_detail_view(request, identifier: str):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    execution = _execution_for_context(context, identifier)
    if execution is None:
        return JsonResponse({"detail": "Field execution not found."}, status=404)
    ensure_editable_record_seeded(execution)
    return JsonResponse(field_execution_payload(execution))


@csrf_exempt
@require_POST
def driller_input_start_view(request):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    try:
        payload = _parse_request_data(request)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)

    execution = _execution_for_context(context, str(payload.get("field_execution_id") or ""))
    if execution is None:
        return JsonResponse({"detail": "Field execution not found."}, status=404)
    try:
        start_drilling_input(
            execution,
            actor={"email": context.user_account.email},
            entry_method=DrillingInputRecord.EntryMethod.DRILLER_DIRECT,
        )
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse({"execution": field_execution_payload(execution)})


@csrf_exempt
@require_http_methods(["PATCH"])
def driller_input_update_view(request, identifier: str):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    record = _record_for_context(context, identifier)
    if record is None:
        return JsonResponse({"detail": "Field log record not found."}, status=404)

    try:
        payload = _parse_request_data(request)
        update_drilling_input_record(record, payload=payload, actor={"email": context.user_account.email})
    except FieldLogValidationError as exc:
        return JsonResponse({"detail": exc.detail, "field_errors": exc.field_errors}, status=400)
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse({"execution": field_execution_payload(record.field_execution)})


@csrf_exempt
@require_POST
def driller_input_submit_view(request, identifier: str):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    record = _record_for_context(context, identifier)
    if record is None:
        return JsonResponse({"detail": "Field log record not found."}, status=404)

    try:
        submit_drilling_input_record(record, actor={"email": context.user_account.email})
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse({"execution": field_execution_payload(record.field_execution)})


@require_GET
def driller_input_artifact_view(request, identifier: str):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    record = _record_for_context(context, identifier)
    if record is None:
        return JsonResponse({"detail": "Field log record not found."}, status=404)
    if record.status != DrillingInputRecord.Status.ACCEPTED:
        return JsonResponse({"detail": "Accepted field logs only expose a stored artifact."}, status=400)

    artifact = getattr(record, "pdf_artifact", None)
    if artifact is None or not artifact.file:
        return JsonResponse(
            {"detail": "Accepted field-log artifact is not available yet. Re-approve or backfill the stored snapshot."},
            status=409,
        )

    response = FileResponse(artifact.file.open("rb"), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{field_log_pdf_display_name(record)}"'
    return response
