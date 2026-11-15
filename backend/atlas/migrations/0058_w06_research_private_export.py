from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("atlas", "0057_w06_brain_private_intake")]

    operations = [
        migrations.RemoveConstraint(model_name="adminartifact", name="ck_cms_artifact_kind"),
        migrations.AddConstraint(
            model_name="adminartifact",
            constraint=models.CheckConstraint(condition=models.Q(kind__in=(
                "research_json", "dsm_json", "assessment_json", "brain_json",
                "evidence_json", "learning_json", "learning_export_json",
                "research_request_json", "research_export_json",
                "privacy_request_json", "privacy_export_json")), name="ck_cms_artifact_kind"),
        ),
        migrations.RemoveConstraint(model_name="adminjob", name="ck_cms_job_kind"),
        migrations.AddConstraint(
            model_name="adminjob",
            constraint=models.CheckConstraint(condition=models.Q(kind__in=(
                "research_intake", "research_export", "artifact_cleanup",
                "learning_import", "learning_export", "privacy_export")), name="ck_cms_job_kind"),
        ),
    ]
