from collections import deque
from collections.abc import Mapping

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .learning import record_activity
from .models import (
    CognitiveDistortionPracticeAttempt,
    CognitiveDistortionPracticeItem,
    Concept,
    ConceptRelationship,
    ConceptSymptom,
    Disorder,
    DisorderConcept,
    DisorderSymptom,
    DSMRecord,
    StudyActivity,
    UserConceptProgress,
)
from .serializers import DisorderListSerializer
from .v3_serializers import ConceptCatalogSerializer, ConceptListSerializer
from .v3_views import _linked_dsm_nearby_edges


def _object_payload(request):
    if not isinstance(request.data, Mapping):
        raise ValidationError({"detail": "بدنه درخواست باید یک شیء JSON باشد."})
    return request.data


def _positive_int(value, *, field):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValidationError({field: "شناسه معتبر نیست."})
    if isinstance(value, str) and not value.isdigit():
        raise ValidationError({field: "شناسه معتبر نیست."})
    result = int(value)
    if result <= 0:
        raise ValidationError({field: "شناسه معتبر نیست."})
    return result


def _build_atlas_graph():
    concepts = list(Concept.objects.filter(is_active=True).order_by("name_en"))
    disorders = list(Disorder.objects.filter(is_active=True).select_related("category").order_by("name_en"))
    concept_ids = {concept.id for concept in concepts}
    disorder_ids = {disorder.id for disorder in disorders}
    disorder_id_by_slug = {disorder.slug: disorder.id for disorder in disorders}

    nodes = [
        {
            "id": f"concept:{concept.slug}",
            "type": "concept",
            "slug": concept.slug,
            "label": concept.name_fa or concept.name_en,
            "name_en": concept.name_en,
            "name_fa": concept.name_fa,
            "kind": concept.kind,
            "group": concept.get_kind_display(),
            "domain": concept.domain,
            "domain_label": concept.get_domain_display(),
            "subtype": concept.subtype,
            "summary": concept.simple_definition,
            "href": f"/concepts/{concept.slug}",
        }
        for concept in concepts
    ]
    edges = []

    for relation in (
        ConceptRelationship.objects.filter(
            source_concept_id__in=concept_ids,
            target_concept_id__in=concept_ids,
        )
        .select_related("source_concept", "target_concept")
        .order_by("id")
    ):
        edges.append({
            "source": f"concept:{relation.source_concept.slug}",
            "target": f"concept:{relation.target_concept.slug}",
            "kind": relation.relationship_type,
            "explanation": relation.explanation,
        })

    for link in (
        DisorderConcept.objects.filter(concept_id__in=concept_ids, disorder_id__in=disorder_ids)
        .select_related("concept", "disorder")
        .order_by("disorder_id", "sort_order", "id")
    ):
        edges.append({
            "source": f"disorder:{link.disorder.slug}",
            "target": f"concept:{link.concept.slug}",
            "kind": link.role,
            "explanation": link.explanation,
        })

    symptom_by_id = {}
    for link in (
        ConceptSymptom.objects.filter(concept__is_active=True)
        .select_related("concept", "symptom")
        .order_by("concept_id", "sort_order", "id")
    ):
        symptom_by_id[link.symptom_id] = link.symptom
        edges.append({
            "source": f"concept:{link.concept.slug}",
            "target": f"symptom:{link.symptom.slug}",
            "kind": f"concept_symptom_{link.relationship_type}",
            "explanation": link.explanation,
        })

    for link in (
        DisorderSymptom.objects.filter(disorder_id__in=disorder_ids)
        .select_related("disorder", "symptom")
        .order_by("disorder_id", "sort_order", "id")
    ):
        symptom_by_id[link.symptom_id] = link.symptom
        edges.append({
            "source": f"disorder:{link.disorder.slug}",
            "target": f"symptom:{link.symptom.slug}",
            "kind": f"symptom_{link.prominence}",
            "explanation": link.note,
        })

    for source, target, _relation in _linked_dsm_nearby_edges():
        if source.id not in disorder_ids or target.id not in disorder_ids:
            continue
        edges.append({
            "source": f"disorder:{source.slug}",
            "target": f"disorder:{target.slug}",
            "kind": "dsm_nearby",
            "explanation": "در DSM MASTER به‌عنوان عنوان نزدیک یا ارجاع مرتبط ثبت شده است.",
        })

    nodes.extend({
        "id": f"disorder:{disorder.slug}",
        "type": "disorder",
        "slug": disorder.slug,
        "label": disorder.name_fa or disorder.name_en,
        "name_en": disorder.name_en,
        "name_fa": disorder.name_fa,
        "kind": disorder.category.slug,
        "group": disorder.category.name_fa or disorder.category.name_en,
        "category": disorder.category.slug,
        "summary": disorder.short_description,
        "href": f"/disorders/{disorder.slug}",
    } for disorder in disorders)

    dsm_by_disorder = {
        row.linked_disorder_id: row
        for row in DSMRecord.objects.filter(
            corpus__is_active=True,
            is_active=True,
            linked_disorder_id__in=disorder_ids,
        ).order_by("sort_index")
    }
    for node in nodes:
        if node["type"] != "disorder":
            continue
        dsm_record = dsm_by_disorder.get(disorder_id_by_slug.get(node["slug"]))
        if dsm_record:
            node["dsm_master_id"] = dsm_record.master_id
            node["dsm_chapter_number"] = dsm_record.chapter_number
            node["dsm_chapter_name_fa"] = dsm_record.chapter_name_fa

    nodes.extend({
        "id": f"symptom:{symptom.slug}",
        "type": "symptom",
        "slug": symptom.slug,
        "label": symptom.name_fa or symptom.name_en,
        "name_en": symptom.name_en,
        "name_fa": symptom.name_fa,
        "kind": symptom.domain,
        "group": symptom.get_domain_display(),
        "summary": symptom.description,
        "href": f"/search?q={symptom.slug}",
    } for symptom in sorted(symptom_by_id.values(), key=lambda row: row.name_en))

    degree = {node["id"]: 0 for node in nodes}
    edge_kinds = {}
    for edge in edges:
        degree[edge["source"]] = degree.get(edge["source"], 0) + 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1
        edge_kinds[edge["kind"]] = edge_kinds.get(edge["kind"], 0) + 1
    for node in nodes:
        node["degree"] = degree.get(node["id"], 0)

    return nodes, edges, edge_kinds


