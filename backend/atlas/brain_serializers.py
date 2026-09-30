"""Bounded Brain payloads. Staging documents and curation metadata are private."""

from rest_framework import serializers

from .brain_publication import NESTED_LIMIT
from .models import BrainAnatomicalEntity
from .serializers import ScientificSourceSerializer


def anatomy_brief(entity):
    return {key: getattr(entity, key) for key in ("slug", "name_en", "name_fa", "kind", "laterality", "review_status")}


def sources(rows):
    return [{"note": row.note, "source": ScientificSourceSerializer(row.source).data} for row in rows[:NESTED_LIMIT]]


def hierarchy(link, endpoint):
    return {
        "predicate": "part_of", "entity": anatomy_brief(getattr(link, endpoint)),
        "source_version": link.source_version, "review_status": link.review_status,
        "explanation_en": link.explanation_en, "explanation_fa": link.explanation_fa,
        "sources": sources(link.public_sources),
        "sources_truncated": len(link.public_sources) > NESTED_LIMIT,
    }


class BrainAnatomyListSerializer(serializers.ModelSerializer):
    aliases = serializers.SerializerMethodField()
    sources = serializers.SerializerMethodField()
    aliases_truncated = serializers.SerializerMethodField()
    sources_truncated = serializers.SerializerMethodField()

    class Meta:
        model = BrainAnatomicalEntity
        fields = ("id", "slug", "name_en", "name_fa", "kind", "laterality", "review_status",
                  "aliases", "sources", "aliases_truncated", "sources_truncated")

    def get_aliases(self, obj):
        return [{"text": row.text, "language": row.language, "alias_type": row.alias_type,
                 "review_status": row.review_status, "source_note": row.source_note,
                 "source": ScientificSourceSerializer(row.source).data}
                for row in obj.public_aliases[:NESTED_LIMIT]]

    def get_sources(self, obj):
        return sources(obj.public_sources)

    def get_aliases_truncated(self, obj):
        return len(obj.public_aliases) > NESTED_LIMIT

    def get_sources_truncated(self, obj):
        return len(obj.public_sources) > NESTED_LIMIT


class BrainAnatomyDetailSerializer(BrainAnatomyListSerializer):
    parent = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    children_truncated = serializers.SerializerMethodField()
    external_identifiers = serializers.SerializerMethodField()
    external_identifiers_truncated = serializers.SerializerMethodField()
    network_memberships = serializers.SerializerMethodField()
    network_memberships_truncated = serializers.SerializerMethodField()
    functional_associations = serializers.SerializerMethodField()
    functional_associations_truncated = serializers.SerializerMethodField()

    class Meta(BrainAnatomyListSerializer.Meta):
        fields = BrainAnatomyListSerializer.Meta.fields + (
            "description_en", "description_fa", "parent", "children", "children_truncated",
            "external_identifiers", "external_identifiers_truncated",
            "network_memberships", "network_memberships_truncated", "functional_associations", "functional_associations_truncated",
        )

    def get_parent(self, obj):
        return hierarchy(obj.public_parents[0], "parent") if obj.public_parents else None

    def get_children(self, obj):
        return [hierarchy(row, "child") for row in obj.public_children[:NESTED_LIMIT]]

    def get_children_truncated(self, obj):
        return len(obj.public_children) > NESTED_LIMIT

    def get_external_identifiers(self, obj):
        return [{**{key: getattr(row, key) for key in ("namespace", "identifier", "source_version", "url")},
                 "source": ScientificSourceSerializer(row.source).data}
                for row in obj.public_identifiers[:NESTED_LIMIT]]

    def get_external_identifiers_truncated(self, obj):
        return len(obj.public_identifiers) > NESTED_LIMIT

    def get_network_memberships(self, obj):
        return [{**evidence(row), "qualifier": row.qualifier,
                 "network": {key: getattr(row.network, key) for key in ("slug", "name_en", "name_fa", "kind", "review_status")}}
                for row in obj.public_memberships[:NESTED_LIMIT]]

    def get_functional_associations(self, obj):
        return [{**evidence(row), "subject_type": "anatomy", "task_context": row.task_context,
                 "population_context": row.population_context,
                 "concept": {key: getattr(row.concept, key) for key in ("slug", "name_en", "name_fa")}}
                for row in obj.public_associations[:NESTED_LIMIT]]

    def get_network_memberships_truncated(self, obj):
        return len(obj.public_memberships) > NESTED_LIMIT

    def get_functional_associations_truncated(self, obj):
        return len(obj.public_associations) > NESTED_LIMIT


def evidence(row):
    return {**{key: getattr(row, key) for key in ("evidence_key", "predicate", "review_status", "source_version", "method",
                                               "explanation_en", "explanation_fa", "limitations")},
            "sources": sources(row.public_sources), "sources_truncated": len(row.public_sources) > NESTED_LIMIT}
