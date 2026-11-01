"""Private bounded domain readers; canonical import and publication never run here."""
import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Count, Q
from rest_framework.response import Response

from .assessment_publication import protected_paths
from .cms_audit import attribution
from .cms_content import canonical_snapshot, dependencies, digest, editable_snapshot, resolve
from .cms_domains import domain_for, entry_tuple, preview_snapshot, required_reference_capabilities
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, effective_permissions, policy_lock, require
from .cms_sessions import current_session
from .cms_views import AdminAPIView, expected_version, page, payload
from .models import DSMCorpus, DSMRecord, DSMRecordRelation, SourceReference


def positive_id(value):
    if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > 19 or not 0 < int(value) < 2**63:
        raise CMSFailure("INVALID_QUERY", 400)
    return int(value)


def corpus_data(corpus):
    return {"id": corpus.pk, "title": corpus.title, "version_name": corpus.version_name,
        "source_sha256": corpus.source_sha256, "is_active": corpus.is_active}


class ContentOptionsView(AdminAPIView):
    capability = "cms_enter"

    def get(self, request, kind):
        with policy_lock():
            if kind == "source":
                require(request.user, "cms_source_view")
                model, fields = SourceReference, ("title", "organization", "doi", "pmid")
            else:
                model = entry_tuple(kind)[0]
                require(request.user, "cms_" + domain_for(kind) + "_view")
                fields = tuple(f.name for f in model._meta.concrete_fields
                    if f.name in {"name_en", "name_fa", "title", "title_en", "title_fa", "master_id", "key", "alias"})
            query = request.query_params.get("q", "").strip()
            if len(query) > 200:
                raise CMSFailure("INVALID_QUERY", 400)
            rows = model.objects.order_by("pk")
            if query:
                condition = Q(pk__in=[])
                for field in fields:
                    condition |= Q(**{field + "__icontains": query})
                if query.isascii() and query.isdigit() and len(query) < 19:
                    condition |= Q(pk=int(query))
                rows = rows.filter(condition)
            meta, rows = page(request, rows, extra=("q",))
            values = []
            for obj in rows:
                label = next((str(getattr(obj, f)) for f in fields if getattr(obj, f)), str(obj.pk))
                if kind == "source":
                    from .cms_sources import source_snapshot
                    version = digest(source_snapshot(obj))
                else:
                    version = digest(canonical_snapshot(kind, obj))
                values.append({"id": obj.pk, "label": label[:500], "version": version})
            return Response({**meta, "results": values})



class TherapyPublicComparePreviewView(AdminAPIView):
    """Exact existing public Therapy comparison projection, accessible from CMS.

    Published canonical records only: no draft or reviewer-only material leaks,
    and public eligibility is never inferred from an editorial approval.
    """
    capability = "cms_therapy_preview"

    def get(self, request):
        if set(request.query_params) != {"left", "right"}:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_therapy_view")
            require(request.user, "cms_therapy_preview")
            left, right = positive_id(request.query_params["left"]), positive_id(request.query_params["right"])
            if left == right:
                raise CMSFailure("INVALID_QUERY", 400)
            from .views import _therapy_detail_queryset
            from .serializers import TherapyDetailSerializer
            rows = list(_therapy_detail_queryset().filter(pk__in=(left, right)))
            indexed = {row.pk: row for row in rows}
            if len(indexed) != 2:
                raise CMSFailure("NOT_FOUND", 404)
            response = {"items": TherapyDetailSerializer([indexed[left], indexed[right]], many=True).data,
                "scope": "current_public_projection_only", "publication_available": False,
                "note": "پیش‌نمایش واقعی مقایسهٔ عمومی فقط از درمان‌های منتشرشده است؛ پیشنویس، تأیید علمی یا تضمین اثربخشی نیست."}
            if len(json.dumps(response, cls=DjangoJSONEncoder, ensure_ascii=False).encode("utf-8")) > 256 * 1024:
                raise CMSFailure("PREVIEW_LIMIT", 400)
            if any(protected_paths(item) for item in response["items"]):
                raise CMSFailure("PROTECTED_MATERIAL", 409)
            return Response(response)