def _filter_graph(nodes, edges, request):
    node_type = request.query_params.get("node_type", "").strip()
    domain = request.query_params.get("domain", "").strip()
    kind = request.query_params.get("kind", "").strip()
    subtype = request.query_params.get("subtype", "").strip()
    category = request.query_params.get("category", "").strip()
    relation = request.query_params.get("relation", "").strip()
    raw_degree = request.query_params.get("min_degree", "").strip()

    min_degree = 0
    if raw_degree:
        if not raw_degree.isdigit():
            raise ValidationError({"min_degree": "min_degree باید عدد صحیح نامنفی باشد."})
        min_degree = min(1000, int(raw_degree))

    filtered = []
    for node in nodes:
        if node_type and node_type != "all" and node["type"] != node_type:
            continue
        if domain and node["type"] == "concept" and node.get("domain") != domain:
            continue
        if domain and node["type"] != "concept":
            continue
        if kind and node["type"] == "concept" and node.get("kind") != kind:
            continue
        if kind and node["type"] != "concept":
            continue
        if subtype and node["type"] == "concept" and node.get("subtype") != subtype:
            continue
        if subtype and node["type"] != "concept":
            continue
        if category and node["type"] == "disorder" and node.get("category") != category:
            continue
        if category and node["type"] != "disorder":
            continue
        if node.get("degree", 0) < min_degree:
            continue
        filtered.append(node)

    ids = {node["id"] for node in filtered}
    filtered_edges = [
        edge for edge in edges
        if edge["source"] in ids and edge["target"] in ids and (not relation or edge["kind"] == relation)
    ]

    if relation:
        connected = {edge["source"] for edge in filtered_edges} | {edge["target"] for edge in filtered_edges}
        filtered = [node for node in filtered if node["id"] in connected]
        ids = connected

    degree = {node_id: 0 for node_id in ids}
    for edge in filtered_edges:
        degree[edge["source"]] = degree.get(edge["source"], 0) + 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1
    for node in filtered:
        node["filtered_degree"] = degree.get(node["id"], 0)

    return filtered, filtered_edges


