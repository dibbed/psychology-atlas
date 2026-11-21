"""P13 immutable, private learning-explanation provenance revisions.

A locator is editorial evidence, not scientific approval or a publication grant.
Records are never copied implicitly into new questions or imported learning items.
"""
from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel


class LearningEvidenceRevision(AppendOnlyModel):
    kind = models.CharField(max_length=24)
    target_pk = models.PositiveBigIntegerField()
    sequence = models.PositiveBigIntegerField()
    content_digest = models.CharField(max_length=64)
    fingerprint_version = models.CharField(max_length=32, default="claim-text-v1")
    change_reason = models.CharField(max_length=500, blank=True, default="")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        constraints = [
            models.UniqueConstraint(fields=("kind", "target_pk", "sequence"),
                                    name="uq_learning_evidence_revision"),
        ]
        indexes = [models.Index(fields=("kind", "target_pk", "-sequence"),
                                name="cms_learning_ev_latest_idx")]


class LearningEvidenceSource(AppendOnlyModel):
    revision = models.ForeignKey(LearningEvidenceRevision, on_delete=models.PROTECT,
                                 related_name="links")
    source = models.ForeignKey("atlas.SourceReference", on_delete=models.PROTECT,
                               related_name="learning_evidence_links")
    locator = models.CharField(max_length=500)
    source_digest = models.CharField(max_length=64)

    @property
    def domain(self):
        # Source-impact permission classification; never expose via public APIs.
        return "learning"

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        constraints = [
            models.UniqueConstraint(fields=("revision", "source"),
                                    name="uq_learning_evidence_revision_source"),
        ]
