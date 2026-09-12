from django.conf import settings
from django.core.exceptions import ValidationError
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
    url = models.URLField(max_length=1000, blank=True)
    publication_year = models.PositiveSmallIntegerField(null=True, blank=True)
    source_type = models.CharField(max_length=64, blank=True)
    authors = models.JSONField(default=list, blank=True)
    doi = models.CharField(max_length=255, blank=True, db_index=True)
    pmid = models.CharField(max_length=64, blank=True, db_index=True)
    verification_status = models.CharField(max_length=64, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("title",)),
            models.Index(fields=("publication_year",)),
        ]


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
    seed_managed = models.BooleanField(default=False)


class QuizQuestion(TimeStampedModel):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    prompt = models.TextField()
    explanation = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "id")


class QuizChoice(models.Model):
    question = models.ForeignKey(QuizQuestion, on_delete=models.CASCADE, related_name="choices")
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

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

    class StructureMode(models.TextChoices):
        LINEAR = "linear", "Linear"
        BRANCHING = "branching", "Branching"

    slug = models.SlugField(max_length=160, unique=True)
    title = models.CharField(max_length=255)
    patient_summary = models.TextField()
    educational_objective = models.TextField(blank=True)
    primary_disorder = models.ForeignKey(Disorder, on_delete=models.SET_NULL, null=True, blank=True, related_name="clinical_cases")
    difficulty = models.CharField(max_length=24, choices=Difficulty.choices, default=Difficulty.INTRODUCTORY)
    structure_mode = models.CharField(max_length=24, choices=StructureMode.choices, default=StructureMode.LINEAR, db_index=True)
    current_revision = models.ForeignKey(
        "CaseRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_for_cases",
    )
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    def clean(self):
        super().clean()
        if self.current_revision_id:
            if self.current_revision.case_id != self.id:
                raise ValidationError({"current_revision": "Current revision must belong to this clinical case."})
            if self.current_revision.status != CaseRevision.Status.PUBLISHED:
                raise ValidationError({"current_revision": "Current revision must be published."})


class CaseRevision(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        RETIRED = "retired", "Retired"

    case = models.ForeignKey(ClinicalCase, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=255, blank=True)
    patient_summary = models.TextField(blank=True)
    educational_objective = models.TextField(blank=True)
    difficulty = models.CharField(max_length=24, choices=ClinicalCase.Difficulty.choices, default=ClinicalCase.Difficulty.INTRODUCTORY)
    primary_disorder = models.ForeignKey(
        Disorder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="clinical_case_revisions",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PUBLISHED, db_index=True)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    entry_step = models.ForeignKey(
        "CaseStep",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="entry_for_revisions",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("case_id", "version")
        constraints = [
            models.UniqueConstraint(fields=("case", "version"), name="uq_case_revision_version"),
        ]
        indexes = [
            models.Index(fields=("case", "status")),
        ]

    def clean(self):
        super().clean()
        if self.entry_step_id:
            if self.entry_step.case_id != self.case_id:
                raise ValidationError({"entry_step": "Entry step must belong to the same clinical case."})
            if self.entry_step.revision_id != self.id:
                raise ValidationError({"entry_step": "Entry step must belong to this case revision."})


class CaseStep(models.Model):
    class NodeKind(models.TextChoices):
        DECISION = "decision", "Decision"
        INFORMATION = "information", "Information"
        TERMINAL = "terminal", "Terminal"

    case = models.ForeignKey(ClinicalCase, on_delete=models.CASCADE, related_name="steps")
    revision = models.ForeignKey(CaseRevision, on_delete=models.PROTECT, related_name="steps")
    stable_key = models.SlugField(max_length=120)
    node_kind = models.CharField(max_length=24, choices=NodeKind.choices, default=NodeKind.DECISION)
    title = models.CharField(max_length=255, blank=True)
    narrative = models.TextField()
    sort_order = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("revision", "stable_key"), name="uq_case_revision_step_key"),
            models.UniqueConstraint(fields=("revision", "sort_order"), name="uq_case_revision_step_order"),
        ]
        indexes = [
            models.Index(fields=("case", "revision", "is_active")),
        ]

    def clean(self):
        super().clean()
        if self.revision_id and self.case_id and self.revision.case_id != self.case_id:
            raise ValidationError({"revision": "Step revision must belong to the same clinical case."})


class CaseQuestion(TimeStampedModel):
    step = models.ForeignKey(CaseStep, on_delete=models.CASCADE, related_name="questions")
    prompt = models.TextField()
    explanation = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "id")


class CaseChoice(models.Model):
    question = models.ForeignKey(CaseQuestion, on_delete=models.CASCADE, related_name="choices")
    text = models.TextField()
    score_value = models.IntegerField(default=0)
    feedback = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "id")


class CaseTransition(models.Model):
    class Outcome(models.TextChoices):
        CONTINUE = "continue", "Continue"
        COMPLETE = "complete", "Complete"

    revision = models.ForeignKey(CaseRevision, on_delete=models.CASCADE, related_name="transitions")
    source_step = models.ForeignKey(CaseStep, on_delete=models.CASCADE, related_name="outgoing_transitions")
    choice = models.OneToOneField(
        CaseChoice,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="branch_transition",
    )
    target_step = models.ForeignKey(
        CaseStep,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incoming_transitions",
    )
    outcome = models.CharField(max_length=24, choices=Outcome.choices, default=Outcome.CONTINUE)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("source_step__sort_order", "sort_order", "id")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(outcome="continue", target_step__isnull=False)
                    | Q(outcome="complete", target_step__isnull=True)
                ),
                name="ck_case_transition_target_by_outcome",
            ),
            models.UniqueConstraint(
                fields=("revision", "source_step"),
                condition=Q(choice__isnull=True, is_active=True),
                name="uq_active_case_auto_transition",
            ),
        ]
        indexes = [
            models.Index(fields=("revision", "source_step", "is_active")),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.source_step_id and self.source_step.revision_id != self.revision_id:
            errors["source_step"] = "Source step must belong to this revision."
        if self.target_step_id and self.target_step.revision_id != self.revision_id:
            errors["target_step"] = "Target step must belong to this revision."
        if self.choice_id and self.source_step_id and self.choice.question.step_id != self.source_step_id:
            errors["choice"] = "Transition choice must belong to the source step."
        if self.outcome == self.Outcome.CONTINUE and not self.target_step_id:
            errors["target_step"] = "Continue transitions require a target step."
        if self.outcome == self.Outcome.COMPLETE and self.target_step_id:
            errors["target_step"] = "Complete transitions cannot target another step."
        if errors:
            raise ValidationError(errors)


class CaseAttempt(TimeStampedModel):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="case_attempts")
    case = models.ForeignKey(ClinicalCase, on_delete=models.PROTECT, related_name="attempts")
    revision = models.ForeignKey(CaseRevision, on_delete=models.PROTECT, related_name="attempts")
    current_step = models.ForeignKey(
        CaseStep,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="current_attempts",
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.IN_PROGRESS)
    state_version = models.PositiveIntegerField(default=0)
    score = models.IntegerField(default=0)
    max_score = models.IntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=("user", "status")),
            models.Index(fields=("user", "case", "status")),
            models.Index(fields=("user", "-created_at")),
            models.Index(fields=("case", "revision", "status")),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.revision_id and self.case_id and self.revision.case_id != self.case_id:
            errors["revision"] = "Attempt revision must belong to the selected clinical case."
        if self.current_step_id:
            if self.current_step.case_id != self.case_id:
                errors["current_step"] = "Current step must belong to the selected clinical case."
            if self.current_step.revision_id != self.revision_id:
                errors["current_step"] = "Current step must belong to the attempt revision."
        if self.status == self.Status.IN_PROGRESS and not self.current_step_id:
            errors["current_step"] = "In-progress attempts require a current step."
        if errors:
            raise ValidationError(errors)


