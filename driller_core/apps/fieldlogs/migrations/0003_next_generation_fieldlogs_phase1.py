from decimal import Decimal
import uuid

import django.core.validators
import django.db.models.deletion
import driller_core.apps.fieldlogs.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fieldlogs", "0002_drilleruser_portal_access_enabled"),
    ]

    operations = [
        migrations.DeleteModel(name="Attachment"),
        migrations.DeleteModel(name="Groundwater"),
        migrations.DeleteModel(name="SPT"),
        migrations.DeleteModel(name="SoilLayer"),
        migrations.DeleteModel(name="Boring"),
        migrations.CreateModel(
            name="BoringExecution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=64)),
                ("planned_depth", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("actual_depth", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("status", models.CharField(choices=[("planned", "Planned"), ("active", "Active"), ("completed", "Completed"), ("terminated_early", "Terminated early"), ("abandoned", "Abandoned")], default="planned", max_length=32)),
                ("drilling_method", models.CharField(blank=True, max_length=64)),
                ("surface_elevation", models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ("backfill_method", models.CharField(blank=True, max_length=128)),
                ("notes", models.TextField(blank=True)),
                ("relocation_note", models.TextField(blank=True)),
                ("drilling_input_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="borings", to="fieldlogs.drillinginputrecord")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="FieldAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("file", models.FileField(upload_to=driller_core.apps.fieldlogs.models.attachment_upload_to)),
                ("source_note", models.CharField(blank=True, max_length=255)),
                ("drilling_input_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="attachments", to="fieldlogs.drillinginputrecord")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="SamplingPlan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("method_key", models.CharField(default="spt_standard", max_length=64)),
                ("rule_type", models.CharField(default="phase1_standard_spt", max_length=64)),
                ("rule_config", models.JSONField(blank=True, default=dict)),
                ("generated_to_depth", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("is_default", models.BooleanField(default=True)),
                ("boring", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="sampling_plan", to="fieldlogs.boringexecution")),
            ],
            options={"ordering": ["boring_id"]},
        ),
        migrations.CreateModel(
            name="GroundwaterObservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("observation_type", models.CharField(choices=[("encountered", "Encountered"), ("seepage", "Seepage"), ("stabilized", "Stabilized"), ("final", "Final"), ("cave_in", "Cave in"), ("after_completion", "After completion")], max_length=32)),
                ("depth", models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("observed_at", models.DateTimeField(blank=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("boring", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="groundwater_observations", to="fieldlogs.boringexecution")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="BoringCompletion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("final_depth", models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("termination_reason", models.CharField(choices=[("reached_planned_depth", "Reached planned depth"), ("refusal", "Refusal"), ("obstruction", "Obstruction"), ("cave_in", "Cave in"), ("not_possible", "Not possible"), ("access_limit", "Access limit"), ("operator_stop", "Operator stop"), ("other", "Other")], default="reached_planned_depth", max_length=32)),
                ("refusal_depth", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("obstruction_depth", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("cave_in_depth", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("notes", models.TextField(blank=True)),
                ("boring", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="completion", to="fieldlogs.boringexecution")),
            ],
        ),
        migrations.CreateModel(
            name="SampleInterval",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("sequence_number", models.PositiveIntegerField()),
                ("method_key", models.CharField(default="spt_standard", max_length=64)),
                ("state", models.CharField(choices=[("planned", "Planned"), ("taken", "Taken"), ("skipped", "Skipped"), ("refusal", "Refusal"), ("obstruction", "Obstruction"), ("terminated_early", "Terminated early"), ("not_possible", "Not possible")], default="planned", max_length=32)),
                ("planned_from_depth", models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("planned_to_depth", models.DecimalField(decimal_places=2, max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("actual_from_depth", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("actual_to_depth", models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("internal_sample_id", models.CharField(default=driller_core.apps.fieldlogs.models.generate_internal_sample_id, editable=False, max_length=64, unique=True)),
                ("sample_label", models.CharField(blank=True, max_length=128)),
                ("is_manual", models.BooleanField(default=False)),
                ("deviation_reason", models.CharField(blank=True, max_length=255)),
                ("operator_notes", models.TextField(blank=True)),
                ("boring", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="intervals", to="fieldlogs.boringexecution")),
                ("sampling_plan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="intervals", to="fieldlogs.samplingplan")),
            ],
            options={"ordering": ["boring_id", "sequence_number", "id"]},
        ),
        migrations.AddConstraint(
            model_name="sampleinterval",
            constraint=models.UniqueConstraint(fields=("boring", "sequence_number"), name="uniq_fieldlog_interval_boring_sequence"),
        ),
        migrations.CreateModel(
            name="SampleObservation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("visual_classification", models.CharField(blank=True, max_length=128)),
                ("moisture_condition", models.CharField(blank=True, max_length=128)),
                ("color", models.CharField(blank=True, max_length=128)),
                ("description", models.TextField(blank=True)),
                ("recovery_length", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=8, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("recovery_percent", models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True, validators=[django.core.validators.MinValueValidator(Decimal("0.00"))])),
                ("retained_sample", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("interval", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="observation", to="fieldlogs.sampleinterval")),
            ],
        ),
        migrations.CreateModel(
            name="SPTResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shared_uuid", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("blows_1", models.PositiveIntegerField(default=0)),
                ("blows_2", models.PositiveIntegerField(default=0)),
                ("blows_3", models.PositiveIntegerField(default=0)),
                ("n_value", models.PositiveIntegerField(default=0)),
                ("refusal_flag", models.BooleanField(default=False)),
                ("notes", models.TextField(blank=True)),
                ("interval", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="spt_result", to="fieldlogs.sampleinterval")),
            ],
        ),
    ]
