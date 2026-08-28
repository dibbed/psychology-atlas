from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    slug = models.SlugField(max_length=120, unique=True)
    name_en = models.CharField(max_length=200)
    name_fa = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "name_en")

    def __str__(self):
        return self.name_en


class Disorder(TimeStampedModel):
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="disorders")
    slug = models.SlugField(max_length=160, unique=True)
    name_en = models.CharField(max_length=220)
    name_fa = models.CharField(max_length=220, blank=True)
    short_description = models.TextField(blank=True)
    overview = models.TextField(blank=True)
    clinical_features = models.TextField(blank=True)
    risk_factors = models.TextField(blank=True)
    treatment_overview = models.TextField(blank=True)
    assessment_overview = models.TextField(blank=True)
    typical_onset = models.CharField(max_length=220, blank=True)
    course_note = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name_en",)
        indexes = [
            models.Index(fields=("category", "is_active")),
            models.Index(fields=("name_en",)),
            models.Index(fields=("name_fa",)),
        ]

    def __str__(self):
        return self.name_en


class Symptom(TimeStampedModel):
    class Domain(models.TextChoices):
        COGNITIVE = "cognitive", "Cognitive"
        EMOTIONAL = "emotional", "Emotional"
        BEHAVIORAL = "behavioral", "Behavioral"
        SOMATIC = "somatic", "Somatic"
        INTERPERSONAL = "interpersonal", "Interpersonal"
        OTHER = "other", "Other"

    slug = models.SlugField(max_length=160, unique=True)
    name_en = models.CharField(max_length=220)
    name_fa = models.CharField(max_length=220, blank=True)
    description = models.TextField(blank=True)
    domain = models.CharField(max_length=32, choices=Domain.choices, default=Domain.OTHER)

    def __str__(self):
        return self.name_en


class DisorderSymptom(models.Model):
    class Prominence(models.TextChoices):
        CORE = "core", "Core"
        COMMON = "common", "Common"
        POSSIBLE = "possible", "Possible"
        CONTEXTUAL = "contextual", "Contextual"

    disorder = models.ForeignKey(Disorder, on_delete=models.CASCADE, related_name="symptom_links")
    symptom = models.ForeignKey(Symptom, on_delete=models.PROTECT, related_name="disorder_links")
    prominence = models.CharField(max_length=32, choices=Prominence.choices, default=Prominence.COMMON)
    note = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("disorder", "symptom"), name="uq_disorder_symptom")
        ]


class DifferentialRelationship(TimeStampedModel):
    class Kind(models.TextChoices):
        DIFFERENTIAL = "differential", "Differential"
        RELATED = "related", "Related"
        COMMONLY_CONFUSED = "commonly_confused", "Commonly confused"

    disorder = models.ForeignKey(Disorder, on_delete=models.CASCADE, related_name="outgoing_relationships")
    related_disorder = models.ForeignKey(Disorder, on_delete=models.CASCADE, related_name="incoming_relationships")
    relationship_type = models.CharField(max_length=32, choices=Kind.choices)
    explanation = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("disorder", "related_disorder", "relationship_type"),
                name="uq_disorder_relationship",
            ),
            models.CheckConstraint(
                condition=~Q(disorder=F("related_disorder")),
                name="ck_relationship_not_self",
            ),
        ]


class SourceReference(TimeStampedModel):
    title = models.CharField(max_length=500)
    organization = models.CharField(max_length=255, blank=True)
    citation = models.TextField(blank=True)
    url = models.URLField(blank=True)
    publication_year = models.PositiveSmallIntegerField(null=True, blank=True)
    source_type = models.CharField(max_length=64, blank=True)


class DisorderSource(models.Model):
    disorder = models.ForeignKey(Disorder, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="disorder_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("disorder", "source"), name="uq_disorder_source")
        ]


