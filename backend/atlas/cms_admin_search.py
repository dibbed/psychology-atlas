"""P17 first private search: bounded slug-only records, no free-text PII."""
import re
import uuid

from rest_framework.response import Response

from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_views import AdminAPIView
from .cms_models import AdminAuditEvent
from .cms_job_models import AdminJob
from .cms_review_models import ReviewTask
from .models import (ClinicalCase, Flashcard, Quiz, ResearchDataset, ResearchRecord, SourceReference,
    ConceptAlias, TherapyAlias, TechniqueAlias, PsychologistAlias, TheoryAlias,
    BrainAnatomicalAlias, BrainNetworkAlias)
from .assessment_models import AssessmentAlias


_QUERY = re.compile(r"^[a-z0-9-]{2,80}$")
_RECORDS = (("cases", "clinical_case", ClinicalCase),
            ("learning", "quiz", Quiz), ("learning", "flashcard", Flashcard))
# Exact ASCII alias discovery only. Never return alias text or parent names.
_ALIASES = (
    ("concept_alias", "concept-alias", "cms_core_view", ConceptAlias),
    ("therapy_alias", "therapy-alias", "cms_therapy_view", TherapyAlias),
    ("technique_alias", "technique-alias", "cms_therapy_view", TechniqueAlias),
    ("psychologist_alias", "psychologist-alias", "cms_history_view", PsychologistAlias),
    ("theory_alias", "theory-alias", "cms_history_view", TheoryAlias),
    ("brain_anatomical_alias", "brain-anatomical-alias", "cms_brain_view", BrainAnatomicalAlias),
    ("brain_network_alias", "brain-network-alias", "cms_brain_view", BrainNetworkAlias),
    ("assessment_alias", "assessment-alias", "cms_assessment_view", AssessmentAlias),
)


