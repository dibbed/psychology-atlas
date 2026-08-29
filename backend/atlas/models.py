from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


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
    class Origin(models.TextChoices):
        CURATED = "curated", "Curated Atlas"
        DSM_MASTER = "dsm_master", "DSM MASTER"

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
    data_origin = models.CharField(max_length=24, choices=Origin.choices, default=Origin.CURATED, db_index=True)
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


class Concept(TimeStampedModel):
    class Kind(models.TextChoices):
        CLINICAL = "clinical", "Clinical"
        COGNITIVE = "cognitive", "Cognitive"
        BEHAVIORAL = "behavioral", "Behavioral"
        EMOTIONAL = "emotional", "Emotional"
        INTERPERSONAL = "interpersonal", "Interpersonal"
        ASSESSMENT = "assessment", "Assessment"
        TREATMENT = "treatment", "Treatment"
        GENERAL = "general", "General"

    slug = models.SlugField(max_length=160, unique=True)
    name_en = models.CharField(max_length=220)
    name_fa = models.CharField(max_length=220, blank=True)
    simple_definition = models.TextField()
    academic_definition = models.TextField(blank=True)
    example = models.TextField(blank=True)
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.GENERAL)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name_en",)
        indexes = [
            models.Index(fields=("kind", "is_active")),
            models.Index(fields=("name_en",)),
            models.Index(fields=("name_fa",)),
        ]

    def __str__(self):
        return self.name_en


class ConceptRelationship(TimeStampedModel):
    class Kind(models.TextChoices):
        RELATED = "related", "Related"
        PART_OF = "part_of", "Part of"
        MAINTAINS = "maintains", "Maintains"
        INFLUENCES = "influences", "Influences"
        CONTRASTS = "contrasts", "Contrasts with"
        APPLIED_IN = "applied_in", "Applied in"

    source_concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="outgoing_concept_relationships")
    target_concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="incoming_concept_relationships")
    relationship_type = models.CharField(max_length=32, choices=Kind.choices, default=Kind.RELATED)
    explanation = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("source_concept", "target_concept", "relationship_type"),
                name="uq_concept_relationship",
            ),
            models.CheckConstraint(
                condition=~Q(source_concept=F("target_concept")),
                name="ck_concept_relationship_not_self",
            ),
        ]


class DisorderConcept(TimeStampedModel):
    class Role(models.TextChoices):
        CORE = "core", "Core"
        ASSOCIATED = "associated", "Associated"
        MAINTAINING = "maintaining", "Maintaining"
        ASSESSMENT = "assessment", "Assessment"
        TREATMENT = "treatment", "Treatment"
        DIFFERENTIAL = "differential", "Differential"

    disorder = models.ForeignKey(Disorder, on_delete=models.CASCADE, related_name="concept_links")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="disorder_links")
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.ASSOCIATED)
    explanation = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("disorder", "concept", "role"), name="uq_disorder_concept_role")
        ]


class ConceptSource(models.Model):
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="concept_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("concept", "source"), name="uq_concept_source")
        ]


class Flashcard(TimeStampedModel):
    class Difficulty(models.TextChoices):
        BASIC = "basic", "Basic"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    slug = models.SlugField(max_length=180, unique=True)
    front = models.TextField()
    back = models.TextField()
    hint = models.TextField(blank=True)
    concept = models.ForeignKey(Concept, on_delete=models.SET_NULL, null=True, blank=True, related_name="flashcards")
    disorder = models.ForeignKey(Disorder, on_delete=models.SET_NULL, null=True, blank=True, related_name="flashcards")
    difficulty = models.CharField(max_length=24, choices=Difficulty.choices, default=Difficulty.BASIC)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "id")
        indexes = [models.Index(fields=("is_active", "difficulty"))]

    def __str__(self):
        return self.slug


class UserFlashcardProgress(TimeStampedModel):
    class State(models.TextChoices):
        NEW = "new", "New"
        LEARNING = "learning", "Learning"
        REVIEW = "review", "Review"

    class Rating(models.TextChoices):
        AGAIN = "again", "Again"
        HARD = "hard", "Hard"
        GOOD = "good", "Good"
        EASY = "easy", "Easy"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="flashcard_progress")
    flashcard = models.ForeignKey(Flashcard, on_delete=models.CASCADE, related_name="user_progress")
    state = models.CharField(max_length=20, choices=State.choices, default=State.NEW)
    due_at = models.DateTimeField(default=timezone.now)
    interval_days = models.PositiveIntegerField(default=0)
    ease_factor = models.FloatField(default=2.5, validators=[MinValueValidator(1.3), MaxValueValidator(4.0)])
    repetitions = models.PositiveIntegerField(default=0)
    lapses = models.PositiveIntegerField(default=0)
    last_rating = models.CharField(max_length=16, choices=Rating.choices, blank=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "flashcard"), name="uq_user_flashcard_progress")
        ]
        indexes = [models.Index(fields=("user", "due_at"))]


