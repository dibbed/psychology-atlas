"""Immutable frozen review plan, explicitly not publication authority."""
import uuid

from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel


class PublicationFrozenManifest(AppendOnlyModel):
    """One immutable manifest per sealed dossier.

    Approval, atomic Apply and eventual receipts are separate operations.
    Historic manifest bytes and digest are retained on any policy change.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dossier = models.OneToOneField(
        "atlas.PublicationPreparationDossier", on_delete=models.PROTECT,
        related_name="frozen_manifest",
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
