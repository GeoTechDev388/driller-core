from __future__ import annotations

from decimal import Decimal
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def attachment_upload_to(instance, filename: str) -> str:
    return f"fieldlogs/attachments/{instance.drilling_input_record.field_execution.external_project_id}/{filename}"


def drilling_input_pdf_upload_to(instance, filename: str) -> str:
    return f"fieldlogs/pdfs/{instance.drilling_input_record.field_execution.external_project_id}/{filename}"


def generate_internal_sample_id() -> str:
    return f"SMP-{uuid.uuid4().hex[:20].upper()}"


class MethodAuthority(models.TextChoices):
    ASTM = "astm", "ASTM"
    AASHTO = "aashto", "AASHTO"
    INTERNAL = "internal", "Internal"
    OTHER = "other", "Other"
    UNKNOWN = "unknown", "Unknown / not specified"


class FieldLogTimestampedModel(models.Model):
    shared_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DrillerUser(FieldLogTimestampedModel):
    driller = models.ForeignKey("network.DrillerProfile", on_delete=models.CASCADE, related_name="driller_users")
    user_account = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="driller_user")
    is_active = models.BooleanField(default=True)
    portal_access_enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["driller__company_name", "user_account__email", "id"]

    def __str__(self) -> str:
        return self.email

    @property
    def email(self) -> str:
        return self.user_account.email


class FieldExecution(FieldLogTimestampedModel):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"
        ACCEPTED = "accepted", "Accepted"
        NEEDS_CORRECTION = "needs_correction", "Needs correction"

    external_project_id = models.CharField(max_length=128, unique=True)
    booking_request = models.OneToOneField(
        "network.BookingRequest",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="field_execution",
    )
    assigned_driller = models.ForeignKey("network.DrillerProfile", on_delete=models.PROTECT, related_name="field_executions")
    scheduled_start_date = models.DateField(null=True, blank=True)
    estimated_days = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    project_number = models.CharField(max_length=64, blank=True)
    proposal_number = models.CharField(max_length=64, blank=True)
    project_name = models.CharField(max_length=255, blank=True)
    client_name = models.CharField(max_length=255, blank=True)
    planned_borings = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.ASSIGNED)
    status_detail = models.TextField(blank=True)

    class Meta:
        ordering = ["scheduled_start_date", "project_number", "id"]

    def __str__(self) -> str:
        return self.project_number or self.external_project_id