class StudyActivity(models.Model):
    class Kind(models.TextChoices):
        DISORDER_VIEW = "disorder_view", "Disorder view"
        CONCEPT_VIEW = "concept_view", "Concept view"
        QUIZ_COMPLETED = "quiz_completed", "Quiz completed"
        CASE_COMPLETED = "case_completed", "Case completed"
        FLASHCARD_REVIEW = "flashcard_review", "Flashcard review"
        DAILY_CHALLENGE = "daily_challenge", "Daily challenge"
        NOTE_SAVED = "note_saved", "Note saved"
        BOOKMARK_SAVED = "bookmark_saved", "Bookmark saved"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="study_activities")
    activity_type = models.CharField(max_length=32, choices=Kind.choices)
    disorder = models.ForeignKey(Disorder, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_activities")
    concept = models.ForeignKey(Concept, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_activities")
    quiz = models.ForeignKey(Quiz, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_activities")
    clinical_case = models.ForeignKey(ClinicalCase, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_activities")
    flashcard = models.ForeignKey(Flashcard, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_activities")
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-occurred_at", "-id")
        indexes = [models.Index(fields=("user", "-occurred_at")), models.Index(fields=("user", "activity_type"))]


class UserConceptProgress(TimeStampedModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="concept_progress")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="user_progress")
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.IN_PROGRESS)
    progress_percent = models.PositiveSmallIntegerField(default=10, validators=[MinValueValidator(0), MaxValueValidator(100)])
    last_viewed_at = models.DateTimeField(null=True, blank=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "concept"), name="uq_user_concept_progress")
        ]
        indexes = [models.Index(fields=("user", "progress_percent"))]


class ConceptBookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="concept_bookmarks")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="bookmarked_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "concept"), name="uq_user_concept_bookmark")
        ]


class ConceptNote(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="concept_notes")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="user_notes")
    body = models.TextField(blank=True)

    class Meta:
        ordering = ("-updated_at",)
        constraints = [
            models.UniqueConstraint(fields=("user", "concept"), name="uq_user_concept_note")
        ]


class DailyChallenge(TimeStampedModel):
    prompt = models.TextField()
    explanation = models.TextField(blank=True)
    concept = models.ForeignKey(Concept, on_delete=models.SET_NULL, null=True, blank=True, related_name="daily_challenges")
    disorder = models.ForeignKey(Disorder, on_delete=models.SET_NULL, null=True, blank=True, related_name="daily_challenges")
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "id")


class DailyChallengeChoice(models.Model):
    challenge = models.ForeignKey(DailyChallenge, on_delete=models.CASCADE, related_name="choices")
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")


class DailyChallengeAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_challenge_attempts")
    challenge = models.ForeignKey(DailyChallenge, on_delete=models.PROTECT, related_name="attempts")
    activity_date = models.DateField()
    selected_choice = models.ForeignKey(DailyChallengeChoice, on_delete=models.PROTECT)
    is_correct = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("user", "activity_date"), name="uq_user_daily_challenge_date")
        ]
        indexes = [models.Index(fields=("user", "-activity_date"))]


class DSMCorpus(TimeStampedModel):
    """One imported DSM MASTER educational corpus.

    The original JSON is retained verbatim as parsed JSON so the normalized
    record index never becomes the only copy of source-provided information.
    """

    key = models.SlugField(max_length=160, unique=True)
    title = models.CharField(max_length=500)
    version_name = models.CharField(max_length=300, blank=True)
    version_date = models.DateField(null=True, blank=True)
    language = models.CharField(max_length=80, blank=True)
    purpose = models.TextField(blank=True)
    copyright_note = models.TextField(blank=True)
    clinical_note = models.TextField(blank=True)
    source_filename = models.CharField(max_length=500)
    source_sha256 = models.CharField(max_length=64, db_index=True)
    official_status = models.JSONField(default=dict, blank=True)
    source_registry = models.JSONField(default=dict, blank=True)
    quality_audit = models.JSONField(default=dict, blank=True)
    stats = models.JSONField(default=dict, blank=True)
    study_guide = models.JSONField(default=list, blank=True)
    urgent_warnings = models.JSONField(default=dict, blank=True)
    cultural_note = models.TextField(blank=True)
    periodic_review = models.JSONField(default=list, blank=True)
    release_updates = models.JSONField(default=dict, blank=True)
    health_check = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    raw_document = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-version_date", "-id")

    def __str__(self):
        return self.version_name or self.title


