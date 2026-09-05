import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date

from django.db import IntegrityError
from django.utils.text import slugify

from .models import (
    Concept,
    Psychologist,
    PsychologistAlias,
    PsychologistAttributionType,
    PsychologistConcept,
    PsychologistConceptSource,
    PsychologistPsychologist,
    PsychologistPsychologistSource,
    PsychologistSource,
    PsychologistTheory,
    PsychologistTheorySource,
    PsychologistTherapy,
    PsychologistTherapySource,
    ResearchRecord,
    ScientificReviewStatus,
    SourceReference,
    Technique,
    Theory,
    TheoryAlias,
    TheoryConcept,
    TheoryConceptSource,
    TheoryRelationType,
    TheorySource,
    TheoryTechnique,
    TheoryTechniqueSource,
    TheoryTheory,
    TheoryTheorySource,
    TheoryTherapy,
    TheoryTherapySource,
    Therapy,
    TimelineConcept,
    TimelineConceptSource,
    TimelineEvent,
    TimelineEventSource,
    TimelineLinkRole,
    TimelinePsychologist,
    TimelinePsychologistSource,
    TimelineTheory,
    TimelineTheorySource,
    TimelineTherapy,
    TimelineTherapySource,
    TimelineTechnique,
    TimelineTechniqueSource,
)


FUTURE_SECTIONS = ("psychologists", "theories", "timeline_events")

PSYCHOLOGIST_RELATION_TYPES = {value for value, _label in PsychologistAttributionType.choices}
THEORY_RELATION_TYPES = {value for value, _label in TheoryRelationType.choices}


def _text(value):
    return str(value or "").strip()


def _normalize_identity(value):
    value = unicodedata.normalize("NFKC", _text(value)).casefold()
    return "".join(character for character in value if character.isalnum())


def _core_identity(value):
    """Normalize harmless initials/possessives without doing fuzzy matching."""
    value = unicodedata.normalize("NFKC", _text(value)).casefold()
    value = re.sub(r"\b([a-z]+)[’']s\b", r"\1", value)
    tokens = re.findall(r"[^\W_]+", value, flags=re.UNICODE)
    tokens = [
        token
        for token in tokens
        if not (len(token) == 1 and token.isascii() and token.isalpha())
    ]
    return "".join(tokens)


def _list(value):
    return list(value) if isinstance(value, list) else []