class Quiz(TimeStampedModel):
    slug = models.SlugField(max_length=160, unique=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    disorder = models.ForeignKey(Disorder, on_delete=models.SET_NULL, null=True, blank=True, related_name="quizzes")
    is_active = models.BooleanField(default=True)


class QuizQuestion(TimeStampedModel):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    prompt = models.TextField()
    explanation = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")


class QuizChoice(models.Model):
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="choices")
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")


class QuizAttempt(TimeStampedModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    quiz = models.ForeignKey(Quiz, on_delete=models.PROTECT, related_name="attempts")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.IN_PROGRESS)
    score = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    correct_count = models.PositiveIntegerField(default=0)
    total_questions = models.PositiveIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("user", "status")),
            models.Index(fields=("user", "-created_at")),
        ]


class QuizAttemptAnswer(models.Model):
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(QuizQuestion, on_delete=models.PROTECT)
    selected_choice = models.ForeignKey(QuizChoice, on_delete=models.PROTECT)
    is_correct = models.BooleanField()
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("attempt", "question"), name="uq_quiz_attempt_question")
        ]


class ClinicalCase(TimeStampedModel):
    class Difficulty(models.TextChoices):
        INTRODUCTORY = "introductory", "Introductory"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    slug = models.SlugField(max_length=160, unique=True)
    title = models.CharField(max_length=255)
    patient_summary = models.TextField()
    educational_objective = models.TextField(blank=True)
    primary_disorder = models.ForeignKey(Disorder, on_delete=models.SET_NULL, null=True, blank=True, related_name="clinical_cases")
    difficulty = models.CharField(max_length=24, choices=Difficulty.choices, default=Difficulty.INTRODUCTORY)
    is_active = models.BooleanField(default=True)


class CaseStep(models.Model):
    case = models.ForeignKey(ClinicalCase, on_delete=models.CASCADE, related_name="steps")
    title = models.CharField(max_length=255, blank=True)
    narrative = models.TextField()
    sort_order = models.PositiveIntegerField()

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("case", "sort_order"), name="uq_case_step_order")
        ]


class CaseQuestion(TimeStampedModel):
    step = models.ForeignKey(CaseStep, on_delete=models.CASCADE, related_name="questions")
    prompt = models.TextField()
    explanation = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")


class CaseChoice(models.Model):
    question = models.ForeignKey(CaseQuestion, on_delete=models.CASCADE, related_name="choices")
    text = models.TextField()
    score_value = models.IntegerField(default=0)
    feedback = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")


class CaseAttempt(TimeStampedModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="case_attempts")
    case = models.ForeignKey(ClinicalCase, on_delete=models.PROTECT, related_name="attempts")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.IN_PROGRESS)
    score = models.IntegerField(default=0)
    max_score = models.IntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("user", "status")),
            models.Index(fields=("user", "-created_at")),
        ]


class CaseAttemptAnswer(models.Model):
    attempt = models.ForeignKey(CaseAttempt, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(CaseQuestion, on_delete=models.PROTECT)
    selected_choice = models.ForeignKey(CaseChoice, on_delete=models.PROTECT)
    awarded_score = models.IntegerField(default=0)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("attempt", "question"), name="uq_case_attempt_question")
        ]


class Bookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks")
    disorder = models.ForeignKey(Disorder, on_delete=models.CASCADE, related_name="bookmarked_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "disorder"), name="uq_user_disorder_bookmark")
        ]


class UserProgress(TimeStampedModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="learning_progress")
    disorder = models.ForeignKey(Disorder, on_delete=models.CASCADE, related_name="user_progress")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.IN_PROGRESS)
    progress_percent = models.PositiveSmallIntegerField(default=10, validators=[MinValueValidator(0), MaxValueValidator(100)])
    last_viewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "disorder"), name="uq_user_disorder_progress")
        ]


class UserNote(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="psychology_notes")
    disorder = models.ForeignKey(Disorder, on_delete=models.CASCADE, related_name="user_notes")
    body = models.TextField(blank=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(fields=("user", "disorder"), name="uq_user_disorder_note")
        ]

    def __str__(self):
        return f"{self.user_id}:{self.disorder.slug}"
