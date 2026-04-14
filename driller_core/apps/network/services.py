from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from driller_core.apps.fieldlogs.models import FieldExecution

from .availability import (
    aware_end_of_day,
    aware_start_of_day,
    finish_workday_span,
    local_date,
    next_enabled_workday_after,
    next_enabled_workday_on_or_after,
    normalize_working_days,
    supported_working_days_payload,
    workday_count_for_duration,
)
from .models import (
    BookingRequest,
    DrillerBlackoutDate,
    DrillerCoverage,
    DrillerFeeLineItem,
    DrillerFeeSchedule,
    DrillerProfile,
    normalize_coverage_county_name,
    normalize_coverage_state_code,
)

ESTIMATE_811_BUFFER_DAYS = 3
MONEY_PLACES = Decimal("0.01")
logger = logging.getLogger(__name__)

EXCLUSION_NO_WORKING_DAYS = "NO_WORKING_DAYS"
EXCLUSION_COVERAGE_MISMATCH = "COVERAGE_MISMATCH"
EXCLUSION_CAPABILITY_MISMATCH = "CAPABILITY_MISMATCH"
EXCLUSION_MISSING_FEE_SCHEDULE = "MISSING_FEE_SCHEDULE"
EXCLUSION_INTERNAL_ERROR = "INTERNAL_ERROR"
EXCLUSION_FEE_SCHEDULE_UNPRICEABLE = "FEE_SCHEDULE_UNPRICEABLE"


@dataclass
class OpportunityMatch:
    driller: DrillerProfile
    start_at: datetime
    end_at: datetime
    window: dict
    fee_schedule: DrillerFeeSchedule | None
    pricing: dict | None


def _exclusion(reason_code: str, detail: str) -> dict:
    return {
        "reason_code": reason_code,
        "detail": detail,
    }


def _driller_debug_row(*, driller: DrillerProfile, exclusions: list[dict] | None = None, live_opportunity: bool = False, fee_schedule_priced: bool = False) -> dict:
    return {
        "driller": {
            "shared_uuid": str(driller.shared_uuid),
            "display_name": driller.display_name,
            "company_name": driller.company_name,
        },
        "live_opportunity": live_opportunity,
        "fee_schedule_priced": fee_schedule_priced,
        "exclusions": exclusions or [],
    }


def _capability_match(driller: DrillerProfile, capability_required: str) -> bool:
    if not capability_required:
        return True
    return capability_required in (driller.capability_keys or [])


def _requested_coverage_target(requested_coverage_area: dict | None) -> tuple[str | None, str]:
    if not isinstance(requested_coverage_area, dict):
        return None, "TX"
    county_name = normalize_coverage_county_name(requested_coverage_area.get("county"))
    state_code = normalize_coverage_state_code(
        requested_coverage_area.get("state_code") or requested_coverage_area.get("state")
    )
    return county_name or None, state_code


def coverage_payload(coverage: DrillerCoverage) -> dict:
    return {
        "id": coverage.id,
        "shared_uuid": str(coverage.shared_uuid),
        "county_name": coverage.county_name,
        "state_code": coverage.state_code,
        "active": coverage.active,
    }


def list_driller_coverages(driller: DrillerProfile, *, active_only: bool = True) -> list[dict]:
    queryset = DrillerCoverage.objects.filter(driller=driller)
    if active_only:
        queryset = queryset.filter(active=True)
    return [coverage_payload(item) for item in queryset.order_by("county_name", "state_code", "id")]


def driller_coverage_area_payload(driller: DrillerProfile) -> dict:
    items = list_driller_coverages(driller, active_only=True)
    if not items:
        return {}
    counties = [
        {
            "name": item["county_name"],
            "state_code": item["state_code"],
        }
        for item in items
    ]
    unique_states = sorted({item["state_code"] for item in items if item.get("state_code")})
    payload: dict[str, object] = {"counties": counties}
    if len(counties) == 1:
        payload["county"] = counties[0]["name"]
    if len(unique_states) == 1:
        payload["state_code"] = unique_states[0]
    return payload


