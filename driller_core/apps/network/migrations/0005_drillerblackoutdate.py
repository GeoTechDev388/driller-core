import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("network", "0004_workday_availability"),
    ]

    operations = [
        migrations.CreateModel(
            name="DrillerBlackoutDate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("date", models.DateField()),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("active", models.BooleanField(default=True)),
                (
                    "driller",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="blackout_dates",
                        to="network.drillerprofile",
                    ),
                ),
            ],
            options={
                "ordering": ["date", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="drillerblackoutdate",
            constraint=models.UniqueConstraint(fields=("driller", "date"), name="uniq_driller_blackout_date"),
        ),
    ]
