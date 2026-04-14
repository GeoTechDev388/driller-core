from __future__ import annotations

from django.core.management.base import BaseCommand

from driller_core.apps.accounts.models import UserAccount
from driller_core.apps.fieldlogs.models import DrillerUser
from driller_core.apps.network.models import (
    DrillerCoverage,
    DrillerFeeLineItem,
    DrillerFeeSchedule,
    DrillerProfile,
)


class Command(BaseCommand):
    help = "Seed Day 1 driller-core demo resources and availability."

    def handle(self, *args, **options):
        driller_a, _ = DrillerProfile.objects.get_or_create(
            display_name="Sunrise Field Crew Alpha",
            defaults={
                "company_name": "Sunrise Field Services",
                "contact_name": "Alex Alpha",
                "email": "alpha@driller-demo.local",
                "phone": "512-555-0101",
                "capability_keys": ["geotechnical-drilling"],
                "coverage_area": {"base_city": "Austin"},
                "notes": "Primary Day 1 demo drilling crew.",
            },
        )
        driller_b, _ = DrillerProfile.objects.get_or_create(
            display_name="Sunrise Field Crew Bravo",
            defaults={
                "company_name": "Sunrise Field Services",
                "contact_name": "Bailey Bravo",
                "email": "bravo@driller-demo.local",
                "phone": "512-555-0102",
                "capability_keys": ["geotechnical-drilling"],
                "coverage_area": {"base_city": "San Marcos"},
                "notes": "Secondary Day 1 demo drilling crew.",
            },
        )

        for county_name in ("Travis", "Williamson"):
            coverage, _created = DrillerCoverage.objects.get_or_create(
                driller=driller_a,
                county_name=county_name,
                state_code="TX",
                defaults={"active": True},
            )
            if not coverage.active:
                coverage.active = True
                coverage.save(update_fields=["active", "updated_at"])
        for county_name in ("Hays", "Comal"):
            coverage, _created = DrillerCoverage.objects.get_or_create(
                driller=driller_b,
                county_name=county_name,
                state_code="TX",
                defaults={"active": True},
            )
            if not coverage.active:
                coverage.active = True
                coverage.save(update_fields=["active", "updated_at"])
        driller_a.working_days = ["monday", "tuesday", "wednesday", "thursday", "friday"]
        driller_b.working_days = ["monday", "wednesday", "friday"]
        driller_a.save(update_fields=["working_days", "updated_at"])
        driller_b.save(update_fields=["working_days", "updated_at"])

        alpha_schedule, _ = DrillerFeeSchedule.objects.get_or_create(
            driller=driller_a,
            name="Day 1 Standard Pricing",
            defaults={
                "currency": "usd",
                "is_active": True,
                "notes": "Seeded pricing for Day 1 proposal estimating.",
            },
        )
        bravo_schedule, _ = DrillerFeeSchedule.objects.get_or_create(
            driller=driller_b,
            name="Day 1 Standard Pricing",
            defaults={
                "currency": "usd",
                "is_active": True,
                "notes": "Seeded pricing for Day 1 proposal estimating.",
            },
        )

        seeded_line_items = {
            alpha_schedule: [
                (DrillerFeeLineItem.LineItemType.MOBILIZATION, "Mobilization", "2400.00", {}),
                (DrillerFeeLineItem.LineItemType.PER_BORE, "Per bore setup", "325.00", {}),
                (DrillerFeeLineItem.LineItemType.PER_FOOT, "Drilling footage", "24.00", {}),
                (DrillerFeeLineItem.LineItemType.CASING_PER_BORE, "Casing allowance", "110.00", {}),
                (DrillerFeeLineItem.LineItemType.ROCK_DRILLING_PER_BORE, "Rock drilling premium", "220.00", {}),
                (DrillerFeeLineItem.LineItemType.MINIMUM_CHARGE, "Minimum charge", "6500.00", {}),
            ],
            bravo_schedule: [
                (DrillerFeeLineItem.LineItemType.MOBILIZATION, "Mobilization", "2100.00", {}),
                (DrillerFeeLineItem.LineItemType.PER_BORE, "Per bore setup", "360.00", {}),
                (DrillerFeeLineItem.LineItemType.PER_FOOT, "Drilling footage", "22.50", {}),
                (DrillerFeeLineItem.LineItemType.STANDBY_DAY, "Standby day", "850.00", {}),
                (DrillerFeeLineItem.LineItemType.TRAVEL_ZONE_ADDER, "Outer travel zone adder", "500.00", {"travel_zone": "outer"}),
                (DrillerFeeLineItem.LineItemType.MINIMUM_CHARGE, "Minimum charge", "6200.00", {}),
            ],
        }

        for schedule, line_items in seeded_line_items.items():
            for sort_order, (line_item_type, label, amount, metadata) in enumerate(line_items, start=10):
                DrillerFeeLineItem.objects.get_or_create(
                    fee_schedule=schedule,
                    line_item_type=line_item_type,
                    label=label,
                    defaults={
                        "amount": amount,
                        "metadata": metadata,
                        "sort_order": sort_order,
                    },
                )
        self._ensure_driller_user(driller_a, email="alpha@driller-demo.local", password="AlphaPass123!")
        self._ensure_driller_user(driller_b, email="bravo@driller-demo.local", password="BravoPass123!")

        self.stdout.write(self.style.SUCCESS("Seeded driller-core Day 1 demo resources, workday availability, fee schedules, and driller portal users."))
        self.stdout.write("Driller login: alpha@driller-demo.local / AlphaPass123!")
        self.stdout.write("Driller login: bravo@driller-demo.local / BravoPass123!")

    def _ensure_driller_user(self, driller: DrillerProfile, *, email: str, password: str) -> None:
        user, created = UserAccount.objects.get_or_create(
            email=email,
            defaults={"is_active": True},
        )
        if created or not user.check_password(password):
            user.set_password(password)
            user.is_active = True
            user.save()
        driller_user, _ = DrillerUser.objects.get_or_create(
            driller=driller,
            user_account=user,
            defaults={"is_active": True, "portal_access_enabled": True},
        )
        if not driller_user.is_active or not driller_user.portal_access_enabled:
            driller_user.is_active = True
            driller_user.portal_access_enabled = True
            driller_user.save(update_fields=["is_active", "portal_access_enabled", "updated_at"])
