"""Session/CSRF source API; every write is a persisted, versioned source plan."""
from rest_framework.response import Response

from .cms_policy import CMSFailure, policy_lock, require
from .cms_source_models import SourceHistory, SourcePlan, SourceState
from .cms_sources import (SOURCE_AUDIT_REASONS, SOURCE_FIELDS, _id, _view_snapshot, normalized_pmid,
    apply_source_plan, plan_data, preview_source, require_impact_scope, require_plan_scope,
    source_data, source_fingerprint, source_impact, source_snapshot)
from .cms_views import AdminAPIView, expected_version, page, payload, versioned
from .brain_source_resolution import normalized_doi
from .models import SourceReference, lock_brain_curation
from .search_utils import icontains_any
from django.db import connection


def source_rows(request):
    query = request.query_params.get("q", "").strip()
    doi = request.query_params.get("doi", "").strip()
    pmid = request.query_params.get("pmid", "").strip()
    archived = request.query_params.get("archived", "0")
    if len(query) > 200 or len(doi) > 1000 or len(pmid) > 200 or query and (doi or pmid) or archived not in {"0", "1"}:
        raise CMSFailure("INVALID_QUERY", 400)
    rows = SourceReference.objects.order_by("title", "pk")
    archived_ids = SourceState.objects.filter(archived=True).values("source_pk")
    rows = rows.filter(pk__in=archived_ids) if archived == "1" else rows.exclude(pk__in=archived_ids)
    if query:
        rows = rows.filter(icontains_any(("title",), query))
    if doi:
        doi = normalized_doi(doi)
        if not doi:
            raise CMSFailure("INVALID_QUERY", 400)
        rows = rows.filter(pk__in=[pk for pk, value in rows.values_list("pk", "doi") if value and normalized_doi(value) == doi])
    if pmid:
        pmid = normalized_pmid(pmid)
        rows = rows.filter(pk__in=[pk for pk, value in rows.values_list("pk", "pmid") if value and normalized_pmid(value) == pmid])
    return page(request, rows, extra=("q", "doi", "pmid", "archived"))


def get_source(source_id, lock=False):
    if not _id(source_id):
        raise CMSFailure("NOT_FOUND", 404)
    rows = SourceReference.objects.filter(pk=source_id)
    if lock:
        rows = rows.select_for_update()
    source = rows.first()
    if source is None:
        raise CMSFailure("NOT_FOUND", 404)
    return source


def get_plan(plan_id):
    plan = SourcePlan.objects.filter(pk=plan_id).first()
    if plan is None:
        raise CMSFailure("NOT_FOUND", 404)
    return plan


class SourceListView(AdminAPIView):
    capability = "cms_source_view"

    def get(self, request):
        with policy_lock():
            require(request.user, self.capability)
            meta, rows = source_rows(request)
            return Response({**meta, "results": [source_data(source, request.user, include_impact=False) for source in rows]})


class SourceDetailView(AdminAPIView):
    capability = "cms_source_view"

    def get(self, request, source_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, self.capability)
            lock_brain_curation(connection.alias)
            source = get_source(source_id, lock=True)
            impact = source_impact(source)
            require_impact_scope(request.user, impact)
            data = source_data(source, request.user, impact)
            return versioned({"source": data, "impact": impact, "fingerprint": source_fingerprint(source),
                "successors": impact["successors"], "reason_codes": sorted(SOURCE_AUDIT_REASONS)}, data["version"])


class SourcePreviewView(AdminAPIView):
    capability = "cms_source_preview"

    def post(self, request):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        data = payload(request, {"operation", "source_id", "changes", "mapping", "candidates", "field_choices"})
        plan = preview_source(request.user.pk, request.cms_session.pk, data, self.request_id)
        with policy_lock():
            response = versioned(plan_data(plan, request.user), 1)
        response.status_code = 201
        return response


class SourcePlanView(AdminAPIView):
    capability = "cms_source_view"

    def get(self, request, plan_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            data = plan_data(get_plan(plan_id), request.user)
            return versioned(data, data["version"])


class SourcePlanApplyView(AdminAPIView):
    capability = "cms_source_preview"

    def post(self, request, plan_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        payload(request, set())
        plan = apply_source_plan(request.user.pk, request.cms_session.pk, plan_id, expected_version(request), self.request_id)
        with policy_lock():
            data = plan_data(plan, request.user)
            return versioned(data, data["version"])


class SourceHistoryView(AdminAPIView):
    capability = "cms_source_view"

    def get(self, request, source_id):
        with policy_lock():
            require(request.user, self.capability)
            if not _id(source_id):
                raise CMSFailure("NOT_FOUND", 404)
            source = SourceReference.objects.filter(pk=source_id).first()
            if source is not None:
                require_impact_scope(request.user, source_impact(source))
            elif not SourceState.objects.filter(source_pk=source_id, deleted=True).exists():
                raise CMSFailure("NOT_FOUND", 404)
            rows = SourceHistory.objects.filter(source_pk=source_id).select_related("plan").order_by("-version")
            # Check the entire history before exposing even its count or a past plan's private mapping keys.
            for plan in SourcePlan.objects.filter(pk__in=rows.values("plan_id")):
                require_plan_scope(request.user, plan)
            meta, rows = page(request, rows)
            return Response({**meta, "results": [{"id": row.pk, "source_id": row.source_pk,
                "version": row.version, "plan_id": str(row.plan_id), "operation": row.operation,
                "before": _view_snapshot(row.before), "after": _view_snapshot(row.after),
                "actor_ref": row.actor_ref, "created_at": row.created_at} for row in rows]})


class SourceExportView(AdminAPIView):
    capability = "cms_source_export"

    def get(self, request):
        with policy_lock():
            require(request.user, "cms_source_view")
            require(request.user, self.capability)
            meta, rows = source_rows(request)
            return Response({**meta, "results": [{"id": source.pk, **{name: value for name, value in source_snapshot(source).items()
                if name in SOURCE_FIELDS - {"verification_status"}}} for source in rows]})