class CaseAttemptEvent(models.Model):
    class EventType(models.TextChoices):
        DECISION = "decision", "Decision"
        ADVANCE = "advance", "Advance"
        TERMINAL_COMPLETE = "terminal_complete", "Terminal complete"

    attempt = models.ForeignKey(CaseAttempt, on_delete=models.CASCADE, related_name="events")
    step = models.ForeignKey(CaseStep, on_delete=models.PROTECT, related_name="attempt_events")
    event_type = models.CharField(max_length=32, choices=EventType.choices)
    question = models.ForeignKey(CaseQuestion, on_delete=models.PROTECT, null=True, blank=True)
    selected_choice = models.ForeignKey(CaseChoice, on_delete=models.PROTECT, null=True, blank=True)
    transition = models.ForeignKey(CaseTransition, on_delete=models.PROTECT, null=True, blank=True)
    next_step = models.ForeignKey(
        CaseStep,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incoming_attempt_events",
    )
    outcome = models.CharField(max_length=24, choices=CaseTransition.Outcome.choices)
    awarded_score = models.IntegerField(default=0)
    max_score = models.IntegerField(default=0)
    state_version_before = models.PositiveIntegerField()
    state_version_after = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(fields=("attempt", "step"), name="uq_case_attempt_event_step"),
            models.UniqueConstraint(fields=("attempt", "state_version_before"), name="uq_case_attempt_event_version"),
        ]
        indexes = [
            models.Index(fields=("attempt", "created_at")),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.step_id and self.attempt_id and self.step.revision_id != self.attempt.revision_id:
            errors["step"] = "Event step must belong to the attempt revision."
        if self.state_version_after != self.state_version_before + 1:
            errors["state_version_after"] = "Event state version must advance exactly once."
        if self.event_type == self.EventType.DECISION:
            if not self.question_id or not self.selected_choice_id or not self.transition_id:
                errors["event_type"] = "Decision events require question, choice, and transition."
            else:
                if self.question.step_id != self.step_id:
                    errors["question"] = "Decision question must belong to the event step."
                if self.selected_choice.question_id != self.question_id:
                    errors["selected_choice"] = "Decision choice must belong to the event question."
                if self.transition.source_step_id != self.step_id or self.transition.choice_id != self.selected_choice_id:
                    errors["transition"] = "Decision transition must match the event step and selected choice."
        elif self.event_type == self.EventType.ADVANCE:
            if self.question_id or self.selected_choice_id or not self.transition_id:
                errors["event_type"] = "Advance events require an automatic transition and no question or choice."
            elif self.transition.source_step_id != self.step_id or self.transition.choice_id is not None:
                errors["transition"] = "Advance transition must be automatic and belong to the event step."
        elif self.event_type == self.EventType.TERMINAL_COMPLETE:
            if self.question_id or self.selected_choice_id or self.transition_id or self.next_step_id:
                errors["event_type"] = "Terminal completion cannot include question, choice, transition, or next step."
            if self.step.node_kind != CaseStep.NodeKind.TERMINAL:
                errors["step"] = "Terminal completion requires a terminal step."
        if self.transition_id:
            if self.transition.revision_id != self.attempt.revision_id:
                errors["transition"] = "Event transition must belong to the attempt revision."
            if self.outcome != self.transition.outcome:
                errors["outcome"] = "Event outcome must match the selected transition."
            if self.next_step_id != self.transition.target_step_id:
                errors["next_step"] = "Event next step must match the selected transition."
        elif self.event_type == self.EventType.TERMINAL_COMPLETE and self.outcome != CaseTransition.Outcome.COMPLETE:
            errors["outcome"] = "Terminal completion must use a complete outcome."
        if self.next_step_id and self.next_step.revision_id != self.attempt.revision_id:
            errors["next_step"] = "Event next step must belong to the attempt revision."
        if errors:
            raise ValidationError(errors)


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

    def clean(self):
        super().clean()
        errors = {}
        if self.selected_choice_id and self.question_id and self.selected_choice.question_id != self.question_id:
            errors["selected_choice"] = "Selected choice must belong to the selected question."
        if self.attempt_id and self.question_id and self.question.step.revision_id != self.attempt.revision_id:
            errors["question"] = "Question must belong to the same case revision as the attempt."
        if errors:
            raise ValidationError(errors)


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

    class Domain(models.TextChoices):
        PSYCHOPATHOLOGY = "psychopathology", "Psychopathology"
        COGNITIVE_PSYCHOLOGY = "cognitive_psychology", "Cognitive Psychology"
        CBT = "cbt", "Cognitive Behavioral Therapy"
        BEHAVIORAL_SCIENCE = "behavioral_science", "Behavioral Science"
        EMOTION = "emotion", "Emotion"
        INTERPERSONAL = "interpersonal", "Interpersonal"
        ASSESSMENT = "assessment", "Assessment"
        GENERAL = "general", "General Psychology"

    class Subtype(models.TextChoices):
        GENERAL = "general", "General concept"
        COGNITIVE_DISTORTION = "cognitive_distortion", "Cognitive distortion"

    slug = models.SlugField(max_length=160, unique=True)
    name_en = models.CharField(max_length=220)
    name_fa = models.CharField(max_length=220, blank=True)
    simple_definition = models.TextField()
    academic_definition = models.TextField(blank=True)
    example = models.TextField(blank=True)
    counterexample = models.TextField(blank=True)
    recognition_cues = models.TextField(blank=True)
    common_confusions = models.TextField(blank=True)
    kind = models.CharField(max_length=32, choices=Kind.choices, default=Kind.GENERAL)
    domain = models.CharField(max_length=48, choices=Domain.choices, default=Domain.GENERAL, db_index=True)
    subtype = models.CharField(max_length=48, choices=Subtype.choices, default=Subtype.GENERAL, db_index=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name_en",)
        indexes = [
            models.Index(fields=("kind", "is_active")),
            models.Index(fields=("domain", "is_active")),
            models.Index(fields=("subtype", "is_active")),
            models.Index(fields=("name_en",)),
            models.Index(fields=("name_fa",)),
        ]

    def __str__(self):
        return self.name_en


class ConceptRelationship(TimeStampedModel):
    class Kind(models.TextChoices):
        RELATED = "related", "Related"
        PART_OF = "part_of", "Part of"
        SUBTYPE_OF = "subtype_of", "Subtype of"
        PREREQUISITE = "prerequisite", "Prerequisite"
        MAINTAINS = "maintains", "Maintains"
        INFLUENCES = "influences", "Influences"
        MECHANISM = "mechanism", "Mechanism"
        CONTRASTS = "contrasts", "Contrasts with"
        COMMONLY_CONFUSED_WITH = "commonly_confused_with", "Commonly confused with"
        ASSOCIATED_WITH = "associated_with", "Associated with"
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


class ConceptAlias(models.Model):
    class Language(models.TextChoices):
        FA = "fa", "Persian"
        EN = "en", "English"
        OTHER = "other", "Other"

    class AliasType(models.TextChoices):
        ALTERNATIVE = "alternative", "Alternative"
        ABBREVIATION = "abbreviation", "Abbreviation"
        HISTORICAL = "historical", "Historical"

    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="aliases")
    text = models.CharField(max_length=220)
    language = models.CharField(max_length=12, choices=Language.choices, default=Language.OTHER)
    alias_type = models.CharField(max_length=24, choices=AliasType.choices, default=AliasType.ALTERNATIVE)

    class Meta:
        ordering = ("language", "text")
        constraints = [
            models.UniqueConstraint(fields=("concept", "text", "language"), name="uq_concept_alias")
        ]
        indexes = [models.Index(fields=("text",))]


class ConceptRelationshipSource(models.Model):
    relationship = models.ForeignKey(ConceptRelationship, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="concept_relationship_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_concept_relationship_source")
        ]


