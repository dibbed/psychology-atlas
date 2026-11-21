"""Scoped append-only W16-03 reviewer attestations, never public Apply."""
from rest_framework.response import Response

from .cms_policy import CMSFailure
from .cms_publication_attestations import (
    read_attestations, record_attestation, _receipt,
)
from .cms_views import AdminAPIView


class PublicationAttestationsView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, plan_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        return Response(read_attestations(
            request.user.pk, request.cms_session.pk, plan_id,
        ))

    def post(self, request, plan_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        record, created = record_attestation(
            request.user.pk, request.cms_session.pk, plan_id,
            request.data, self.request_id,
        )
        return Response(_receipt(record, recovered=not created),
                        status=201 if created else 200)