@api_view(["GET"])
def concept_map_v2(request):
    nodes, edges, all_edge_kinds = _build_atlas_graph()
    filtered_nodes, filtered_edges = _filter_graph(nodes, edges, request)
    node_types = {
        "concept": sum(1 for node in filtered_nodes if node["type"] == "concept"),
        "disorder": sum(1 for node in filtered_nodes if node["type"] == "disorder"),
        "symptom": sum(1 for node in filtered_nodes if node["type"] == "symptom"),
    }
    edge_kinds = {}
    for edge in filtered_edges:
        edge_kinds[edge["kind"]] = edge_kinds.get(edge["kind"], 0) + 1
    return Response({
        "meta": {
            "node_count": len(filtered_nodes),
            "edge_count": len(filtered_edges),
            "node_types": node_types,
            "edge_kinds": edge_kinds,
            "available_edge_kinds": all_edge_kinds,
        },
        "nodes": filtered_nodes,
        "edges": filtered_edges,
    })


@api_view(["GET"])
def concept_neighborhood(request, slug):
    concept = get_object_or_404(Concept, slug=slug, is_active=True)
    raw_depth = request.query_params.get("depth", "1")
    if not raw_depth.isdigit() or int(raw_depth) not in {1, 2}:
        raise ValidationError({"depth": "عمق همسایگی باید ۱ یا ۲ باشد."})
    depth = int(raw_depth)
    relation = request.query_params.get("relation", "").strip()
    node_type = request.query_params.get("node_type", "").strip()

    nodes, edges, _ = _build_atlas_graph()
    start = f"concept:{concept.slug}"
    adjacency = {}
    for edge in edges:
        if relation and edge["kind"] != relation:
            continue
        adjacency.setdefault(edge["source"], []).append((edge["target"], edge))
        adjacency.setdefault(edge["target"], []).append((edge["source"], edge))

    distance = {start: 0}
    queue = deque([start])
    selected_edges = []
    seen_edge_keys = set()
    while queue:
        current = queue.popleft()
        if distance[current] >= depth:
            continue
        for neighbor, edge in adjacency.get(current, []):
            key = (edge["source"], edge["target"], edge["kind"])
            if key not in seen_edge_keys:
                seen_edge_keys.add(key)
                selected_edges.append(edge)
            if neighbor not in distance:
                distance[neighbor] = distance[current] + 1
                queue.append(neighbor)

    selected_ids = set(distance)
    selected_nodes = [node for node in nodes if node["id"] in selected_ids]
    if node_type and node_type != "all":
        allowed = {start} | {node["id"] for node in selected_nodes if node["type"] == node_type}
        selected_nodes = [node for node in selected_nodes if node["id"] in allowed]
        selected_edges = [edge for edge in selected_edges if edge["source"] in allowed and edge["target"] in allowed]
    for node in selected_nodes:
        node["distance"] = distance.get(node["id"], 0)

    return Response({
        "center": start,
        "depth": depth,
        "nodes": selected_nodes,
        "edges": selected_edges,
    })


@api_view(["GET"])
def graph_path(request):
    source_id = request.query_params.get("from", "").strip()
    target_id = request.query_params.get("to", "").strip()
    if not source_id or not target_id:
        raise ValidationError({"detail": "پارامترهای from و to الزامی هستند."})
    if source_id == target_id:
        raise ValidationError({"detail": "گره شروع و پایان باید متفاوت باشند."})

    nodes, edges, _ = _build_atlas_graph()
    node_by_id = {node["id"]: node for node in nodes}
    if source_id not in node_by_id or target_id not in node_by_id:
        return Response({"detail": "یکی از گره‌های مسیر وجود ندارد."}, status=404)

    relation = request.query_params.get("relation", "").strip()
    adjacency = {}
    for index, edge in enumerate(edges):
        if relation and edge["kind"] != relation:
            continue
        adjacency.setdefault(edge["source"], []).append((edge["target"], index))
        adjacency.setdefault(edge["target"], []).append((edge["source"], index))

    parent = {source_id: None}
    parent_edge = {}
    queue = deque([source_id])
    while queue and target_id not in parent:
        current = queue.popleft()
        for neighbor, edge_index in adjacency.get(current, []):
            if neighbor in parent:
                continue
            parent[neighbor] = current
            parent_edge[neighbor] = edge_index
            queue.append(neighbor)

    if target_id not in parent:
        return Response({
            "from": source_id,
            "to": target_id,
            "found": False,
            "hops": None,
            "nodes": [],
            "edges": [],
        })

    path_ids = []
    cursor = target_id
    while cursor is not None:
        path_ids.append(cursor)
        cursor = parent[cursor]
    path_ids.reverse()

    path_edges = []
    for node_id in path_ids[1:]:
        path_edges.append(edges[parent_edge[node_id]])

    return Response({
        "from": source_id,
        "to": target_id,
        "found": True,
        "hops": len(path_edges),
        "nodes": [node_by_id[node_id] for node_id in path_ids],
        "edges": path_edges,
    })