class ConceptSymptom(TimeStampedModel):
    class Kind(models.TextChoices):
        ASSOCIATED = "associated", "Associated"
        MANIFESTATION = "manifestation", "Manifestation"
        OVERLAPS_WITH = "overlaps_with", "Overlaps with"
        CONTRASTS = "contrasts", "Contrasts with"

    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="symptom_links")
    symptom = models.ForeignKey(Symptom, on_delete=models.PROTECT, related_name="concept_links")
    relationship_type = models.CharField(max_length=32, choices=Kind.choices, default=Kind.ASSOCIATED)
    explanation = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("concept", "symptom", "relationship_type"), name="uq_concept_symptom")
        ]


class ConceptSymptomSource(models.Model):
    relationship = models.ForeignKey(ConceptSymptom, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="concept_symptom_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_concept_symptom_source")
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
    seed_managed = models.BooleanField(default=False)

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


class CognitiveDistortionPracticeItem(TimeStampedModel):
    class Difficulty(models.TextChoices):
        BASIC = "basic", "Basic"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"

    slug = models.SlugField(max_length=180, unique=True)
    prompt = models.TextField()
    explanation = models.TextField()
    difficulty = models.CharField(max_length=24, choices=Difficulty.choices, default=Difficulty.BASIC)
    target_concept = models.ForeignKey(
        Concept,
        on_delete=models.PROTECT,
        related_name="distortion_practice_items",
        limit_choices_to={"subtype": Concept.Subtype.COGNITIVE_DISTORTION},
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("sort_order", "id")
        indexes = [models.Index(fields=("is_active", "difficulty"))]


class CognitiveDistortionPracticeChoice(models.Model):
    item = models.ForeignKey(CognitiveDistortionPracticeItem, on_delete=models.CASCADE, related_name="choices")
    concept = models.ForeignKey(Concept, on_delete=models.PROTECT, related_name="distortion_practice_choices")
    text = models.CharField(max_length=300)
    is_correct = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("item", "concept"), name="uq_distortion_practice_item_concept")
        ]


class CognitiveDistortionPracticeAttempt(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="distortion_practice_attempts")
    item = models.ForeignKey(CognitiveDistortionPracticeItem, on_delete=models.PROTECT, related_name="attempts")
    selected_choice = models.ForeignKey(CognitiveDistortionPracticeChoice, on_delete=models.PROTECT, related_name="attempts")
    is_correct = models.BooleanField()

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("user", "-created_at")),
            models.Index(fields=("user", "is_correct")),
        ]


