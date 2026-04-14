from django.contrib import admin

from .models import (
    BoringCompletion,
    BoringExecution,
    DrillerUser,
    DrillingInputPDF,
    DrillingInputRecord,
    FieldAttachment,
    FieldExecution,
    GroundwaterObservation,
    SPTResult,
    SampleInterval,
    SampleObservation,
    SamplingPlan,
)


class SampleObservationInline(admin.StackedInline):
    model = SampleObservation
    extra = 0


class SPTResultInline(admin.StackedInline):
    model = SPTResult
    extra = 0


class SampleIntervalInline(admin.TabularInline):
    model = SampleInterval
    extra = 0


class GroundwaterObservationInline(admin.TabularInline):
    model = GroundwaterObservation
    extra = 0


class BoringCompletionInline(admin.StackedInline):
    model = BoringCompletion
    extra = 0


@admin.register(DrillerUser)
class DrillerUserAdmin(admin.ModelAdmin):
    list_display = ("email", "driller", "is_active", "portal_access_enabled")
    search_fields = ("user_account__email", "driller__company_name", "driller__display_name")
    list_filter = ("is_active", "portal_access_enabled")


@admin.register(FieldExecution)
class FieldExecutionAdmin(admin.ModelAdmin):
    list_display = ("project_number", "assigned_driller", "scheduled_start_date", "status")
    search_fields = ("external_project_id", "project_number", "project_name", "client_name")
    list_filter = ("status",)


@admin.register(DrillingInputRecord)
class DrillingInputRecordAdmin(admin.ModelAdmin):
    list_display = ("field_execution", "entry_method", "status", "entered_by", "submitted_at", "accepted_at")
    search_fields = ("field_execution__project_number", "entered_by", "reviewed_by", "notes")
    list_filter = ("entry_method", "status")


@admin.register(BoringExecution)
class BoringExecutionAdmin(admin.ModelAdmin):
    list_display = ("name", "drilling_input_record", "status", "planned_depth", "actual_depth", "drilling_method")
    search_fields = ("name", "drilling_input_record__field_execution__project_number")
    list_filter = ("status", "drilling_method")
    inlines = [SampleIntervalInline, GroundwaterObservationInline, BoringCompletionInline]


@admin.register(SamplingPlan)
class SamplingPlanAdmin(admin.ModelAdmin):
    list_display = ("boring", "method_key", "rule_type", "generated_to_depth", "is_default")
    search_fields = ("boring__name", "boring__drilling_input_record__field_execution__project_number")


@admin.register(SampleInterval)
class SampleIntervalAdmin(admin.ModelAdmin):
    list_display = (
        "sample_label",
        "boring",
        "sequence_number",
        "sample_type",
        "state",
        "planned_from_depth",
        "planned_to_depth",
        "internal_sample_id",
    )
    search_fields = ("sample_label", "internal_sample_id", "boring__name", "boring__drilling_input_record__field_execution__project_number")
    list_filter = ("sample_type", "state", "method_key", "is_manual")
    inlines = [SampleObservationInline, SPTResultInline]


@admin.register(FieldAttachment)
class FieldAttachmentAdmin(admin.ModelAdmin):
    list_display = ("drilling_input_record", "file", "source_note")
    search_fields = ("drilling_input_record__field_execution__project_number", "source_note")


@admin.register(DrillingInputPDF)
class DrillingInputPDFAdmin(admin.ModelAdmin):
    list_display = ("drilling_input_record", "file", "generated_at", "template_version", "fingerprint")
    search_fields = ("drilling_input_record__field_execution__project_number", "fingerprint")
