import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from atlas.models import (
    Concept,
    ConceptAlias,
    ConceptRelationship,
    ConceptRelationshipSource,
    ConceptSource,
    ConceptSymptom,
    ConceptSymptomSource,
    Disorder,
    DisorderSource,
    ResearchDataset,
    ResearchRecord,
    ScientificReviewStatus,
    SourceReference,
    Symptom,
    Technique,
    TechniqueAlias,
    TechniqueConcept,
    TechniqueConceptSource,
    TechniqueSource,
    Therapy,
    TherapyAlias,
    TherapyClassification,
    TherapyClassificationLink,
    TherapyConcept,
    TherapyConceptSource,
    TherapyDisorder,
    TherapyDisorderSource,
    TherapyFamily,
    TherapySource,
    TherapyTechnique,
    TherapyTechniqueSource,
)


DEFAULT_FILENAMES = (
    "psychology_atlas_research_dataset.json",
    "psychology_atlas_research_dataset_complete___1.json",
)

LIST_SECTIONS = (
    "sources",
    "concepts",
    "cognitive_distortions",
    "symptoms",
    "disorders",
    "therapy_families",
    "therapy_classifications",
    "therapies",
    "techniques",
    "psychologists",
    "theories",
    "timeline_events",
    "relationships",
    "claims",
    "research_gaps",
    "potential_duplicates",
    "terminology_notes",
    "corrections",
)

ID_KEYS = {
    "sources": ("id", "source_id"),
    "concepts": ("id", "concept_id"),
    "cognitive_distortions": ("id", "distortion_id"),
    "symptoms": ("id", "symptom_id"),
    "disorders": ("id", "disorder_id"),
    "therapy_families": ("id", "family_id"),
    "therapy_classifications": ("id", "classification_id"),
    "therapies": ("id", "therapy_id"),
    "techniques": ("id", "technique_id"),
    "psychologists": ("id", "psychologist_id"),
    "theories": ("id", "theory_id"),
    "timeline_events": ("id", "event_id"),
    "relationships": ("id", "rel_id", "relationship_id"),
    "claims": ("id", "claim_id"),
    "research_gaps": ("id", "gap_id"),
    "potential_duplicates": ("id", "duplicate_id"),
    "terminology_notes": ("id", "note_id", "term_id"),
    "corrections": ("id", "correction_id"),
}

SOURCE_VERIFICATION_RANK = {
    "": 0,
    "citation_from_model_knowledge": 1,
    "constructed_for_this_dataset": 1,
    "search_context_verified": 2,
    "source_checked": 2,
    "search_verified": 3,
    "web_verified_doi": 3,
    "web_verified_doi_and_pmid": 4,
    "verified": 4,
}

CONCEPT_DOMAIN_MAP = {
    "psychopathology": Concept.Domain.PSYCHOPATHOLOGY,
    "clinical_psychology": Concept.Domain.PSYCHOPATHOLOGY,
    "clinical": Concept.Domain.PSYCHOPATHOLOGY,
    "cognitive_psychology": Concept.Domain.COGNITIVE_PSYCHOLOGY,
    "cognitive": Concept.Domain.COGNITIVE_PSYCHOLOGY,
    "cbt": Concept.Domain.CBT,
    "psychotherapy": Concept.Domain.CBT,
    "behavioral_psychology": Concept.Domain.BEHAVIORAL_SCIENCE,
    "behavioral_science": Concept.Domain.BEHAVIORAL_SCIENCE,
    "learning_and_behavior": Concept.Domain.BEHAVIORAL_SCIENCE,
    "emotion": Concept.Domain.EMOTION,
    "emotion_regulation": Concept.Domain.EMOTION,
    "interpersonal": Concept.Domain.INTERPERSONAL,
    "social_psychology": Concept.Domain.INTERPERSONAL,
    "assessment": Concept.Domain.ASSESSMENT,
}

SYMPTOM_DOMAIN_MAP = {
    "cognitive": Symptom.Domain.COGNITIVE,
    "thought": Symptom.Domain.COGNITIVE,
    "mood": Symptom.Domain.EMOTIONAL,
    "emotional": Symptom.Domain.EMOTIONAL,
    "emotion": Symptom.Domain.EMOTIONAL,
    "behavioral": Symptom.Domain.BEHAVIORAL,
    "behavioural": Symptom.Domain.BEHAVIORAL,
    "somatic": Symptom.Domain.SOMATIC,
    "physical": Symptom.Domain.SOMATIC,
    "sleep": Symptom.Domain.SOMATIC,
    "interpersonal": Symptom.Domain.INTERPERSONAL,
    "social": Symptom.Domain.INTERPERSONAL,
}


class ImportContext:
    def __init__(self, path, document, dataset, is_complete):
        self.path = path
        self.document = document
        self.dataset = dataset
        self.is_complete = is_complete
        self.source_map = {}
        self.entity_map = {}

    def map_entity(self, external_id, obj):
        if external_id:
            self.entity_map[str(external_id)] = obj


