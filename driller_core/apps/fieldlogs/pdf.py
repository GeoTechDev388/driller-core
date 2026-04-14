from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.core.files.base import ContentFile
from django.utils import timezone

from driller_core.documents.rendering.hashes import compute_render_fingerprint
from driller_core.documents.rendering.service import PROJECT_ROOT, STYLES_ROOT, render_html, render_pdf_from_html

from .models import DrillingInputPDF, DrillingInputRecord, SampleInterval


FIELD_LOG_TEMPLATE_VERSION = "field-log-v3"
FIELD_LOG_TEMPLATE_NAME = "fieldlogs/field_log.html.j2"
FIELD_LOG_STYLESHEETS = (
    STYLES_ROOT / "fieldlogs" / "field_log.css",
)


def _humanize(value: str | None, *, uppercase_spt: bool = False) -> str:
    raw = (value or "").strip()
    if not raw:
        return "Not captured"
    if uppercase_spt and raw == SampleInterval.SampleType.SPT:
        return "SPT"
    return raw.replace("_", " ").title()


def _display_decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _display_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d")


def _display_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")


def _interval_context(interval: SampleInterval) -> dict:
    observation = getattr(interval, "observation", None)
    spt_result = getattr(interval, "spt_result", None)
    return {
        "sequence_number": interval.sequence_number,
        "sample_label": interval.sample_label,
        "internal_sample_id": interval.internal_sample_id,
        "sample_type": interval.sample_type,
        "sample_type_label": _humanize(interval.sample_type, uppercase_spt=True),
        "state": interval.state,
        "state_label": _humanize(interval.state),
        "planned_from_depth": str(interval.planned_from_depth),
        "planned_to_depth": str(interval.planned_to_depth),
        "actual_from_depth": _display_decimal(interval.actual_from_depth),
        "actual_to_depth": _display_decimal(interval.actual_to_depth),
        "deviation_reason": interval.deviation_reason or None,
        "operator_notes": interval.operator_notes or None,
        "pocket_penetrometer": _display_decimal(interval.pocket_penetrometer),
        "pocket_penetrometer_top": _display_decimal(interval.pocket_penetrometer_top),
        "pocket_penetrometer_middle": _display_decimal(interval.pocket_penetrometer_middle),
        "pocket_penetrometer_bottom": _display_decimal(interval.pocket_penetrometer_bottom),
        "rqd_percent": _display_decimal(interval.rqd_percent),
        "observation": (
            {
                "provisional_field_classification": observation.visual_classification or None,
                "visual_classification": observation.visual_classification or None,
                "moisture_condition": observation.moisture_condition or None,
                "color": observation.color or None,
                "description": observation.description or None,
                "provisional_description": observation.description or None,
                "recovery_length": str(observation.recovery_length),
                "recovery_percent": _display_decimal(observation.recovery_percent),
                "sample_condition": observation.sample_condition or None,
                "core_run_length": _display_decimal(observation.core_run_length),
                "rock_core_classification": observation.rock_core_classification or None,
                "rock_type_name": observation.rock_type_name or None,
                "rock_notes": observation.rock_notes or None,
                "retained_sample": observation.retained_sample,
                "notes": observation.notes or None,
            }
            if observation is not None
            else None
        ),
        "spt_result": (
            {
                "blows_1": spt_result.blows_1,
                "blows_2": spt_result.blows_2,
                "blows_3": spt_result.blows_3,
                "n_value": spt_result.n_value,
                "refusal_flag": spt_result.refusal_flag,
                "notes": spt_result.notes or None,
            }
            if spt_result is not None
            else None
        ),
    }


