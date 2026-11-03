"""Session/CSRF-only private artifacts and metadata-only research endpoints."""
import uuid

from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponse
from django.urls import path
from django.utils import timezone
from django.utils.http import content_disposition_header
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from . import cms_artifacts as service
from .cms_job_models import AdminArtifact
from .cms_policy import CMSFailure, effective_permissions, policy_lock
from .cms_sessions import current_session
from .cms_views import AdminAPIView, expected_version, page, payload, versioned


def no_query(request):
    if request.query_params:
        raise CMSFailure("INVALID_QUERY", 400)


def _integer(value):
    if type(value) is not str or not value.isascii() or not value.isdigit() or len(value) > 19 or not 0 < int(value) < 2**63:
        raise CMSFailure("INVALID_SCOPE", 400)
    return int(value)


class ArtifactListView(AdminAPIView):
    capability = "cms_enter"
    parser_classes = (MultiPartParser,)

    def get(self, request):
        with policy_lock():
            held = effective_permissions(request.user)
            allowed = Q(pk__in=[])
            for kind, domain in service.KINDS.items():
                if domain == "learning":
                    continue
                write = "cms_research_intake" if domain == "research" else "cms_" + domain + "_edit"
                if {"cms_" + domain + "_view", write} <= held:
                    allowed |= Q(kind=kind, domain=domain)
            learning, _ = service.learning_artifact_filter(held)
            allowed |= learning
            from .cms_governance import REGISTRY
            for resource_type, (model, domain, *_) in REGISTRY.items():
                if "cms_" + domain + "_view" in held:
                    allowed |= Q(kind="evidence_json", domain=domain, resource_type=resource_type,
                        resource_id__in=model.objects.values("pk"))
            scope = (request.query_params.get("resource_type"), request.query_params.get("resource_id"),
                request.query_params.get("resource_version"))
            if any(value is not None for value in scope):
                if any(value is None for value in scope):
                    raise CMSFailure("INVALID_SCOPE", 400)
                from .cms_governance import entry, resource_binding
                domain = entry(scope[0])[1]
                if "cms_" + domain + "_view" not in held:
                    raise CMSFailure("NOT_FOUND", 404)
                binding = resource_binding(scope[0], _integer(scope[1]))
                if binding["resource_version"] != scope[2]:
                    raise CMSFailure("NOT_FOUND", 404)
                allowed = Q(kind="evidence_json", domain=domain, resource_type=scope[0],
                    resource_id=binding["resource_id"], resource_version=scope[2])
            rows = AdminArtifact.objects.filter(allowed)
            if "cms_owner" not in held:
                rows = rows.filter(owner=request.user)
            for field in ("kind", "state"):
                value = request.query_params.get(field)
                if value is not None:
                    choices = {*service.KINDS, "evidence_json", "learning_export_json"} if field == "kind" else {"quarantine", "ready", "rejected", "revoked", "expired"}
                    if value not in choices:
                        raise CMSFailure("INVALID_QUERY", 400)
                    if field == "state" and value == "expired":
                        rows = rows.filter(Q(state="expired") | Q(expires_at__lte=timezone.now()) & ~Q(state="revoked"))
                    elif field == "state" and value in {"quarantine", "ready", "rejected"}:
                        rows = rows.filter(state=value, expires_at__gt=timezone.now())
                    else:
                        rows = rows.filter(**{field: value})
            meta, rows = page(request, rows.order_by("created_at", "pk"),
                extra=("kind", "state", "resource_type", "resource_id", "resource_version"))
            return Response({**meta, "results": [service.artifact_data(row) for row in rows]})

    def post(self, request):
        no_query(request)
        allowed = {"file", "kind", "resource_type", "resource_id", "resource_version"}
        if (set(request.data) - allowed or set(request.FILES) != {"file"}
                or any(len(request.data.getlist(key)) != 1 for key in request.data)):
            raise CMSFailure("INVALID_FIELDS", 400)
        resource_id = request.data.get("resource_id")
        artifact = service.upload_artifact(request.user.pk, request.cms_session.pk, request.FILES.get("file"),
            request.data.get("kind"), request.data.get("resource_type"),
            _integer(resource_id) if resource_id is not None else None,
            request.data.get("resource_version"), self.request_id)
        response = versioned({"artifact": service.artifact_data(artifact)}, artifact.version)
        response.status_code = 201
        response["Location"] = "/api/admin/artifacts/" + str(artifact.pk) + "/"
        return response


class ArtifactDetailView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, artifact_id):
        no_query(request)
        with policy_lock():
            artifact = service.get_artifact(request.user, artifact_id)
            return versioned({"artifact": service.artifact_data(artifact)}, artifact.version)


class ArtifactMutationView(AdminAPIView):
    capability = "cms_artifact_upload"
    operation = None

    def post(self, request, artifact_id):
        no_query(request)
        payload(request, set())
        function = service.validate_artifact if self.operation == "validate" else service.revoke_artifact
        artifact = function(request.user.pk, request.cms_session.pk, artifact_id, expected_version(request), self.request_id)
        return versioned({"artifact": service.artifact_data(artifact)}, artifact.version)


class ArtifactCleanupView(AdminAPIView):
    capability = "cms_artifact_upload"

    def post(self, request, artifact_id):
        from .cms_jobs import enqueue_job, job_data
        no_query(request)
        payload(request, set())
        job = enqueue_job(request.user.pk, request.cms_session.pk, artifact_id, uuid.uuid4(), self.request_id,
            kind="artifact_cleanup", expected=expected_version(request))
        response = versioned({"job": job_data(job)}, job.version)
        response.status_code = 202
        response["Location"] = "/api/admin/jobs/" + str(job.pk) + "/"
        return response


