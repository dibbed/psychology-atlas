from collections import deque
from collections.abc import Mapping

from django.core.cache import cache
from django.db import transaction
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .learning import record_activity
from .models import (
    CognitiveDistortionPracticeAttempt,
    CognitiveDistortionPracticeChoice,
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
from .validation import positive_int
from .v3_views import _linked_dsm_nearby_edges


def _object_payload(request):
    if not isinstance(request.data, Mapping):
        raise ValidationError({"detail": "بدنه درخواست باید یک شیء JSON باشد."})
    return request.data


def _positive_int(value, *, field):
    return positive_int(value, field=field)


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

    for source_id, source_slug, target_id, target_slug in _linked_dsm_nearby_edges():
        if source_id not in disorder_ids or target_id not in disorder_ids:
            continue
        edges.append({
            "source": f"disorder:{source_slug}",
            "target": f"disorder:{target_slug}",
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


def invalidate_atlas_graph_cache():
    cache.delete("atlas_graph_v4")


def _get_atlas_graph():
    payload = cache.get("atlas_graph_v4")
    if payload is None:
        payload = _build_atlas_graph()
        cache.set("atlas_graph_v4", payload, timeout=300)
    nodes, edges, edge_kinds = payload
    return [dict(node) for node in nodes], [dict(edge) for edge in edges], dict(edge_kinds)


def _filter_graph(nodes, edges, request):
    node_type = request.query_params.get("node_type", "").strip()
    domain = request.query_params.get("domain", "").strip()
    kind = request.query_params.get("kind", "").strip()
    subtype = request.query_params.get("subtype", "").strip()
    category = request.query_params.get("category", "").strip()
    relation = request.query_params.get("relation", "").strip()
    raw_degree = request.query_params.get("min_degree", "").strip()

    if node_type and node_type not in {"all", "concept", "disorder", "symptom"}:
        raise ValidationError({"node_type": "نوع گره معتبر نیست."})

    min_degree = 0
    if raw_degree:
        if not raw_degree.isascii() or not raw_degree.isdigit() or len(raw_degree) > 4:
            raise ValidationError({"min_degree": "min_degree باید عدد صحیح نامنفی باشد."})
        min_degree = min(1000, int(raw_degree))

    filtered = []
    for node in nodes:
        if node_type and node_type != "all" and node["type"] != node_type:
            continue
        if domain and (node["type"] != "concept" or node.get("domain") != domain):
            continue
        if kind and (node["type"] != "concept" or node.get("kind") != kind):
            continue
        if subtype and (node["type"] != "concept" or node.get("subtype") != subtype):
            continue
        if category and (node["type"] != "disorder" or node.get("category") != category):
            continue
        filtered.append(node)

    ids = {node["id"] for node in filtered}
    filtered_edges = [
        edge for edge in edges
        if edge["source"] in ids and edge["target"] in ids and (not relation or edge["kind"] == relation)
    ]

    if relation:
        ids = {edge["source"] for edge in filtered_edges} | {edge["target"] for edge in filtered_edges}

    if min_degree:
        active_ids = set(ids)
        while active_ids:
            degree = {node_id: 0 for node_id in active_ids}
            for edge in filtered_edges:
                if edge["source"] in active_ids and edge["target"] in active_ids:
                    degree[edge["source"]] += 1
                    degree[edge["target"]] += 1
            remove = {node_id for node_id, value in degree.items() if value < min_degree}
            if not remove:
                break
            active_ids.difference_update(remove)
        ids = active_ids

    filtered = [node for node in filtered if node["id"] in ids]
    filtered_edges = [edge for edge in filtered_edges if edge["source"] in ids and edge["target"] in ids]
    degree = {node_id: 0 for node_id in ids}
    for edge in filtered_edges:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    for node in filtered:
        node["filtered_degree"] = degree.get(node["id"], 0)

    return filtered, filtered_edges


@api_view(["GET"])
def concept_map_v2(request):
    nodes, edges, all_edge_kinds = _get_atlas_graph()
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
    raw_depth = request.query_params.get("depth", "1").strip()
    if raw_depth not in {"1", "2"}:
        raise ValidationError({"depth": "عمق همسایگی باید ۱ یا ۲ باشد."})
    depth = int(raw_depth)
    relation = request.query_params.get("relation", "").strip()
    node_type = request.query_params.get("node_type", "").strip()
    if node_type and node_type not in {"all", "concept", "disorder", "symptom"}:
        raise ValidationError({"node_type": "نوع گره معتبر نیست."})

    nodes, edges, all_edge_kinds = _get_atlas_graph()
    if relation and relation not in all_edge_kinds:
        raise ValidationError({"relation": "نوع رابطه معتبر نیست."})

    start = f"concept:{concept.slug}"
    node_by_id = {node["id"]: node for node in nodes}
    allowed_ids = set(node_by_id)
    if node_type and node_type != "all":
        allowed_ids = {start} | {
            node_id for node_id, node in node_by_id.items()
            if node["type"] == node_type
        }

    eligible_edges = [
        edge for edge in edges
        if edge["source"] in allowed_ids
        and edge["target"] in allowed_ids
        and (not relation or edge["kind"] == relation)
    ]
    adjacency = {}
    for edge in eligible_edges:
        adjacency.setdefault(edge["source"], []).append(edge["target"])
        adjacency.setdefault(edge["target"], []).append(edge["source"])

    distance = {start: 0}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        if distance[current] >= depth:
            continue
        for neighbor in adjacency.get(current, []):
            if neighbor in distance:
                continue
            distance[neighbor] = distance[current] + 1
            queue.append(neighbor)

    selected_ids = set(distance)
    selected_nodes = [dict(node_by_id[node_id]) for node_id in selected_ids]
    selected_edges = [
        edge for edge in eligible_edges
        if edge["source"] in selected_ids and edge["target"] in selected_ids
    ]
    for node in selected_nodes:
        node["distance"] = distance[node["id"]]
    selected_nodes.sort(key=lambda node: (node["distance"], node["label"]))

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

    nodes, edges, all_edge_kinds = _get_atlas_graph()
    node_by_id = {node["id"]: node for node in nodes}
    if source_id not in node_by_id or target_id not in node_by_id:
        return Response({"detail": "یکی از گره‌های مسیر وجود ندارد."}, status=404)

    relation = request.query_params.get("relation", "").strip()
    if relation and relation not in all_edge_kinds:
        raise ValidationError({"relation": "نوع رابطه معتبر نیست."})
    include_structural = request.query_params.get("include_structural", "0").strip() in {"1", "true", "yes"}

    adjacency = {}
    for index, edge in enumerate(edges):
        if relation and edge["kind"] != relation:
            continue
        if not relation and not include_structural and edge["kind"] == "dsm_nearby":
            continue
        adjacency.setdefault(edge["source"], []).append((edge["target"], index, "forward"))
        adjacency.setdefault(edge["target"], []).append((edge["source"], index, "reverse"))

    parent = {source_id: None}
    parent_edge = {}
    queue = deque([source_id])
    while queue and target_id not in parent:
        current = queue.popleft()
        for neighbor, edge_index, traversal_direction in adjacency.get(current, []):
            if neighbor in parent:
                continue
            parent[neighbor] = current
            parent_edge[neighbor] = (edge_index, traversal_direction)
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
    for index, node_id in enumerate(path_ids[1:], start=1):
        edge_index, traversal_direction = parent_edge[node_id]
        edge = dict(edges[edge_index])
        edge["traversal_direction"] = traversal_direction
        edge["traversed_from"] = path_ids[index - 1]
        edge["traversed_to"] = node_id
        path_edges.append(edge)

    return Response({
        "from": source_id,
        "to": target_id,
        "found": True,
        "hops": len(path_edges),
        "structural_edges_included": include_structural or relation == "dsm_nearby",
        "nodes": [node_by_id[node_id] for node_id in path_ids],
        "edges": path_edges,
    })


def _practice_item_queryset(*, difficulty=""):
    qs = (
        CognitiveDistortionPracticeItem.objects.filter(
            is_active=True,
            target_concept__is_active=True,
            target_concept__subtype=Concept.Subtype.COGNITIVE_DISTORTION,
        )
        .select_related("target_concept")
        .prefetch_related(Prefetch(
            "choices",
            queryset=(
                CognitiveDistortionPracticeChoice.objects.filter(
                    is_active=True,
                    concept__is_active=True,
                    concept__subtype=Concept.Subtype.COGNITIVE_DISTORTION,
                )
                .select_related("concept")
                .order_by("sort_order", "id")
            ),
            to_attr="active_choices",
        ))
        .order_by("sort_order", "id")
    )
    if difficulty:
        qs = qs.filter(difficulty=difficulty)
    return qs


def _practice_item_is_valid(item):
    choices = list(item.active_choices)
    correct = [choice for choice in choices if choice.is_correct]
    return len(choices) >= 2 and len(correct) == 1 and correct[0].concept_id == item.target_concept_id


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
    practice_count = sum(1 for item in _practice_item_queryset() if _practice_item_is_valid(item))
    return Response({
        "count": distortions.count(),
        "practice_count": practice_count,
        "items": ConceptCatalogSerializer(distortions, many=True).data,
    })


@api_view(["GET"])
def distortion_practice_queue(request):
    limit = positive_int(request.query_params.get("limit", "12"), field="limit", maximum=20)
    difficulty = request.query_params.get("difficulty", "").strip()
    valid_difficulties = {choice for choice, _label in CognitiveDistortionPracticeItem.Difficulty.choices}
    if difficulty and difficulty not in valid_difficulties:
        raise ValidationError({"difficulty": "سطح دشواری معتبر نیست."})

    items = []
    for item in _practice_item_queryset(difficulty=difficulty):
        if not _practice_item_is_valid(item):
            continue
        choices = list(item.active_choices)
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
                for choice in choices
            ],
        })
        if len(items) >= limit:
            break
    return Response({"count": len(items), "items": items})


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def distortion_practice_submit(request, slug):
    payload = _object_payload(request)
    choice_id = _positive_int(payload.get("choice_id"), field="choice_id")
    try:
        item = next(item for item in _practice_item_queryset() if item.slug == slug)
    except StopIteration:
        return Response({"detail": "تمرین پیدا نشد."}, status=status.HTTP_404_NOT_FOUND)

    choices_by_id = {choice.id: choice for choice in item.active_choices}
    choice = choices_by_id.get(choice_id)
    if choice is None:
        return Response({"detail": "گزینه انتخاب‌شده معتبر نیست."}, status=status.HTTP_404_NOT_FOUND)
    if not _practice_item_is_valid(item):
        return Response(
            {"detail": "محتوای این تمرین از نظر پاسخ صحیح ناسازگار است."},
            status=status.HTTP_409_CONFLICT,
        )
    correct_choice = next(choice for choice in item.active_choices if choice.is_correct)

    with transaction.atomic():
        attempt = CognitiveDistortionPracticeAttempt.objects.create(
            user=request.user,
            item=item,
            selected_choice=choice,
            is_correct=choice.id == correct_choice.id,
        )
        now = timezone.now()
        progress, _ = UserConceptProgress.objects.select_for_update().get_or_create(
            user=request.user,
            concept=item.target_concept,
        )
        progress.progress_percent = max(progress.progress_percent, 75 if attempt.is_correct else 35)
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
                "correct": attempt.is_correct,
                "selected_concept": choice.concept.slug,
            },
        )

    return Response({
        "attempt_id": attempt.id,
        "correct": attempt.is_correct,
        "selected_choice_id": choice.id,
        "correct_choice_id": correct_choice.id,
        "correct_concept": ConceptListSerializer(correct_choice.concept).data,
        "explanation": item.explanation,
        "progress_percent": progress.progress_percent,
    }, status=status.HTTP_201_CREATED)
