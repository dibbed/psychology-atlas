from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError
from django.db.models import Q
from rest_framework import serializers

from . import models as atlas_models
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
    therapies = serializers.SerializerMethodField()

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
            "therapies",
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

    def get_therapies(self, obj):
        rows = []
        for link in obj.therapy_links.all():
            therapy = link.therapy
            if not link.is_active or not therapy.is_active or not therapy.family.is_active:
                continue
            rows.append({
                "slug": therapy.slug,
                "name_en": therapy.name_en,
                "name_fa": therapy.name_fa,
                "summary": therapy.summary,
                "family": {
                    "slug": therapy.family.slug,
                    "name_en": therapy.family.name_en,
                    "name_fa": therapy.family.name_fa,
                },
                "clinical_role": link.clinical_role,
                "clinical_role_label": link.get_clinical_role_display(),
                "evidence_basis": link.evidence_basis,
                "evidence_basis_label": link.get_evidence_basis_display(),
                "explanation": link.explanation,
                "evidence_note": link.evidence_note,
                "sources": SourceSerializer([row.source for row in link.source_links.all()], many=True).data,
            })
        return rows


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
        choices = [choice for choice in obj.choices.all() if choice.is_active]
        choices.sort(key=lambda choice: (choice.sort_order, choice.id))
        return CaseChoiceSerializer(choices, many=True).data


class CaseStepSerializer(serializers.ModelSerializer):
    questions = serializers.SerializerMethodField()

    class Meta:
        model = CaseStep
        fields = ("id", "stable_key", "node_kind", "title", "narrative", "sort_order", "questions")

    def get_questions(self, obj):
        questions = [question for question in obj.questions.all() if question.is_active]
        questions.sort(key=lambda question: (question.sort_order, question.id))
        return CaseQuestionSerializer(questions, many=True).data


class ClinicalCaseListSerializer(serializers.ModelSerializer):
    primary_disorder = DisorderListSerializer(read_only=True)
    step_count = serializers.SerializerMethodField()
    revision_number = serializers.SerializerMethodField()

    class Meta:
        model = ClinicalCase
        fields = (
            "id",
            "slug",
            "title",
            "patient_summary",
            "difficulty",
            "structure_mode",
            "revision_number",
            "primary_disorder",
            "step_count",
        )

    def get_step_count(self, obj):
        if not obj.current_revision_id:
            return 0
        return sum(1 for step in obj.current_revision.steps.all() if step.is_active)

    def get_revision_number(self, obj):
        return obj.current_revision.version if obj.current_revision_id else None


class ClinicalCaseDetailSerializer(ClinicalCaseListSerializer):
    steps = serializers.SerializerMethodField()

    class Meta(ClinicalCaseListSerializer.Meta):
        fields = ClinicalCaseListSerializer.Meta.fields + ("educational_objective", "steps")

    def get_steps(self, obj):
        if not obj.current_revision_id:
            return []
        steps = [step for step in obj.current_revision.steps.all() if step.is_active]
        return CaseStepSerializer(steps, many=True).data


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
    TherapyBookmark,
    TherapyClassification,
    TherapyFamily,
    TherapyNote,
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
    therapies = serializers.SerializerMethodField()
    techniques = serializers.SerializerMethodField()

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
            "therapies",
            "techniques",
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

    def get_therapies(self, obj):
        rows = []
        for link in obj.therapy_links.all():
            therapy = link.therapy
            if not link.is_active or not therapy.is_active or not therapy.family.is_active:
                continue
            rows.append({
                "relationship_type": link.relationship_type,
                "explanation": link.explanation,
                "therapy": {
                    "slug": therapy.slug,
                    "name_en": therapy.name_en,
                    "name_fa": therapy.name_fa,
                    "summary": therapy.summary,
                    "family": {
                        "slug": therapy.family.slug,
                        "name_en": therapy.family.name_en,
                        "name_fa": therapy.family.name_fa,
                    },
                },
                "sources": SourceSerializer([row.source for row in link.source_links.all()], many=True).data,
            })
        return rows

    def get_techniques(self, obj):
        rows = []
        for link in obj.technique_links.all():
            technique = link.technique
            if not link.is_active or not technique.is_active:
                continue
            rows.append({
                "relationship_type": link.relationship_type,
                "explanation": link.explanation,
                "technique": {
                    "slug": technique.slug,
                    "name_en": technique.name_en,
                    "name_fa": technique.name_fa,
                    "summary": technique.summary,
                },
                "sources": SourceSerializer([row.source for row in link.source_links.all()], many=True).data,
            })
        return rows

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