class StudyActivity(models.Model):
    class Kind(models.TextChoices):
        DISORDER_VIEW = "disorder_view", "Disorder view"
        CONCEPT_VIEW = "concept_view", "Concept view"
        QUIZ_COMPLETED = "quiz_completed", "Quiz completed"
        CASE_COMPLETED = "case_completed", "Case completed"
        FLASHCARD_REVIEW = "flashcard_review", "Flashcard review"
        DAILY_CHALLENGE = "daily_challenge", "Daily challenge"
        DISTORTION_PRACTICE = "distortion_practice", "Cognitive distortion practice"
        NOTE_SAVED = "note_saved", "Note saved"
        BOOKMARK_SAVED = "bookmark_saved", "Bookmark saved"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="study_activities")
    activity_type = models.CharField(max_length=32, choices=Kind.choices)
    disorder = models.ForeignKey(Disorder, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_activities")
    concept = models.ForeignKey(Concept, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_activities")
    quiz = models.ForeignKey(Quiz, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_activities")
    clinical_case = models.ForeignKey(ClinicalCase, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_activities")
    flashcard = models.ForeignKey(Flashcard, on_delete=models.SET_NULL, null=True, blank=True, related_name="study_activities")
    therapy = models.ForeignKey("Therapy", on_delete=models.SET_NULL, null=True, blank=True, related_name="study_activities")
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
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("sort_order", "id")


class DailyChallengeChoice(models.Model):
    challenge = models.ForeignKey(DailyChallenge, on_delete=models.CASCADE, related_name="choices")
    text = models.TextField()
    is_correct = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

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


class ScientificReviewStatus(models.TextChoices):
    UNREVIEWED = "unreviewed", "Unreviewed"
    SOURCE_CHECKED = "source_checked", "Source checked"
    REVIEWED = "reviewed", "Reviewed"


class TherapyFamily(TimeStampedModel):
    """Primary theoretical/orientation family for a therapy.

    This is deliberately separate from overlapping classifications such as
    trauma-focused, exposure-based, or mindfulness-based.
    """

    slug = models.SlugField(max_length=120, unique=True)
    name_en = models.CharField(max_length=220)
    name_fa = models.CharField(max_length=220, blank=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("sort_order", "name_en")
        indexes = [models.Index(fields=("is_active", "sort_order"))]

    def __str__(self):
        return self.name_en


class TherapyClassification(TimeStampedModel):
    """Optional overlapping classification/tag for therapies.

    Unlike TherapyFamily, multiple classifications may apply to one therapy.
    """

    class Kind(models.TextChoices):
        FOCUS = "focus", "Focus"
        METHOD = "method", "Method"
        DELIVERY = "delivery", "Delivery"
        POPULATION = "population", "Population"
        OTHER = "other", "Other"

    slug = models.SlugField(max_length=120, unique=True)
    name_en = models.CharField(max_length=220)
    name_fa = models.CharField(max_length=220, blank=True)
    kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.OTHER, db_index=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("kind", "sort_order", "name_en")
        indexes = [models.Index(fields=("kind", "is_active"))]

    def __str__(self):
        return self.name_en


class Therapy(TimeStampedModel):
    family = models.ForeignKey(
        TherapyFamily,
        on_delete=models.PROTECT,
        related_name="therapies",
    )
    slug = models.SlugField(max_length=180, unique=True)
    name_en = models.CharField(max_length=255)
    name_fa = models.CharField(max_length=255, blank=True)
    summary = models.TextField(blank=True)
    academic_definition = models.TextField(blank=True)
    historical_context = models.TextField(blank=True)
    core_principles = models.TextField(blank=True)
    typical_structure = models.TextField(blank=True)
    appropriate_contexts = models.TextField(blank=True)
    limitations = models.TextField(blank=True)
    safety_notes = models.TextField(blank=True)
    evidence_note = models.TextField(blank=True)
    review_status = models.CharField(
        max_length=24,
        choices=ScientificReviewStatus.choices,
        default=ScientificReviewStatus.UNREVIEWED,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("name_en",)
        indexes = [
            models.Index(fields=("family", "is_active")),
            models.Index(fields=("review_status", "is_active")),
            models.Index(fields=("name_en",)),
            models.Index(fields=("name_fa",)),
        ]

    def __str__(self):
        return self.name_en


class TherapyBookmark(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="therapy_bookmarks")
    therapy = models.ForeignKey(Therapy, on_delete=models.CASCADE, related_name="bookmarked_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("user", "therapy"), name="uq_user_therapy_bookmark")
        ]
        indexes = [models.Index(fields=("user", "-created_at"))]


class TherapyNote(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="therapy_notes")
    therapy = models.ForeignKey(Therapy, on_delete=models.CASCADE, related_name="user_notes")
    body = models.TextField(blank=True)

    class Meta:
        ordering = ("-updated_at", "-id")
        constraints = [
            models.UniqueConstraint(fields=("user", "therapy"), name="uq_user_therapy_note")
        ]
        indexes = [models.Index(fields=("user", "-updated_at"))]

    def __str__(self):
        return f"{self.user_id}:{self.therapy.slug}"


class TherapyAlias(models.Model):
    class Language(models.TextChoices):
        FA = "fa", "Persian"
        EN = "en", "English"
        OTHER = "other", "Other"

    class AliasType(models.TextChoices):
        ALTERNATIVE = "alternative", "Alternative"
        ABBREVIATION = "abbreviation", "Abbreviation"
        HISTORICAL = "historical", "Historical"

    therapy = models.ForeignKey(Therapy, on_delete=models.CASCADE, related_name="aliases")
    text = models.CharField(max_length=255)
    language = models.CharField(max_length=12, choices=Language.choices, default=Language.OTHER)
    alias_type = models.CharField(max_length=24, choices=AliasType.choices, default=AliasType.ALTERNATIVE)

    class Meta:
        ordering = ("language", "text")
        constraints = [
            models.UniqueConstraint(fields=("therapy", "text", "language"), name="uq_therapy_alias")
        ]
        indexes = [models.Index(fields=("text",))]


class TherapyClassificationLink(TimeStampedModel):
    therapy = models.ForeignKey(Therapy, on_delete=models.CASCADE, related_name="classification_links")
    classification = models.ForeignKey(
        TherapyClassification,
        on_delete=models.PROTECT,
        related_name="therapy_links",
    )
    explanation = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("therapy", "classification"),
                name="uq_therapy_classification",
            )
        ]


class Technique(TimeStampedModel):
    slug = models.SlugField(max_length=180, unique=True)
    name_en = models.CharField(max_length=255)
    name_fa = models.CharField(max_length=255, blank=True)
    summary = models.TextField(blank=True)
    academic_definition = models.TextField(blank=True)
    application_notes = models.TextField(blank=True)
    limitations = models.TextField(blank=True)
    safety_notes = models.TextField(blank=True)
    review_status = models.CharField(
        max_length=24,
        choices=ScientificReviewStatus.choices,
        default=ScientificReviewStatus.UNREVIEWED,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("name_en",)
        indexes = [
            models.Index(fields=("review_status", "is_active")),
            models.Index(fields=("name_en",)),
            models.Index(fields=("name_fa",)),
        ]

    def __str__(self):
        return self.name_en


class TechniqueAlias(models.Model):
    class Language(models.TextChoices):
        FA = "fa", "Persian"
        EN = "en", "English"
        OTHER = "other", "Other"

    class AliasType(models.TextChoices):
        ALTERNATIVE = "alternative", "Alternative"
        ABBREVIATION = "abbreviation", "Abbreviation"
        HISTORICAL = "historical", "Historical"

    technique = models.ForeignKey(Technique, on_delete=models.CASCADE, related_name="aliases")
    text = models.CharField(max_length=255)
    language = models.CharField(max_length=12, choices=Language.choices, default=Language.OTHER)
    alias_type = models.CharField(max_length=24, choices=AliasType.choices, default=AliasType.ALTERNATIVE)

    class Meta:
        ordering = ("language", "text")
        constraints = [
            models.UniqueConstraint(fields=("technique", "text", "language"), name="uq_technique_alias")
        ]
        indexes = [models.Index(fields=("text",))]


class TherapyTechnique(TimeStampedModel):
    class Role(models.TextChoices):
        CORE = "core", "Core"
        COMMON = "common", "Common"
        OPTIONAL = "optional", "Optional"
        ADAPTED = "adapted", "Adapted"
        COMPONENT = "component", "Component"

    therapy = models.ForeignKey(Therapy, on_delete=models.CASCADE, related_name="technique_links")
    technique = models.ForeignKey(Technique, on_delete=models.PROTECT, related_name="therapy_links")
    role = models.CharField(max_length=24, choices=Role.choices, default=Role.COMMON)
    explanation = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    review_status = models.CharField(
        max_length=24,
        choices=ScientificReviewStatus.choices,
        default=ScientificReviewStatus.UNREVIEWED,
    )
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("therapy", "technique"), name="uq_therapy_technique")
        ]
        indexes = [models.Index(fields=("therapy", "is_active"))]


class TherapyDisorder(TimeStampedModel):
    class ClinicalRole(models.TextChoices):
        UNSPECIFIED = "unspecified", "Unspecified"
        GUIDELINE_RECOMMENDED = "guideline_recommended", "Guideline recommended"
        COMMONLY_USED = "commonly_used", "Commonly used"
        ADJUNCTIVE = "adjunctive", "Adjunctive"
        ALTERNATIVE = "alternative", "Alternative"
        CONTEXT_DEPENDENT = "context_dependent", "Context dependent"
        NOT_FIRST_LINE = "not_first_line", "Not first line"
        RESEARCH_CONTEXT = "research_context", "Research context"

    class EvidenceBasis(models.TextChoices):
        NOT_ASSESSED = "not_assessed", "Not assessed"
        GUIDELINE = "guideline", "Guideline"
        SYSTEMATIC_REVIEW = "systematic_review", "Systematic review / meta-analysis"
        CONTROLLED_TRIALS = "controlled_trials", "Controlled trials"
        OBSERVATIONAL = "observational", "Observational evidence"
        MIXED = "mixed", "Mixed evidence"
        EMERGING = "emerging", "Emerging evidence"
        INSUFFICIENT = "insufficient", "Insufficient evidence"

    therapy = models.ForeignKey(Therapy, on_delete=models.CASCADE, related_name="disorder_links")
    disorder = models.ForeignKey(Disorder, on_delete=models.CASCADE, related_name="therapy_links")
    clinical_role = models.CharField(
        max_length=32,
        choices=ClinicalRole.choices,
        default=ClinicalRole.UNSPECIFIED,
        db_index=True,
    )
    evidence_basis = models.CharField(
        max_length=32,
        choices=EvidenceBasis.choices,
        default=EvidenceBasis.NOT_ASSESSED,
        db_index=True,
    )
    explanation = models.TextField(blank=True)
    evidence_note = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    review_status = models.CharField(
        max_length=24,
        choices=ScientificReviewStatus.choices,
        default=ScientificReviewStatus.UNREVIEWED,
    )
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("therapy", "disorder"), name="uq_therapy_disorder")
        ]
        indexes = [
            models.Index(fields=("therapy", "is_active")),
            models.Index(fields=("disorder", "is_active")),
            models.Index(fields=("evidence_basis", "is_active")),
        ]


class TherapyConcept(TimeStampedModel):
    class Kind(models.TextChoices):
        TARGETS = "targets", "Targets"
        USES = "uses", "Uses"
        ADDRESSES = "addresses", "Addresses"
        TEACHES = "teaches", "Teaches"
        MECHANISM = "mechanism", "Mechanism"
        APPLIED_TO = "applied_to", "Applied to"

    therapy = models.ForeignKey(Therapy, on_delete=models.CASCADE, related_name="concept_links")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="therapy_links")
    relationship_type = models.CharField(max_length=24, choices=Kind.choices)
    explanation = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    review_status = models.CharField(
        max_length=24,
        choices=ScientificReviewStatus.choices,
        default=ScientificReviewStatus.UNREVIEWED,
    )
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("therapy", "concept", "relationship_type"),
                name="uq_therapy_concept_relation",
            )
        ]
        indexes = [
            models.Index(fields=("therapy", "is_active")),
            models.Index(fields=("concept", "is_active")),
        ]


