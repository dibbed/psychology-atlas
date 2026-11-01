from rest_framework.response import Response
from django.utils import timezone

from .cms_content import (REGISTRY, capability, discard, inspect_proposal, kind_entry, propose, resolve,
    revision_data, safe_payload, scoped_states, scoped_revisions, immutable_metadata, archive_proposal)
from .cms_domains import domain_for, schema_data
from .cms_content_models import ContentState, ContentRevision
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .search_utils import icontains_any
from .cms_views import AdminAPIView, expected_version, page, payload, versioned


class ContentCreateView(AdminAPIView):
    capability = "cms_core_create"

    def get(self, request, kind):
        with policy_lock():
            kind_entry(kind)
            require(request.user, capability(kind, "view"))
            rows = scoped_states(request.user, ContentState.objects.filter(kind=kind)).select_related("current_revision")
            query = request.query_params.get("q", "").strip()
            status = request.query_params.get("status", "")
            ordering = request.query_params.get("sort", "newest")
            if len(query) > 200 or status not in {"", *ContentRevision.Status.values} or ordering not in {"newest", "oldest"}:
                raise CMSFailure("INVALID_QUERY", 400)
            if query:
                rows = rows.filter(icontains_any(("current_revision__payload__name_en", "current_revision__payload__name_fa"), query))
            if status:
                rows = rows.filter(current_revision__status=status)
            rows = rows.order_by("-created_at", "-pk") if ordering == "newest" else rows.order_by("created_at", "pk")
            meta, items = page(request, rows, extra=("q", "status", "sort"))
            return Response({**meta, "results": [revision_data(item) for item in items]})

    def get_permissions(self):
        # Collection reads and draft creation have distinct existing capabilities.
        self.capability = capability(self.kwargs["kind"], "view" if self.request.method in {"GET", "HEAD"} else "create")
        return super().get_permissions()

    def post(self, request, kind):
        data = payload(request, {"payload", "reason"})
        state = propose(request.user.pk, request.cms_session.pk, kind, None, data.get("payload"), None, None,
            data.get("reason", "DRAFT_CREATION"), self.request_id)
        response = versioned(revision_data(state), state.version)
        response.status_code = 201
        return response


class ContentDetailView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, kind, target_id):
        with policy_lock():
            state, obj = resolve(request.user, kind, target_id)
            return versioned(revision_data(state, obj), state.version)


class ContentRevisionView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, kind, target_id):
        with policy_lock():
            state, obj = resolve(request.user, kind, target_id)
            meta, rows = page(request, scoped_revisions(request.user, kind, state.revisions.order_by("-sequence")))
            return versioned({**meta, "domain": domain_for(kind), "immutable_fields": immutable_metadata(kind, obj),
                "results": [{"id": row.pk, "sequence": row.sequence, "status": row.status,
                "base_version": row.base_version, "payload": safe_payload(kind, row.payload), "payload_digest": row.payload_digest,
                "domain": domain_for(kind), "intent": row.intent,
                "dependency_digest": row.dependency_digest, "created_at": row.created_at} for row in rows]}, state.version)

    def post(self, request, kind, target_id):
        data = payload(request, {"payload", "base_digest", "reason"})
        state = propose(request.user.pk, request.cms_session.pk, kind, target_id, data.get("payload"),
            expected_version(request), data.get("base_digest"), data.get("reason", "CONTENT_UPDATE"), self.request_id)
        return versioned(revision_data(state), state.version)


class ContentDiscardView(AdminAPIView):
    capability = "cms_enter"

    def post(self, request, kind, target_id):
        data = payload(request, {"base_digest"})
        state = discard(request.user.pk, request.cms_session.pk, kind, target_id, expected_version(request),
            data.get("base_digest"), self.request_id)
        return versioned(revision_data(state), state.version)


def audit_data(event):
    return {"id": event.pk, "created_at": event.created_at, "actor_ref": event.actor_ref, "actor_type": event.actor_type,
        "action": event.action, "outcome": event.outcome, "target_kind": event.target_kind,
        "target_key": event.target_key, "target_id": event.target_id, "base_revision": event.base_revision,
        "new_revision": event.new_revision, "diff": event.diff, "reason": event.reason,
        "request_id": str(event.request_id), "policy_version": event.policy_version, "error_code": event.error_code}


class DashboardView(AdminAPIView):
    capability = "cms_dashboard"

    def get(self, request):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_dashboard")
            held = effective_permissions(request.user)
            content = None
            if any(capability(kind, "view") in held for kind in REGISTRY):
                scoped = scoped_states(request.user, ContentState.objects.all())
                content = [{"kind": kind, "total": scoped.filter(kind=kind).count(),
                    "drafts": scoped.filter(kind=kind, current_revision__status="draft").count()}
                    for kind in REGISTRY if capability(kind, "view") in held]
            audit = None
            if "cms_audit_view" in held:
                rows = AdminAuditEvent.objects.order_by("-created_at", "-pk")
                audit = {"count": rows.count(), "latest": [audit_data(row) for row in rows[:5]]}
            return Response({"measured_at": timezone.now(), "scope": "authorized_cms_anchors",
                "content": content, "audit": audit, "unavailable": ["publication", "jobs", "rights", "search_telemetry"]})


class AuditView(AdminAPIView):
    capability = "cms_audit_view"

    def get(self, request, event_id=None):
        if event_id is not None:
            event = AdminAuditEvent.objects.filter(pk=event_id).first()
            if event is None:
                raise CMSFailure("NOT_FOUND", 404)
            return Response(audit_data(event))
        meta, rows = page(request, AdminAuditEvent.objects.order_by("-id"))
        return Response({**meta, "results": [audit_data(row) for row in rows]})



class ContentSchemaView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            held = effective_permissions(request.user)
            return Response({"kinds": [schema_data(kind) for kind in REGISTRY
                if capability(kind, "view") in held]})


class ContentValidateView(AdminAPIView):
    capability = "cms_enter"
    action = "validate"

    def post(self, request, kind, target_id):
        kind_entry(kind)
        payload(request, set())
        state, data = inspect_proposal(request.user.pk, request.cms_session.pk, kind, target_id,
            expected_version(request), self.action)
        return versioned(data, state.version)


class ContentPreviewView(ContentValidateView):
    action = "preview"


class ContentArchiveView(AdminAPIView):
    capability = "cms_enter"

    def post(self, request, kind, target_id):
        kind_entry(kind)
        payload(request, set())
        state = archive_proposal(request.user.pk, request.cms_session.pk, kind, target_id,
            expected_version(request), self.request_id)
        return versioned(revision_data(state), state.version)