class TherapyBookmarkSerializer(serializers.ModelSerializer):
    therapy = TherapyListSerializer(read_only=True)

    class Meta:
        model = TherapyBookmark
        fields = ("id", "therapy", "created_at")
        read_only_fields = ("id", "therapy", "created_at")


class TherapyNoteSerializer(serializers.ModelSerializer):
    therapy = TherapyListSerializer(read_only=True)

    class Meta:
        model = TherapyNote
        fields = ("id", "therapy", "body", "created_at", "updated_at")
        read_only_fields = ("id", "therapy", "created_at", "updated_at")


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


class ScientificSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = atlas_models.SourceReference
        fields = (
            "id", "title", "organization", "citation", "url", "publication_year",
            "source_type", "authors", "doi", "pmid", "verification_status",
        )


class PsychologistAliasV6Serializer(serializers.ModelSerializer):
    class Meta:
        model = atlas_models.PsychologistAlias
        fields = ("text", "language", "alias_type")


class TheoryAliasV6Serializer(serializers.ModelSerializer):
    class Meta:
        model = atlas_models.TheoryAlias
        fields = ("text", "language", "alias_type")


def _entity_source_links(links):
    return [
        {
            "role": link.role,
            "role_label": link.get_role_display(),
            "note": link.note,
            "source": ScientificSourceSerializer(link.source).data,
        }
        for link in links
    ]


def _relation_sources(link):
    return ScientificSourceSerializer(
        [row.source for row in link.source_links.all()],
        many=True,
    ).data


def _psychologist_brief(obj):
    return {
        "slug": obj.slug,
        "name_en": obj.name_en,
        "name_fa": obj.name_fa,
        "role_en": obj.role_en,
        "role_fa": obj.role_fa,
        "review_status": obj.review_status,
    }


def _theory_brief(obj):
    return {
        "slug": obj.slug,
        "name_en": obj.name_en,
        "name_fa": obj.name_fa,
        "domain": obj.domain,
        "modern_status": obj.modern_status,
        "review_status": obj.review_status,
    }


def _concept_brief(obj):
    return {
        "slug": obj.slug,
        "name_en": obj.name_en,
        "name_fa": obj.name_fa,
        "kind": obj.kind,
        "domain": obj.domain,
    }


def _therapy_brief(obj):
    return {
        "slug": obj.slug,
        "name_en": obj.name_en,
        "name_fa": obj.name_fa,
        "family": {
            "slug": obj.family.slug,
            "name_en": obj.family.name_en,
            "name_fa": obj.family.name_fa,
        } if obj.family_id else None,
        "review_status": obj.review_status,
    }


def _technique_brief(obj):
    return {
        "slug": obj.slug,
        "name_en": obj.name_en,
        "name_fa": obj.name_fa,
        "review_status": obj.review_status,
    }


def _timeline_brief(obj):
    return {
        "slug": obj.slug,
        "title_en": obj.title_en,
        "title_fa": obj.title_fa,
        "event_type": obj.event_type,
        "date_precision": obj.date_precision,
        "date_text": obj.date_text,
        "year_start": obj.year_start,
        "year_end": obj.year_end,
        "exact_date": obj.exact_date,
        "review_status": obj.review_status,
    }


def _annotated_or_prefetched_count(obj, annotation, manager_name, predicate):
    value = getattr(obj, annotation, None)
    if value is not None:
        return value
    return sum(1 for row in getattr(obj, manager_name).all() if predicate(row))


class PsychologistListSerializer(serializers.ModelSerializer):
    aliases = PsychologistAliasV6Serializer(many=True, read_only=True)
    theory_count = serializers.SerializerMethodField()
    concept_count = serializers.SerializerMethodField()
    therapy_count = serializers.SerializerMethodField()
    timeline_event_count = serializers.SerializerMethodField()

    class Meta:
        model = atlas_models.Psychologist
        fields = (
            "id", "slug", "name_en", "name_fa", "summary_en", "summary_fa",
            "role_en", "role_fa", "nationality_en", "nationality_fa",
            "birth_year", "death_year", "review_status", "aliases",
            "theory_count", "concept_count", "therapy_count", "timeline_event_count",
        )

    def get_theory_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "theory_count", "theory_links",
            lambda row: row.is_active and row.theory.is_active,
        )

    def get_concept_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "concept_count", "concept_links",
            lambda row: row.is_active and row.concept.is_active,
        )

    def get_therapy_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "therapy_count", "therapy_links",
            lambda row: row.is_active and row.therapy.is_active and row.therapy.family.is_active,
        )

    def get_timeline_event_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "timeline_event_count", "timeline_links",
            lambda row: row.is_active and row.event.is_active,
        )


