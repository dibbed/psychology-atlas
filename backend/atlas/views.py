from collections.abc import Mapping

from django.contrib.auth.models import User
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .learning import (
    activity_heatmap,
    available_flashcards,
    challenge_attempt_for_today,
    current_streak,
    get_recommendations,
    record_activity,
)
from .models import (
    Bookmark,
    Category,
    ClinicalCase,
    ConceptBookmark,
    ConceptNote,
    Disorder,
    Quiz,
    StudyActivity,
    Technique,
    TechniqueConcept,
    TechniqueConceptSource,
    Therapy,
    TherapyBookmark,
    TherapyClassification,
    TherapyClassificationLink,
    TherapyConcept,
    TherapyConceptSource,
    TherapyDisorder,
    TherapyDisorderSource,
    TherapyFamily,
    TherapyNote,
    TherapySource,
    TherapyTechnique,
    TherapyTechniqueSource,
    UserConceptProgress,
    UserFlashcardProgress,
    UserNote,
    UserProgress,
)
from .search_utils import icontains_any
from .serializers import (
    BookmarkSerializer,
    ClinicalCaseDetailSerializer,
    ClinicalCaseListSerializer,
    DisorderDetailSerializer,
    DisorderListSerializer,
    QuizDetailSerializer,
    QuizListSerializer,
    RegisterSerializer,
    TechniqueDetailSerializer,
    TechniqueListSerializer,
    TherapyBookmarkSerializer,
    TherapyClassificationSerializer,
    TherapyDetailSerializer,
    TherapyFamilySerializer,
    TherapyListSerializer,
    TherapyNoteSerializer,
    UserNoteSerializer,
    UserSerializer,
)
from .services import submit_case, submit_quiz


def _object_payload(request):
    if not isinstance(request.data, Mapping):
        raise ValidationError({"detail": "بدنه درخواست باید یک شیء JSON باشد."})
    return request.data


def available_quizzes():
    return Quiz.objects.filter(is_active=True).filter(
        Q(disorder__isnull=True) | Q(disorder__is_active=True)
    )


