"""Immutable frozen review plan, explicitly not publication authority."""
import uuid

from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel


class PublicationFrozenManifest(AppendOnlyModel):
    """Immutable manifest for a sealed dossier; reinstatement adds a new row.

    Approval, atomic Apply and eventual receipts are separate operations.
    Historic manifest bytes and digest are retained on any policy change.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dossier = models.ForeignKey(
        "atlas.PublicationPreparationDossier", on_delete=models.PROTECT,
        related_name="frozen_manifests",
    )
    reinstates = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT,
        related_name="reinstatements",
    )
    request_key = models.UUIDField(unique=True)
    manifest = models.JSONField(default=dict)
    manifest_digest = models.CharField(max_length=64)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                              on_delete=models.SET_NULL, related_name="+")
    actor_ref = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        indexes = [
            models.Index(fields=("created_at",), name="cms_pub_frozen_created"),
        ]


class PublicationManifestAttestation(AppendOnlyModel):
    """Append-only, explicitly non-authorizing human evidence for one manifest."""

    id = models.BigAutoField(primary_key=True)
    plan = models.ForeignKey(
        PublicationFrozenManifest, on_delete=models.PROTECT,
        related_name="attestations",
    )
    request_key = models.UUIDField(unique=True)
    manifest_digest = models.CharField(max_length=64)
    kind = models.CharField(max_length=16, choices=(
        ("source", "Source"), ("scientific", "Scientific"), ("rights", "Rights"),
    ))
    outcome = models.CharField(max_length=16, choices=(
        ("attested", "Attested"), ("revoked", "Revoked"),
    ))
    evidence_source_ids = models.JSONField(default=list)
    rights_scope = models.JSONField(default=list)
    evidence_reference = models.CharField(max_length=400, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                              on_delete=models.SET_NULL, related_name="+")
    actor_ref = models.CharField(max_length=64)
    policy_version = models.PositiveBigIntegerField()
    policy_mode = models.CharField(max_length=16)
    self_review = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        indexes = [
            models.Index(fields=("plan", "kind", "-id"),
                         name="cms_pub_att_plan_kind"),
        ]
