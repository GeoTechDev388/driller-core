from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING

from django.utils import timezone


WORKING_DAY_DEFINITIONS = [
    {"code": "monday", "label": "Monday", "index": 0},
    {"code": "tuesday", "label": "Tuesday", "index": 1},
    {"code": "wednesday", "label": "Wednesday", "index": 2},
    {"code": "thursday", "label": "Thursday", "index": 3},
    {"code": "friday", "label": "Friday", "index": 4},
    {"code": "saturday", "label": "Saturday", "index": 5},
    {"code": "sunday", "label": "Sunday", "index": 6},
]

WORKING_DAY_CODE_TO_INDEX = {
    item["code"]: int(item["index"]) for item in WORKING_DAY_DEFINITIONS
}
WORKING_DAY_INDEX_TO_CODE = {
    int(item["index"]): item["code"] for item in WORKING_DAY_DEFINITIONS
}


def default_working_days() -> list[str]:
    return ["monday", "tuesday", "wednesday", "thursday", "friday"]


def normalize_working_days(values) -> list[str]:
    raw_values = values if isinstance(values, (list, tuple)) else []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        normalized_value = str(value or "").strip().lower()
        if normalized_value not in WORKING_DAY_CODE_TO_INDEX or normalized_value in seen:
            continue
        normalized.append(normalized_value)
        seen.add(normalized_value)
    normalized.sort(key=lambda item: WORKING_DAY_CODE_TO_INDEX[item])
    return normalized


def supported_working_days_payload() -> list[dict]:
    return [dict(item) for item in WORKING_DAY_DEFINITIONS]


def working_day_label_map() -> dict[str, str]:
    return {str(item["code"]): str(item["label"]) for item in WORKING_DAY_DEFINITIONS}


def effective_working_days(values) -> list[str]:
    normalized = normalize_working_days(values)
    return normalized or default_working_days()


def workday_count_for_duration(estimated_days) -> int:
    value = Decimal(str(estimated_days or "0.00"))
    if value <= 0:
        value = Decimal("1.00")
    return max(1, int(value.to_integral_value(rounding=ROUND_CEILING)))


def local_date(value: datetime | date | None = None) -> date:
    if value is None:
        return timezone.localdate()
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    next_value = value
    if timezone.is_aware(next_value):
        next_value = timezone.localtime(next_value, timezone.get_current_timezone())
    return next_value.date()


def aware_start_of_day(value: date) -> datetime:
    return timezone.make_aware(datetime.combine(value, time.min), timezone.get_current_timezone())


def aware_end_of_day(value: date) -> datetime:
    return timezone.make_aware(datetime.combine(value, time.max), timezone.get_current_timezone())


def is_enabled_workday(value: date, working_days: list[str]) -> bool:
    return value.weekday() in {
        WORKING_DAY_CODE_TO_INDEX[item] for item in normalize_working_days(working_days)
    }


def is_valid_workday(
    value: date,
    working_days: list[str],
    blackout_dates: set[date] | None = None,
) -> bool:
    return is_enabled_workday(value, working_days) and value not in (blackout_dates or set())


def next_enabled_workday_on_or_after(
    anchor_date: date,
    working_days: list[str],
    blackout_dates: set[date] | None = None,
) -> date | None:
    normalized = normalize_working_days(working_days)
    if not normalized:
        return None
    current = anchor_date
    for _ in range(14):
        if is_valid_workday(current, normalized, blackout_dates):
            return current
        current += timedelta(days=1)
    while True:
        if is_valid_workday(current, normalized, blackout_dates):
            return current
        current += timedelta(days=1)


def next_enabled_workday_after(
    anchor_date: date,
    working_days: list[str],
    blackout_dates: set[date] | None = None,
) -> date | None:
    return next_enabled_workday_on_or_after(anchor_date + timedelta(days=1), working_days, blackout_dates)


def finish_workday_span(
    start_date: date,
    *,
    required_workdays: int,
    working_days: list[str],
    blackout_dates: set[date] | None = None,
) -> date | None:
    normalized = normalize_working_days(working_days)
    if not normalized:
        return None

    current = start_date
    counted = 0
    while True:
        if is_valid_workday(current, normalized, blackout_dates):
            counted += 1
            if counted >= max(1, required_workdays):
                return current
        current += timedelta(days=1)
