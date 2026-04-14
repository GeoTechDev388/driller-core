from django.db import migrations, models


DEFAULT_WORKING_DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
WORKING_DAY_INDEX_TO_CODE = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}


def migrate_window_days_to_working_days(apps, schema_editor):
    DrillerProfile = apps.get_model("network", "DrillerProfile")
    AvailabilityWindow = apps.get_model("network", "AvailabilityWindow")

    for driller in DrillerProfile.objects.all().iterator():
        weekday_indexes = sorted(
            {
                window.start_at.weekday()
                for window in AvailabilityWindow.objects.filter(driller=driller)
                if window.start_at is not None
            }
        )
        if weekday_indexes:
            driller.working_days = [
                WORKING_DAY_INDEX_TO_CODE[index]
                for index in weekday_indexes
                if index in WORKING_DAY_INDEX_TO_CODE
            ]
        else:
            driller.working_days = list(DEFAULT_WORKING_DAYS)
        driller.save(update_fields=["working_days"])


class Migration(migrations.Migration):

    dependencies = [
        ("network", "0003_drillercoverage"),
    ]

    operations = [
        migrations.AddField(
            model_name="drillerprofile",
            name="working_days",
            field=models.JSONField(blank=True, default=["monday", "tuesday", "wednesday", "thursday", "friday"]),
        ),
        migrations.RunPython(migrate_window_days_to_working_days, migrations.RunPython.noop),
        migrations.DeleteModel(
            name="AvailabilityWindow",
        ),
        migrations.DeleteModel(
            name="BlackoutDate",
        ),
    ]