class TechniqueConcept(TimeStampedModel):
    class Kind(models.TextChoices):
        TARGETS = "targets", "Targets"
        ADDRESSES = "addresses", "Addresses"
        TEACHES = "teaches", "Teaches"
        MECHANISM = "mechanism", "Mechanism"
        APPLIED_TO = "applied_to", "Applied to"

    technique = models.ForeignKey(Technique, on_delete=models.CASCADE, related_name="concept_links")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="technique_links")
    relationship_type = models.CharField(max_length=24, choices=Kind.choices)
    explanation = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    review_status = models.CharField(
        max_length=24,
        choices=ScientificReviewStatus.choices,
        default=ScientificReviewStatus.UNREVIEWED,
    )
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("technique", "concept", "relationship_type"),
                name="uq_technique_concept_relation",
            )
        ]
        indexes = [
            models.Index(fields=("technique", "is_active")),
            models.Index(fields=("concept", "is_active")),
        ]


class TherapySource(models.Model):
    therapy = models.ForeignKey(Therapy, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="therapy_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("therapy", "source"), name="uq_therapy_source")
        ]


class TechniqueSource(models.Model):
    technique = models.ForeignKey(Technique, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="technique_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("technique", "source"), name="uq_technique_source")
        ]


class TherapyTechniqueSource(models.Model):
    relationship = models.ForeignKey(TherapyTechnique, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="therapy_technique_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("relationship", "source"),
                name="uq_therapy_technique_source",
            )
        ]


class TherapyDisorderSource(models.Model):
    relationship = models.ForeignKey(TherapyDisorder, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="therapy_disorder_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("relationship", "source"),
                name="uq_therapy_disorder_source",
            )
        ]


class TherapyConceptSource(models.Model):
    relationship = models.ForeignKey(TherapyConcept, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="therapy_concept_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("relationship", "source"),
                name="uq_therapy_concept_source",
            )
        ]


class TechniqueConceptSource(models.Model):
    relationship = models.ForeignKey(TechniqueConcept, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="technique_concept_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("relationship", "source"),
                name="uq_technique_concept_source",
            )
        ]


class ResearchDataset(TimeStampedModel):
    """Lossless import envelope for externally researched Psychology Atlas data.

    Raw JSON is retained so future schema upgrades can re-project the source
    without asking the research agent to regenerate it.
    """

    key = models.SlugField(max_length=180, unique=True)
    source_filename = models.CharField(max_length=500)
    source_sha256 = models.CharField(max_length=64, unique=True, db_index=True)
    dataset_name = models.CharField(max_length=300, blank=True)
    dataset_version = models.CharField(max_length=120, blank=True)
    generated_at_text = models.CharField(max_length=120, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    statistics = models.JSONField(default=dict, blank=True)
    quality_control = models.JSONField(default=dict, blank=True)
    ingestion_audit = models.JSONField(default=dict, blank=True)
    raw_document = models.JSONField(default=dict, blank=True)
    raw_text = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("-created_at", "-id")

    def __str__(self):
        return self.dataset_name or self.source_filename


class ResearchRecord(TimeStampedModel):
    """Normalized searchable index over one ResearchDataset record.

    `payload` is lossless for the individual row. `canonical_key` is a
    cross-dataset semantic key used for dedupe/promotion, while external_id
    preserves the source dataset's own identifier.
    """

    dataset = models.ForeignKey(ResearchDataset, on_delete=models.CASCADE, related_name="records")
    section = models.CharField(max_length=64, db_index=True)
    external_id = models.CharField(max_length=300)
    canonical_key = models.CharField(max_length=400, blank=True, db_index=True)
    slug = models.SlugField(max_length=220, blank=True, db_index=True)
    name_en = models.CharField(max_length=500, blank=True)
    name_fa = models.CharField(max_length=500, blank=True)
    source_ids = models.JSONField(default=list, blank=True)
    verification_status = models.CharField(max_length=64, blank=True, db_index=True)
    review_status = models.CharField(max_length=64, blank=True, db_index=True)
    payload = models.JSONField(default=dict)
    promoted_model = models.CharField(max_length=80, blank=True, db_index=True)
    promoted_pk = models.PositiveBigIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("dataset_id", "section", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("dataset", "section", "external_id"),
                name="uq_research_dataset_section_external_id",
            )
        ]
        indexes = [
            models.Index(fields=("section", "canonical_key")),
            models.Index(fields=("promoted_model", "promoted_pk")),
        ]

    def __str__(self):
        return f"{self.section}:{self.external_id}"


class Psychologist(TimeStampedModel):
    slug = models.SlugField(max_length=180, unique=True)
    name_en = models.CharField(max_length=255)
    name_fa = models.CharField(max_length=255, blank=True)
    summary_en = models.TextField(blank=True)
    summary_fa = models.TextField(blank=True)
    role_en = models.CharField(max_length=180, blank=True)
    role_fa = models.CharField(max_length=180, blank=True)
    nationality_en = models.CharField(max_length=180, blank=True)
    nationality_fa = models.CharField(max_length=180, blank=True)
    birth_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(9999)],
    )
    death_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(9999)],
    )
    academic_disciplines = models.JSONField(default=list, blank=True)
    contributions_en = models.JSONField(default=list, blank=True)
    contributions_fa = models.JSONField(default=list, blank=True)
    affiliations = models.JSONField(default=list, blank=True)
    historical_context_en = models.TextField(blank=True)
    historical_context_fa = models.TextField(blank=True)
    review_status = models.CharField(
        max_length=24,
        choices=ScientificReviewStatus.choices,
        default=ScientificReviewStatus.UNREVIEWED,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("name_en",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(death_year__isnull=True)
                    | Q(birth_year__isnull=True)
                    | Q(death_year__gte=F("birth_year"))
                ),
                name="ck_psychologist_life_year_order",
            )
        ]
        indexes = [
            models.Index(fields=("review_status", "is_active")),
            models.Index(fields=("name_en",)),
            models.Index(fields=("name_fa",)),
            models.Index(fields=("birth_year",)),
        ]

    def __str__(self):
        return self.name_en


class PsychologistAlias(models.Model):
    class Language(models.TextChoices):
        FA = "fa", "Persian"
        EN = "en", "English"
        OTHER = "other", "Other"

    class AliasType(models.TextChoices):
        ALTERNATIVE = "alternative", "Alternative"
        INITIALS = "initials", "Initials"
        TRANSLITERATION = "transliteration", "Transliteration"
        HISTORICAL = "historical", "Historical"

    psychologist = models.ForeignKey(Psychologist, on_delete=models.CASCADE, related_name="aliases")
    text = models.CharField(max_length=255)
    language = models.CharField(max_length=12, choices=Language.choices, default=Language.OTHER)
    alias_type = models.CharField(max_length=24, choices=AliasType.choices, default=AliasType.ALTERNATIVE)

    class Meta:
        ordering = ("language", "text")
        constraints = [
            models.UniqueConstraint(
                fields=("psychologist", "text", "language"),
                name="uq_psychologist_alias",
            )
        ]
        indexes = [models.Index(fields=("text",))]


