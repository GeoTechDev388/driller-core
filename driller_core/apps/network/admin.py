from django.contrib import admin

from .availability import working_day_label_map
from .models import (
    BookingRequest,
    DrillerBlackoutDate,
    DrillerCoverage,
    DrillerFeeLineItem,
    DrillerFeeSchedule,
    DrillerProfile,
)


class DrillerCoverageInline(admin.TabularInline):
    model = DrillerCoverage
    extra = 0
    fields = ("county_name", "state_code", "active")
    ordering = ("county_name", "state_code", "id")


class DrillerBlackoutDateInline(admin.TabularInline):
    model = DrillerBlackoutDate
    extra = 0
    fields = ("date", "reason", "active")
    ordering = ("date", "id")


@admin.register(DrillerProfile)
class DrillerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "company_name",
        "contact_name",
        "email",
        "phone",
        "working_days_display",
        "coverage_count",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("display_name", "company_name", "contact_name", "email", "phone")
    inlines = [DrillerCoverageInline, DrillerBlackoutDateInline]

    @admin.display(description="Working days")
    def working_days_display(self, obj: DrillerProfile) -> str:
        labels = working_day_label_map()
        selected = [labels.get(item, item.title()) for item in (obj.working_days or [])]
        return ", ".join(selected) or "None"

    @admin.display(description="Active counties")
    def coverage_count(self, obj: DrillerProfile) -> int:
        return obj.county_coverages.filter(active=True).count()


@admin.register(DrillerCoverage)
class DrillerCoverageAdmin(admin.ModelAdmin):
    list_display = ("county_name", "state_code", "driller", "active")
    list_filter = ("active", "state_code")
    search_fields = ("county_name", "driller__display_name", "driller__company_name")
    list_select_related = ("driller",)


@admin.register(DrillerBlackoutDate)
class DrillerBlackoutDateAdmin(admin.ModelAdmin):
    list_display = ("date", "driller", "reason", "active")
    list_filter = ("active", "date")
    search_fields = ("driller__display_name", "driller__company_name", "reason")
    list_select_related = ("driller",)


class DrillerFeeLineItemInline(admin.TabularInline):
    model = DrillerFeeLineItem
    extra = 0
    fields = ("sort_order", "line_item_type", "label", "amount", "metadata")
    ordering = ("sort_order", "id")


@admin.register(DrillerFeeSchedule)
class DrillerFeeScheduleAdmin(admin.ModelAdmin):
    list_display = ("driller", "name", "currency", "is_active", "line_item_count")
    list_filter = ("is_active", "currency")
    search_fields = ("driller__display_name", "name")
    list_select_related = ("driller",)
    inlines = [DrillerFeeLineItemInline]

    @admin.display(description="Line items")
    def line_item_count(self, obj: DrillerFeeSchedule) -> int:
        return obj.line_items.count()


@admin.register(DrillerFeeLineItem)
class DrillerFeeLineItemAdmin(admin.ModelAdmin):
    list_display = ("label", "line_item_type", "fee_schedule", "schedule_driller", "amount", "sort_order")
    list_filter = ("line_item_type", "fee_schedule__currency", "fee_schedule__is_active")
    search_fields = ("label", "fee_schedule__name", "fee_schedule__driller__display_name", "fee_schedule__driller__company_name")
    list_select_related = ("fee_schedule", "fee_schedule__driller")

    @admin.display(ordering="fee_schedule__driller__display_name", description="Driller")
    def schedule_driller(self, obj: DrillerFeeLineItem) -> DrillerProfile:
        return obj.fee_schedule.driller


@admin.register(BookingRequest)
class BookingRequestAdmin(admin.ModelAdmin):
    list_display = ("project_number", "project_name", "status", "assigned_driller", "committed_start_at", "committed_end_at")
    list_filter = ("status",)
    search_fields = ("project_number", "proposal_number", "project_name", "external_project_key")
