from __future__ import annotations

import json
from datetime import date

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from driller_core.apps.fieldlogs.auth import DrillerAuthError, resolve_driller_session_token

from .driller_settings import (
    add_driller_blackout_date,
    deactivate_driller_blackout_date,
    driller_settings_payload,
    list_driller_blackouts,
    replace_availability_settings,
    replace_driller_coverages_for_state,
    replace_pricing_settings,
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


def _parse_date_value(value, *, field_name: str) -> date:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required.")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid date.") from exc


@require_GET
def driller_settings_view(request):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response
    return JsonResponse(driller_settings_payload(context.driller))


@csrf_exempt
@require_http_methods(["PUT"])
def driller_coverage_settings_update_view(request):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    try:
        payload = _parse_request_data(request)
        coverage = replace_driller_coverages_for_state(
            context.driller,
            state_code=payload.get("state_code"),
            county_names=list(payload.get("county_names") or []),
        )
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse({"coverage": coverage})


@csrf_exempt
@require_http_methods(["PUT"])
def driller_availability_settings_update_view(request):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    try:
        payload = _parse_request_data(request)
        availability = replace_availability_settings(
            context.driller,
            working_days_payload=list(payload.get("working_days") or []),
        )
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse({"availability": availability})


@csrf_exempt
@require_http_methods(["GET", "POST"])
def driller_blackouts_view(request):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    if request.method == "GET":
        return JsonResponse({"items": list_driller_blackouts(context.driller)})

    try:
        payload = _parse_request_data(request)
        blackout = add_driller_blackout_date(
            context.driller,
            blackout_date=_parse_date_value(payload.get("date"), field_name="date"),
            reason=payload.get("reason"),
        )
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse(
        {
            "item": blackout,
            "availability": driller_settings_payload(context.driller)["availability"],
        },
        status=201,
    )


@csrf_exempt
@require_http_methods(["DELETE"])
def driller_blackout_detail_view(request, blackout_id: int):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    blackout = deactivate_driller_blackout_date(context.driller, blackout_id)
    if blackout is None:
        return JsonResponse({"detail": "Blackout date was not found."}, status=404)
    return JsonResponse(
        {
            "removed_id": blackout_id,
            "availability": driller_settings_payload(context.driller)["availability"],
        }
    )


@csrf_exempt
@require_http_methods(["PUT"])
def driller_pricing_settings_update_view(request):
    context, error_response = _driller_context_or_response(request)
    if error_response is not None:
        return error_response

    try:
        payload = _parse_request_data(request)
        pricing = replace_pricing_settings(
            context.driller,
            schedule_name=payload.get("name"),
            currency=payload.get("currency"),
            notes=payload.get("notes"),
            line_items_payload=list(payload.get("line_items") or []),
        )
    except ValueError as exc:
        return JsonResponse({"detail": str(exc)}, status=400)
    return JsonResponse({"pricing": pricing})
