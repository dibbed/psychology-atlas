from django.contrib.auth.models import User
from rest_framework.response import Response

from .cms_audit import POLICY_REASONS, REVIEW_REASONS
from .cms_content import REGISTRY, capability, kind_entry, resolve, scoped_states
from .cms_domains import required_reference_capabilities
from .cms_content_models import ContentRevision, ContentState
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_review import (assign_review, change_review_policy, current_policy, decide_review, latest_tasks,
    policy_data, reopen_review, review_capability, review_data, reviewer_conflict, submit_review)
from .cms_review_models import ReviewDecision, ReviewPolicyRevision, ReviewTask
from .cms_views import AdminAPIView, expected_version, page, payload, versioned
from .models import SourceReference
from .search_utils import icontains_any


class ReviewQueueView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request):
        with policy_lock():
            if not any(capability(kind, "view") in effective_permissions(request.user) for kind in REGISTRY):
                raise CMSFailure("PERMISSION_DENIED")
            kind, status = request.query_params.get("kind", ""), request.query_params.get("status", "")
            query, mine = request.query_params.get("q", "").strip(), request.query_params.get("mine", "")
            if kind and kind not in REGISTRY:
                raise CMSFailure("INVALID_QUERY", 400)
            if status not in {"", *ContentRevision.Status.values} or len(query) > 200 or mine not in {"", "1"}:
                raise CMSFailure("INVALID_QUERY", 400)
            rows = scoped_states(request.user, ContentState.objects.select_related("current_revision")).order_by("-created_at", "-pk")
            if kind:
                rows = rows.filter(kind=kind)
            if status:
                rows = rows.filter(current_revision__status=status)
            if query:
                rows = rows.filter(icontains_any(("current_revision__payload__name_en", "current_revision__payload__name_fa"), query))
            if mine:
                rows = rows.filter(revisions__review_tasks__assignee=request.user,
                    revisions__review_tasks__status="assigned", current_revision__status="in_review").distinct()
            meta, items = page(request, rows, extra=("kind", "status", "q", "mine"))
            results = []
            for item in items:
                _, obj = resolve(request.user, item.kind, str(item.pk))
                results.append(review_data(item, obj))
            return Response({**meta, "results": results, "policy": policy_data(current_policy())})


class ReviewDetailView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, kind, target_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            state, obj = resolve(request.user, kind, target_id)
            return versioned({**review_data(state, obj), "rejection_reasons": sorted(REVIEW_REASONS),
                "evidence_fields": list(kind_entry(kind)[1]().fields)}, state.version)


class ReviewActionView(AdminAPIView):
    capability = "cms_enter"

    def post(self, request, kind, target_id, action):
        expected = expected_version(request)
        args = (request.user.pk, request.cms_session.pk, kind, target_id, expected)
        if action == "submit":
            data = payload(request, {"evidence"})
            state = submit_review(*args, data.get("evidence"), self.request_id)
        elif action == "assign":
            data = payload(request, {"task_id", "task_version", "reviewer_id"})
            state = assign_review(*args, data.get("task_id"), data.get("task_version"), data.get("reviewer_id"), self.request_id)
        elif action == "decide":
            data = payload(request, {"task_id", "task_version", "outcome", "reason", "fields", "self_review_ack"})
            state = decide_review(*args, data.get("task_id"), data.get("task_version"), data.get("outcome"),
                data.get("reason"), data.get("fields", []), data.get("self_review_ack", False), self.request_id)
        elif action == "reopen":
            payload(request, set())
            state = reopen_review(*args, self.request_id)
        else:
            raise CMSFailure("NOT_FOUND", 404)
        with policy_lock():
            # A competing write can follow the commit; always return its actual version with its snapshot.
            state, obj = resolve(request.user, kind, str(state.pk))
            return versioned(review_data(state, obj), state.version)


class ReviewHistoryView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, kind, target_id):
        with policy_lock():
            state, _ = resolve(request.user, kind, target_id)
            meta, rows = page(request, ReviewDecision.objects.filter(task__subject__state=state).select_related("task").order_by("-pk"))
            return versioned({**meta, "results": [{"id": row.pk, "review_type": row.task.review_type,
                "subject_revision": row.task.subject_id, "revision": row.revision_id, "outcome": row.outcome,
                "actor_ref": row.actor_ref, "assignee_ref": row.assignee_ref, "reason": row.reason,
                "fields": row.fields, "evidence": row.evidence, "revision_hash": row.revision_hash,
                "dependency_digest": row.dependency_digest, "policy_version": row.policy_version,
                "policy_mode": row.policy_mode, "self_review": row.self_review, "supersedes": row.supersedes_id,
                "created_at": row.created_at} for row in rows]}, state.version)


class ReviewReviewerView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, kind, target_id):
        with policy_lock():
            state, _ = resolve(request.user, kind, target_id)
            review_type = request.query_params.get("review_type")
            require(request.user, review_capability(review_type, kind))
            task = next((task for task in latest_tasks(state) if task.review_type == review_type), None)
            if task is None:
                raise CMSFailure("NOT_FOUND", 404)
            users = User.objects.filter(is_active=True, is_staff=True).order_by("username", "pk")
            # Eligibility is authority, not a group label; this list is bounded by the normal paging contract.
            eligible = []
            for user in users:
                if {"cms_enter", capability(kind, "view"), review_capability(review_type, kind),
                        *required_reference_capabilities(kind, state.current_revision.payload)} <= effective_permissions(user):
                    eligible.append(user.pk)
            meta, users = page(request, users.filter(pk__in=eligible), extra=("review_type",))
            results = []
            for user in users:
                conflict = None
                try:
                    reviewer_conflict(user, task, current_policy())
                except CMSFailure as error:
                    conflict = str(error.detail["code"])
                results.append({"id": user.pk, "username": user.username, "conflict": conflict})
            return Response({**meta, "results": results})


class ReviewSourcesView(AdminAPIView):
    capability = "cms_source_view"

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if len(query) > 200:
            raise CMSFailure("INVALID_QUERY", 400)
        rows = SourceReference.objects.order_by("title", "pk")
        if query:
            rows = rows.filter(icontains_any(("title", "doi", "pmid"), query))
        meta, sources = page(request, rows, extra=("q",))
        return Response({**meta, "results": [{"id": source.pk, "title": source.title,
            "doi": source.doi, "pmid": source.pmid, "verification_status": source.verification_status} for source in sources]})


class ReviewPolicyView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request):
        with policy_lock():
            if not any(capability(kind, "view") in effective_permissions(request.user) for kind in REGISTRY):
                raise CMSFailure("PERMISSION_DENIED")
            meta, history = page(request, ReviewPolicyRevision.objects.order_by("-version"))
            policy = current_policy()
            return versioned({**policy_data(policy), "reason_codes": sorted(POLICY_REASONS),
                "history": {**meta, "results": [{"version": item.version, "previous_mode": item.previous_mode,
                    "mode": item.mode, "reason": item.reason, "created_at": item.created_at} for item in history]}}, policy.version)

    def post(self, request):
        data = payload(request, {"mode", "reason"})
        policy = change_review_policy(request.user.pk, request.cms_session.pk, expected_version(request), data, self.request_id)
        return versioned(policy_data(policy), policy.version)
