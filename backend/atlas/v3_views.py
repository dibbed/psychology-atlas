from collections.abc import Mapping

from django.db import IntegrityError, transaction
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .learning import (
    activity_heatmap,
    available_flashcards,
    challenge_attempt_for_today,
    current_streak,
    get_recommendations,
    get_review_queue,
    mark_concept_viewed,
    record_activity,
    review_flashcard,
    today_challenge,
)
from .models import (
    Category,
    ClinicalCase,
    Concept,
    ConceptBookmark,
    ConceptNote,
    ConceptRelationship,
    ConceptSymptom,
    DailyChallenge,
    DailyChallengeAttempt,
    DSMRecord,
    DSMRecordRelation,
    Disorder,
    DisorderConcept,
    Quiz,
    DisorderSymptom,
    StudyActivity,
    Symptom,
    UserConceptProgress,
    UserFlashcardProgress,
)
from .search_utils import icontains_any
from .serializers import DisorderListSerializer
from .v3_serializers import (
    ConceptBookmarkSerializer,
    ConceptCatalogSerializer,
    ConceptDetailSerializer,
    ConceptListSerializer,
    ConceptNoteSerializer,
    DailyChallengeSerializer,
    FlashcardProgressSerializer,
    FlashcardSerializer,
)


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


class ConceptListView(generics.ListAPIView):
    serializer_class = ConceptCatalogSerializer

    def get_queryset(self):
        qs = Concept.objects.filter(is_active=True).prefetch_related(
            "aliases",
            "disorder_links__disorder",
            "flashcards",
            "outgoing_concept_relationships__target_concept",
            "incoming_concept_relationships__source_concept",
        )
        kind = self.request.query_params.get("kind", "").strip()
        domain = self.request.query_params.get("domain", "").strip()
        subtype = self.request.query_params.get("subtype", "").strip()
        q = self.request.query_params.get("q", "").strip()
        if kind:
            qs = qs.filter(kind=kind)
        if domain:
            qs = qs.filter(domain=domain)
        if subtype:
            qs = qs.filter(subtype=subtype)
        if q:
            qs = qs.filter(icontains_any(
                (
                    "name_en", "name_fa", "slug", "simple_definition", "academic_definition", "example",
                    "counterexample", "recognition_cues", "common_confusions", "aliases__text",
                ),
                q,
            )).distinct()
        return qs


class ConceptDetailView(generics.RetrieveAPIView):
    serializer_class = ConceptDetailSerializer
    lookup_field = "slug"
    queryset = (
        Concept.objects.filter(is_active=True)
        .prefetch_related(
            "aliases",
            "outgoing_concept_relationships__target_concept",
            "outgoing_concept_relationships__source_links__source",
            "incoming_concept_relationships__source_concept",
            "incoming_concept_relationships__source_links__source",
            "disorder_links__disorder__category",
            "symptom_links__symptom",
            "source_links__source",
            "flashcards",
        )
    )


class FlashcardListView(generics.ListAPIView):
    serializer_class = FlashcardSerializer

    def get_queryset(self):
        qs = available_flashcards().select_related("concept", "disorder", "disorder__category")
        concept = self.request.query_params.get("concept", "").strip()
        disorder = self.request.query_params.get("disorder", "").strip()
        difficulty = self.request.query_params.get("difficulty", "").strip()
        if concept:
            qs = qs.filter(concept__slug=concept)
        if disorder:
            qs = qs.filter(disorder__slug=disorder)
        if difficulty:
            qs = qs.filter(difficulty=difficulty)
        return qs


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def concept_view(request, slug):
    concept = get_object_or_404(Concept, slug=slug, is_active=True)
    progress = mark_concept_viewed(request.user, concept)
    return Response({
        "slug": concept.slug,
        "progress_percent": progress.progress_percent,
        "status": progress.status,
    })


