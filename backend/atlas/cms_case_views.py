"""Private CaseRevision graph inspector for P12 editor preparation.

Read-only canonical graph and validator output. No CaseAttempt, scoring,
StudyActivity, current-revision selection or publication mutations.
"""
from rest_framework.response import Response

from .case_graph import validate_case_revision_graph
from .cms_case_editor import revision_etag
from .cms_case_fingerprint import case_revision_fingerprint
from .cms_policy import CMSFailure, policy_lock, require
from .cms_views import AdminAPIView
from .models import CaseChoice, CaseQuestion, CaseRevision, CaseScoringDimension, CaseStep, CaseTransition


class CaseRevisionGraphView(AdminAPIView):
    capability = "cms_cases_preview"

    def get(self, request, case_id, revision_id):
        with policy_lock():
            require(request.user, "cms_cases_view")
            if request.query_params:
                raise CMSFailure("INVALID_QUERY", 400)
            revision = CaseRevision.objects.filter(
                pk=revision_id, case_id=case_id,
            ).only(
                "id", "case_id", "version", "status", "title", "patient_summary",
                "educational_objective", "difficulty", "rubric_version", "entry_step_id",
                "content_hash", "primary_disorder_id",
            ).first()
            if revision is None:
                raise CMSFailure("NOT_FOUND", 404)

            # Enforce explicit limits before serializing any content or running
            # the recursive canonical graph validator.
            scopes = (
                (CaseStep.objects.filter(revision_id=revision.pk), 200),
                (CaseQuestion.objects.filter(step__revision_id=revision.pk), 800),
                (CaseChoice.objects.filter(question__step__revision_id=revision.pk), 2000),
                (CaseTransition.objects.filter(revision_id=revision.pk), 2000),
                (CaseScoringDimension.objects.filter(revision_id=revision.pk), 50),
            )
            for queryset, ceiling in scopes:
                if queryset.values_list("pk", flat=True)[:ceiling + 1].count() > ceiling:
                    raise CMSFailure("PREVIEW_LIMIT", 400)

            steps = list(scopes[0][0].order_by("sort_order", "pk").values(
                "id", "stable_key", "node_kind", "title", "narrative", "sort_order", "is_active",
            ))
            questions = list(scopes[1][0].order_by("step_id", "sort_order", "pk").values(
                "id", "step_id", "scoring_dimension_id", "prompt", "explanation",
                "sort_order", "is_active",
            ))
            choices = list(scopes[2][0].order_by("question_id", "sort_order", "pk").values(
                "id", "question_id", "text", "score_value", "feedback", "sort_order", "is_active",
            ))
            transitions = list(scopes[3][0].order_by("source_step_id", "sort_order", "pk").values(
                "id", "source_step_id", "choice_id", "target_step_id", "outcome",
                "sort_order", "is_active",
            ))
            dimensions = list(scopes[4][0].order_by("sort_order", "pk").values(
                "id", "stable_key", "label", "description", "sort_order", "is_active",
            ))
            issues = validate_case_revision_graph(revision)
            response = Response({
                "scope": "private_canonical_revision_graph",
                "case_id": case_id,
                "revision_id": revision.pk,
                "revision_version": revision.version,
                "revision_status": revision.status,
                "current_revision_id": revision.case.current_revision_id,
                "content_hash": revision.content_hash,
                "revision_digest": case_revision_fingerprint(revision),
                "title": revision.title,
                "patient_summary": revision.patient_summary,
                "educational_objective": revision.educational_objective,
                "difficulty": revision.difficulty,
                "primary_disorder_id": revision.primary_disorder_id,
                "rubric_version": revision.rubric_version,
                "entry_step_id": revision.entry_step_id,
                "steps": steps,
                "questions": questions,
                "choices": choices,
                "transitions": transitions,
                "scoring_dimensions": dimensions,
                "valid": not issues,
                "issues": issues,
                "simulation_creates_attempt": False,
                "publication_available": False,
                "notice": "PRIVATE_READ_ONLY; VALIDATION_IS_NOT_SCIENTIFIC_REVIEW_OR_PUBLICATION",
            })
            response["ETag"] = f'"{revision_etag(revision)}"'
            return response
