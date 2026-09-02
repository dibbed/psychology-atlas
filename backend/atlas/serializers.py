from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError
from django.db.models import Q
from rest_framework import serializers

from .models import (
    Bookmark,
    CaseChoice,
    CaseQuestion,
    CaseStep,
    ClinicalCase,
    DifferentialRelationship,
    Disorder,
    DisorderSymptom,
    Quiz,
    QuizChoice,
    QuizQuestion,
    SourceReference,
    UserNote,
    UserProgress,
)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("email", "password")

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(Q(username__iexact=value) | Q(email__iexact=value)).exists():
            raise serializers.ValidationError("قبلاً با این ایمیل حساب ساخته شده است.")
        return value

    def validate(self, attrs):
        email = attrs["email"]
        candidate = User(username=email, email=email)
        validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        email = validated_data["email"].lower()
        try:
            return User.objects.create_user(username=email, email=email, password=validated_data["password"])
        except IntegrityError:
            raise serializers.ValidationError({"email": "قبلاً با این ایمیل حساب ساخته شده است."})


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email")


class SymptomLinkSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(source="symptom.slug")
    name_en = serializers.CharField(source="symptom.name_en")
    name_fa = serializers.CharField(source="symptom.name_fa")
    description = serializers.CharField(source="symptom.description")
    domain = serializers.CharField(source="symptom.domain")

    class Meta:
        model = DisorderSymptom
        fields = ("slug", "name_en", "name_fa", "description", "domain", "prominence", "note")


class RelatedDisorderSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(source="related_disorder.slug")
    name_en = serializers.CharField(source="related_disorder.name_en")
    name_fa = serializers.CharField(source="related_disorder.name_fa")

    class Meta:
        model = DifferentialRelationship
        fields = ("slug", "name_en", "name_fa", "relationship_type", "explanation")


class SourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceReference
        fields = ("id", "title", "organization", "citation", "url", "publication_year", "source_type")


class DisorderListSerializer(serializers.ModelSerializer):
    category = serializers.CharField(source="category.name_fa")
    category_slug = serializers.CharField(source="category.slug")

    class Meta:
        model = Disorder
        fields = ("id", "slug", "name_en", "name_fa", "short_description", "category", "category_slug", "data_origin")


class DisorderDetailSerializer(DisorderListSerializer):
    symptoms = SymptomLinkSerializer(source="symptom_links", many=True)
    related = serializers.SerializerMethodField()
    sources = serializers.SerializerMethodField()
    study_resources = serializers.SerializerMethodField()
    concepts = serializers.SerializerMethodField()

    class Meta(DisorderListSerializer.Meta):
        fields = DisorderListSerializer.Meta.fields + (
            "overview",
            "clinical_features",
            "risk_factors",
            "treatment_overview",
            "assessment_overview",
            "typical_onset",
            "course_note",
            "symptoms",
            "related",
            "sources",
            "study_resources",
            "concepts",
        )

    def get_related(self, obj):
        rows = []
        seen = set()
        for relation in obj.outgoing_relationships.all():
            other = relation.related_disorder
            if not other.is_active:
                continue
            key = (other.slug, relation.relationship_type)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "slug": other.slug,
                "name_en": other.name_en,
                "name_fa": other.name_fa,
                "relationship_type": relation.relationship_type,
                "explanation": relation.explanation,
            })
        for relation in obj.incoming_relationships.all():
            other = relation.disorder
            if not other.is_active:
                continue
            key = (other.slug, relation.relationship_type)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "slug": other.slug,
                "name_en": other.name_en,
                "name_fa": other.name_fa,
                "relationship_type": relation.relationship_type,
                "explanation": relation.explanation,
            })
        return rows

    def get_sources(self, obj):
        return SourceSerializer([x.source for x in obj.source_links.all()], many=True).data

    def get_study_resources(self, obj):
        quizzes = sorted((q for q in obj.quizzes.all() if q.is_active), key=lambda q: q.title)[:4]
        cases = sorted((c for c in obj.clinical_cases.all() if c.is_active), key=lambda c: c.title)[:4]
        return {
            "quizzes": [{"slug": q.slug, "title": q.title} for q in quizzes],
            "cases": [
                {"slug": c.slug, "title": c.title, "difficulty": c.difficulty}
                for c in cases
            ],
        }

    def get_concepts(self, obj):
        return [
            {
                "slug": link.concept.slug,
                "name_en": link.concept.name_en,
                "name_fa": link.concept.name_fa,
                "kind": link.concept.kind,
                "role": link.role,
                "explanation": link.explanation,
            }
            for link in obj.concept_links.all()
            if link.concept.is_active
        ]


class QuizChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizChoice
        fields = ("id", "text")


class QuizQuestionSerializer(serializers.ModelSerializer):
    choices = serializers.SerializerMethodField()

    class Meta:
        model = QuizQuestion
        fields = ("id", "prompt", "sort_order", "choices")

    def get_choices(self, obj):
        return QuizChoiceSerializer(obj.choices.filter(is_active=True).order_by("sort_order", "id"), many=True).data


class QuizListSerializer(serializers.ModelSerializer):
    disorder = DisorderListSerializer(read_only=True)
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = ("id", "slug", "title", "description", "disorder", "question_count")

    def get_question_count(self, obj):
        return obj.questions.filter(is_active=True).count()


class QuizDetailSerializer(QuizListSerializer):
    questions = serializers.SerializerMethodField()

    class Meta(QuizListSerializer.Meta):
        fields = QuizListSerializer.Meta.fields + ("questions",)

    def get_questions(self, obj):
        return QuizQuestionSerializer(obj.questions.filter(is_active=True).order_by("sort_order", "id"), many=True).data


class CaseChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseChoice
        fields = ("id", "text")


class CaseQuestionSerializer(serializers.ModelSerializer):
    choices = serializers.SerializerMethodField()

    class Meta:
        model = CaseQuestion
        fields = ("id", "prompt", "sort_order", "choices")

    def get_choices(self, obj):
        return CaseChoiceSerializer(obj.choices.filter(is_active=True).order_by("sort_order", "id"), many=True).data


class CaseStepSerializer(serializers.ModelSerializer):
    questions = serializers.SerializerMethodField()

    class Meta:
        model = CaseStep
        fields = ("id", "title", "narrative", "sort_order", "questions")

    def get_questions(self, obj):
        return CaseQuestionSerializer(obj.questions.filter(is_active=True).order_by("sort_order", "id"), many=True).data


class ClinicalCaseListSerializer(serializers.ModelSerializer):
    primary_disorder = DisorderListSerializer(read_only=True)
    step_count = serializers.SerializerMethodField()

    class Meta:
        model = ClinicalCase
        fields = ("id", "slug", "title", "patient_summary", "difficulty", "primary_disorder", "step_count")

    def get_step_count(self, obj):
        return obj.steps.filter(is_active=True).count()


class ClinicalCaseDetailSerializer(ClinicalCaseListSerializer):
    steps = serializers.SerializerMethodField()

    class Meta(ClinicalCaseListSerializer.Meta):
        fields = ClinicalCaseListSerializer.Meta.fields + ("educational_objective", "steps")

    def get_steps(self, obj):
        return CaseStepSerializer(obj.steps.filter(is_active=True).order_by("sort_order", "id"), many=True).data


class BookmarkSerializer(serializers.ModelSerializer):
    disorder = DisorderListSerializer(read_only=True)

    class Meta:
        model = Bookmark
        fields = ("id", "disorder", "created_at")


class ProgressSerializer(serializers.ModelSerializer):
    disorder = DisorderListSerializer(read_only=True)

    class Meta:
        model = UserProgress
        fields = ("disorder", "status", "progress_percent", "last_viewed_at", "completed_at")


class UserNoteSerializer(serializers.ModelSerializer):
    disorder = DisorderListSerializer(read_only=True)

    class Meta:
        model = UserNote
        fields = ("id", "disorder", "body", "created_at", "updated_at")
        read_only_fields = ("id", "disorder", "created_at", "updated_at")


# Unified concept and study serializers
from rest_framework import serializers

