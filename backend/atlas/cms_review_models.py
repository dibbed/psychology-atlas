"""Mutable review queues and append-only decisions, separate from canonical publication."""
from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel, ContentRevision


class ReviewPolicy(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    mode = models.CharField(max_length=16, choices=(("solo_owner", "Solo owner"), ("two_person", "Two person")), default="solo_owner")
    version = models.PositiveBigIntegerField(default=0)

    class Meta:
        default_permissions = ()


class ReviewPolicyRevision(AppendOnlyModel):
    version = models.PositiveBigIntegerField(unique=True)
    previous_mode = models.CharField(max_length=16)
    mode = models.CharField(max_length=16)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    reason = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)


class ReviewTask(models.Model):
    class Type(models.TextChoices):
        SOURCE = "source", "Source check"
        SCIENTIFIC = "scientific", "Scientific review"

    subject = models.ForeignKey(ContentRevision, on_delete=models.PROTECT, related_name="review_tasks")
    review_type = models.CharField(max_length=16, choices=Type.choices)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    version = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=16, default="queued", choices=tuple((s, s) for s in ("queued", "assigned", "approved", "rejected", "cancelled")))
    revision_hash = models.CharField(max_length=64)
    dependency_digest = models.CharField(max_length=64)
    evidence = models.JSONField(default=list)
    authors = models.JSONField(default=list)
    policy_version = models.PositiveBigIntegerField()
    policy_mode = models.CharField(max_length=16)

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=("subject", "review_type"), name="uq_cms_review_subject_type")]


class ReviewDecision(AppendOnlyModel):
    task = models.ForeignKey(ReviewTask, on_delete=models.PROTECT, related_name="decisions")
    revision = models.ForeignKey(ContentRevision, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)
    outcome = models.CharField(max_length=16)
    reason = models.CharField(max_length=32)
    fields = models.JSONField(default=list)
    evidence = models.JSONField(default=list)
    revision_hash = models.CharField(max_length=64)
    dependency_digest = models.CharField(max_length=64)
    policy_version = models.PositiveBigIntegerField()
    policy_mode = models.CharField(max_length=16)
    self_review = models.BooleanField(default=False)
    assignee_ref = models.CharField(max_length=64, blank=True)
    supersedes = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
