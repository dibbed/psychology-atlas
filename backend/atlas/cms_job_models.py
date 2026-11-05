"""Durable, scoped work and private bytes; canonical research models stay authoritative."""
import uuid

from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel


class AdminArtifact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=24)
    domain = models.CharField(max_length=16)
    resource_type = models.CharField(max_length=40, blank=True)
    resource_id = models.PositiveBigIntegerField(null=True)
    resource_version = models.CharField(max_length=500, blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="cms_artifacts")
    owner_ref = models.CharField(max_length=64)
    state = models.CharField(max_length=16, default="quarantine")
    version = models.PositiveBigIntegerField(default=1)
    storage_key = models.CharField(max_length=180, unique=True)
    filename = models.CharField(max_length=120)
    sha256 = models.CharField(max_length=64, db_index=True)
    size = models.PositiveBigIntegerField()
    validation_code = models.CharField(max_length=48, blank=True)
    expires_at = models.DateTimeField()
    purged_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        constraints = [
            models.CheckConstraint(condition=models.Q(state__in=("quarantine", "ready", "rejected", "revoked", "expired")), name="ck_cms_artifact_state"),
            models.CheckConstraint(condition=models.Q(kind__in=("research_json", "dsm_json", "assessment_json", "evidence_json", "learning_json", "learning_export_json", "privacy_request_json", "privacy_export_json")), name="ck_cms_artifact_kind"),
        ]


class AdminJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=24)
    schema_version = models.PositiveSmallIntegerField(default=1)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="cms_jobs")
    actor_ref = models.CharField(max_length=64)
    session = models.ForeignKey("AdminSession", null=True, on_delete=models.SET_NULL, related_name="jobs")
    policy_version = models.PositiveBigIntegerField()
    artifact = models.ForeignKey(AdminArtifact, on_delete=models.PROTECT, related_name="jobs")
    output_artifact = models.ForeignKey(AdminArtifact, null=True, blank=True, on_delete=models.PROTECT, related_name="output_jobs")
    request_key = models.UUIDField()
    payload_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=24, default="queued")
    version = models.PositiveBigIntegerField(default=1)
    attempt = models.PositiveSmallIntegerField(default=0)
    lease_token = models.UUIDField(null=True)
    lease_expires_at = models.DateTimeField(null=True)
    heartbeat_at = models.DateTimeField(null=True)
    available_at = models.DateTimeField()
    cancel_requested = models.BooleanField(default=False)
    progress_done = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(null=True)
    checkpoint = models.JSONField(default=dict)
    result = models.JSONField(default=dict)
    error_code = models.CharField(max_length=48, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=("actor_ref", "request_key"), name="uq_cms_job_request"),
            models.CheckConstraint(condition=models.Q(status__in=("queued", "running", "succeeded", "failed", "cancelled", "reconciling")), name="ck_cms_job_status"),
            models.CheckConstraint(condition=models.Q(kind__in=("research_intake", "artifact_cleanup", "learning_import", "learning_export", "privacy_export")), name="ck_cms_job_kind"),
        ]
        indexes = [models.Index(fields=("status", "available_at"), name="cms_job_claim_idx")]


class ResearchRecordDecision(AppendOnlyModel):
    record = models.ForeignKey("ResearchRecord", on_delete=models.PROTECT, related_name="cms_decisions")
    sequence = models.PositiveBigIntegerField()
    action = models.CharField(max_length=16)
    mapping = models.JSONField(default=dict)
    payload_digest = models.CharField(max_length=64)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)
    reason = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        constraints = [
            models.UniqueConstraint(fields=("record", "sequence"), name="uq_cms_research_decision"),
            models.CheckConstraint(condition=models.Q(action__in=("map", "reject", "defer", "stage")), name="ck_cms_research_decision"),
        ]