from .models import (
    Concept,
    ConceptAlias,
    ConceptBookmark,
    ConceptNote,
    DailyChallenge,
    DailyChallengeChoice,
    Flashcard,
    SourceReference,
    UserFlashcardProgress,
    Technique,
    TechniqueAlias,
    Therapy,
    TherapyAlias,
    TherapyClassification,
    TherapyFamily,
)


class ConceptAliasSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConceptAlias
        fields = ("text", "language", "alias_type")


class ConceptListSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    domain_label = serializers.CharField(source="get_domain_display", read_only=True)
    subtype_label = serializers.CharField(source="get_subtype_display", read_only=True)
    aliases = ConceptAliasSerializer(many=True, read_only=True)

    class Meta:
        model = Concept
        fields = (
            "id",
            "slug",
            "name_en",
            "name_fa",
            "kind",
            "kind_label",
            "domain",
            "domain_label",
            "subtype",
            "subtype_label",
            "simple_definition",
            "aliases",
        )


class ConceptCatalogSerializer(ConceptListSerializer):
    disorder_count = serializers.SerializerMethodField()
    flashcard_count = serializers.SerializerMethodField()
    relationship_count = serializers.SerializerMethodField()

    class Meta(ConceptListSerializer.Meta):
        fields = ConceptListSerializer.Meta.fields + (
            "disorder_count",
            "flashcard_count",
            "relationship_count",
        )

    def get_disorder_count(self, obj):
        return sum(1 for link in obj.disorder_links.all() if link.disorder.is_active)

    def get_flashcard_count(self, obj):
        return sum(1 for card in obj.flashcards.all() if card.is_active)

    def get_relationship_count(self, obj):
        outgoing = sum(1 for row in obj.outgoing_concept_relationships.all() if row.target_concept.is_active)
        incoming = sum(1 for row in obj.incoming_concept_relationships.all() if row.source_concept.is_active)
        return outgoing + incoming


class ConceptDetailSerializer(ConceptCatalogSerializer):
    relationships = serializers.SerializerMethodField()
    disorders = serializers.SerializerMethodField()
    sources = serializers.SerializerMethodField()

    symptoms = serializers.SerializerMethodField()

    class Meta(ConceptCatalogSerializer.Meta):
        fields = ConceptCatalogSerializer.Meta.fields + (
            "academic_definition",
            "example",
            "counterexample",
            "recognition_cues",
            "common_confusions",
            "relationships",
            "disorders",
            "symptoms",
            "sources",
        )

    def get_relationships(self, obj):
        rows = []
        seen = set()
        for relation in obj.outgoing_concept_relationships.all():
            other = relation.target_concept
            if not other.is_active:
                continue
            key = (other.slug, relation.relationship_type, "outgoing")
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "slug": other.slug,
                "name_en": other.name_en,
                "name_fa": other.name_fa,
                "relationship_type": relation.relationship_type,
                "direction": "outgoing",
                "explanation": relation.explanation,
                "sources": SourceSerializer([link.source for link in relation.source_links.all()], many=True).data,
            })
        for relation in obj.incoming_concept_relationships.all():
            other = relation.source_concept
            if not other.is_active:
                continue
            key = (other.slug, relation.relationship_type, "incoming")
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "slug": other.slug,
                "name_en": other.name_en,
                "name_fa": other.name_fa,
                "relationship_type": relation.relationship_type,
                "direction": "incoming",
                "explanation": relation.explanation,
                "sources": SourceSerializer([link.source for link in relation.source_links.all()], many=True).data,
            })
        return rows

    def get_disorders(self, obj):
        return [
            {
                "role": link.role,
                "explanation": link.explanation,
                "disorder": DisorderListSerializer(link.disorder).data,
            }
            for link in obj.disorder_links.all()
            if link.disorder.is_active
        ]

    def get_symptoms(self, obj):
        return [
            {
                "slug": link.symptom.slug,
                "name_en": link.symptom.name_en,
                "name_fa": link.symptom.name_fa,
                "domain": link.symptom.domain,
                "relationship_type": link.relationship_type,
                "explanation": link.explanation,
            }
            for link in obj.symptom_links.all()
        ]

    def get_sources(self, obj):
        return SourceSerializer([link.source for link in obj.source_links.all()], many=True).data


