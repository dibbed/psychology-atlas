"""Operational governance API; parent includes this closed route namespace."""
from django.contrib.auth.models import User
from django.urls import path
from rest_framework.response import Response

from .cms_governance import (APPROVAL_REASONS, COMMON, COMPUTED_STATUSES, REGISTRY, REVIEW_REASONS,
    RIGHTS_FIELDS, TERM_FIELDS, WORKFLOW_STATUSES, conflict, create_governance, decision_caps,
    entry, mutate_governance, record_data, resolve, resource_binding)
from .cms_governance_models import GovernanceDecision, GovernanceRecord
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_review import current_policy
from .cms_sessions import current_session
from .cms_views import AdminAPIView, expected_version, page, payload, versioned
from .models import SourceReference
from .search_utils import icontains_any


def query_id(value):
    if type(value) is not str or not value.isascii() or not value.isdigit() or len(value) > 19 or not 0 < int(value) < 2**63:
        raise CMSFailure("INVALID_QUERY", 400)
    return int(value)


def read_context(request):
    current_session(request.cms_session.pk, request.user)
    require(request.user, "cms_enter")


def detail_data(record):
    policy = current_policy()
    return {"record": record_data(record), "policy": {"mode": policy.mode, "version": policy.version},
        "reason_codes": {"approve": [APPROVAL_REASONS[record.kind]], "reject": sorted(REVIEW_REASONS),
            "revoke": sorted(REVIEW_REASONS) if record.kind == "rights" else []}}


class GovernanceResourcesView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request):
        with policy_lock():
            read_context(request)
            resource_type = request.query_params.get("resource_type")
            model, domain, en, fa, _, _ = entry(resource_type)
            if "cms_" + domain + "_view" not in effective_permissions(request.user):
                raise CMSFailure("NOT_FOUND", 404)
            query = request.query_params.get("q", "").strip()
            if len(query) > 200:
                raise CMSFailure("INVALID_QUERY", 400)
            rows = model.objects.order_by("pk")
            if query:
                rows = rows.filter(icontains_any(tuple(f for f in (en, fa) if f), query))
            meta, rows = page(request, rows, extra=("resource_type", "q"))
            types = [{"resource_type": t, "domain": e[1]} for t, e in REGISTRY.items() if "cms_" + e[1] + "_view" in effective_permissions(request.user)]
            return Response({**meta, "results": [resource_binding(resource_type, row.pk) for row in rows], "resource_types": types})


class GovernanceEvidenceView(AdminAPIView):
    capability = "cms_source_view"

    def get(self, request):
        with policy_lock():
            read_context(request)
            require(request.user, "cms_source_view")
            query = request.query_params.get("q", "").strip()
            if len(query) > 200:
                raise CMSFailure("INVALID_QUERY", 400)
            rows = SourceReference.objects.order_by("pk")
            if query:
                rows = rows.filter(icontains_any(("title", "doi", "pmid"), query))
            meta, rows = page(request, rows, extra=("q",))
            return Response({**meta, "results": [{"id": s.pk, "title": s.title, "url": s.url,
                "doi": s.doi, "pmid": s.pmid, "verification_status": s.verification_status} for s in rows]})


class GovernanceListView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, kind):
        with policy_lock():
            read_context(request)
            domains = [domain for domain in {e[1] for e in REGISTRY.values()} if "cms_" + domain + "_view" in effective_permissions(request.user)]
            rows = GovernanceRecord.objects.filter(kind=kind, domain__in=domains).select_related("current_revision", "assignee").order_by("-created_at", "-pk")
            resource_type = request.query_params.get("resource_type", "")
            status = request.query_params.get("status", "")
            computed = request.query_params.get("computed_status", "")
            query, mine = request.query_params.get("q", "").strip(), request.query_params.get("mine", "")
            if (resource_type and resource_type not in REGISTRY or status and status not in WORKFLOW_STATUSES
                    or computed and computed not in COMPUTED_STATUSES or mine not in {"", "1"} or len(query) > 200):
                raise CMSFailure("INVALID_QUERY", 400)
            if resource_type:
                rows = rows.filter(resource_type=resource_type)
            if "resource_id" in request.query_params:
                if not resource_type:
                    raise CMSFailure("INVALID_QUERY", 400)
                rows = rows.filter(resource_id=query_id(request.query_params["resource_id"]))
            if status:
                rows = rows.filter(status=status)
            if mine:
                rows = rows.filter(assignee=request.user)
            if query:
                fields = ("current_revision__payload__name_en", "current_revision__payload__name_fa") if kind == "terminology" else ("current_revision__payload__rightsholder",)
                rows = rows.filter(icontains_any(fields, query))
            if computed:
                from .cms_governance import eligibility
                # Evaluate every authorized candidate before count/paging; never truncate the overdue queue.
                matching = [r.pk for r in rows.iterator(chunk_size=100) if eligibility(r)["status"] == computed]
                rows = rows.filter(pk__in=matching)
            meta, rows = page(request, rows, extra=("resource_type", "resource_id", "status", "computed_status", "q", "mine"))
            return Response({**meta, "results": [record_data(row) for row in rows]})

    def post(self, request, kind):
        data = payload(request, COMMON | (RIGHTS_FIELDS if kind == "rights" else TERM_FIELDS))
        record = create_governance(request.user.pk, request.cms_session.pk, kind, data, self.request_id)
        with policy_lock():
            read_context(request)
            record = resolve(request.user, kind, record.pk)
            response = versioned(detail_data(record), record.version)
            response.status_code = 201
            return response