def _unique(values):
    result = []
    seen = set()
    for value in values:
        marker = str(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def _review_rank(record):
    if record.review_status == ScientificReviewStatus.REVIEWED:
        return 3
    if record.review_status == ScientificReviewStatus.SOURCE_CHECKED:
        return 2
    return 1 if record.verification_status else 0


def _record_sort_key(record):
    return (-_review_rank(record), -len(record.source_ids or []), record.external_id)


def _safe_year(value):
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= 9999 else None


def _safe_date(value):
    value = _text(value)
    if not value or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _first(records, *keys):
    for record in records:
        for key in keys:
            value = record.payload.get(key)
            if value not in (None, "", [], {}):
                return value
    return None


def _first_text(records, *keys):
    value = _first(records, *keys)
    return _text(value)


def _merged_list(records, *keys):
    values = []
    for record in records:
        for key in keys:
            value = record.payload.get(key)
            if isinstance(value, list):
                values.extend(value)
    return _unique(values)


def _preferred_slug(records, prefix):
    ordered = sorted(records, key=_record_sort_key)
    for record in ordered:
        explicit = slugify(_text(record.payload.get("slug")))
        if explicit:
            return explicit[:220]
    for record in ordered:
        external = _text(record.external_id)
        if ":" in external:
            namespace, suffix = external.split(":", 1)
            if namespace in {prefix, "event"}:
                candidate = slugify(suffix)
                if candidate:
                    return candidate[:220]
    for record in ordered:
        external = _text(record.external_id)
        candidate = slugify(external.replace("_", "-"))
        if candidate:
            return candidate[:220]
    candidate = slugify(_text(ordered[0].name_en))
    return candidate[:220]


def _explicit_aliases(record):
    aliases = []
    for item in _list(record.payload.get("aliases")):
        if isinstance(item, str):
            text = item.strip()
            if text:
                aliases.append((text, "other", "alternative"))
        elif isinstance(item, dict):
            text = _text(item.get("text") or item.get("name") or item.get("alias"))
            if not text:
                continue
            language = _text(item.get("language") or item.get("lang") or "other").lower()
            if language not in {"fa", "en", "other"}:
                language = "other"
            alias_type = _text(item.get("alias_type") or item.get("type") or "alternative").lower()
            aliases.append((text, language, alias_type))
    return aliases


class ResearchStagingPromoter:
    """Conservatively project source-backed future-domain staging records.

    The promoter never fabricates missing sources, dates, aliases, or relation
    semantics. Exact-name identity groups are merged; fuzzy person/theory
    matching is intentionally not attempted. Unsupported or unsourced records
    remain in ResearchRecord with null promotion pointers.
    """

    def __init__(self):
        self.report = Counter()
        self._source_map = self._build_source_map()
        self._endpoint_map = {}
        self._endpoint_ambiguities = set()

    def promote(self):
        self._repair_staging_canonical_keys()
        self._promote_psychologists()
        self._promote_theories()
        self._refresh_endpoint_map()
        self._promote_timeline_events()
        self._refresh_endpoint_map()
        self._promote_explicit_relationships()
        self._promote_timeline_links()
        return self.report

    def _build_source_map(self):
        source_rows = list(
            ResearchRecord.objects.filter(
                section="sources",
                promoted_model="atlas.sourcereference",
                promoted_pk__isnull=False,
            ).values_list("external_id", "promoted_pk")
        )
        source_objects = SourceReference.objects.in_bulk({pk for _external_id, pk in source_rows})
        result = {}
        for external_id, pk in source_rows:
            source = source_objects.get(pk)
            if source is not None:
                result[str(external_id)] = source
        return result

    def _repair_staging_canonical_keys(self):
        repairs = (
            ("theories", "theorie:", "theory:"),
            ("timeline_events", "timeline_event:", "timeline-event:"),
        )
        for section, old_prefix, new_prefix in repairs:
            for record in ResearchRecord.objects.filter(section=section, canonical_key__startswith=old_prefix):
                record.canonical_key = new_prefix + record.canonical_key[len(old_prefix):]
                record.save(update_fields=["canonical_key", "updated_at"])
                self.report["staging_canonical_keys_repaired"] += 1

    def _source_ids_for_record(self, record):
        source_ids = [str(value) for value in record.source_ids or [] if value not in (None, "")]
        if record.section == "psychologists":
            for key in ("key_works", "major_publications"):
                source_ids.extend(str(value) for value in _list(record.payload.get(key)) if value not in (None, ""))
        return _unique(source_ids)

    def _resolved_sources(self, record):
        source_ids = self._source_ids_for_record(record)
        if not source_ids:
            return []
        sources = [self._source_map.get(source_id) for source_id in source_ids]
        if any(source is None for source in sources):
            return []
        return sources

    def _is_source_backed(self, record):
        return bool(self._resolved_sources(record))

    def _identity_groups(self, section, prefix):
        exact_groups = defaultdict(list)
        for record in ResearchRecord.objects.filter(section=section).order_by("dataset_id", "id"):
            key = _normalize_identity(record.name_en)
            if not key:
                self.report[f"{section}_skipped_missing_identity"] += 1
                continue
            exact_groups[key].append(record)

        merged = defaultdict(list)
        for exact_key, records in exact_groups.items():
            slug = _preferred_slug(records, prefix)
            core_key = _core_identity(records[0].name_en)
            merge_key = (slug, core_key) if slug and core_key else (slug, exact_key)
            merged[merge_key].extend(records)

        for records in merged.values():
            exact_keys = {_normalize_identity(record.name_en) for record in records}
            if len(exact_keys) > 1:
                self.report[f"{section}_identity_merges"] += len(exact_keys) - 1
        return merged

    def _eligible_records(self, records):
        return [record for record in records if self._is_source_backed(record)]

    def _find_or_create_by_slug(self, model, slug, identity_key, **defaults):
        existing = model.objects.filter(slug=slug).first()
        if existing is not None:
            existing_name = existing.name_en if hasattr(existing, "name_en") else existing.title_en
            existing_identity = _core_identity(existing_name) or _normalize_identity(existing_name)
            if existing_identity and existing_identity != identity_key:
                self.report[f"{model._meta.model_name}_slug_conflict"] += 1
                return None, False
            return existing, False
        try:
            return model.objects.create(slug=slug, **defaults), True
        except IntegrityError:
            self.report[f"{model._meta.model_name}_create_conflict"] += 1
            return None, False

    def _mark_records(self, records, obj, canonical_key):
        model_label = obj._meta.label_lower
        for record in records:
            updates = []
            if record.promoted_model != model_label:
                record.promoted_model = model_label
                updates.append("promoted_model")
            if record.promoted_pk != obj.pk:
                record.promoted_pk = obj.pk
                updates.append("promoted_pk")
            if record.canonical_key != canonical_key:
                record.canonical_key = canonical_key[:400]
                updates.append("canonical_key")
            if record.slug != obj.slug:
                record.slug = obj.slug[:220]
                updates.append("slug")
            if updates:
                updates.append("updated_at")
                record.save(update_fields=updates)

    def _entity_review_status(self, records):
        statuses = {record.review_status for record in records}
        if ScientificReviewStatus.REVIEWED in statuses:
            return ScientificReviewStatus.REVIEWED
        if ScientificReviewStatus.SOURCE_CHECKED in statuses:
            return ScientificReviewStatus.SOURCE_CHECKED
        return ScientificReviewStatus.UNREVIEWED

    def _promote_psychologists(self):
        existing_by_name = {
            (_core_identity(obj.name_en) or _normalize_identity(obj.name_en)): obj
            for obj in Psychologist.objects.all()
            if _normalize_identity(obj.name_en)
        }
        for _group_key, records in self._identity_groups("psychologists", "psychologist").items():
            eligible = self._eligible_records(records)
            if not eligible:
                self.report["psychologists_skipped_no_resolved_source"] += 1
                continue
            ordered = sorted(eligible, key=_record_sort_key)
            source_checked = [
                record for record in ordered
                if record.review_status in {ScientificReviewStatus.SOURCE_CHECKED, ScientificReviewStatus.REVIEWED}
            ]
            canonical_records = source_checked or ordered
            slug = _preferred_slug(canonical_records, "psychologist")
            if not slug:
                self.report["psychologists_skipped_missing_slug"] += 1
                continue
            name_en = _text(canonical_records[0].name_en)
            name_fa = next((_text(record.name_fa) for record in canonical_records if _text(record.name_fa)), "")
            identity_key = _core_identity(name_en) or _normalize_identity(name_en)
            obj = existing_by_name.get(identity_key)
            created = False
            if obj is None:
                obj, created = self._find_or_create_by_slug(
                    Psychologist,
                    slug,
                    identity_key,
                    name_en=name_en,
                    name_fa=name_fa,
                    review_status=self._entity_review_status(eligible),
                    seed_managed=False,
                    is_active=True,
                )
                if obj is None:
                    continue
                existing_by_name[identity_key] = obj

            changed = False
            if not obj.name_fa and name_fa:
                obj.name_fa = name_fa
                changed = True
            if source_checked:
                preferred = sorted(source_checked, key=_record_sort_key)
                nationality = _first_text(preferred, "nationality_background")
                birth_year = _safe_year(_first(preferred, "birth_year"))
                death_year = _safe_year(_first(preferred, "death_year"))
                academic_disciplines = _merged_list(preferred, "academic_disciplines")
                contributions = _merged_list(preferred, "major_contributions")
                affiliations = _merged_list(preferred, "institutions")
                historical_context = _first_text(preferred, "historical_context")
                for field, value in (
                    ("nationality_en", nationality),
                    ("birth_year", birth_year),
                    ("death_year", death_year),
                    ("historical_context_en", historical_context),
                ):
                    if value not in (None, "") and getattr(obj, field) in (None, ""):
                        setattr(obj, field, value)
                        changed = True
                for field, value in (
                    ("academic_disciplines", academic_disciplines),
                    ("contributions_en", contributions),
                    ("affiliations", affiliations),
                ):
                    if value and not getattr(obj, field):
                        setattr(obj, field, value)
                        changed = True
            desired_review = self._entity_review_status(eligible)
            if obj.review_status != desired_review and desired_review != ScientificReviewStatus.UNREVIEWED:
                obj.review_status = desired_review
                changed = True
            if not obj.is_active:
                obj.is_active = True
                changed = True
            if changed:
                obj.full_clean()
                obj.save()

            self._create_person_aliases(obj, records)
            self._link_psychologist_sources(obj, eligible)
            self._mark_records(records, obj, f"psychologist:{obj.slug}")
            self.report["psychologists_created" if created else "psychologists_matched"] += 1

    def _create_person_aliases(self, obj, records):
        candidates = []
        for record in records:
            if record.name_en and _normalize_identity(record.name_en) != _normalize_identity(obj.name_en):
                candidates.append((record.name_en, PsychologistAlias.Language.EN, PsychologistAlias.AliasType.ALTERNATIVE))
            if record.name_fa and record.name_fa != obj.name_fa:
                candidates.append((record.name_fa, PsychologistAlias.Language.FA, PsychologistAlias.AliasType.ALTERNATIVE))
            for text, language, alias_type in _explicit_aliases(record):
                if language == "fa":
                    lang = PsychologistAlias.Language.FA
                elif language == "en":
                    lang = PsychologistAlias.Language.EN
                else:
                    lang = PsychologistAlias.Language.OTHER
                if alias_type == "initials":
                    kind = PsychologistAlias.AliasType.INITIALS
                elif alias_type == "transliteration":
                    kind = PsychologistAlias.AliasType.TRANSLITERATION
                elif alias_type == "historical":
                    kind = PsychologistAlias.AliasType.HISTORICAL
                else:
                    kind = PsychologistAlias.AliasType.ALTERNATIVE
                candidates.append((text, lang, kind))
        for text, language, alias_type in _unique(candidates):
            if not _text(text):
                continue
            _alias, created = PsychologistAlias.objects.get_or_create(
                psychologist=obj,
                text=_text(text)[:255],
                language=language,
                defaults={"alias_type": alias_type},
            )
            if created:
                self.report["psychologist_aliases_created"] += 1

    def _link_psychologist_sources(self, obj, records):
        for record in records:
            primary_ids = set(
                str(value)
                for key in ("key_works", "major_publications")
                for value in _list(record.payload.get(key))
                if value not in (None, "")
            )
            for source_id in self._source_ids_for_record(record):
                source = self._source_map.get(source_id)
                if source is None:
                    continue
                role = PsychologistSource.Role.PRIMARY_WORK if source_id in primary_ids else PsychologistSource.Role.OTHER
                _link, created = PsychologistSource.objects.get_or_create(
                    psychologist=obj,
                    source=source,
                    role=role,
                )
                if created:
                    self.report["psychologist_sources_created"] += 1

    def _promote_theories(self):
        existing_by_name = {
            (_core_identity(obj.name_en) or _normalize_identity(obj.name_en)): obj
            for obj in Theory.objects.all()
            if _normalize_identity(obj.name_en)
        }
        for _group_key, records in self._identity_groups("theories", "theory").items():
            eligible = self._eligible_records(records)
            if not eligible:
                self.report["theories_skipped_no_resolved_source"] += 1
                continue
            ordered = sorted(eligible, key=_record_sort_key)
            slug = _preferred_slug(ordered, "theory")
            if not slug:
                self.report["theories_skipped_missing_slug"] += 1
                continue
            name_en = _text(ordered[0].name_en)
            name_fa = next((_text(record.name_fa) for record in ordered if _text(record.name_fa)), "")
            identity_key = _core_identity(name_en) or _normalize_identity(name_en)
            obj = existing_by_name.get(identity_key)
            created = False
            if obj is None:
                obj, created = self._find_or_create_by_slug(
                    Theory,
                    slug,
                    identity_key,
                    name_en=name_en,
                    name_fa=name_fa,
                    review_status=self._entity_review_status(eligible),
                    seed_managed=False,
                    is_active=True,
                )
                if obj is None:
                    continue
                existing_by_name[identity_key] = obj

            values = {
                "domain": _first_text(ordered, "theory_family_domain", "domain"),
                "period_text": _first_text(ordered, "origin_development_period", "period"),
                "summary_en": _first_text(ordered, "summary_en"),
                "summary_fa": _first_text(ordered, "summary_fa"),
                "core_proposition_en": _first_text(ordered, "core_proposition_en"),
                "core_proposition_fa": _first_text(ordered, "core_proposition_fa"),
                "historical_context_en": _first_text(ordered, "historical_context"),
                "modern_status": _first_text(ordered, "modern_scientific_status", "status"),
                "historical_importance_en": _first_text(ordered, "historical_importance"),
            }
            list_values = {
                "key_propositions_en": _merged_list(ordered, "core_propositions"),
                "applications_en": _merged_list(ordered, "applications"),
                "criticisms_en": _merged_list(ordered, "criticism", "challenges"),
                "limitations_en": _merged_list(ordered, "limitations"),
            }
            changed = False
            if not obj.name_fa and name_fa:
                obj.name_fa = name_fa
                changed = True
            for field, value in values.items():
                if value and not getattr(obj, field):
                    setattr(obj, field, value)
                    changed = True
            for field, value in list_values.items():
                if value and not getattr(obj, field):
                    setattr(obj, field, value)
                    changed = True
            desired_review = self._entity_review_status(eligible)
            if obj.review_status != desired_review and desired_review != ScientificReviewStatus.UNREVIEWED:
                obj.review_status = desired_review
                changed = True
            if not obj.is_active:
                obj.is_active = True
                changed = True
            if changed:
                obj.save()

            self._create_theory_aliases(obj, records)
            self._link_theory_sources(obj, eligible)
            self._mark_records(records, obj, f"theory:{obj.slug}")
            self.report["theories_created" if created else "theories_matched"] += 1

    def _create_theory_aliases(self, obj, records):
        candidates = []
        for record in records:
            if record.name_en and _normalize_identity(record.name_en) != _normalize_identity(obj.name_en):
                candidates.append((record.name_en, TheoryAlias.Language.EN, TheoryAlias.AliasType.ALTERNATIVE))
            if record.name_fa and record.name_fa != obj.name_fa:
                candidates.append((record.name_fa, TheoryAlias.Language.FA, TheoryAlias.AliasType.ALTERNATIVE))
            for text, language, alias_type in _explicit_aliases(record):
                if language == "fa":
                    lang = TheoryAlias.Language.FA
                elif language == "en":
                    lang = TheoryAlias.Language.EN
                else:
                    lang = TheoryAlias.Language.OTHER
                if alias_type == "abbreviation":
                    kind = TheoryAlias.AliasType.ABBREVIATION
                elif alias_type == "historical":
                    kind = TheoryAlias.AliasType.HISTORICAL
                elif alias_type == "transliteration":
                    kind = TheoryAlias.AliasType.TRANSLITERATION
                else:
                    kind = TheoryAlias.AliasType.ALTERNATIVE
                candidates.append((text, lang, kind))
        for text, language, alias_type in _unique(candidates):
            if not _text(text):
                continue
            _alias, created = TheoryAlias.objects.get_or_create(
                theory=obj,
                text=_text(text)[:255],
                language=language,
                defaults={"alias_type": alias_type},
            )
            if created:
                self.report["theory_aliases_created"] += 1

    def _link_theory_sources(self, obj, records):
        for record in records:
            for source in self._resolved_sources(record):
                _link, created = TheorySource.objects.get_or_create(
                    theory=obj,
                    source=source,
                    role=TheorySource.Role.OTHER,
                )
                if created:
                    self.report["theory_sources_created"] += 1

    def _timeline_values(self, record):
        payload = record.payload
        precision_raw = _text(payload.get("date_precision")).lower()
        raw_date = _text(payload.get("date"))
        year_start = _safe_year(payload.get("year_start") or payload.get("year"))
        year_end = _safe_year(payload.get("year_end"))
        exact_date = None

        if precision_raw == TimelineEvent.DatePrecision.EXACT_DATE:
            exact_date = _safe_date(raw_date)
            if exact_date is None:
                return None
            year_start = exact_date.year
            precision = TimelineEvent.DatePrecision.EXACT_DATE
        elif precision_raw in {"range", "year_range"}:
            if year_start is None or year_end is None:
                return None
            precision = TimelineEvent.DatePrecision.YEAR_RANGE
        elif precision_raw in {"approximate", "approximate_year", "circa"}:
            if year_start is None:
                return None
            precision = TimelineEvent.DatePrecision.APPROXIMATE_YEAR
        elif year_start is not None:
            precision = TimelineEvent.DatePrecision.YEAR
        else:
            precision = TimelineEvent.DatePrecision.UNKNOWN

        title_en = _text(payload.get("title_en") or payload.get("event_en") or record.name_en)
        title_fa = _text(payload.get("title_fa") or payload.get("event_fa") or record.name_fa)
        if not title_en:
            return None
        return {
            "title_en": title_en,
            "title_fa": title_fa,
            "description_en": _text(payload.get("description_en") or payload.get("event_en")),
            "description_fa": _text(payload.get("description_fa") or payload.get("event_fa")),
            "historical_importance_en": _text(payload.get("historical_importance_en")),
            "historical_importance_fa": _text(payload.get("historical_importance_fa")),
            "event_type": self._timeline_event_type(payload),
            "category": _text(payload.get("category"))[:160],
            "date_precision": precision,
            "date_text": raw_date or _text(payload.get("year")) or _text(payload.get("year_start")),
            "year_start": year_start,
            "year_end": year_end,
            "exact_date": exact_date,
        }

    def _timeline_event_type(self, payload):
        value = _text(payload.get("event_type")).lower()
        valid = {choice for choice, _label in TimelineEvent.EventType.choices}
        if value in valid:
            return value
        category = _text(payload.get("category")).lower()
        if "guideline" in category:
            return TimelineEvent.EventType.GUIDELINE
        if "nosology" in category or "classification" in category:
            return TimelineEvent.EventType.CLASSIFICATION
        return TimelineEvent.EventType.UNSPECIFIED

    def _promote_timeline_events(self):
        for _group_key, records in self._identity_groups("timeline_events", "event").items():
            eligible = self._eligible_records(records)
            if not eligible:
                self.report["timeline_events_skipped_no_resolved_source"] += 1
                continue
            ordered = sorted(eligible, key=_record_sort_key)
            values = self._timeline_values(ordered[0])
            if values is None:
                self.report["timeline_events_skipped_invalid_date_or_title"] += 1
                continue
            slug = _preferred_slug(ordered, "event")
            if not slug:
                self.report["timeline_events_skipped_missing_slug"] += 1
                continue
            identity_key = _core_identity(values["title_en"]) or _normalize_identity(values["title_en"])
            obj, created = self._find_or_create_by_slug(
                TimelineEvent,
                slug,
                identity_key,
                **values,
                review_status=self._entity_review_status(eligible),
                seed_managed=False,
                is_active=True,
            )
            if obj is None:
                continue
            changed = False
            for field, value in values.items():
                current = getattr(obj, field)
                if current in (None, "") and value not in (None, ""):
                    setattr(obj, field, value)
                    changed = True
            desired_review = self._entity_review_status(eligible)
            if obj.review_status != desired_review and desired_review != ScientificReviewStatus.UNREVIEWED:
                obj.review_status = desired_review
                changed = True
            if not obj.is_active:
                obj.is_active = True
                changed = True
            if changed:
                obj.full_clean()
                obj.save()
            for record in eligible:
                for source in self._resolved_sources(record):
                    _link, source_created = TimelineEventSource.objects.get_or_create(
                        event=obj,
                        source=source,
                        role=TimelineEventSource.Role.OTHER,
                    )
                    if source_created:
                        self.report["timeline_event_sources_created"] += 1
            self._mark_records(records, obj, f"timeline-event:{obj.slug}")
            self.report["timeline_events_created" if created else "timeline_events_matched"] += 1

    def _refresh_endpoint_map(self):
        bucket = defaultdict(set)
        rows = ResearchRecord.objects.filter(promoted_pk__isnull=False).exclude(promoted_model="").values_list(
            "external_id", "promoted_model", "promoted_pk"
        )
        for external_id, model_label, pk in rows:
            bucket[str(external_id)].add((model_label, pk))

        model_map = {
            "atlas.psychologist": Psychologist,
            "atlas.theory": Theory,
            "atlas.concept": Concept,
            "atlas.therapy": Therapy,
            "atlas.technique": Technique,
            "atlas.timelineevent": TimelineEvent,
        }
        endpoint_map = {}
        ambiguities = set()
        for external_id, targets in bucket.items():
            if len(targets) != 1:
                ambiguities.add(external_id)
                continue
            model_label, pk = next(iter(targets))
            model = model_map.get(model_label)
            if model is None:
                continue
            obj = model.objects.filter(pk=pk).first()
            if obj is not None:
                endpoint_map[external_id] = obj
        self._endpoint_map = endpoint_map
        self._endpoint_ambiguities = ambiguities

    def _relationship_parts(self, payload):
        source_id = payload.get("source_id") if payload.get("source_id") is not None else payload.get("source")
        target_id = payload.get("target_id") if payload.get("target_id") is not None else payload.get("target")
        relation_type = payload.get("relation_type") if payload.get("relation_type") is not None else payload.get("relation")
        source_ids = payload.get("source_ids") if payload.get("source_ids") is not None else payload.get("sources")
        if source_ids is None:
            source_ids = []
        if not isinstance(source_ids, list):
            source_ids = [source_ids]
        return _text(source_id), _text(target_id), _text(relation_type).lower(), [str(value) for value in source_ids if value not in (None, "")]

    def _relation_sources(self, source_ids):
        if not source_ids:
            return []
        sources = [self._source_map.get(source_id) for source_id in source_ids]
        if any(source is None for source in sources):
            return []
        return sources

    def _promote_explicit_relationships(self):
        for record in ResearchRecord.objects.filter(section="relationships").order_by("dataset_id", "id"):
            source_id, target_id, relation_type, source_ids = self._relationship_parts(record.payload)
            if not source_id or not target_id or not relation_type:
                continue
            if source_id in self._endpoint_ambiguities or target_id in self._endpoint_ambiguities:
                self.report["relations_skipped_ambiguous_endpoint"] += 1
                continue
            source_obj = self._endpoint_map.get(source_id)
            target_obj = self._endpoint_map.get(target_id)
            if source_obj is None or target_obj is None:
                continue
            sources = self._relation_sources(source_ids)
            if not sources:
                if isinstance(source_obj, (Psychologist, Theory)) or isinstance(target_obj, (Psychologist, Theory)):
                    self.report["v06_relations_skipped_no_resolved_source"] += 1
                continue
            relation, source_model = self._create_supported_relation(source_obj, target_obj, relation_type, record.payload)
            if relation is None:
                if isinstance(source_obj, (Psychologist, Theory)) or isinstance(target_obj, (Psychologist, Theory)):
                    self.report["v06_relations_skipped_unsupported_semantics"] += 1
                continue
            for source in sources:
                source_model.objects.get_or_create(relationship=relation, source=source)
            self._mark_relation_record(record, relation)
            self.report["v06_relations_promoted"] += 1

    def _create_supported_relation(self, source_obj, target_obj, relation_type, payload):
        explanation_en = _text(payload.get("explanation_en") or payload.get("explanation"))
        explanation_fa = _text(payload.get("explanation_fa"))
        defaults = {
            "explanation_en": explanation_en,
            "explanation_fa": explanation_fa,
            "review_status": ScientificReviewStatus.SOURCE_CHECKED,
            "is_active": True,
            "seed_managed": False,
        }
        if (
            isinstance(source_obj, TimelineEvent)
            and isinstance(target_obj, Psychologist)
            and relation_type == TimelineLinkRole.INVOLVES_PERSON
        ):
            return self._upsert_timeline_relation(
                TimelinePsychologist,
                TimelinePsychologistSource,
                {"event": source_obj, "psychologist": target_obj},
                relation_type,
                defaults,
            )
        if (
            isinstance(source_obj, TimelineEvent)
            and isinstance(target_obj, Theory)
            and relation_type == TimelineLinkRole.MARKS_THEORY_MILESTONE
        ):
            return self._upsert_timeline_relation(
                TimelineTheory,
                TimelineTheorySource,
                {"event": source_obj, "theory": target_obj},
                relation_type,
                defaults,
            )
        if (
            isinstance(source_obj, TimelineEvent)
            and isinstance(target_obj, Therapy)
            and relation_type == TimelineLinkRole.MARKS_THERAPY_MILESTONE
        ):
            return self._upsert_timeline_relation(
                TimelineTherapy,
                TimelineTherapySource,
                {"event": source_obj, "therapy": target_obj},
                relation_type,
                defaults,
            )
        if (
            isinstance(source_obj, TimelineEvent)
            and isinstance(target_obj, Technique)
            and relation_type == TimelineLinkRole.MARKS_TECHNIQUE_EVIDENCE_MILESTONE
        ):
            return self._upsert_timeline_relation(
                TimelineTechnique,
                TimelineTechniqueSource,
                {"event": source_obj, "technique": target_obj},
                relation_type,
                defaults,
            )

        mapping = None
        if isinstance(source_obj, Psychologist) and isinstance(target_obj, Theory) and relation_type in PSYCHOLOGIST_RELATION_TYPES:
            mapping = (PsychologistTheory, PsychologistTheorySource, {"psychologist": source_obj, "theory": target_obj, "relationship_type": relation_type})
        elif isinstance(source_obj, Psychologist) and isinstance(target_obj, Therapy) and relation_type in PSYCHOLOGIST_RELATION_TYPES:
            mapping = (PsychologistTherapy, PsychologistTherapySource, {"psychologist": source_obj, "therapy": target_obj, "relationship_type": relation_type})
        elif isinstance(source_obj, Psychologist) and isinstance(target_obj, Concept) and relation_type in PSYCHOLOGIST_RELATION_TYPES:
            mapping = (PsychologistConcept, PsychologistConceptSource, {"psychologist": source_obj, "concept": target_obj, "relationship_type": relation_type})
        elif isinstance(source_obj, Psychologist) and isinstance(target_obj, Psychologist):
            return None, None
        elif isinstance(source_obj, Theory) and isinstance(target_obj, Concept) and relation_type in THEORY_RELATION_TYPES:
            mapping = (TheoryConcept, TheoryConceptSource, {"theory": source_obj, "concept": target_obj, "relationship_type": relation_type})
        elif isinstance(source_obj, Theory) and isinstance(target_obj, Therapy) and relation_type in THEORY_RELATION_TYPES:
            mapping = (TheoryTherapy, TheoryTherapySource, {"theory": source_obj, "therapy": target_obj, "relationship_type": relation_type})
        elif isinstance(source_obj, Theory) and isinstance(target_obj, Technique) and relation_type in THEORY_RELATION_TYPES:
            mapping = (TheoryTechnique, TheoryTechniqueSource, {"theory": source_obj, "technique": target_obj, "relationship_type": relation_type})
        elif isinstance(source_obj, Theory) and isinstance(target_obj, Theory) and relation_type in THEORY_RELATION_TYPES:
            mapping = (TheoryTheory, TheoryTheorySource, {"theory": source_obj, "related_theory": target_obj, "relationship_type": relation_type})
        if mapping is None:
            return None, None
        model, source_model, lookup = mapping
        relation, created = model.objects.get_or_create(**lookup, defaults=defaults)
        changed = False
        if not created:
            for field, value in defaults.items():
                current = getattr(relation, field)
                if field in {"is_active", "seed_managed", "review_status"}:
                    if field == "is_active" and not current:
                        setattr(relation, field, True)
                        changed = True
                    elif field == "seed_managed" and current:
                        setattr(relation, field, False)
                        changed = True
                    elif field == "review_status" and current == ScientificReviewStatus.UNREVIEWED:
                        setattr(relation, field, ScientificReviewStatus.SOURCE_CHECKED)
                        changed = True
                elif value and not current:
                    setattr(relation, field, value)
                    changed = True
            if changed:
                relation.save()
        return relation, source_model

    def _upsert_timeline_relation(self, model, source_model, lookup, role, defaults):
        relation = model.objects.filter(**lookup, role=role).order_by("id").first()
        if relation is None and role != TimelineLinkRole.RELATED:
            relation = model.objects.filter(**lookup, role=TimelineLinkRole.RELATED).order_by("id").first()
        if relation is None:
            relation = model.objects.filter(**lookup).order_by("id").first()
        if relation is None:
            relation = model.objects.create(**lookup, role=role, **defaults)
            return relation, source_model

        changed = False
        if relation.role == TimelineLinkRole.RELATED and role != TimelineLinkRole.RELATED:
            relation.role = role
            changed = True
        for field, value in defaults.items():
            current = getattr(relation, field)
            if field == "is_active" and not current:
                relation.is_active = True
                changed = True
            elif field == "seed_managed" and current:
                relation.seed_managed = False
                changed = True
            elif field == "review_status" and current == ScientificReviewStatus.UNREVIEWED:
                relation.review_status = ScientificReviewStatus.SOURCE_CHECKED
                changed = True
            elif field not in {"is_active", "seed_managed", "review_status"} and value and not current:
                setattr(relation, field, value)
                changed = True
        if changed:
            relation.save()
        return relation, source_model

    def _mark_relation_record(self, record, relation):
        model_label = relation._meta.label_lower
        updates = []
        if record.promoted_model != model_label:
            record.promoted_model = model_label
            updates.append("promoted_model")
        if record.promoted_pk != relation.pk:
            record.promoted_pk = relation.pk
            updates.append("promoted_pk")
        if updates:
            updates.append("updated_at")
            record.save(update_fields=updates)

    def _promote_timeline_links(self):
        event_records = ResearchRecord.objects.filter(
            section="timeline_events",
            promoted_model="atlas.timelineevent",
            promoted_pk__isnull=False,
        ).order_by("dataset_id", "id")
        event_objects = TimelineEvent.objects.in_bulk(set(event_records.values_list("promoted_pk", flat=True)))
        for record in event_records:
            event = event_objects.get(record.promoted_pk)
            if event is None:
                continue
            sources = self._resolved_sources(record)
            if not sources:
                continue
            link_ids = defaultdict(list)
            payload = record.payload
            for key, kind in (
                ("people_ids", "psychologist"),
                ("theory_ids", "theory"),
                ("therapy_ids", "therapy"),
                ("technique_ids", "technique"),
                ("concept_ids", "concept"),
            ):
                for external_id in _list(payload.get(key)):
                    link_ids[kind].append(str(external_id))
            for external_id in _list(payload.get("related")):
                external_id = str(external_id)
                target = self._endpoint_map.get(external_id)
                if isinstance(target, Psychologist):
                    link_ids["psychologist"].append(external_id)
                elif isinstance(target, Theory):
                    link_ids["theory"].append(external_id)
                elif isinstance(target, Therapy):
                    link_ids["therapy"].append(external_id)
                elif isinstance(target, Technique):
                    link_ids["technique"].append(external_id)
                elif isinstance(target, Concept):
                    link_ids["concept"].append(external_id)

            for kind, external_ids in link_ids.items():
                for external_id in _unique(external_ids):
                    target = self._endpoint_map.get(external_id)
                    relation, source_model = self._timeline_link(event, target, kind)
                    if relation is None:
                        self.report["timeline_links_skipped_unresolved"] += 1
                        continue
                    for source in sources:
                        source_model.objects.get_or_create(relationship=relation, source=source)
                    self.report["timeline_links_promoted"] += 1

    def _timeline_link(self, event, target, kind):
        defaults = {
            "review_status": ScientificReviewStatus.SOURCE_CHECKED,
            "is_active": True,
            "seed_managed": False,
        }
        if kind == "psychologist" and isinstance(target, Psychologist):
            return self._upsert_timeline_relation(
                TimelinePsychologist,
                TimelinePsychologistSource,
                {"event": event, "psychologist": target},
                TimelineLinkRole.RELATED,
                defaults,
            )
        if kind == "theory" and isinstance(target, Theory):
            return self._upsert_timeline_relation(
                TimelineTheory,
                TimelineTheorySource,
                {"event": event, "theory": target},
                TimelineLinkRole.RELATED,
                defaults,
            )
        if kind == "therapy" and isinstance(target, Therapy):
            return self._upsert_timeline_relation(
                TimelineTherapy,
                TimelineTherapySource,
                {"event": event, "therapy": target},
                TimelineLinkRole.RELATED,
                defaults,
            )
        if kind == "technique" and isinstance(target, Technique):
            return self._upsert_timeline_relation(
                TimelineTechnique,
                TimelineTechniqueSource,
                {"event": event, "technique": target},
                TimelineLinkRole.RELATED,
                defaults,
            )
        if kind == "concept" and isinstance(target, Concept):
            return self._upsert_timeline_relation(
                TimelineConcept,
                TimelineConceptSource,
                {"event": event, "concept": target},
                TimelineLinkRole.RELATED,
                defaults,
            )
        return None, None


def promote_research_staging():
    return ResearchStagingPromoter().promote()