def add_driller_coverage(driller: DrillerProfile, *, county_name: str | None, state_code: str | None = "TX") -> DrillerCoverage:
    normalized_county = normalize_coverage_county_name(county_name)
    if not normalized_county:
        raise ValueError("County name is required.")
    normalized_state = normalize_coverage_state_code(state_code)

    existing = DrillerCoverage.objects.filter(
        driller=driller,
        county_name=normalized_county,
        state_code=normalized_state,
    ).first()
    if existing is not None:
        if existing.active:
            raise ValueError(f"{normalized_county}, {normalized_state} is already in this driller's coverage.")
        existing.active = True
        existing.save(update_fields=["active", "updated_at"])
        return existing

    return DrillerCoverage.objects.create(
        driller=driller,
        county_name=normalized_county,
        state_code=normalized_state,
        active=True,
    )


def deactivate_driller_coverage(driller: DrillerProfile, coverage_id: int) -> DrillerCoverage | None:
    coverage = DrillerCoverage.objects.filter(driller=driller, pk=coverage_id).first()
    if coverage is None:
        return None
    if coverage.active:
        coverage.active = False
        coverage.save(update_fields=["active", "updated_at"])
    return coverage


def _coverage_match(driller: DrillerProfile, requested_coverage_area: dict | None) -> bool:
    requested_county_name, requested_state_code = _requested_coverage_target(requested_coverage_area)
    if not requested_county_name:
        return False
    return DrillerCoverage.objects.filter(
        driller=driller,
        county_name=requested_county_name,
        state_code=requested_state_code,
        active=True,
    ).exists()


def _coverage_mismatch_exclusion(driller: DrillerProfile, requested_coverage_area: dict | None) -> dict:
    requested_county_name, requested_state_code = _requested_coverage_target(requested_coverage_area)
    if not requested_county_name:
        return _exclusion(
            EXCLUSION_COVERAGE_MISMATCH,
            (
                f"Requested project county is unavailable for county-based driller matching, "
                f"so {driller.display_name} cannot be evaluated."
            ),
        )
    return _exclusion(
        EXCLUSION_COVERAGE_MISMATCH,
        f"Driller {driller.display_name} does not cover {requested_county_name}, {requested_state_code}.",
    )


def _requested_duration_days(estimated_days) -> Decimal:
    value = Decimal(estimated_days or 0)
    if value <= 0:
        value = Decimal("1.00")
    return value


def requested_duration_workdays(estimated_days) -> int:
    return workday_count_for_duration(_requested_duration_days(estimated_days))


def _active_fee_schedule(driller: DrillerProfile) -> DrillerFeeSchedule | None:
    return driller.fee_schedules.filter(is_active=True).order_by("id").first()


def _opportunity_cutoff_start() -> datetime:
    target_date = timezone.localdate() + timedelta(days=ESTIMATE_811_BUFFER_DAYS)
    naive = datetime.combine(target_date, time.min)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def _estimate_earliest_start(requested_start_at):
    cutoff = _opportunity_cutoff_start()
    if requested_start_at is None:
        return cutoff
    return max(requested_start_at, cutoff)


def driller_working_days(driller: DrillerProfile) -> list[str]:
    return normalize_working_days(driller.working_days)


def active_blackout_dates_for_driller(driller: DrillerProfile) -> set:
    return set(
        DrillerBlackoutDate.objects.filter(driller=driller, active=True).values_list("date", flat=True)
    )


