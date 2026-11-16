"""P16 preparation-only endpoints. No approval, publish, or Apply action."""
from rest_framework.response import Response

from .cms_policy import CMSFailure
from .cms_publication_preparation import (
    prepare_selection, read_preparation, verify_preparation, list_preparations,
    recheck_recent_preparations, _receipt,
)
from .cms_views import AdminAPIView


class PreparationBulkRecheckView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request):
        return Response(recheck_recent_preparations(
            request.user.pk, request.cms_session.pk, request.query_params,
        ))


class PreparationInboxView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request):
        return Response(list_preparations(
            request.user.pk, request.cms_session.pk, request.query_params,
        ))


class PreparationCreateView(AdminAPIView):
    capability = "cms_enter"

    def post(self, request, selection_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        dossier, created = prepare_selection(
            request.user.pk, request.cms_session.pk, selection_id,
            request.data, self.request_id,
        )
        return Response(_receipt(dossier, recovered=not created),
                        status=201 if created else 200)


class PreparationDetailView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, dossier_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        return Response(read_preparation(
            request.user.pk, request.cms_session.pk, dossier_id,
        ))


class PreparationCandidatePreviewView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, dossier_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        from .cms_publication_candidate_preview import private_candidate_projection
        return Response(private_candidate_projection(
            request.user.pk, request.cms_session.pk, dossier_id,
        ))


class PreparationVerifyView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, dossier_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        return Response(verify_preparation(
            request.user.pk, request.cms_session.pk, dossier_id,
        ))
