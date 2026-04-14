from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .availability import normalize_working_days, supported_working_days_payload
from .geography import (
    DEFAULT_DRILLER_STATE_CODE,
    ensure_supported_counties,
    supported_states_payload,
)
from .models import (
    DrillerBlackoutDate,
    DrillerCoverage,
    DrillerFeeLineItem,
    DrillerFeeSchedule,
    DrillerProfile,
    normalize_coverage_state_code,
)
from .services import (
    list_driller_coverages,
    latest_commitment_end_at_for_driller,
    next_available_start_at_for_driller,
)


PRICING_LINE_ITEM_DEFINITIONS = [
    {
        "line_item_type": DrillerFeeLineItem.LineItemType.MOBILIZATION,
        "label": "Mobilization",
        "description": "One-time mobilization and setup charge.",
        "sort_order": 10,
        "metadata_fields": [],
    },
    {
        "line_item_type": DrillerFeeLineItem.LineItemType.PER_BORE,
        "label": "Per bore",
        "description": "Charge applied per planned boring.",
        "sort_order": 20,
        "metadata_fields": [],
    },
    {
        "line_item_type": DrillerFeeLineItem.LineItemType.PER_FOOT,
        "label": "Per foot",
        "description": "Charge applied to total drilled footage.",
        "sort_order": 30,
        "metadata_fields": [],
    },
    {
        "line_item_type": DrillerFeeLineItem.LineItemType.STANDBY_DAY,
        "label": "Standby day",
        "description": "Charge applied per standby day.",
        "sort_order": 40,
        "metadata_fields": [],
    },
    {
        "line_item_type": DrillerFeeLineItem.LineItemType.CASING_PER_BORE,
        "label": "Casing per bore",
        "description": "Optional adder when casing is required.",
        "sort_order": 50,
        "metadata_fields": [],
    },
    {
        "line_item_type": DrillerFeeLineItem.LineItemType.ROCK_DRILLING_PER_BORE,
        "label": "Rock drilling premium",
        "description": "Optional adder when rock drilling is required.",
        "sort_order": 60,
        "metadata_fields": [],
    },
    {
        "line_item_type": DrillerFeeLineItem.LineItemType.TRAVEL_ZONE_ADDER,
        "label": "Travel zone adder",
        "description": "Optional adder for outer or premium travel zones.",
        "sort_order": 70,
        "metadata_fields": [
            {
                "name": "travel_zone",
                "label": "Travel zone key",
                "placeholder": "outer",
            }
        ],
    },
    {
        "line_item_type": DrillerFeeLineItem.LineItemType.MINIMUM_CHARGE,
        "label": "Minimum charge",
        "description": "Minimum total charge floor for the active schedule.",
        "sort_order": 80,
        "metadata_fields": [],
    },
]

PRICING_LINE_ITEM_DEFINITION_MAP = {
    str(item["line_item_type"]): item for item in PRICING_LINE_ITEM_DEFINITIONS
}


