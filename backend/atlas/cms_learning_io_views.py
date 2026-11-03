"""Scoped enqueue and bounded selection; no synchronous browser persistence."""
from django.urls import path
from rest_framework.parsers import BaseParser
from rest_framework.response import Response

from . import cms_learning_io as service
from .cms_jobs import enqueue_job, job_data
from .cms_policy import CMSFailure, policy_lock
from .cms_case_editor import revision_etag
from .cms_views import AdminAPIView, page, payload, versioned


def queued(job):
    response = versioned({"job": job_data(job)}, job.version)
    response.status_code = 202
    response["Location"] = f"/api/admin/jobs/{job.pk}/"
    return response


class LearningTransferParser(BaseParser):
    media_type = "application/json"

    def parse(self, stream, media_type=None, parser_context=None):
        return service._json(stream.read(service.MAX_BYTES + 1))


class LearningTransferSelectionView(AdminAPIView):
    capability = "cms_learning_export"

    def get(self, request):
        if len(request.query_params.getlist("kind")) != 1:
            raise CMSFailure("INVALID_QUERY", 400)
        kind = request.query_params["kind"]
        with policy_lock():
            service.require_transfer(request.user, "learning_export")
            label = "title" if kind == "quiz" else "pk" if kind == "daily" else "slug"
            meta, rows = page(request, service.candidates(kind).only("pk", "updated_at", label).order_by("pk"), extra=("kind",))
            return Response({**meta, "results": [{"kind": kind, "resource_id": row.pk,
                "label": getattr(row, "title", None) or getattr(row, "slug", None) or f"#{row.pk}",
                "etag": f'"{revision_etag(row)}"'} for row in rows]})


class LearningImportView(AdminAPIView):
    capability = "cms_learning_create"
    parser_classes = (LearningTransferParser,)

    def post(self, request):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        data = payload(request, {"artifact_id", "request_key"})
        if set(data) != {"artifact_id", "request_key"} or any(type(value) is not str for value in data.values()):
            raise CMSFailure("INVALID_FIELDS", 400)
        job = enqueue_job(request.user.pk, request.cms_session.pk, data["artifact_id"], data["request_key"],
                          self.request_id, kind="learning_import")
        return queued(job)


class LearningExportView(AdminAPIView):
    capability = "cms_learning_export"
    parser_classes = (LearningTransferParser,)

    def post(self, request):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        return queued(service.enqueue_export(request.user.pk, request.cms_session.pk,
            payload(request, {"items", "request_key"}), self.request_id))


urlpatterns = [path("selection/", LearningTransferSelectionView.as_view()),
               path("import/", LearningImportView.as_view()), path("export/", LearningExportView.as_view())]
