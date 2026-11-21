"""Immutable P16 review selections. Never a scientific/rights/publication approval."""
import uuid

from django.conf import settings
from django.db import models

from .cms_content_models import AppendOnlyModel


class PublicationCandidateSelection(AppendOnlyModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    domain = models.CharField(max_length=16, choices=(
        ("learning", "Learning"), ("brain", "Brain"), ("assessment", "Assessment"),
    ))
    request_key = models.UUIDField(unique=True)
    request_digest = models.CharField(max_length=64)
    selection = models.JSONField(default=dict)
    selection_digest = models.CharField(max_length=64)
    policy_version = models.PositiveBigIntegerField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_ref = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(AppendOnlyModel.Meta):
        abstract = False
        indexes = [
            models.Index(fields=("domain", "-created_at"), name="cms_pub_sel_domain_idx"),
        ]
