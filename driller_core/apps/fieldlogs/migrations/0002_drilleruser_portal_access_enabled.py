from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fieldlogs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="drilleruser",
            name="portal_access_enabled",
            field=models.BooleanField(default=True),
        ),
    ]
