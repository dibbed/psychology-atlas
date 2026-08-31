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
)
from .serializers import DisorderListSerializer, SourceSerializer


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
