from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.test import Client, TestCase, override_settings
from django.utils import timezone

from driller_core.apps.fieldlogs.models import FieldExecution

from .models import (
    BookingRequest,
    DrillerBlackoutDate,
    DrillerCoverage,
    DrillerFeeLineItem,
    DrillerFeeSchedule,
    DrillerProfile,
)
from .services import evaluate_and_commit_booking


def aware_datetime(year: int, month: int, day: int, hour: int = 7) -> datetime:
    return timezone.make_aware(
        datetime(year, month, day, hour, 0, 0),
        timezone.get_current_timezone(),
    )


@override_settings(DRILLER_CORE_INTERNAL_SHARED_SECRET="test-internal-secret")
class BookingCommitmentTests(TestCase):
    def setUp(self):
        self.client = Client()

    def _create_schedule(self, driller: DrillerProfile):
        schedule = DrillerFeeSchedule.objects.create(driller=driller, name="Standard", currency="usd")
        DrillerFeeLineItem.objects.create(
            fee_schedule=schedule,
            line_item_type=DrillerFeeLineItem.LineItemType.MOBILIZATION,
            label="Mobilization",
            amount=Decimal("1000.00"),
            sort_order=10,
        )
        DrillerFeeLineItem.objects.create(
            fee_schedule=schedule,
            line_item_type=DrillerFeeLineItem.LineItemType.PER_BORE,
            label="Per bore",
            amount=Decimal("200.00"),
            sort_order=20,
        )
        DrillerFeeLineItem.objects.create(
            fee_schedule=schedule,
            line_item_type=DrillerFeeLineItem.LineItemType.PER_FOOT,
            label="Per foot",
            amount=Decimal("10.00"),
            sort_order=30,
        )
        DrillerFeeLineItem.objects.create(
            fee_schedule=schedule,
            line_item_type=DrillerFeeLineItem.LineItemType.MINIMUM_CHARGE,
            label="Minimum charge",
            amount=Decimal("2500.00"),
            sort_order=40,
        )
        return schedule

    def _add_county_coverage(self, driller: DrillerProfile, county_name: str = "Travis", state_code: str = "TX"):
        return DrillerCoverage.objects.create(
            driller=driller,
            county_name=county_name,
            state_code=state_code,
            active=True,
        )

    def test_one_day_booking_commits_from_working_day_truth(self):
        driller = DrillerProfile.objects.create(
            company_name="Sunrise Drilling",
            display_name="Crew A",
            capability_keys=["geotechnical-drilling"],
            working_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        self._add_county_coverage(driller, "Travis")
        self._create_schedule(driller)
        booking = BookingRequest.objects.create(
            external_project_key="project-seeded-window",
            project_name="North Site",
            capability_required="geotechnical-drilling",
            coverage_area={"county": "Travis", "state_code": "TX"},
            estimated_days=Decimal("1.00"),
            earliest_start_at=aware_datetime(2026, 4, 20),
        )
        booking = evaluate_and_commit_booking(booking)
        self.assertEqual(booking.status, BookingRequest.Status.COMMITTED)
        self.assertEqual(booking.committed_start_at.date().isoformat(), "2026-04-20")

    def test_booking_request_endpoint_reuses_external_project_key(self):
        driller = DrillerProfile.objects.create(
            company_name="Sunrise Drilling",
            display_name="Crew A",
            capability_keys=["geotechnical-drilling"],
            working_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        self._add_county_coverage(driller, "Travis")
        self._create_schedule(driller)
        start_at = aware_datetime(2026, 4, 20)
        payload = {
            "external_project_key": "project-retry",
            "project_name": "North Site",
            "capability_required": "geotechnical-drilling",
            "coverage_area": {"county": "Travis", "state_code": "TX"},
            "estimated_days": "1.00",
            "earliest_start_at": start_at.isoformat(),
        }

        first = self.client.post(
            "/api/network/booking-requests/",
            data=payload,
            content_type="application/json",
            headers={"X-Internal-Service-Secret": "test-internal-secret"},
        )
        second = self.client.post(
            "/api/network/booking-requests/",
            data=payload,
            content_type="application/json",
            headers={"X-Internal-Service-Secret": "test-internal-secret"},
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(BookingRequest.objects.filter(external_project_key="project-retry").count(), 1)

    def test_booking_request_endpoint_requires_internal_secret(self):
        response = self.client.post(
            "/api/network/booking-requests/",
            data={"external_project_key": "missing-secret", "estimated_days": "1.00"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_next_available_start_moves_to_next_enabled_workday_after_active_commitment(self):
        driller = DrillerProfile.objects.create(
            company_name="Sunrise Drilling",
            display_name="Crew A",
            capability_keys=["geotechnical-drilling"],
            working_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        self._add_county_coverage(driller, "Travis")
        self._create_schedule(driller)
        BookingRequest.objects.create(
            external_project_key="occupied-friday",
            project_name="Occupied Site",
            capability_required="geotechnical-drilling",
            coverage_area={"county": "Travis", "state_code": "TX"},
            estimated_days=Decimal("1.00"),
            status=BookingRequest.Status.COMMITTED,
            assigned_driller=driller,
            committed_start_at=aware_datetime(2026, 4, 23),
            committed_end_at=aware_datetime(2026, 4, 24, 17),
        )

        booking = BookingRequest.objects.create(
            external_project_key="project-after-friday",
            project_name="North Site",
            capability_required="geotechnical-drilling",
            coverage_area={"county": "Travis", "state_code": "TX"},
            estimated_days=Decimal("1.00"),
            earliest_start_at=aware_datetime(2026, 4, 24),
        )
        booking = evaluate_and_commit_booking(booking)

        self.assertEqual(booking.status, BookingRequest.Status.COMMITTED)
        self.assertEqual(booking.committed_start_at.date().isoformat(), "2026-04-27")

    def test_blackout_date_pushes_next_available_start_forward(self):
        driller = DrillerProfile.objects.create(
            company_name="Sunrise Drilling",
            display_name="Crew A",
            capability_keys=["geotechnical-drilling"],
            working_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        self._add_county_coverage(driller, "Travis")
        self._create_schedule(driller)
        DrillerBlackoutDate.objects.create(
            driller=driller,
            date=aware_datetime(2026, 4, 20).date(),
            reason="Holiday",
            active=True,
        )

        booking = BookingRequest.objects.create(
            external_project_key="project-after-blackout",
            project_name="North Site",
            capability_required="geotechnical-drilling",
            coverage_area={"county": "Travis", "state_code": "TX"},
            estimated_days=Decimal("1.00"),
            earliest_start_at=aware_datetime(2026, 4, 20),
        )
        booking = evaluate_and_commit_booking(booking)

        self.assertEqual(booking.status, BookingRequest.Status.COMMITTED)
        self.assertEqual(booking.committed_start_at.date().isoformat(), "2026-04-21")

    def test_opportunities_endpoint_counts_only_enabled_workdays_in_displayed_window(self):
        driller = DrillerProfile.objects.create(
            company_name="Sunrise Drilling",
            display_name="Crew A",
            capability_keys=["geotechnical-drilling"],
            working_days=["monday", "wednesday", "friday"],
        )
        self._add_county_coverage(driller, "Travis")
        self._create_schedule(driller)

        response = self.client.post(
            "/api/network/opportunities/",
            data={
                "capability_required": "geotechnical-drilling",
                "estimated_days": "2.00",
                "earliest_start_at": aware_datetime(2026, 4, 22).isoformat(),
                "coverage_area": {"county": "Travis", "state_code": "TX"},
                "scope_facts": {
                    "bore_count": 4,
                    "bore_depth_ft": 20,
                },
            },
            content_type="application/json",
            headers={"X-Internal-Service-Secret": "test-internal-secret"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        opportunity = payload["items"][0]
        self.assertEqual(opportunity["window"]["start_at"][:10], "2026-04-22")
        self.assertEqual(opportunity["window"]["end_at"][:10], "2026-04-24")
        self.assertEqual(opportunity["window"]["required_workdays"], 2)
        self.assertEqual(opportunity["pricing"]["total_amount"], "2600.00")

    def test_blackout_inside_job_extends_displayed_window(self):
        driller = DrillerProfile.objects.create(
            company_name="Sunrise Drilling",
            display_name="Crew A",
            capability_keys=["geotechnical-drilling"],
            working_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        self._add_county_coverage(driller, "Travis")
        self._create_schedule(driller)
        DrillerBlackoutDate.objects.create(
            driller=driller,
            date=aware_datetime(2026, 4, 23).date(),
            reason="Crew PTO",
            active=True,
        )

        response = self.client.post(
            "/api/network/opportunities/",
            data={
                "capability_required": "geotechnical-drilling",
                "estimated_days": "2.00",
                "earliest_start_at": aware_datetime(2026, 4, 22).isoformat(),
                "coverage_area": {"county": "Travis", "state_code": "TX"},
                "scope_facts": {
                    "bore_count": 4,
                    "bore_depth_ft": 20,
                },
            },
            content_type="application/json",
            headers={"X-Internal-Service-Secret": "test-internal-secret"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        opportunity = payload["items"][0]
        self.assertEqual(opportunity["window"]["start_at"][:10], "2026-04-22")
        self.assertEqual(opportunity["window"]["end_at"][:10], "2026-04-24")

    def test_blackout_and_non_working_day_interactions_skip_both(self):
        driller = DrillerProfile.objects.create(
            company_name="Sunrise Drilling",
            display_name="Crew A",
            capability_keys=["geotechnical-drilling"],
            working_days=["monday", "wednesday", "friday"],
        )
        self._add_county_coverage(driller, "Travis")
        self._create_schedule(driller)
        DrillerBlackoutDate.objects.create(
            driller=driller,
            date=aware_datetime(2026, 4, 24).date(),
            reason="Friday blackout",
            active=True,
        )

        response = self.client.post(
            "/api/network/opportunities/",
            data={
                "capability_required": "geotechnical-drilling",
                "estimated_days": "2.00",
                "earliest_start_at": aware_datetime(2026, 4, 22).isoformat(),
                "coverage_area": {"county": "Travis", "state_code": "TX"},
                "scope_facts": {
                    "bore_count": 4,
                    "bore_depth_ft": 20,
                },
            },
            content_type="application/json",
            headers={"X-Internal-Service-Secret": "test-internal-secret"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        opportunity = payload["items"][0]
        self.assertEqual(opportunity["window"]["start_at"][:10], "2026-04-22")
        self.assertEqual(opportunity["window"]["end_at"][:10], "2026-04-27")

    def test_opportunities_endpoint_returns_machine_readable_exclusion_reason_when_no_working_days(self):
        driller = DrillerProfile.objects.create(
            company_name="Sunrise Drilling",
            display_name="Crew A",
            capability_keys=["geotechnical-drilling"],
            working_days=[],
        )
        self._add_county_coverage(driller, "Travis")
        self._create_schedule(driller)

        response = self.client.post(
            "/api/network/opportunities/",
            data={
                "capability_required": "geotechnical-drilling",
                "estimated_days": "1.00",
                "earliest_start_at": aware_datetime(2026, 4, 22).isoformat(),
                "coverage_area": {"county": "Travis", "state_code": "TX"},
                "scope_facts": {
                    "bore_count": 4,
                    "bore_depth_ft": 20,
                },
            },
            content_type="application/json",
            headers={"X-Internal-Service-Secret": "test-internal-secret"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["driller_debug"][0]["driller"]["display_name"], "Crew A")
        self.assertEqual(payload["driller_debug"][0]["exclusions"][0]["reason_code"], "NO_WORKING_DAYS")

    def test_opportunities_endpoint_filters_to_requested_county_coverage(self):
        central_driller = DrillerProfile.objects.create(
            company_name="Austin Drilling",
            display_name="Central Crew",
            capability_keys=["geotechnical-drilling"],
            working_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        coastal_driller = DrillerProfile.objects.create(
            company_name="Corpus Drilling",
            display_name="Coastal Crew",
            capability_keys=["geotechnical-drilling"],
            working_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        self._add_county_coverage(central_driller, "Travis")
        self._add_county_coverage(coastal_driller, "Nueces")
        self._create_schedule(central_driller)
        self._create_schedule(coastal_driller)

        response = self.client.post(
            "/api/network/opportunities/",
            data={
                "capability_required": "geotechnical-drilling",
                "estimated_days": "1.00",
                "earliest_start_at": aware_datetime(2026, 4, 22).isoformat(),
                "coverage_area": {
                    "county": "Travis County",
                    "state_code": "TX",
                },
                "scope_facts": {
                    "bore_count": 4,
                    "bore_depth_ft": 20,
                },
            },
            content_type="application/json",
            headers={"X-Internal-Service-Secret": "test-internal-secret"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["driller"]["display_name"], "Central Crew")

    def test_opportunities_endpoint_excludes_drillers_without_requested_county_coverage(self):
        driller = DrillerProfile.objects.create(
            company_name="Austin Drilling",
            display_name="Central Crew",
            capability_keys=["geotechnical-drilling"],
            working_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        self._add_county_coverage(driller, "Williamson")
        self._create_schedule(driller)

        response = self.client.post(
            "/api/network/opportunities/",
            data={
                "capability_required": "geotechnical-drilling",
                "estimated_days": "1.00",
                "earliest_start_at": aware_datetime(2026, 4, 22).isoformat(),
                "coverage_area": {
                    "county": "Travis",
                    "state_code": "TX",
                },
                "scope_facts": {
                    "bore_count": 4,
                    "bore_depth_ft": 20,
                },
            },
            content_type="application/json",
            headers={"X-Internal-Service-Secret": "test-internal-secret"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["driller_debug"][0]["exclusions"][0]["reason_code"], "COVERAGE_MISMATCH")

    def test_accepted_field_execution_no_longer_blocks_next_availability(self):
        driller = DrillerProfile.objects.create(
            company_name="Sunrise Drilling",
            display_name="Crew A",
            capability_keys=["geotechnical-drilling"],
            working_days=["monday", "tuesday", "wednesday", "thursday", "friday"],
        )
        self._add_county_coverage(driller, "Travis")
        self._create_schedule(driller)
        accepted_booking = BookingRequest.objects.create(
            external_project_key="accepted-history",
            project_name="Historic Site",
            capability_required="geotechnical-drilling",
            coverage_area={"county": "Travis", "state_code": "TX"},
            estimated_days=Decimal("1.00"),
            status=BookingRequest.Status.COMMITTED,
            assigned_driller=driller,
            committed_start_at=aware_datetime(2026, 4, 21),
            committed_end_at=aware_datetime(2026, 4, 24, 17),
        )
        FieldExecution.objects.create(
            external_project_id="accepted-history",
            booking_request=accepted_booking,
            assigned_driller=driller,
            scheduled_start_date=accepted_booking.committed_start_at.date(),
            estimated_days=Decimal("1.00"),
            status=FieldExecution.Status.ACCEPTED,
        )

        booking = BookingRequest.objects.create(
            external_project_key="new-work",
            project_name="North Site",
            capability_required="geotechnical-drilling",
            coverage_area={"county": "Travis", "state_code": "TX"},
            estimated_days=Decimal("1.00"),
            earliest_start_at=aware_datetime(2026, 4, 20),
        )
        booking = evaluate_and_commit_booking(booking)

        self.assertEqual(booking.status, BookingRequest.Status.COMMITTED)
        self.assertEqual(booking.committed_start_at.date().isoformat(), "2026-04-20")
