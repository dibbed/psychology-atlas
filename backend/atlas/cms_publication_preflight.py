"""P16 server-owned candidate inventory (safe first step, NEVER an Apply endpoint).

A candidate shown here is not scientifically, legally or operationally
publishable. Real reviewed manifests, receipts and dependency closure remain
separate P16 requirements. Existing pin-based publishers stay untouched.
"""
from rest_framework.response import Response

from .case_graph import validate_case_revision_graph
from .cms_case_fingerprint import case_revision_fingerprint
from .cms_case_publication import _review_status

from .cms_policy import CMSFailure, policy_lock, require
from .cms_views import AdminAPIView, page
from .models import (
    CaseRevision, CognitiveDistortionPracticeItem, DailyChallenge, Flashcard, Quiz,
)


_DOMAINS = {"cases", "learning"}
_REVIEW_BLOCKERS = (
    "SCIENTIFIC_REVIEW_NOT_LINKED", "SOURCE_RIGHTS_REVIEW_NOT_LINKED",
    "P16_MANIFEST_AND_RECEIPT_REQUIRED",
)


class PublicationPreflightView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request):
        domain = request.query_params.get("domain")
        if domain not in _DOMAINS or list(request.query_params.getlist("domain")) != [domain]:
            raise CMSFailure("INVALID_QUERY", 400)
        if set(request.query_params) - {"domain", "page", "page_size"}:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_publication_validate_" + domain)
            require(request.user, "cms_" + ("cases" if domain == "cases" else "learning") + "_view")
            if domain == "cases":
                queryset = CaseRevision.objects.filter(status=CaseRevision.Status.DRAFT).order_by("-pk")
                meta, revisions = page(request, queryset, extra=("domain",))
                rows = []
                for rev in revisions:
                    blockers, _ = _review_status(rev)
                    if not rev.title.strip() or not rev.patient_summary.strip() or not rev.educational_objective.strip():
                        blockers.append("REQUIRED_CASE_METADATA_MISSING")
                    if rev.seed_managed or rev.case.seed_managed:
                        blockers.append("SEED_MANAGED_REVISION")
                    if validate_case_revision_graph(rev):
                        blockers.append("CASE_GRAPH_INVALID")
                    if "SOURCE_REVIEW_REQUIRED" in blockers or "RIGHTS_REVIEW_REQUIRED" in blockers:
                        blockers.append("SOURCE_RIGHTS_REVIEW_NOT_LINKED")
                    if "SCIENTIFIC_REVIEW_REQUIRED" in blockers:
                        blockers.append("SCIENTIFIC_REVIEW_NOT_LINKED")
                    rows.append({"kind": "case_revision", "resource_id": rev.pk, "case_id": rev.case_id,
                        "version": rev.version, "eligible": not blockers,
                        "revision_digest": case_revision_fingerprint(rev),
                        "blockers": sorted(set(blockers))})
            else:
                candidates = []
                for model, name in (
                    (Quiz, "quiz"), (Flashcard, "flashcard"),
                    (DailyChallenge, "daily_challenge"),
                    (CognitiveDistortionPracticeItem, "distortion_practice"),
                ):
                    identifiers = list(model.objects.filter(
                        is_active=False, seed_managed=False,
                    ).order_by("-pk").values_list("pk", flat=True)[:1001])
                    if len(identifiers) > 1000:
                        raise CMSFailure("PREVIEW_LIMIT", 400)
                    candidates.extend((name, item_id) for item_id in identifiers)
                # Filtered learning candidates have no user identity and no
                # publish authority. Stable order and bounded server paging.
                candidates.sort(key=lambda value: (value[0], -value[1]))
                from django.core.paginator import Paginator, EmptyPage
                try:
                    current = int(request.query_params.get("page", "1"))
                    size = int(request.query_params.get("page_size", "30"))
                except (TypeError, ValueError):
                    raise CMSFailure("INVALID_QUERY", 400)
                if not 1 <= current <= 100000 or not 1 <= size <= 100:
                    raise CMSFailure("INVALID_QUERY", 400)
                paginator = Paginator(candidates, size)
                if current > paginator.num_pages:
                    raise CMSFailure("INVALID_QUERY", 400)
                rows = [{
                    "kind": kind, "resource_id": identifier,
                    "eligible": False, "blockers": [*_REVIEW_BLOCKERS, "CONTENT_VALIDATION_REQUIRED"],
                } for kind, identifier in paginator.page(current).object_list]
                meta = {"count": len(candidates), "page": current, "page_size": size}
            return Response({
                **meta, "domain": domain, "results": rows,
                "publication_available": domain == "cases",
                "scope": "private_unpublished_candidates_only",
                "notice": "REVIEWED_CASES_REQUIRE_EXPLICIT_MANIFEST_APPROVAL_AND_MFA_APPLY",
            })