class PsychologistDetailSerializer(PsychologistListSerializer):
    sources = serializers.SerializerMethodField()
    theories = serializers.SerializerMethodField()
    concepts = serializers.SerializerMethodField()
    therapies = serializers.SerializerMethodField()
    related_psychologists = serializers.SerializerMethodField()
    timeline_events = serializers.SerializerMethodField()

    class Meta(PsychologistListSerializer.Meta):
        fields = PsychologistListSerializer.Meta.fields + (
            "academic_disciplines", "contributions_en", "contributions_fa", "affiliations",
            "historical_context_en", "historical_context_fa", "sources", "theories",
            "concepts", "therapies", "related_psychologists", "timeline_events",
        )

    def get_sources(self, obj):
        return _entity_source_links(obj.source_links.all())

    def get_theories(self, obj):
        return [
            {
                "relationship_type": link.relationship_type,
                "relationship_label": link.get_relationship_type_display(),
                "explanation_en": link.explanation_en,
                "explanation_fa": link.explanation_fa,
                "review_status": link.review_status,
                "theory": _theory_brief(link.theory),
                "sources": _relation_sources(link),
            }
            for link in obj.theory_links.all()
            if link.is_active and link.theory.is_active
        ]

    def get_concepts(self, obj):
        return [
            {
                "relationship_type": link.relationship_type,
                "relationship_label": link.get_relationship_type_display(),
                "explanation_en": link.explanation_en,
                "explanation_fa": link.explanation_fa,
                "review_status": link.review_status,
                "concept": _concept_brief(link.concept),
                "sources": _relation_sources(link),
            }
            for link in obj.concept_links.all()
            if link.is_active and link.concept.is_active
        ]

    def get_therapies(self, obj):
        return [
            {
                "relationship_type": link.relationship_type,
                "relationship_label": link.get_relationship_type_display(),
                "explanation_en": link.explanation_en,
                "explanation_fa": link.explanation_fa,
                "review_status": link.review_status,
                "therapy": _therapy_brief(link.therapy),
                "sources": _relation_sources(link),
            }
            for link in obj.therapy_links.all()
            if link.is_active and link.therapy.is_active and link.therapy.family.is_active
        ]

    def get_related_psychologists(self, obj):
        rows = []
        for link in obj.outgoing_psychologist_links.all():
            if link.is_active and link.related_psychologist.is_active:
                rows.append({
                    "direction": "outgoing",
                    "relationship_type": link.relationship_type,
                    "relationship_label": link.get_relationship_type_display(),
                    "explanation_en": link.explanation_en,
                    "explanation_fa": link.explanation_fa,
                    "review_status": link.review_status,
                    "psychologist": _psychologist_brief(link.related_psychologist),
                    "sources": _relation_sources(link),
                })
        for link in obj.incoming_psychologist_links.all():
            if link.is_active and link.psychologist.is_active:
                rows.append({
                    "direction": "incoming",
                    "relationship_type": link.relationship_type,
                    "relationship_label": link.get_relationship_type_display(),
                    "explanation_en": link.explanation_en,
                    "explanation_fa": link.explanation_fa,
                    "review_status": link.review_status,
                    "psychologist": _psychologist_brief(link.psychologist),
                    "sources": _relation_sources(link),
                })
        return rows

    def get_timeline_events(self, obj):
        return [
            {
                "role": link.role,
                "role_label": link.get_role_display(),
                "review_status": link.review_status,
                "event": _timeline_brief(link.event),
                "sources": _relation_sources(link),
            }
            for link in obj.timeline_links.all()
            if link.is_active and link.event.is_active
        ]


