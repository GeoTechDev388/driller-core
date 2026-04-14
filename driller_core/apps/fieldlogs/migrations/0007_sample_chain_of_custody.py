import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fieldlogs", "0006_field_log_observation_details"),
    ]

    operations = [
        migrations.CreateModel(
            name="SampleChainOfCustody",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("released_by_name", models.CharField(max_length=255)),
                ("released_by_role", models.CharField(max_length=255)),
                ("released_at", models.DateTimeField()),
                ("received_by_name", models.CharField(blank=True, max_length=255)),
                ("received_by_role", models.CharField(blank=True, max_length=255)),
                ("received_at", models.DateTimeField(blank=True, null=True)),
                (
                    "transfer_method",
                    models.CharField(
                        choices=[
                            ("hand_delivery", "Hand delivery"),
                            ("courier", "Courier"),
                            ("shipped", "Shipped"),
                            ("lab_pickup", "Lab pickup"),
                            ("other", "Other"),
                        ],
                        max_length=32,
                    ),
                ),
                ("transfer_location", models.CharField(max_length=255)),
                (
                    "destination_type",
                    models.CharField(
                        choices=[
                            ("sunrise_lab", "Sunrise lab"),
                            ("outside_lab", "Outside lab"),
                            ("storage", "Storage"),
                            ("other", "Other"),
                        ],
                        max_length=32,
                    ),
                ),
                ("destination_name", models.CharField(max_length=255)),
                ("tracking_number", models.CharField(blank=True, max_length=128)),
                ("sample_condition_on_transfer", models.CharField(blank=True, max_length=255)),
                ("custody_notes", models.TextField(blank=True)),
                (
                    "drilling_input_record",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chain_of_custody",
                        to="fieldlogs.drillinginputrecord",
                    ),
                ),
            ],
            options={
                "ordering": ["-released_at", "-id"],
            },
        ),
    ]