class Theory(TimeStampedModel):
    slug = models.SlugField(max_length=180, unique=True)
    name_en = models.CharField(max_length=255)
    name_fa = models.CharField(max_length=255, blank=True)
    domain = models.CharField(max_length=160, blank=True, db_index=True)
    period_text = models.CharField(max_length=180, blank=True)
    summary_en = models.TextField(blank=True)
    summary_fa = models.TextField(blank=True)
    core_proposition_en = models.TextField(blank=True)
    core_proposition_fa = models.TextField(blank=True)
    historical_context_en = models.TextField(blank=True)
    historical_context_fa = models.TextField(blank=True)
    key_propositions_en = models.JSONField(default=list, blank=True)
    key_propositions_fa = models.JSONField(default=list, blank=True)
    applications_en = models.JSONField(default=list, blank=True)
    applications_fa = models.JSONField(default=list, blank=True)
    criticisms_en = models.JSONField(default=list, blank=True)
    criticisms_fa = models.JSONField(default=list, blank=True)
    limitations_en = models.JSONField(default=list, blank=True)
    limitations_fa = models.JSONField(default=list, blank=True)
    modern_status = models.CharField(max_length=180, blank=True, db_index=True)
    historical_importance_en = models.TextField(blank=True)
    historical_importance_fa = models.TextField(blank=True)
    review_status = models.CharField(
        max_length=24,
        choices=ScientificReviewStatus.choices,
        default=ScientificReviewStatus.UNREVIEWED,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("name_en",)
        indexes = [
            models.Index(fields=("domain", "is_active")),
            models.Index(fields=("review_status", "is_active")),
            models.Index(fields=("name_en",)),
            models.Index(fields=("name_fa",)),
        ]

    def __str__(self):
        return self.name_en


class TheoryAlias(models.Model):
    class Language(models.TextChoices):
        FA = "fa", "Persian"
        EN = "en", "English"
        OTHER = "other", "Other"

    class AliasType(models.TextChoices):
        ALTERNATIVE = "alternative", "Alternative"
        ABBREVIATION = "abbreviation", "Abbreviation"
        HISTORICAL = "historical", "Historical"
        TRANSLITERATION = "transliteration", "Transliteration"

    theory = models.ForeignKey(Theory, on_delete=models.CASCADE, related_name="aliases")
    text = models.CharField(max_length=255)
    language = models.CharField(max_length=12, choices=Language.choices, default=Language.OTHER)
    alias_type = models.CharField(max_length=24, choices=AliasType.choices, default=AliasType.ALTERNATIVE)

    class Meta:
        ordering = ("language", "text")
        constraints = [
            models.UniqueConstraint(fields=("theory", "text", "language"), name="uq_theory_alias")
        ]
        indexes = [models.Index(fields=("text",))]


class TimelineEvent(TimeStampedModel):
    class DatePrecision(models.TextChoices):
        EXACT_DATE = "exact_date", "Exact date"
        YEAR = "year", "Year only"
        YEAR_RANGE = "year_range", "Year range"
        APPROXIMATE_YEAR = "approximate_year", "Approximate year"
        UNKNOWN = "unknown", "Unknown"

    class EventType(models.TextChoices):
        PUBLICATION = "publication", "Publication"
        THEORY_DEVELOPMENT = "theory_development", "Theory development"
        THERAPY_DEVELOPMENT = "therapy_development", "Therapy development"
        RESEARCH_FINDING = "research_finding", "Research finding"
        INSTITUTIONAL = "institutional", "Institutional milestone"
        PROFESSIONAL = "professional", "Professional milestone"
        CLASSIFICATION = "classification", "Classification / nosology"
        GUIDELINE = "guideline", "Guideline"
        OTHER = "other", "Other"
        UNSPECIFIED = "unspecified", "Unspecified"

    slug = models.SlugField(max_length=220, unique=True)
    title_en = models.CharField(max_length=500)
    title_fa = models.CharField(max_length=500, blank=True)
    description_en = models.TextField(blank=True)
    description_fa = models.TextField(blank=True)
    historical_importance_en = models.TextField(blank=True)
    historical_importance_fa = models.TextField(blank=True)
    event_type = models.CharField(
        max_length=32,
        choices=EventType.choices,
        default=EventType.UNSPECIFIED,
        db_index=True,
    )
    category = models.CharField(max_length=160, blank=True, db_index=True)
    date_precision = models.CharField(
        max_length=24,
        choices=DatePrecision.choices,
        default=DatePrecision.UNKNOWN,
        db_index=True,
    )
    date_text = models.CharField(max_length=180, blank=True)
    year_start = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(9999)],
        db_index=True,
    )
    year_end = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(9999)],
    )
    exact_date = models.DateField(null=True, blank=True)
    review_status = models.CharField(
        max_length=24,
        choices=ScientificReviewStatus.choices,
        default=ScientificReviewStatus.UNREVIEWED,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        ordering = ("year_start", "exact_date", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(year_end__isnull=True) | Q(year_start__isnull=False),
                name="ck_timeline_end_requires_start",
            ),
            models.CheckConstraint(
                condition=Q(year_end__isnull=True) | Q(year_end__gte=F("year_start")),
                name="ck_timeline_year_order",
            ),
            models.CheckConstraint(
                condition=~Q(date_precision="exact_date") | Q(exact_date__isnull=False),
                name="ck_timeline_exact_requires_date",
            ),
            models.CheckConstraint(
                condition=Q(date_precision="exact_date") | Q(exact_date__isnull=True),
                name="ck_timeline_nonexact_has_no_date",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(
                        date_precision__in=("year", "year_range", "approximate_year")
                    )
                    | Q(year_start__isnull=False)
                ),
                name="ck_timeline_year_precision_start",
            ),
            models.CheckConstraint(
                condition=~Q(date_precision="year_range") | Q(year_end__isnull=False),
                name="ck_timeline_range_requires_end",
            ),
        ]
        indexes = [
            models.Index(fields=("year_start", "is_active")),
            models.Index(fields=("event_type", "is_active")),
            models.Index(fields=("review_status", "is_active")),
            models.Index(fields=("title_en",)),
            models.Index(fields=("title_fa",)),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.date_precision == self.DatePrecision.EXACT_DATE and self.exact_date is None:
            errors["exact_date"] = "Exact-date events require exact_date."
        if self.date_precision != self.DatePrecision.EXACT_DATE and self.exact_date is not None:
            errors["exact_date"] = "Non-exact events must not invent an exact date."
        if self.date_precision in {
            self.DatePrecision.YEAR,
            self.DatePrecision.YEAR_RANGE,
            self.DatePrecision.APPROXIMATE_YEAR,
        } and self.year_start is None:
            errors["year_start"] = "This date precision requires year_start."
        if self.date_precision == self.DatePrecision.YEAR_RANGE and self.year_end is None:
            errors["year_end"] = "Year-range events require year_end."
        if self.year_start is not None and self.year_end is not None and self.year_end < self.year_start:
            errors["year_end"] = "year_end cannot be earlier than year_start."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.title_en


class PsychologistSource(models.Model):
    class Role(models.TextChoices):
        BIOGRAPHY = "biography", "Biography"
        PRIMARY_WORK = "primary_work", "Primary work"
        INSTITUTIONAL = "institutional", "Institutional biography/archive"
        HISTORICAL_REVIEW = "historical_review", "Historical review"
        OTHER = "other", "Other"

    psychologist = models.ForeignKey(Psychologist, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="psychologist_links")
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.OTHER)
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("psychologist", "source", "role"), name="uq_psychologist_source")
        ]