class DSMTreeView(AdminAPIView):
    capability = "cms_dsm_view"

    def get(self, request):
        with policy_lock():
            require(request.user, "cms_dsm_view")
            corpus_id = positive_id(request.query_params.get("corpus"))
            corpus = DSMCorpus.objects.filter(pk=corpus_id).first()
            if corpus is None:
                raise CMSFailure("NOT_FOUND", 404)
            parent = request.query_params.get("parent")
            parent_id = positive_id(parent) if parent is not None else None
            if parent_id is not None and not DSMRecord.objects.filter(pk=parent_id, corpus=corpus).exists():
                raise CMSFailure("NOT_FOUND", 404)
            rows = DSMRecord.objects.filter(corpus=corpus, parent_id=parent_id).annotate(children_count=Count("children"))
            meta, rows = page(request, rows.order_by("sort_index", "master_id", "pk"), extra=("corpus", "parent"))
            result = [{"id": row.pk, "master_id": row.master_id, "name_en": row.name_en,
                "name_fa": row.name_fa, "parent_id": row.parent_id, "linked_disorder_id": row.linked_disorder_id,
                "display_type": row.display_type, "children_count": row.children_count} for row in rows]
            ids = [row["id"] for row in result]
            edges = list(DSMRecordRelation.objects.filter(source_id__in=ids, target_id__in=ids).order_by("pk")
                .values("id", "source_id", "target_id", "relationship_type")[:1001])
            if len(edges) > 1000:
                raise CMSFailure("PREVIEW_LIMIT", 400)
            registry = None
            if "cms_source_view" in effective_permissions(request.user):
                registry = sorted(corpus.source_registry) if isinstance(corpus.source_registry, dict) else []
                if len(registry) > 1000:
                    raise CMSFailure("PREVIEW_LIMIT", 400)
            return Response({**meta, "corpus": corpus_data(corpus), "parent_id": parent_id,
                "results": result, "source_registry_keys": registry,
                "graph": {"scope": "page", "nodes": result, "edges": edges},
                "notice": "PRIVATE_UNPUBLISHED_PREVIEW; PUBLIC_ELIGIBILITY_UNCHANGED"})


def comparison_fields(row):
    excluded = {"id", "corpus", "created_at", "updated_at", "source_payload", "search_text"}
    value = {field.name: getattr(row, field.attname) for field in row._meta.concrete_fields if field.name not in excluded}
    value["parent"] = row.parent.master_id if row.parent_id else None
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


class DSMCompareView(AdminAPIView):
    capability = "cms_dsm_preview"

    def get(self, request):
        with policy_lock():
            require(request.user, "cms_dsm_view")
            require(request.user, "cms_dsm_preview")
            left_id, right_id = (positive_id(request.query_params.get(key)) for key in ("left", "right"))
            if left_id == right_id:
                raise CMSFailure("INVALID_QUERY", 400)
            corpora = {row.pk: row for row in DSMCorpus.objects.filter(pk__in=(left_id, right_id))}
            if len(corpora) != 2:
                raise CMSFailure("NOT_FOUND", 404)
            master_ids = DSMRecord.objects.filter(corpus_id__in=(left_id, right_id)).order_by("master_id").values_list("master_id", flat=True).distinct()
            meta, selected = page(request, master_ids, extra=("left", "right"))
            rows = DSMRecord.objects.filter(corpus_id__in=corpora, master_id__in=list(selected)).select_related("parent").defer("source_payload", "parent__source_payload")
            indexed = {(row.corpus_id, row.master_id): row for row in rows}
            result = []
            for master_id in selected:
                left, right = indexed.get((left_id, master_id)), indexed.get((right_id, master_id))
                a, b = comparison_fields(left) if left else {}, comparison_fields(right) if right else {}
                changed = sorted(key for key in a.keys() | b.keys() if a.get(key) != b.get(key))
                status = "added" if left is None else "removed" if right is None else "changed" if changed else "unchanged"
                named = right or left
                result.append({"master_id": master_id, "status": status, "changed_fields": changed,
                    "left_id": left.pk if left else None, "right_id": right.pk if right else None,
                    "name_en": named.name_en, "name_fa": named.name_fa})
            return Response({**meta, "left": corpus_data(corpora[left_id]), "right": corpus_data(corpora[right_id]),
                "results": result, "counts_scope": "page",
                "raw_archive_changed": corpora[left_id].source_sha256 != corpora[right_id].source_sha256,
                "raw_comparison": "CORPUS_CHECKSUM_ONLY; RAW_PAYLOAD_NOT_LOADED",
                "notice": "PRIVATE_VERSION_COMPARISON; NO_ACTIVATION_OR_CANONICAL_WRITE"})