class DrillingInputRecord(FieldLogTimestampedModel):
    class EntryMethod(models.TextChoices):
        DRILLER_DIRECT = "driller_direct", "Driller direct"
        EMPLOYEE_FROM_PAPER = "employee_from_paper", "Employee from paper"
        EMPLOYEE_FROM_CALL = "employee_from_call", "Employee from call"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        UNDER_REVIEW = "under_review", "Under review"
        ACCEPTED = "accepted", "Accepted"
        NEEDS_CORRECTION = "needs_correction", "Needs correction"

    field_execution = models.ForeignKey(FieldExecution, on_delete=models.CASCADE, related_name="drilling_input_records")
    entry_method = models.CharField(max_length=32, choices=EntryMethod.choices)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    entered_by = models.CharField(max_length=255, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.CharField(max_length=255, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-updated_at", "-id"]

    def __str__(self) -> str:
        return f"{self.field_execution} {self.entry_method}"


class SampleChainOfCustody(FieldLogTimestampedModel):
    class TransferMethod(models.TextChoices):
        HAND_DELIVERY = "hand_delivery", "Hand delivery"
        COURIER = "courier", "Courier"
        SHIPPED = "shipped", "Shipped"
        LAB_PICKUP = "lab_pickup", "Lab pickup"
        OTHER = "other", "Other"

    class DestinationType(models.TextChoices):
        SUNRISE_LAB = "sunrise_lab", "Sunrise lab"
        OUTSIDE_LAB = "outside_lab", "Outside lab"
        STORAGE = "storage", "Storage"
        OTHER = "other", "Other"

    drilling_input_record = models.OneToOneField(
        DrillingInputRecord,
        on_delete=models.CASCADE,
        related_name="chain_of_custody",
    )
    released_by_name = models.CharField(max_length=255)
    released_by_role = models.CharField(max_length=255)
    released_at = models.DateTimeField()
    received_by_name = models.CharField(max_length=255, blank=True)
    received_by_role = models.CharField(max_length=255, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    transfer_method = models.CharField(max_length=32, choices=TransferMethod.choices)
    transfer_location = models.CharField(max_length=255)
    destination_type = models.CharField(max_length=32, choices=DestinationType.choices)
    destination_name = models.CharField(max_length=255)
    tracking_number = models.CharField(max_length=128, blank=True)
    sample_condition_on_transfer = models.CharField(max_length=255, blank=True)
    custody_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-released_at", "-id"]


class BoringExecution(FieldLogTimestampedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        TERMINATED_EARLY = "terminated_early", "Terminated early"
        ABANDONED = "abandoned", "Abandoned"

    class CoordinateSystem(models.TextChoices):
        GEOGRAPHIC = "geographic", "Geographic"
        PROJECTED = "projected", "Projected"
        LOCAL = "local", "Local / site"
        UNKNOWN = "unknown", "Unknown"

    class LocationCaptureSource(models.TextChoices):
        MANUAL_ENTRY = "manual_entry", "Manual entry"
        UPLOADED_MAP_FILE = "uploaded_map_file", "Uploaded map file"
        APPENDIX_B_MAP_WORKSPACE = "appendix_b_map_workspace", "Appendix B map workspace"
        FIELD_LOG_MANUAL = "field_log_manual", "Field log manual entry"
        PHONE_GPS = "phone_gps", "Phone GPS"
        SURVEY = "survey", "Survey"
        UNKNOWN = "unknown", "Unknown"

    class LocationConfidence(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        UNKNOWN = "unknown", "Unknown"

    class LocationReviewStatus(models.TextChoices):
        UNREVIEWED = "unreviewed", "Unreviewed"
        REVIEWED = "reviewed", "Reviewed"
        REJECTED = "rejected", "Rejected"

    drilling_input_record = models.ForeignKey(DrillingInputRecord, on_delete=models.CASCADE, related_name="borings")
    name = models.CharField(max_length=64)
    planned_sequence = models.PositiveIntegerField(default=0)
    planned_category = models.CharField(max_length=32, blank=True)
    planned_depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    actual_depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PLANNED)
    drilling_method = models.CharField(max_length=64, blank=True)
    drilling_method_authority = models.CharField(
        max_length=32,
        choices=MethodAuthority.choices,
        default=MethodAuthority.UNKNOWN,
    )
    drilling_method_code = models.CharField(max_length=64, blank=True)
    drilling_method_version = models.CharField(max_length=32, blank=True)
    drilling_method_notes = models.TextField(blank=True)
    depth_unit = models.CharField(max_length=16, default="ft")
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-90.0000000")),
            MaxValueValidator(Decimal("90.0000000")),
        ],
    )
    longitude = models.DecimalField(
        max_digits=11,
        decimal_places=7,
        null=True,
        blank=True,
        validators=[
            MinValueValidator(Decimal("-180.0000000")),
            MaxValueValidator(Decimal("180.0000000")),
        ],
    )
    coordinate_system = models.CharField(
        max_length=24,
        choices=CoordinateSystem.choices,
        default=CoordinateSystem.GEOGRAPHIC,
    )
    coordinate_crs = models.CharField(max_length=64, blank=True)
    horizontal_datum = models.CharField(max_length=64, blank=True)
    coordinate_source = models.CharField(
        max_length=32,
        choices=LocationCaptureSource.choices,
        default=LocationCaptureSource.UNKNOWN,
    )
    coordinate_accuracy_m = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    coordinate_confidence = models.CharField(
        max_length=16,
        choices=LocationConfidence.choices,
        default=LocationConfidence.UNKNOWN,
    )
    coordinate_captured_at = models.DateTimeField(null=True, blank=True)
    coordinate_recorded_by = models.CharField(max_length=255, blank=True)
    location_review_status = models.CharField(
        max_length=16,
        choices=LocationReviewStatus.choices,
        default=LocationReviewStatus.UNREVIEWED,
    )
    location_notes = models.TextField(blank=True)
    surface_elevation = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    surface_elevation_unit = models.CharField(max_length=16, default="ft")
    surface_elevation_vertical_datum = models.CharField(max_length=64, blank=True)
    surface_elevation_reference = models.CharField(max_length=128, blank=True)
    surface_elevation_source = models.CharField(
        max_length=32,
        choices=LocationCaptureSource.choices,
        default=LocationCaptureSource.UNKNOWN,
    )
    surface_elevation_accuracy_ft = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    backfill_method = models.CharField(max_length=128, blank=True)
    notes = models.TextField(blank=True)
    relocation_note = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return self.name


class SamplingPlan(FieldLogTimestampedModel):
    boring = models.OneToOneField(BoringExecution, on_delete=models.CASCADE, related_name="sampling_plan")
    method_key = models.CharField(max_length=64, default="spt_standard")
    rule_type = models.CharField(max_length=64, default="phase1_standard_spt")
    rule_config = models.JSONField(default=dict, blank=True)
    generated_to_depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_default = models.BooleanField(default=True)

    class Meta:
        ordering = ["boring_id"]


class SampleInterval(FieldLogTimestampedModel):
    class SampleType(models.TextChoices):
        SPT = "spt", "SPT"
        SHELBY = "shelby", "Shelby"
        GRAB = "grab", "Grab"
        CORING = "coring", "Coring"

    class State(models.TextChoices):
        PLANNED = "planned", "Planned"
        TAKEN = "taken", "Taken"
        SKIPPED = "skipped", "Skipped"
        REFUSAL = "refusal", "Refusal"
        OBSTRUCTION = "obstruction", "Obstruction"
        TERMINATED_EARLY = "terminated_early", "Terminated early"
        NOT_POSSIBLE = "not_possible", "Not possible"

    boring = models.ForeignKey(BoringExecution, on_delete=models.CASCADE, related_name="intervals")
    sampling_plan = models.ForeignKey(
        SamplingPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="intervals",
    )
    sequence_number = models.PositiveIntegerField()
    method_key = models.CharField(max_length=64, default="spt_standard")
    method_authority = models.CharField(
        max_length=32,
        choices=MethodAuthority.choices,
        default=MethodAuthority.UNKNOWN,
    )
    method_code = models.CharField(max_length=64, blank=True)
    method_version = models.CharField(max_length=32, blank=True)
    method_notes = models.TextField(blank=True)
    sample_type = models.CharField(max_length=32, choices=SampleType.choices, default=SampleType.SPT)
    state = models.CharField(max_length=32, choices=State.choices, default=State.PLANNED)
    depth_unit = models.CharField(max_length=16, default="ft")
    planned_from_depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    planned_to_depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    actual_from_depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    actual_to_depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    internal_sample_id = models.CharField(max_length=64, unique=True, default=generate_internal_sample_id, editable=False)
    sample_label = models.CharField(max_length=128, blank=True)
    is_manual = models.BooleanField(default=False)
    deviation_reason = models.CharField(max_length=255, blank=True)
    operator_notes = models.TextField(blank=True)
    pocket_penetrometer = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    pocket_penetrometer_top = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    pocket_penetrometer_middle = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    pocket_penetrometer_bottom = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    pocket_penetrometer_unit = models.CharField(max_length=16, default="tsf")
    rqd_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    rqd_unit = models.CharField(max_length=16, default="percent")

    class Meta:
        ordering = ["boring_id", "sequence_number", "id"]
        constraints = [
            models.UniqueConstraint(fields=["boring", "sequence_number"], name="uniq_fieldlog_interval_boring_sequence"),
        ]


class SampleObservation(FieldLogTimestampedModel):
    interval = models.OneToOneField(SampleInterval, on_delete=models.CASCADE, related_name="observation")
    visual_classification = models.CharField(max_length=128, blank=True)
    moisture_condition = models.CharField(max_length=128, blank=True)
    color = models.CharField(max_length=128, blank=True)
    description = models.TextField(blank=True)
    recovery_length = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    recovery_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    sample_condition = models.CharField(max_length=128, blank=True)
    core_run_length = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    rock_core_classification = models.CharField(max_length=128, blank=True)
    rock_type_name = models.CharField(max_length=128, blank=True)
    rock_notes = models.TextField(blank=True)
    retained_sample = models.BooleanField(default=False)
    notes = models.TextField(blank=True)


class SPTResult(FieldLogTimestampedModel):
    interval = models.OneToOneField(SampleInterval, on_delete=models.CASCADE, related_name="spt_result")
    blows_1 = models.PositiveIntegerField(default=0)
    blows_2 = models.PositiveIntegerField(default=0)
    blows_3 = models.PositiveIntegerField(default=0)
    n_value = models.PositiveIntegerField(default=0)
    refusal_flag = models.BooleanField(default=False)
    method_authority = models.CharField(
        max_length=32,
        choices=MethodAuthority.choices,
        default=MethodAuthority.UNKNOWN,
    )
    method_code = models.CharField(max_length=64, blank=True)
    method_version = models.CharField(max_length=32, blank=True)
    method_notes = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        self.n_value = int(self.blows_2 or 0) + int(self.blows_3 or 0)
        super().save(*args, **kwargs)


class GroundwaterObservation(FieldLogTimestampedModel):
    class ObservationType(models.TextChoices):
        ENCOUNTERED = "encountered", "Encountered"
        SEEPAGE = "seepage", "Seepage"
        STABILIZED = "stabilized", "Stabilized"
        FINAL = "final", "Final"
        CAVE_IN = "cave_in", "Cave in"
        AFTER_COMPLETION = "after_completion", "After completion"

    boring = models.ForeignKey(BoringExecution, on_delete=models.CASCADE, related_name="groundwater_observations")
    observation_type = models.CharField(max_length=32, choices=ObservationType.choices)
    depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    observed_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at", "id"]


class BoringCompletion(FieldLogTimestampedModel):
    class TerminationReason(models.TextChoices):
        REACHED_PLANNED_DEPTH = "reached_planned_depth", "Reached planned depth"
        REFUSAL = "refusal", "Refusal"
        OBSTRUCTION = "obstruction", "Obstruction"
        CAVE_IN = "cave_in", "Cave in"
        NOT_POSSIBLE = "not_possible", "Not possible"
        ACCESS_LIMIT = "access_limit", "Inaccessible"
        UTILITY_CONFLICT = "utility_conflict", "Utility conflict"
        WEATHER = "weather", "Weather"
        FIELD_DIRECTION = "field_direction", "Owner / field direction"
        OPERATOR_STOP = "operator_stop", "Operator stop"
        OTHER = "other", "Other"

    boring = models.OneToOneField(BoringExecution, on_delete=models.CASCADE, related_name="completion")
    completed_at = models.DateTimeField(null=True, blank=True)
    final_depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    termination_reason = models.CharField(
        max_length=32,
        choices=TerminationReason.choices,
        default=TerminationReason.REACHED_PLANNED_DEPTH,
    )
    refusal_depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    obstruction_depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    cave_in_depth = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    notes = models.TextField(blank=True)


class FieldAttachment(FieldLogTimestampedModel):
    drilling_input_record = models.ForeignKey(DrillingInputRecord, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_upload_to)
    source_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class DrillingInputPDF(FieldLogTimestampedModel):
    drilling_input_record = models.OneToOneField(
        DrillingInputRecord,
        on_delete=models.CASCADE,
        related_name="pdf_artifact",
    )
    file = models.FileField(upload_to=drilling_input_pdf_upload_to, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    fingerprint = models.CharField(max_length=64, blank=True)
    template_version = models.CharField(max_length=32, blank=True)

    class Meta:
        ordering = ["-generated_at", "-id"]