class AdminSearchView(AdminAPIView):
    capability = "cms_search"

    def get(self, request):
        if set(request.query_params) - {"q", "domain", "page", "page_size"}:
            raise CMSFailure("INVALID_QUERY", 400)
        if any(len(request.query_params.getlist(k)) != 1 for k in request.query_params):
            raise CMSFailure("INVALID_QUERY", 400)
        q = request.query_params.get("q", "")
        domain = request.query_params.get("domain", "all")
        numeric_id = q.isascii() and q.isdigit() and 1 <= len(q) <= 19
        if (type(q) is not str or domain not in
                {"all", "cases", "learning", "sources", "research", "audit", "tasks", "jobs", "aliases"}
                or not (_QUERY.fullmatch(q.lower()) or (numeric_id and domain in {"all", "audit", "tasks"}))):
            raise CMSFailure("INVALID_QUERY", 400)
        try:
            page = int(request.query_params.get("page", "1"))
            size = int(request.query_params.get("page_size", "30"))
        except (TypeError, ValueError):
            raise CMSFailure("INVALID_QUERY", 400)
        if not 1 <= page <= 10000 or not 1 <= size <= 50:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_search")
            permissions = effective_permissions(request.user)
            available = {name for name, capability in (
                ("cases", "cms_cases_view"),
                ("learning", "cms_learning_view"),
                ("sources", "cms_source_view"),
                ("research", "cms_research_view"),
                ("audit", "cms_audit_view"),
            ) if capability in permissions}
            if any(cap in permissions for _, _, cap, _ in _ALIASES):
                available.add("aliases")
            # Exact operational discovery is owner-only, not a general editorial read.
            if "cms_owner" in permissions:
                available.update({"tasks", "jobs"})
            selected = available if domain == "all" else {domain}
            if not selected or not selected <= available:
                raise CMSFailure("PERMISSION_DENIED", 403)
            rows = []
            for name, kind, model in _RECORDS:
                if name not in selected:
                    continue
                candidates = list(model.objects.filter(slug__icontains=q).order_by("-pk")
                                  .values_list("pk", "slug", "is_active")[:101])
                if len(candidates) > 100:
                    raise CMSFailure("PREVIEW_LIMIT", 400)
                rows.extend({
                    "kind": kind, "resource_id": pk, "slug": slug, "is_active": active,
                } for pk, slug, active in candidates)
            if "sources" in selected:
                # Source titles are only visible under the independent source
                # capability. Citation text, rights evidence and metadata are
                # deliberately excluded from this bounded discovery surface.
                sources = list(SourceReference.objects.filter(title__icontains=q)
                               .order_by("-pk").values_list("pk", "title")[:101])
                if len(sources) > 100:
                    raise CMSFailure("PREVIEW_LIMIT", 400)
                rows.extend({
                    "kind": "source_reference", "resource_id": pk,
                    "slug": str(pk), "label": title[:160],
                } for pk, title in sources)
            if "research" in selected:
                # Staging keys and slugs only, never raw JSON, source filenames,
                # external IDs, translated names, or private research payloads.
                datasets = list(ResearchDataset.objects.filter(key__icontains=q)
                                .order_by("-pk").values_list("pk", "key", "is_active")[:101])
                records = list(ResearchRecord.objects.filter(slug__icontains=q)
                               .order_by("-pk").values_list("pk", "slug")[:101])
                if len(datasets) > 100 or len(records) > 100:
                    raise CMSFailure("PREVIEW_LIMIT", 400)
                rows.extend({"kind": "research_dataset", "resource_id": pk,
                             "slug": slug, "is_active": active}
                            for pk, slug, active in datasets)
                rows.extend({"kind": "research_record", "resource_id": pk,
                             "slug": slug} for pk, slug in records)
            if "audit" in selected and q.isascii() and q.isdigit() and len(q) <= 19:
                # Only an exact numeric audit ID is discoverable; no actor,
                # reason, request, target, or event payload search/return.
                audit_pk = int(q)
                if 0 < audit_pk < 2**63:
                    row = AdminAuditEvent.objects.filter(pk=audit_pk).values_list(
                        "pk", flat=True).first()
                    if row is not None:
                        rows.append({"kind": "audit_event", "resource_id": row,
                                     "slug": str(row)})
            if "aliases" in selected:
                for alias_kind, collection_kind, cap, model in _ALIASES:
                    if cap not in permissions:
                        continue
                    # Exact match only. The content editor independently enforces
                    # its own permission and reference visibility boundary.
                    alias_ids = list(model.objects.filter(text__iexact=q)
                                     .order_by("-pk").values_list("pk", flat=True)[:101])
                    if len(alias_ids) > 100:
                        raise CMSFailure("PREVIEW_LIMIT", 400)
                    rows.extend({"kind": alias_kind, "resource_id": pk,
                                 "slug": str(pk), "collection_kind": collection_kind}
                                for pk in alias_ids)
            if "tasks" in selected and numeric_id:
                task_pk = int(q)
                if 0 < task_pk < 2**63:
                    task = ReviewTask.objects.filter(pk=task_pk).values(
                        "pk", "subject__state__kind", "subject__state_id").first()
                    if task is not None:
                        rows.append({"kind": "review_task", "resource_id": task["pk"],
                                     "slug": str(task["pk"]),
                                     "review_kind": task["subject__state__kind"],
                                     "review_state": str(task["subject__state_id"])})
            if "jobs" in selected:
                try:
                    job_uuid = uuid.UUID(q)
                except (ValueError, AttributeError):
                    job_uuid = None
                if job_uuid is not None and str(job_uuid) == q.lower():
                    job_id = AdminJob.objects.filter(pk=job_uuid).values_list("pk", flat=True).first()
                    if job_id is not None:
                        rows.append({"kind": "admin_job", "resource_id": str(job_id),
                                     "slug": str(job_id)})
            rows.sort(key=lambda v: (v["kind"],
                                     -v["resource_id"] if isinstance(v["resource_id"], int) else 0))
            total = len(rows)
            start = (page - 1) * size
            return Response({
                "scope": "private_slug_index", "query": q, "domain": domain,
                "count": total, "page": page, "page_size": size,
                "results": rows[start:start + size],
                "public_publication_inferred": False,
                "notice": "PRIVATE_AUTHORIZED_SLUGS_ONLY_NO_PRIVATE_TEXT",
            })
