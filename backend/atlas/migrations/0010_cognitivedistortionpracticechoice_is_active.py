from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("atlas", "0009_alter_studyactivity_activity_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="cognitivedistortionpracticechoice",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
