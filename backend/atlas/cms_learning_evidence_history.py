"""Read-only, permission-aware, paginated learning evidence revision history."""
from rest_framework.response import Response

from .cms_learning_evidence import _claim_context, _state, _target
from .cms_learning_evidence_models import LearningEvidenceRevision
from .cms_policy import CMSFailure, policy_lock, require
from .cms_sources import require_impact_scope, source_impact
from .cms_views import AdminAPIView


class LearningEvidenceHistoryView(AdminAPIView):
    capability = "cms_learning_view"

    def get(self, request, kind, item_id):
        raw_page = request.query_params.get("page", "1")
        if (set(request.query_params) - {"page"} or
                not raw_page.isascii() or not raw_page.isdigit() or
                not 1 <= int(raw_page) <= 10000):
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_learning_view")
            require(request.user, "cms_source_view")
            item, field = _target(kind, item_id)
            queryset = LearningEvidenceRevision.objects.filter(kind=kind, target_pk=item_id)
            page = int(raw_page)
            revisions = list(queryset.order_by("sequence").prefetch_related(
                "links__source")[(page - 1) * 50:page * 50])
            if revisions:
                predecessor = queryset.filter(
                    sequence__lt=revisions[0].sequence).order_by("-sequence").first()
                previous = set(predecessor.links.values_list("source_id", flat=True)) if predecessor else set()
            else:
                previous = set()
            checked = set()
            context_digest = _claim_context(kind, item)
            source_cache = {}
            result = []
            for revision in revisions:
                links = list(revision.links.all())
                for link in links:
                    if link.source_id not in checked:
                        require_impact_scope(request.user, source_impact(link.source))
                        checked.add(link.source_id)
                state, _ = _state(kind, item, field, revision,
                                   context_digest=context_digest, source_cache=source_cache)
                current = {link.source_id for link in links}
                result.append({
                    "revision": revision.sequence,
                    "created_at": revision.created_at,
                    "actor_id": revision.actor_id,
                    "fingerprint_version": revision.fingerprint_version,
                    "status": state["status"],
                    "content_digest": revision.content_digest,
                    "links": state["links"],
                    "added_source_ids": sorted(current - previous),
                    "removed_source_ids": sorted(previous - current),
                    "change_reason": revision.change_reason or "LEGACY_REASON_UNRECORDED",
                })
                previous = current
            total = queryset.count()
            return Response({
                "kind": kind, "item_id": item_id, "revisions": result,
                "page": page, "count": total,
                "next_page": page + 1 if page * 50 < total else None,
            })