def _parse_money_value(value, *, field_name: str) -> Decimal:
    try:
        amount = Decimal(str(value or "").strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal amount.") from exc
    if amount < Decimal("0.00"):
        raise ValueError(f"{field_name} must be zero or greater.")
    return amount.quantize(Decimal("0.01"))


def fee_schedule_payload(schedule: DrillerFeeSchedule | None) -> dict | None:
    if schedule is None:
        return None
    return {
        "id": schedule.id,
        "name": schedule.name,
        "currency": schedule.currency.lower(),
        "is_active": schedule.is_active,
        "notes": schedule.notes,
    }


def fee_line_item_payload(item: DrillerFeeLineItem) -> dict:
    return {
        "id": item.id,
        "line_item_type": item.line_item_type,
        "label": item.label,
        "amount": str(item.amount.quantize(Decimal("0.01"))),
        "metadata": item.metadata or {},
        "sort_order": item.sort_order,
    }


def blackout_date_payload(item: DrillerBlackoutDate) -> dict:
    return {
        "id": item.id,
        "shared_uuid": str(item.shared_uuid),
        "date": item.date.isoformat(),
        "reason": item.reason,
        "active": item.active,
    }


def list_driller_blackouts(driller: DrillerProfile, *, active_only: bool = True) -> list[dict]:
    queryset = DrillerBlackoutDate.objects.filter(driller=driller)
    if active_only:
        queryset = queryset.filter(active=True)
    return [blackout_date_payload(item) for item in queryset.order_by("date", "id")]


def coverage_settings_payload(driller: DrillerProfile) -> dict:
    items = list_driller_coverages(driller, active_only=True)
    selected_by_state: dict[str, list[str]] = {}
    for item in items:
        selected_by_state.setdefault(item["state_code"], []).append(item["county_name"])
    for state_code in list(selected_by_state.keys()):
        selected_by_state[state_code] = sorted(selected_by_state[state_code])
    return {
        "items": items,
        "supported_states": supported_states_payload(),
        "default_state_code": DEFAULT_DRILLER_STATE_CODE,
        "selected_by_state": selected_by_state,
    }


def availability_settings_payload(driller: DrillerProfile) -> dict:
    working_days = normalize_working_days(driller.working_days)
    blackout_dates = list_driller_blackouts(driller, active_only=True)
    next_available_start_at = next_available_start_at_for_driller(
        driller,
        baseline_datetime=None,
    )
    latest_commitment_end_at = latest_commitment_end_at_for_driller(driller)
    return {
        "model": "workday_interim_v1",
        "summary": {
            "next_available_start_at": next_available_start_at.isoformat() if next_available_start_at else None,
            "latest_commitment_end_at": latest_commitment_end_at.isoformat() if latest_commitment_end_at else None,
            "enabled_day_count": len(working_days),
            "blackout_count": len(blackout_dates),
        },
        "working_days": working_days,
        "supported_working_days": supported_working_days_payload(),
        "blackout_dates": blackout_dates,
    }


def pricing_settings_payload(driller: DrillerProfile) -> dict:
    schedule = driller.fee_schedules.filter(is_active=True).order_by("id").first()
    line_items = []
    if schedule is not None:
        line_items = [
            fee_line_item_payload(item)
            for item in schedule.line_items.order_by("sort_order", "id")
        ]
    return {
        "active_fee_schedule": fee_schedule_payload(schedule),
        "line_items": line_items,
        "supported_line_items": PRICING_LINE_ITEM_DEFINITIONS,
    }


def driller_settings_payload(driller: DrillerProfile) -> dict:
    return {
        "coverage": coverage_settings_payload(driller),
        "availability": availability_settings_payload(driller),
        "pricing": pricing_settings_payload(driller),
    }


@transaction.atomic
def replace_driller_coverages_for_state(
    driller: DrillerProfile,
    *,
    state_code: str | None,
    county_names: list[str] | tuple[str, ...],
) -> dict:
    normalized_state = normalize_coverage_state_code(state_code)
    selected_counties = ensure_supported_counties(
        state_code=normalized_state,
        county_names=county_names,
    )
    selected_lookup = set(selected_counties)

    existing_coverages = {
        coverage.county_name: coverage
        for coverage in DrillerCoverage.objects.filter(
            driller=driller,
            state_code=normalized_state,
        )
    }

    for county_name in selected_counties:
        coverage = existing_coverages.get(county_name)
        if coverage is None:
            DrillerCoverage.objects.create(
                driller=driller,
                state_code=normalized_state,
                county_name=county_name,
                active=True,
            )
            continue
        if not coverage.active:
            coverage.active = True
            coverage.save(update_fields=["active", "updated_at"])

    for county_name, coverage in existing_coverages.items():
        should_be_active = county_name in selected_lookup
        if coverage.active != should_be_active:
            coverage.active = should_be_active
            coverage.save(update_fields=["active", "updated_at"])

    return coverage_settings_payload(driller)


@transaction.atomic
def replace_availability_settings(
    driller: DrillerProfile,
    *,
    working_days_payload: list[str] | tuple[str, ...],
) -> dict:
    normalized_working_days = normalize_working_days(working_days_payload)
    if not normalized_working_days:
        raise ValueError("Select at least one working day.")

    driller.working_days = normalized_working_days
    driller.save(update_fields=["working_days", "updated_at"])
    return availability_settings_payload(driller)


@transaction.atomic
def add_driller_blackout_date(
    driller: DrillerProfile,
    *,
    blackout_date: date,
    reason: str | None = None,
) -> dict:
    normalized_reason = str(reason or "").strip()
    existing = DrillerBlackoutDate.objects.filter(driller=driller, date=blackout_date).first()
    if existing is not None:
        if existing.active:
            raise ValueError(f"{blackout_date.isoformat()} is already blocked for this driller.")
        existing.active = True
        existing.reason = normalized_reason
        existing.save(update_fields=["active", "reason", "updated_at"])
    else:
        existing = DrillerBlackoutDate.objects.create(
            driller=driller,
            date=blackout_date,
            reason=normalized_reason,
            active=True,
        )
    return blackout_date_payload(existing)


@transaction.atomic
def deactivate_driller_blackout_date(driller: DrillerProfile, blackout_id: int) -> DrillerBlackoutDate | None:
    blackout = DrillerBlackoutDate.objects.filter(driller=driller, pk=blackout_id).first()
    if blackout is None:
        return None
    if blackout.active:
        blackout.active = False
        blackout.save(update_fields=["active", "updated_at"])
    return blackout


@transaction.atomic
def replace_pricing_settings(
    driller: DrillerProfile,
    *,
    schedule_name: str | None,
    currency: str | None,
    notes: str | None,
    line_items_payload: list[dict],
) -> dict:
    normalized_name = str(schedule_name or "").strip() or "Portal Managed Pricing"
    normalized_currency = str(currency or "usd").strip().lower() or "usd"
    normalized_notes = str(notes or "").strip()

    normalized_items: list[dict] = []
    seen_line_types: set[str] = set()
    for item in line_items_payload:
        line_item_type = str(item.get("line_item_type") or "").strip()
        definition = PRICING_LINE_ITEM_DEFINITION_MAP.get(line_item_type)
        if definition is None:
            raise ValueError(f"{line_item_type or 'Line item'} is not a supported pricing line.")
        if line_item_type in seen_line_types:
            raise ValueError(f"{line_item_type} can only appear once in the active schedule.")
        seen_line_types.add(line_item_type)
        metadata = dict(item.get("metadata") or {})
        travel_zone = str(item.get("travel_zone") or metadata.get("travel_zone") or "").strip().lower()
        if travel_zone:
            metadata["travel_zone"] = travel_zone
        elif line_item_type == DrillerFeeLineItem.LineItemType.TRAVEL_ZONE_ADDER:
            metadata = {}
        normalized_items.append(
            {
                "line_item_type": line_item_type,
                "label": str(definition["label"]),
                "amount": _parse_money_value(item.get("amount"), field_name=str(definition["label"])),
                "metadata": metadata,
                "sort_order": int(definition["sort_order"]),
            }
        )

    schedule = driller.fee_schedules.filter(is_active=True).order_by("id").first()
    if schedule is None:
        schedule = DrillerFeeSchedule.objects.create(
            driller=driller,
            name=normalized_name,
            currency=normalized_currency,
            is_active=True,
            notes=normalized_notes,
        )
    else:
        schedule.name = normalized_name
        schedule.currency = normalized_currency
        schedule.notes = normalized_notes
        schedule.is_active = True
        schedule.save(update_fields=["name", "currency", "notes", "is_active", "updated_at"])

    driller.fee_schedules.exclude(pk=schedule.pk).filter(is_active=True).update(is_active=False)
    schedule.line_items.all().delete()

    for item in normalized_items:
        DrillerFeeLineItem.objects.create(
            fee_schedule=schedule,
            line_item_type=item["line_item_type"],
            label=item["label"],
            amount=item["amount"],
            metadata=item["metadata"],
            sort_order=item["sort_order"],
        )

    return pricing_settings_payload(driller)