class FlashcardSerializer(serializers.ModelSerializer):
    concept = ConceptListSerializer(read_only=True)
    disorder = DisorderListSerializer(read_only=True)

    class Meta:
        model = Flashcard
        fields = (
            "id",
            "slug",
            "front",
            "back",
            "hint",
            "difficulty",
            "concept",
            "disorder",
        )


class FlashcardProgressSerializer(serializers.ModelSerializer):
    flashcard = FlashcardSerializer(read_only=True)

    class Meta:
        model = UserFlashcardProgress
        fields = (
            "flashcard",
            "state",
            "due_at",
            "interval_days",
            "ease_factor",
            "repetitions",
            "lapses",
            "last_rating",
            "last_reviewed_at",
        )


class ConceptBookmarkSerializer(serializers.ModelSerializer):
    concept = ConceptListSerializer(read_only=True)

    class Meta:
        model = ConceptBookmark
        fields = ("id", "concept", "created_at")


class ConceptNoteSerializer(serializers.ModelSerializer):
    concept = ConceptListSerializer(read_only=True)

    class Meta:
        model = ConceptNote
        fields = ("id", "concept", "body", "created_at", "updated_at")
        read_only_fields = ("id", "concept", "created_at", "updated_at")


class DailyChallengeChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyChallengeChoice
        fields = ("id", "text")


class DailyChallengeSerializer(serializers.ModelSerializer):
    choices = serializers.SerializerMethodField()
    concept = serializers.SerializerMethodField()
    disorder = serializers.SerializerMethodField()

    class Meta:
        model = DailyChallenge
        fields = ("id", "prompt", "choices", "concept", "disorder")

    def get_choices(self, obj):
        return DailyChallengeChoiceSerializer(
            obj.choices.filter(is_active=True).order_by("sort_order", "id"),
            many=True,
        ).data

    def get_concept(self, obj):
        if not obj.concept_id or not obj.concept.is_active:
            return None
        return ConceptListSerializer(obj.concept).data

    def get_disorder(self, obj):
        if not obj.disorder_id or not obj.disorder.is_active:
            return None
        return DisorderListSerializer(obj.disorder).data

class TherapyFamilySerializer(serializers.ModelSerializer):
    class Meta:
        model = TherapyFamily
        fields = ("slug", "name_en", "name_fa", "description")


class TherapyClassificationSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = TherapyClassification
        fields = ("slug", "name_en", "name_fa", "kind", "kind_label", "description")


class TherapyAliasSerializer(serializers.ModelSerializer):
    class Meta:
        model = TherapyAlias
        fields = ("text", "language", "alias_type")


class TechniqueAliasSerializer(serializers.ModelSerializer):
    class Meta:
        model = TechniqueAlias
        fields = ("text", "language", "alias_type")


class TechniqueListSerializer(serializers.ModelSerializer):
    aliases = TechniqueAliasSerializer(many=True, read_only=True)
    therapy_count = serializers.SerializerMethodField()
    concept_count = serializers.SerializerMethodField()

    class Meta:
        model = Technique
        fields = (
            "id", "slug", "name_en", "name_fa", "summary", "review_status",
            "aliases", "therapy_count", "concept_count",
        )

    def get_therapy_count(self, obj):
        return sum(
            1 for link in obj.therapy_links.all()
            if link.is_active and link.therapy.is_active and link.therapy.family.is_active
        )

    def get_concept_count(self, obj):
        return sum(1 for link in obj.concept_links.all() if link.is_active and link.concept.is_active)


class TherapyListSerializer(serializers.ModelSerializer):
    family = TherapyFamilySerializer(read_only=True)
    aliases = TherapyAliasSerializer(many=True, read_only=True)
    classifications = serializers.SerializerMethodField()
    technique_count = serializers.SerializerMethodField()
    disorder_count = serializers.SerializerMethodField()
    concept_count = serializers.SerializerMethodField()

    class Meta:
        model = Therapy
        fields = (
            "id", "slug", "name_en", "name_fa", "summary", "family", "aliases",
            "classifications", "review_status", "technique_count", "disorder_count", "concept_count",
        )

    def get_classifications(self, obj):
        return TherapyClassificationSerializer(
            [link.classification for link in obj.classification_links.all() if link.is_active and link.classification.is_active],
            many=True,
        ).data

    def get_technique_count(self, obj):
        return sum(1 for link in obj.technique_links.all() if link.is_active and link.technique.is_active)

    def get_disorder_count(self, obj):
        return sum(1 for link in obj.disorder_links.all() if link.is_active and link.disorder.is_active)

    def get_concept_count(self, obj):
        return sum(1 for link in obj.concept_links.all() if link.is_active and link.concept.is_active)


