"""Typed source lifecycle and immutable plans; canonical provenance stays in SourceReference."""
import uuid

from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel


class SourceState(models.Model):
    # A retained integer identity survives deletion of an unused canonical source.
    source_pk = models.PositiveBigIntegerField(unique=True)
    version = models.PositiveBigIntegerField(default=0)
    resource_version = models.CharField(max_length=120, blank=True)
    archived = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)

    class Meta:
        default_permissions = ()


class SourcePlan(AppendOnlyModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    schema_version = models.PositiveSmallIntegerField(default=1)
    version = models.PositiveBigIntegerField(default=1)
    operation = models.CharField(max_length=16)
    source_pk = models.PositiveBigIntegerField(null=True)
    source_ids = models.JSONField(default=list)
    request = models.JSONField(default=dict)
    fingerprint = models.CharField(max_length=64)
    preview = models.JSONField(default=dict)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        base_manager_name = "retained"


class SourcePlanReceipt(AppendOnlyModel):
    plan = models.OneToOneField(SourcePlan, on_delete=models.PROTECT, related_name="receipt")
    result = models.JSONField(default=dict)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)


class SourceHistory(AppendOnlyModel):
    source_pk = models.PositiveBigIntegerField(db_index=True)
    version = models.PositiveBigIntegerField()
    plan = models.ForeignKey(SourcePlan, on_delete=models.PROTECT, related_name="history")
    operation = models.CharField(max_length=16)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        base_manager_name = "retained"
        constraints = [models.UniqueConstraint(fields=("source_pk", "version"), name="uq_cms_source_history_version")]


class SourceSuccessor(AppendOnlyModel):
    source_pk = models.PositiveBigIntegerField(db_index=True)
    successor_pk = models.PositiveBigIntegerField(db_index=True)
    plan = models.ForeignKey(SourcePlan, on_delete=models.PROTECT, related_name="successors")
    operation = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        base_manager_name = "retained"
        constraints = [
            models.UniqueConstraint(fields=("source_pk", "successor_pk", "plan"), name="uq_cms_source_successor_plan"),
            models.CheckConstraint(condition=~models.Q(source_pk=models.F("successor_pk")), name="ck_cms_source_successor_not_self"),
        ]