def build_field_log_pdf_context(record: DrillingInputRecord) -> dict:
    execution = record.field_execution
    driller = execution.assigned_driller
    custody = getattr(record, "chain_of_custody", None)
    borings = []
    for boring in record.borings.select_related("sampling_plan", "completion").prefetch_related(
        "intervals__observation",
        "intervals__spt_result",
        "groundwater_observations",
    ):
        borings.append(
            {
                "name": boring.name,
                "planned_sequence": boring.planned_sequence or None,
                "planned_category": boring.planned_category or None,
                "planned_depth": str(boring.planned_depth),
                "actual_depth": _display_decimal(boring.actual_depth),
                "status": boring.status,
                "status_label": _humanize(boring.status),
                "drilling_method": boring.drilling_method or None,
                "surface_elevation": _display_decimal(boring.surface_elevation),
                "backfill_method": boring.backfill_method or None,
                "notes": boring.notes or None,
                "relocation_note": boring.relocation_note or None,
                "sampling_plan": (
                    {
                        "method_key": boring.sampling_plan.method_key,
                        "rule_type": boring.sampling_plan.rule_type,
                        "generated_to_depth": str(boring.sampling_plan.generated_to_depth),
                    }
                    if getattr(boring, "sampling_plan", None) is not None
                    else None
                ),
                "intervals": [_interval_context(interval) for interval in boring.intervals.all()],
                "groundwater_observations": [
                    {
                        "observation_type": observation.observation_type,
                        "observation_type_label": _humanize(observation.observation_type),
                        "depth": str(observation.depth),
                        "observed_at": _display_datetime(observation.observed_at),
                        "note": observation.note or None,
                    }
                    for observation in boring.groundwater_observations.all()
                ],
                "completion": (
                    {
                        "completed_at": _display_datetime(boring.completion.completed_at),
                        "final_depth": str(boring.completion.final_depth),
                        "termination_reason": boring.completion.termination_reason,
                        "termination_reason_label": _humanize(boring.completion.termination_reason),
                        "refusal_depth": _display_decimal(boring.completion.refusal_depth),
                        "obstruction_depth": _display_decimal(boring.completion.obstruction_depth),
                        "cave_in_depth": _display_decimal(boring.completion.cave_in_depth),
                        "notes": boring.completion.notes or None,
                    }
                    if getattr(boring, "completion", None) is not None
                    else None
                ),
            }
        )

    return {
        "artifact_title": "Operational Field Log",
        "boundary_note": "Operational/provisional field artifact only. This record is not the final boring log and does not represent final lab-backed engineering classifications.",
        "project_number": execution.project_number,
        "proposal_number": execution.proposal_number,
        "project_name": execution.project_name,
        "client_name": execution.client_name,
        "external_project_id": execution.external_project_id,
        "scheduled_start_date": _display_date(execution.scheduled_start_date),
        "estimated_days": str(execution.estimated_days),
        "entry_method": record.get_entry_method_display(),
        "record_reference": str(record.shared_uuid),
        "record_status": record.status,
        "record_status_label": _humanize(record.status),
        "entered_by": record.entered_by or None,
        "submitted_at": _display_datetime(record.submitted_at),
        "reviewed_by": record.reviewed_by or None,
        "accepted_at": _display_datetime(record.accepted_at),
        "custody": (
            {
                "released_by_name": custody.released_by_name,
                "released_by_role": custody.released_by_role,
                "released_at": _display_datetime(custody.released_at),
                "received_by_name": custody.received_by_name or None,
                "received_by_role": custody.received_by_role or None,
                "received_at": _display_datetime(custody.received_at),
                "transfer_method": _humanize(custody.transfer_method),
                "transfer_location": custody.transfer_location,
                "destination_type": _humanize(custody.destination_type),
                "destination_name": custody.destination_name,
                "tracking_number": custody.tracking_number or None,
                "sample_condition_on_transfer": custody.sample_condition_on_transfer or None,
                "custody_notes": custody.custody_notes or None,
            }
            if custody is not None
            else None
        ),
        "assigned_driller": {
            "company_name": driller.company_name,
            "display_name": driller.display_name,
            "contact_name": driller.contact_name or None,
            "email": driller.email or None,
            "phone": driller.phone or None,
        },
        "notes": record.notes or None,
        "borings": borings,
        "boring_count": len(borings),
    }


def field_log_pdf_display_name(record: DrillingInputRecord) -> str:
    reference = record.field_execution.project_number or record.field_execution.external_project_id
    return f"{reference} Field Log.pdf"


def ensure_drilling_input_pdf_current(record: DrillingInputRecord) -> DrillingInputPDF:
    if record.status != DrillingInputRecord.Status.ACCEPTED:
        raise ValueError("Field log PDFs may only be generated for accepted records.")

    artifact, _created = DrillingInputPDF.objects.get_or_create(drilling_input_record=record)
    context = build_field_log_pdf_context(record)
    fingerprint = compute_render_fingerprint(context, schema_version=FIELD_LOG_TEMPLATE_VERSION)
    if (
        artifact.file
        and artifact.file.name
        and artifact.fingerprint == fingerprint
        and artifact.template_version == FIELD_LOG_TEMPLATE_VERSION
        and artifact.file.storage.exists(artifact.file.name)
    ):
        return artifact

    html = render_html(FIELD_LOG_TEMPLATE_NAME, context)
    pdf_bytes = render_pdf_from_html(
        html,
        base_url=PROJECT_ROOT,
        stylesheet_paths=FIELD_LOG_STYLESHEETS,
    )
    existing_name = artifact.file.name
    if existing_name:
        artifact.file.storage.delete(existing_name)
    artifact.file.save(field_log_pdf_display_name(record), ContentFile(pdf_bytes), save=False)
    artifact.generated_at = timezone.now()
    artifact.fingerprint = fingerprint
    artifact.template_version = FIELD_LOG_TEMPLATE_VERSION
    artifact.save(update_fields=["file", "generated_at", "fingerprint", "template_version", "updated_at"])
    return artifact
