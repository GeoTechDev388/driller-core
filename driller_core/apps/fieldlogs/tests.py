from __future__ import annotations

import shutil
import tempfile
from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from driller_core.apps.accounts.models import UserAccount
from driller_core.apps.network.models import (
    BookingRequest,
    DrillerBlackoutDate,
    DrillerCoverage,
    DrillerFeeLineItem,
    DrillerFeeSchedule,
    DrillerProfile,
)

from .models import DrillerUser, DrillingInputRecord, FieldExecution
from .pdf import build_field_log_pdf_context
from .services import ensure_field_execution_for_booking


TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="driller-core-fieldlogs-tests-")


def tearDownModule():
    shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)


@override_settings(
    MEDIA_ROOT=TEST_MEDIA_ROOT,
    DRILLER_CORE_INTERNAL_SHARED_SECRET="test-internal-secret",
    DRILLER_ACCESS_TOKEN_SALT="driller-core.test-token",
)
class FieldLogLifecycleTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.driller = DrillerProfile.objects.create(
            company_name="Sunrise Field Services",
            display_name="Crew Alpha",
            contact_name="Alex Alpha",
            email="alpha@driller.test",
            phone="512-555-0101",
            capability_keys=["geotechnical-drilling"],
        )
        user = UserAccount.objects.create_user(email="alpha@driller.test", password="AlphaPass123!", is_active=True)
        DrillerUser.objects.create(driller=self.driller, user_account=user, is_active=True)
        booking = BookingRequest.objects.create(
            external_project_key="project-uuid-123",
            project_number="PRJ-2026-0001",
            proposal_number="SUN-2026-0001",
            project_name="North Loop Site",
            client_name="Acme Development",
            estimated_days=Decimal("1.00"),
            status=BookingRequest.Status.COMMITTED,
            assigned_driller=self.driller,
        )
        self.execution = ensure_field_execution_for_booking(booking)

    def _login(self) -> str:
        response = self.client.post(
            "/api/driller-portal/auth/login/",
            data={"email": "alpha@driller.test", "password": "AlphaPass123!"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["token"]

    def _start_record(self) -> tuple[str, int]:
        token = self._login()
        response = self.client.post(
            "/api/driller-portal/drilling-input/start/",
            data={"field_execution_id": str(self.execution.shared_uuid)},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 200)
        return token, response.json()["execution"]["latest_record"]["id"]

    def _set_planned_boring_scope(self):
        self.execution.planned_borings = [
            {
                "name": "B-1",
                "sequence_number": 1,
                "planned_depth": "15.00",
                "category": "structure",
            }
        ]
        self.execution.save(update_fields=["planned_borings", "updated_at"])

    def _boring_payload(self, interval_payload: dict) -> dict:
        return {
            "name": "B-1",
            "planned_depth": "15.00",
            "actual_depth": "2.00",
            "status": "active",
            "drilling_method": "hollow_stem_auger",
            "intervals": [interval_payload],
            "groundwater_observations": [],
        }

    def _interval_payload(self, **overrides) -> dict:
        payload = {
            "sequence_number": 1,
            "state": "taken",
            "planned_from_depth": "0.50",
            "planned_to_depth": "2.00",
            "actual_from_depth": "0.50",
            "actual_to_depth": "2.00",
        }
        payload.update(overrides)
        return payload

    def test_driller_me_endpoint_returns_bootstrap_payload(self):
        token = self._login()

        response = self.client.get(
            "/api/driller-portal/auth/me/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user"]["email"], "alpha@driller.test")
        self.assertTrue(payload["driller_user"]["portal_access_enabled"])
        self.assertEqual(len(payload["assigned_jobs"]), 1)

    def test_field_execution_payload_includes_backend_form_options(self):
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Backend-owned option contract coverage.",
                "borings": [
                    self._boring_payload(
                        self._interval_payload(
                            observation={
                                "visual_classification": "CL",
                                "moisture_condition": "moist",
                                "description": "Lean clay",
                                "recovery_length": "1.50",
                            },
                            spt_result={
                                "blows_1": 4,
                                "blows_2": 5,
                                "blows_3": 6,
                            },
                        )
                    )
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        options = response.json()["execution"]["field_log_options"]
        self.assertTrue(any(item["value"] == "hollow_stem_auger" for item in options["drilling_methods"]))
        self.assertTrue(any(item["value"] == "CL" for item in options["soil_classifications"]))
        self.assertTrue(any(item["value"] == "moist" for item in options["moisture_conditions"]))

    def test_scope_boring_is_preserved_when_omitted_from_update_payload(self):
        self._set_planned_boring_scope()
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={"notes": "No boring changes yet.", "borings": []},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        borings = response.json()["execution"]["latest_record"]["borings"]
        self.assertEqual(len(borings), 1)
        self.assertTrue(borings[0]["is_scope_boring"])
        self.assertFalse(borings[0]["can_remove"])
        self.assertEqual(borings[0]["name"], "B-1")

    def test_extra_boring_can_be_removed_by_omission(self):
        token, record_id = self._start_record()

        create_response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Add extra boring.",
                "borings": [
                    {
                        "name": "B-Extra",
                        "planned_depth": "8.00",
                        "actual_depth": "",
                        "drilling_method": "hollow_stem_auger",
                        "intervals": [],
                        "groundwater_observations": [],
                    }
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(create_response.status_code, 200)
        borings = create_response.json()["execution"]["latest_record"]["borings"]
        self.assertEqual(len(borings), 1)
        self.assertFalse(borings[0]["is_scope_boring"])
        self.assertTrue(borings[0]["can_remove"])

        remove_response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={"notes": "Removed extra boring.", "borings": []},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(remove_response.json()["execution"]["latest_record"]["borings"], [])

    def test_boring_status_is_derived_from_completion_facts(self):
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Outcome derivation coverage.",
                "borings": [
                    {
                        "name": "B-1",
                        "planned_depth": "15.00",
                        "drilling_method": "hollow_stem_auger",
                        "intervals": [],
                        "groundwater_observations": [],
                        "completion": {
                            "completed_at": "2026-04-10T12:00:00Z",
                            "final_depth": "0.00",
                            "termination_reason": "utility_conflict",
                            "notes": "Stopped before drilling due to marked utilities.",
                        },
                    }
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        boring = response.json()["execution"]["latest_record"]["borings"][0]
        self.assertEqual(boring["status"], "abandoned")

    def test_driller_coverage_endpoints_support_county_crud(self):
        token = self._login()

        initial_response = self.client.get(
            "/api/driller-portal/coverage/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(initial_response.status_code, 200)
        self.assertEqual(initial_response.json()["items"], [])

        create_response = self.client.post(
            "/api/driller-portal/coverage/",
            data={"county_name": "hidalgo county", "state_code": "tx"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(create_response.status_code, 201)
        item = create_response.json()["item"]
        self.assertEqual(item["county_name"], "Hidalgo")
        self.assertEqual(item["state_code"], "TX")

        duplicate_response = self.client.post(
            "/api/driller-portal/coverage/",
            data={"county_name": "Hidalgo", "state_code": "TX"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(duplicate_response.status_code, 400)

        list_response = self.client.get(
            "/api/driller-portal/coverage/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()["items"]), 1)

        delete_response = self.client.delete(
            f"/api/driller-portal/coverage/{item['id']}/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["removed_id"], item["id"])

        final_response = self.client.get(
            "/api/driller-portal/coverage/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(final_response.status_code, 200)
        self.assertEqual(final_response.json()["items"], [])

    def test_driller_settings_returns_texas_geography_options(self):
        token = self._login()

        response = self.client.get(
            "/api/driller-portal/settings/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["coverage"]["default_state_code"], "TX")
        texas = next(
            item for item in payload["coverage"]["supported_states"] if item["state_code"] == "TX"
        )
        self.assertEqual(texas["name"], "Texas")
        self.assertIn("Travis", texas["counties"])
        self.assertIn("Harris", texas["counties"])
        self.assertGreaterEqual(texas["county_count"], 200)

    def test_driller_settings_bulk_coverage_update_drives_live_matching_truth(self):
        token = self._login()

        schedule = DrillerFeeSchedule.objects.create(driller=self.driller, name="Standard", currency="usd")
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
            amount=Decimal("250.00"),
            sort_order=20,
        )
        DrillerFeeLineItem.objects.create(
            fee_schedule=schedule,
            line_item_type=DrillerFeeLineItem.LineItemType.MINIMUM_CHARGE,
            label="Minimum charge",
            amount=Decimal("1500.00"),
            sort_order=30,
        )
        self.driller.working_days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
        self.driller.save(update_fields=["working_days", "updated_at"])

        save_response = self.client.put(
            "/api/driller-portal/settings/coverage/",
            data={
                "state_code": "TX",
                "county_names": ["Travis", "Williamson"],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(
            save_response.json()["coverage"]["selected_by_state"]["TX"],
            ["Travis", "Williamson"],
        )
        self.assertEqual(
            list(
                DrillerCoverage.objects.filter(driller=self.driller, active=True)
                .order_by("county_name")
                .values_list("county_name", flat=True)
            ),
            ["Travis", "Williamson"],
        )

        matching_response = self.client.post(
            "/api/network/opportunities/",
            data={
                "capability_required": "geotechnical-drilling",
                "estimated_days": "1.00",
                "coverage_area": {"county": "Travis", "state_code": "TX"},
                "scope_facts": {"bore_count": 2},
            },
            content_type="application/json",
            HTTP_X_INTERNAL_SERVICE_SECRET="test-internal-secret",
        )
        self.assertEqual(matching_response.status_code, 200)
        self.assertEqual(len(matching_response.json()["items"]), 1)

        replace_response = self.client.put(
            "/api/driller-portal/settings/coverage/",
            data={
                "state_code": "TX",
                "county_names": ["Hidalgo"],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(replace_response.status_code, 200)
        self.assertEqual(
            list(
                DrillerCoverage.objects.filter(driller=self.driller, active=True)
                .order_by("county_name")
                .values_list("county_name", flat=True)
            ),
            ["Hidalgo"],
        )

        non_matching_response = self.client.post(
            "/api/network/opportunities/",
            data={
                "capability_required": "geotechnical-drilling",
                "estimated_days": "1.00",
                "coverage_area": {"county": "Travis", "state_code": "TX"},
                "scope_facts": {"bore_count": 2},
            },
            content_type="application/json",
            HTTP_X_INTERNAL_SERVICE_SECRET="test-internal-secret",
        )
        self.assertEqual(non_matching_response.status_code, 200)
        self.assertEqual(non_matching_response.json()["items"], [])

    def test_driller_settings_availability_update_replaces_working_days(self):
        token = self._login()

        response = self.client.put(
            "/api/driller-portal/settings/availability/",
            data={
                "working_days": ["monday", "wednesday", "friday"],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["availability"]
        self.assertEqual(payload["model"], "workday_interim_v1")
        self.assertEqual(payload["working_days"], ["monday", "wednesday", "friday"])
        self.assertEqual(payload["summary"]["enabled_day_count"], 3)
        self.assertEqual(payload["summary"]["blackout_count"], 0)
        self.driller.refresh_from_db()
        self.assertEqual(self.driller.working_days, ["monday", "wednesday", "friday"])

    def test_driller_blackout_endpoints_add_list_and_remove_dates(self):
        token = self._login()

        create_response = self.client.post(
            "/api/driller-portal/blackouts/",
            data={
                "date": "2026-04-22",
                "reason": "Crew vacation",
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["item"]["date"], "2026-04-22")
        self.assertEqual(create_response.json()["availability"]["summary"]["blackout_count"], 1)

        list_response = self.client.get(
            "/api/driller-portal/blackouts/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()["items"]), 1)

        blackout_id = list_response.json()["items"][0]["id"]
        delete_response = self.client.delete(
            f"/api/driller-portal/blackouts/{blackout_id}/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["availability"]["summary"]["blackout_count"], 0)
        self.assertFalse(DrillerBlackoutDate.objects.get(pk=blackout_id).active)

    def test_driller_settings_pricing_update_replaces_active_fee_schedule_lines(self):
        token = self._login()

        response = self.client.put(
            "/api/driller-portal/settings/pricing/",
            data={
                "name": "Crew Alpha Standard",
                "currency": "usd",
                "notes": "Portal-managed pricing for GeoPro.",
                "line_items": [
                    {"line_item_type": "mobilization", "amount": "2400.00"},
                    {"line_item_type": "per_bore", "amount": "325.00"},
                    {"line_item_type": "per_foot", "amount": "24.00"},
                    {
                        "line_item_type": "travel_zone_adder",
                        "amount": "550.00",
                        "metadata": {"travel_zone": "outer"},
                    },
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()["pricing"]
        self.assertEqual(payload["active_fee_schedule"]["name"], "Crew Alpha Standard")
        self.assertEqual(len(payload["line_items"]), 4)

        schedule = DrillerFeeSchedule.objects.get(driller=self.driller, is_active=True)
        self.assertEqual(schedule.notes, "Portal-managed pricing for GeoPro.")
        self.assertEqual(schedule.line_items.count(), 4)
        travel_zone_item = schedule.line_items.get(
            line_item_type=DrillerFeeLineItem.LineItemType.TRAVEL_ZONE_ADDER
        )
        self.assertEqual(travel_zone_item.metadata["travel_zone"], "outer")

    def test_login_denies_when_portal_access_disabled(self):
        driller_user = DrillerUser.objects.get(user_account__email="alpha@driller.test")
        driller_user.portal_access_enabled = False
        driller_user.save(update_fields=["portal_access_enabled", "updated_at"])

        response = self.client.post(
            "/api/driller-portal/auth/login/",
            data={"email": "alpha@driller.test", "password": "AlphaPass123!"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "portal_access_disabled")

    def test_sample_interval_defaults_to_spt_when_sample_type_is_omitted(self):
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Default sample type coverage.",
                "borings": [
                    self._boring_payload(
                        self._interval_payload(
                            observation={
                                "visual_classification": "CL",
                                "moisture_condition": "moist",
                                "description": "Lean clay",
                                "recovery_length": "1.50",
                            },
                            spt_result={
                                "blows_1": 4,
                                "blows_2": 5,
                                "blows_3": 6,
                            },
                        )
                    )
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        interval = response.json()["execution"]["latest_record"]["borings"][0]["intervals"][0]
        self.assertEqual(interval["sample_type"], "spt")
        self.assertIsNone(interval["pocket_penetrometer"])
        self.assertIsNone(interval["rqd_percent"])
        self.assertEqual(interval["spt_result"]["blows_3"], 6)

    def test_spt_validation_requires_blow_counts(self):
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "SPT validation coverage.",
                "borings": [
                    self._boring_payload(
                        self._interval_payload(
                            sample_type="spt",
                            observation={
                                "visual_classification": "SM",
                                "moisture_condition": "moist",
                                "description": "Silty sand",
                                "recovery_length": "1.10",
                            },
                        )
                    )
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Please fix the highlighted fields.")
        self.assertEqual(
            response.json()["field_errors"]["borings.0.intervals.0.spt_result.blows_1"],
            "0-6 in blow count is required.",
        )

    def test_spt_validation_returns_field_specific_missing_increment_message(self):
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "SPT partial entry validation coverage.",
                "borings": [
                    self._boring_payload(
                        self._interval_payload(
                            sample_type="spt",
                            observation={
                                "visual_classification": "SM",
                                "moisture_condition": "moist",
                                "description": "Silty sand",
                                "recovery_length": "1.10",
                            },
                            spt_result={
                                "blows_1": 4,
                                "blows_3": 9,
                            },
                        )
                    )
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["field_errors"]["borings.0.intervals.0.spt_result.blows_2"],
            "6-12 in blow count is required.",
        )

    def test_spt_zero_blow_counts_are_accepted_when_all_increments_are_present(self):
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "SPT zero-count coverage.",
                "borings": [
                    self._boring_payload(
                        self._interval_payload(
                            sample_type="spt",
                            observation={
                                "visual_classification": "SM",
                                "moisture_condition": "moist",
                                "description": "Loose silty sand",
                                "recovery_length": "1.10",
                            },
                            spt_result={
                                "blows_1": 0,
                                "blows_2": 0,
                                "blows_3": 0,
                            },
                        )
                    )
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        interval = response.json()["execution"]["latest_record"]["borings"][0]["intervals"][0]
        self.assertEqual(interval["spt_result"]["blows_1"], 0)
        self.assertEqual(interval["spt_result"]["blows_2"], 0)
        self.assertEqual(interval["spt_result"]["blows_3"], 0)

    def test_shelby_validation_requires_pocket_penetrometer(self):
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Shelby validation coverage.",
                "borings": [
                    self._boring_payload(
                        self._interval_payload(
                            sample_type="shelby",
                            observation={
                                "visual_classification": "CL",
                                "moisture_condition": "moist",
                                "description": "Shelby tube sample",
                                "recovery_length": "1.40",
                            },
                        )
                    )
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Please fix the highlighted fields.")
        self.assertEqual(
            response.json()["field_errors"]["borings.0.intervals.0.pocket_penetrometer_middle"],
            "At least one pocket penetrometer reading is required.",
        )

    def test_invalid_datetime_returns_field_level_error(self):
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Datetime validation coverage.",
                "borings": [
                    {
                        **self._boring_payload(
                            self._interval_payload(
                                sample_type="grab",
                                state="taken",
                            )
                        ),
                        "groundwater_observations": [
                            {
                                "observation_type": "encountered",
                                "depth": "4.00",
                                "observed_at": "not-a-date",
                                "note": "Bad test value",
                            }
                        ],
                    }
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Please fix the highlighted fields.")
        self.assertEqual(
            response.json()["field_errors"]["borings.0.groundwater_observations.0.observed_at"],
            "Invalid date selected.",
        )

    def test_field_log_context_carries_typed_sample_details_and_provisional_labels(self):
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Typed field-log artifact coverage.",
                "borings": [
                    {
                        "name": "B-1",
                        "planned_depth": "20.00",
                        "actual_depth": "12.00",
                        "status": "active",
                        "drilling_method": "hollow_stem_auger",
                        "intervals": [
                            {
                                "sequence_number": 1,
                                "sample_type": "shelby",
                                "state": "taken",
                                "planned_from_depth": "0.50",
                                "planned_to_depth": "2.00",
                                "actual_from_depth": "0.50",
                                "actual_to_depth": "2.00",
                                "pocket_penetrometer_top": "1.10",
                                "pocket_penetrometer_middle": "1.40",
                                "pocket_penetrometer_bottom": "1.20",
                                "observation": {
                                    "visual_classification": "CL",
                                    "moisture_condition": "moist",
                                    "description": "Brown lean clay tube sample.",
                                    "recovery_length": "1.50",
                                    "recovery_percent": "92.00",
                                    "sample_condition": "intact",
                                },
                            },
                            {
                                "sequence_number": 2,
                                "sample_type": "coring",
                                "state": "taken",
                                "planned_from_depth": "2.00",
                                "planned_to_depth": "7.00",
                                "actual_from_depth": "2.00",
                                "actual_to_depth": "7.00",
                                "rqd_percent": "63.00",
                                "observation": {
                                    "description": "Field core run through fractured limestone.",
                                    "recovery_length": "5.00",
                                    "recovery_percent": "83.00",
                                    "core_run_length": "6.00",
                                    "rock_core_classification": "Weathered limestone",
                                    "rock_type_name": "Edwards limestone",
                                    "rock_notes": "Fractured seams with clay infill.",
                                },
                            },
                        ],
                        "groundwater_observations": [],
                    }
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        record = DrillingInputRecord.objects.get(pk=record_id)
        context = build_field_log_pdf_context(record)
        self.assertIn("not the final boring log", context["boundary_note"].lower())
        shelby_interval = context["borings"][0]["intervals"][0]
        self.assertEqual(shelby_interval["sample_type"], "shelby")
        self.assertEqual(shelby_interval["pocket_penetrometer_middle"], "1.40")
        self.assertEqual(shelby_interval["observation"]["sample_condition"], "intact")
        coring_interval = context["borings"][0]["intervals"][1]
        self.assertEqual(coring_interval["sample_type"], "coring")
        self.assertEqual(coring_interval["rqd_percent"], "63.00")
        self.assertEqual(coring_interval["observation"]["core_run_length"], "6.00")
        self.assertEqual(coring_interval["observation"]["rock_type_name"], "Edwards limestone")

    def test_coring_validation_requires_rqd(self):
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Coring validation coverage.",
                "borings": [
                    self._boring_payload(
                        self._interval_payload(
                            sample_type="coring",
                            observation={
                                "description": "Sound limestone core",
                                "recovery_length": "1.50",
                            },
                        )
                    )
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Please fix the highlighted fields.")
        self.assertEqual(
            response.json()["field_errors"]["borings.0.intervals.0.rqd_percent"],
            "RQD is required for coring samples.",
        )

    def test_grab_sample_allows_minimal_non_spt_payload(self):
        token, record_id = self._start_record()

        response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Grab sample coverage.",
                "borings": [
                    self._boring_payload(
                        self._interval_payload(
                            sample_type="grab",
                            operator_notes="Surface bag sample near boring stake.",
                        )
                    )
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 200)
        interval = response.json()["execution"]["latest_record"]["borings"][0]["intervals"][0]
        self.assertEqual(interval["sample_type"], "grab")
        self.assertIsNone(interval["spt_result"])
        self.assertIsNone(interval["pocket_penetrometer"])
        self.assertIsNone(interval["rqd_percent"])

    def test_sample_type_update_clears_stale_spt_data(self):
        token, record_id = self._start_record()

        initial_response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Initial SPT sample.",
                "borings": [
                    self._boring_payload(
                        self._interval_payload(
                            sample_type="spt",
                            observation={
                                "visual_classification": "SM",
                                "moisture_condition": "moist",
                                "description": "SPT interval",
                                "recovery_length": "1.20",
                            },
                            spt_result={
                                "blows_1": 3,
                                "blows_2": 4,
                                "blows_3": 5,
                            },
                        )
                    )
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(initial_response.status_code, 200)

        update_response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Converted to Shelby sample.",
                "borings": [
                    self._boring_payload(
                        self._interval_payload(
                            sample_type="shelby",
                            observation={
                                "visual_classification": "CL",
                                "moisture_condition": "moist",
                                "description": "Shelby tube interval",
                                "recovery_length": "1.30",
                            },
                            pocket_penetrometer="1.75",
                        )
                    )
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(update_response.status_code, 200)
        interval = update_response.json()["execution"]["latest_record"]["borings"][0]["intervals"][0]
        self.assertEqual(interval["sample_type"], "shelby")
        self.assertEqual(interval["pocket_penetrometer"], "1.75")
        self.assertIsNone(interval["spt_result"])
        self.assertIsNone(interval["rqd_percent"])

    @patch("driller_core.apps.fieldlogs.pdf.render_pdf_from_html", return_value=b"%PDF-1.4 field-log")
    def test_employee_completion_can_finish_draft_without_separate_submit_step(self, _mock_render_pdf):
        token, record_id = self._start_record()

        update_response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Employee completion from draft.",
                "borings": [
                    {
                        "name": "B-1",
                        "planned_depth": "10.00",
                        "actual_depth": "10.00",
                        "status": "completed",
                        "drilling_method": "hollow_stem_auger",
                        "intervals": [
                            {
                                "sequence_number": 1,
                                "sample_type": "spt",
                                "state": "taken",
                                "planned_from_depth": "0.50",
                                "planned_to_depth": "2.00",
                                "actual_from_depth": "0.50",
                                "actual_to_depth": "2.00",
                                "observation": {
                                    "visual_classification": "CL",
                                    "moisture_condition": "moist",
                                    "description": "Lean clay draft sample.",
                                    "recovery_length": "1.50",
                                },
                                "spt_result": {
                                    "blows_1": 4,
                                    "blows_2": 5,
                                    "blows_3": 6,
                                },
                            }
                        ],
                        "groundwater_observations": [],
                        "completion": {
                            "completed_at": "2026-04-10T12:30:00Z",
                            "final_depth": "10.00",
                            "termination_reason": "reached_planned_depth",
                        },
                    }
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.json()["execution"]["latest_record"]["status"], "draft")

        complete_response = self.client.post(
            f"/api/employee-portal/drilling-input/{record_id}/complete/",
            data={"actor_name": "Parker PM", "actor_email": "pm@sunrise.test"},
            content_type="application/json",
            HTTP_X_INTERNAL_SERVICE_SECRET="test-internal-secret",
        )
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(complete_response.json()["execution"]["accepted_record"]["status"], "accepted")

    @patch("driller_core.apps.fieldlogs.pdf.render_pdf_from_html", return_value=b"%PDF-1.4 field-log")
    def test_driller_lifecycle_and_internal_accepted_payload(self, _mock_render_pdf):
        token = self._login()

        dashboard_response = self.client.get(
            "/api/driller-portal/dashboard/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(len(dashboard_response.json()["assigned_jobs"]), 1)

        start_response = self.client.post(
            "/api/driller-portal/drilling-input/start/",
            data={"field_execution_id": str(self.execution.shared_uuid)},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(start_response.status_code, 200)
        record_id = start_response.json()["execution"]["latest_record"]["id"]

        update_response = self.client.patch(
            f"/api/driller-portal/drilling-input/{record_id}/",
            data={
                "notes": "Rig access confirmed.",
                "borings": [
                    {
                        "name": "B-1",
                        "planned_depth": "15.00",
                        "actual_depth": "15.00",
                        "status": "completed",
                        "drilling_method": "hollow_stem_auger",
                        "intervals": [
                            {
                                "sequence_number": 1,
                                "sample_type": "spt",
                                "state": "taken",
                                "planned_from_depth": "0.50",
                                "planned_to_depth": "2.00",
                                "actual_from_depth": "0.50",
                                "actual_to_depth": "2.00",
                                "observation": {
                                    "visual_classification": "CL",
                                    "moisture_condition": "moist",
                                    "color": "Brown",
                                    "description": "Brown lean clay.",
                                    "recovery_length": "1.50",
                                },
                                "spt_result": {
                                    "blows_1": 4,
                                    "blows_2": 5,
                                    "blows_3": 6,
                                },
                            }
                        ],
                        "groundwater_observations": [],
                        "completion": {
                            "completed_at": "2026-04-10T15:30:00Z",
                            "final_depth": "15.00",
                            "termination_reason": "reached_planned_depth",
                        },
                    }
                ],
            },
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(update_response.status_code, 200)

        submit_response = self.client.post(
            f"/api/driller-portal/drilling-input/{record_id}/submit/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(submit_response.status_code, 200)
        self.assertEqual(submit_response.json()["execution"]["latest_record"]["status"], "under_review")

        employee_update_response = self.client.patch(
            f"/api/employee-portal/drilling-input/{record_id}/",
            data={
                "notes": "Employee updated the submitted field log before completion.",
                "borings": submit_response.json()["execution"]["latest_record"]["borings"],
            },
            content_type="application/json",
            HTTP_X_INTERNAL_SERVICE_SECRET="test-internal-secret",
        )
        self.assertEqual(employee_update_response.status_code, 200)
        self.assertEqual(employee_update_response.json()["execution"]["latest_record"]["status"], "under_review")

        complete_response = self.client.post(
            f"/api/employee-portal/drilling-input/{record_id}/complete/",
            data={"actor_name": "Parker PM", "actor_email": "pm@sunrise.test"},
            content_type="application/json",
            HTTP_X_INTERNAL_SERVICE_SECRET="test-internal-secret",
        )
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(complete_response.json()["execution"]["accepted_record"]["status"], "accepted")

        accepted_response = self.client.get(
            "/api/internal/drilling-input/project-uuid-123/",
            HTTP_X_INTERNAL_SERVICE_SECRET="test-internal-secret",
        )
        self.assertEqual(accepted_response.status_code, 200)
        payload = accepted_response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["schema_version"], "field-log-export-v1")
        self.assertEqual(payload["export_type"], "accepted_field_logs")
        self.assertEqual(payload["items"][0]["borings"][0]["name"], "B-1")
        self.assertEqual(payload["accepted_field_logs"][0]["pdf"]["artifact_type"], "field_log_pdf_snapshot")
        self.assertEqual(payload["accepted_field_logs"][0]["pdf"]["display_name"], "PRJ-2026-0001 Field Log.pdf")
        self.assertEqual(payload["items"][0]["borings"][0]["intervals"][0]["sample_type"], "spt")
        self.assertEqual(payload["items"][0]["borings"][0]["intervals"][0]["spt_result"]["n_value"], 11)
        self.assertEqual(
            payload["items"][0]["borings"][0]["intervals"][0]["observation"]["provisional_field_classification"],
            "CL",
        )
        self.assertTrue(bool(payload["items"][0]["pdf"]["fingerprint"]))

        artifact_response = self.client.get(
            f"/api/driller-portal/drilling-input/{record_id}/artifact/",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(artifact_response.status_code, 200)
        self.assertEqual(artifact_response["Content-Type"], "application/pdf")
        self.assertIn("Field Log.pdf", artifact_response["Content-Disposition"])

        self.execution.refresh_from_db()
        self.assertEqual(self.execution.status, FieldExecution.Status.ACCEPTED)
