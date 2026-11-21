"""Append-only P16 preparation dossiers; *never* an approval or public manifest."""
import uuid

from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel


class PublicationPreparationDossier(AppendOnlyModel):
    """Sealed, non-authorizing evidence snapshot for independent later review."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    selection = models.ForeignKey(
        "atlas.PublicationCandidateSelection", on_delete=models.PROTECT,
        related_name="preparation_dossiers",
    )
    request_key = models.UUIDField(unique=True)
    selection_digest = models.CharField(max_length=64)
    dossier = models.JSONField(default=dict)
    dossier_digest = models.CharField(max_length=64)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True,
                              on_delete=models.SET_NULL, related_name="+")
    actor_ref = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        indexes = [
            models.Index(fields=("selection", "-created_at"), name="cms_pub_prep_sel_idx"),
        ]