class DSMGraphView(AdminAPIView):
    capability = "cms_dsm_preview"

    def get(self, request):
        if set(request.query_params) != {"corpus", "record"}:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_dsm_view")
            require(request.user, "cms_dsm_preview")
            corpus_id, record_id = (positive_id(request.query_params.get(key)) for key in ("corpus", "record"))
            focus = DSMRecord.objects.select_related("corpus").filter(pk=record_id, corpus_id=corpus_id).first()
            if focus is None:
                raise CMSFailure("NOT_FOUND", 404)
            children = list(DSMRecord.objects.filter(parent=focus, corpus_id=corpus_id).order_by("sort_index", "pk").values_list("pk", flat=True)[:51])
            relations = list(DSMRecordRelation.objects.filter(Q(source=focus) | Q(target=focus),
                source__corpus_id=corpus_id, target__corpus_id=corpus_id).order_by("pk")
                .values("source_id", "target_id", "relationship_type")[:51])
            ids = {focus.pk, *children[:50]}
            if focus.parent_id and DSMRecord.objects.filter(pk=focus.parent_id, corpus_id=corpus_id).exists():
                ids.add(focus.parent_id)
            ids.update(value for edge in relations[:50] for key, value in edge.items() if key.endswith("_id"))
            ordered = [focus.pk, *sorted(ids - {focus.pk})]
            truncated = len(children) > 50 or len(relations) > 50 or len(ordered) > 100
            indexed = {row.pk: row for row in DSMRecord.objects.filter(pk__in=ordered[:100], corpus_id=corpus_id)
                .only("pk", "master_id", "name_en", "name_fa", "parent_id", "linked_disorder_id", "display_type")}
            nodes = [{"id": row.pk, "master_id": row.master_id, "name_en": row.name_en, "name_fa": row.name_fa,
                "parent_id": row.parent_id, "linked_disorder_id": row.linked_disorder_id, "display_type": row.display_type}
                for key in ordered[:100] if (row := indexed.get(key)) is not None]
            edges = [edge for edge in relations[:50] if edge["source_id"] in indexed and edge["target_id"] in indexed]
            edges += [{"source_id": row["parent_id"], "target_id": row["id"], "relationship_type": "parent_child"}
                for row in nodes if row["parent_id"] in indexed]
            return Response({"corpus": corpus_data(focus.corpus), "focus_id": focus.pk,
                "scope": "same_corpus_neighborhood", "truncated": truncated, "nodes": nodes, "edges": edges,
                "publication_available": False, "notice": "PRIVATE_UNPUBLISHED_GRAPH_PREVIEW"})


