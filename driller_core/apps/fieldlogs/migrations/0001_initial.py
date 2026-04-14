from decimal import Decimal
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.core.validators
import driller_core.apps.fieldlogs.models
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("network", "0002_drillerprofile_contact_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="Boring",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=64)),
                ("total_depth", models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
            ],
            options={
                "ordering": ["name", "id"],
            },
        ),
        migrations.CreateModel(
            name="DrillingInputPDF",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("file", models.FileField(blank=True, upload_to=driller_core.apps.fieldlogs.models.drilling_input_pdf_upload_to)),
                ("generated_at", models.DateTimeField(blank=True, null=True)),
                ("fingerprint", models.CharField(blank=True, max_length=64)),
                ("template_version", models.CharField(blank=True, max_length=32)),
            ],
            options={
                "ordering": ["-generated_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="DrillerUser",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(default=True)),
                ("driller", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="driller_users", to="network.drillerprofile")),
                ("user_account", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="driller_user", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["driller__company_name", "user_account__email", "id"],
            },
        ),
        migrations.CreateModel(
            name="FieldExecution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("external_project_id", models.CharField(max_length=128, unique=True)),
                ("scheduled_start_date", models.DateField(blank=True, null=True)),
                ("estimated_days", models.DecimalField(decimal_places=2, max_digits=6, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("project_number", models.CharField(blank=True, max_length=64)),
                ("proposal_number", models.CharField(blank=True, max_length=64)),
                ("project_name", models.CharField(blank=True, max_length=255)),
                ("client_name", models.CharField(blank=True, max_length=255)),
                ("status", models.CharField(choices=[("assigned", "Assigned"), ("in_progress", "In progress"), ("submitted", "Submitted"), ("accepted", "Accepted"), ("needs_correction", "Needs correction")], default="assigned", max_length=32)),
                ("status_detail", models.TextField(blank=True)),
                ("assigned_driller", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="field_executions", to="network.drillerprofile")),
                ("booking_request", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="field_execution", to="network.bookingrequest")),
            ],
            options={
                "ordering": ["scheduled_start_date", "project_number", "id"],
            },
        ),
        migrations.CreateModel(
            name="DrillingInputRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("entry_method", models.CharField(choices=[("driller_direct", "Driller direct"), ("employee_from_paper", "Employee from paper"), ("employee_from_call", "Employee from call")], max_length=32)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("submitted", "Submitted"), ("under_review", "Under review"), ("accepted", "Accepted"), ("needs_correction", "Needs correction")], default="draft", max_length=32)),
                ("entered_by", models.CharField(blank=True, max_length=255)),
                ("submitted_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_by", models.CharField(blank=True, max_length=255)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("field_execution", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="drilling_input_records", to="fieldlogs.fieldexecution")),
            ],
            options={
                "ordering": ["-updated_at", "-id"],
            },
        ),
        migrations.AddField(
            model_name="drillinginputpdf",
            name="drilling_input_record",
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="pdf_artifact", to="fieldlogs.drillinginputrecord"),
        ),
        migrations.AddField(
            model_name="boring",
            name="drilling_input_record",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="borings", to="fieldlogs.drillinginputrecord"),
        ),
        migrations.CreateModel(
            name="SoilLayer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("depth_from", models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("depth_to", models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("visual_classification", models.CharField(blank=True, max_length=128)),
                ("moisture_condition", models.CharField(blank=True, max_length=128)),
                ("description", models.TextField(blank=True)),
                ("boring", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="soil_layers", to="fieldlogs.boring")),
            ],
            options={
                "ordering": ["depth_from", "id"],
            },
        ),
        migrations.CreateModel(
            name="SPT",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("depth", models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("blows_1", models.PositiveIntegerField(default=0)),
                ("blows_2", models.PositiveIntegerField(default=0)),
                ("blows_3", models.PositiveIntegerField(default=0)),
                ("n_value", models.PositiveIntegerField(default=0)),
                ("recovery", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("boring", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="spts", to="fieldlogs.boring")),
            ],
            options={
                "ordering": ["depth", "id"],
            },
        ),
        migrations.CreateModel(
            name="Groundwater",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("depth", models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("type", models.CharField(blank=True, max_length=128)),
                ("observed_at", models.DateTimeField(blank=True, null=True)),
                ("boring", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="groundwater_readings", to="fieldlogs.boring")),
            ],
            options={
                "ordering": ["depth", "id"],
            },
        ),
        migrations.CreateModel(
            name="Attachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("file", models.FileField(upload_to=driller_core.apps.fieldlogs.models.attachment_upload_to)),
                ("source_note", models.CharField(blank=True, max_length=255)),
                ("drilling_input_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="fieldlogs.drillinginputrecord")),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
