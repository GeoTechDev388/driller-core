from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fieldlogs", "0003_next_generation_fieldlogs_phase1"),
    ]

    operations = [
        migrations.AddField(
            model_name="fieldexecution",
            name="planned_borings",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="planned_category",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="boringexecution",
            name="planned_sequence",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
