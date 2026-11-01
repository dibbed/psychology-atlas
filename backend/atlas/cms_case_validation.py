"""P12 case graph validation and publication prerequisite inventory.

This endpoint never grants scientific, rights, or publishing approval.
P16 must attach verified, revision-bound evidence before any activation.
"""
from rest_framework.response import Response

from .case_graph import validate_case_revision_graph
from .cms_case_fingerprint import case_revision_fingerprint
from .cms_case_publication import _review_status
from .cms_policy import CMSFailure, policy_lock, require
from .cms_views import AdminAPIView
from .models import CaseChoice, CaseQuestion, CaseRevision, CaseStep, CaseTransition


class CaseRevisionValidationView(AdminAPIView):
    capability = "cms_cases_validate"

    def get(self, request, case_id, revision_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_cases_view")
            require(request.user, "cms_cases_preview")
            revision = CaseRevision.objects.filter(pk=revision_id, case_id=case_id).first()
            if revision is None:
                raise CMSFailure("NOT_FOUND", 404)
            counts = {
                "steps": CaseStep.objects.filter(revision=revision).count(),
                "questions": CaseQuestion.objects.filter(step__revision=revision).count(),
                "choices": CaseChoice.objects.filter(question__step__revision=revision).count(),
                "transitions": CaseTransition.objects.filter(revision=revision).count(),
                "scoring_dimensions": revision.scoring_dimensions.count(),
            }
            if any(counts[k] > bound for k, bound in {
                "steps": 200, "questions": 800, "choices": 2000,
                "transitions": 2000, "scoring_dimensions": 50,
            }.items()):
                raise CMSFailure("PREVIEW_LIMIT", 400)
            issues = validate_case_revision_graph(revision)
            blockers = []
            if revision.status != CaseRevision.Status.DRAFT:
                blockers.append("NOT_EDITABLE_DRAFT")
            if not revision.title.strip() or not revision.patient_summary.strip():
                blockers.append("REQUIRED_CASE_METADATA_MISSING")
            if revision.seed_managed:
                blockers.append("SEED_MANAGED_REVISION")
            if issues:
                blockers.append("CASE_GRAPH_INVALID")
            # Governance metadata for ClinicalCase alone does not bind approvals
            # to this revision's full graph, scoring, narrative or source claims.
            # Never mistake case-wide legacy flags for revision-specific approval.
            approval_blockers, _ = _review_status(revision)
            blockers.extend(approval_blockers)
            if "SCIENTIFIC_REVIEW_REQUIRED" in approval_blockers:
                blockers.append("SCIENTIFIC_REVIEW_NOT_LINKED")
            if "SOURCE_REVIEW_REQUIRED" in approval_blockers or "RIGHTS_REVIEW_REQUIRED" in approval_blockers:
                blockers.append("SOURCE_RIGHTS_REVIEW_NOT_LINKED")
            return Response({
                "case_id": case_id, "revision_id": revision_id,
                "revision_digest": case_revision_fingerprint(revision),
                "revision_status": revision.status,
                "graph_valid": not issues, "graph_issues": issues,
                "counts": counts, "publication_eligible": not blockers,
                "publication_available": not blockers,
                "publication_blockers": blockers,
                "notice": "GRAPH_VALIDATION_IS_NOT_SCIENTIFIC_REVIEW_OR_RIGHTS_CLEARANCE",
            })
