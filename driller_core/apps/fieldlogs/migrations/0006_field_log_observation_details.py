from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fieldlogs", "0005_sample_interval_types"),
    ]

    operations = [
        migrations.AddField(
            model_name="sampleinterval",
            name="pocket_penetrometer_top",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="sampleinterval",
            name="pocket_penetrometer_middle",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="sampleinterval",
            name="pocket_penetrometer_bottom",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="sampleobservation",
            name="sample_condition",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="sampleobservation",
            name="core_run_length",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="sampleobservation",
            name="rock_core_classification",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="sampleobservation",
            name="rock_type_name",
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name="sampleobservation",
            name="rock_notes",
            field=models.TextField(blank=True),
        ),
    ]