class Command(BaseCommand):
    help = (
        "Losslessly ingest Psychology Atlas research JSON datasets and conservatively "
        "promote source-backed v0.5-compatible records into canonical runtime tables."
    )

    def add_arguments(self, parser):
        parser.add_argument("paths", nargs="*", help="JSON files. Defaults to the two research files in project root.")
        parser.add_argument("--dry-run", action="store_true", help="Validate and execute inside a rolled-back transaction.")
        parser.add_argument("--no-promote", action="store_true", help="Store ResearchDataset/ResearchRecord only; do not touch runtime content.")

    def handle(self, *args, **options):
        paths = self._resolve_paths(options["paths"])
        dry_run = options["dry_run"]
        promote = not options["no_promote"]
        report = Counter()

        with transaction.atomic():
            contexts = [self._ingest_dataset(path, report) for path in paths]
            contexts.sort(key=lambda ctx: (ctx.is_complete, ctx.dataset.dataset_version), reverse=True)

            if promote:
                for ctx in contexts:
                    self._promote_sources(ctx, report)
                for ctx in contexts:
                    self._promote_concepts(ctx, report)
                    self._promote_symptoms(ctx, report)
                    self._map_disorders(ctx, report)
                    self._promote_families(ctx, report, create_new=ctx.is_complete)
                    self._promote_classifications(ctx, report, create_new=ctx.is_complete)
                    self._promote_therapies(ctx, report, create_new=ctx.is_complete)
                    self._promote_techniques(ctx, report, create_new=ctx.is_complete)
                for ctx in contexts:
                    if ctx.is_complete:
                        self._promote_supported_relationships(ctx, report)
                cache.delete("atlas_graph")

            if dry_run:
                transaction.set_rollback(True)

        mode = "DRY RUN" if dry_run else "COMMITTED"
        self.stdout.write(self.style.SUCCESS(f"Research import {mode}"))
        for key in sorted(report):
            self.stdout.write(f"  {key}: {report[key]}")

    def _resolve_paths(self, supplied):
        if supplied:
            paths = [Path(value).expanduser().resolve() for value in supplied]
        else:
            project_root = Path(settings.BASE_DIR).parent
            paths = [(project_root / filename).resolve() for filename in DEFAULT_FILENAMES]
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            suffix = ""
            if not supplied and ResearchDataset.objects.filter(is_active=True, raw_text__gt="").exists():
                suffix = (
                    " The original files may have been intentionally removed after verified ingestion; "
                    "use `python manage.py export_research_datasets <output_dir>` to reconstruct them "
                    "from the database, then pass the exported paths explicitly."
                )
            raise CommandError("Research dataset file(s) not found: " + ", ".join(missing) + suffix)
        return paths

    def _ingest_dataset(self, path, report):
        raw_bytes = path.read_bytes()
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        try:
            raw_text = raw_bytes.decode("utf-8")
            document = json.loads(raw_text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommandError(f"Invalid UTF-8 JSON: {path}: {exc}") from exc
        if not isinstance(document, dict):
            raise CommandError(f"Top-level JSON must be an object: {path}")

        metadata = document.get("dataset_metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        stats = document.get("statistics") or metadata.get("statistics") or {}
        if not isinstance(stats, dict):
            stats = {}
        quality_control = document.get("quality_control") or {}
        if not isinstance(quality_control, dict):
            quality_control = {}
        ingestion_audit = self._build_ingestion_audit(document)

        dataset_name = str(metadata.get("dataset_name") or path.stem)[:300]
        dataset_version = str(metadata.get("dataset_version") or metadata.get("version") or "")[:120]
        generated_at = str(metadata.get("generated_at") or metadata.get("generated") or "")[:120]
        key_base = slugify(f"{dataset_name}-{dataset_version}") or "psychology-research"
        key = f"{key_base[:160]}-{sha256[:12]}"

        dataset, created = ResearchDataset.objects.get_or_create(
            source_sha256=sha256,
            defaults={
                "key": key,
                "source_filename": path.name,
                "dataset_name": dataset_name,
                "dataset_version": dataset_version,
                "generated_at_text": generated_at,
                "metadata": metadata,
                "statistics": stats,
                "quality_control": quality_control,
                "ingestion_audit": ingestion_audit,
                "raw_document": document,
                "raw_text": raw_text,
                "is_active": True,
            },
        )
        if created:
            report["research_datasets_created"] += 1
        else:
            report["research_datasets_reused"] += 1
            changed = False
            for field, value in (
                ("source_filename", path.name),
                ("dataset_name", dataset_name),
                ("dataset_version", dataset_version),
                ("generated_at_text", generated_at),
                ("metadata", metadata),
                ("statistics", stats),
                ("quality_control", quality_control),
                ("ingestion_audit", ingestion_audit),
                ("raw_document", document),
                ("raw_text", raw_text),
                ("is_active", True),
            ):
                if getattr(dataset, field) != value:
                    setattr(dataset, field, value)
                    changed = True
            if changed:
                dataset.save()
                report["research_datasets_refreshed"] += 1

        for section in LIST_SECTIONS:
            rows = document.get(section) or []
            if not isinstance(rows, list):
                report[f"invalid_section_{section}"] += 1
                continue
            for index, payload in enumerate(rows):
                if not isinstance(payload, dict):
                    report[f"invalid_record_{section}"] += 1
                    continue
                external_id = self._external_id(section, payload, index)
                canonical_key = self._canonical_key(section, payload, external_id)
                name_en, name_fa = self._names(section, payload)
                source_ids = self._source_ids(payload)
                verification = str(
                    payload.get("verification_status")
                    or payload.get("verification")
                    or payload.get("evidence_status")
                    or ""
                )[:64]
                review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
                review_status = str(review.get("status") or "")[:64]
                defaults = {
                    "canonical_key": canonical_key[:400],
                    "slug": self._safe_slug(payload.get("slug"))[:220],
                    "name_en": name_en[:500],
                    "name_fa": name_fa[:500],
                    "source_ids": source_ids,
                    "verification_status": verification,
                    "review_status": review_status,
                    "payload": payload,
                }
                record, record_created = ResearchRecord.objects.update_or_create(
                    dataset=dataset,
                    section=section,
                    external_id=external_id[:300],
                    defaults=defaults,
                )
                report["research_records_created" if record_created else "research_records_reused"] += 1

        is_complete = "complete" in dataset_version.lower() or "complete" in path.name.lower()
        return ImportContext(path, document, dataset, is_complete)

    def _external_id(self, section, payload, index):
        for key in ID_KEYS.get(section, ("id",)):
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        return f"{section}:{digest}:{index}"

    def _canonical_key(self, section, payload, external_id):
        slug = self._safe_slug(payload.get("slug"))
        if section == "sources":
            doi = self._normalize_doi(payload.get("doi"))
            if doi:
                return f"source:doi:{doi}"
            url = self._normalize_url(payload.get("url"))
            if url:
                return f"source:url:{url}"
            title = self._normalize_name(payload.get("title"))
            year = payload.get("publication_year") or payload.get("year") or ""
            return f"source:title:{title}:{year}"
        entity_type = section.rstrip("s").replace("cognitive_distortion", "cognitive-distortion")
        if slug:
            return f"{entity_type}:{slug}"
        name_en, _ = self._names(section, payload)
        if name_en:
            return f"{entity_type}:name:{self._normalize_name(name_en)}"
        return f"{entity_type}:external:{external_id}"

    def _names(self, section, payload):
        name_en = (
            payload.get("name_en")
            or payload.get("canonical_name_en")
            or payload.get("canonical_name")
            or payload.get("full_name")
            or payload.get("title_en")
            or payload.get("event_en")
            or payload.get("claim_en")
            or payload.get("statement_en")
            or payload.get("note_en")
            or payload.get("issue_en")
            or payload.get("reason_en")
            or (payload.get("title") if section == "sources" else "")
            or ""
        )
        name_fa = (
            payload.get("name_fa")
            or payload.get("title_fa")
            or payload.get("event_fa")
            or payload.get("claim_fa")
            or payload.get("statement_fa")
            or payload.get("note_fa")
            or payload.get("issue_fa")
            or payload.get("reason_fa")
            or payload.get("persian_title")
            or ""
        )
        return str(name_en), str(name_fa)

    def _build_ingestion_audit(self, document):
        rules = {
            "concepts": (("name_en",), ("name_fa",), ("definition_en", "simple_definition_en", "academic_definition_en"), ("definition_fa", "simple_definition_fa", "academic_definition_fa")),
            "cognitive_distortions": (("name_en", "canonical_name_en"), ("name_fa",), ("definition_en",), ("definition_fa",)),
            "symptoms": (("name_en",), ("name_fa",), ("definition_en", "description_en"), ("definition_fa", "description_fa")),
            "disorders": (("name_en",), ("name_fa",), ("brief_description_en", "overview_en"), ("brief_description_fa", "overview_fa")),
            "therapy_families": (("name_en",), ("name_fa",), ("definition_en", "description_en"), ("definition_fa", "description_fa")),
            "therapy_classifications": (("name_en",), ("name_fa",), ("scheme_en", "description_en"), ("scheme_fa", "description_fa")),
            "therapies": (("name_en",), ("name_fa",), ("description_en", "academic_definition_en"), ("description_fa", "academic_definition_fa")),
            "techniques": (("name_en",), ("name_fa",), ("description_en", "academic_definition_en"), ("description_fa", "academic_definition_fa")),
            "psychologists": (("name_en", "canonical_name", "full_name"), ("name_fa",), (), ()),
            "theories": (("name_en",), ("name_fa",), ("core_proposition_en", "summary_en"), ("core_proposition_fa", "summary_fa")),
            "timeline_events": (("title_en", "event_en"), ("title_fa", "event_fa"), ("description_en", "event_en"), ("description_fa", "event_fa")),
            "claims": (("claim_en", "statement_en"), ("claim_fa", "statement_fa"), ("claim_en", "statement_en"), ("claim_fa", "statement_fa")),
        }

        def has_value(payload, keys):
            return any(payload.get(key) not in (None, "", [], {}) for key in keys)

        sections = {}
        for section, (name_en_keys, name_fa_keys, content_en_keys, content_fa_keys) in rules.items():
            rows = document.get(section) or []
            if not isinstance(rows, list):
                rows = []
            result = {
                "records": len(rows),
                "bilingual_name_records": 0,
                "missing_english_name": 0,
                "missing_persian_name": 0,
                "bilingual_content_records": 0,
                "content_pair_applicable": bool(content_en_keys or content_fa_keys),
            }
            for payload in rows:
                if not isinstance(payload, dict):
                    continue
                en_name = has_value(payload, name_en_keys)
                fa_name = has_value(payload, name_fa_keys)
                if en_name and fa_name:
                    result["bilingual_name_records"] += 1
                elif not en_name:
                    result["missing_english_name"] += 1
                elif not fa_name:
                    result["missing_persian_name"] += 1
                if content_en_keys or content_fa_keys:
                    if has_value(payload, content_en_keys) and has_value(payload, content_fa_keys):
                        result["bilingual_content_records"] += 1
            sections[section] = result

        list_counts = {
            section: len(document.get(section) or [])
            for section in LIST_SECTIONS
            if isinstance(document.get(section) or [], list)
        }
        return {
            "schema": "research-ingestion-audit-v1",
            "list_section_counts": list_counts,
            "list_record_total": sum(list_counts.values()),
            "bilingual_educational_sections": sections,
            "bibliographic_title_policy": "preserve_original_title_without_fabricated_translation",
            "staging_metadata_policy": "preserve_source_language_and_payload_losslessly_until_dedicated_domain_schema",
        }

    def _source_ids(self, payload):
        values = payload.get("source_ids")
        if values is None:
            values = payload.get("sources")
        if values is None:
            values = []
        if not isinstance(values, list):
            values = [values]
        return [str(value) for value in values if value not in (None, "")]

    def _promote_sources(self, ctx, report):
        for payload in ctx.document.get("sources") or []:
            if not isinstance(payload, dict):
                continue
            external_id = self._external_id("sources", payload, 0)
            source, created = self._upsert_source(payload)
            ctx.source_map[external_id] = source
            self._mark_promoted(ctx.dataset, "sources", external_id, source)
            report["sources_created" if created else "sources_matched"] += 1

    def _upsert_source(self, payload):
        doi = self._normalize_doi(payload.get("doi"))
        url = self._normalize_url(payload.get("url"))
        title = str(payload.get("title") or "").strip()
        year = self._safe_year(payload.get("publication_year") or payload.get("year"))
        source = None
        if doi:
            source = SourceReference.objects.filter(doi__iexact=doi).order_by("id").first()
        if source is None and url:
            source = SourceReference.objects.filter(url__iexact=url).order_by("id").first()
            if source is None:
                source = SourceReference.objects.filter(url__iexact=url + "/").order_by("id").first()
        if source is None and title:
            query = SourceReference.objects.filter(title__iexact=title)
            if year:
                query = query.filter(publication_year=year)
            source = query.order_by("id").first()

        created = source is None
        if source is None:
            source = SourceReference(title=title[:500] or "Untitled research source")

        organization = str(payload.get("organization") or "").strip()
        authors = payload.get("authors") if isinstance(payload.get("authors"), list) else []
        source_type = str(payload.get("source_type") or "")[:64]
        pmid = str(payload.get("pmid") or "").strip()[:64]
        verification = str(payload.get("verification_status") or payload.get("verification") or "")[:64]
        citation = self._citation(payload)

        self._fill_blank(source, "organization", organization[:255])
        self._fill_blank(source, "citation", citation)
        self._fill_blank(source, "url", url[:1000])
        if source.publication_year is None and year:
            source.publication_year = year
        self._fill_blank(source, "source_type", source_type)
        if not source.authors and authors:
            source.authors = authors
        self._fill_blank(source, "doi", doi[:255])
        self._fill_blank(source, "pmid", pmid)
        if SOURCE_VERIFICATION_RANK.get(verification, 1) > SOURCE_VERIFICATION_RANK.get(source.verification_status, 0):
            source.verification_status = verification
        metadata = dict(source.metadata or {})
        for key in ("venue", "journal", "volume", "issue", "pages", "volume_pages", "language", "evidence_level", "peer_reviewed"):
            if payload.get(key) not in (None, "") and key not in metadata:
                metadata[key] = payload.get(key)
        source.metadata = metadata
        source.save()
        return source, created

    def _citation(self, payload):
        parts = []
        authors = payload.get("authors")
        if isinstance(authors, list) and authors:
            parts.append("; ".join(str(value) for value in authors))
        year = payload.get("publication_year") or payload.get("year")
        if year:
            parts.append(str(year))
        venue = payload.get("journal") or payload.get("venue") or payload.get("organization")
        if venue:
            parts.append(str(venue))
        volume_pages = payload.get("volume_pages")
        if volume_pages:
            parts.append(str(volume_pages))
        else:
            volume = payload.get("volume")
            issue = payload.get("issue")
            pages = payload.get("pages")
            if volume:
                text = str(volume)
                if issue:
                    text += f"({issue})"
                if pages:
                    text += f":{pages}"
                parts.append(text)
        doi = self._normalize_doi(payload.get("doi"))
        pmid = payload.get("pmid")
        if doi:
            parts.append(f"doi:{doi}")
        if pmid:
            parts.append(f"PMID:{pmid}")
        return ". ".join(parts)

    def _promote_concepts(self, ctx, report):
        for section in ("concepts", "cognitive_distortions"):
            for payload in ctx.document.get(section) or []:
                if not isinstance(payload, dict):
                    continue
                external_id = self._external_id(section, payload, 0)
                slug = self._safe_slug(payload.get("slug"))
                name_en, name_fa = self._names(section, payload)
                if not slug:
                    slug = self._safe_slug(name_en)
                if not slug or not name_en:
                    report["concepts_skipped_missing_identity"] += 1
                    continue
                concept = Concept.objects.filter(slug=slug).first()
                created = concept is None
                subtype = Concept.Subtype.COGNITIVE_DISTORTION if section == "cognitive_distortions" else Concept.Subtype.GENERAL
                if concept is None:
                    simple_fa = self._localized(payload, "simple_definition", "definition", "detailed_explanation")
                    academic_fa = self._localized(payload, "academic_definition", "definition", "detailed_explanation")
                    concept = Concept.objects.create(
                        slug=slug,
                        name_en=name_en[:220],
                        name_fa=name_fa[:220],
                        simple_definition=simple_fa or name_fa or name_en,
                        academic_definition=academic_fa,
                        example=self._localized_list(payload.get("educational_examples")) or str(payload.get("example_fa") or ""),
                        counterexample=self._localized_list(payload.get("counterexamples")) or str(payload.get("counterexample_fa") or ""),
                        recognition_cues=self._localized_list(payload.get("recognition_cues")),
                        common_confusions=self._localized_list(payload.get("common_misconceptions")) or self._localized_list(payload.get("common_confusions")),
                        kind=self._concept_kind(payload, subtype),
                        domain=self._concept_domain(payload.get("domain")),
                        subtype=subtype,
                        is_active=True,
                    )
                else:
                    changed = []
                    if not concept.name_fa and name_fa:
                        concept.name_fa = name_fa[:220]
                        changed.append("name_fa")
                    if not concept.academic_definition:
                        value = self._localized(payload, "academic_definition", "definition", "detailed_explanation")
                        if value:
                            concept.academic_definition = value
                            changed.append("academic_definition")
                    if section == "cognitive_distortions" and concept.subtype != Concept.Subtype.COGNITIVE_DISTORTION:
                        concept.subtype = Concept.Subtype.COGNITIVE_DISTORTION
                        changed.append("subtype")
                    if changed:
                        concept.save(update_fields=tuple(changed) + ("updated_at",))
                self._concept_aliases(concept, payload)
                self._attach_sources(ConceptSource, "concept", concept, ctx, payload, report)
                ctx.map_entity(external_id, concept)
                self._mark_promoted(ctx.dataset, section, external_id, concept)
                report["concepts_created" if created else "concepts_matched"] += 1

    def _concept_aliases(self, concept, payload):
        rows = []
        for value in payload.get("aliases_en") or []:
            rows.append((value, ConceptAlias.Language.EN, ConceptAlias.AliasType.ALTERNATIVE))
        for value in payload.get("aliases_fa") or []:
            rows.append((value, ConceptAlias.Language.FA, ConceptAlias.AliasType.ALTERNATIVE))
        aliases = payload.get("aliases") or []
        if isinstance(aliases, list):
            rows.extend((value, ConceptAlias.Language.EN, ConceptAlias.AliasType.ALTERNATIVE) for value in aliases)
        for value in payload.get("abbreviations") or []:
            rows.append((value, ConceptAlias.Language.EN, ConceptAlias.AliasType.ABBREVIATION))
        for value, language, alias_type in rows:
            text = str(value).strip()[:220]
            if text and self._normalize_name(text) not in {self._normalize_name(concept.name_en), self._normalize_name(concept.name_fa)}:
                ConceptAlias.objects.get_or_create(
                    concept=concept,
                    text=text,
                    language=language,
                    defaults={"alias_type": alias_type},
                )

    def _promote_symptoms(self, ctx, report):
        for payload in ctx.document.get("symptoms") or []:
            if not isinstance(payload, dict):
                continue
            external_id = self._external_id("symptoms", payload, 0)
            slug = self._safe_slug(payload.get("slug"))
            name_en, name_fa = self._names("symptoms", payload)
            if not slug:
                slug = self._safe_slug(name_en)
            if not slug or not name_en:
                report["symptoms_skipped_missing_identity"] += 1
                continue
            symptom = Symptom.objects.filter(slug=slug).first()
            created = symptom is None
            if symptom is None:
                symptom = Symptom.objects.create(
                    slug=slug,
                    name_en=name_en[:220],
                    name_fa=name_fa[:220],
                    description=self._localized(payload, "description", "definition"),
                    domain=self._symptom_domain(payload),
                )
            else:
                changed = []
                if not symptom.name_fa and name_fa:
                    symptom.name_fa = name_fa[:220]
                    changed.append("name_fa")
                if not symptom.description:
                    description = self._localized(payload, "description", "definition")
                    if description:
                        symptom.description = description
                        changed.append("description")
                if changed:
                    symptom.save(update_fields=tuple(changed) + ("updated_at",))
            ctx.map_entity(external_id, symptom)
            self._mark_promoted(ctx.dataset, "symptoms", external_id, symptom)
            report["symptoms_created" if created else "symptoms_matched"] += 1

    def _map_disorders(self, ctx, report):
        for payload in ctx.document.get("disorders") or []:
            if not isinstance(payload, dict):
                continue
            external_id = self._external_id("disorders", payload, 0)
            slug = self._safe_slug(payload.get("slug"))
            name_en, _ = self._names("disorders", payload)
            disorder = Disorder.objects.filter(slug=slug).first() if slug else None
            if disorder is None and name_en:
                disorder = self._find_by_normalized_name(Disorder, name_en)
            if disorder is None:
                report["disorders_staged_not_promoted"] += 1
                continue
            self._attach_sources(DisorderSource, "disorder", disorder, ctx, payload, report)
            ctx.map_entity(external_id, disorder)
            self._mark_promoted(ctx.dataset, "disorders", external_id, disorder)
            report["disorders_matched"] += 1

    def _promote_families(self, ctx, report, create_new):
        for payload in ctx.document.get("therapy_families") or []:
            if not isinstance(payload, dict):
                continue
            external_id = self._external_id("therapy_families", payload, 0)
            slug = self._safe_slug(payload.get("slug"))
            name_en, name_fa = self._names("therapy_families", payload)
            family = TherapyFamily.objects.filter(slug=slug).first() if slug else None
            if family is None and name_en:
                family = self._find_family_by_name(name_en)
            created = False
            if family is None and create_new and name_en:
                slug = slug or self._family_slug(name_en)
                if slug:
                    family, created = TherapyFamily.objects.get_or_create(
                        slug=slug,
                        defaults={
                            "name_en": name_en[:220],
                            "name_fa": name_fa[:220],
                            "description": self._localized(payload, "description", "definition"),
                            "is_active": True,
                            "seed_managed": False,
                        },
                    )
            if family is None:
                report["therapy_families_staged_not_promoted"] += 1
                continue
            ctx.map_entity(external_id, family)
            self._mark_promoted(ctx.dataset, "therapy_families", external_id, family)
            report["therapy_families_created" if created else "therapy_families_matched"] += 1

    def _promote_classifications(self, ctx, report, create_new):
        for payload in ctx.document.get("therapy_classifications") or []:
            if not isinstance(payload, dict):
                continue
            external_id = self._external_id("therapy_classifications", payload, 0)
            slug = self._safe_slug(payload.get("slug"))
            name_en, name_fa = self._names("therapy_classifications", payload)
            classification = TherapyClassification.objects.filter(slug=slug).first() if slug else None
            if classification is None and name_en:
                classification = self._find_by_normalized_name(TherapyClassification, name_en)
            created = False
            if classification is None and create_new and name_en:
                slug = slug or self._safe_slug(name_en)
                if slug:
                    classification, created = TherapyClassification.objects.get_or_create(
                        slug=slug,
                        defaults={
                            "name_en": name_en[:220],
                            "name_fa": name_fa[:220],
                            "kind": self._classification_kind(slug, name_en),
                            "description": self._localized(payload, "description", "scheme"),
                            "is_active": True,
                            "seed_managed": False,
                        },
                    )
            if classification is None:
                report["therapy_classifications_staged_not_promoted"] += 1
                continue
            ctx.map_entity(external_id, classification)
            self._mark_promoted(ctx.dataset, "therapy_classifications", external_id, classification)
            report["therapy_classifications_created" if created else "therapy_classifications_matched"] += 1

    def _promote_therapies(self, ctx, report, create_new):
        for payload in ctx.document.get("therapies") or []:
            if not isinstance(payload, dict):
                continue
            external_id = self._external_id("therapies", payload, 0)
            slug = self._safe_slug(payload.get("slug"))
            name_en, name_fa = self._names("therapies", payload)
            therapy = Therapy.objects.filter(slug=slug).first() if slug else None
            if therapy is None and name_en:
                therapy = self._find_by_normalized_name(Therapy, self._strip_generic_suffix(name_en))
            created = False
            if therapy is None and create_new and slug and name_en:
                family_id = payload.get("primary_family_id") or payload.get("family_id")
                family = ctx.entity_map.get(str(family_id)) if family_id else None
                if not isinstance(family, TherapyFamily):
                    report["therapies_staged_missing_family"] += 1
                    continue
                therapy = Therapy.objects.create(
                    family=family,
                    slug=slug,
                    name_en=name_en[:255],
                    name_fa=name_fa[:255],
                    summary=self._localized(payload, "summary", "description", "academic_definition"),
                    academic_definition=self._localized(payload, "academic_definition", "description"),
                    historical_context=self._localized_value(payload.get("historical_context")),
                    core_principles=self._localized_list(payload.get("core_principles")),
                    typical_structure=self._localized_value(payload.get("typical_structure") or payload.get("typical_format")),
                    appropriate_contexts=self._localized_list(payload.get("appropriate_educational_clinical_contexts")),
                    limitations=self._localized_list(payload.get("limitations")),
                    safety_notes=self._localized_list(payload.get("safety_considerations")),
                    evidence_note=self._localized_value(payload.get("evidence_overview")),
                    review_status=self._scientific_review_status(payload, ctx),
                    is_active=True,
                    seed_managed=False,
                )
                created = True
            if therapy is None:
                report["therapies_staged_not_promoted"] += 1
                continue
            self._therapy_aliases(therapy, payload)
            self._attach_sources(TherapySource, "therapy", therapy, ctx, payload, report)
            for classification_id in payload.get("classification_ids") or []:
                classification = ctx.entity_map.get(str(classification_id))
                if isinstance(classification, TherapyClassification):
                    TherapyClassificationLink.objects.get_or_create(
                        therapy=therapy,
                        classification=classification,
                        defaults={"is_active": True},
                    )
            ctx.map_entity(external_id, therapy)
            self._mark_promoted(ctx.dataset, "therapies", external_id, therapy)
            report["therapies_created" if created else "therapies_matched"] += 1

    def _therapy_aliases(self, therapy, payload):
        rows = []
        aliases = payload.get("aliases") or []
        if isinstance(aliases, list):
            rows.extend((value, TherapyAlias.AliasType.ALTERNATIVE) for value in aliases)
        for value in payload.get("abbreviations") or []:
            rows.append((value, TherapyAlias.AliasType.ABBREVIATION))
        for value, alias_type in rows:
            text = str(value).strip()[:255]
            if text and self._normalize_name(text) != self._normalize_name(therapy.name_en):
                TherapyAlias.objects.get_or_create(
                    therapy=therapy,
                    text=text,
                    language=TherapyAlias.Language.EN,
                    defaults={"alias_type": alias_type},
                )

    def _promote_techniques(self, ctx, report, create_new):
        for payload in ctx.document.get("techniques") or []:
            if not isinstance(payload, dict):
                continue
            external_id = self._external_id("techniques", payload, 0)
            slug = self._safe_slug(payload.get("slug"))
            name_en, name_fa = self._names("techniques", payload)
            technique = Technique.objects.filter(slug=slug).first() if slug else None
            if technique is None and name_en:
                technique = self._find_by_normalized_name(Technique, name_en)
            created = False
            if technique is None and create_new and slug and name_en:
                technique = Technique.objects.create(
                    slug=slug,
                    name_en=name_en[:255],
                    name_fa=name_fa[:255],
                    summary=self._localized(payload, "summary", "description", "academic_definition"),
                    academic_definition=self._localized(payload, "academic_definition", "description"),
                    application_notes=self._localized_value(payload.get("application_overview") or payload.get("purpose")),
                    limitations=self._localized_list(payload.get("limitations")),
                    safety_notes=self._localized_list(payload.get("safety_considerations")),
                    review_status=self._scientific_review_status(payload, ctx),
                    is_active=True,
                    seed_managed=False,
                )
                created = True
            if technique is None:
                report["techniques_staged_not_promoted"] += 1
                continue
            self._technique_aliases(technique, payload)
            self._attach_sources(TechniqueSource, "technique", technique, ctx, payload, report)
            ctx.map_entity(external_id, technique)
            self._mark_promoted(ctx.dataset, "techniques", external_id, technique)
            report["techniques_created" if created else "techniques_matched"] += 1

    def _technique_aliases(self, technique, payload):
        rows = []
        aliases = payload.get("aliases") or []
        if isinstance(aliases, list):
            rows.extend((value, TechniqueAlias.AliasType.ALTERNATIVE) for value in aliases)
        for value in payload.get("abbreviations") or []:
            rows.append((value, TechniqueAlias.AliasType.ABBREVIATION))
        for value, alias_type in rows:
            text = str(value).strip()[:255]
            if text and self._normalize_name(text) != self._normalize_name(technique.name_en):
                TechniqueAlias.objects.get_or_create(
                    technique=technique,
                    text=text,
                    language=TechniqueAlias.Language.EN,
                    defaults={"alias_type": alias_type},
                )

    def _promote_supported_relationships(self, ctx, report):
        for payload in ctx.document.get("relationships") or []:
            if not isinstance(payload, dict):
                continue
            external_id = self._external_id("relationships", payload, 0)
            source_id = str(payload.get("source_id") or "")
            target_id = str(payload.get("target_id") or "")
            relation_type = str(payload.get("relation_type") or "")
            source = ctx.entity_map.get(source_id)
            target = ctx.entity_map.get(target_id)
            if source is None or target is None:
                report["relations_staged_unmapped_endpoint"] += 1
                continue
            explanation = str(payload.get("explanation_fa") or payload.get("explanation_en") or "")
            created_relation = None
            source_link_model = None

            if isinstance(source, Therapy) and isinstance(target, Technique) and relation_type == "uses":
                created_relation, _ = TherapyTechnique.objects.update_or_create(
                    therapy=source,
                    technique=target,
                    defaults={
                        "role": TherapyTechnique.Role.COMMON,
                        "explanation": explanation,
                        "review_status": ScientificReviewStatus.SOURCE_CHECKED,
                        "is_active": True,
                    },
                )
                source_link_model = TherapyTechniqueSource
            elif isinstance(source, Therapy) and isinstance(target, Disorder) and relation_type == "clinical_evidence_for":
                clinical_role = str(payload.get("clinical_role") or TherapyDisorder.ClinicalRole.UNSPECIFIED)
                evidence_basis = str(payload.get("evidence_basis") or TherapyDisorder.EvidenceBasis.NOT_ASSESSED)
                valid_roles = {value for value, _ in TherapyDisorder.ClinicalRole.choices}
                valid_evidence = {value for value, _ in TherapyDisorder.EvidenceBasis.choices}
                created_relation, _ = TherapyDisorder.objects.update_or_create(
                    therapy=source,
                    disorder=target,
                    defaults={
                        "clinical_role": clinical_role if clinical_role in valid_roles else TherapyDisorder.ClinicalRole.UNSPECIFIED,
                        "evidence_basis": evidence_basis if evidence_basis in valid_evidence else TherapyDisorder.EvidenceBasis.NOT_ASSESSED,
                        "explanation": explanation,
                        "evidence_note": str(payload.get("notes") or ""),
                        "review_status": ScientificReviewStatus.SOURCE_CHECKED,
                        "is_active": True,
                    },
                )
                source_link_model = TherapyDisorderSource
            elif isinstance(source, Technique) and isinstance(target, Concept) and relation_type == "targets_or_uses_process":
                created_relation, _ = TechniqueConcept.objects.update_or_create(
                    technique=source,
                    concept=target,
                    relationship_type=TechniqueConcept.Kind.TARGETS,
                    defaults={
                        "explanation": explanation,
                        "review_status": ScientificReviewStatus.SOURCE_CHECKED,
                        "is_active": True,
                    },
                )
                source_link_model = TechniqueConceptSource
            elif isinstance(source, Therapy) and isinstance(target, Concept) and relation_type in {"targets_or_organizes_around", "relies_on"}:
                kind = TherapyConcept.Kind.TARGETS if relation_type == "targets_or_organizes_around" else TherapyConcept.Kind.MECHANISM
                created_relation, _ = TherapyConcept.objects.update_or_create(
                    therapy=source,
                    concept=target,
                    relationship_type=kind,
                    defaults={
                        "explanation": explanation,
                        "review_status": ScientificReviewStatus.SOURCE_CHECKED,
                        "is_active": True,
                    },
                )
                source_link_model = TherapyConceptSource
            elif isinstance(source, Concept) and isinstance(target, Therapy) and source_id.startswith("cognitive-distortion:") and relation_type == "educational_construct_used_in":
                created_relation, _ = TherapyConcept.objects.update_or_create(
                    therapy=target,
                    concept=source,
                    relationship_type=TherapyConcept.Kind.USES,
                    defaults={
                        "explanation": explanation,
                        "review_status": ScientificReviewStatus.SOURCE_CHECKED,
                        "is_active": True,
                    },
                )
                source_link_model = TherapyConceptSource
            elif isinstance(source, Concept) and isinstance(target, Technique) and source_id.startswith("cognitive-distortion:") and relation_type == "can_be_examined_with":
                created_relation, _ = TechniqueConcept.objects.update_or_create(
                    technique=target,
                    concept=source,
                    relationship_type=TechniqueConcept.Kind.ADDRESSES,
                    defaults={
                        "explanation": explanation,
                        "review_status": ScientificReviewStatus.SOURCE_CHECKED,
                        "is_active": True,
                    },
                )
                source_link_model = TechniqueConceptSource
            elif isinstance(source, Concept) and isinstance(target, Concept):
                mapped = self._concept_relation_mapping(source, target, relation_type)
                if mapped:
                    rel_source, rel_target, kind = mapped
                    created_relation, _ = ConceptRelationship.objects.update_or_create(
                        source_concept=rel_source,
                        target_concept=rel_target,
                        relationship_type=kind,
                        defaults={"explanation": explanation},
                    )
                    source_link_model = ConceptRelationshipSource
            elif isinstance(source, Concept) and isinstance(target, Symptom):
                kind = None
                if relation_type in {"can_manifest_as", "clinical_manifestation"}:
                    kind = ConceptSymptom.Kind.MANIFESTATION
                elif relation_type == "relevant_to":
                    kind = ConceptSymptom.Kind.ASSOCIATED
                if kind:
                    created_relation, _ = ConceptSymptom.objects.update_or_create(
                        concept=source,
                        symptom=target,
                        relationship_type=kind,
                        defaults={"explanation": explanation},
                    )
                    source_link_model = ConceptSymptomSource

            if created_relation is None:
                report["relations_staged_unsupported_semantics"] += 1
                continue

            attached = 0
            for source_ref in self._relation_source_objects(ctx, payload):
                source_link_model.objects.get_or_create(
                    relationship=created_relation,
                    source=source_ref,
                    defaults={"note": str(payload.get("evidence_status") or "")},
                )
                attached += 1
            if attached == 0:
                # Do not leave a newly imported scientific relation masquerading as sourced.
                # The complete dataset claims source-backed relations, so zero resolved sources
                # indicates an import mapping problem. Remove only if it did not pre-exist with sources.
                if not created_relation.source_links.exists():
                    created_relation.delete()
                    report["relations_rejected_without_resolved_source"] += 1
                    continue
            self._mark_promoted(ctx.dataset, "relationships", external_id, created_relation)
            report["relations_promoted"] += 1

    def _concept_relation_mapping(self, source, target, relation_type):
        if relation_type == "influences":
            return source, target, ConceptRelationship.Kind.INFLUENCES
        if relation_type in {"functionally_opposed_process", "distinct_from", "distinct_mechanism_from"}:
            return source, target, ConceptRelationship.Kind.CONTRASTS
        if relation_type in {"has_subtype", "broader_than"}:
            return target, source, ConceptRelationship.Kind.SUBTYPE_OF
        if relation_type in {"includes_component", "includes_broad_dimension"}:
            return target, source, ConceptRelationship.Kind.PART_OF
        return None

    def _relation_source_objects(self, ctx, payload):
        seen = set()
        rows = []
        for external_id in self._source_ids(payload):
            source = ctx.source_map.get(str(external_id))
            if source is not None and source.pk not in seen:
                seen.add(source.pk)
                rows.append(source)
        return rows

    def _attach_sources(self, link_model, object_field, obj, ctx, payload, report):
        attached = 0
        for external_id in self._source_ids(payload):
            source = ctx.source_map.get(str(external_id))
            if source is None:
                report["source_links_unresolved"] += 1
                continue
            link_model.objects.get_or_create(**{object_field: obj, "source": source})
            attached += 1
        report["source_links_attached"] += attached

    def _mark_promoted(self, dataset, section, external_id, obj):
        ResearchRecord.objects.filter(
            dataset=dataset,
            section=section,
            external_id=str(external_id)[:300],
        ).update(promoted_model=obj._meta.label_lower, promoted_pk=obj.pk)

    def _scientific_review_status(self, payload, ctx):
        review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
        status = str(review.get("status") or "")
        if ctx.is_complete and status == "source_checked" and self._source_ids(payload):
            return ScientificReviewStatus.SOURCE_CHECKED
        return ScientificReviewStatus.UNREVIEWED

    def _concept_kind(self, payload, subtype):
        if subtype == Concept.Subtype.COGNITIVE_DISTORTION:
            return Concept.Kind.COGNITIVE
        domain = str(payload.get("domain") or "").lower()
        if "behavior" in domain or "learning" in domain:
            return Concept.Kind.BEHAVIORAL
        if "emotion" in domain:
            return Concept.Kind.EMOTIONAL
        if "interpersonal" in domain or "social" in domain:
            return Concept.Kind.INTERPERSONAL
        if "assessment" in domain:
            return Concept.Kind.ASSESSMENT
        if "therapy" in domain or "treatment" in domain:
            return Concept.Kind.TREATMENT
        if "clinical" in domain or "pathology" in domain:
            return Concept.Kind.CLINICAL
        if "cognitive" in domain or "neuropsych" in domain:
            return Concept.Kind.COGNITIVE
        return Concept.Kind.GENERAL

    def _concept_domain(self, value):
        key = str(value or "").strip().lower()
        return CONCEPT_DOMAIN_MAP.get(key, Concept.Domain.GENERAL)

    def _symptom_domain(self, payload):
        category_values = payload.get("categories") if isinstance(payload.get("categories"), list) else []
        candidates = [payload.get("symptom_domain"), payload.get("domain"), *category_values]
        for value in candidates:
            key = str(value or "").strip().lower()
            if key in SYMPTOM_DOMAIN_MAP:
                return SYMPTOM_DOMAIN_MAP[key]
        return Symptom.Domain.OTHER

    def _classification_kind(self, slug, name):
        text = f"{slug} {name}".lower()
        if any(word in text for word in ("trauma", "cognitive", "behavior", "emotion", "mindfulness", "exposure", "skills")):
            return TherapyClassification.Kind.FOCUS
        if any(word in text for word in ("structured", "process", "method")):
            return TherapyClassification.Kind.METHOD
        if any(word in text for word in ("group", "individual", "internet", "digital", "delivery")):
            return TherapyClassification.Kind.DELIVERY
        if any(word in text for word in ("child", "adolescent", "adult", "couple", "family")):
            return TherapyClassification.Kind.POPULATION
        return TherapyClassification.Kind.OTHER

    def _find_by_normalized_name(self, model, name):
        target = self._normalize_name(name)
        if not target:
            return None
        for obj in model.objects.only("id", "name_en"):
            if self._normalize_name(obj.name_en) == target:
                return obj
        return None

    def _find_family_by_name(self, name):
        target = self._family_name_key(name)
        for family in TherapyFamily.objects.only("id", "name_en"):
            if self._family_name_key(family.name_en) == target:
                return family
        return None

    def _family_name_key(self, value):
        text = self._normalize_name(value)
        for token in ("therapy family", "therapies", "therapy", "family", "approaches", "approach"):
            text = text.replace(token, " ")
        return " ".join(text.split())

    def _family_slug(self, name):
        key = self._family_name_key(name)
        return self._safe_slug(key)

    def _strip_generic_suffix(self, value):
        return re.sub(r"\s*\(generic\)\s*$", "", str(value or ""), flags=re.IGNORECASE).strip()

    def _localized(self, payload, *bases):
        for base in bases:
            direct = payload.get(f"{base}_fa")
            if direct:
                return self._localized_value(direct)
            value = payload.get(base)
            if value:
                text = self._localized_value(value)
                if text:
                    return text
        return ""

    def _localized_value(self, value):
        if value in (None, ""):
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("fa", "text_fa", "description_fa", "en", "text_en", "description_en"):
                if value.get(key):
                    return self._localized_value(value.get(key))
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        if isinstance(value, list):
            return self._localized_list(value)
        return str(value)

    def _localized_list(self, values):
        if values in (None, ""):
            return ""
        if not isinstance(values, list):
            return self._localized_value(values)
        rows = []
        for value in values:
            text = self._localized_value(value)
            if text:
                rows.append(text)
        return "\n".join(rows)

    def _fill_blank(self, obj, field, value):
        if value not in (None, "") and getattr(obj, field) in (None, "", [], {}):
            setattr(obj, field, value)

    def _safe_slug(self, value):
        if value in (None, ""):
            return ""
        raw = str(value).strip().lower().replace("_", "-")
        candidate = slugify(raw)
        return candidate or re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")

    def _normalize_name(self, value):
        text = str(value or "").lower().replace("–", "-").replace("—", "-")
        text = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", text)
        return " ".join(text.split())

    def _normalize_doi(self, value):
        text = str(value or "").strip().lower()
        text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
        return text.strip()

    def _normalize_url(self, value):
        return str(value or "").strip().rstrip("/")

    def _safe_year(self, value):
        try:
            year = int(value)
        except (TypeError, ValueError):
            return None
        return year if 1000 <= year <= 9999 else None
