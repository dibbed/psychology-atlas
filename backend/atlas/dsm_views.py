from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .dsm_serializers import DSMRecordBriefSerializer, DSMRecordDetailSerializer
from .models import DSMCorpus, DSMRecord, DSMRecordRelation
from .pagination import AtlasPagination
from .search_utils import icontains_any


def _active_corpus():
    return DSMCorpus.objects.filter(is_active=True).order_by("-version_date", "-id").first()


@api_view(["GET"])
def dsm_overview(request):
    corpus = _active_corpus()
    if not corpus:
        return Response({"detail": "DSM MASTER هنوز وارد نشده است."}, status=404)

    records = corpus.records.filter(is_active=True)
    type_counts = {
        row["display_type"]: row["count"]
        for row in records.values("display_type").annotate(count=Count("id")).order_by("display_type")
    }
    root_counts = {
        row["root_section"]: row["count"]
        for row in records.values("root_section").annotate(count=Count("id")).order_by("root_section")
    }
    chapters = list(
        records.filter(chapter_number__isnull=False)
        .values("chapter_number", "chapter_name_fa", "chapter_name_en")
        .annotate(
            record_count=Count("id"),
            diagnosis_count=Count("id", filter=Q(display_type=DSMRecord.DisplayType.DIAGNOSIS)),
        )
        .order_by("chapter_number")
    )

    return Response({
        "corpus": {
            "key": corpus.key,
            "title": corpus.title,
            "version_name": corpus.version_name,
            "version_date": corpus.version_date,
            "language": corpus.language,
            "purpose": corpus.purpose,
            "copyright_note": corpus.copyright_note,
            "clinical_note": corpus.clinical_note,
            "source_filename": corpus.source_filename,
            "source_sha256": corpus.source_sha256,
        },
        "counts": {
            "records": records.count(),
            "linked_atlas_disorders": records.filter(linked_disorder__isnull=False).count(),
            "types": type_counts,
            "roots": root_counts,
        },
        "chapters": chapters,
        "stats": corpus.stats,
        "official_status": corpus.official_status,
        "source_registry": corpus.source_registry,
        "quality_audit": corpus.quality_audit,
        "study_guide": corpus.study_guide,
        "urgent_warnings": corpus.urgent_warnings,
        "cultural_note": corpus.cultural_note,
        "periodic_review": corpus.periodic_review,
        "release_updates": corpus.release_updates,
        "health_check": corpus.health_check,
    })


@api_view(["GET"])
def dsm_metadata(request):
    corpus = _active_corpus()
    if not corpus:
        return Response({"detail": "DSM MASTER هنوز وارد نشده است."}, status=404)
    return Response({
        "key": corpus.key,
        "metadata": corpus.metadata,
    })


class DSMRecordListView(generics.ListAPIView):
    serializer_class = DSMRecordBriefSerializer
    pagination_class = AtlasPagination

    def get_queryset(self):
        corpus = _active_corpus()
        if not corpus:
            return DSMRecord.objects.none()

        qs = corpus.records.filter(is_active=True).select_related("linked_disorder", "linked_disorder__category")
        q = self.request.query_params.get("q", "").strip()
        display_type = self.request.query_params.get("type", "").strip()
        root = self.request.query_params.get("root", "").strip()
        chapter = self.request.query_params.get("chapter", "").strip()
        linked = self.request.query_params.get("linked", "").strip().lower()

        if q:
            qs = qs.filter(icontains_any(
                (
                    "master_id",
                    "name_fa",
                    "name_en",
                    "classification_status",
                    "chapter_name_fa",
                    "chapter_name_en",
                    "group_name",
                    "summary",
                    "search_text",
                ),
                q,
            ))
        if display_type and display_type in DSMRecord.DisplayType.values:
            qs = qs.filter(display_type=display_type)
        if root:
            qs = qs.filter(root_section=root)
        if chapter:
            try:
                qs = qs.filter(chapter_number=int(chapter))
            except ValueError:
                pass
        if linked == "true":
            qs = qs.filter(linked_disorder__isnull=False)
        elif linked == "false":
            qs = qs.filter(linked_disorder__isnull=True)

        ordering = self.request.query_params.get("ordering", "structure")
        if ordering == "name":
            return qs.order_by("name_fa", "name_en", "sort_index")
        return qs.order_by("sort_index", "master_id")


class DSMRecordDetailView(generics.RetrieveAPIView):
    serializer_class = DSMRecordDetailSerializer
    lookup_field = "master_id"
    lookup_url_kwarg = "master_id"

    def get_queryset(self):
        corpus = _active_corpus()
        if not corpus:
            return DSMRecord.objects.none()
        return (
            corpus.records.filter(is_active=True)
            .select_related("corpus", "parent", "linked_disorder", "linked_disorder__category")
            .prefetch_related(
                "children__linked_disorder__category",
                "outgoing_dsm_relations__target__linked_disorder__category",
                "incoming_dsm_relations__source__linked_disorder__category",
            )
        )


