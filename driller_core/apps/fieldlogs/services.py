from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import models, transaction
from django.db.models import Prefetch
from django.utils import timezone

from driller_core.apps.network.models import BookingRequest

from .models import (
    BoringCompletion,
    BoringExecution,
    DrillingInputPDF,
    DrillingInputRecord,
    FieldExecution,
    GroundwaterObservation,
    SampleChainOfCustody,
    SPTResult,
    SampleInterval,
    SampleObservation,
    SamplingPlan,
)
from .pdf import ensure_drilling_input_pdf_current, field_log_pdf_display_name
from .sampling import (
    STANDARD_SPT_METHOD_KEY,
    STANDARD_SPT_RULE_TYPE,
    generate_standard_spt_intervals,
    sample_label_for_boring,
    standard_spt_rule_config,
)


DEFAULT_LAB_TESTS = (
    "moisture_contents",
    "atterberg_limits",
    "minus_200",
)

CORING_LAB_TESTS = (
    "moisture_contents",
)

DRILLING_METHOD_OPTIONS = (
    ("hollow_stem_auger", "Hollow Stem Auger"),
    ("solid_stem_auger", "Solid Stem Auger"),
    ("mud_rotary", "Mud Rotary"),
    ("air_rotary", "Air Rotary"),
    ("wash_boring", "Wash Boring"),
    ("direct_push", "Direct Push"),
    ("core_rig", "Core Rig"),
    ("hand_auger", "Hand Auger"),
    ("other", "Other"),
)

USCS_CLASSIFICATION_OPTIONS = (
    ("GW", "GW - Well Graded Gravel"),
    ("GP", "GP - Poorly Graded Gravel"),
    ("GM", "GM - Silty Gravel"),
    ("GC", "GC - Clayey Gravel"),
    ("SW", "SW - Well Graded Sand"),
    ("SP", "SP - Poorly Graded Sand"),
    ("SM", "SM - Silty Sand"),
    ("SC", "SC - Clayey Sand"),
    ("ML", "ML - Silt"),
    ("CL", "CL - Lean Clay"),
    ("OL", "OL - Organic Silt / Clay"),
    ("MH", "MH - Elastic Silt"),
    ("CH", "CH - Fat Clay"),
    ("OH", "OH - Organic Clay / Silt"),
    ("PT", "PT - Peat"),
)

MOISTURE_CONDITION_OPTIONS = (
    ("dry", "Dry"),
    ("moist", "Moist"),
    ("wet", "Wet"),
)

SAMPLE_CONDITION_OPTIONS = (
    ("intact", "Intact"),
    ("slightly_disturbed", "Slightly Disturbed"),
    ("disturbed", "Disturbed"),
    ("fractured", "Fractured"),
    ("crumbled", "Crumbled"),
    ("flow_in", "Flow-In"),
    ("no_recovery", "No Recovery"),
)

CHAIN_OF_CUSTODY_TRANSFER_METHOD_OPTIONS = tuple(SampleChainOfCustody.TransferMethod.choices)
CHAIN_OF_CUSTODY_DESTINATION_TYPE_OPTIONS = tuple(SampleChainOfCustody.DestinationType.choices)

SOIL_SAMPLE_TYPES = {
    SampleInterval.SampleType.SPT,
    SampleInterval.SampleType.SHELBY,
}


class FieldLogValidationError(ValueError):
    def __init__(self, detail: str = "Please fix the highlighted fields.", *, field_errors: dict[str, str] | None = None):
        super().__init__(detail)
        self.detail = detail
        self.field_errors = field_errors or {}


def _option_payload(options) -> list[dict]:
    return [{"value": value, "label": label} for value, label in options]


def field_log_form_options_payload() -> dict:
    return {
        "drilling_methods": _option_payload(DRILLING_METHOD_OPTIONS),
        "soil_classifications": _option_payload(USCS_CLASSIFICATION_OPTIONS),
        "moisture_conditions": _option_payload(MOISTURE_CONDITION_OPTIONS),
        "sample_conditions": _option_payload(SAMPLE_CONDITION_OPTIONS),
        "sample_types": _option_payload(SampleInterval.SampleType.choices),
        "groundwater_types": _option_payload(GroundwaterObservation.ObservationType.choices),
        "completion_reasons": _option_payload(BoringCompletion.TerminationReason.choices),
        "custody_transfer_methods": _option_payload(CHAIN_OF_CUSTODY_TRANSFER_METHOD_OPTIONS),
        "custody_destination_types": _option_payload(CHAIN_OF_CUSTODY_DESTINATION_TYPE_OPTIONS),
    }


def _actor_label(actor: str | dict | None) -> str:
    if isinstance(actor, str):
        return actor.strip()
    if isinstance(actor, dict):
        for key in ("display_name", "full_name", "email", "name"):
            value = str(actor.get(key) or "").strip()
            if value:
                return value
    return ""


