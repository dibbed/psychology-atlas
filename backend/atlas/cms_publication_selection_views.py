"""Purpose-limited P16 immutable review-selection endpoints. No Apply."""
from rest_framework.response import Response

from .cms_policy import CMSFailure
from .cms_publication_selection import read_selection, response_data, select_candidates, verify_selection
from .cms_views import AdminAPIView


class PublicationSelectionView(AdminAPIView):
    capability = "cms_enter"

    def post(self, request):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        selected, created = select_candidates(
            request.user.pk, request.cms_session.pk, request.data, self.request_id,
        )
        return Response(response_data(selected, recovered=not created), status=201 if created else 200)


class PublicationSelectionDetailView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, selection_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        selected = read_selection(request.user.pk, request.cms_session.pk, selection_id)
        return Response(response_data(selected))


class PublicationSelectionVerifyView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, selection_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        return Response(verify_selection(request.user.pk, request.cms_session.pk, selection_id))
