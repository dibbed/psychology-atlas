from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("atlas", "0056_v100_p18_worker_poll_observation")]

    operations = [
        migrations.RemoveConstraint(model_name="adminartifact", name="ck_cms_artifact_kind"),
        migrations.AddConstraint(
            model_name="adminartifact",
            constraint=models.CheckConstraint(
                condition=models.Q(kind__in=(
                    "research_json", "dsm_json", "assessment_json", "brain_json",
                    "evidence_json", "learning_json", "learning_export_json",
                    "privacy_request_json", "privacy_export_json")),
                name="ck_cms_artifact_kind",
            ),
        ),
    ]