class TheoryListSerializer(serializers.ModelSerializer):
    aliases = TheoryAliasV6Serializer(many=True, read_only=True)
    psychologist_count = serializers.SerializerMethodField()
    concept_count = serializers.SerializerMethodField()
    therapy_count = serializers.SerializerMethodField()
    technique_count = serializers.SerializerMethodField()
    timeline_event_count = serializers.SerializerMethodField()

    class Meta:
        model = atlas_models.Theory
        fields = (
            "id", "slug", "name_en", "name_fa", "domain", "period_text",
            "summary_en", "summary_fa", "modern_status", "review_status", "aliases",
            "psychologist_count", "concept_count", "therapy_count", "technique_count",
            "timeline_event_count",
        )

    def get_psychologist_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "psychologist_count", "psychologist_links",
            lambda row: row.is_active and row.psychologist.is_active,
        )

    def get_concept_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "concept_count", "concept_links",
            lambda row: row.is_active and row.concept.is_active,
        )

    def get_therapy_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "therapy_count", "therapy_links",
            lambda row: row.is_active and row.therapy.is_active and row.therapy.family.is_active,
        )

    def get_technique_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "technique_count", "technique_links",
            lambda row: row.is_active and row.technique.is_active,
        )

    def get_timeline_event_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "timeline_event_count", "timeline_links",
            lambda row: row.is_active and row.event.is_active,
        )


class TheoryDetailSerializer(TheoryListSerializer):
    sources = serializers.SerializerMethodField()
    psychologists = serializers.SerializerMethodField()
    concepts = serializers.SerializerMethodField()
    therapies = serializers.SerializerMethodField()
    techniques = serializers.SerializerMethodField()
    related_theories = serializers.SerializerMethodField()
    timeline_events = serializers.SerializerMethodField()

    class Meta(TheoryListSerializer.Meta):
        fields = TheoryListSerializer.Meta.fields + (
            "core_proposition_en", "core_proposition_fa", "historical_context_en",
            "historical_context_fa", "key_propositions_en", "key_propositions_fa",
            "applications_en", "applications_fa", "criticisms_en", "criticisms_fa",
            "limitations_en", "limitations_fa", "historical_importance_en",
            "historical_importance_fa", "sources", "psychologists", "concepts",
            "therapies", "techniques", "related_theories", "timeline_events",
        )

    def get_sources(self, obj):
        return _entity_source_links(obj.source_links.all())

    def get_psychologists(self, obj):
        return [
            {
                "relationship_type": link.relationship_type,
                "relationship_label": link.get_relationship_type_display(),
                "explanation_en": link.explanation_en,
                "explanation_fa": link.explanation_fa,
                "review_status": link.review_status,
                "psychologist": _psychologist_brief(link.psychologist),
                "sources": _relation_sources(link),
            }
            for link in obj.psychologist_links.all()
            if link.is_active and link.psychologist.is_active
        ]

    def get_concepts(self, obj):
        return [
            {
                "relationship_type": link.relationship_type,
                "relationship_label": link.get_relationship_type_display(),
                "explanation_en": link.explanation_en,
                "explanation_fa": link.explanation_fa,
                "review_status": link.review_status,
                "concept": _concept_brief(link.concept),
                "sources": _relation_sources(link),
            }
            for link in obj.concept_links.all()
            if link.is_active and link.concept.is_active
        ]

    def get_therapies(self, obj):
        return [
            {
                "relationship_type": link.relationship_type,
                "relationship_label": link.get_relationship_type_display(),
                "explanation_en": link.explanation_en,
                "explanation_fa": link.explanation_fa,
                "review_status": link.review_status,
                "therapy": _therapy_brief(link.therapy),
                "sources": _relation_sources(link),
            }
            for link in obj.therapy_links.all()
            if link.is_active and link.therapy.is_active and link.therapy.family.is_active
        ]

    def get_techniques(self, obj):
        return [
            {
                "relationship_type": link.relationship_type,
                "relationship_label": link.get_relationship_type_display(),
                "explanation_en": link.explanation_en,
                "explanation_fa": link.explanation_fa,
                "review_status": link.review_status,
                "technique": _technique_brief(link.technique),
                "sources": _relation_sources(link),
            }
            for link in obj.technique_links.all()
            if link.is_active and link.technique.is_active
        ]

    def get_related_theories(self, obj):
        rows = []
        for link in obj.outgoing_theory_links.all():
            if link.is_active and link.related_theory.is_active:
                rows.append({
                    "direction": "outgoing",
                    "relationship_type": link.relationship_type,
                    "relationship_label": link.get_relationship_type_display(),
                    "explanation_en": link.explanation_en,
                    "explanation_fa": link.explanation_fa,
                    "review_status": link.review_status,
                    "theory": _theory_brief(link.related_theory),
                    "sources": _relation_sources(link),
                })
        for link in obj.incoming_theory_links.all():
            if link.is_active and link.theory.is_active:
                rows.append({
                    "direction": "incoming",
                    "relationship_type": link.relationship_type,
                    "relationship_label": link.get_relationship_type_display(),
                    "explanation_en": link.explanation_en,
                    "explanation_fa": link.explanation_fa,
                    "review_status": link.review_status,
                    "theory": _theory_brief(link.theory),
                    "sources": _relation_sources(link),
                })
        return rows

    def get_timeline_events(self, obj):
        return [
            {
                "role": link.role,
                "role_label": link.get_role_display(),
                "review_status": link.review_status,
                "event": _timeline_brief(link.event),
                "sources": _relation_sources(link),
            }
            for link in obj.timeline_links.all()
            if link.is_active and link.event.is_active
        ]