class DSMStudyView(AdminAPIView):
    capability = "cms_dsm_preview"

    def get(self, request):
        if set(request.query_params) != {"record"}:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_dsm_view")
            require(request.user, "cms_dsm_preview")
            record_id = positive_id(request.query_params.get("record"))
            obj = DSMRecord.objects.filter(pk=record_id).first()
            if obj is None:
                raise CMSFailure("NOT_FOUND", 404)
            snapshot = editable_snapshot("dsm-record", obj)
            for capability in required_reference_capabilities("dsm-record", snapshot):
                require(request.user, capability)
            candidate = preview_snapshot("dsm-record", snapshot, obj)["candidate"]
            keys = ("key_features", "assessment", "differential", "comorbidity", "course", "management",
                "assessment_tools", "context_considerations", "red_flags", "pitfalls", "exam_tip", "self_test")
            sections = [{"key": key, "value": candidate.get(key, getattr(obj, key))} for key in keys
                if candidate.get(key, getattr(obj, key)) not in (None, "", [], {})]
            response = {"record_id": obj.pk, "corpus_id": obj.corpus_id, "master_id": obj.master_id,
                "name_en": candidate.get("name_en", obj.name_en), "name_fa": candidate.get("name_fa", obj.name_fa),
                "summary": candidate.get("summary", obj.summary), "sections": sections,
                "publication_available": False, "notice": "PRIVATE_UNPUBLISHED_STUDY_PREVIEW"}
            if len(json.dumps(response, cls=DjangoJSONEncoder).encode("utf-8")) > 256 * 1024:
                raise CMSFailure("PREVIEW_LIMIT", 400)
            if protected_paths(response):
                raise CMSFailure("PROTECTED_MATERIAL", 409)
            return Response(response)


class ContentRawView(AdminAPIView):
    capability = "cms_research_raw_read"

    def post(self, request, kind, target_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        data = payload(request, {"purpose", "reason"})
        if data.get("purpose") != "source_review" or data.get("reason") != "RESEARCH_RAW":
            raise CMSFailure("INVALID_REASON", 400)
        field = {"dsm-corpus": "raw_document", "dsm-record": "source_payload"}.get(kind)
        if field is None:
            raise CMSFailure("NOT_FOUND", 404)
        with policy_lock() as policy:
            current_session(request.cms_session.pk, request.user)
            require(request.user, "cms_research_raw_read")
            require(request.user, "cms_dsm_view")
            state, obj = resolve(request.user, kind, target_id, lock=True)
            if state.version != expected_version(request):
                raise CMSFailure("STALE_REVISION", 412)
            if obj is None:
                raise CMSFailure("NOT_FOUND", 404)
            if digest(canonical_snapshot(kind, obj)) != state.canonical_digest:
                raise CMSFailure("CANONICAL_RECONCILIATION_REQUIRED", 409)
            if dependencies(kind, obj, state.current_revision.payload) != state.current_revision.dependency_digest:
                raise CMSFailure("DEPENDENCY_CHANGED", 409)
            from .cms_artifacts import MAX_BYTES, bounded_json
            value = getattr(obj, field)
            encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if len(encoded) > MAX_BYTES:
                raise CMSFailure("PREVIEW_LIMIT", 400)
            if protected_paths(value):
                raise CMSFailure("PROTECTED_MATERIAL", 409)
            try:
                _, value = bounded_json(encoded)
            except CMSFailure as error:
                if str(error.detail.get("code")) == "PROTECTED_CONTENT":
                    raise CMSFailure("PROTECTED_MATERIAL", 409) from error
                raise
            AdminAuditEvent.objects.create(actor=request.user, actor_ref=attribution(request.user.pk),
                action="research.raw", outcome="success", target_kind=kind, target_key=str(state.pk),
                reason="RESEARCH_RAW", policy_version=policy.version, request_id=self.request_id)
            return Response({"kind": kind, "field": field, "raw": value,
                "sha256": hashlib.sha256(encoded).hexdigest(), "serialization": "normalized_json",
                "bytes": len(encoded), "editable": False, "version": state.version})
