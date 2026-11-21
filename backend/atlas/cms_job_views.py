from django.urls import path
from rest_framework.response import Response

from .cms_job_models import AdminJob
from .cms_jobs import get_job, job_data, mutate_job, visible_jobs
from .cms_policy import CMSFailure, policy_lock
from .cms_views import AdminAPIView, expected_version, page, payload, versioned


class JobListView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request):
        with policy_lock():
            rows = visible_jobs(request.user, AdminJob.objects.order_by("-created_at", "-id"))
            status = request.query_params.get("status")
            if status:
                if status not in {"queued", "running", "succeeded", "failed", "cancelled"}:
                    raise CMSFailure("INVALID_QUERY", 400)
                rows = rows.filter(status=status)
            meta, rows = page(request, rows, extra=("status",))
            return Response({**meta, "results": [job_data(row) for row in rows]})


class JobDetailView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, job_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            job = get_job(request.user, job_id)
            return versioned({"job": job_data(job)}, job.version)


class JobActionView(AdminAPIView):
    capability = "cms_enter"

    def post(self, request, job_id, action):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        payload(request, set())
        job = mutate_job(request.user.pk, request.cms_session.pk, job_id, expected_version(request), action, self.request_id)
        return versioned({"job": job_data(job)}, job.version)


urlpatterns = [path("jobs/", JobListView.as_view()), path("jobs/<uuid:job_id>/", JobDetailView.as_view()),
    path("jobs/<uuid:job_id>/<str:action>/", JobActionView.as_view())]
