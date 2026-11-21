"""P10 private Brain ancestry and proposed-parent impact. Read-only canonical."""
from django.db.models import Q
from rest_framework.response import Response

from .cms_content_models import ContentState
from .cms_policy import CMSFailure, policy_lock, require
from .cms_views import AdminAPIView, page
from .models import BrainAnatomicalEntity, BrainHierarchyLink


def positive_id(raw):
    if not isinstance(raw, str) or not raw.isascii() or not raw.isdecimal() or len(raw) > 19:
        raise CMSFailure("INVALID_QUERY", 400)
    number = int(raw)
    if not 0 < number < 2**63:
        raise CMSFailure("INVALID_QUERY", 400)
    return number


class BrainTreeView(AdminAPIView):
    capability = "cms_brain_view"

    def get(self, request):
        with policy_lock():
            params = request.query_params
            if set(params) - {"page", "page_size", "child", "parent"}:
                raise CMSFailure("INVALID_QUERY", 400)
            changing = "child" in params or "parent" in params
            if changing:
                require(request.user, "cms_brain_preview")
                if "child" not in params or "parent" not in params or set(params) != {"child", "parent"}:
                    raise CMSFailure("INVALID_QUERY", 400)
                return self.impact(positive_id(params["child"]), positive_id(params["parent"]))

            # The editor is only for actual existing canonical anatomy nodes.
            rows = BrainAnatomicalEntity.objects.order_by("name_en", "pk")
            meta, selected = page(request, rows)
            ids = [row.pk for row in selected]
            links = dict(BrainHierarchyLink.objects.filter(child_id__in=ids, is_active=True)
                         .values_list("child_id", "parent_id"))
            states = dict(ContentState.objects.filter(kind="brain-anatomical-entity",
                canonical_pk__in=ids).values_list("canonical_pk", "pk"))
            return Response({**meta, "scope": "private_canonical_metadata",
                "publication_available": False, "results": [{
                    "id": row.pk, "slug": row.slug, "name_en": row.name_en, "name_fa": row.name_fa,
                    "laterality": row.laterality, "kind": row.kind, "is_active": row.is_active,
                    "review_status": row.review_status, "parent_id": links.get(row.pk),
                    "cms_state_id": str(states[row.pk]) if row.pk in states else None,
                } for row in selected],
                "notice": "This tree is private canonical data; no proposal is published here."})

    def impact(self, child_id, parent_id):
        # A bounded graph protects the preview from arbitrary corpus expansion.
        records = list(BrainAnatomicalEntity.objects.values(
            "pk", "name_en", "name_fa", "laterality", "is_active")[:5001])
        if len(records) > 5000:
            raise CMSFailure("PREVIEW_LIMIT", 400)
        nodes = {row["pk"]: row for row in records}
        if child_id not in nodes or parent_id not in nodes:
            raise CMSFailure("NOT_FOUND", 404)
        edges = list(BrainHierarchyLink.objects.filter(is_active=True)
                     .values_list("child_id", "parent_id")[:5001])
        if len(edges) > 5000:
            raise CMSFailure("PREVIEW_LIMIT", 400)
        parent_map = dict(edges)
        before_id = parent_map.get(child_id)
        children = {}
        for child, parent in edges:
            children.setdefault(parent, []).append(child)
        descendants = []
        pending = list(children.get(child_id, ()))
        visited = {child_id}
        while pending:
            current = pending.pop()
            if current in visited:
                raise CMSFailure("INVALID_CANONICAL_TREE", 409)
            visited.add(current)
            descendants.append(current)
            pending.extend(children.get(current, ()))
        blockers = []
        if child_id == parent_id or parent_id in visited:
            blockers.append("CYCLE")
        if not nodes[child_id]["is_active"] or not nodes[parent_id]["is_active"]:
            blockers.append("INACTIVE_ENDPOINT")
        if BrainHierarchyLink.laterality_conflicts(nodes[child_id]["laterality"], nodes[parent_id]["laterality"]):
            blockers.append("LATERALITY_CONFLICT")
        return Response({
            "child_id": child_id,
            "before": {"parent_id": before_id},
            "after": {"parent_id": parent_id, "valid": not blockers, "blockers": blockers},
            "affected_descendants": sorted(descendants),
            "affected_count": len(descendants) + 1,
            "requires_scientific_source_review": True,
            "requires_publication_manifest": True,
            "publication_available": False,
            "scope": "private_impact_preview_only",
            "notice": "Parent changes are private proposals. Other active links, reviewed evidence and public eligibility are not changed.",
        })
