from __future__ import annotations

from decimal import Decimal
import uuid

from django.core.validators import MinValueValidator
from django.db import models

from .availability import default_working_days, normalize_working_days

class NetworkTimestampedModel(models.Model):
    shared_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def normalize_coverage_county_name(value: str | None) -> str:
    text = " ".join(str(value or "").replace("_", " ").replace("-", " ").split())
    if not text:
        return ""
    lowered = text.lower()
    if lowered.endswith(" county"):
        text = text[: -len(" county")].strip()
    return " ".join(part.capitalize() for part in text.split())


def normalize_coverage_state_code(value: str | None) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"", "TEXAS"}:
        return "TX"
    return normalized


class DrillerProfile(NetworkTimestampedModel):
    company_name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    capability_keys = models.JSONField(default=list, blank=True)
    working_days = models.JSONField(default=default_working_days, blank=True)
    coverage_area = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["company_name", "display_name", "id"]

    def __str__(self) -> str:
        return self.display_name

    def save(self, *args, **kwargs):
        self.working_days = normalize_working_days(self.working_days)
        super().save(*args, **kwargs)


class DrillerCoverage(NetworkTimestampedModel):
    driller = models.ForeignKey(DrillerProfile, on_delete=models.CASCADE, related_name="county_coverages")
    county_name = models.CharField(max_length=128)
    state_code = models.CharField(max_length=8, default="TX")
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["driller__company_name", "driller__display_name", "state_code", "county_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["driller", "county_name", "state_code"],
                name="uniq_driller_county_coverage",
            ),
        ]

    def save(self, *args, **kwargs):
        self.county_name = normalize_coverage_county_name(self.county_name)
        self.state_code = normalize_coverage_state_code(self.state_code)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.driller.display_name}: {self.county_name}, {self.state_code}"


class DrillerBlackoutDate(NetworkTimestampedModel):
    driller = models.ForeignKey(DrillerProfile, on_delete=models.CASCADE, related_name="blackout_dates")
    date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["date", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["driller", "date"],
                name="uniq_driller_blackout_date",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.driller.display_name}: {self.date.isoformat()}"


class DrillerFeeSchedule(NetworkTimestampedModel):
    driller = models.ForeignKey(DrillerProfile, on_delete=models.CASCADE, related_name="fee_schedules")
    name = models.CharField(max_length=150)
    currency = models.CharField(max_length=8, default="usd")
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["driller__company_name", "name", "id"]

    def __str__(self) -> str:
        return f"{self.driller.display_name} - {self.name}"


class DrillerFeeLineItem(NetworkTimestampedModel):
    class LineItemType(models.TextChoices):
        MOBILIZATION = "mobilization", "Mobilization"
        PER_BORE = "per_bore", "Per bore"
        PER_FOOT = "per_foot", "Per foot"
        STANDBY_DAY = "standby_day", "Standby day"
        CASING_PER_BORE = "casing_per_bore", "Casing per bore"
        ROCK_DRILLING_PER_BORE = "rock_drilling_per_bore", "Rock drilling premium per bore"
        TRAVEL_ZONE_ADDER = "travel_zone_adder", "Travel zone adder"
        MINIMUM_CHARGE = "minimum_charge", "Minimum charge"

    fee_schedule = models.ForeignKey(DrillerFeeSchedule, on_delete=models.CASCADE, related_name="line_items")
    line_item_type = models.CharField(max_length=32, choices=LineItemType.choices)
    label = models.CharField(max_length=150)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    metadata = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["fee_schedule__driller__company_name", "sort_order", "id"]

    def __str__(self) -> str:
        return f"{self.fee_schedule} - {self.label}"


class BookingRequest(NetworkTimestampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        COMMITTED = "committed", "Committed"
        BLOCKED = "blocked", "Blocked"
        COMPLETED = "completed", "Completed"

    external_project_key = models.CharField(max_length=128, unique=True)
    project_number = models.CharField(max_length=64, blank=True)
    proposal_number = models.CharField(max_length=64, blank=True)
    project_name = models.CharField(max_length=255)
    client_name = models.CharField(max_length=255, blank=True)
    capability_required = models.CharField(max_length=128, blank=True)
    coverage_area = models.JSONField(default=dict, blank=True)
    estimated_days = models.DecimalField(max_digits=6, decimal_places=2)
    earliest_start_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
    assigned_driller = models.ForeignKey(
        DrillerProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_requests",
    )
    committed_start_at = models.DateTimeField(null=True, blank=True)
    committed_end_at = models.DateTimeField(null=True, blank=True)
    blocking_reason = models.TextField(blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.project_number or self.external_project_key} {self.status}"
