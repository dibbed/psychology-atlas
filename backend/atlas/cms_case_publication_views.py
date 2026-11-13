"""MFA CMS views for source/review/rights-bound CaseRevision publication."""
from rest_framework.response import Response

from .cms_case_editor import revision_etag
from .cms_case_publication import (
    approve_plan, apply_plan, detail_plan, freeze_revision,
    reinstate_plan, review_details, review_revision, withdraw_plan,
)
from .cms_policy import CMSFailure
from .cms_views import AdminAPIView, expected_version, payload
from .models import CaseRevision


class CasePublicationReviewView(AdminAPIView):
    capability = "cms_cases_validate"

    def get_permissions(self):
        self.capability = "cms_cases_validate" if self.request.method in {"GET", "HEAD"} else "cms_enter"
        return super().get_permissions()

    def get(self, request, case_id, revision_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        return Response(review_details(request.user.pk, request.cms_session.pk, case_id, revision_id))

    def post(self, request, case_id, revision_id):
        data = payload(request, {"kind", "outcome", "evidence", "rights", "self_review_ack"})
        row = review_revision(request.user.pk, request.cms_session.pk, case_id, revision_id,
                              expected_version(request), data, self.request_id)
        response = Response({"id": row.pk, "kind": row.kind, "outcome": row.outcome,
                             "revision_id": row.revision_id, "revision_digest": row.revision_digest}, status=201)
        response["ETag"] = f'"{revision_etag(row.revision)}"'
        return response


class CasePublicationFreezeView(AdminAPIView):
    capability = "cms_publication_freeze_cases"

    def post(self, request, case_id, revision_id):
        payload(request, set())
        plan = freeze_revision(request.user.pk, request.cms_session.pk, case_id,
                               revision_id, expected_version(request), self.request_id)
        return Response({"plan_id": str(plan.pk), "status": plan.status,
                         "manifest_digest": plan.manifest_digest, "manifest": plan.manifest}, status=201)


class CasePublicationPlanView(AdminAPIView):
    capability = "cms_publication_verify_cases"

    def get(self, request, plan_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        return Response(detail_plan(request.user.pk, request.cms_session.pk, plan_id))


class CasePublicationApproveView(AdminAPIView):
    capability = "cms_publication_approve_cases"

    def post(self, request, plan_id):
        data = payload(request, {"manifest_digest", "self_review_ack"})
        plan = approve_plan(request.user.pk, request.cms_session.pk, plan_id,
                            data.get("manifest_digest"), data.get("self_review_ack"), self.request_id)
        return Response({"plan_id": str(plan.pk), "status": plan.status,
                         "manifest_digest": plan.manifest_digest})


class CasePublicationApplyView(AdminAPIView):
    capability = "cms_publication_apply_cases"

    def post(self, request, plan_id):
        data = payload(request, {"manifest_digest", "idempotency_key"})
        receipt, created = apply_plan(request.user.pk, request.cms_session.pk, plan_id,
                        data.get("manifest_digest"), data.get("idempotency_key"), self.request_id)
        return Response({"receipt_id": receipt.pk, "status": receipt.event_type,
                         "manifest_digest": receipt.manifest_digest,
                         "case_id": receipt.revision.case_id,
                         "revision_id": receipt.revision_id, "newly_applied": created})


class CasePublicationReinstateView(AdminAPIView):
    capability = "cms_publication_reinstate_cases"

    def post(self, request, plan_id):
        data = payload(request, {"manifest_digest"})
        plan, created = reinstate_plan(request.user.pk, request.cms_session.pk, plan_id,
                                       data.get("manifest_digest"), self.request_id)
        return Response({"plan_id": str(plan.pk), "status": plan.status,
                         "manifest_digest": plan.manifest_digest, "manifest": plan.manifest,
                         "reinstates_plan_id": plan.manifest.get("reinstates_plan_id"),
                         "newly_frozen": created}, status=201 if created else 200)


class CasePublicationWithdrawView(AdminAPIView):
    capability = "cms_publication_withdraw_cases"

    def post(self, request, plan_id):
        data = payload(request, {"manifest_digest", "idempotency_key"})
        receipt, created = withdraw_plan(request.user.pk, request.cms_session.pk, plan_id,
                           data.get("manifest_digest"), data.get("idempotency_key"), self.request_id)
        return Response({"receipt_id": receipt.pk, "status": receipt.event_type,
                         "manifest_digest": receipt.manifest_digest,
                         "case_id": receipt.revision.case_id,
                         "revision_id": receipt.revision_id, "newly_withdrawn": created})