def available_clinical_cases():
    return ClinicalCase.objects.filter(is_active=True).filter(
        Q(primary_disorder__isnull=True) | Q(primary_disorder__is_active=True)
    )


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response({
            "user": UserSerializer(user).data,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def me(request):
    return Response(UserSerializer(request.user).data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def logout(request):
    payload = _object_payload(request)
    refresh = payload.get("refresh")
    if not isinstance(refresh, str) or not refresh.strip():
        raise ValidationError({"refresh": "توکن refresh معتبر نیست."})
    try:
        RefreshToken(refresh.strip()).blacklist()
    except TokenError:
        raise ValidationError({"refresh": "توکن refresh معتبر نیست یا قبلاً باطل شده است."})
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def categories(request):
    data = []
    qs = (
        Category.objects.filter(is_active=True)
        .annotate(disorder_count=Count("disorders", filter=Q(disorders__is_active=True)))
        .filter(disorder_count__gt=0)
    )
    for category in qs:
        data.append({
            "slug": category.slug,
            "name_en": category.name_en,
            "name_fa": category.name_fa,
            "description": category.description,
            "disorder_count": category.disorder_count,
        })
    return Response(data)


class DisorderListView(generics.ListAPIView):
    serializer_class = DisorderListSerializer

    def get_queryset(self):
        qs = Disorder.objects.filter(is_active=True).select_related("category")
        category = self.request.query_params.get("category")
        q = self.request.query_params.get("q", "").strip()
        if category:
            qs = qs.filter(category__slug=category)
        if q:
            qs = qs.filter(icontains_any(
                (
                    "name_en",
                    "name_fa",
                    "slug",
                    "short_description",
                    "overview",
                    "clinical_features",
                    "dsm_master_records__search_text",
                    "symptom_links__symptom__name_en",
                    "symptom_links__symptom__name_fa",
                    "symptom_links__symptom__description",
                ),
                q,
            )).annotate(
                _direct_name_match=Case(
                    When(icontains_any(("name_en", "name_fa"), q), then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("_direct_name_match", "name_en").distinct()
        return qs


class DisorderDetailView(generics.RetrieveAPIView):
    serializer_class = DisorderDetailSerializer
    lookup_field = "slug"
    queryset = (
        Disorder.objects.filter(is_active=True)
        .select_related("category")
        .prefetch_related(
            "symptom_links__symptom",
            "outgoing_relationships__related_disorder",
            "incoming_relationships__disorder",
            "source_links__source",
            "quizzes",
            "clinical_cases",
            "concept_links__concept",
            "therapy_links__therapy__family",
            "therapy_links__source_links__source",
        )
    )



@api_view(["GET"])
def compare_disorders(request):
    slugs = [x.strip() for x in request.query_params.get("slugs", "").split(",") if x.strip()]
    if not 2 <= len(slugs) <= 4:
        return Response({"detail": "بین ۲ تا ۴ اختلال انتخاب کن."}, status=400)
    if len(set(slugs)) != len(slugs):
        return Response({"detail": "هر اختلال فقط یک بار می‌تواند در مقایسه باشد."}, status=400)
    qs = (
        Disorder.objects.filter(slug__in=slugs, is_active=True)
        .select_related("category")
        .prefetch_related(
            "symptom_links__symptom",
            "outgoing_relationships__related_disorder",
            "incoming_relationships__disorder",
            "source_links__source",
            "quizzes",
            "clinical_cases",
            "concept_links__concept",
            "therapy_links__therapy__family",
            "therapy_links__source_links__source",
        )
    )
    by_slug = {x.slug: x for x in qs}
    missing = [slug for slug in slugs if slug not in by_slug]
    if missing:
        return Response({"detail": "یک یا چند اختلال انتخاب‌شده پیدا نشد."}, status=404)
    ordered = [by_slug[s] for s in slugs]
    return Response(DisorderDetailSerializer(ordered, many=True).data)


class QuizListView(generics.ListAPIView):
    serializer_class = QuizListSerializer
    queryset = available_quizzes().select_related("disorder", "disorder__category").prefetch_related("questions").order_by("title", "id")


class QuizDetailView(generics.RetrieveAPIView):
    serializer_class = QuizDetailSerializer
    lookup_field = "slug"
    queryset = available_quizzes().select_related("disorder", "disorder__category").prefetch_related("questions__choices")


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def quiz_submit(request, slug):
    quiz = get_object_or_404(available_quizzes().prefetch_related("questions__choices"), slug=slug)
    payload = _object_payload(request)
    attempt, feedback = submit_quiz(user=request.user, quiz=quiz, answers=payload.get("answers", []))
    return Response({
        "attempt_id": attempt.id,
        "score": attempt.score,
        "correct_count": attempt.correct_count,
        "total_questions": attempt.total_questions,
        "feedback": feedback,
    })


class ClinicalCaseListView(generics.ListAPIView):
    serializer_class = ClinicalCaseListSerializer
    queryset = (
        available_clinical_cases()
        .select_related("primary_disorder", "primary_disorder__category")
        .prefetch_related("steps")
        .annotate(
            difficulty_order=Case(
                When(difficulty=ClinicalCase.Difficulty.INTRODUCTORY, then=Value(0)),
                When(difficulty=ClinicalCase.Difficulty.INTERMEDIATE, then=Value(1)),
                When(difficulty=ClinicalCase.Difficulty.ADVANCED, then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            )
        )
        .order_by("difficulty_order", "title", "id")
    )


class ClinicalCaseDetailView(generics.RetrieveAPIView):
    serializer_class = ClinicalCaseDetailSerializer
    lookup_field = "slug"
    queryset = available_clinical_cases().select_related("primary_disorder", "primary_disorder__category").prefetch_related("steps__questions__choices")


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def case_submit(request, slug):
    case = get_object_or_404(available_clinical_cases().prefetch_related("steps__questions__choices"), slug=slug)
    payload = _object_payload(request)
    attempt, feedback = submit_case(user=request.user, clinical_case=case, answers=payload.get("answers", []))
    return Response({
        "attempt_id": attempt.id,
        "score": attempt.score,
        "max_score": attempt.max_score,
        "feedback": feedback,
    })


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def bookmarks(request):
    if request.method == "GET":
        qs = Bookmark.objects.filter(user=request.user, disorder__is_active=True).select_related("disorder", "disorder__category").order_by("-created_at")
        return Response(BookmarkSerializer(qs, many=True).data)

    payload = _object_payload(request)
    slug = payload.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        raise ValidationError({"slug": "شناسه اختلال باید یک slug معتبر باشد."})
    slug = slug.strip()
    disorder = get_object_or_404(Disorder, slug=slug, is_active=True)
    bookmark, created = Bookmark.objects.get_or_create(user=request.user, disorder=disorder)
    if created:
        record_activity(request.user, StudyActivity.Kind.BOOKMARK_SAVED, disorder=disorder)
    return Response(BookmarkSerializer(bookmark).data, status=201 if created else 200)


@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def bookmark_delete(request, slug):
    Bookmark.objects.filter(user=request.user, disorder__slug=slug).delete()
    return Response(status=204)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def progress_view(request, slug):
    disorder = get_object_or_404(Disorder, slug=slug, is_active=True)
    progress, _ = UserProgress.objects.get_or_create(user=request.user, disorder=disorder)
    progress.progress_percent = max(progress.progress_percent, 25)
    progress.last_viewed_at = timezone.now()
    progress.save(update_fields=("progress_percent", "last_viewed_at", "updated_at"))
    record_activity(request.user, StudyActivity.Kind.DISORDER_VIEW, disorder=disorder)
    return Response({
        "slug": disorder.slug,
        "progress_percent": progress.progress_percent,
        "status": progress.status,
    })


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def notes(request):
    qs = UserNote.objects.filter(user=request.user, disorder__is_active=True).select_related("disorder", "disorder__category")
    return Response(UserNoteSerializer(qs, many=True).data)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def note_detail(request, slug):
    disorder = get_object_or_404(Disorder, slug=slug, is_active=True)
    note = UserNote.objects.filter(user=request.user, disorder=disorder).first()

    if request.method == "GET":
        if not note:
            return Response({"disorder_slug": slug, "body": "", "exists": False})
        data = UserNoteSerializer(note).data
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
        return Response({"detail": "یادداشت بیش از حد طولانی است."}, status=400)
    if not body:
        if note:
            note.delete()
        return Response({"disorder_slug": slug, "body": "", "exists": False})
    note, _ = UserNote.objects.update_or_create(
        user=request.user,
        disorder=disorder,
        defaults={"body": body},
    )
    record_activity(request.user, StudyActivity.Kind.NOTE_SAVED, disorder=disorder)
    data = UserNoteSerializer(note).data
    data["exists"] = True
    return Response(data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def dashboard(request):
    bookmarks_qs = Bookmark.objects.filter(user=request.user, disorder__is_active=True).select_related("disorder", "disorder__category").order_by("-created_at")
    progress_qs = UserProgress.objects.filter(user=request.user, disorder__is_active=True).select_related("disorder", "disorder__category").order_by("-last_viewed_at")
    quiz_attempts = request.user.quiz_attempts.filter(
        Q(quiz__disorder__isnull=True) | Q(quiz__disorder__is_active=True),
        status="completed",
        quiz__is_active=True,
    ).select_related("quiz", "quiz__disorder").order_by("-completed_at")
    case_attempts = request.user.case_attempts.filter(
        Q(case__primary_disorder__isnull=True) | Q(case__primary_disorder__is_active=True),
        status="completed",
        case__is_active=True,
    ).select_related("case", "case__primary_disorder").order_by("-completed_at")
    notes_qs = UserNote.objects.filter(user=request.user, disorder__is_active=True).select_related("disorder", "disorder__category").order_by("-updated_at")
    concept_bookmarks_qs = ConceptBookmark.objects.filter(user=request.user, concept__is_active=True).select_related("concept").order_by("-created_at")
    concept_notes_qs = ConceptNote.objects.filter(user=request.user, concept__is_active=True).select_related("concept").order_by("-updated_at")
    therapy_bookmarks_qs = TherapyBookmark.objects.filter(
        user=request.user,
        therapy__is_active=True,
        therapy__family__is_active=True,
    ).select_related("therapy", "therapy__family").order_by("-created_at")
    therapy_notes_qs = TherapyNote.objects.filter(
        user=request.user,
        therapy__is_active=True,
        therapy__family__is_active=True,
    ).select_related("therapy", "therapy__family").order_by("-updated_at")
    concept_progress_qs = UserConceptProgress.objects.filter(user=request.user, concept__is_active=True).select_related("concept")
    visible_cards = available_flashcards()
    due_flashcards = UserFlashcardProgress.objects.filter(
        user=request.user,
        flashcard_id__in=visible_cards.values_list("id", flat=True),
        due_at__lte=timezone.now(),
    ).count()
    unseen_flashcards = visible_cards.exclude(
        id__in=UserFlashcardProgress.objects.filter(user=request.user).values_list("flashcard_id", flat=True)
    ).count()

    completed_quizzes = quiz_attempts.count()
    avg_quiz_score = 0
    if completed_quizzes:
        avg_quiz_score = round(sum(quiz_attempts.values_list("score", flat=True)) / completed_quizzes)

    completed_cases = case_attempts.count()
    case_percentages = [
        round(a.score * 100 / a.max_score) if a.max_score else 0
        for a in case_attempts
    ]
    avg_case_score = round(sum(case_percentages) / len(case_percentages)) if case_percentages else 0

    activity_dates = set()
    for value in quiz_attempts.values_list("completed_at", flat=True):
        if value:
            activity_dates.add(value.date())
    for value in case_attempts.values_list("completed_at", flat=True):
        if value:
            activity_dates.add(value.date())
    for value in progress_qs.values_list("last_viewed_at", flat=True):
        if value:
            activity_dates.add(value.date())
    for value in concept_progress_qs.values_list("last_viewed_at", flat=True):
        if value:
            activity_dates.add(value.date())
    for value in StudyActivity.objects.filter(user=request.user).values_list("occurred_at", flat=True):
        if value:
            activity_dates.add(value.date())

    weak_topics = [
        {
            "slug": p.disorder.slug,
            "name_fa": p.disorder.name_fa,
            "name_en": p.disorder.name_en,
            "progress_percent": p.progress_percent,
        }
        for p in progress_qs.filter(progress_percent__lt=80).order_by("progress_percent", "-last_viewed_at")[:4]
    ]

    return Response({
        "saved_topics": bookmarks_qs.count() + concept_bookmarks_qs.count() + therapy_bookmarks_qs.count(),
        "disorders_studied": progress_qs.count(),
        "concepts_studied": concept_progress_qs.count(),
        "concepts_mastered": concept_progress_qs.filter(status=UserConceptProgress.Status.COMPLETED).count(),
        "topics_studied": progress_qs.count() + concept_progress_qs.count(),
        "quizzes_completed": completed_quizzes,
        "quiz_accuracy": avg_quiz_score,
        "cases_completed": completed_cases,
        "case_accuracy": avg_case_score,
        "notes_count": notes_qs.count() + concept_notes_qs.count() + therapy_notes_qs.count(),
        "study_days": len(activity_dates),
        "streak": current_streak(request.user),
        "heatmap": activity_heatmap(request.user, days=42),
        "recommendations": get_recommendations(request.user),
        "review_due": due_flashcards,
        "review_new": unseen_flashcards,
        "daily_challenge_completed": bool(challenge_attempt_for_today(request.user)),
        "recent_saved": BookmarkSerializer(bookmarks_qs[:4], many=True).data,
        "recent_concept_saved": [
            {
                "id": row.id,
                "slug": row.concept.slug,
                "name_en": row.concept.name_en,
                "name_fa": row.concept.name_fa,
                "kind": row.concept.kind,
            }
            for row in concept_bookmarks_qs[:4]
        ],
        "recent_therapy_saved": [
            {
                "id": row.id,
                "slug": row.therapy.slug,
                "name_en": row.therapy.name_en,
                "name_fa": row.therapy.name_fa,
                "family": row.therapy.family.name_fa or row.therapy.family.name_en,
            }
            for row in therapy_bookmarks_qs[:4]
        ],
        "recent_notes": UserNoteSerializer(notes_qs[:4], many=True).data,
        "recent_concept_notes": [
            {
                "id": row.id,
                "slug": row.concept.slug,
                "name_en": row.concept.name_en,
                "name_fa": row.concept.name_fa,
                "body": row.body,
            }
            for row in concept_notes_qs[:4]
        ],
        "recent_therapy_notes": [
            {
                "id": row.id,
                "slug": row.therapy.slug,
                "name_en": row.therapy.name_en,
                "name_fa": row.therapy.name_fa,
                "family": row.therapy.family.name_fa or row.therapy.family.name_en,
                "body": row.body,
            }
            for row in therapy_notes_qs[:4]
        ],
        "weak_topics": weak_topics,
        "recent_quizzes": [
            {
                "id": a.id,
                "title": a.quiz.title,
                "slug": a.quiz.slug,
                "score": a.score,
                "completed_at": a.completed_at,
            }
            for a in quiz_attempts[:4]
        ],
        "recent_cases": [
            {
                "id": a.id,
                "title": a.case.title,
                "slug": a.case.slug,
                "score": a.score,
                "max_score": a.max_score,
                "completed_at": a.completed_at,
            }
            for a in case_attempts[:4]
        ],
        "continue_learning": [
            {
                "slug": p.disorder.slug,
                "name_en": p.disorder.name_en,
                "name_fa": p.disorder.name_fa,
                "progress_percent": p.progress_percent,
                "status": p.status,
            }
            for p in progress_qs[:6]
        ],
        "continue_concepts": [
            {
                "slug": p.concept.slug,
                "name_en": p.concept.name_en,
                "name_fa": p.concept.name_fa,
                "progress_percent": p.progress_percent,
                "status": p.status,
            }
            for p in concept_progress_qs.order_by("-last_viewed_at", "-last_reviewed_at")[:6]
        ],
    })


# Unified concept, study, graph, and practice views
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
    CognitiveDistortionPracticeAttempt,
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
from .validation import positive_int
from .serializers import (
    ConceptBookmarkSerializer,
    ConceptCatalogSerializer,
    ConceptDetailSerializer,
    ConceptListSerializer,
    ConceptNoteSerializer,
    DailyChallengeSerializer,
    FlashcardProgressSerializer,
    FlashcardSerializer,
)




def _positive_int(value, *, field):
    return positive_int(value, field=field)


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
            "therapy_links__therapy__family",
            "therapy_links__source_links__source",
            "technique_links__technique",
            "technique_links__source_links__source",
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
        return Response({
            "query": q,
            "disorders": [],
            "concepts": [],
            "symptoms": [],
            "therapies": [],
            "techniques": [],
        })

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

    therapy_base = Therapy.objects.filter(is_active=True, family__is_active=True).select_related("family")
    therapy_exact = (
        Q(name_en__iexact=q)
        | Q(name_fa__iexact=q)
        | Q(slug__iexact=q)
        | Q(aliases__text__iexact=q)
    )
    therapies = therapy_base.filter(therapy_exact)
    if not therapies.exists():
        therapies = therapy_base.filter(icontains_any(
            (
                "slug", "name_en", "name_fa", "summary", "academic_definition",
                "core_principles", "aliases__text", "family__name_en", "family__name_fa",
            ),
            q,
        ))
    therapies = therapies.prefetch_related(
        "aliases",
        "classification_links__classification",
        "technique_links__technique",
        "disorder_links__disorder",
        "concept_links__concept",
    ).distinct()[:10]

    technique_base = Technique.objects.filter(is_active=True)
    technique_exact = (
        Q(name_en__iexact=q)
        | Q(name_fa__iexact=q)
        | Q(slug__iexact=q)
        | Q(aliases__text__iexact=q)
    )
    techniques = technique_base.filter(technique_exact)
    if not techniques.exists():
        techniques = technique_base.filter(icontains_any(
            ("slug", "name_en", "name_fa", "summary", "academic_definition", "aliases__text"),
            q,
        ))
    techniques = techniques.prefetch_related(
        "aliases",
        "therapy_links__therapy__family",
        "concept_links__concept",
    ).distinct()[:10]

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
        "therapies": TherapyListSerializer(therapies, many=True).data,
        "techniques": TechniqueListSerializer(techniques, many=True).data,
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
        .values_list(
            "source__linked_disorder_id",
            "source__linked_disorder__slug",
            "target__linked_disorder_id",
            "target__linked_disorder__slug",
        )
        .order_by("source__linked_disorder_id", "target__linked_disorder_id")
    )
    seen = set()
    edges = []
    for source_id, source_slug, target_id, target_slug in rows:
        if not source_id or not target_id or source_id == target_id:
            continue
        pair = tuple(sorted((source_id, target_id)))
        if pair in seen:
            continue
        seen.add(pair)
        edges.append((source_id, source_slug, target_id, target_slug))
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
    therapy_count = Therapy.objects.filter(is_active=True, family__is_active=True).count()
    technique_count = Technique.objects.filter(is_active=True).count()
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
        + TherapyDisorder.objects.filter(
            is_active=True,
            therapy__is_active=True,
            therapy__family__is_active=True,
            disorder__is_active=True,
        ).count()
        + TherapyConcept.objects.filter(
            is_active=True,
            therapy__is_active=True,
            therapy__family__is_active=True,
            concept__is_active=True,
        ).count()
        + TherapyTechnique.objects.filter(
            is_active=True,
            therapy__is_active=True,
            therapy__family__is_active=True,
            technique__is_active=True,
        ).count()
        + TechniqueConcept.objects.filter(
            is_active=True,
            technique__is_active=True,
            concept__is_active=True,
        ).count()
        + len(dsm_nearby_edges)
    )

    return Response({
        "counts": {
            "categories": len(categories),
            "disorders": Disorder.objects.filter(is_active=True).count(),
            "concepts": Concept.objects.filter(is_active=True).count(),
            "symptoms": symptom_count,
            "therapies": therapy_count,
            "techniques": technique_count,
            "flashcards": available_flashcards().count(),
            "daily_challenges": valid_challenges.count(),
            "quizzes": valid_quizzes.count(),
            "clinical_cases": valid_cases.count(),
        },
        "graph": {
            "nodes": (
                Disorder.objects.filter(is_active=True).count()
                + Concept.objects.filter(is_active=True).count()
                + symptom_count
                + therapy_count
                + technique_count
            ),
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
@permission_classes([permissions.IsAuthenticated])
def review_queue(request):
    try:
        limit = positive_int(request.query_params.get("limit", "20"), field="limit", maximum=50)
    except ValidationError:
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
    choice = get_object_or_404(challenge.choices.filter(is_active=True), id=choice_id)
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
    distortion_attempts = CognitiveDistortionPracticeAttempt.objects.filter(user=request.user)
    distortion_total = distortion_attempts.count()
    distortion_correct = distortion_attempts.filter(is_correct=True).count()
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
        "distortion_practice": {
            "attempts": distortion_total,
            "correct": distortion_correct,
            "accuracy": round((distortion_correct / distortion_total) * 100) if distortion_total else 0,
        },
    })


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
from .serializers import ConceptCatalogSerializer, ConceptListSerializer
from .validation import positive_int






def _build_atlas_graph():
    concepts = list(Concept.objects.filter(is_active=True).order_by("name_en"))
    disorders = list(Disorder.objects.filter(is_active=True).select_related("category").order_by("name_en"))
    therapies = list(
        Therapy.objects.filter(is_active=True, family__is_active=True)
        .select_related("family")
        .order_by("name_en")
    )
    techniques = list(Technique.objects.filter(is_active=True).order_by("name_en"))
    concept_ids = {concept.id for concept in concepts}
    disorder_ids = {disorder.id for disorder in disorders}
    therapy_ids = {therapy.id for therapy in therapies}
    technique_ids = {technique.id for technique in techniques}
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

    def edge_sources(link):
        return [
            {
                "title": source_link.source.title,
                "organization": source_link.source.organization,
                "url": source_link.source.url,
            }
            for source_link in link.source_links.all()
        ]

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

    for link in (
        TherapyDisorder.objects.filter(
            is_active=True,
            therapy_id__in=therapy_ids,
            disorder_id__in=disorder_ids,
        )
        .select_related("therapy", "disorder")
        .prefetch_related(Prefetch("source_links", queryset=TherapyDisorderSource.objects.select_related("source")))
        .order_by("therapy_id", "sort_order", "id")
    ):
        edges.append({
            "source": f"therapy:{link.therapy.slug}",
            "target": f"disorder:{link.disorder.slug}",
            "kind": f"therapy_disorder_{link.clinical_role}",
            "explanation": link.explanation or link.evidence_note,
            "sources": edge_sources(link),
        })

    for link in (
        TherapyConcept.objects.filter(
            is_active=True,
            therapy_id__in=therapy_ids,
            concept_id__in=concept_ids,
        )
        .select_related("therapy", "concept")
        .prefetch_related(Prefetch("source_links", queryset=TherapyConceptSource.objects.select_related("source")))
        .order_by("therapy_id", "sort_order", "id")
    ):
        edges.append({
            "source": f"therapy:{link.therapy.slug}",
            "target": f"concept:{link.concept.slug}",
            "kind": f"therapy_concept_{link.relationship_type}",
            "explanation": link.explanation,
            "sources": edge_sources(link),
        })

    for link in (
        TherapyTechnique.objects.filter(
            is_active=True,
            therapy_id__in=therapy_ids,
            technique_id__in=technique_ids,
        )
        .select_related("therapy", "technique")
        .prefetch_related(Prefetch("source_links", queryset=TherapyTechniqueSource.objects.select_related("source")))
        .order_by("therapy_id", "sort_order", "id")
    ):
        edges.append({
            "source": f"therapy:{link.therapy.slug}",
            "target": f"technique:{link.technique.slug}",
            "kind": f"therapy_technique_{link.role}",
            "explanation": link.explanation,
            "sources": edge_sources(link),
        })

    for link in (
        TechniqueConcept.objects.filter(
            is_active=True,
            technique_id__in=technique_ids,
            concept_id__in=concept_ids,
        )
        .select_related("technique", "concept")
        .prefetch_related(Prefetch("source_links", queryset=TechniqueConceptSource.objects.select_related("source")))
        .order_by("technique_id", "sort_order", "id")
    ):
        edges.append({
            "source": f"technique:{link.technique.slug}",
            "target": f"concept:{link.concept.slug}",
            "kind": f"technique_concept_{link.relationship_type}",
            "explanation": link.explanation,
            "sources": edge_sources(link),
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

    nodes.extend({
        "id": f"therapy:{therapy.slug}",
        "type": "therapy",
        "slug": therapy.slug,
        "label": therapy.name_fa or therapy.name_en,
        "name_en": therapy.name_en,
        "name_fa": therapy.name_fa,
        "kind": therapy.family.slug,
        "group": therapy.family.name_fa or therapy.family.name_en,
        "family": therapy.family.slug,
        "review_status": therapy.review_status,
        "summary": therapy.summary,
        "href": f"/therapies/{therapy.slug}",
    } for therapy in therapies)

    nodes.extend({
        "id": f"technique:{technique.slug}",
        "type": "technique",
        "slug": technique.slug,
        "label": technique.name_fa or technique.name_en,
        "name_en": technique.name_en,
        "name_fa": technique.name_fa,
        "kind": "technique",
        "group": "تکنیک درمانی",
        "review_status": technique.review_status,
        "summary": technique.summary,
        "href": f"/techniques/{technique.slug}",
    } for technique in techniques)

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
    cache.delete("atlas_graph")


def _get_atlas_graph():
    payload = cache.get("atlas_graph")
    if payload is None:
        payload = _build_atlas_graph()
        cache.set("atlas_graph", payload, timeout=300)
    nodes, edges, edge_kinds = payload
    return [dict(node) for node in nodes], [dict(edge) for edge in edges], dict(edge_kinds)


def _filter_graph(nodes, edges, request):
    node_type = request.query_params.get("node_type", "").strip()
    domain = request.query_params.get("domain", "").strip()
    kind = request.query_params.get("kind", "").strip()
    subtype = request.query_params.get("subtype", "").strip()
    category = request.query_params.get("category", "").strip()
    family = request.query_params.get("family", "").strip()
    relation = request.query_params.get("relation", "").strip()
    raw_degree = request.query_params.get("min_degree", "").strip()

    if node_type and node_type not in {"all", "concept", "disorder", "symptom", "therapy", "technique"}:
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
        if family and (node["type"] != "therapy" or node.get("family") != family):
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
def concept_map(request):
    nodes, edges, all_edge_kinds = _get_atlas_graph()
    filtered_nodes, filtered_edges = _filter_graph(nodes, edges, request)
    node_types = {
        "concept": sum(1 for node in filtered_nodes if node["type"] == "concept"),
        "disorder": sum(1 for node in filtered_nodes if node["type"] == "disorder"),
        "symptom": sum(1 for node in filtered_nodes if node["type"] == "symptom"),
        "therapy": sum(1 for node in filtered_nodes if node["type"] == "therapy"),
        "technique": sum(1 for node in filtered_nodes if node["type"] == "technique"),
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
    if node_type and node_type not in {"all", "concept", "disorder", "symptom", "therapy", "technique"}:
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

def _therapy_detail_queryset():
    active_classifications = TherapyClassificationLink.objects.filter(
        is_active=True,
        classification__is_active=True,
    ).select_related("classification")
    active_technique_links = TherapyTechnique.objects.filter(
        is_active=True,
        technique__is_active=True,
    ).select_related("technique").prefetch_related(
        "technique__aliases",
        Prefetch(
            "technique__therapy_links",
            queryset=TherapyTechnique.objects.filter(
                is_active=True,
                therapy__is_active=True,
                therapy__family__is_active=True,
            ).select_related("therapy", "therapy__family"),
        ),
        Prefetch(
            "technique__concept_links",
            queryset=TechniqueConcept.objects.filter(
                is_active=True,
                concept__is_active=True,
            ).select_related("concept"),
        ),
        Prefetch(
            "source_links",
            queryset=TherapyTechniqueSource.objects.select_related("source"),
        ),
    )
    active_disorder_links = TherapyDisorder.objects.filter(
        is_active=True,
        disorder__is_active=True,
    ).select_related("disorder", "disorder__category").prefetch_related(
        Prefetch(
            "source_links",
            queryset=TherapyDisorderSource.objects.select_related("source"),
        )
    )
    active_concept_links = TherapyConcept.objects.filter(
        is_active=True,
        concept__is_active=True,
    ).select_related("concept").prefetch_related(
        "concept__aliases",
        Prefetch(
            "source_links",
            queryset=TherapyConceptSource.objects.select_related("source"),
        ),
    )
    return (
        Therapy.objects.filter(is_active=True, family__is_active=True)
        .select_related("family")
        .prefetch_related(
            "aliases",
            Prefetch("classification_links", queryset=active_classifications),
            Prefetch("source_links", queryset=TherapySource.objects.select_related("source")),
            Prefetch("technique_links", queryset=active_technique_links),
            Prefetch("disorder_links", queryset=active_disorder_links),
            Prefetch("concept_links", queryset=active_concept_links),
        )
    )


class TherapyListView(generics.ListAPIView):
    serializer_class = TherapyListSerializer

    def get_queryset(self):
        qs = (
            Therapy.objects.filter(is_active=True, family__is_active=True)
            .select_related("family")
            .prefetch_related(
                "aliases",
                "classification_links__classification",
                "technique_links__technique",
                "disorder_links__disorder",
                "concept_links__concept",
            )
        )
        q = self.request.query_params.get("q", "").strip()
        family = self.request.query_params.get("family", "").strip()
        classification = self.request.query_params.get("classification", "").strip()
        disorder = self.request.query_params.get("disorder", "").strip()
        concept = self.request.query_params.get("concept", "").strip()
        evidence_basis = self.request.query_params.get("evidence_basis", "").strip()
        clinical_role = self.request.query_params.get("clinical_role", "").strip()

        if q:
            exact_match = (
                Q(name_en__iexact=q)
                | Q(name_fa__iexact=q)
                | Q(slug__iexact=q)
                | Q(aliases__text__iexact=q)
            )
            if qs.filter(exact_match).exists():
                qs = qs.filter(exact_match)
            else:
                qs = qs.filter(icontains_any(
                    (
                        "name_en", "name_fa", "slug", "summary", "academic_definition",
                        "core_principles", "aliases__text", "family__name_en", "family__name_fa",
                    ),
                    q,
                ))
        if family:
            qs = qs.filter(family__slug=family)
        if classification:
            qs = qs.filter(
                classification_links__classification__slug=classification,
                classification_links__is_active=True,
                classification_links__classification__is_active=True,
            )
        if disorder:
            qs = qs.filter(
                disorder_links__disorder__slug=disorder,
                disorder_links__is_active=True,
                disorder_links__disorder__is_active=True,
            )
        if concept:
            qs = qs.filter(
                concept_links__concept__slug=concept,
                concept_links__is_active=True,
                concept_links__concept__is_active=True,
            )
        if evidence_basis:
            if evidence_basis not in TherapyDisorder.EvidenceBasis.values:
                raise ValidationError({"evidence_basis": "مبنای شواهد معتبر نیست."})
            qs = qs.filter(
                disorder_links__evidence_basis=evidence_basis,
                disorder_links__is_active=True,
                disorder_links__disorder__is_active=True,
            )
        if clinical_role:
            if clinical_role not in TherapyDisorder.ClinicalRole.values:
                raise ValidationError({"clinical_role": "نقش بالینی معتبر نیست."})
            qs = qs.filter(
                disorder_links__clinical_role=clinical_role,
                disorder_links__is_active=True,
                disorder_links__disorder__is_active=True,
            )
        return qs.distinct().order_by("name_en")


class TherapyDetailView(generics.RetrieveAPIView):
    serializer_class = TherapyDetailSerializer
    lookup_field = "slug"
    queryset = _therapy_detail_queryset()


@api_view(["GET"])
def compare_therapies(request):
    slugs = [value.strip() for value in request.query_params.get("slugs", "").split(",") if value.strip()]
    if not 2 <= len(slugs) <= 4:
        return Response({"detail": "بین ۲ تا ۴ درمان انتخاب کن."}, status=400)
    if len(set(slugs)) != len(slugs):
        return Response({"detail": "هر درمان فقط یک بار می‌تواند در مقایسه باشد."}, status=400)

    rows = list(_therapy_detail_queryset().filter(slug__in=slugs))
    by_slug = {row.slug: row for row in rows}
    missing = [slug for slug in slugs if slug not in by_slug]
    if missing:
        return Response({"detail": "یک یا چند درمان انتخاب‌شده پیدا نشد یا غیرفعال است."}, status=404)
    ordered = [by_slug[slug] for slug in slugs]
    return Response({
        "items": TherapyDetailSerializer(ordered, many=True).data,
        "note": "این جدول برای مقایسه ساختاریافته آموزشی است و رتبه‌بندی اثربخشی یا توصیه درمانی شخصی نیست.",
    })


@api_view(["GET"])
def therapy_taxonomy(request):
    families = TherapyFamily.objects.filter(is_active=True).order_by("sort_order", "name_en")
    classifications = TherapyClassification.objects.filter(is_active=True).order_by("kind", "sort_order", "name_en")
    return Response({
        "families": TherapyFamilySerializer(families, many=True).data,
        "classifications": TherapyClassificationSerializer(classifications, many=True).data,
        "clinical_roles": [
            {"value": value, "label": label}
            for value, label in TherapyDisorder.ClinicalRole.choices
        ],
        "evidence_bases": [
            {"value": value, "label": label}
            for value, label in TherapyDisorder.EvidenceBasis.choices
        ],
        "note": "این taxonomy آموزشی است؛ evidence_basis نوع منبع شواهد را نشان می‌دهد و رتبه‌بندی شخصی درمان نیست.",
    })


@api_view(["GET", "POST"])
@permission_classes([permissions.IsAuthenticated])
def therapy_bookmarks(request):
    qs = TherapyBookmark.objects.filter(
        user=request.user,
        therapy__is_active=True,
        therapy__family__is_active=True,
    ).select_related("therapy", "therapy__family").prefetch_related(
        "therapy__aliases",
        "therapy__classification_links__classification",
        "therapy__technique_links__technique",
        "therapy__disorder_links__disorder",
        "therapy__concept_links__concept",
    ).order_by("-created_at", "-id")
    if request.method == "GET":
        return Response(TherapyBookmarkSerializer(qs, many=True).data)

    payload = _object_payload(request)
    slug = payload.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        raise ValidationError({"slug": "شناسه درمان باید یک slug معتبر باشد."})
    therapy = get_object_or_404(Therapy.objects.filter(is_active=True, family__is_active=True), slug=slug.strip())
    bookmark, created = TherapyBookmark.objects.get_or_create(user=request.user, therapy=therapy)
    if created:
        record_activity(request.user, StudyActivity.Kind.BOOKMARK_SAVED, therapy=therapy)
    bookmark = qs.filter(pk=bookmark.pk).first() or bookmark
    return Response(TherapyBookmarkSerializer(bookmark).data, status=201 if created else 200)


@api_view(["DELETE"])
@permission_classes([permissions.IsAuthenticated])
def therapy_bookmark_delete(request, slug):
    TherapyBookmark.objects.filter(user=request.user, therapy__slug=slug).delete()
    return Response(status=204)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def therapy_notes(request):
    qs = TherapyNote.objects.filter(
        user=request.user,
        therapy__is_active=True,
        therapy__family__is_active=True,
    ).select_related("therapy", "therapy__family").prefetch_related(
        "therapy__aliases",
        "therapy__classification_links__classification",
        "therapy__technique_links__technique",
        "therapy__disorder_links__disorder",
        "therapy__concept_links__concept",
    ).order_by("-updated_at", "-id")
    return Response(TherapyNoteSerializer(qs, many=True).data)


@api_view(["GET", "PUT", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def therapy_note_detail(request, slug):
    therapy = get_object_or_404(Therapy.objects.filter(is_active=True, family__is_active=True), slug=slug)
    note = TherapyNote.objects.filter(user=request.user, therapy=therapy).first()

    if request.method == "GET":
        if not note:
            return Response({"therapy_slug": slug, "body": "", "exists": False})
        data = TherapyNoteSerializer(note).data
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
        return Response({"therapy_slug": slug, "body": "", "exists": False})

    note, _ = TherapyNote.objects.update_or_create(
        user=request.user,
        therapy=therapy,
        defaults={"body": body},
    )
    record_activity(request.user, StudyActivity.Kind.NOTE_SAVED, therapy=therapy)
    data = TherapyNoteSerializer(note).data
    data["exists"] = True
    return Response(data)


class TechniqueListView(generics.ListAPIView):
    serializer_class = TechniqueListSerializer

    def get_queryset(self):
        qs = Technique.objects.filter(is_active=True).prefetch_related(
            "aliases",
            "therapy_links__therapy__family",
            "concept_links__concept",
        )
        q = self.request.query_params.get("q", "").strip()
        therapy = self.request.query_params.get("therapy", "").strip()
        concept = self.request.query_params.get("concept", "").strip()
        if q:
            exact_match = (
                Q(name_en__iexact=q)
                | Q(name_fa__iexact=q)
                | Q(slug__iexact=q)
                | Q(aliases__text__iexact=q)
            )
            if qs.filter(exact_match).exists():
                qs = qs.filter(exact_match)
            else:
                qs = qs.filter(icontains_any(
                    ("name_en", "name_fa", "slug", "summary", "academic_definition", "aliases__text"),
                    q,
                ))
        if therapy:
            qs = qs.filter(
                therapy_links__therapy__slug=therapy,
                therapy_links__is_active=True,
                therapy_links__therapy__is_active=True,
                therapy_links__therapy__family__is_active=True,
            )
        if concept:
            qs = qs.filter(
                concept_links__concept__slug=concept,
                concept_links__is_active=True,
                concept_links__concept__is_active=True,
            )
        return qs.distinct().order_by("name_en")


class TechniqueDetailView(generics.RetrieveAPIView):
    serializer_class = TechniqueDetailSerializer
    lookup_field = "slug"
    queryset = Technique.objects.filter(is_active=True).prefetch_related(
        "aliases",
        "source_links__source",
        "therapy_links__therapy__family",
        "therapy_links__source_links__source",
        "concept_links__concept__aliases",
        "concept_links__source_links__source",
    )