class TheorySource(models.Model):
    class Role(models.TextChoices):
        PRIMARY_PUBLICATION = "primary_publication", "Primary publication"
        HISTORICAL_REVIEW = "historical_review", "Historical review"
        EVIDENCE_REVIEW = "evidence_review", "Evidence review"
        INSTITUTIONAL = "institutional", "Institutional source"
        OTHER = "other", "Other"

    theory = models.ForeignKey(Theory, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="theory_links")
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.OTHER)
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("theory", "source", "role"), name="uq_theory_source")
        ]


class TimelineEventSource(models.Model):
    class Role(models.TextChoices):
        PRIMARY = "primary", "Primary source"
        HISTORICAL_REVIEW = "historical_review", "Historical review"
        INSTITUTIONAL = "institutional", "Institutional source"
        OTHER = "other", "Other"

    event = models.ForeignKey(TimelineEvent, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="timeline_event_links")
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.OTHER)
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("event", "source", "role"), name="uq_timeline_event_source")
        ]


class ScientificRelationBase(TimeStampedModel):
    explanation_en = models.TextField(blank=True)
    explanation_fa = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    review_status = models.CharField(
        max_length=24,
        choices=ScientificReviewStatus.choices,
        default=ScientificReviewStatus.UNREVIEWED,
        db_index=True,
    )
    is_active = models.BooleanField(default=True)
    seed_managed = models.BooleanField(default=False)

    class Meta:
        abstract = True


class PsychologistAttributionType(models.TextChoices):
    ORIGINATED = "originated", "Originated"
    PROPOSED = "proposed", "Proposed"
    CO_PROPOSED = "co_proposed", "Co-proposed"
    DEVELOPED = "developed", "Developed"
    CO_DEVELOPED = "co_developed", "Co-developed"
    DEVELOPED_OR_MAJORLY_ASSOCIATED_WITH = (
        "developed_or_majorly_associated_with",
        "Developed or majorly associated with",
    )
    EXPANDED = "expanded", "Expanded"
    POPULARIZED = "popularized", "Popularized"
    RESEARCHED = "researched", "Researched"
    RESEARCHED_OR_DEVELOPED = "researched_or_developed", "Researched or developed"
    APPLIED = "applied", "Applied"
    CONTRIBUTED_TO = "contributed_to", "Contributed to"
    CRITICIZED = "criticized", "Criticized"
    CHALLENGED = "challenged", "Challenged"
    ASSOCIATED_WITH = "associated_with", "Associated with"
    MAJORLY_ASSOCIATED_WITH = "majorly_associated_with", "Majorly associated with"


class TheoryRelationType(models.TextChoices):
    GROUNDS = "grounds", "Grounds"
    INCLUDES_CONSTRUCT = "includes_construct", "Includes construct"
    INFORMS = "informs", "Informs"
    SUPPORTS = "supports", "Supports"
    COMPLEMENTS = "complements", "Complements"
    CHALLENGES = "challenges", "Challenges"
    CHALLENGED_BY = "challenged_by", "Challenged by"
    REFORMULATED_AS = "reformulated_as", "Reformulated as"
    SUPPORTS_INTERPRETATION_OF = "supports_interpretation_of", "Supports interpretation of"
    EXTENDS = "extends", "Extends"
    REFINES = "refines", "Refines"
    ASSOCIATED_WITH = "associated_with", "Associated with"


class PsychologistRelationshipType(models.TextChoices):
    COLLABORATED_WITH = "collaborated_with", "Collaborated with"
    INFLUENCED = "influenced", "Influenced"
    MENTORED = "mentored", "Mentored"
    CRITICIZED = "criticized", "Criticized"
    ASSOCIATED_WITH = "associated_with", "Associated with"


class TimelineLinkRole(models.TextChoices):
    RELATED = "related", "Related"
    INVOLVES_PERSON = "involves_person", "Involves person"
    MARKS_THEORY_MILESTONE = "marks_theory_milestone", "Marks theory milestone"
    MARKS_THERAPY_MILESTONE = "marks_therapy_milestone", "Marks therapy milestone"
    MARKS_TECHNIQUE_EVIDENCE_MILESTONE = (
        "marks_technique_evidence_milestone",
        "Marks technique evidence milestone",
    )
    SUBJECT = "subject", "Subject"
    AUTHOR = "author", "Author"
    DEVELOPER = "developer", "Developer"
    PUBLICATION = "publication", "Publication"
    INSTITUTIONAL = "institutional", "Institutional"
    CONTEXT = "context", "Context"


class PsychologistTheory(ScientificRelationBase):
    psychologist = models.ForeignKey(Psychologist, on_delete=models.CASCADE, related_name="theory_links")
    theory = models.ForeignKey(Theory, on_delete=models.CASCADE, related_name="psychologist_links")
    relationship_type = models.CharField(max_length=48, choices=PsychologistAttributionType.choices)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("psychologist", "theory", "relationship_type"),
                name="uq_psychologist_theory_relation",
            )
        ]
        indexes = [
            models.Index(fields=("psychologist", "is_active")),
            models.Index(fields=("theory", "is_active")),
        ]


class PsychologistTheorySource(models.Model):
    relationship = models.ForeignKey(PsychologistTheory, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="psychologist_theory_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_psychologist_theory_source")
        ]


class PsychologistConcept(ScientificRelationBase):
    psychologist = models.ForeignKey(Psychologist, on_delete=models.CASCADE, related_name="concept_links")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="psychologist_links")
    relationship_type = models.CharField(max_length=48, choices=PsychologistAttributionType.choices)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("psychologist", "concept", "relationship_type"),
                name="uq_psychologist_concept_relation",
            )
        ]
        indexes = [
            models.Index(fields=("psychologist", "is_active")),
            models.Index(fields=("concept", "is_active")),
        ]


class PsychologistConceptSource(models.Model):
    relationship = models.ForeignKey(PsychologistConcept, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="psychologist_concept_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_psychologist_concept_source")
        ]


class PsychologistTherapy(ScientificRelationBase):
    psychologist = models.ForeignKey(Psychologist, on_delete=models.CASCADE, related_name="therapy_links")
    therapy = models.ForeignKey(Therapy, on_delete=models.CASCADE, related_name="psychologist_links")
    relationship_type = models.CharField(max_length=48, choices=PsychologistAttributionType.choices)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("psychologist", "therapy", "relationship_type"),
                name="uq_psychologist_therapy_relation",
            )
        ]
        indexes = [
            models.Index(fields=("psychologist", "is_active")),
            models.Index(fields=("therapy", "is_active")),
        ]


class PsychologistTherapySource(models.Model):
    relationship = models.ForeignKey(PsychologistTherapy, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="psychologist_therapy_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_psychologist_therapy_source")
        ]


class PsychologistPsychologist(ScientificRelationBase):
    psychologist = models.ForeignKey(Psychologist, on_delete=models.CASCADE, related_name="outgoing_psychologist_links")
    related_psychologist = models.ForeignKey(
        Psychologist,
        on_delete=models.CASCADE,
        related_name="incoming_psychologist_links",
    )
    relationship_type = models.CharField(max_length=32, choices=PsychologistRelationshipType.choices)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("psychologist", "related_psychologist", "relationship_type"),
                name="uq_psychologist_psychologist_relation",
            ),
            models.CheckConstraint(
                condition=~Q(psychologist=F("related_psychologist")),
                name="ck_psychologist_relation_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=("psychologist", "is_active")),
            models.Index(fields=("related_psychologist", "is_active")),
        ]


