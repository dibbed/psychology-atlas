"""Scoped governance proposals; histories never rewrite scientific canonical facts."""
import uuid

from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel


class GovernanceRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=(("rights", "Rights"), ("terminology", "Terminology")))
    domain = models.CharField(max_length=16)
    resource_type = models.CharField(max_length=40)
    resource_id = models.PositiveBigIntegerField()
    resource_version = models.CharField(max_length=500)
    material = models.CharField(max_length=24, blank=True)
    intended_use = models.CharField(max_length=24, blank=True)
    term_kind = models.CharField(max_length=16, blank=True)
    version = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=16, default="submitted")
    current_revision = models.ForeignKey("GovernanceRevision", null=True, on_delete=models.PROTECT, related_name="current_for")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="cms_governance_assignments")
    contributors = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        indexes = [models.Index(fields=("resource_type", "resource_id", "material", "intended_use"), name="cms_gov_scope_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(kind__in=("rights", "terminology")), name="ck_cms_gov_kind"),
            models.CheckConstraint(condition=models.Q(status__in=("submitted", "in_review", "approved", "rejected", "revoked")), name="ck_cms_gov_status"),
        ]


class GovernanceRevision(AppendOnlyModel):
    record = models.ForeignKey(GovernanceRecord, on_delete=models.PROTECT, related_name="revisions")
    sequence = models.PositiveBigIntegerField()
    payload = models.JSONField()
    payload_digest = models.CharField(max_length=64)
    resource_digest = models.CharField(max_length=64)
    dependency_digest = models.CharField(max_length=64)
    source_ids = models.JSONField(default=list)
    status = models.CharField(max_length=16)
    assignee_ref = models.CharField(max_length=64, blank=True)
    policy_version = models.PositiveBigIntegerField()
    policy_mode = models.CharField(max_length=16)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)
    action = models.CharField(max_length=16)
    reason = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        constraints = [models.UniqueConstraint(fields=("record", "sequence"), name="uq_cms_gov_revision")]


class GovernanceDecision(AppendOnlyModel):
    record = models.ForeignKey(GovernanceRecord, on_delete=models.PROTECT, related_name="decisions")
    revision = models.ForeignKey(GovernanceRevision, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)
    assignee_ref = models.CharField(max_length=64, blank=True)
    outcome = models.CharField(max_length=16)
    reason = models.CharField(max_length=32)
    self_review = models.BooleanField(default=False)
    revision_hash = models.CharField(max_length=64)
    dependency_digest = models.CharField(max_length=64)
    policy_version = models.PositiveBigIntegerField()
    policy_mode = models.CharField(max_length=16)
    supersedes = models.ForeignKey("self", null=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