class ArtifactDownloadView(AdminAPIView):
    capability = "cms_artifact_download"

    def get(self, request, artifact_id):
        purpose = request.query_params.get("purpose")
        if set(request.query_params) != {"purpose"} or purpose not in service.PURPOSES:
            raise CMSFailure("INVALID_PURPOSE", 400)
        with policy_lock():
            artifact = service.get_artifact(request.user, artifact_id, download=True)
            if (artifact.domain == "learning") != (purpose == "learning_authoring"):
                raise CMSFailure("INVALID_PURPOSE", 400)
        raw = service.artifact_bytes(artifact)
        with policy_lock() as policy:
            actor = User.objects.get(pk=request.user.pk)
            current_session(request.cms_session.pk, actor)
            current = service.get_artifact(actor, artifact_id, download=True, lock=True)
            if (current.version, current.sha256, current.size) != (artifact.version, artifact.sha256, artifact.size):
                raise CMSFailure("ARTIFACT_CHANGED", 409)
            service.audit(actor, "artifact.download", "ARTIFACT_DOWNLOAD", self.request_id, artifact=current, policy=policy)
        response = HttpResponse(raw, content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = content_disposition_header(True, artifact.filename)
        response["X-Content-Type-Options"] = "nosniff"
        response["ETag"] = '"%s"' % artifact.version
        return response


class ResearchIntakeView(AdminAPIView):
    capability = "cms_research_intake"

    def post(self, request):
        from .cms_jobs import enqueue_job, job_data
        no_query(request)
        data = payload(request, {"artifact_id", "request_key"})
        if set(data) != {"artifact_id", "request_key"}:
            raise CMSFailure("INVALID_FIELDS", 400)
        job = enqueue_job(request.user.pk, request.cms_session.pk, data["artifact_id"], data["request_key"], self.request_id)
        response = versioned({"job": job_data(job)}, job.version)
        response.status_code = 202
        response["Location"] = "/api/admin/jobs/" + str(job.pk) + "/"
        return response


class ResearchDatasetsView(AdminAPIView):
    capability = "cms_research_view"

    def get(self, request):
        with policy_lock():
            meta, rows = page(request, service.scoped_datasets(request.user))
            return Response({**meta, "results": [service.dataset_data(row) for row in rows]})


class ResearchRecordsView(AdminAPIView):
    capability = "cms_research_view"

    def get(self, request, dataset_id):
        with policy_lock():
            dataset = service.get_dataset(request.user, dataset_id)
            meta, rows = page(request, dataset.records.defer("payload", "source_ids").order_by("pk"))
            return Response({**meta, "results": [service.record_data(row, request.user) for row in rows]})


class ResearchRecordView(AdminAPIView):
    capability = "cms_research_view"

    def get(self, request, record_id):
        no_query(request)
        with policy_lock():
            record = service.record_data(service.get_record(request.user, record_id), request.user)
            return versioned({"record": record}, record["version"])


class ResearchHistoryView(AdminAPIView):
    capability = "cms_research_view"

    def get(self, request, record_id):
        with policy_lock():
            record = service.get_record(request.user, record_id)
            meta, rows = page(request, record.cms_decisions.order_by("sequence"))
            return Response({**meta, "results": [service.decision_data(row, request.user) for row in rows]})


class ResearchRawView(AdminAPIView):
    capability = "cms_research_raw_read"

    def post(self, request, record_id):
        no_query(request)
        data = payload(request, {"purpose", "reason"})
        return Response({"record": service.raw_preview(request.user.pk, request.cms_session.pk, record_id,
            data.get("purpose"), data.get("reason"), self.request_id)})


class ResearchDecisionView(AdminAPIView):
    capability = "cms_research_view"

    def post(self, request, record_id):
        no_query(request)
        data = payload(request, {"action", "mapping", "reason"})
        if set(data) != {"action", "mapping", "reason"}:
            raise CMSFailure("INVALID_FIELDS", 400)
        service.decide_record(request.user.pk, request.cms_session.pk, record_id, expected_version(request),
            data["action"], data["mapping"], data["reason"], self.request_id)
        with policy_lock():
            record = service.record_data(service.get_record(request.user, record_id), request.user)
            return versioned({"record": record}, record["version"])


urlpatterns = [
    path("artifacts/", ArtifactListView.as_view()),
    path("artifacts/<uuid:artifact_id>/", ArtifactDetailView.as_view()),
    path("artifacts/<uuid:artifact_id>/validate/", ArtifactMutationView.as_view(operation="validate")),
    path("artifacts/<uuid:artifact_id>/revoke/", ArtifactMutationView.as_view(operation="revoke")),
    path("artifacts/<uuid:artifact_id>/cleanup/", ArtifactCleanupView.as_view()),
    path("artifacts/<uuid:artifact_id>/download/", ArtifactDownloadView.as_view()),
    path("research/imports/", ResearchIntakeView.as_view()),
    path("research/datasets/", ResearchDatasetsView.as_view()),
    path("research/datasets/<int:dataset_id>/records/", ResearchRecordsView.as_view()),
    path("research/records/<int:record_id>/", ResearchRecordView.as_view()),
    path("research/records/<int:record_id>/history/", ResearchHistoryView.as_view()),
    path("research/records/<int:record_id>/raw-preview/", ResearchRawView.as_view()),
    path("research/records/<int:record_id>/decisions/", ResearchDecisionView.as_view()),
]
