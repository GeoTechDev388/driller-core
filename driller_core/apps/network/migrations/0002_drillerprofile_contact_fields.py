from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("network", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="drillerprofile",
            name="contact_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="drillerprofile",
            name="email",
            field=models.EmailField(blank=True, max_length=254),
        ),
        migrations.AddField(
            model_name="drillerprofile",
            name="phone",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]