@api_view(["GET"])
def cognitive_distortions_overview(request):
    distortions = (
        Concept.objects.filter(is_active=True, subtype=Concept.Subtype.COGNITIVE_DISTORTION)
        .prefetch_related(
            "aliases",
            "disorder_links__disorder",
            "flashcards",
            "outgoing_concept_relationships__target_concept",
            "incoming_concept_relationships__source_concept",
        )
        .order_by("name_en")
    )
    practice_count = CognitiveDistortionPracticeItem.objects.filter(
        is_active=True,
        target_concept__is_active=True,
        target_concept__subtype=Concept.Subtype.COGNITIVE_DISTORTION,
    ).count()
    return Response({
        "count": distortions.count(),
        "practice_count": practice_count,
        "items": ConceptCatalogSerializer(distortions, many=True).data,
    })


@api_view(["GET"])
def distortion_practice_queue(request):
    raw_limit = request.query_params.get("limit", "12")
    if not raw_limit.isdigit() or int(raw_limit) <= 0:
        raise ValidationError({"limit": "limit باید عدد صحیح مثبت باشد."})
    limit = min(20, int(raw_limit))
    difficulty = request.query_params.get("difficulty", "").strip()
    qs = (
        CognitiveDistortionPracticeItem.objects.filter(
            is_active=True,
            target_concept__is_active=True,
            target_concept__subtype=Concept.Subtype.COGNITIVE_DISTORTION,
        )
        .select_related("target_concept")
        .prefetch_related("choices__concept")
        .order_by("sort_order", "id")
    )
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    items = []
    for item in qs[:limit]:
        items.append({
            "slug": item.slug,
            "prompt": item.prompt,
            "difficulty": item.difficulty,
            "choices": [
                {
                    "id": choice.id,
                    "text": choice.text,
                    "concept": {
                        "slug": choice.concept.slug,
                        "name_en": choice.concept.name_en,
                        "name_fa": choice.concept.name_fa,
                    },
                }
                for choice in item.choices.all()
            ],
        })
    return Response({"count": len(items), "items": items})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def distortion_practice_submit(request, slug):
    payload = _object_payload(request)
    choice_id = _positive_int(payload.get("choice_id"), field="choice_id")
    item = get_object_or_404(
        CognitiveDistortionPracticeItem.objects.filter(
            is_active=True,
            target_concept__is_active=True,
            target_concept__subtype=Concept.Subtype.COGNITIVE_DISTORTION,
        ).select_related("target_concept"),
        slug=slug,
    )
    choice = get_object_or_404(item.choices.select_related("concept"), id=choice_id)

    with transaction.atomic():
        attempt = CognitiveDistortionPracticeAttempt.objects.create(
            user=request.user,
            item=item,
            selected_choice=choice,
            is_correct=choice.is_correct,
        )
        now = timezone.now()
        progress, _ = UserConceptProgress.objects.select_for_update().get_or_create(
            user=request.user,
            concept=item.target_concept,
        )
        progress.progress_percent = max(progress.progress_percent, 75 if choice.is_correct else 35)
        progress.last_reviewed_at = now
        progress.last_viewed_at = progress.last_viewed_at or now
        if progress.progress_percent >= 85:
            progress.status = UserConceptProgress.Status.COMPLETED
            progress.completed_at = progress.completed_at or now
        progress.save(update_fields=(
            "progress_percent", "last_reviewed_at", "last_viewed_at", "status", "completed_at", "updated_at"
        ))
        record_activity(
            request.user,
            StudyActivity.Kind.DISTORTION_PRACTICE,
            concept=item.target_concept,
            metadata={
                "item": item.slug,
                "correct": choice.is_correct,
                "selected_concept": choice.concept.slug,
            },
        )

    correct_choices = list(item.choices.filter(is_correct=True).select_related("concept")[:2])
    if len(correct_choices) != 1:
        return Response({"detail": "محتوای این تمرین از نظر پاسخ صحیح ناسازگار است."}, status=status.HTTP_409_CONFLICT)
    correct_choice = correct_choices[0]
    return Response({
        "attempt_id": attempt.id,
        "correct": attempt.is_correct,
        "selected_choice_id": choice.id,
        "correct_choice_id": correct_choice.id,
        "correct_concept": ConceptListSerializer(correct_choice.concept).data,
        "explanation": item.explanation,
        "progress_percent": progress.progress_percent,
    }, status=status.HTTP_201_CREATED)
