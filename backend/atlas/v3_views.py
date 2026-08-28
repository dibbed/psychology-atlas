from collections.abc import Mapping

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .learning import (
    activity_heatmap,
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
    Concept,
    ConceptBookmark,
    ConceptNote,
    DailyChallengeAttempt,
    Disorder,
    DisorderSymptom,
    Flashcard,
    StudyActivity,
    Symptom,
    UserConceptProgress,
    UserFlashcardProgress,
)
from .serializers import DisorderListSerializer
from .v3_serializers import (
    ConceptBookmarkSerializer,
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
    serializer_class = ConceptListSerializer

    def get_queryset(self):
        qs = Concept.objects.filter(is_active=True)
        kind = self.request.query_params.get("kind", "").strip()
        q = self.request.query_params.get("q", "").strip()
        if kind:
            qs = qs.filter(kind=kind)
        if q:
            qs = qs.filter(
                Q(name_en__icontains=q)
                | Q(name_fa__icontains=q)
                | Q(slug__icontains=q)
                | Q(simple_definition__icontains=q)
                | Q(academic_definition__icontains=q)
                | Q(example__icontains=q)
            )
        return qs


class ConceptDetailView(generics.RetrieveAPIView):
    serializer_class = ConceptDetailSerializer
    lookup_field = "slug"
    queryset = (
        Concept.objects.filter(is_active=True)
        .prefetch_related(
            "outgoing_concept_relationships__target_concept",
            "incoming_concept_relationships__source_concept",
            "disorder_links__disorder__category",
            "source_links__source",
            "flashcards",
        )
    )


class FlashcardListView(generics.ListAPIView):
    serializer_class = FlashcardSerializer

    def get_queryset(self):
        qs = Flashcard.objects.filter(is_active=True).select_related("concept", "disorder", "disorder__category")
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
        .filter(
            Q(name_en__icontains=q)
            | Q(name_fa__icontains=q)
            | Q(short_description__icontains=q)
            | Q(symptom_links__symptom__name_en__icontains=q)
            | Q(symptom_links__symptom__name_fa__icontains=q)
        )
        .select_related("category")
        .distinct()[:10]
    )
    concepts = Concept.objects.filter(is_active=True).filter(
        Q(name_en__icontains=q)
        | Q(name_fa__icontains=q)
        | Q(simple_definition__icontains=q)
        | Q(academic_definition__icontains=q)
        | Q(example__icontains=q)
    )[:10]
    symptoms = (
        Symptom.objects.filter(disorder_links__disorder__is_active=True)
        .filter(Q(slug__icontains=q) | Q(name_en__icontains=q) | Q(name_fa__icontains=q) | Q(description__icontains=q))
        .distinct()[:10]
    )

    return Response({
        "query": q,
        "disorders": DisorderListSerializer(disorders, many=True).data,
        "concepts": ConceptListSerializer(concepts, many=True).data,
        "symptoms": [
            {
                "slug": symptom.slug,
                "name_en": symptom.name_en,
                "name_fa": symptom.name_fa,
                "description": symptom.description,
                "domain": symptom.domain,
            }
            for symptom in symptoms
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
            "kind": concept.kind,
            "href": f"/concepts/{concept.slug}",
        }
        for concept in concepts
    ]
    edges = []
    disorder_ids = set()

    for concept in concepts:
        for relation in concept.outgoing_concept_relationships.select_related("target_concept").filter(target_concept_id__in=concept_ids):
            edges.append({
                "source": f"concept:{concept.slug}",
                "target": f"concept:{relation.target_concept.slug}",
                "kind": relation.relationship_type,
            })
        for link in concept.disorder_links.select_related("disorder", "disorder__category").filter(disorder__is_active=True):
            disorder_ids.add(link.disorder_id)
            edges.append({
                "source": f"disorder:{link.disorder.slug}",
                "target": f"concept:{concept.slug}",
                "kind": link.role,
            })

    symptom_links = list(
        DisorderSymptom.objects.filter(disorder__is_active=True)
        .select_related("disorder", "disorder__category", "symptom")
        .order_by("disorder_id", "sort_order", "id")
    )
    symptom_ids = set()
    for link in symptom_links:
        disorder_ids.add(link.disorder_id)
        symptom_ids.add(link.symptom_id)
        edges.append({
            "source": f"disorder:{link.disorder.slug}",
            "target": f"symptom:{link.symptom.slug}",
            "kind": f"symptom_{link.prominence}",
        })

    disorders = Disorder.objects.filter(id__in=disorder_ids, is_active=True).select_related("category").order_by("name_en")
    nodes.extend({
        "id": f"disorder:{disorder.slug}",
        "type": "disorder",
        "slug": disorder.slug,
        "label": disorder.name_fa or disorder.name_en,
        "kind": disorder.category.slug,
        "href": f"/disorders/{disorder.slug}",
    } for disorder in disorders)

    symptoms = Symptom.objects.filter(id__in=symptom_ids).order_by("name_en")
    nodes.extend({
        "id": f"symptom:{symptom.slug}",
        "type": "symptom",
        "slug": symptom.slug,
        "label": symptom.name_fa or symptom.name_en,
        "kind": symptom.domain,
        "href": f"/search?q={symptom.slug}",
    } for symptom in symptoms)

    return Response({"nodes": nodes, "edges": edges})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def review_queue(request):
    try:
        limit = min(50, max(1, int(request.query_params.get("limit", "20"))))
    except ValueError:
        limit = 20
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
        Flashcard.objects.select_related("concept", "disorder"),
        slug=slug,
        is_active=True,
    )
    try:
        progress = review_flashcard(user=request.user, flashcard=flashcard, rating=rating)
    except ValueError:
        raise ValidationError({"rating": "گزینه ارزیابی باید again، hard، good یا easy باشد."})
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
    raw_body = payload.get("body", "")
    if raw_body is None:
        body = ""
    elif isinstance(raw_body, str):
        body = raw_body.strip()
    else:
        raise ValidationError({"body": "متن یادداشت باید رشته متنی باشد."})
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
    challenge = today_challenge()
    if not challenge:
        return Response({"detail": "چالش روزانه هنوز آماده نشده است."}, status=404)

    if request.method == "GET":
        attempt = challenge_attempt_for_today(request.user) if request.user.is_authenticated else None
        if attempt:
            challenge = attempt.challenge
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
    except IntegrityError:
        existing = challenge_attempt_for_today(request.user)
        return Response({
            "detail": "چالش امروز قبلاً پاسخ داده شده است.",
            "correct": existing.is_correct if existing else False,
            "explanation": existing.challenge.explanation if existing else challenge.explanation,
        }, status=status.HTTP_409_CONFLICT)
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
    return Response({
        "correct": attempt.is_correct,
        "selected_choice_id": choice.id,
        "explanation": challenge.explanation,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def study_overview(request):
    due_count = UserFlashcardProgress.objects.filter(
        user=request.user,
        flashcard__is_active=True,
        due_at__lte=timezone.now(),
    ).count()
    unseen_count = Flashcard.objects.filter(is_active=True).exclude(
        id__in=UserFlashcardProgress.objects.filter(user=request.user).values_list("flashcard_id", flat=True)
    ).count()
    reviewed_cards = UserFlashcardProgress.objects.filter(user=request.user, last_reviewed_at__isnull=False).count()
    concept_rows = UserConceptProgress.objects.filter(user=request.user)
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