class GovernanceDetailView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, kind, record_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            read_context(request)
            record = resolve(request.user, kind, record_id)
            return versioned(detail_data(record), record.version)

    def patch(self, request, kind, record_id):
        record = mutate_governance(request.user.pk, request.cms_session.pk, kind, record_id,
            expected_version(request), "update", request.data, self.request_id)
        with policy_lock():
            read_context(request)
            record = resolve(request.user, kind, record.pk)
            return versioned(detail_data(record), record.version)


class GovernanceActionView(AdminAPIView):
    capability = "cms_enter"

    def post(self, request, kind, record_id, action):
        record = mutate_governance(request.user.pk, request.cms_session.pk, kind, record_id,
            expected_version(request), action, request.data, self.request_id)
        with policy_lock():
            read_context(request)
            record = resolve(request.user, kind, record.pk)
            return versioned(detail_data(record), record.version)


class GovernanceHistoryView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, kind, record_id):
        with policy_lock():
            read_context(request)
            record = resolve(request.user, kind, record_id)
            meta, rows = page(request, record.revisions.order_by("-sequence"))
            results = []
            for revision in rows:
                decisions = GovernanceDecision.objects.filter(revision=revision).order_by("pk")
                results.append({"revision": revision.pk, "version": revision.sequence, "action": revision.action,
                    "status": revision.status, "reason": revision.reason, "payload": revision.payload,
                    "actor_ref": revision.actor_ref, "assignee_ref": revision.assignee_ref, "payload_digest": revision.payload_digest,
                    "resource_digest": revision.resource_digest, "dependency_digest": revision.dependency_digest,
                    "policy_version": revision.policy_version, "policy_mode": revision.policy_mode, "created_at": revision.created_at,
                    "decisions": [{"id": d.pk, "outcome": d.outcome, "reason": d.reason, "self_review": d.self_review,
                        "actor_ref": d.actor_ref, "assignee_ref": d.assignee_ref, "revision_hash": d.revision_hash,
                        "dependency_digest": d.dependency_digest, "supersedes": d.supersedes_id} for d in decisions]})
            return versioned({**meta, "results": results}, record.version)


class GovernanceReviewersView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, kind, record_id):
        with policy_lock():
            read_context(request)
            record = resolve(request.user, kind, record_id)
            for cap in decision_caps(record):
                require(request.user, cap)
            candidates = []
            for user in User.objects.filter(is_active=True, is_staff=True).order_by("username", "pk"):
                if decision_caps(record) <= effective_permissions(user):
                    candidates.append(user)
            meta, users = page(request, candidates)
            result = []
            for user in users:
                try:
                    conflict(user, record, current_policy())
                    blockers = []
                except CMSFailure as error:
                    blockers = [str(error.detail["code"])]
                result.append({"id": user.pk, "username": user.username, "conflicts": blockers})
            return versioned({**meta, "results": result}, record.version)


urlpatterns = [path("resources/", GovernanceResourcesView.as_view()), path("evidence/", GovernanceEvidenceView.as_view())]
for kind in ("rights", "terminology"):
    urlpatterns += [
        path(kind + "/", GovernanceListView.as_view(), {"kind": kind}),
        path(kind + "/<uuid:record_id>/", GovernanceDetailView.as_view(), {"kind": kind}),
        path(kind + "/<uuid:record_id>/history/", GovernanceHistoryView.as_view(), {"kind": kind}),
        path(kind + "/<uuid:record_id>/reviewers/", GovernanceReviewersView.as_view(), {"kind": kind}),
    ]
    for action in ("assign", "decide", "reopen", *(("revoke",) if kind == "rights" else ())):
        urlpatterns.append(path(kind + "/<uuid:record_id>/" + action + "/", GovernanceActionView.as_view(), {"kind": kind, "action": action}))
