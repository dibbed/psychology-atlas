from rest_framework import serializers

from .models import (
    Concept,
    ConceptBookmark,
    ConceptNote,
    DailyChallenge,
    DailyChallengeChoice,
    Flashcard,
    SourceReference,
    UserFlashcardProgress,
)
from .serializers import DisorderListSerializer, SourceSerializer


class ConceptListSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Concept
        fields = (
            "id",
            "slug",
            "name_en",
            "name_fa",
            "kind",
            "kind_label",
            "simple_definition",
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

    class Meta(ConceptCatalogSerializer.Meta):
        fields = ConceptCatalogSerializer.Meta.fields + (
            "academic_definition",
            "example",
            "relationships",
            "disorders",
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
    choices = DailyChallengeChoiceSerializer(many=True)
    concept = serializers.SerializerMethodField()
    disorder = serializers.SerializerMethodField()

    class Meta:
        model = DailyChallenge
        fields = ("id", "prompt", "choices", "concept", "disorder")

    def get_concept(self, obj):
        if not obj.concept_id or not obj.concept.is_active:
            return None
        return ConceptListSerializer(obj.concept).data

    def get_disorder(self, obj):
        if not obj.disorder_id or not obj.disorder.is_active:
            return None
        return DisorderListSerializer(obj.disorder).data