def latest_commitment_end_at_for_driller(
    driller: DrillerProfile,
    *,
    booking_to_exclude: BookingRequest | None = None,
) -> datetime | None:
    working_days = driller_working_days(driller)
    blackout_dates = active_blackout_dates_for_driller(driller)
    latest_end_at: datetime | None = None
    active_execution_statuses = {
        FieldExecution.Status.ASSIGNED,
        FieldExecution.Status.IN_PROGRESS,
        FieldExecution.Status.SUBMITTED,
        FieldExecution.Status.NEEDS_CORRECTION,
    }

    committed_bookings = BookingRequest.objects.filter(
        assigned_driller=driller,
        status=BookingRequest.Status.COMMITTED,
        committed_end_at__isnull=False,
    ).exclude(field_execution__status=FieldExecution.Status.ACCEPTED)
    if booking_to_exclude is not None:
        committed_bookings = committed_bookings.exclude(pk=booking_to_exclude.pk)
    committed_booking_end_at = committed_bookings.order_by("-committed_end_at").values_list(
        "committed_end_at",
        flat=True,
    ).first()
    if committed_booking_end_at is not None:
        latest_end_at = committed_booking_end_at

    executions = (
        FieldExecution.objects.select_related("booking_request")
        .filter(assigned_driller=driller, status__in=active_execution_statuses)
        .order_by("scheduled_start_date", "id")
    )
    for execution in executions:
        if execution.booking_request_id:
            if booking_to_exclude is not None and execution.booking_request_id == booking_to_exclude.id:
                continue
            if execution.booking_request and execution.booking_request.committed_end_at:
                if latest_end_at is None or execution.booking_request.committed_end_at > latest_end_at:
                    latest_end_at = execution.booking_request.committed_end_at
                continue
        if execution.scheduled_start_date is None:
            continue
        start_date = next_enabled_workday_on_or_after(
            execution.scheduled_start_date,
            working_days,
            blackout_dates,
        )
        if start_date is None:
            continue
        end_date = finish_workday_span(
            start_date,
            required_workdays=requested_duration_workdays(execution.estimated_days),
            working_days=working_days,
            blackout_dates=blackout_dates,
        )
        if end_date is None:
            continue
        derived_end_at = aware_end_of_day(end_date)
        if latest_end_at is None or derived_end_at > latest_end_at:
            latest_end_at = derived_end_at
    return latest_end_at


def next_available_start_at_for_driller(
    driller: DrillerProfile,
    *,
    baseline_datetime: datetime | None = None,
    booking_to_exclude: BookingRequest | None = None,
) -> datetime | None:
    working_days = driller_working_days(driller)
    normalized_working_days = normalize_working_days(working_days)
    if not normalized_working_days:
        return None
    blackout_dates = active_blackout_dates_for_driller(driller)

    baseline_date = local_date(baseline_datetime)
    latest_commitment_end_at = latest_commitment_end_at_for_driller(
        driller,
        booking_to_exclude=booking_to_exclude,
    )
    latest_commitment_end_date = local_date(latest_commitment_end_at) if latest_commitment_end_at else None

    if latest_commitment_end_date is not None and latest_commitment_end_date >= baseline_date:
        next_start_date = next_enabled_workday_after(
            latest_commitment_end_date,
            normalized_working_days,
            blackout_dates,
        )
    else:
        next_start_date = next_enabled_workday_on_or_after(
            baseline_date,
            normalized_working_days,
            blackout_dates,
        )

    if next_start_date is None:
        return None
    return aware_start_of_day(next_start_date)


def availability_window_for_driller(
    driller: DrillerProfile,
    *,
    baseline_datetime: datetime | None,
    estimated_days,
    booking_to_exclude: BookingRequest | None = None,
) -> dict | None:
    bounds = availability_window_bounds_for_driller(
        driller,
        baseline_datetime=baseline_datetime,
        estimated_days=estimated_days,
        booking_to_exclude=booking_to_exclude,
    )
    if bounds is None:
        return None
    start_at, end_at, latest_commitment_end_at, normalized_working_days, required_workdays = bounds
    return {
        "start_at": start_at.isoformat(),
        "end_at": end_at.isoformat(),
        "required_workdays": required_workdays,
        "working_days": list(normalized_working_days),
        "supported_working_days": supported_working_days_payload(),
        "latest_commitment_end_at": latest_commitment_end_at.isoformat() if latest_commitment_end_at else None,
    }