class TimelineEventListSerializer(serializers.ModelSerializer):
    event_type_label = serializers.CharField(source="get_event_type_display", read_only=True)
    date_precision_label = serializers.CharField(source="get_date_precision_display", read_only=True)
    psychologist_count = serializers.SerializerMethodField()
    theory_count = serializers.SerializerMethodField()
    therapy_count = serializers.SerializerMethodField()
    technique_count = serializers.SerializerMethodField()
    concept_count = serializers.SerializerMethodField()

    class Meta:
        model = atlas_models.TimelineEvent
        fields = (
            "id", "slug", "title_en", "title_fa", "event_type", "event_type_label",
            "category", "date_precision", "date_precision_label", "date_text", "year_start",
            "year_end", "exact_date", "review_status", "psychologist_count", "theory_count",
            "therapy_count", "technique_count", "concept_count",
        )

    def get_psychologist_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "psychologist_count", "psychologist_links",
            lambda row: row.is_active and row.psychologist.is_active,
        )

    def get_theory_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "theory_count", "theory_links",
            lambda row: row.is_active and row.theory.is_active,
        )

    def get_therapy_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "therapy_count", "therapy_links",
            lambda row: row.is_active and row.therapy.is_active and row.therapy.family.is_active,
        )

    def get_technique_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "technique_count", "technique_links",
            lambda row: row.is_active and row.technique.is_active,
        )

    def get_concept_count(self, obj):
        return _annotated_or_prefetched_count(
            obj, "concept_count", "concept_links",
            lambda row: row.is_active and row.concept.is_active,
        )


class TimelineEventDetailSerializer(TimelineEventListSerializer):
    sources = serializers.SerializerMethodField()
    psychologists = serializers.SerializerMethodField()
    theories = serializers.SerializerMethodField()
    therapies = serializers.SerializerMethodField()
    techniques = serializers.SerializerMethodField()
    concepts = serializers.SerializerMethodField()

    class Meta(TimelineEventListSerializer.Meta):
        fields = TimelineEventListSerializer.Meta.fields + (
            "description_en", "description_fa", "historical_importance_en",
            "historical_importance_fa", "sources", "psychologists", "theories",
            "therapies", "techniques", "concepts",
        )

    def get_sources(self, obj):
        return _entity_source_links(obj.source_links.all())

    def get_psychologists(self, obj):
        return [
            {
                "role": link.role,
                "role_label": link.get_role_display(),
                "review_status": link.review_status,
                "psychologist": _psychologist_brief(link.psychologist),
                "sources": _relation_sources(link),
            }
            for link in obj.psychologist_links.all()
            if link.is_active and link.psychologist.is_active
        ]

    def get_theories(self, obj):
        return [
            {
                "role": link.role,
                "role_label": link.get_role_display(),
                "review_status": link.review_status,
                "theory": _theory_brief(link.theory),
                "sources": _relation_sources(link),
            }
            for link in obj.theory_links.all()
            if link.is_active and link.theory.is_active
        ]

    def get_therapies(self, obj):
        return [
            {
                "role": link.role,
                "role_label": link.get_role_display(),
                "review_status": link.review_status,
                "therapy": _therapy_brief(link.therapy),
                "sources": _relation_sources(link),
            }
            for link in obj.therapy_links.all()
            if link.is_active and link.therapy.is_active and link.therapy.family.is_active
        ]

    def get_techniques(self, obj):
        return [
            {
                "role": link.role,
                "role_label": link.get_role_display(),
                "review_status": link.review_status,
                "technique": _technique_brief(link.technique),
                "sources": _relation_sources(link),
            }
            for link in obj.technique_links.all()
            if link.is_active and link.technique.is_active
        ]

    def get_concepts(self, obj):
        return [
            {
                "role": link.role,
                "role_label": link.get_role_display(),
                "review_status": link.review_status,
                "concept": _concept_brief(link.concept),
                "sources": _relation_sources(link),
            }
            for link in obj.concept_links.all()
            if link.is_active and link.concept.is_active
        ]