"""P12 guarded draft API: CaseRevision only, never learner attempts."""
from rest_framework.response import Response

from .cms_case_editor import clone_draft, revision_etag, update_draft_metadata
from .cms_case_graph_editor import replace_draft_graph
from .cms_views import AdminAPIView, expected_version, payload


class CaseCloneDraftView(AdminAPIView):
    capability = "cms_cases_create"

    def post(self, request, case_id, revision_id):
        payload(request, set())
        draft = clone_draft(request.user.pk, request.cms_session.pk, case_id,
                            revision_id, expected_version(request), self.request_id)
        response = Response({
            "case_id": draft.case_id, "revision_id": draft.pk,
            "revision_version": draft.version, "status": draft.status,
            "publication_available": False,
        }, status=201)
        response["ETag"] = f'"{revision_etag(draft)}"'
        return response


class CaseDraftMetadataView(AdminAPIView):
    capability = "cms_cases_edit"

    def post(self, request, case_id, revision_id):
        data = payload(request, {"title", "patient_summary", "educational_objective",
                                 "difficulty", "primary_disorder_id"})
        revision = update_draft_metadata(request.user.pk, request.cms_session.pk,
                                          case_id, revision_id, expected_version(request),
                                          data, self.request_id)
        response = Response({
            "case_id": revision.case_id, "revision_id": revision.pk,
            "revision_version": revision.version, "title": revision.title,
            "status": revision.status, "publication_available": False,
        })
        response["ETag"] = f'"{revision_etag(revision)}"'
        return response

class CaseDraftGraphEditView(AdminAPIView):
    capability = "cms_cases_edit"

    def post(self, request, case_id, revision_id):
        data = payload(request, {"entry_step_key", "rubric_version", "steps",
                                 "scoring_dimensions", "questions", "choices", "transitions"})
        draft, issues = replace_draft_graph(
            request.user.pk, request.cms_session.pk, case_id, revision_id,
            expected_version(request), data, self.request_id,
        )
        response = Response({
            "case_id": draft.case_id, "revision_id": draft.pk,
            "status": draft.status, "valid": not issues, "issues": issues,
            "publication_available": False,
        })
        response["ETag"] = f'"{revision_etag(draft)}"'
        return response
