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
        fields = ("id", "slug", "name_en", "name_fa", "short_description", "category", "category_slug")


class DisorderDetailSerializer(DisorderListSerializer):
    symptoms = SymptomLinkSerializer(source="symptom_links", many=True)
    related = serializers.SerializerMethodField()
    sources = serializers.SerializerMethodField()
    study_resources = serializers.SerializerMethodField()

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
        )

    def get_related(self, obj):
        rows = []
        seen = set()
        for relation in obj.outgoing_relationships.all():
            other = relation.related_disorder
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


class QuizChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuizChoice
        fields = ("id", "text")


class QuizQuestionSerializer(serializers.ModelSerializer):
    choices = QuizChoiceSerializer(many=True)

    class Meta:
        model = QuizQuestion
        fields = ("id", "prompt", "sort_order", "choices")


class QuizListSerializer(serializers.ModelSerializer):
    disorder = DisorderListSerializer(read_only=True)
    question_count = serializers.SerializerMethodField()

    class Meta:
        model = Quiz
        fields = ("id", "slug", "title", "description", "disorder", "question_count")

    def get_question_count(self, obj):
        return obj.questions.count()


class QuizDetailSerializer(QuizListSerializer):
    questions = QuizQuestionSerializer(many=True)

    class Meta(QuizListSerializer.Meta):
        fields = QuizListSerializer.Meta.fields + ("questions",)


class CaseChoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseChoice
        fields = ("id", "text")


class CaseQuestionSerializer(serializers.ModelSerializer):
    choices = CaseChoiceSerializer(many=True)

    class Meta:
        model = CaseQuestion
        fields = ("id", "prompt", "sort_order", "choices")


class CaseStepSerializer(serializers.ModelSerializer):
    questions = CaseQuestionSerializer(many=True)

    class Meta:
        model = CaseStep
        fields = ("id", "title", "narrative", "sort_order", "questions")


class ClinicalCaseListSerializer(serializers.ModelSerializer):
    primary_disorder = DisorderListSerializer(read_only=True)
    step_count = serializers.SerializerMethodField()

    class Meta:
        model = ClinicalCase
        fields = ("id", "slug", "title", "patient_summary", "difficulty", "primary_disorder", "step_count")

    def get_step_count(self, obj):
        return obj.steps.count()


class ClinicalCaseDetailSerializer(ClinicalCaseListSerializer):
    steps = CaseStepSerializer(many=True)

    class Meta(ClinicalCaseListSerializer.Meta):
        fields = ClinicalCaseListSerializer.Meta.fields + ("educational_objective", "steps")


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
