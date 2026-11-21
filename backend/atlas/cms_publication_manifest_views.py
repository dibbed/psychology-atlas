"""Independent private W16-02 plan endpoints. No public writes."""
from rest_framework.response import Response

from .cms_policy import CMSFailure
from .cms_publication_manifest import dry_run_manifest, freeze_manifest, read_manifest, _receipt
from .cms_views import AdminAPIView


class ManifestDryRunView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, dossier_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        return Response(dry_run_manifest(
            request.user.pk, request.cms_session.pk, dossier_id,
        ))


class ManifestFreezeView(AdminAPIView):
    capability = "cms_enter"

    def post(self, request, dossier_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        plan, created = freeze_manifest(
            request.user.pk, request.cms_session.pk, dossier_id,
            request.data, self.request_id,
        )
        return Response(_receipt(plan, recovered=not created),
                        status=201 if created else 200)


class ManifestReadView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, plan_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        return Response(read_manifest(
            request.user.pk, request.cms_session.pk, plan_id,
        ))