class TherapyDetailSerializer(TherapyListSerializer):
    sources = serializers.SerializerMethodField()
    techniques = serializers.SerializerMethodField()
    disorders = serializers.SerializerMethodField()
    concepts = serializers.SerializerMethodField()

    class Meta(TherapyListSerializer.Meta):
        fields = TherapyListSerializer.Meta.fields + (
            "academic_definition", "historical_context", "core_principles", "typical_structure",
            "appropriate_contexts", "limitations", "safety_notes", "evidence_note",
            "sources", "techniques", "disorders", "concepts",
        )

    def get_sources(self, obj):
        return SourceSerializer([link.source for link in obj.source_links.all()], many=True).data

    def get_techniques(self, obj):
        rows = []
        for link in obj.technique_links.all():
            if not link.is_active or not link.technique.is_active:
                continue
            rows.append({
                "role": link.role,
                "explanation": link.explanation,
                "technique": TechniqueListSerializer(link.technique).data,
                "sources": SourceSerializer([row.source for row in link.source_links.all()], many=True).data,
            })
        return rows

    def get_disorders(self, obj):
        rows = []
        for link in obj.disorder_links.all():
            if not link.is_active or not link.disorder.is_active:
                continue
            rows.append({
                "clinical_role": link.clinical_role,
                "clinical_role_label": link.get_clinical_role_display(),
                "evidence_basis": link.evidence_basis,
                "evidence_basis_label": link.get_evidence_basis_display(),
                "explanation": link.explanation,
                "evidence_note": link.evidence_note,
                "disorder": DisorderListSerializer(link.disorder).data,
                "sources": SourceSerializer([row.source for row in link.source_links.all()], many=True).data,
            })
        return rows

    def get_concepts(self, obj):
        rows = []
        for link in obj.concept_links.all():
            if not link.is_active or not link.concept.is_active:
                continue
            rows.append({
                "relationship_type": link.relationship_type,
                "explanation": link.explanation,
                "concept": ConceptListSerializer(link.concept).data,
                "sources": SourceSerializer([row.source for row in link.source_links.all()], many=True).data,
            })
        return rows


class TechniqueDetailSerializer(TechniqueListSerializer):
    sources = serializers.SerializerMethodField()
    therapies = serializers.SerializerMethodField()
    concepts = serializers.SerializerMethodField()

    class Meta(TechniqueListSerializer.Meta):
        fields = TechniqueListSerializer.Meta.fields + (
            "academic_definition", "application_notes", "limitations", "safety_notes",
            "sources", "therapies", "concepts",
        )

    def get_sources(self, obj):
        return SourceSerializer([link.source for link in obj.source_links.all()], many=True).data

    def get_therapies(self, obj):
        rows = []
        for link in obj.therapy_links.all():
            if not link.is_active or not link.therapy.is_active or not link.therapy.family.is_active:
                continue
            rows.append({
                "role": link.role,
                "explanation": link.explanation,
                "therapy": {
                    "slug": link.therapy.slug,
                    "name_en": link.therapy.name_en,
                    "name_fa": link.therapy.name_fa,
                    "family": TherapyFamilySerializer(link.therapy.family).data,
                },
                "sources": SourceSerializer([row.source for row in link.source_links.all()], many=True).data,
            })
        return rows

    def get_concepts(self, obj):
        rows = []
        for link in obj.concept_links.all():
            if not link.is_active or not link.concept.is_active:
                continue
            rows.append({
                "relationship_type": link.relationship_type,
                "explanation": link.explanation,
                "concept": ConceptListSerializer(link.concept).data,
                "sources": SourceSerializer([row.source for row in link.source_links.all()], many=True).data,
            })
        return rows