@api_view(["GET"])
def dsm_record_by_disorder(request, slug):
    corpus = _active_corpus()
    if not corpus:
        return Response({"detail": "DSM MASTER هنوز وارد نشده است."}, status=404)
    record = get_object_or_404(
        corpus.records.select_related("corpus", "parent", "linked_disorder", "linked_disorder__category"),
        linked_disorder__slug=slug,
        is_active=True,
    )
    detailed = request.query_params.get("detail", "").strip().lower() in {"1", "true", "yes"}
    if detailed:
        record = (
            corpus.records.filter(pk=record.pk)
            .select_related("corpus", "parent", "linked_disorder", "linked_disorder__category")
            .prefetch_related(
                "children__linked_disorder__category",
                "outgoing_dsm_relations__target__linked_disorder__category",
                "incoming_dsm_relations__source__linked_disorder__category",
            )
            .get()
        )
        return Response(DSMRecordDetailSerializer(record).data)
    return Response(DSMRecordBriefSerializer(record).data)


@api_view(["GET"])
def dsm_study_kit(request):
    corpus = _active_corpus()
    if not corpus:
        return Response({"detail": "DSM MASTER هنوز وارد نشده است."}, status=404)
    records = list(corpus.records.filter(is_active=True).only("self_test", "exam_tip", "display_type"))
    glossary = corpus.metadata.get("واژه‌نامه_مطالعاتی", {})
    return Response({
        "glossary": glossary if isinstance(glossary, dict) else {},
        "study_guide": corpus.study_guide,
        "cultural_note": corpus.cultural_note,
        "urgent_warnings": corpus.urgent_warnings,
        "stats": {
            "records": len(records),
            "diagnoses": sum(1 for row in records if row.display_type == DSMRecord.DisplayType.DIAGNOSIS),
            "self_test_questions": sum(len(row.self_test) for row in records if isinstance(row.self_test, list)),
            "exam_tips": sum(1 for row in records if row.exam_tip),
            "glossary_terms": len(glossary) if isinstance(glossary, dict) else 0,
        },
    })


@api_view(["GET"])
def dsm_graph(request):
    corpus = _active_corpus()
    if not corpus:
        return Response({"detail": "DSM MASTER هنوز وارد نشده است."}, status=404)
    records = list(
        corpus.records.filter(is_active=True)
        .select_related("linked_disorder")
        .order_by("sort_index", "master_id")
    )
    record_ids = {row.id for row in records}
    record_by_id = {row.id: row for row in records}
    relations = list(
        DSMRecordRelation.objects.filter(source_id__in=record_ids, target_id__in=record_ids)
        .select_related("source", "target")
        .order_by("source__sort_index", "target__sort_index", "relationship_type")
    )
    degree = {row.master_id: 0 for row in records}
    edges = []
    for row in records:
        if row.parent_id and row.parent_id in record_ids:
            parent = record_by_id.get(row.parent_id)
            if parent:
                edges.append({"source": parent.master_id, "target": row.master_id, "kind": "hierarchy", "explanation": "رابطه ساختاری parent/child در MASTER."})
                degree[parent.master_id] += 1
                degree[row.master_id] += 1
    for relation in relations:
        edges.append({
            "source": relation.source.master_id,
            "target": relation.target.master_id,
            "kind": relation.relationship_type,
            "explanation": relation.explanation,
        })
        degree[relation.source.master_id] += 1
        degree[relation.target.master_id] += 1
    return Response({
        "meta": {
            "node_count": len(records),
            "edge_count": len(edges),
            "relation_counts": {
                "hierarchy": sum(1 for edge in edges if edge["kind"] == "hierarchy"),
                "nearby": sum(1 for edge in edges if edge["kind"] == DSMRecordRelation.Kind.NEARBY),
                "differential": sum(1 for edge in edges if edge["kind"] == DSMRecordRelation.Kind.DIFFERENTIAL),
            },
        },
        "nodes": [
            {
                "id": row.master_id,
                "label": row.name_fa or row.name_en or row.master_id,
                "name_en": row.name_en,
                "display_type": row.display_type,
                "classification_status": row.classification_status,
                "chapter_number": row.chapter_number,
                "chapter_name_fa": row.chapter_name_fa,
                "group_name": row.group_name,
                "summary": row.summary,
                "degree": degree[row.master_id],
                "href": f"/dsm/{row.master_id}",
                "linked_disorder_slug": row.linked_disorder.slug if row.linked_disorder_id else None,
            }
            for row in records
        ],
        "edges": edges,
    })