def _decimal_value(value, *, default: str = "0.00") -> Decimal:
    raw_value = default if value in (None, "") else value
    try:
        return Decimal(str(raw_value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("A numeric field contained an invalid decimal value.") from exc


def _nullable_decimal_value(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return _decimal_value(value)


def _decimal_field_valid(value) -> bool:
    if value in (None, ""):
        return True
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return False
    return parsed.is_finite()


def _int_value(value, *, default: int = 0) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _bool_value(value) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _datetime_value(value) -> datetime | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("A datetime field contained an invalid value.") from exc
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed.astimezone(timezone.get_current_timezone())


def _add_field_error(field_errors: dict[str, str], path: str, message: str) -> None:
    if path and path not in field_errors:
        field_errors[path] = message


def _validate_decimal_field(
    field_errors: dict[str, str],
    *,
    path: str,
    value,
    required: bool = False,
    required_message: str = "This numeric field is required.",
) -> None:
    if value in (None, ""):
        if required:
            _add_field_error(field_errors, path, required_message)
        return
    if not _decimal_field_valid(value):
        _add_field_error(field_errors, path, "Enter a valid decimal value.")


def _raw_text(value) -> str:
    return str(value or "").strip()


def _safe_file_size(file_field) -> int | None:
    if not file_field or not getattr(file_field, "name", None):
        return None
    try:
        return file_field.size
    except Exception:
        return None


def _validate_datetime_field(field_errors: dict[str, str], *, path: str, value, required_message: str) -> None:
    raw = _raw_text(value)
    if not raw:
        _add_field_error(field_errors, path, required_message)
        return
    try:
        _datetime_value(raw)
    except ValueError:
        _add_field_error(field_errors, path, "Invalid date selected.")


def _validate_datetime_field_if_present(field_errors: dict[str, str], *, path: str, value) -> None:
    raw = _raw_text(value)
    if not raw:
        return
    try:
        _datetime_value(raw)
    except ValueError:
        _add_field_error(field_errors, path, "Invalid date selected.")


def _validate_choice_field(
    field_errors: dict[str, str],
    *,
    path: str,
    value,
    valid_values: set[str],
    required_message: str,
    invalid_message: str,
    required: bool = True,
) -> None:
    raw = _raw_text(value)
    if not raw:
        if required:
            _add_field_error(field_errors, path, required_message)
        return
    if raw not in valid_values:
        _add_field_error(field_errors, path, invalid_message)


def _has_value(value) -> bool:
    if isinstance(value, bool):
        return value
    return value not in (None, "")


def _validate_update_payload(payload: dict) -> None:
    field_errors: dict[str, str] = {}
    borings_payload = payload.get("borings") or []
    if not isinstance(borings_payload, list):
        raise FieldLogValidationError("Please fix the highlighted fields.", field_errors={"borings": "Borings must be a list."})

    drilling_method_values = {value for value, _label in DRILLING_METHOD_OPTIONS}
    soil_classification_values = {value for value, _label in USCS_CLASSIFICATION_OPTIONS}
    moisture_condition_values = {value for value, _label in MOISTURE_CONDITION_OPTIONS}
    sample_condition_values = {value for value, _label in SAMPLE_CONDITION_OPTIONS}
    sample_type_values = {choice for choice, _label in SampleInterval.SampleType.choices}
    groundwater_type_values = {choice for choice, _label in GroundwaterObservation.ObservationType.choices}
    completion_reason_values = {choice for choice, _label in BoringCompletion.TerminationReason.choices}

    for boring_index, boring_payload in enumerate(borings_payload):
        boring_path = f"borings.{boring_index}"
        drilling_method = _raw_text(boring_payload.get("drilling_method"))
        _validate_decimal_field(field_errors, path=f"{boring_path}.planned_depth", value=boring_payload.get("planned_depth"))
        _validate_decimal_field(field_errors, path=f"{boring_path}.actual_depth", value=boring_payload.get("actual_depth"))
        _validate_decimal_field(field_errors, path=f"{boring_path}.surface_elevation", value=boring_payload.get("surface_elevation"))
        _validate_choice_field(
            field_errors,
            path=f"{boring_path}.drilling_method",
            value=drilling_method,
            valid_values=drilling_method_values,
            required_message="Drilling method is required.",
            invalid_message="Select a valid drilling method.",
        )

        for groundwater_index, groundwater_payload in enumerate(boring_payload.get("groundwater_observations") or []):
            groundwater_path = f"{boring_path}.groundwater_observations.{groundwater_index}"
            _validate_decimal_field(field_errors, path=f"{groundwater_path}.depth", value=groundwater_payload.get("depth"))
            _validate_choice_field(
                field_errors,
                path=f"{groundwater_path}.observation_type",
                value=groundwater_payload.get("observation_type"),
                valid_values=groundwater_type_values,
                required_message="Groundwater event type is required.",
                invalid_message="Select a valid groundwater event type.",
            )
            _validate_datetime_field(
                field_errors,
                path=f"{groundwater_path}.observed_at",
                value=groundwater_payload.get("observed_at"),
                required_message="Observation time is required.",
            )

        completion_payload = boring_payload.get("completion") or None
        if completion_payload:
            completion_path = f"{boring_path}.completion"
            _validate_decimal_field(
                field_errors,
                path=f"{completion_path}.final_depth",
                value=completion_payload.get("final_depth"),
                required=True,
                required_message="Final depth / ATD is required.",
            )
            _validate_decimal_field(field_errors, path=f"{completion_path}.refusal_depth", value=completion_payload.get("refusal_depth"))
            _validate_decimal_field(field_errors, path=f"{completion_path}.obstruction_depth", value=completion_payload.get("obstruction_depth"))
            _validate_decimal_field(field_errors, path=f"{completion_path}.cave_in_depth", value=completion_payload.get("cave_in_depth"))
            _validate_datetime_field(
                field_errors,
                path=f"{completion_path}.completed_at",
                value=completion_payload.get("completed_at"),
                required_message="Completion time is required.",
            )
            _validate_choice_field(
                field_errors,
                path=f"{completion_path}.termination_reason",
                value=completion_payload.get("termination_reason"),
                valid_values=completion_reason_values,
                required_message="Termination reason is required.",
                invalid_message="Select a valid termination reason.",
            )

        for interval_index, interval_payload in enumerate(boring_payload.get("intervals") or []):
            interval_path = f"{boring_path}.intervals.{interval_index}"
            sample_type = _raw_text(interval_payload.get("sample_type") or SampleInterval.SampleType.SPT)
            observation_payload = interval_payload.get("observation") or {}
            spt_payload = interval_payload.get("spt_result") or {}
            _validate_decimal_field(field_errors, path=f"{interval_path}.actual_from_depth", value=interval_payload.get("actual_from_depth"))
            _validate_decimal_field(field_errors, path=f"{interval_path}.actual_to_depth", value=interval_payload.get("actual_to_depth"))
            _validate_decimal_field(field_errors, path=f"{interval_path}.pocket_penetrometer", value=interval_payload.get("pocket_penetrometer"))
            _validate_decimal_field(field_errors, path=f"{interval_path}.pocket_penetrometer_top", value=interval_payload.get("pocket_penetrometer_top"))
            _validate_decimal_field(field_errors, path=f"{interval_path}.pocket_penetrometer_middle", value=interval_payload.get("pocket_penetrometer_middle"))
            _validate_decimal_field(field_errors, path=f"{interval_path}.pocket_penetrometer_bottom", value=interval_payload.get("pocket_penetrometer_bottom"))
            _validate_decimal_field(field_errors, path=f"{interval_path}.rqd_percent", value=interval_payload.get("rqd_percent"))
            _validate_decimal_field(field_errors, path=f"{interval_path}.observation.recovery_length", value=observation_payload.get("recovery_length"))
            _validate_decimal_field(field_errors, path=f"{interval_path}.observation.recovery_percent", value=observation_payload.get("recovery_percent"))
            _validate_decimal_field(field_errors, path=f"{interval_path}.observation.core_run_length", value=observation_payload.get("core_run_length"))

            _validate_choice_field(
                field_errors,
                path=f"{interval_path}.sample_type",
                value=sample_type,
                valid_values=sample_type_values,
                required_message="Sample type is required.",
                invalid_message="Select a valid sample type.",
            )
            state = _derived_interval_state_from_payload(interval_payload, sample_type=sample_type)
            measurement_required = _requires_sample_measurements(state)

            if sample_type in SOIL_SAMPLE_TYPES:
                _validate_choice_field(
                    field_errors,
                    path=f"{interval_path}.observation.visual_classification",
                    value=observation_payload.get("visual_classification"),
                    valid_values=soil_classification_values,
                    required_message="USCS classification is required.",
                    invalid_message="Select a valid USCS classification.",
                    required=measurement_required,
                )
                _validate_choice_field(
                    field_errors,
                    path=f"{interval_path}.observation.moisture_condition",
                    value=observation_payload.get("moisture_condition"),
                    valid_values=moisture_condition_values,
                    required_message="Moisture is required.",
                    invalid_message="Select a valid moisture condition.",
                    required=measurement_required,
                )
                if _has_value(observation_payload.get("rock_core_classification")):
                    _add_field_error(field_errors, f"{interval_path}.observation.rock_core_classification", "Rock fields are only used for coring samples.")
                if _has_value(observation_payload.get("rock_type_name")):
                    _add_field_error(field_errors, f"{interval_path}.observation.rock_type_name", "Rock fields are only used for coring samples.")
                if _has_value(observation_payload.get("rock_notes")):
                    _add_field_error(field_errors, f"{interval_path}.observation.rock_notes", "Rock fields are only used for coring samples.")
            else:
                if _has_value(observation_payload.get("visual_classification")):
                    _add_field_error(field_errors, f"{interval_path}.observation.visual_classification", "USCS classification is only used for soil samples.")
                if _has_value(observation_payload.get("moisture_condition")):
                    _add_field_error(field_errors, f"{interval_path}.observation.moisture_condition", "Moisture is only used for soil samples.")

            if sample_type == SampleInterval.SampleType.SPT and measurement_required:
                for blow_key, label in (
                    ("blows_1", "0-6 in blow count"),
                    ("blows_2", "6-12 in blow count"),
                    ("blows_3", "12-18 in blow count"),
                ):
                    if spt_payload.get(blow_key) in (None, ""):
                        _add_field_error(field_errors, f"{interval_path}.spt_result.{blow_key}", f"{label} is required.")

            if sample_type == SampleInterval.SampleType.SHELBY:
                _validate_choice_field(
                    field_errors,
                    path=f"{interval_path}.observation.sample_condition",
                    value=observation_payload.get("sample_condition"),
                    valid_values=sample_condition_values,
                    required_message="Sample condition is required.",
                    invalid_message="Select a valid sample condition.",
                    required=False,
                )
                if measurement_required and not any(
                    interval_payload.get(key) not in (None, "")
                    for key in (
                        "pocket_penetrometer",
                        "pocket_penetrometer_top",
                        "pocket_penetrometer_middle",
                        "pocket_penetrometer_bottom",
                    )
                ):
                    _add_field_error(
                        field_errors,
                        f"{interval_path}.pocket_penetrometer_middle",
                        "At least one pocket penetrometer reading is required.",
                    )
            elif _has_value(observation_payload.get("sample_condition")):
                _add_field_error(
                    field_errors,
                    f"{interval_path}.observation.sample_condition",
                    "Sample condition is only used for Shelby samples.",
                )

            if sample_type == SampleInterval.SampleType.CORING:
                if measurement_required and interval_payload.get("rqd_percent") in (None, ""):
                    _add_field_error(field_errors, f"{interval_path}.rqd_percent", "RQD is required for coring samples.")
            elif _has_value(interval_payload.get("rqd_percent")):
                _add_field_error(field_errors, f"{interval_path}.rqd_percent", "RQD is only used for coring samples.")

            if sample_type == SampleInterval.SampleType.GRAB:
                if _has_value(observation_payload.get("rock_core_classification")):
                    _add_field_error(field_errors, f"{interval_path}.observation.rock_core_classification", "Rock classification is only used for coring samples.")
                if _has_value(observation_payload.get("sample_condition")):
                    _add_field_error(field_errors, f"{interval_path}.observation.sample_condition", "Sample condition is only used for Shelby samples.")

    if field_errors:
        raise FieldLogValidationError(field_errors=field_errors)


def dashboard_status_for_execution(execution: FieldExecution) -> str:
    latest_record = execution.drilling_input_records.order_by("-updated_at", "-id").first()
    if latest_record is None:
        return "not_started"
    if latest_record.status == DrillingInputRecord.Status.DRAFT:
        return "in_progress"
    if latest_record.status == DrillingInputRecord.Status.NEEDS_CORRECTION:
        return "needs_correction"
    if latest_record.status in {
        DrillingInputRecord.Status.SUBMITTED,
        DrillingInputRecord.Status.UNDER_REVIEW,
    }:
        return "under_review"
    if latest_record.status == DrillingInputRecord.Status.ACCEPTED:
        return "accepted"
    return "in_progress"


def _choice_value(value, *, default: str, valid_choices, field_label: str) -> str:
    next_value = (value or default or "").strip()
    if next_value not in valid_choices:
        raise ValueError(f"{field_label} must be one of: {', '.join(sorted(valid_choices))}.")
    return next_value


def _normalized_planned_borings(raw_planned_borings) -> list[dict]:
    if not isinstance(raw_planned_borings, list):
        return []

    normalized: list[dict] = []
    for index, raw_boring in enumerate(raw_planned_borings, start=1):
        if not isinstance(raw_boring, dict):
            continue

        sequence_number = _int_value(raw_boring.get("sequence_number"), default=index)
        normalized.append(
            {
                "name": (raw_boring.get("name") or f"B-{sequence_number}").strip() or f"B-{sequence_number}",
                "sequence_number": max(1, sequence_number),
                "planned_depth": str(
                    _decimal_value(
                        raw_boring.get("planned_depth") or raw_boring.get("planned_depth_ft") or "0.00",
                    )
                ),
                "category": (raw_boring.get("category") or "").strip() or None,
                "category_sequence": _int_value(raw_boring.get("category_sequence"), default=0),
                "source_scope_item_id": _int_value(raw_boring.get("source_scope_item_id"), default=0) or None,
                "source_scope_item_uuid": (raw_boring.get("source_scope_item_uuid") or "").strip() or None,
                "source_description": (raw_boring.get("source_description") or "").strip() or None,
            }
        )

    normalized.sort(key=lambda boring: (boring["sequence_number"], boring["name"]))
    return normalized


def _planned_borings_for_execution(execution: FieldExecution) -> list[dict]:
    if execution.planned_borings:
        return _normalized_planned_borings(execution.planned_borings)
    booking_payload = execution.booking_request.request_payload if execution.booking_request is not None else {}
    return _normalized_planned_borings(booking_payload.get("planned_borings"))


def _seed_record_from_planned_borings(record: DrillingInputRecord) -> DrillingInputRecord:
    if record.borings.exists():
        return record

    for planned_boring in _planned_borings_for_execution(record.field_execution):
        boring = BoringExecution.objects.create(
            drilling_input_record=record,
            name=planned_boring["name"],
            planned_sequence=planned_boring["sequence_number"],
            planned_category=planned_boring["category"] or "",
            planned_depth=_decimal_value(planned_boring["planned_depth"]),
            status=BoringExecution.Status.PLANNED,
        )
        sampling_plan = _ensure_sampling_plan(boring, boring.planned_depth)
        _sync_generated_intervals(boring, sampling_plan, boring.planned_depth)

    return record


def ensure_editable_record_seeded(execution: FieldExecution) -> DrillingInputRecord | None:
    editable = _editable_record_queryset(execution).first()
    if editable is None:
        return None
    return _seed_record_from_planned_borings(editable)


def ensure_field_execution_for_booking(booking: BookingRequest) -> FieldExecution | None:
    if booking.status != BookingRequest.Status.COMMITTED or booking.assigned_driller_id is None:
        return None

    planned_borings = _normalized_planned_borings((booking.request_payload or {}).get("planned_borings"))
    execution = FieldExecution.objects.filter(external_project_id=booking.external_project_key).first()
    if execution is None:
        return FieldExecution.objects.create(
            external_project_id=booking.external_project_key,
            booking_request=booking,
            assigned_driller=booking.assigned_driller,
            scheduled_start_date=booking.committed_start_at.date() if booking.committed_start_at else None,
            estimated_days=booking.estimated_days,
            project_number=booking.project_number,
            proposal_number=booking.proposal_number,
            project_name=booking.project_name,
            client_name=booking.client_name,
            planned_borings=planned_borings,
            status=FieldExecution.Status.ASSIGNED,
            status_detail="Assigned from committed driller-core booking.",
        )

    execution.booking_request = booking
    execution.assigned_driller = booking.assigned_driller
    execution.scheduled_start_date = booking.committed_start_at.date() if booking.committed_start_at else execution.scheduled_start_date
    execution.estimated_days = booking.estimated_days
    execution.project_number = booking.project_number
    execution.proposal_number = booking.proposal_number
    execution.project_name = booking.project_name
    execution.client_name = booking.client_name
    execution.planned_borings = planned_borings
    execution.save(
        update_fields=[
            "booking_request",
            "assigned_driller",
            "scheduled_start_date",
            "estimated_days",
            "project_number",
            "proposal_number",
            "project_name",
            "client_name",
            "planned_borings",
            "updated_at",
        ]
    )
    return execution


def _editable_record_queryset(execution: FieldExecution):
    return execution.drilling_input_records.filter(
        status__in=[
            DrillingInputRecord.Status.DRAFT,
            DrillingInputRecord.Status.NEEDS_CORRECTION,
        ]
    ).order_by("-updated_at", "-id")


@transaction.atomic
def start_drilling_input(
    execution: FieldExecution,
    *,
    actor: str | dict | None,
    entry_method: str = DrillingInputRecord.EntryMethod.DRILLER_DIRECT,
) -> DrillingInputRecord:
    editable = _editable_record_queryset(execution).first()
    if editable is not None:
        return _seed_record_from_planned_borings(editable)

    if execution.drilling_input_records.filter(status=DrillingInputRecord.Status.ACCEPTED).exists():
        raise ValueError("An accepted field log already exists for this execution.")

    record = DrillingInputRecord.objects.create(
        field_execution=execution,
        entry_method=entry_method,
        status=DrillingInputRecord.Status.DRAFT,
        entered_by=_actor_label(actor),
    )
    execution.status = FieldExecution.Status.IN_PROGRESS
    execution.status_detail = "Field log drafting is in progress."
    execution.save(update_fields=["status", "status_detail", "updated_at"])
    return _seed_record_from_planned_borings(record)


def _resolve_boring(record: DrillingInputRecord, payload: dict) -> BoringExecution | None:
    boring_id = payload.get("id")
    if boring_id:
        return record.borings.filter(pk=int(boring_id)).first()

    boring_uuid = str(payload.get("shared_uuid") or "").strip()
    if boring_uuid:
        return record.borings.filter(shared_uuid=boring_uuid).first()
    return None


def _resolve_interval(boring: BoringExecution, payload: dict) -> SampleInterval | None:
    interval_id = payload.get("id")
    if interval_id:
        return boring.intervals.filter(pk=int(interval_id)).first()

    interval_uuid = str(payload.get("shared_uuid") or "").strip()
    if interval_uuid:
        return boring.intervals.filter(shared_uuid=interval_uuid).first()

    internal_sample_id = str(payload.get("internal_sample_id") or "").strip()
    if internal_sample_id:
        return boring.intervals.filter(internal_sample_id=internal_sample_id).first()

    sequence_number = payload.get("sequence_number")
    if sequence_number not in (None, ""):
        return boring.intervals.filter(sequence_number=int(sequence_number)).first()
    return None


def _ensure_sampling_plan(boring: BoringExecution, generated_to_depth: Decimal) -> SamplingPlan:
    plan, created = SamplingPlan.objects.get_or_create(
        boring=boring,
        defaults={
            "method_key": STANDARD_SPT_METHOD_KEY,
            "rule_type": STANDARD_SPT_RULE_TYPE,
            "rule_config": standard_spt_rule_config(),
            "generated_to_depth": generated_to_depth,
            "is_default": True,
        },
    )
    if created:
        return plan

    plan.method_key = STANDARD_SPT_METHOD_KEY
    plan.rule_type = STANDARD_SPT_RULE_TYPE
    plan.rule_config = standard_spt_rule_config()
    plan.generated_to_depth = generated_to_depth
    plan.is_default = True
    plan.save()
    return plan


def _generated_depth_target(boring_payload: dict, boring: BoringExecution) -> Decimal:
    completion_payload = boring_payload.get("completion") or {}
    depths = [
        boring.planned_depth or Decimal("0.00"),
        boring.actual_depth or Decimal("0.00"),
        _nullable_decimal_value(boring_payload.get("planned_depth")) or Decimal("0.00"),
        _nullable_decimal_value(boring_payload.get("actual_depth")) or Decimal("0.00"),
        _nullable_decimal_value(completion_payload.get("final_depth")) or Decimal("0.00"),
    ]
    return max(depths)


def _sync_generated_intervals(boring: BoringExecution, plan: SamplingPlan, target_depth: Decimal) -> None:
    expected_intervals = generate_standard_spt_intervals(target_depth)
    existing_by_sequence = {interval.sequence_number: interval for interval in boring.intervals.filter(is_manual=False)}

    for sequence_number, (planned_from_depth, planned_to_depth) in enumerate(expected_intervals, start=1):
        interval = existing_by_sequence.get(sequence_number)
        sample_label = sample_label_for_boring(boring.name, sequence_number)
        if interval is None:
            SampleInterval.objects.create(
                boring=boring,
                sampling_plan=plan,
                sequence_number=sequence_number,
                method_key=STANDARD_SPT_METHOD_KEY,
                planned_from_depth=planned_from_depth,
                planned_to_depth=planned_to_depth,
                sample_label=sample_label,
            )
            continue

        interval.sampling_plan = plan
        interval.method_key = STANDARD_SPT_METHOD_KEY
        interval.planned_from_depth = planned_from_depth
        interval.planned_to_depth = planned_to_depth
        interval.sample_label = sample_label
        interval.save()

    highest_sequence = len(expected_intervals)
    for interval in boring.intervals.filter(is_manual=False, sequence_number__gt=highest_sequence):
        if (
            interval.state == SampleInterval.State.PLANNED
            and interval.actual_from_depth is None
            and interval.actual_to_depth is None
            and not hasattr(interval, "observation")
            and not hasattr(interval, "spt_result")
        ):
            interval.delete()


def _observation_payload_present(payload: dict) -> bool:
    return any(
        payload.get(key) not in (None, "", False)
        for key in (
            "visual_classification",
            "moisture_condition",
            "color",
            "description",
            "recovery_length",
            "recovery_percent",
            "sample_condition",
            "core_run_length",
            "rock_core_classification",
            "rock_type_name",
            "rock_notes",
            "retained_sample",
            "notes",
        )
    )


def _spt_payload_present(payload: dict) -> bool:
    return any(
        payload.get(key) is not None and payload.get(key) != ""
        for key in ("blows_1", "blows_2", "blows_3", "refusal_flag", "notes")
    )


def _sample_type_value(value: str | None, *, default: str = SampleInterval.SampleType.SPT) -> str:
    return _choice_value(
        value,
        default=default,
        valid_choices={choice for choice, _label in SampleInterval.SampleType.choices},
        field_label="Sample type",
    )


def _requires_sample_measurements(state: str) -> bool:
    return state in {SampleInterval.State.TAKEN, SampleInterval.State.REFUSAL}


def _interval_has_fact_payload(payload: dict) -> bool:
    observation_payload = payload.get("observation") or {}
    return any(
        (
            payload.get("actual_from_depth"),
            payload.get("actual_to_depth"),
            payload.get("pocket_penetrometer"),
            payload.get("pocket_penetrometer_top"),
            payload.get("pocket_penetrometer_middle"),
            payload.get("pocket_penetrometer_bottom"),
            payload.get("rqd_percent"),
            payload.get("deviation_reason"),
            payload.get("operator_notes"),
            _observation_payload_present(observation_payload),
            _spt_payload_present(payload.get("spt_result") or {}),
        )
    )


def _derived_interval_state_from_payload(payload: dict, *, sample_type: str) -> str:
    spt_payload = payload.get("spt_result") or {}
    if sample_type == SampleInterval.SampleType.SPT and _bool_value(spt_payload.get("refusal_flag")):
        return SampleInterval.State.REFUSAL
    if (
        payload.get("deviation_reason") not in (None, "")
        or payload.get("operator_notes") not in (None, "")
    ) and payload.get("actual_from_depth") in (None, "") and payload.get("actual_to_depth") in (None, "") and not _observation_payload_present(payload.get("observation") or {}) and not _spt_payload_present(spt_payload) and payload.get("rqd_percent") in (None, ""):
        return SampleInterval.State.NOT_POSSIBLE
    if payload.get("actual_from_depth") not in (None, "") or payload.get("actual_to_depth") not in (None, ""):
        return SampleInterval.State.TAKEN
    if _interval_has_fact_payload(payload):
        return SampleInterval.State.TAKEN
    return SampleInterval.State.PLANNED


def _interval_has_captured_data(interval: SampleInterval) -> bool:
    if interval.actual_from_depth is not None or interval.actual_to_depth is not None:
        return True
    if interval.pocket_penetrometer is not None or interval.pocket_penetrometer_top is not None or interval.pocket_penetrometer_middle is not None or interval.pocket_penetrometer_bottom is not None or interval.rqd_percent is not None:
        return True
    if interval.deviation_reason or interval.operator_notes:
        return True
    if hasattr(interval, "spt_result"):
        result = interval.spt_result
        if any(value is not None and value != "" for value in (result.blows_1, result.blows_2, result.blows_3)) or result.refusal_flag or bool(result.notes):
            return True
    if hasattr(interval, "observation"):
        observation = interval.observation
        if any(
            (
                observation.visual_classification,
                observation.moisture_condition,
                observation.color,
                observation.description,
                observation.recovery_length and observation.recovery_length > Decimal("0.00"),
                observation.recovery_percent is not None,
                observation.sample_condition,
                observation.core_run_length is not None,
                observation.rock_core_classification,
                observation.rock_type_name,
                observation.rock_notes,
                observation.retained_sample,
                observation.notes,
            )
        ):
            return True
    return False


def _boring_is_scope_boring(boring: BoringExecution) -> bool:
    return bool(boring.planned_sequence or (boring.planned_category or "").strip())


def _derive_boring_status(boring: BoringExecution) -> str:
    completion = getattr(boring, "completion", None)
    if completion is not None:
        final_depth = completion.final_depth or Decimal("0.00")
        if completion.termination_reason == BoringCompletion.TerminationReason.REACHED_PLANNED_DEPTH and final_depth >= (boring.planned_depth or Decimal("0.00")):
            return BoringExecution.Status.COMPLETED
        if final_depth <= Decimal("0.00"):
            return BoringExecution.Status.ABANDONED
        return BoringExecution.Status.TERMINATED_EARLY

    if boring.actual_depth is not None and boring.actual_depth > Decimal("0.00"):
        return BoringExecution.Status.ACTIVE
    if boring.groundwater_observations.exists():
        return BoringExecution.Status.ACTIVE
    if any(_interval_has_captured_data(interval) for interval in boring.intervals.all()):
        return BoringExecution.Status.ACTIVE
    return BoringExecution.Status.PLANNED


def _recommended_tests_for_sample_type(sample_type: str) -> list[str]:
    if sample_type == SampleInterval.SampleType.CORING:
        return list(CORING_LAB_TESTS)
    return list(DEFAULT_LAB_TESTS)


def _first_present_decimal(*values: Decimal | None) -> Decimal | None:
    for value in values:
        if value is not None:
            return value
    return None


def _normalize_shelby_readings(interval: SampleInterval) -> None:
    if (
        interval.pocket_penetrometer is not None
        and interval.pocket_penetrometer_middle is None
        and interval.pocket_penetrometer_top is None
        and interval.pocket_penetrometer_bottom is None
    ):
        interval.pocket_penetrometer_middle = interval.pocket_penetrometer

    interval.pocket_penetrometer = _first_present_decimal(
        interval.pocket_penetrometer_middle,
        interval.pocket_penetrometer_top,
        interval.pocket_penetrometer_bottom,
        interval.pocket_penetrometer,
    )


def _normalize_interval_type_specific_fields(interval: SampleInterval, *, sample_type: str) -> None:
    if sample_type != SampleInterval.SampleType.SHELBY:
        interval.pocket_penetrometer = None
        interval.pocket_penetrometer_top = None
        interval.pocket_penetrometer_middle = None
        interval.pocket_penetrometer_bottom = None
    else:
        _normalize_shelby_readings(interval)
    if sample_type != SampleInterval.SampleType.CORING:
        interval.rqd_percent = None


def _normalize_observation_type_specific_fields(observation: SampleObservation, *, sample_type: str) -> None:
    if sample_type not in SOIL_SAMPLE_TYPES:
        observation.visual_classification = ""
        observation.moisture_condition = ""
    if sample_type != SampleInterval.SampleType.SHELBY:
        observation.sample_condition = ""
    if sample_type != SampleInterval.SampleType.CORING:
        observation.core_run_length = None
        observation.rock_core_classification = ""
        observation.rock_type_name = ""
        observation.rock_notes = ""


def _validate_interval_type_specific_fields(
    interval: SampleInterval,
    *,
    sample_type: str,
    state: str,
    spt_payload: dict,
) -> None:
    if not _requires_sample_measurements(state):
        return

    if sample_type == SampleInterval.SampleType.SPT:
        if not all(key in spt_payload for key in ("blows_1", "blows_2", "blows_3")):
            raise ValueError("SPT samples require blows_1, blows_2, and blows_3.")
        return

    if sample_type == SampleInterval.SampleType.SHELBY and _first_present_decimal(
        interval.pocket_penetrometer_top,
        interval.pocket_penetrometer_middle,
        interval.pocket_penetrometer_bottom,
        interval.pocket_penetrometer,
    ) is None:
        raise ValueError("Shelby samples require at least one pocket penetrometer reading.")

    if sample_type == SampleInterval.SampleType.CORING and interval.rqd_percent is None:
        raise ValueError("Coring samples require rqd_percent.")


def _upsert_interval(interval: SampleInterval, payload: dict) -> None:
    actual_from_depth = _nullable_decimal_value(payload.get("actual_from_depth"))
    actual_to_depth = _nullable_decimal_value(payload.get("actual_to_depth"))
    sample_type = _sample_type_value(payload.get("sample_type"), default=interval.sample_type or SampleInterval.SampleType.SPT)
    next_state = _derived_interval_state_from_payload(payload, sample_type=sample_type)
    if next_state in {SampleInterval.State.TAKEN, SampleInterval.State.REFUSAL}:
        actual_from_depth = actual_from_depth if actual_from_depth is not None else interval.planned_from_depth
        actual_to_depth = actual_to_depth if actual_to_depth is not None else interval.planned_to_depth

    interval.sample_type = sample_type
    interval.state = next_state
    interval.actual_from_depth = actual_from_depth
    interval.actual_to_depth = actual_to_depth
    interval.deviation_reason = (payload.get("deviation_reason") or "").strip()
    interval.operator_notes = (payload.get("operator_notes") or "").strip()
    interval.pocket_penetrometer = _nullable_decimal_value(payload.get("pocket_penetrometer"))
    interval.pocket_penetrometer_top = _nullable_decimal_value(payload.get("pocket_penetrometer_top"))
    interval.pocket_penetrometer_middle = _nullable_decimal_value(payload.get("pocket_penetrometer_middle"))
    interval.pocket_penetrometer_bottom = _nullable_decimal_value(payload.get("pocket_penetrometer_bottom"))
    interval.rqd_percent = _nullable_decimal_value(payload.get("rqd_percent"))
    _normalize_interval_type_specific_fields(interval, sample_type=sample_type)
    interval.sample_label = sample_label_for_boring(interval.boring.name, interval.sequence_number)
    interval.save()

    observation_payload = payload.get("observation") or {}
    if _observation_payload_present(observation_payload):
        observation, _created = SampleObservation.objects.get_or_create(interval=interval)
        observation.visual_classification = (observation_payload.get("visual_classification") or "").strip()
        observation.moisture_condition = (observation_payload.get("moisture_condition") or "").strip()
        observation.color = (observation_payload.get("color") or "").strip()
        observation.description = (observation_payload.get("description") or "").strip()
        observation.recovery_length = _decimal_value(observation_payload.get("recovery_length"), default="0.00")
        observation.recovery_percent = _nullable_decimal_value(observation_payload.get("recovery_percent"))
        observation.sample_condition = (observation_payload.get("sample_condition") or "").strip()
        observation.core_run_length = _nullable_decimal_value(observation_payload.get("core_run_length"))
        observation.rock_core_classification = (observation_payload.get("rock_core_classification") or "").strip()
        observation.rock_type_name = (observation_payload.get("rock_type_name") or "").strip()
        observation.rock_notes = (observation_payload.get("rock_notes") or "").strip()
        _normalize_observation_type_specific_fields(observation, sample_type=sample_type)
        observation.retained_sample = _bool_value(observation_payload.get("retained_sample"))
        observation.notes = (observation_payload.get("notes") or "").strip()
        observation.save()
    elif hasattr(interval, "observation"):
        interval.observation.delete()

    spt_payload = payload.get("spt_result") or {}
    if sample_type == SampleInterval.SampleType.SPT and _spt_payload_present(spt_payload):
        spt_result, _created = SPTResult.objects.get_or_create(interval=interval)
        spt_result.blows_1 = _int_value(spt_payload.get("blows_1"))
        spt_result.blows_2 = _int_value(spt_payload.get("blows_2"))
        spt_result.blows_3 = _int_value(spt_payload.get("blows_3"))
        spt_result.refusal_flag = _bool_value(spt_payload.get("refusal_flag"))
        spt_result.notes = (spt_payload.get("notes") or "").strip()
        spt_result.save()
    elif hasattr(interval, "spt_result"):
        interval.spt_result.delete()

    _validate_interval_type_specific_fields(
        interval,
        sample_type=sample_type,
        state=next_state,
        spt_payload=spt_payload,
    )


def _sync_intervals(boring: BoringExecution, payload_intervals: list[dict]) -> None:
    seen_interval_ids: set[int] = set()
    max_sequence = boring.intervals.aggregate(max_sequence=models.Max("sequence_number")).get("max_sequence") or 0

    for interval_payload in payload_intervals:
        interval = _resolve_interval(boring, interval_payload)
        if interval is None:
            requested_sequence = interval_payload.get("sequence_number")
            if requested_sequence in (None, ""):
                max_sequence += 1
                requested_sequence = max_sequence
            else:
                requested_sequence = int(requested_sequence)
                max_sequence = max(max_sequence, requested_sequence)
            interval = SampleInterval.objects.create(
                boring=boring,
                sampling_plan=getattr(boring, "sampling_plan", None),
                sequence_number=requested_sequence,
                method_key=(interval_payload.get("method_key") or STANDARD_SPT_METHOD_KEY).strip(),
                sample_type=_sample_type_value(interval_payload.get("sample_type")),
                state=SampleInterval.State.PLANNED,
                planned_from_depth=_decimal_value(
                    interval_payload.get("planned_from_depth") or interval_payload.get("actual_from_depth"),
                ),
                planned_to_depth=_decimal_value(
                    interval_payload.get("planned_to_depth") or interval_payload.get("actual_to_depth"),
                ),
                sample_label=sample_label_for_boring(boring.name, requested_sequence),
                is_manual=_bool_value(interval_payload.get("is_manual")) or True,
                deviation_reason=(interval_payload.get("deviation_reason") or "").strip(),
                operator_notes=(interval_payload.get("operator_notes") or "").strip(),
            )

        seen_interval_ids.add(interval.id)
        _upsert_interval(interval, interval_payload)

    for interval in boring.intervals.filter(is_manual=True):
        if interval.id not in seen_interval_ids and interval.state == SampleInterval.State.PLANNED:
            interval.delete()


def _sync_groundwater_observations(boring: BoringExecution, payload: list[dict]) -> None:
    boring.groundwater_observations.all().delete()
    for groundwater_payload in payload:
        if groundwater_payload.get("depth") in (None, ""):
            continue
        GroundwaterObservation.objects.create(
            boring=boring,
            observation_type=(groundwater_payload.get("observation_type") or GroundwaterObservation.ObservationType.ENCOUNTERED).strip(),
            depth=_decimal_value(groundwater_payload.get("depth")),
            observed_at=_datetime_value(groundwater_payload.get("observed_at")),
            note=(groundwater_payload.get("note") or "").strip(),
        )


def _sync_completion(boring: BoringExecution, payload: dict | None) -> None:
    if not payload:
        if hasattr(boring, "completion") and boring.status in {BoringExecution.Status.PLANNED, BoringExecution.Status.ACTIVE}:
            boring.completion.delete()
        derived_status = _derive_boring_status(boring)
        if boring.status != derived_status:
            boring.status = derived_status
            boring.save(update_fields=["status", "updated_at"])
        return

    completion, _created = BoringCompletion.objects.get_or_create(
        boring=boring,
        defaults={"final_depth": _decimal_value(payload.get("final_depth"))},
    )
    completion.completed_at = _datetime_value(payload.get("completed_at")) or completion.completed_at or timezone.now()
    completion.final_depth = _decimal_value(payload.get("final_depth"))
    completion.termination_reason = (
        payload.get("termination_reason") or BoringCompletion.TerminationReason.REACHED_PLANNED_DEPTH
    ).strip()
    completion.refusal_depth = _nullable_decimal_value(payload.get("refusal_depth"))
    completion.obstruction_depth = _nullable_decimal_value(payload.get("obstruction_depth"))
    completion.cave_in_depth = _nullable_decimal_value(payload.get("cave_in_depth"))
    completion.notes = (payload.get("notes") or "").strip()
    completion.save()

    boring.actual_depth = completion.final_depth
    boring.status = _derive_boring_status(boring)
    boring.save(update_fields=["actual_depth", "status", "updated_at"])

    for interval in boring.intervals.order_by("sequence_number", "id"):
        if interval.actual_to_depth is not None:
            continue
        if interval.planned_from_depth >= completion.final_depth or interval.planned_to_depth > completion.final_depth:
            if interval.state == SampleInterval.State.PLANNED:
                interval.state = SampleInterval.State.TERMINATED_EARLY
                interval.save(update_fields=["state", "updated_at"])


def _upsert_boring(record: DrillingInputRecord, boring_payload: dict, *, default_name: str) -> BoringExecution:
    boring = _resolve_boring(record, boring_payload)
    if boring is None:
        boring = BoringExecution.objects.create(
            drilling_input_record=record,
            name=(boring_payload.get("name") or default_name).strip() or default_name,
            planned_sequence=_int_value(boring_payload.get("planned_sequence")),
            planned_category=(boring_payload.get("planned_category") or boring_payload.get("category") or "").strip(),
            planned_depth=_decimal_value(boring_payload.get("planned_depth") or "0.00"),
        )

    if not _boring_is_scope_boring(boring):
        boring.name = (boring_payload.get("name") or boring.name or default_name).strip() or default_name
        if "planned_sequence" in boring_payload:
            boring.planned_sequence = _int_value(boring_payload.get("planned_sequence"))
        if "planned_category" in boring_payload or "category" in boring_payload:
            boring.planned_category = (boring_payload.get("planned_category") or boring_payload.get("category") or "").strip()
        boring.planned_depth = _decimal_value(boring_payload.get("planned_depth") or boring.planned_depth or "0.00")
    if "actual_depth" in boring_payload:
        boring.actual_depth = _nullable_decimal_value(boring_payload.get("actual_depth"))
    boring.drilling_method = (boring_payload.get("drilling_method") or "").strip()
    boring.surface_elevation = _nullable_decimal_value(boring_payload.get("surface_elevation"))
    boring.backfill_method = (boring_payload.get("backfill_method") or "").strip()
    boring.notes = (boring_payload.get("notes") or "").strip()
    boring.relocation_note = (boring_payload.get("relocation_note") or "").strip()
    boring.save()

    target_depth = _generated_depth_target(boring_payload, boring)
    sampling_plan = _ensure_sampling_plan(boring, target_depth)
    _sync_generated_intervals(boring, sampling_plan, target_depth)
    _sync_intervals(boring, boring_payload.get("intervals") or [])
    _sync_groundwater_observations(boring, boring_payload.get("groundwater_observations") or [])
    _sync_completion(
        boring,
        boring_payload.get("completion") or None,
    )
    boring.status = _derive_boring_status(boring)
    boring.save(update_fields=["status", "updated_at"])
    return boring


@transaction.atomic
def update_drilling_input_record(
    record: DrillingInputRecord,
    *,
    payload: dict,
    actor: str | dict | None,
    allow_under_review: bool = False,
) -> DrillingInputRecord:
    allowed_statuses = {
        DrillingInputRecord.Status.DRAFT,
        DrillingInputRecord.Status.NEEDS_CORRECTION,
    }
    if allow_under_review:
        allowed_statuses.add(DrillingInputRecord.Status.UNDER_REVIEW)
        allowed_statuses.add(DrillingInputRecord.Status.SUBMITTED)
    if record.status not in allowed_statuses:
        raise ValueError("Only active field logs may be edited.")

    borings_payload = payload.get("borings") or []
    if not isinstance(borings_payload, list):
        raise ValueError("borings must be a list.")
    _validate_update_payload(payload)

    record.notes = (payload.get("notes") or "").strip()
    if not record.entered_by:
        record.entered_by = _actor_label(actor)
    record.save(update_fields=["notes", "entered_by", "updated_at"])

    seen_boring_ids: set[int] = set()
    for index, boring_payload in enumerate(borings_payload, start=1):
        boring = _upsert_boring(record, boring_payload, default_name=f"B-{index}")
        seen_boring_ids.add(boring.id)

    for boring in record.borings.all():
        if boring.id not in seen_boring_ids:
            if _boring_is_scope_boring(boring):
                continue
            boring.delete()

    if record.status in {
        DrillingInputRecord.Status.DRAFT,
        DrillingInputRecord.Status.NEEDS_CORRECTION,
    }:
        record.field_execution.status = FieldExecution.Status.IN_PROGRESS
        record.field_execution.status_detail = "Field log drafting is in progress."
        record.field_execution.save(update_fields=["status", "status_detail", "updated_at"])
    return record


def _validate_record_can_submit(record: DrillingInputRecord) -> None:
    if not record.borings.exists():
        raise ValueError("At least one boring is required before submitting a field log.")


def _custody_sample_rows(record: DrillingInputRecord) -> list[dict]:
    rows: list[dict] = []
    for boring in record.borings.all():
        for interval in boring.intervals.all():
            if interval.state != SampleInterval.State.TAKEN:
                continue
            rows.append(
                {
                    "internal_sample_id": interval.internal_sample_id,
                    "sample_label": interval.sample_label or interval.internal_sample_id,
                    "boring_name": boring.name,
                }
            )
    return rows


def _validate_chain_of_custody_payload(record: DrillingInputRecord, payload: dict | None) -> None:
    sample_rows = _custody_sample_rows(record)
    if not sample_rows:
        return

    if not isinstance(payload, dict):
        raise FieldLogValidationError(
            "Capture sample handoff details before completing the field log.",
            field_errors={"custody": "Sample handoff details are required before completion."},
        )

    field_errors: dict[str, str] = {}
    transfer_method_values = {value for value, _label in CHAIN_OF_CUSTODY_TRANSFER_METHOD_OPTIONS}
    destination_type_values = {value for value, _label in CHAIN_OF_CUSTODY_DESTINATION_TYPE_OPTIONS}

    for field_name, message in (
        ("released_by_name", "Released by is required."),
        ("released_by_role", "Released-by role is required."),
        ("transfer_location", "Transfer location is required."),
        ("destination_name", "Destination name is required."),
    ):
        if not _raw_text(payload.get(field_name)):
            _add_field_error(field_errors, f"custody.{field_name}", message)

    _validate_datetime_field(
        field_errors,
        path="custody.released_at",
        value=payload.get("released_at"),
        required_message="Release time is required.",
    )
    _validate_choice_field(
        field_errors,
        path="custody.transfer_method",
        value=payload.get("transfer_method"),
        valid_values=transfer_method_values,
        required_message="Transfer method is required.",
        invalid_message="Select a valid transfer method.",
    )
    _validate_choice_field(
        field_errors,
        path="custody.destination_type",
        value=payload.get("destination_type"),
        valid_values=destination_type_values,
        required_message="Destination type is required.",
        invalid_message="Select a valid destination type.",
    )

    received_by_name = _raw_text(payload.get("received_by_name"))
    received_by_role = _raw_text(payload.get("received_by_role"))
    received_at = _raw_text(payload.get("received_at"))
    if received_by_name or received_by_role or received_at:
        if not received_by_name:
            _add_field_error(field_errors, "custody.received_by_name", "Received by is required when receipt is captured.")
        if not received_by_role:
            _add_field_error(field_errors, "custody.received_by_role", "Received-by role is required when receipt is captured.")
        _validate_datetime_field(
            field_errors,
            path="custody.received_at",
            value=payload.get("received_at"),
            required_message="Receipt time is required when receipt is captured.",
        )

    if field_errors:
        raise FieldLogValidationError(
            "Capture sample handoff details before completing the field log.",
            field_errors=field_errors,
        )


def _upsert_chain_of_custody(record: DrillingInputRecord, payload: dict | None) -> None:
    if not payload:
        return
    _validate_chain_of_custody_payload(record, payload)
    # complete_drilling_input_record() validates custody before calling this helper,
    # so persistence here should only create/update with validated values.
    custody_values = {
        "released_by_name": _raw_text(payload.get("released_by_name")),
        "released_by_role": _raw_text(payload.get("released_by_role")),
        "released_at": _datetime_value(payload.get("released_at")),
        "received_by_name": _raw_text(payload.get("received_by_name")),
        "received_by_role": _raw_text(payload.get("received_by_role")),
        "received_at": _datetime_value(payload.get("received_at")),
        "transfer_method": _raw_text(payload.get("transfer_method")),
        "transfer_location": _raw_text(payload.get("transfer_location")),
        "destination_type": _raw_text(payload.get("destination_type")),
        "destination_name": _raw_text(payload.get("destination_name")),
        "tracking_number": _raw_text(payload.get("tracking_number")),
        "sample_condition_on_transfer": _raw_text(payload.get("sample_condition_on_transfer")),
        "custody_notes": _raw_text(payload.get("custody_notes")),
    }
    custody = SampleChainOfCustody.objects.filter(drilling_input_record=record).first()
    if custody is None:
        SampleChainOfCustody.objects.create(
            drilling_input_record=record,
            **custody_values,
        )
        return

    for field_name, value in custody_values.items():
        setattr(custody, field_name, value)
    custody.save()


@transaction.atomic
def submit_drilling_input_record(record: DrillingInputRecord, *, actor: str | dict | None) -> DrillingInputRecord:
    if record.status not in {
        DrillingInputRecord.Status.DRAFT,
        DrillingInputRecord.Status.NEEDS_CORRECTION,
    }:
        raise ValueError("Only draft or correction-requested logs may be submitted.")

    _validate_record_can_submit(record)
    record.entered_by = record.entered_by or _actor_label(actor)
    record.submitted_at = timezone.now()
    record.status = DrillingInputRecord.Status.UNDER_REVIEW
    record.save(update_fields=["entered_by", "submitted_at", "status", "updated_at"])

    record.field_execution.status = FieldExecution.Status.SUBMITTED
    record.field_execution.status_detail = "Field log was submitted and is ready for employee completion."
    record.field_execution.save(update_fields=["status", "status_detail", "updated_at"])
    return record


@transaction.atomic
def complete_drilling_input_record(
    record: DrillingInputRecord,
    *,
    actor: str | dict | None,
    custody_payload: dict | None = None,
) -> DrillingInputPDF:
    if record.status == DrillingInputRecord.Status.ACCEPTED:
        return ensure_drilling_input_pdf_current(record)
    if record.status not in {
        DrillingInputRecord.Status.DRAFT,
        DrillingInputRecord.Status.SUBMITTED,
        DrillingInputRecord.Status.UNDER_REVIEW,
        DrillingInputRecord.Status.NEEDS_CORRECTION,
    }:
        raise ValueError("Only active field logs may be completed.")

    _validate_record_can_submit(record)
    _validate_chain_of_custody_payload(record, custody_payload)
    now = timezone.now()
    record.entered_by = record.entered_by or _actor_label(actor)
    record.submitted_at = record.submitted_at or now
    record.reviewed_by = _actor_label(actor)
    record.accepted_at = now
    record.status = DrillingInputRecord.Status.ACCEPTED
    record.save(
        update_fields=[
            "entered_by",
            "submitted_at",
            "reviewed_by",
            "accepted_at",
            "status",
            "updated_at",
        ]
    )
    _upsert_chain_of_custody(record, custody_payload)

    record.field_execution.status = FieldExecution.Status.ACCEPTED
    record.field_execution.status_detail = "Field log completed and ready for downstream consumption."
    record.field_execution.save(update_fields=["status", "status_detail", "updated_at"])
    return ensure_drilling_input_pdf_current(record)


def sample_observation_payload(observation: SampleObservation | None) -> dict | None:
    if observation is None:
        return None
    return {
        "id": observation.id,
        "shared_uuid": str(observation.shared_uuid),
        "visual_classification": observation.visual_classification,
        "provisional_field_classification": observation.visual_classification or None,
        "moisture_condition": observation.moisture_condition,
        "color": observation.color,
        "description": observation.description,
        "provisional_description": observation.description or None,
        "recovery_length": str(observation.recovery_length),
        "recovery_percent": str(observation.recovery_percent) if observation.recovery_percent is not None else None,
        "sample_condition": observation.sample_condition or None,
        "core_run_length": str(observation.core_run_length) if observation.core_run_length is not None else None,
        "rock_core_classification": observation.rock_core_classification or None,
        "rock_type_name": observation.rock_type_name or None,
        "rock_notes": observation.rock_notes or None,
        "retained_sample": observation.retained_sample,
        "notes": observation.notes,
    }


def spt_result_payload(result: SPTResult | None) -> dict | None:
    if result is None:
        return None
    return {
        "id": result.id,
        "shared_uuid": str(result.shared_uuid),
        "blows_1": result.blows_1,
        "blows_2": result.blows_2,
        "blows_3": result.blows_3,
        "n_value": result.n_value,
        "refusal_flag": result.refusal_flag,
        "notes": result.notes,
    }


def interval_payload(interval: SampleInterval) -> dict:
    observation = getattr(interval, "observation", None)
    spt_result = getattr(interval, "spt_result", None)
    return {
        "id": interval.id,
        "shared_uuid": str(interval.shared_uuid),
        "sequence_number": interval.sequence_number,
        "method_key": interval.method_key,
        "sample_type": interval.sample_type,
        "state": interval.state,
        "planned_from_depth": str(interval.planned_from_depth),
        "planned_to_depth": str(interval.planned_to_depth),
        "actual_from_depth": str(interval.actual_from_depth) if interval.actual_from_depth is not None else None,
        "actual_to_depth": str(interval.actual_to_depth) if interval.actual_to_depth is not None else None,
        "internal_sample_id": interval.internal_sample_id,
        "sample_label": interval.sample_label,
        "is_manual": interval.is_manual,
        "deviation_reason": interval.deviation_reason or None,
        "operator_notes": interval.operator_notes or None,
        "pocket_penetrometer": str(interval.pocket_penetrometer) if interval.pocket_penetrometer is not None else None,
        "pocket_penetrometer_top": str(interval.pocket_penetrometer_top) if interval.pocket_penetrometer_top is not None else None,
        "pocket_penetrometer_middle": str(interval.pocket_penetrometer_middle) if interval.pocket_penetrometer_middle is not None else None,
        "pocket_penetrometer_bottom": str(interval.pocket_penetrometer_bottom) if interval.pocket_penetrometer_bottom is not None else None,
        "rqd_percent": str(interval.rqd_percent) if interval.rqd_percent is not None else None,
        "observation": sample_observation_payload(observation),
        "spt_result": spt_result_payload(spt_result),
        "recommended_tests": _recommended_tests_for_sample_type(interval.sample_type),
    }


def groundwater_observation_payload(observation: GroundwaterObservation) -> dict:
    return {
        "id": observation.id,
        "shared_uuid": str(observation.shared_uuid),
        "observation_type": observation.observation_type,
        "depth": str(observation.depth),
        "observed_at": observation.observed_at.isoformat() if observation.observed_at else None,
        "note": observation.note or None,
    }


def boring_completion_payload(completion: BoringCompletion | None) -> dict | None:
    if completion is None:
        return None
    return {
        "id": completion.id,
        "shared_uuid": str(completion.shared_uuid),
        "completed_at": completion.completed_at.isoformat() if completion.completed_at else None,
        "final_depth": str(completion.final_depth),
        "termination_reason": completion.termination_reason,
        "refusal_depth": str(completion.refusal_depth) if completion.refusal_depth is not None else None,
        "obstruction_depth": str(completion.obstruction_depth) if completion.obstruction_depth is not None else None,
        "cave_in_depth": str(completion.cave_in_depth) if completion.cave_in_depth is not None else None,
        "notes": completion.notes or None,
    }


def boring_payload(boring: BoringExecution) -> dict:
    sampling_plan = getattr(boring, "sampling_plan", None)
    completion = getattr(boring, "completion", None)
    return {
        "id": boring.id,
        "shared_uuid": str(boring.shared_uuid),
        "name": boring.name,
        "planned_sequence": boring.planned_sequence or None,
        "planned_category": boring.planned_category or None,
        "is_scope_boring": _boring_is_scope_boring(boring),
        "can_remove": not _boring_is_scope_boring(boring),
        "planned_depth": str(boring.planned_depth),
        "actual_depth": str(boring.actual_depth) if boring.actual_depth is not None else None,
        "status": boring.status,
        "drilling_method": boring.drilling_method,
        "surface_elevation": str(boring.surface_elevation) if boring.surface_elevation is not None else None,
        "backfill_method": boring.backfill_method,
        "notes": boring.notes,
        "relocation_note": boring.relocation_note,
        "sampling_plan": (
            {
                "id": sampling_plan.id,
                "shared_uuid": str(sampling_plan.shared_uuid),
                "method_key": sampling_plan.method_key,
                "rule_type": sampling_plan.rule_type,
                "rule_config": sampling_plan.rule_config,
                "generated_to_depth": str(sampling_plan.generated_to_depth),
                "is_default": sampling_plan.is_default,
            }
            if sampling_plan is not None
            else None
        ),
        "intervals": [interval_payload(interval) for interval in boring.intervals.all()],
        "groundwater_observations": [
            groundwater_observation_payload(observation)
            for observation in boring.groundwater_observations.all()
        ],
        "completion": boring_completion_payload(completion),
    }


def chain_of_custody_payload(record: DrillingInputRecord, custody: SampleChainOfCustody | None) -> dict | None:
    sample_rows = _custody_sample_rows(record)
    if custody is None and not sample_rows:
        return None

    status = "pending_transfer"
    status_label = "Pending transfer"
    if not sample_rows:
        status = "not_required"
        status_label = "No transferred samples"
    elif custody is not None and custody.received_at is not None:
        status = "received"
        status_label = "Received"
    elif custody is not None and custody.released_at is not None:
        status = "in_transit"
        status_label = "In transit"

    if custody is None:
        return {
            "status": status,
            "status_label": status_label,
            "sample_count": len(sample_rows),
            "samples": sample_rows,
        }

    return {
        "id": custody.id,
        "shared_uuid": str(custody.shared_uuid),
        "status": status,
        "status_label": status_label,
        "released_by_name": custody.released_by_name,
        "released_by_role": custody.released_by_role,
        "released_at": custody.released_at.isoformat() if custody.released_at else None,
        "received_by_name": custody.received_by_name or None,
        "received_by_role": custody.received_by_role or None,
        "received_at": custody.received_at.isoformat() if custody.received_at else None,
        "transfer_method": custody.transfer_method,
        "transfer_location": custody.transfer_location,
        "destination_type": custody.destination_type,
        "destination_name": custody.destination_name,
        "tracking_number": custody.tracking_number or None,
        "sample_condition_on_transfer": custody.sample_condition_on_transfer or None,
        "custody_notes": custody.custody_notes or None,
        "sample_count": len(sample_rows),
        "samples": sample_rows,
    }


def field_log_artifact_payload(record: DrillingInputRecord, artifact: DrillingInputPDF | None) -> dict | None:
    if artifact is None:
        return None
    return {
        "file_name": artifact.file.name if artifact.file else None,
        "display_name": field_log_pdf_display_name(record),
        "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        "generated_at": artifact.generated_at.isoformat() if artifact.generated_at else None,
        "fingerprint": artifact.fingerprint or None,
        "template_version": artifact.template_version or None,
        "content_type": "application/pdf" if artifact.file else None,
        "size_bytes": _safe_file_size(artifact.file),
        "available": bool(artifact.file and artifact.file.name),
        "artifact_type": "field_log_pdf_snapshot",
    }


def drilling_input_record_payload(record: DrillingInputRecord) -> dict:
    pdf_artifact = getattr(record, "pdf_artifact", None)
    custody = getattr(record, "chain_of_custody", None)
    return {
        "id": record.id,
        "shared_uuid": str(record.shared_uuid),
        "entry_method": record.entry_method,
        "status": record.status,
        "entered_by": record.entered_by or None,
        "submitted_at": record.submitted_at.isoformat() if record.submitted_at else None,
        "reviewed_by": record.reviewed_by or None,
        "accepted_at": record.accepted_at.isoformat() if record.accepted_at else None,
        "notes": record.notes,
        "borings": [boring_payload(boring) for boring in record.borings.all()],
        "attachments": [
            {
                "id": attachment.id,
                "shared_uuid": str(attachment.shared_uuid),
                "file_name": attachment.file.name,
                "source_note": attachment.source_note,
            }
            for attachment in record.attachments.all()
        ],
        "pdf": field_log_artifact_payload(record, pdf_artifact),
        "custody": chain_of_custody_payload(record, custody),
    }


def _records_queryset(execution: FieldExecution):
    return execution.drilling_input_records.prefetch_related(
        "attachments",
        Prefetch(
            "borings",
            queryset=BoringExecution.objects.select_related("sampling_plan", "completion").prefetch_related(
                Prefetch(
                    "intervals",
                    queryset=SampleInterval.objects.select_related("observation", "spt_result").order_by("sequence_number", "id"),
                ),
                "groundwater_observations",
            ).order_by("created_at", "id"),
        ),
    ).select_related("pdf_artifact", "chain_of_custody").order_by("-updated_at", "-id")


def field_execution_payload(execution: FieldExecution, *, include_records: bool = True) -> dict:
    records_queryset = _records_queryset(execution)
    latest_record = records_queryset.first()
    accepted_record = execution.drilling_input_records.filter(status=DrillingInputRecord.Status.ACCEPTED).prefetch_related(
        "attachments",
        Prefetch(
            "borings",
            queryset=BoringExecution.objects.select_related("sampling_plan", "completion").prefetch_related(
                Prefetch(
                    "intervals",
                    queryset=SampleInterval.objects.select_related("observation", "spt_result").order_by("sequence_number", "id"),
                ),
                "groundwater_observations",
            ),
        ),
    ).select_related("pdf_artifact", "chain_of_custody").first()
    return {
        "id": execution.id,
        "shared_uuid": str(execution.shared_uuid),
        "external_project_id": execution.external_project_id,
        "project_number": execution.project_number,
        "proposal_number": execution.proposal_number,
        "project_name": execution.project_name,
        "client_name": execution.client_name,
        "planned_borings": _planned_borings_for_execution(execution),
        "assigned_driller": {
            "id": execution.assigned_driller.id,
            "shared_uuid": str(execution.assigned_driller.shared_uuid),
            "company_name": execution.assigned_driller.company_name,
            "display_name": execution.assigned_driller.display_name,
        },
        "scheduled_start_date": execution.scheduled_start_date.isoformat() if execution.scheduled_start_date else None,
        "estimated_days": str(execution.estimated_days),
        "status": execution.status,
        "status_detail": execution.status_detail or None,
        "dashboard_status": dashboard_status_for_execution(execution),
        "field_log_options": field_log_form_options_payload(),
        "latest_record": drilling_input_record_payload(latest_record) if latest_record is not None else None,
        "accepted_record": drilling_input_record_payload(accepted_record) if accepted_record is not None else None,
        "records": [drilling_input_record_payload(record) for record in records_queryset] if include_records else [],
    }


def accepted_field_log_payload(execution: FieldExecution) -> dict:
    accepted_records = execution.drilling_input_records.filter(
        status=DrillingInputRecord.Status.ACCEPTED,
    ).prefetch_related(
        "attachments",
        Prefetch(
            "borings",
            queryset=BoringExecution.objects.select_related("sampling_plan", "completion").prefetch_related(
                Prefetch(
                    "intervals",
                    queryset=SampleInterval.objects.select_related("observation", "spt_result").order_by("sequence_number", "id"),
                ),
                "groundwater_observations",
            ),
        ),
    ).select_related("pdf_artifact", "chain_of_custody")
    items = [drilling_input_record_payload(record) for record in accepted_records]
    return {
        "schema_version": "field-log-export-v1",
        "export_type": "accepted_field_logs",
        "external_project_id": execution.external_project_id,
        "project_number": execution.project_number,
        "proposal_number": execution.proposal_number,
        "project_name": execution.project_name,
        "status": execution.status,
        "scheduled_start_date": execution.scheduled_start_date.isoformat() if execution.scheduled_start_date else None,
        "estimated_days": str(execution.estimated_days),
        "field_execution": {
            "shared_uuid": str(execution.shared_uuid),
            "status": execution.status,
            "status_detail": execution.status_detail or None,
            "assigned_driller": {
                "id": execution.assigned_driller.id,
                "shared_uuid": str(execution.assigned_driller.shared_uuid),
                "company_name": execution.assigned_driller.company_name,
                "display_name": execution.assigned_driller.display_name,
            },
        },
        "accepted_field_logs": items,
        "items": items,
    }


def accepted_drilling_input_payload(execution: FieldExecution) -> dict:
    return accepted_field_log_payload(execution)
