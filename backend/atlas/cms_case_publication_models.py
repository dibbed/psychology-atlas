"""Revision-specific clinical education release decisions and immutable receipts.

Only CMS policy-guarded services may create/update these records. Review
decisions are evidence-bearing human attestations, never synthetic approvals.
"""
import uuid
from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel


class CasePublicationReview(AppendOnlyModel):
    revision = models.ForeignKey("atlas.CaseRevision", on_delete=models.PROTECT, related_name="cms_publication_reviews")
    kind = models.CharField(max_length=16, choices=(
        ("source", "Source"), ("scientific", "Scientific"), ("rights", "Rights"),
    ))
    outcome = models.CharField(max_length=16, choices=(("approved", "Approved"), ("revoked", "Revoked")))
    revision_digest = models.CharField(max_length=64)
    source_digest = models.CharField(max_length=64)
    evidence = models.JSONField(default=list)
    rights = models.JSONField(default=dict)
    policy_version = models.PositiveBigIntegerField()
    policy_mode = models.CharField(max_length=16)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)
    self_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        indexes = [models.Index(fields=("revision", "kind", "-id"), name="case_pub_review_idx")]


class CasePublicationPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.ForeignKey("atlas.CaseRevision", on_delete=models.PROTECT, related_name="cms_publication_plans")
    previous_revision = models.ForeignKey("atlas.CaseRevision", null=True, on_delete=models.PROTECT, related_name="+")
    manifest = models.JSONField()
    manifest_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default="frozen", choices=(
        ("frozen", "Frozen"), ("approved", "Approved"),
        ("applied", "Applied"), ("withdrawn", "Withdrawn"),
    ))
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True)
    applied_at = models.DateTimeField(null=True)

    class Meta:
        default_permissions = ()
        indexes = [models.Index(fields=("revision", "status"), name="case_pub_plan_idx")]


class CasePublicationReceipt(AppendOnlyModel):
    plan = models.ForeignKey(CasePublicationPlan, on_delete=models.PROTECT, related_name="receipts")
    event_type = models.CharField(max_length=16, choices=(("applied", "Applied"), ("withdrawn", "Withdrawn")))
    revision = models.ForeignKey("atlas.CaseRevision", on_delete=models.PROTECT)
    previous_revision = models.ForeignKey("atlas.CaseRevision", null=True, on_delete=models.PROTECT, related_name="+")
    manifest_digest = models.CharField(max_length=64)
    idempotency_key = models.UUIDField(unique=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        constraints = [models.UniqueConstraint(fields=("plan", "event_type"), name="uq_case_pub_receipt_event")]
