import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("network", "0002_drillerprofile_contact_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="DrillerCoverage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("county_name", models.CharField(max_length=128)),
                ("state_code", models.CharField(default="TX", max_length=8)),
                ("active", models.BooleanField(default=True)),
                (
                    "driller",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="county_coverages",
                        to="network.drillerprofile",
                    ),
                ),
            ],
            options={
                "ordering": ["driller__company_name", "driller__display_name", "state_code", "county_name", "id"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("driller", "county_name", "state_code"),
                        name="uniq_driller_county_coverage",
                    )
                ],
            },
        ),
    ]
