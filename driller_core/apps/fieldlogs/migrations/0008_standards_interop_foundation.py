from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fieldlogs", "0007_sample_chain_of_custody"),
    ]

    operations = [
        migrations.AddField(
            model_name="boringexecution",
            name="coordinate_accuracy_m",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=8,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="coordinate_captured_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="coordinate_confidence",
            field=models.CharField(
                choices=[("low", "Low"), ("medium", "Medium"), ("high", "High"), ("unknown", "Unknown")],
                default="unknown",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="coordinate_crs",
            field=models.CharField(blank=True, default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="coordinate_recorded_by",
            field=models.CharField(blank=True, default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="coordinate_source",
            field=models.CharField(
                choices=[
                    ("manual_entry", "Manual entry"),
                    ("uploaded_map_file", "Uploaded map file"),
                    ("appendix_b_map_workspace", "Appendix B map workspace"),
                    ("field_log_manual", "Field log manual entry"),
                    ("phone_gps", "Phone GPS"),
                    ("survey", "Survey"),
                    ("unknown", "Unknown"),
                ],
                default="unknown",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="coordinate_system",
            field=models.CharField(
                choices=[
                    ("geographic", "Geographic"),
                    ("projected", "Projected"),
                    ("local", "Local / site"),
                    ("unknown", "Unknown"),
                ],
                default="geographic",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="depth_unit",
            field=models.CharField(default="ft", max_length=16),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="drilling_method_authority",
            field=models.CharField(
                choices=[
                    ("astm", "ASTM"),
                    ("aashto", "AASHTO"),
                    ("internal", "Internal"),
                    ("other", "Other"),
                    ("unknown", "Unknown / not specified"),
                ],
                default="unknown",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="drilling_method_code",
            field=models.CharField(blank=True, default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="drilling_method_notes",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="drilling_method_version",
            field=models.CharField(blank=True, default="", max_length=32),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="horizontal_datum",
            field=models.CharField(blank=True, default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="latitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                max_digits=10,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("-90.0000000")),
                    django.core.validators.MaxValueValidator(Decimal("90.0000000")),
                ],
            ),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="location_notes",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="location_review_status",
            field=models.CharField(
                choices=[("unreviewed", "Unreviewed"), ("reviewed", "Reviewed"), ("rejected", "Rejected")],
                default="unreviewed",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="longitude",
            field=models.DecimalField(
                blank=True,
                decimal_places=7,
                max_digits=11,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("-180.0000000")),
                    django.core.validators.MaxValueValidator(Decimal("180.0000000")),
                ],
            ),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="surface_elevation_accuracy_ft",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=8,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="surface_elevation_reference",
            field=models.CharField(blank=True, default="", max_length=128),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="surface_elevation_source",
            field=models.CharField(
                choices=[
                    ("manual_entry", "Manual entry"),
                    ("uploaded_map_file", "Uploaded map file"),
                    ("appendix_b_map_workspace", "Appendix B map workspace"),
                    ("field_log_manual", "Field log manual entry"),
                    ("phone_gps", "Phone GPS"),
                    ("survey", "Survey"),
                    ("unknown", "Unknown"),
                ],
                default="unknown",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="surface_elevation_unit",
            field=models.CharField(default="ft", max_length=16),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="surface_elevation_vertical_datum",
            field=models.CharField(blank=True, default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sampleinterval",
            name="depth_unit",
            field=models.CharField(default="ft", max_length=16),
        ),
        migrations.AddField(
            model_name="sampleinterval",
            name="method_authority",
            field=models.CharField(
                choices=[
                    ("astm", "ASTM"),
                    ("aashto", "AASHTO"),
                    ("internal", "Internal"),
                    ("other", "Other"),
                    ("unknown", "Unknown / not specified"),
                ],
                default="unknown",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="sampleinterval",
            name="method_code",
            field=models.CharField(blank=True, default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sampleinterval",
            name="method_notes",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sampleinterval",
            name="method_version",
            field=models.CharField(blank=True, default="", max_length=32),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sampleinterval",
            name="pocket_penetrometer_unit",
            field=models.CharField(default="tsf", max_length=16),
        ),
        migrations.AddField(
            model_name="sampleinterval",
            name="rqd_unit",
            field=models.CharField(default="percent", max_length=16),
        ),
        migrations.AddField(
            model_name="sptresult",
            name="method_authority",
            field=models.CharField(
                choices=[
                    ("astm", "ASTM"),
                    ("aashto", "AASHTO"),
                    ("internal", "Internal"),
                    ("other", "Other"),
                    ("unknown", "Unknown / not specified"),
                ],
                default="unknown",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="sptresult",
            name="method_code",
            field=models.CharField(blank=True, default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sptresult",
            name="method_notes",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="sptresult",
            name="method_version",
            field=models.CharField(blank=True, default="", max_length=32),
            preserve_default=False,
        ),
    ]
