"""Immutable support receipts; no learner evidence or private support text."""
from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel


class StudyOperationReceipt(AppendOnlyModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)
    kind = models.CharField(max_length=8)
    resource_id = models.PositiveBigIntegerField()
    action = models.CharField(max_length=16)
    request_key = models.UUIDField(unique=True)
    request_digest = models.CharField(max_length=64)
    before_etag = models.CharField(max_length=66)
    after_etag = models.CharField(max_length=66)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        constraints = [models.CheckConstraint(condition=(
            models.Q(kind="plan", action__in=("pause", "resume"))
            | models.Q(kind="block", action__in=("reschedule", "skip", "unlock"))
            | models.Q(kind="session", action="abandon")), name="ck_study_support_action")]
