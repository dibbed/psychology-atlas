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


class ConceptDetailSerializer(ConceptListSerializer):
    relationships = serializers.SerializerMethodField()
    disorders = serializers.SerializerMethodField()
    sources = serializers.SerializerMethodField()
    flashcard_count = serializers.SerializerMethodField()

    class Meta(ConceptListSerializer.Meta):
        fields = ConceptListSerializer.Meta.fields + (
            "academic_definition",
            "example",
            "relationships",
            "disorders",
            "sources",
            "flashcard_count",
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

    def get_flashcard_count(self, obj):
        return sum(1 for card in obj.flashcards.all() if card.is_active)


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
    concept = ConceptListSerializer(read_only=True)
    disorder = DisorderListSerializer(read_only=True)

    class Meta:
        model = DailyChallenge
        fields = ("id", "prompt", "choices", "concept", "disorder")