def availability_window_bounds_for_driller(
    driller: DrillerProfile,
    *,
    baseline_datetime: datetime | None,
    estimated_days,
    booking_to_exclude: BookingRequest | None = None,
) -> tuple[datetime, datetime, datetime | None, list[str], int] | None:
    working_days = driller_working_days(driller)
    normalized_working_days = normalize_working_days(working_days)
    if not normalized_working_days:
        return None
    blackout_dates = active_blackout_dates_for_driller(driller)

    start_at = next_available_start_at_for_driller(
        driller,
        baseline_datetime=baseline_datetime,
        booking_to_exclude=booking_to_exclude,
    )
    if start_at is None:
        return None

    required_workdays = requested_duration_workdays(estimated_days)
    end_date = finish_workday_span(
        local_date(start_at),
        required_workdays=required_workdays,
        working_days=normalized_working_days,
        blackout_dates=blackout_dates,
    )
    if end_date is None:
        return None

    latest_commitment_end_at = latest_commitment_end_at_for_driller(
        driller,
        booking_to_exclude=booking_to_exclude,
    )
    return (
        start_at,
        aware_end_of_day(end_date),
        latest_commitment_end_at,
        list(normalized_working_days),
        required_workdays,
    )


def _scope_decimal(scope_facts: dict, key: str, default: str = "0.00") -> Decimal:
    try:
        return Decimal(str(scope_facts.get(key, default) or default))
    except Exception:
        return Decimal(default)


def _scope_text(scope_facts: dict, key: str) -> str:
    return str(scope_facts.get(key) or "").strip()


def _quantize_money(amount: Decimal) -> Decimal:
    return amount.quantize(MONEY_PLACES)


def price_scope_with_fee_schedule(fee_schedule: DrillerFeeSchedule | None, scope_facts: dict | None) -> dict | None:
    if fee_schedule is None:
        return None

    scope_facts = scope_facts or {}
    bore_count = _scope_decimal(scope_facts, "bore_count", "0.00")
    bore_depth_ft = _scope_decimal(scope_facts, "bore_depth_ft", "0.00")
    standby_days = _scope_decimal(scope_facts, "standby_days", "0.00")
    total_footage = _scope_decimal(scope_facts, "total_linear_feet", "0.00")
    if total_footage <= 0:
        total_footage = _scope_decimal(scope_facts, "total_footage", "0.00")
    if total_footage <= 0:
        total_footage = bore_count * bore_depth_ft
    requires_casing = bool(scope_facts.get("requires_casing"))
    requires_rock_drilling = bool(scope_facts.get("requires_rock_drilling"))
    travel_zone = _scope_text(scope_facts, "travel_zone").lower()

    subtotal = Decimal("0.00")
    line_items: list[dict] = []
    minimum_charge: Decimal | None = None

    for line_item in fee_schedule.line_items.order_by("sort_order", "id"):
        quantity = Decimal("0.00")
        if line_item.line_item_type == DrillerFeeLineItem.LineItemType.MOBILIZATION:
            quantity = Decimal("1.00")
        elif line_item.line_item_type == DrillerFeeLineItem.LineItemType.PER_BORE:
            quantity = bore_count
        elif line_item.line_item_type == DrillerFeeLineItem.LineItemType.PER_FOOT:
            quantity = total_footage
        elif line_item.line_item_type == DrillerFeeLineItem.LineItemType.STANDBY_DAY:
            quantity = standby_days
        elif line_item.line_item_type == DrillerFeeLineItem.LineItemType.CASING_PER_BORE and requires_casing:
            quantity = bore_count
        elif line_item.line_item_type == DrillerFeeLineItem.LineItemType.ROCK_DRILLING_PER_BORE and requires_rock_drilling:
            quantity = bore_count
        elif line_item.line_item_type == DrillerFeeLineItem.LineItemType.TRAVEL_ZONE_ADDER:
            metadata_zone = _scope_text(line_item.metadata, "travel_zone").lower()
            if travel_zone and (not metadata_zone or metadata_zone == travel_zone):
                quantity = Decimal("1.00")
        elif line_item.line_item_type == DrillerFeeLineItem.LineItemType.MINIMUM_CHARGE:
            minimum_charge = max(minimum_charge or Decimal("0.00"), line_item.amount)
            continue

        if quantity <= 0:
            continue

        total = _quantize_money(quantity * line_item.amount)
        subtotal += total
        line_items.append(
            {
                "type": line_item.line_item_type,
                "label": line_item.label,
                "quantity": str(quantity),
                "unit_amount": str(_quantize_money(line_item.amount)),
                "total_amount": str(total),
                "metadata": line_item.metadata,
            }
        )

    if minimum_charge is not None and subtotal < minimum_charge:
        adjustment = _quantize_money(minimum_charge - subtotal)
        subtotal = minimum_charge
        line_items.append(
            {
                "type": DrillerFeeLineItem.LineItemType.MINIMUM_CHARGE,
                "label": "Minimum charge adjustment",
                "quantity": "1.00",
                "unit_amount": str(adjustment),
                "total_amount": str(adjustment),
                "metadata": {},
            }
        )

    return {
        "fee_schedule_id": fee_schedule.id,
        "fee_schedule_name": fee_schedule.name,
        "currency": fee_schedule.currency.lower(),
        "line_items": line_items,
        "total_amount": str(_quantize_money(subtotal)),
        "scope_snapshot": {
            "bore_count": str(bore_count),
            "bore_depth_ft": str(bore_depth_ft),
            "total_footage": str(total_footage),
            "standby_days": str(standby_days),
            "requires_casing": requires_casing,
            "requires_rock_drilling": requires_rock_drilling,
            "travel_zone": travel_zone or None,
        },
    }


