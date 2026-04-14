from __future__ import annotations

import hmac
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import BookingRequest
from .services import (
    booking_payload,
    evaluate_and_commit_booking,
    list_fee_schedule_pricing_candidates,
    list_schedule_opportunities,
)


def _parse_datetime(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _internal_secret_valid(request) -> bool:
    expected = settings.DRILLER_CORE_INTERNAL_SHARED_SECRET
    provided = (request.headers.get("X-Internal-Service-Secret") or "").strip()
    return bool(expected) and bool(provided) and hmac.compare_digest(provided, expected)


def _load_json_body(request):
    try:
        return json.loads(request.body.decode("utf-8")) if request.body else {}
    except json.JSONDecodeError:
        return None


@csrf_exempt
@require_http_methods(["GET", "POST"])
def booking_request_collection_view(request):
    if not _internal_secret_valid(request):
        return JsonResponse({"detail": "Internal service authentication failed."}, status=403)

    if request.method == "GET":
        bookings = BookingRequest.objects.select_related("assigned_driller").order_by("-created_at", "-id")
        return JsonResponse({"items": [booking_payload(booking) for booking in bookings]})

    payload = _load_json_body(request)
    if payload is None:
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    try:
        estimated_days = Decimal(str(payload.get("estimated_days")))
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({"detail": "estimated_days must be a valid decimal."}, status=400)

    external_project_key = (payload.get("external_project_key") or "").strip()
    if not external_project_key:
        return JsonResponse({"detail": "external_project_key is required."}, status=400)

    booking, _created = BookingRequest.objects.update_or_create(
        external_project_key=external_project_key,
        defaults={
            "project_number": (payload.get("project_number") or "").strip(),
            "proposal_number": (payload.get("proposal_number") or "").strip(),
            "project_name": (payload.get("project_name") or "").strip() or "Unnamed project",
            "client_name": (payload.get("client_name") or "").strip(),
            "capability_required": (payload.get("capability_required") or "").strip(),
            "coverage_area": payload.get("coverage_area") or {},
            "estimated_days": estimated_days,
            "earliest_start_at": _parse_datetime(payload.get("earliest_start_at")),
            "status": BookingRequest.Status.REQUESTED,
            "assigned_driller": None,
            "committed_start_at": None,
            "committed_end_at": None,
            "blocking_reason": "",
            "request_payload": payload,
            "response_payload": {},
        },
    )
    booking = evaluate_and_commit_booking(booking)
    return JsonResponse(booking_payload(booking), status=201)


@csrf_exempt
@require_http_methods(["POST"])
def schedule_opportunity_collection_view(request):
    if not _internal_secret_valid(request):
        return JsonResponse({"detail": "Internal service authentication failed."}, status=403)

    payload = _load_json_body(request)
    if payload is None:
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    try:
        estimated_days = Decimal(str(payload.get("estimated_days")))
    except (InvalidOperation, TypeError, ValueError):
        return JsonResponse({"detail": "estimated_days must be a valid decimal."}, status=400)

    capability_required = (payload.get("capability_required") or "").strip()
    opportunities = list_schedule_opportunities(
        capability_required=capability_required,
        estimated_days=estimated_days,
        earliest_start_at=_parse_datetime(payload.get("earliest_start_at")),
        coverage_area=payload.get("coverage_area") or {},
        scope_facts=payload.get("scope_facts") or {},
        limit=int(payload.get("limit") or 5),
    )
    return JsonResponse(opportunities)


@csrf_exempt
@require_http_methods(["POST"])
def fee_schedule_pricing_collection_view(request):
    if not _internal_secret_valid(request):
        return JsonResponse({"detail": "Internal service authentication failed."}, status=403)

    payload = _load_json_body(request)
    if payload is None:
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    capability_required = (payload.get("capability_required") or "").strip()
    priced_candidates = list_fee_schedule_pricing_candidates(
        capability_required=capability_required,
        coverage_area=payload.get("coverage_area") or {},
        scope_facts=payload.get("scope_facts") or {},
        limit=int(payload.get("limit") or 5),
    )
    return JsonResponse(priced_candidates)
