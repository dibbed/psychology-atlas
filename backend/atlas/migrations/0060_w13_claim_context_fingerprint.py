"""Version claim fingerprints without upgrading unverified historical evidence.

Existing rows retain their explanation-only SHA and are treated as requires_review
until a new explicit, actor-attributed v2 revision is recorded.
"""
from django.db import migrations, models


def protect_claim_context_rollback(apps, schema_editor):
    """Do not silently discard v2 attribution semantics on downgrade."""
    Revision = apps.get_model("atlas", "LearningEvidenceRevision")
    if Revision.objects.using(schema_editor.connection.alias).exclude(
            fingerprint_version="claim-text-v1").exists():
        raise RuntimeError(
            "Unsafe W13 rollback: claim-context-v2 revisions exist; "
            "preserve their schema and append-only provenance history."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("atlas", "0059_w13_learning_evidence"),
    ]

    operations = [
        migrations.AddField(
            model_name="learningevidencerevision",
            name="fingerprint_version",
            field=models.CharField(default="claim-text-v1", max_length=32),
        ),
        migrations.AddField(
            model_name="learningevidencerevision",
            name="change_reason",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.RunPython(migrations.RunPython.noop, protect_claim_context_rollback),
    ]