def _match_reason_for_window(
    *,
    driller: DrillerProfile,
    requested_start_at,
    estimated_days,
    booking_to_exclude: BookingRequest | None = None,
) -> tuple[OpportunityMatch | None, list[dict]]:
    exclusions: list[dict] = []

    working_days = driller_working_days(driller)
    if not working_days:
        return None, [
            _exclusion(
                EXCLUSION_NO_WORKING_DAYS,
                f"{driller.display_name} does not have any enabled working days.",
            )
        ]

    bounds = availability_window_bounds_for_driller(
        driller,
        baseline_datetime=requested_start_at,
        estimated_days=estimated_days,
        booking_to_exclude=booking_to_exclude,
    )
    if bounds is None:
        return None, [
            _exclusion(
                EXCLUSION_NO_WORKING_DAYS,
                f"{driller.display_name} could not derive a next available workday from the current working-day configuration.",
            )
        ]

    start_at, end_at, latest_commitment_end_at, normalized_working_days, required_workdays = bounds
    fee_schedule = _active_fee_schedule(driller)
    return OpportunityMatch(
        driller=driller,
        window={
            "start_at": start_at.isoformat(),
            "end_at": end_at.isoformat(),
            "required_workdays": required_workdays,
            "working_days": normalized_working_days,
            "supported_working_days": supported_working_days_payload(),
            "latest_commitment_end_at": latest_commitment_end_at.isoformat() if latest_commitment_end_at else None,
            "blackout_count": len(active_blackout_dates_for_driller(driller)),
        },
        start_at=start_at,
        end_at=end_at,
        fee_schedule=fee_schedule,
        pricing=None,
    ), []


