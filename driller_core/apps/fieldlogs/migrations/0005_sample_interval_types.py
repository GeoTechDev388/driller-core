from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("fieldlogs", "0004_fieldexecution_planned_scope_and_boring_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="sampleinterval",
            name="sample_type",
            field=models.CharField(
                choices=[
                    ("spt", "SPT"),
                    ("shelby", "Shelby"),
                    ("grab", "Grab"),
                    ("coring", "Coring"),
                ],
                default="spt",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="sampleinterval",
            name="pocket_penetrometer",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="sampleinterval",
            name="rqd_percent",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True),
        ),
    ]
