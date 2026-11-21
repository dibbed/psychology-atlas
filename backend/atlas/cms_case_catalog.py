"""Private case discovery and safe zero-to-one draft creation for P12."""
import re

from django.contrib.auth import get_user_model
from django.db.models import Count
from rest_framework.response import Response

from .cms_case_editor import revision_etag
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_sessions import current_session
from .cms_views import AdminAPIView, page, payload
from .models import CaseRevision, ClinicalCase

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def create_private_case(actor_id, session_id, data, request_id):
    allowed = {"slug", "title", "patient_summary", "educational_objective", "difficulty"}
    if type(data) is not dict or set(data) != allowed:
        raise CMSFailure("INVALID_FIELDS", 400)
    slug, title = data["slug"], data["title"]
    if (type(slug) is not str or len(slug) > 160 or not _SLUG.fullmatch(slug)
            or type(title) is not str or not title.strip() or len(title) > 255):
        raise CMSFailure("INVALID_FIELDS", 400)
    for field in ("patient_summary", "educational_objective"):
        if type(data[field]) is not str or len(data[field]) > 20000:
            raise CMSFailure("INVALID_FIELDS", 400)
    if data["difficulty"] not in ClinicalCase.Difficulty.values:
        raise CMSFailure("INVALID_FIELDS", 400)
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_cases_create")
        require(actor, "cms_cases_view")
        if ClinicalCase.objects.filter(slug=slug).exists():
            raise CMSFailure("CASE_SLUG_EXISTS", 409)
        case = ClinicalCase.objects.create(
            slug=slug, title=title.strip(), patient_summary=data["patient_summary"],
            educational_objective=data["educational_objective"], difficulty=data["difficulty"],
            structure_mode=ClinicalCase.StructureMode.BRANCHING, current_revision=None,
            is_active=False, seed_managed=False,
        )
        draft = CaseRevision.objects.create(
            case=case, version=1, status=CaseRevision.Status.DRAFT,
            title=case.title, patient_summary=case.patient_summary,
            educational_objective=case.educational_objective, difficulty=case.difficulty,
            content_hash="", published_at=None, seed_managed=False,
        )
        AdminAuditEvent.objects.create(
            actor=actor, outcome="success", action="case.draft_created",
            target_kind="clinical-case", target_id=case.pk, request_id=request_id,
            reason="DRAFT_CREATION", diff=["title"], new_revision=draft.version,
        )
        return draft


class CaseCatalogView(AdminAPIView):
    capability = "cms_cases_view"

    def get_permissions(self):
        self.capability = "cms_cases_view" if self.request.method in {"GET", "HEAD"} else "cms_cases_create"
        return super().get_permissions()

    def get(self, request):
        with policy_lock():
            require(request.user, "cms_cases_view")
            meta, rows = page(request, ClinicalCase.objects.all().order_by("-pk"))
            cases = list(rows)
            case_ids = [case.pk for case in cases]
            drafts = CaseRevision.objects.filter(
                case_id__in=case_ids, status=CaseRevision.Status.DRAFT,
            ).order_by("-version", "-pk")
            draft_by_case = {}
            for draft in drafts:
                draft_by_case.setdefault(draft.case_id, draft.pk)
            return Response({
                **meta, "results": [{
                    "case_id": case.pk, "slug": case.slug, "title": case.title,
                    "is_active": case.is_active,
                    "current_revision_id": case.current_revision_id,
                    "draft_revision_id": draft_by_case.get(case.pk),
                    "structure_mode": case.structure_mode,
                } for case in cases],
            })

    def post(self, request):
        data = payload(request, {"slug", "title", "patient_summary",
                                 "educational_objective", "difficulty"})
        draft = create_private_case(
            request.user.pk, request.cms_session.pk, data, self.request_id,
        )
        response = Response({
            "case_id": draft.case_id, "revision_id": draft.pk,
            "status": draft.status, "publication_available": False,
        }, status=201)
        response["ETag"] = f'"{revision_etag(draft)}"'
        return response

class CaseRevisionHistoryView(AdminAPIView):
    capability = "cms_cases_view"

    def get(self, request, case_id):
        with policy_lock():
            require(request.user, "cms_cases_view")
            case = ClinicalCase.objects.filter(pk=case_id).only("pk", "current_revision_id").first()
            if case is None:
                raise CMSFailure("NOT_FOUND", 404)
            queryset = CaseRevision.objects.filter(case=case).annotate(
                attempt_count=Count("attempts", distinct=True),
            ).order_by("-version", "-pk")
            meta, rows = page(request, queryset)
            return Response({
                **meta, "case_id": case_id, "current_revision_id": case.current_revision_id,
                "results": [{
                    "revision_id": revision.pk, "version": revision.version,
                    "status": revision.status, "title": revision.title,
                    "content_hash": revision.content_hash,
                    "published_at": revision.published_at,
                    "entry_step_id": revision.entry_step_id,
                    "rubric_version": revision.rubric_version,
                    "attempt_count": revision.attempt_count,
                } for revision in rows],
            })
