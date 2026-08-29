from rest_framework import serializers

from .models import DSMRecord, DSMRecordRelation
from .serializers import DisorderListSerializer


class DSMRecordBriefSerializer(serializers.ModelSerializer):
    linked_disorder = DisorderListSerializer(read_only=True)

    class Meta:
        model = DSMRecord
        fields = (
            "master_id",
            "name_fa",
            "name_en",
            "display_type",
            "classification_status",
            "specialization_level",
            "root_section",
            "chapter_number",
            "chapter_name_fa",
            "chapter_name_en",
            "group_name",
            "summary",
            "linked_disorder",
        )


class DSMRecordDetailSerializer(DSMRecordBriefSerializer):
    parent = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()
    sources = serializers.SerializerMethodField()
    relations = serializers.SerializerMethodField()

    class Meta(DSMRecordBriefSerializer.Meta):
        fields = DSMRecordBriefSerializer.Meta.fields + (
            "source_type",
            "key_features",
            "assessment",
            "differential",
            "comorbidity",
            "course",
            "management",
            "assessment_tools",
            "context_considerations",
            "red_flags",
            "pitfalls",
            "nearby_titles",
            "official_updates",
            "homonym_info",
            "prevalence_numeric",
            "prevalence_policy",
            "coding",
            "source_keys",
            "sources",
            "quality",
            "exam_tip",
            "self_test",
            "structural_path",
            "parent",
            "children",
            "relations",
            "source_payload",
        )

    def get_parent(self, obj):
        if not obj.parent_id:
            return None
        return DSMRecordBriefSerializer(obj.parent).data

    def get_children(self, obj):
        rows = obj.children.filter(is_active=True).select_related("linked_disorder").order_by("sort_index")
        return DSMRecordBriefSerializer(rows, many=True).data

    def get_relations(self, obj):
        rows = []
        seen = set()
        for relation in obj.outgoing_dsm_relations.all():
            if not relation.target.is_active:
                continue
            key = (relation.target_id, relation.relationship_type, "out")
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "direction": "out",
                "relationship_type": relation.relationship_type,
                "explanation": relation.explanation,
                "record": DSMRecordBriefSerializer(relation.target).data,
            })
        for relation in obj.incoming_dsm_relations.all():
            if not relation.source.is_active:
                continue
            key = (relation.source_id, relation.relationship_type, "in")
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "direction": "in",
                "relationship_type": relation.relationship_type,
                "explanation": relation.explanation,
                "record": DSMRecordBriefSerializer(relation.source).data,
            })
        return rows

    def get_sources(self, obj):
        registry = obj.corpus.source_registry or {}
        return [
            {
                "key": key,
                **(registry.get(key) if isinstance(registry.get(key), dict) else {}),
            }
            for key in obj.source_keys
        ]