class PsychologistPsychologistSource(models.Model):
    relationship = models.ForeignKey(
        PsychologistPsychologist,
        on_delete=models.CASCADE,
        related_name="source_links",
    )
    source = models.ForeignKey(
        SourceReference,
        on_delete=models.PROTECT,
        related_name="psychologist_psychologist_links",
    )
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("relationship", "source"),
                name="uq_psychologist_psychologist_source",
            )
        ]


class TheoryConcept(ScientificRelationBase):
    theory = models.ForeignKey(Theory, on_delete=models.CASCADE, related_name="concept_links")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="theory_links")
    relationship_type = models.CharField(max_length=40, choices=TheoryRelationType.choices)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("theory", "concept", "relationship_type"),
                name="uq_theory_concept_relation",
            )
        ]
        indexes = [
            models.Index(fields=("theory", "is_active")),
            models.Index(fields=("concept", "is_active")),
        ]


class TheoryConceptSource(models.Model):
    relationship = models.ForeignKey(TheoryConcept, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="theory_concept_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_theory_concept_source")
        ]


class TheoryTherapy(ScientificRelationBase):
    theory = models.ForeignKey(Theory, on_delete=models.CASCADE, related_name="therapy_links")
    therapy = models.ForeignKey(Therapy, on_delete=models.CASCADE, related_name="theory_links")
    relationship_type = models.CharField(max_length=40, choices=TheoryRelationType.choices)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("theory", "therapy", "relationship_type"),
                name="uq_theory_therapy_relation",
            )
        ]
        indexes = [
            models.Index(fields=("theory", "is_active")),
            models.Index(fields=("therapy", "is_active")),
        ]


class TheoryTherapySource(models.Model):
    relationship = models.ForeignKey(TheoryTherapy, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="theory_therapy_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_theory_therapy_source")
        ]


class TheoryTechnique(ScientificRelationBase):
    theory = models.ForeignKey(Theory, on_delete=models.CASCADE, related_name="technique_links")
    technique = models.ForeignKey(Technique, on_delete=models.CASCADE, related_name="theory_links")
    relationship_type = models.CharField(max_length=40, choices=TheoryRelationType.choices)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("theory", "technique", "relationship_type"),
                name="uq_theory_technique_relation",
            )
        ]
        indexes = [
            models.Index(fields=("theory", "is_active")),
            models.Index(fields=("technique", "is_active")),
        ]


class TheoryTechniqueSource(models.Model):
    relationship = models.ForeignKey(TheoryTechnique, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="theory_technique_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_theory_technique_source")
        ]


class TheoryTheory(ScientificRelationBase):
    theory = models.ForeignKey(Theory, on_delete=models.CASCADE, related_name="outgoing_theory_links")
    related_theory = models.ForeignKey(Theory, on_delete=models.CASCADE, related_name="incoming_theory_links")
    relationship_type = models.CharField(max_length=40, choices=TheoryRelationType.choices)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("theory", "related_theory", "relationship_type"),
                name="uq_theory_theory_relation",
            ),
            models.CheckConstraint(
                condition=~Q(theory=F("related_theory")),
                name="ck_theory_relation_not_self",
            ),
        ]
        indexes = [
            models.Index(fields=("theory", "is_active")),
            models.Index(fields=("related_theory", "is_active")),
        ]


class TheoryTheorySource(models.Model):
    relationship = models.ForeignKey(TheoryTheory, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="theory_theory_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_theory_theory_source")
        ]


class TimelinePsychologist(ScientificRelationBase):
    event = models.ForeignKey(TimelineEvent, on_delete=models.CASCADE, related_name="psychologist_links")
    psychologist = models.ForeignKey(Psychologist, on_delete=models.CASCADE, related_name="timeline_links")
    role = models.CharField(max_length=48, choices=TimelineLinkRole.choices, default=TimelineLinkRole.RELATED)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("event", "psychologist", "role"), name="uq_timeline_psychologist")
        ]
        indexes = [
            models.Index(fields=("event", "is_active")),
            models.Index(fields=("psychologist", "is_active")),
        ]


class TimelinePsychologistSource(models.Model):
    relationship = models.ForeignKey(TimelinePsychologist, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="timeline_psychologist_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_timeline_psychologist_source")
        ]


class TimelineTheory(ScientificRelationBase):
    event = models.ForeignKey(TimelineEvent, on_delete=models.CASCADE, related_name="theory_links")
    theory = models.ForeignKey(Theory, on_delete=models.CASCADE, related_name="timeline_links")
    role = models.CharField(max_length=48, choices=TimelineLinkRole.choices, default=TimelineLinkRole.RELATED)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("event", "theory", "role"), name="uq_timeline_theory")
        ]
        indexes = [
            models.Index(fields=("event", "is_active")),
            models.Index(fields=("theory", "is_active")),
        ]


class TimelineTheorySource(models.Model):
    relationship = models.ForeignKey(TimelineTheory, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="timeline_theory_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_timeline_theory_source")
        ]


class TimelineTherapy(ScientificRelationBase):
    event = models.ForeignKey(TimelineEvent, on_delete=models.CASCADE, related_name="therapy_links")
    therapy = models.ForeignKey(Therapy, on_delete=models.CASCADE, related_name="timeline_links")
    role = models.CharField(max_length=48, choices=TimelineLinkRole.choices, default=TimelineLinkRole.RELATED)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("event", "therapy", "role"), name="uq_timeline_therapy")
        ]
        indexes = [
            models.Index(fields=("event", "is_active")),
            models.Index(fields=("therapy", "is_active")),
        ]


class TimelineTherapySource(models.Model):
    relationship = models.ForeignKey(TimelineTherapy, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="timeline_therapy_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_timeline_therapy_source")
        ]


class TimelineTechnique(ScientificRelationBase):
    event = models.ForeignKey(TimelineEvent, on_delete=models.CASCADE, related_name="technique_links")
    technique = models.ForeignKey(Technique, on_delete=models.CASCADE, related_name="timeline_links")
    role = models.CharField(max_length=48, choices=TimelineLinkRole.choices, default=TimelineLinkRole.RELATED)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("event", "technique", "role"), name="uq_timeline_technique")
        ]
        indexes = [
            models.Index(fields=("event", "is_active")),
            models.Index(fields=("technique", "is_active")),
        ]


class TimelineTechniqueSource(models.Model):
    relationship = models.ForeignKey(TimelineTechnique, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="timeline_technique_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_timeline_technique_source")
        ]


class TimelineConcept(ScientificRelationBase):
    event = models.ForeignKey(TimelineEvent, on_delete=models.CASCADE, related_name="concept_links")
    concept = models.ForeignKey(Concept, on_delete=models.CASCADE, related_name="timeline_links")
    role = models.CharField(max_length=48, choices=TimelineLinkRole.choices, default=TimelineLinkRole.RELATED)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(fields=("event", "concept", "role"), name="uq_timeline_concept")
        ]
        indexes = [
            models.Index(fields=("event", "is_active")),
            models.Index(fields=("concept", "is_active")),
        ]


class TimelineConceptSource(models.Model):
    relationship = models.ForeignKey(TimelineConcept, on_delete=models.CASCADE, related_name="source_links")
    source = models.ForeignKey(SourceReference, on_delete=models.PROTECT, related_name="timeline_concept_links")
    note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("relationship", "source"), name="uq_timeline_concept_source")
        ]


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
