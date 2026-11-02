"""Append-only learning archive evidence; canonical learner rows are retained."""
from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel


class LearningArchiveReceipt(AppendOnlyModel):
    kind = models.CharField(max_length=16, choices=(
        ("quiz", "Quiz"), ("flashcard", "Flashcard"),
        ("daily", "Daily"), ("distortions", "Distortions"),
    ))
    resource_id = models.PositiveBigIntegerField()
    original_etag = models.PositiveBigIntegerField()
    request_digest = models.CharField(max_length=64)
    idempotency_key = models.UUIDField(unique=True)
    archived_at = models.DateTimeField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        constraints = [
            models.UniqueConstraint(fields=("kind", "resource_id"), name="uq_learning_archive_resource"),
            models.CheckConstraint(condition=models.Q(kind__in=("quiz", "flashcard", "daily", "distortions")),
                                   name="ck_learning_archive_kind"),
        ]
