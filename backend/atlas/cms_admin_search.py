"""P17 first private search: bounded slug-only records, no free-text PII."""
import re

from rest_framework.response import Response

from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_views import AdminAPIView
from .models import ClinicalCase, Flashcard, Quiz, SourceReference


_QUERY = re.compile(r"^[a-z0-9-]{2,80}$")
_RECORDS = (("cases", "clinical_case", ClinicalCase),
            ("learning", "quiz", Quiz), ("learning", "flashcard", Flashcard))


class AdminSearchView(AdminAPIView):
    capability = "cms_search"

    def get(self, request):
        if set(request.query_params) - {"q", "domain", "page", "page_size"}:
            raise CMSFailure("INVALID_QUERY", 400)
        if any(len(request.query_params.getlist(k)) != 1 for k in request.query_params):
            raise CMSFailure("INVALID_QUERY", 400)
        q = request.query_params.get("q", "")
        domain = request.query_params.get("domain", "all")
        if type(q) is not str or not _QUERY.fullmatch(q.lower()) or domain not in {"all", "cases", "learning", "sources"}:
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
            ) if capability in permissions}
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
            rows.sort(key=lambda v: (v["kind"], -v["resource_id"]))
            total = len(rows)
            start = (page - 1) * size
            return Response({
                "scope": "private_slug_index", "query": q, "domain": domain,
                "count": total, "page": page, "page_size": size,
                "results": rows[start:start + size],
                "public_publication_inferred": False,
                "notice": "PRIVATE_AUTHORIZED_SLUGS_ONLY_NO_PRIVATE_TEXT",
            })