def list_schedule_opportunities(
    *,
    capability_required: str,
    estimated_days,
    earliest_start_at=None,
    coverage_area: dict | None = None,
    scope_facts: dict | None = None,
    limit: int = 5,
) -> dict:
    requested_start_at = _estimate_earliest_start(earliest_start_at)
    items: list[dict] = []
    debug_reasons: list[str] = []
    driller_debug: list[dict] = []
    matches: list[tuple[OpportunityMatch, dict | None]] = []

    for driller in DrillerProfile.objects.filter(is_active=True).order_by("company_name", "display_name", "id"):
        if not _capability_match(driller, capability_required):
            exclusion = _exclusion(
                EXCLUSION_CAPABILITY_MISMATCH,
                f"Driller {driller.display_name} does not advertise capability {capability_required}.",
            )
            debug_reasons.append(exclusion["detail"])
            driller_debug.append(_driller_debug_row(driller=driller, exclusions=[exclusion]))
            continue
        if not _coverage_match(driller, coverage_area):
            exclusion = _coverage_mismatch_exclusion(driller, coverage_area)
            debug_reasons.append(exclusion["detail"])
            driller_debug.append(_driller_debug_row(driller=driller, exclusions=[exclusion]))
            continue

        match, exclusions = _match_reason_for_window(
            driller=driller,
            requested_start_at=requested_start_at,
            estimated_days=estimated_days,
            booking_to_exclude=None,
        )
        if match is None:
            debug_reasons.extend(exclusion["detail"] for exclusion in exclusions)
            driller_debug.append(_driller_debug_row(driller=driller, exclusions=exclusions))
            continue

        try:
            pricing = price_scope_with_fee_schedule(match.fee_schedule, scope_facts)
        except Exception:
            exclusion = _exclusion(
                EXCLUSION_INTERNAL_ERROR,
                f"Pricing could not be generated for {driller.display_name}.",
            )
            debug_reasons.append(exclusion["detail"])
            driller_debug.append(_driller_debug_row(driller=driller, exclusions=[exclusion]))
            continue

        driller_debug.append(_driller_debug_row(driller=driller, live_opportunity=True))
        matches.append((match, pricing))

    matches.sort(
        key=lambda item: (
            item[0].start_at,
            item[0].driller.company_name.lower(),
            item[0].driller.display_name.lower(),
            item[0].driller.id,
        )
    )
    for match, pricing in matches[:limit]:
        items.append(
            {
                "driller": {
                    "shared_uuid": str(match.driller.shared_uuid),
                    "display_name": match.driller.display_name,
                    "company_name": match.driller.company_name,
                    "capability_keys": match.driller.capability_keys,
                    "coverage_area": driller_coverage_area_payload(match.driller),
                },
                "window": match.window,
                "fee_schedule": {
                    "id": match.fee_schedule.id,
                    "name": match.fee_schedule.name,
                    "currency": match.fee_schedule.currency.lower(),
                } if match.fee_schedule else None,
                "pricing": pricing,
            }
        )

    response = {
        "items": items,
        "buffer_days": ESTIMATE_811_BUFFER_DAYS,
        "earliest_considered_start_at": requested_start_at.isoformat() if requested_start_at else None,
        "matcher_reason": debug_reasons[0] if debug_reasons and not items else None,
        "debug_reasons": debug_reasons[:limit],
        "driller_debug": driller_debug,
    }
    logger.info(
        "schedule_opportunity_evaluation %s",
        json.dumps(
            {
                "event": "schedule_opportunity_evaluation",
                "capability_required": capability_required,
                "estimated_days": str(_requested_duration_days(estimated_days)),
                "earliest_requested_start_at": earliest_start_at.isoformat() if earliest_start_at else None,
                "earliest_considered_start_at": response["earliest_considered_start_at"],
                "coverage_area": coverage_area or {},
                "live_opportunities_found": bool(items),
                "driller_debug": driller_debug,
            },
            sort_keys=True,
            default=str,
        ),
    )
    return response


def list_fee_schedule_pricing_candidates(
    *,
    capability_required: str,
    coverage_area: dict | None = None,
    scope_facts: dict | None = None,
    limit: int = 5,
) -> dict:
    items: list[dict] = []
    debug_reasons: list[str] = []
    driller_debug: list[dict] = []

    for driller in DrillerProfile.objects.filter(is_active=True).order_by("company_name", "display_name", "id"):
        if not _capability_match(driller, capability_required):
            exclusion = _exclusion(
                EXCLUSION_CAPABILITY_MISMATCH,
                f"Driller {driller.display_name} does not advertise capability {capability_required}.",
            )
            debug_reasons.append(exclusion["detail"])
            driller_debug.append(_driller_debug_row(driller=driller, exclusions=[exclusion]))
            continue
        if not _coverage_match(driller, coverage_area):
            exclusion = _coverage_mismatch_exclusion(driller, coverage_area)
            debug_reasons.append(exclusion["detail"])
            driller_debug.append(_driller_debug_row(driller=driller, exclusions=[exclusion]))
            continue

        fee_schedule = _active_fee_schedule(driller)
        if fee_schedule is None:
            exclusion = _exclusion(
                EXCLUSION_MISSING_FEE_SCHEDULE,
                f"Driller {driller.display_name} does not have an active fee schedule.",
            )
            debug_reasons.append(exclusion["detail"])
            driller_debug.append(_driller_debug_row(driller=driller, exclusions=[exclusion]))
            continue

        try:
            pricing = price_scope_with_fee_schedule(fee_schedule, scope_facts)
        except Exception:
            exclusion = _exclusion(
                EXCLUSION_INTERNAL_ERROR,
                f"Active fee schedule {fee_schedule.name} could not be evaluated for {driller.display_name}.",
            )
            debug_reasons.append(exclusion["detail"])
            driller_debug.append(_driller_debug_row(driller=driller, exclusions=[exclusion]))
            continue
        if pricing is None or _scope_decimal(pricing, "total_amount", "0.00") <= 0:
            exclusion = _exclusion(
                EXCLUSION_FEE_SCHEDULE_UNPRICEABLE,
                f"Active fee schedule {fee_schedule.name} could not produce pricing for {driller.display_name}.",
            )
            debug_reasons.append(exclusion["detail"])
            driller_debug.append(_driller_debug_row(driller=driller, exclusions=[exclusion]))
            continue

        driller_debug.append(_driller_debug_row(driller=driller, fee_schedule_priced=True))
        items.append(
            {
                "driller": {
                    "shared_uuid": str(driller.shared_uuid),
                    "display_name": driller.display_name,
                    "company_name": driller.company_name,
                    "capability_keys": driller.capability_keys,
                    "coverage_area": driller_coverage_area_payload(driller),
                },
                "fee_schedule": {
                    "id": fee_schedule.id,
                    "name": fee_schedule.name,
                    "currency": fee_schedule.currency.lower(),
                },
                "pricing": pricing,
            }
        )
        if len(items) >= limit:
            break

    return {
        "items": items,
        "matcher_reason": debug_reasons[0] if debug_reasons and not items else None,
        "debug_reasons": debug_reasons[:limit],
        "driller_debug": driller_debug,
    }