class DSMRecord(TimeStampedModel):
    class DisplayType(models.TextChoices):
        DIAGNOSIS = "diagnosis", "Diagnosis"
        STRUCTURAL = "structural", "Structural"
        CLINICAL_ATTENTION = "clinical_attention", "Clinical attention"
        RESEARCH = "research", "Research condition"
        ALTERNATIVE_MODEL = "alternative_model", "Alternative model"
        SPECIFIER = "specifier", "Specifier"
        REFERENCE = "reference", "Structural reference"
        CODE = "code", "Additional code"
        OTHER = "other", "Other"

    corpus = models.ForeignKey(DSMCorpus, on_delete=models.CASCADE, related_name="records")
    master_id = models.CharField(max_length=40, db_index=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    linked_disorder = models.ForeignKey(
        Disorder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dsm_master_records",
    )
    sort_index = models.PositiveIntegerField(default=0)
    root_section = models.CharField(max_length=180, blank=True, db_index=True)
    chapter_number = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    chapter_name_fa = models.CharField(max_length=300, blank=True)
    chapter_name_en = models.CharField(max_length=300, blank=True)
    group_name = models.CharField(max_length=300, blank=True)
    name_fa = models.CharField(max_length=500, blank=True, db_index=True)
    name_en = models.CharField(max_length=500, blank=True, db_index=True)
    source_type = models.CharField(max_length=200, blank=True)
    classification_status = models.CharField(max_length=300, blank=True, db_index=True)
    display_type = models.CharField(
        max_length=32,
        choices=DisplayType.choices,
        default=DisplayType.OTHER,
        db_index=True,
    )
    specialization_level = models.CharField(max_length=220, blank=True)
    summary = models.TextField(blank=True)
    key_features = models.JSONField(default=list, blank=True)
    assessment = models.JSONField(default=list, blank=True)
    differential = models.JSONField(default=list, blank=True)
    comorbidity = models.TextField(blank=True)
    course = models.TextField(blank=True)
    management = models.JSONField(default=list, blank=True)
    assessment_tools = models.JSONField(default=list, blank=True)
    context_considerations = models.TextField(blank=True)
    red_flags = models.TextField(blank=True)
    pitfalls = models.JSONField(default=list, blank=True)
    nearby_titles = models.JSONField(default=list, blank=True)
    official_updates = models.JSONField(default=list, blank=True)
    homonym_info = models.JSONField(default=dict, blank=True)
    prevalence_numeric = models.JSONField(null=True, blank=True)
    prevalence_policy = models.TextField(blank=True)
    coding = models.TextField(blank=True)
    source_keys = models.JSONField(default=list, blank=True)
    quality = models.JSONField(default=dict, blank=True)
    exam_tip = models.TextField(blank=True)
    self_test = models.JSONField(default=list, blank=True)
    structural_path = models.JSONField(default=dict, blank=True)
    search_text = models.TextField(blank=True)
    source_payload = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_index", "master_id")
        constraints = [
            models.UniqueConstraint(fields=("corpus", "master_id"), name="uq_dsm_corpus_master_id")
        ]
        indexes = [
            models.Index(fields=("corpus", "display_type", "sort_index")),
            models.Index(fields=("corpus", "chapter_number", "sort_index")),
            models.Index(fields=("linked_disorder", "is_active")),
        ]

    def __str__(self):
        return f"{self.master_id}: {self.name_en or self.name_fa}"


class DSMRecordRelation(TimeStampedModel):
    class Kind(models.TextChoices):
        NEARBY = "nearby", "Nearby title"
        DIFFERENTIAL = "differential", "Differential title"

    source = models.ForeignKey(DSMRecord, on_delete=models.CASCADE, related_name="outgoing_dsm_relations")
    target = models.ForeignKey(DSMRecord, on_delete=models.CASCADE, related_name="incoming_dsm_relations")
    relationship_type = models.CharField(max_length=24, choices=Kind.choices)
    explanation = models.TextField(blank=True)

    class Meta:
        ordering = ("source__sort_index", "target__sort_index", "relationship_type")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "target", "relationship_type"),
                name="uq_dsm_record_relation",
            ),
            models.CheckConstraint(
                condition=~Q(source=F("target")),
                name="ck_dsm_record_relation_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=("source", "relationship_type")),
            models.Index(fields=("target", "relationship_type")),
        ]
