from collections.abc import Mapping

from django.contrib.auth.models import User
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
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
        )
    )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        if request.user.is_authenticated:
            progress, _ = UserProgress.objects.get_or_create(user=request.user, disorder=instance)
            progress.progress_percent = max(progress.progress_percent, 20)
            progress.last_viewed_at = timezone.now()
            progress.save(update_fields=("progress_percent", "last_viewed_at", "updated_at"))
        return Response(self.get_serializer(instance).data)


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
        "saved_topics": bookmarks_qs.count() + concept_bookmarks_qs.count(),
        "disorders_studied": progress_qs.count(),
        "concepts_studied": concept_progress_qs.count(),
        "concepts_mastered": concept_progress_qs.filter(status=UserConceptProgress.Status.COMPLETED).count(),
        "topics_studied": progress_qs.count() + concept_progress_qs.count(),
        "quizzes_completed": completed_quizzes,
        "quiz_accuracy": avg_quiz_score,
        "cases_completed": completed_cases,
        "case_accuracy": avg_case_score,
        "notes_count": notes_qs.count() + concept_notes_qs.count(),
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
