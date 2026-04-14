from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DrillerProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("company_name", models.CharField(max_length=255)),
                ("display_name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                ("capability_keys", models.JSONField(blank=True, default=list)),
                ("coverage_area", models.JSONField(blank=True, default=dict)),
                ("notes", models.TextField(blank=True)),
            ],
        ),
        migrations.CreateModel(
            name="AvailabilityWindow",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("start_at", models.DateTimeField()),
                ("end_at", models.DateTimeField()),
                ("is_available", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True)),
                ("driller", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="availability_windows", to="network.drillerprofile")),
            ],
        ),
        migrations.CreateModel(
            name="BlackoutDate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("start_at", models.DateTimeField()),
                ("end_at", models.DateTimeField()),
                ("reason", models.CharField(blank=True, max_length=255)),
                ("driller", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="blackout_dates", to="network.drillerprofile")),
            ],
        ),
        migrations.CreateModel(
            name="BookingRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("external_project_key", models.CharField(max_length=128, unique=True)),
                ("project_number", models.CharField(blank=True, max_length=64)),
                ("proposal_number", models.CharField(blank=True, max_length=64)),
                ("project_name", models.CharField(max_length=255)),
                ("client_name", models.CharField(blank=True, max_length=255)),
                ("capability_required", models.CharField(blank=True, max_length=128)),
                ("coverage_area", models.JSONField(blank=True, default=dict)),
                ("estimated_days", models.DecimalField(decimal_places=2, max_digits=6)),
                ("earliest_start_at", models.DateTimeField(blank=True, null=True)),
                ("status", models.CharField(choices=[("requested", "Requested"), ("committed", "Committed"), ("blocked", "Blocked"), ("completed", "Completed")], default="requested", max_length=16)),
                ("committed_start_at", models.DateTimeField(blank=True, null=True)),
                ("committed_end_at", models.DateTimeField(blank=True, null=True)),
                ("blocking_reason", models.TextField(blank=True)),
                ("request_payload", models.JSONField(blank=True, default=dict)),
                ("response_payload", models.JSONField(blank=True, default=dict)),
                ("assigned_driller", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="booking_requests", to="network.drillerprofile")),
            ],
        ),
    ]