@api_view(["GET"])
def global_search(request):
    q = request.query_params.get("q", "").strip()
    if len(q) < 2:
        return Response({"query": q, "disorders": [], "concepts": [], "symptoms": []})

    disorders = (
        Disorder.objects.filter(is_active=True)
        .filter(icontains_any(
            (
                "slug",
                "name_en",
                "name_fa",
                "short_description",
                "dsm_master_records__search_text",
                "symptom_links__symptom__name_en",
                "symptom_links__symptom__name_fa",
            ),
            q,
        ))
        .annotate(
            _direct_name_match=Case(
                When(icontains_any(("name_en", "name_fa"), q), then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
        .select_related("category")
        .order_by("_direct_name_match", "name_en")
        .distinct()[:10]
    )
    concepts = (
        Concept.objects.filter(is_active=True)
        .filter(icontains_any(
            (
                "slug", "name_en", "name_fa", "simple_definition", "academic_definition", "example",
                "counterexample", "recognition_cues", "common_confusions", "aliases__text",
            ),
            q,
        ))
        .prefetch_related(
            "aliases",
            "disorder_links__disorder",
            "flashcards",
            "outgoing_concept_relationships__target_concept",
            "incoming_concept_relationships__source_concept",
        ).distinct()[:10]
    )
    symptoms = list(
        Symptom.objects.filter(disorder_links__disorder__is_active=True)
        .filter(icontains_any(("slug", "name_en", "name_fa", "description"), q))
        .prefetch_related("disorder_links__disorder__category")
        .distinct()[:10]
    )

    return Response({
        "query": q,
        "disorders": DisorderListSerializer(disorders, many=True).data,
        "concepts": ConceptCatalogSerializer(concepts, many=True).data,
        "symptoms": [
            {
                "slug": symptom.slug,
                "name_en": symptom.name_en,
                "name_fa": symptom.name_fa,
                "description": symptom.description,
                "domain": symptom.domain,
                "disorders": DisorderListSerializer(
                    [
                        link.disorder
                        for link in symptom.disorder_links.all()
                        if link.disorder.is_active
                    ][:4],
                    many=True,
                ).data,
            }
            for symptom in symptoms
        ],
    })


def _linked_dsm_nearby_edges():
    rows = (
        DSMRecordRelation.objects.filter(
            relationship_type=DSMRecordRelation.Kind.NEARBY,
            source__corpus__is_active=True,
            target__corpus__is_active=True,
            source__is_active=True,
            target__is_active=True,
            source__linked_disorder__is_active=True,
            target__linked_disorder__is_active=True,
        )
        .select_related("source__linked_disorder", "target__linked_disorder")
        .order_by("source__sort_index", "target__sort_index")
    )
    seen = set()
    edges = []
    for relation in rows:
        source = relation.source.linked_disorder
        target = relation.target.linked_disorder
        if source_id := getattr(source, "id", None):
            if not getattr(target, "id", None) or source_id == target.id:
                continue
        else:
            continue
        pair = tuple(sorted((source.id, target.id)))
        if pair in seen:
            continue
        seen.add(pair)
        edges.append((source, target, relation))
    return edges


@api_view(["GET"])
def atlas_overview(request):
    valid_quizzes = Quiz.objects.filter(is_active=True).filter(
        Q(disorder__isnull=True) | Q(disorder__is_active=True)
    )
    valid_cases = ClinicalCase.objects.filter(is_active=True).filter(
        Q(primary_disorder__isnull=True) | Q(primary_disorder__is_active=True)
    )
    valid_challenges = DailyChallenge.objects.filter(is_active=True).filter(
        Q(concept__isnull=True) | Q(concept__is_active=True),
        Q(disorder__isnull=True) | Q(disorder__is_active=True),
    )
    categories = list(
        Category.objects.filter(is_active=True)
        .annotate(disorder_count=Count("disorders", filter=Q(disorders__is_active=True)))
        .filter(disorder_count__gt=0)
        .order_by("sort_order", "name_en")
    )
    concept_kinds = list(
        Concept.objects.filter(is_active=True)
        .values("kind")
        .annotate(count=Count("id"))
        .order_by("-count", "kind")
    )
    concept_domains = list(
        Concept.objects.filter(is_active=True)
        .values("domain")
        .annotate(count=Count("id"))
        .order_by("-count", "domain")
    )
    concept_subtypes = list(
        Concept.objects.filter(is_active=True)
        .values("subtype")
        .annotate(count=Count("id"))
        .order_by("-count", "subtype")
    )
    symptom_count = (
        Symptom.objects.filter(
            Q(disorder_links__disorder__is_active=True) | Q(concept_links__concept__is_active=True)
        )
        .distinct()
        .count()
    )
    dsm_nearby_edges = _linked_dsm_nearby_edges()
    graph_edge_count = (
        ConceptRelationship.objects.filter(
            source_concept__is_active=True,
            target_concept__is_active=True,
        ).count()
        + DisorderConcept.objects.filter(
            disorder__is_active=True,
            concept__is_active=True,
        ).count()
        + DisorderSymptom.objects.filter(disorder__is_active=True).count()
        + ConceptSymptom.objects.filter(concept__is_active=True).count()
        + len(dsm_nearby_edges)
    )

    return Response({
        "counts": {
            "categories": len(categories),
            "disorders": Disorder.objects.filter(is_active=True).count(),
            "concepts": Concept.objects.filter(is_active=True).count(),
            "symptoms": symptom_count,
            "flashcards": available_flashcards().count(),
            "daily_challenges": valid_challenges.count(),
            "quizzes": valid_quizzes.count(),
            "clinical_cases": valid_cases.count(),
        },
        "graph": {
            "nodes": Disorder.objects.filter(is_active=True).count() + Concept.objects.filter(is_active=True).count() + symptom_count,
            "edges": graph_edge_count,
        },
        "categories": [
            {
                "slug": category.slug,
                "name_en": category.name_en,
                "name_fa": category.name_fa,
                "count": category.disorder_count,
            }
            for category in categories
        ],
        "concept_kinds": [
            {
                "kind": row["kind"],
                "label": Concept.Kind(row["kind"]).label,
                "count": row["count"],
            }
            for row in concept_kinds
        ],
        "concept_domains": [
            {
                "domain": row["domain"],
                "label": Concept.Domain(row["domain"]).label,
                "count": row["count"],
            }
            for row in concept_domains
        ],
        "concept_subtypes": [
            {
                "subtype": row["subtype"],
                "label": Concept.Subtype(row["subtype"]).label,
                "count": row["count"],
            }
            for row in concept_subtypes
        ],
    })


@api_view(["GET"])
def concept_map(request):
    concepts = list(Concept.objects.filter(is_active=True).order_by("name_en"))
    concept_ids = {concept.id for concept in concepts}
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
    disorders = list(
        Disorder.objects.filter(is_active=True)
        .select_related("category")
        .order_by("name_en")
    )
    disorder_ids = {disorder.id for disorder in disorders}

    concept_relations = (
        ConceptRelationship.objects.filter(
            source_concept_id__in=concept_ids,
            target_concept_id__in=concept_ids,
        )
        .select_related("source_concept", "target_concept")
        .order_by("id")
    )
    for relation in concept_relations:
        edges.append({
            "source": f"concept:{relation.source_concept.slug}",
            "target": f"concept:{relation.target_concept.slug}",
            "kind": relation.relationship_type,
            "explanation": relation.explanation,
        })

    disorder_concept_links = (
        DisorderConcept.objects.filter(
            concept_id__in=concept_ids,
            disorder__is_active=True,
        )
        .select_related("concept", "disorder", "disorder__category")
        .order_by("disorder_id", "sort_order", "id")
    )
    for link in disorder_concept_links:
        disorder_ids.add(link.disorder_id)
        edges.append({
            "source": f"disorder:{link.disorder.slug}",
            "target": f"concept:{link.concept.slug}",
            "kind": link.role,
            "explanation": link.explanation,
        })

    concept_symptom_links = list(
        ConceptSymptom.objects.filter(concept__is_active=True)
        .select_related("concept", "symptom")
        .order_by("concept_id", "sort_order", "id")
    )
    symptom_ids = set()
    symptom_by_id = {}
    for link in concept_symptom_links:
        symptom_ids.add(link.symptom_id)
        symptom_by_id[link.symptom_id] = link.symptom
        edges.append({
            "source": f"concept:{link.concept.slug}",
            "target": f"symptom:{link.symptom.slug}",
            "kind": f"concept_symptom_{link.relationship_type}",
            "explanation": link.explanation,
        })

    symptom_links = list(
        DisorderSymptom.objects.filter(disorder__is_active=True)
        .select_related("disorder", "disorder__category", "symptom")
        .order_by("disorder_id", "sort_order", "id")
    )
    for link in symptom_links:
        disorder_ids.add(link.disorder_id)
        symptom_ids.add(link.symptom_id)
        symptom_by_id[link.symptom_id] = link.symptom
        edges.append({
            "source": f"disorder:{link.disorder.slug}",
            "target": f"symptom:{link.symptom.slug}",
            "kind": f"symptom_{link.prominence}",
            "explanation": link.note,
        })

    dsm_nearby_edges = _linked_dsm_nearby_edges()
    for source, target, relation in dsm_nearby_edges:
        disorder_ids.add(source.id)
        disorder_ids.add(target.id)
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
        disorder = next((row for row in disorders if row.slug == node["slug"]), None)
        if not disorder:
            continue
        dsm_record = dsm_by_disorder.get(disorder.id)
        if dsm_record:
            node["dsm_master_id"] = dsm_record.master_id
            node["dsm_chapter_number"] = dsm_record.chapter_number
            node["dsm_chapter_name_fa"] = dsm_record.chapter_name_fa

    symptoms = sorted(symptom_by_id.values(), key=lambda symptom: symptom.name_en)
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
    } for symptom in symptoms)

    degree = {node["id"]: 0 for node in nodes}
    edge_kinds = {}
    for edge in edges:
        degree[edge["source"]] = degree.get(edge["source"], 0) + 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1
        edge_kinds[edge["kind"]] = edge_kinds.get(edge["kind"], 0) + 1
    for node in nodes:
        node["degree"] = degree.get(node["id"], 0)

    node_types = {
        "concept": sum(1 for node in nodes if node["type"] == "concept"),
        "disorder": sum(1 for node in nodes if node["type"] == "disorder"),
        "symptom": sum(1 for node in nodes if node["type"] == "symptom"),
    }

    return Response({
        "meta": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "node_types": node_types,
            "edge_kinds": edge_kinds,
        },
        "nodes": nodes,
        "edges": edges,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def review_queue(request):
    raw_limit = request.query_params.get("limit", "20")
    try:
        if isinstance(raw_limit, str) and (not raw_limit.isdigit() or int(raw_limit) <= 0):
            raise ValueError
        limit = min(50, int(raw_limit))
    except (TypeError, ValueError):
        return Response({"detail": "پارامتر limit باید یک عدد صحیح مثبت باشد."}, status=400)
    concept_slug = request.query_params.get("concept", "").strip() or None
    disorder_slug = request.query_params.get("disorder", "").strip() or None
    due_rows, new_cards = get_review_queue(
        request.user,
        limit=limit,
        concept_slug=concept_slug,
        disorder_slug=disorder_slug,
    )
    items = [
        {
            "is_new": False,
            "flashcard": FlashcardSerializer(row.flashcard).data,
            "progress": FlashcardProgressSerializer(row).data,
        }
        for row in due_rows
    ]
    items.extend({
        "is_new": True,
        "flashcard": FlashcardSerializer(card).data,
        "progress": None,
    } for card in new_cards)
    return Response({
        "count": len(items),
        "due_count": len(due_rows),
        "new_count": len(new_cards),
        "items": items,
    })


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def flashcard_review(request, slug):
    payload = _object_payload(request)
    rating = payload.get("rating")
    if not isinstance(rating, str):
        raise ValidationError({"rating": "ارزیابی کارت معتبر نیست."})
    flashcard = get_object_or_404(
        available_flashcards().select_related("concept", "disorder"),
        slug=slug,
    )
    try:
        progress = review_flashcard(user=request.user, flashcard=flashcard, rating=rating)
    except ValueError as error:
        if str(error) == "invalid_rating":
            raise ValidationError({"rating": "گزینه ارزیابی باید again، hard، good یا easy باشد."})
        raise ValidationError({"detail": "این فلش‌کارت دیگر برای مرور فعال نیست."})
    return Response(FlashcardProgressSerializer(progress).data)


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def concept_bookmarks(request):
    if request.method == "GET":
        rows = ConceptBookmark.objects.filter(user=request.user, concept__is_active=True).select_related("concept").order_by("-created_at")
        return Response(ConceptBookmarkSerializer(rows, many=True).data)
    payload = _object_payload(request)
    slug = payload.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        raise ValidationError({"slug": "slug مفهوم معتبر نیست."})
    concept = get_object_or_404(Concept, slug=slug.strip(), is_active=True)
    bookmark, created = ConceptBookmark.objects.get_or_create(user=request.user, concept=concept)
    if created:
        record_activity(request.user, StudyActivity.Kind.BOOKMARK_SAVED, concept=concept)
    return Response(ConceptBookmarkSerializer(bookmark).data, status=201 if created else 200)


@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def concept_bookmark_delete(request, slug):
    ConceptBookmark.objects.filter(user=request.user, concept__slug=slug).delete()
    return Response(status=204)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def concept_notes(request):
    rows = ConceptNote.objects.filter(user=request.user, concept__is_active=True).select_related("concept")
    return Response(ConceptNoteSerializer(rows, many=True).data)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def concept_note_detail(request, slug):
    concept = get_object_or_404(Concept, slug=slug, is_active=True)
    note = ConceptNote.objects.filter(user=request.user, concept=concept).first()
    if request.method == "GET":
        if not note:
            return Response({"concept_slug": slug, "body": "", "exists": False})
        data = ConceptNoteSerializer(note).data
        data["exists"] = True
        return Response(data)
    if request.method == "DELETE":
        if note:
            note.delete()
        return Response(status=204)

    payload = _object_payload(request)
    if "body" not in payload or not isinstance(payload["body"], str):
        raise ValidationError({"body": "متن یادداشت باید رشته متنی باشد."})
    body = payload["body"].strip()
    if len(body) > 12000:
        raise ValidationError({"body": "یادداشت بیش از حد طولانی است."})
    if not body:
        if note:
            note.delete()
        return Response({"concept_slug": slug, "body": "", "exists": False})
    note, _ = ConceptNote.objects.update_or_create(
        user=request.user,
        concept=concept,
        defaults={"body": body},
    )
    record_activity(request.user, StudyActivity.Kind.NOTE_SAVED, concept=concept)
    data = ConceptNoteSerializer(note).data
    data["exists"] = True
    return Response(data)


@api_view(["GET", "POST"])
@permission_classes([permissions.AllowAny])
def daily_challenge(request):
    if request.method == "GET":
        attempt = challenge_attempt_for_today(request.user) if request.user.is_authenticated else None
        challenge = attempt.challenge if attempt else today_challenge()
        if not challenge:
            return Response({"detail": "چالش روزانه هنوز آماده نشده است."}, status=404)
        data = DailyChallengeSerializer(challenge).data
        data["date"] = timezone.localdate().isoformat()
        data["attempt"] = None
        if attempt:
            data["attempt"] = {
                "selected_choice_id": attempt.selected_choice_id,
                "correct": attempt.is_correct,
                "explanation": attempt.challenge.explanation,
            }
        return Response(data)

    if not request.user.is_authenticated:
        return Response({"detail": "برای ثبت پاسخ باید وارد حساب شوی."}, status=status.HTTP_401_UNAUTHORIZED)

    existing = challenge_attempt_for_today(request.user)
    if existing:
        return Response({
            "detail": "چالش امروز قبلاً پاسخ داده شده است.",
            "correct": existing.is_correct,
            "explanation": existing.challenge.explanation,
        }, status=status.HTTP_409_CONFLICT)

    challenge = today_challenge()
    if not challenge:
        return Response({"detail": "چالش روزانه هنوز آماده نشده است."}, status=404)

    payload = _object_payload(request)
    choice_id = _positive_int(payload.get("choice_id"), field="choice_id")
    choice = get_object_or_404(challenge.choices.all(), id=choice_id)
    try:
        with transaction.atomic():
            attempt = DailyChallengeAttempt.objects.create(
                user=request.user,
                challenge=challenge,
                activity_date=timezone.localdate(),
                selected_choice=choice,
                is_correct=choice.is_correct,
            )
            record_activity(
                request.user,
                StudyActivity.Kind.DAILY_CHALLENGE,
                concept=challenge.concept,
                disorder=challenge.disorder,
                metadata={"correct": choice.is_correct},
            )
            if challenge.concept_id:
                progress, _ = UserConceptProgress.objects.get_or_create(user=request.user, concept=challenge.concept)
                progress.progress_percent = max(progress.progress_percent, 70 if choice.is_correct else 30)
                progress.last_reviewed_at = timezone.now()
                if progress.progress_percent >= 85:
                    progress.status = UserConceptProgress.Status.COMPLETED
                    progress.completed_at = progress.completed_at or timezone.now()
                progress.save(update_fields=("progress_percent", "last_reviewed_at", "status", "completed_at", "updated_at"))
    except IntegrityError:
        existing = challenge_attempt_for_today(request.user)
        if not existing:
            raise
        return Response({
            "detail": "چالش امروز قبلاً پاسخ داده شده است.",
            "correct": existing.is_correct,
            "explanation": existing.challenge.explanation,
        }, status=status.HTTP_409_CONFLICT)
    return Response({
        "correct": attempt.is_correct,
        "selected_choice_id": choice.id,
        "explanation": challenge.explanation,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def study_overview(request):
    visible_cards = available_flashcards()
    visible_card_ids = visible_cards.values_list("id", flat=True)
    due_count = UserFlashcardProgress.objects.filter(
        user=request.user,
        flashcard_id__in=visible_card_ids,
        due_at__lte=timezone.now(),
    ).count()
    unseen_count = visible_cards.exclude(
        id__in=UserFlashcardProgress.objects.filter(user=request.user).values_list("flashcard_id", flat=True)
    ).count()
    reviewed_cards = UserFlashcardProgress.objects.filter(
        user=request.user,
        flashcard_id__in=visible_card_ids,
        last_reviewed_at__isnull=False,
    ).count()
    concept_rows = UserConceptProgress.objects.filter(user=request.user, concept__is_active=True)
    attempt = challenge_attempt_for_today(request.user)
    return Response({
        "streak": current_streak(request.user),
        "heatmap": activity_heatmap(request.user, days=42),
        "recommendations": get_recommendations(request.user),
        "review": {
            "due": due_count,
            "new": unseen_count,
            "reviewed": reviewed_cards,
        },
        "concepts": {
            "studied": concept_rows.count(),
            "mastered": concept_rows.filter(status=UserConceptProgress.Status.COMPLETED).count(),
        },
        "daily_challenge_completed": bool(attempt),
    })