@transaction.atomic
def evaluate_and_commit_booking(booking: BookingRequest) -> BookingRequest:
    last_reason = "No driller could derive a valid next available workday for this request."
    committed_matches: list[OpportunityMatch] = []

    for driller in DrillerProfile.objects.filter(is_active=True).order_by("company_name", "display_name", "id"):
        if not _capability_match(driller, booking.capability_required):
            last_reason = f"Driller {driller.display_name} does not advertise capability {booking.capability_required}."
            continue
        if not _coverage_match(driller, booking.coverage_area):
            last_reason = _coverage_mismatch_exclusion(driller, booking.coverage_area)["detail"]
            continue

        match, reason = _match_reason_for_window(
            driller=driller,
            requested_start_at=_estimate_earliest_start(booking.earliest_start_at),
            estimated_days=booking.estimated_days,
            booking_to_exclude=booking,
        )
        if match is None:
            if isinstance(reason, list) and reason:
                last_reason = str(reason[0].get("detail") or last_reason)
            else:
                last_reason = str(reason or last_reason)
            continue
        committed_matches.append(match)

    if committed_matches:
        committed_matches.sort(
            key=lambda item: (
                item.start_at,
                item.driller.company_name.lower(),
                item.driller.display_name.lower(),
                item.driller.id,
            )
        )
        match = committed_matches[0]
        booking.status = BookingRequest.Status.COMMITTED
        booking.assigned_driller = match.driller
        booking.committed_start_at = match.start_at
        booking.committed_end_at = match.end_at
        booking.blocking_reason = ""
        booking.response_payload = {
            "assigned_driller": match.driller.display_name,
            "capability_keys": match.driller.capability_keys,
            "coverage_area": driller_coverage_area_payload(match.driller),
            "window": match.window,
        }
        booking.save()
        from driller_core.apps.fieldlogs.services import ensure_field_execution_for_booking

        ensure_field_execution_for_booking(booking)
        return booking

    booking.status = BookingRequest.Status.BLOCKED
    booking.blocking_reason = last_reason
    booking.response_payload = {"matcher_reason": last_reason}
    booking.save()
    return booking


def booking_payload(booking: BookingRequest) -> dict:
    return {
        "booking_id": booking.id,
        "booking_reference": str(booking.shared_uuid),
        "status": booking.status,
        "project_number": booking.project_number or None,
        "assigned_driller": booking.assigned_driller.display_name if booking.assigned_driller else None,
        "committed_start_at": booking.committed_start_at.isoformat() if booking.committed_start_at else None,
        "committed_end_at": booking.committed_end_at.isoformat() if booking.committed_end_at else None,
        "blocking_reason": booking.blocking_reason or None,
    }
