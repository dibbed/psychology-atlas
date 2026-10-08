"""Read-only educational registry, with bounded context beside each finding."""
import re

from django.db.models import Exists, F, OuterRef, Prefetch, Q
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.exceptions import ValidationError

from . import models as m
from .brain_publication import NONBLANK_PATTERN, resolved_sources
from .pagination import AtlasPagination
from .search_utils import icontains_any, ranked_public_search

LIMIT = 30
INTERPRETATION = "Educational metadata. Screening and measurement do not establish a diagnosis. Findings apply only to the stated edition, form, population and study. Access does not grant redistribution or scoring permission."


def public_sets():
    # Resolve shared bibliographies once, rather than repeating provenance regex work in every nested subquery.
    source_ids = list(resolved_sources().values_list("pk", flat=True))
    checked = dict(is_active=True, review_status="reviewed")
    links = m.AssessmentSource.objects.filter(source_id__in=source_ids, note__regex=NONBLANK_PATTERN)
    instruments = m.AssessmentInstrument.objects.filter(**checked).filter(Exists(links.filter(instrument_id=OuterRef("pk"))))
    versions = m.AssessmentVersion.objects.filter(**checked, instrument__in=instruments).filter(Exists(links.filter(version_id=OuterRef("pk"))))
    forms = m.AssessmentLanguageForm.objects.filter(**checked, version__in=versions).filter(Exists(links.filter(language_form_id=OuterRef("pk"))))
    forms = forms.filter(Q(authorization_status="unknown") | Q(authorization_status="authorized", authorization_source_id__in=source_ids,
                                                             authorization_note__regex=NONBLANK_PATTERN))
    studies = m.AssessmentValidationStudy.objects.filter(**checked, version__in=versions, language_form__in=forms,
        language_form__version_id=F("version_id"), source_id__in=source_ids)
    for field in ("source_note", "design", "population", "sample_context", "administration", "informant", "method", "limitations"):
        studies = studies.filter(**{field + "__regex": NONBLANK_PATTERN})
    findings = m.AssessmentPsychometricEvidence.objects.filter(**checked, study__in=studies,
        measurement_property__in=m.AssessmentPsychometricEvidence.Property.values)
    for field in ("statistic", "method", "finding", "limitations", "extraction_locator"):
        findings = findings.filter(**{field + "__regex": NONBLANK_PATTERN})
    aliases = m.AssessmentAlias.objects.filter(**checked, instrument__in=instruments, source_id__in=source_ids,
        source_note__regex=NONBLANK_PATTERN, alias_type__in=m.AssessmentAlias.Kind.values).filter(
        Q(version__isnull=True) | Q(version__in=versions, version__instrument_id=F("instrument_id")))
    access = m.AssessmentAccess.objects.filter(**checked, version__in=versions, source_id__in=source_ids,
        source_note__regex=NONBLANK_PATTERN, license_status__in=m.AssessmentAccess.License.values,
        availability__in=m.AssessmentAccess.Availability.values).filter(
        Q(language_form__isnull=True) | Q(language_form__in=forms, language_form__version_id=F("version_id"))).filter(
        Q(expires_on__isnull=True) | Q(expires_on__gte=timezone.localdate())).filter(
        Q(license_status="unknown", availability="unknown") | Q(verified_on__isnull=False))
    relations = m.AssessmentRelation.objects.filter(**checked, version__in=versions).filter(
        Exists(links.filter(relation_id=OuterRef("pk")))).filter(
        Q(language_form__isnull=True) | Q(language_form__in=forms, language_form__version_id=F("version_id")))
    relations = relations.filter(
        Q(predicate__in=("measures", "research_measure_of", "monitors"), concept__is_active=True, symptom__isnull=True, disorder__isnull=True)
        | Q(predicate__in=("screens_for", "monitors"), symptom__isnull=False, concept__isnull=True, disorder__isnull=True)
        | Q(predicate__in=("screens_for", "monitors", "diagnostic_support_for"), disorder__is_active=True, concept__isnull=True, symptom__isnull=True))
    return dict(source_ids=source_ids, instruments=instruments, versions=versions, forms=forms, studies=studies,
                findings=findings, aliases=aliases, access=access, relations=relations, links=links)


def bounded(rows, serialize):
    return dict(results=[serialize(row) for row in rows[:LIMIT]], truncated=len(rows) > LIMIT)


def source_data(source):
    return {name: getattr(source, name) for name in ("id", "title", "citation", "url", "doi", "pmid", "publication_year")}


def source_link(link):
    return dict(source=source_data(link.source), note=link.note)


def alias_data(alias):
    return dict(text=alias.text, language=alias.language, alias_type=alias.alias_type, source=source_data(alias.source))


def identity_data(obj, fields):
    return {field: getattr(obj, field) for field in fields}


def form_data(form):
    return dict(**identity_data(form, ("key", "language", "label", "form_kind", "owner", "authorization_status", "authorization_note", "review_status")),
                authorization_source=source_data(form.authorization_source) if form.authorization_source_id else None,
                sources=bounded(form.public_sources, source_link))


def finding_data(finding):
    return identity_data(finding, ("key", "measurement_property", "statistic", "method", "value_text", "units",
                                  "uncertainty", "finding", "limitations", "extraction_locator", "review_status"))


def study_data(study):
    return dict(**identity_data(study, ("key", "design", "population", "sample_context", "sample_size", "administration", "informant", "method", "comparator", "limitations", "review_status")),
                version=study.version.key, language_form=study.language_form.key, language=study.language_form.language,
                source=source_data(study.source), source_note=study.source_note,
                findings=bounded(study.public_findings, finding_data))


def access_data(access):
    return dict(**identity_data(access, ("key", "material_type", "use", "jurisdiction", "owner", "availability", "license_status", "terms", "verified_on", "expires_on")),
                language_form=access.language_form.key if access.language_form_id else None,
                source=source_data(access.source), source_note=access.source_note)


def relation_data(relation):
    field = next(name for name in ("concept", "symptom", "disorder") if getattr(relation, name + "_id"))
    target = getattr(relation, field)
    return dict(**identity_data(relation, ("key", "predicate", "claim", "context", "limitations")),
                language_form=relation.language_form.key if relation.language_form_id else None,
                target=dict(type=field, slug=target.slug, name_en=target.name_en),
                sources=bounded(relation.public_sources, source_link))


def version_data(version, detail=False):
    data = dict(**identity_data(version, ("key", "label", "form_kind", "publication_year", "construct", "intended_use", "administration", "informant", "population", "limitations", "review_status")),
                derived_from=version.derived_from.key if version.derived_from_id and version.derived_from_public else None,
                sources=bounded(version.public_sources, source_link))
    if detail:
        data.update(aliases=bounded(version.public_aliases, alias_data), language_forms=bounded(version.public_forms, form_data),
                    access=bounded(version.public_access, access_data), validation_studies=bounded(version.public_studies, study_data),
                    relations=bounded(version.public_relations, relation_data))
    return data


class AssessmentSerializer(serializers.BaseSerializer):
    def to_representation(self, instrument):
        detail = self.context.get("detail", False)
        return dict(**identity_data(instrument, ("slug", "name_en", "name_fa", "description", "construct_overview", "rightsholder", "review_status")),
                    aliases=bounded(instrument.public_aliases, alias_data),
                    versions=bounded(instrument.public_versions, lambda version: version_data(version, detail)),
                    sources=bounded(instrument.public_sources, source_link), interpretation_limitations=INTERPRETATION)


def loaded_instruments(sets, *, detail=False):
    links = sets["links"].select_related("source").order_by("source_id", "pk")[:LIMIT + 1]
    aliases = sets["aliases"].select_related("source").order_by("language", "text", "pk")
    versions = sets["versions"].annotate(derived_from_public=Exists(sets["versions"].filter(
        pk=OuterRef("derived_from_id"), instrument_id=OuterRef("instrument_id")))).select_related("derived_from").order_by("key", "pk").prefetch_related(
        Prefetch("source_links", queryset=links, to_attr="public_sources"))
    if detail:
        forms = sets["forms"].select_related("authorization_source").order_by("language", "key", "pk").prefetch_related(
            Prefetch("source_links", queryset=links, to_attr="public_sources"))
        findings = sets["findings"].order_by("key", "pk")
        studies = sets["studies"].select_related("source", "version", "language_form").order_by("key", "pk").prefetch_related(
            Prefetch("findings", queryset=findings[:LIMIT + 1], to_attr="public_findings"))
        relations = sets["relations"].select_related("concept", "symptom", "disorder", "language_form").order_by("key", "pk").prefetch_related(
            Prefetch("source_links", queryset=links, to_attr="public_sources"))
        versions = versions.prefetch_related(
            Prefetch("aliases", queryset=aliases[:LIMIT + 1], to_attr="public_aliases"),
            Prefetch("language_forms", queryset=forms[:LIMIT + 1], to_attr="public_forms"),
            Prefetch("access_records", queryset=sets["access"].select_related("source", "language_form").order_by("key", "pk")[:LIMIT + 1], to_attr="public_access"),
            Prefetch("validation_studies", queryset=studies[:LIMIT + 1], to_attr="public_studies"),
            Prefetch("relations", queryset=relations[:LIMIT + 1], to_attr="public_relations"))
    return sets["instruments"].prefetch_related(
        Prefetch("aliases", queryset=aliases.filter(version__isnull=True)[:LIMIT + 1], to_attr="public_aliases"),
        Prefetch("source_links", queryset=links, to_attr="public_sources"),
        Prefetch("versions", queryset=versions[:LIMIT + 1], to_attr="public_versions"))


class AssessmentListView(generics.ListAPIView):
    serializer_class = AssessmentSerializer
    pagination_class = AtlasPagination

    def get_queryset(self):
        params = self.request.query_params
        allowed = {"q", "construct", "intended_use", "language", "access", "license", "form_kind", "page", "page_size", "format"}
        if set(params) - allowed:
            raise ValidationError({key: "Unsupported Assessment filter." for key in sorted(set(params) - allowed)})
        if any(len(params.getlist(key)) != 1 for key in params):
            raise ValidationError("Assessment parameters require one value each.")
        sets = public_sets()
        versions = sets["versions"].filter(instrument_id=OuterRef("pk"))
        qs = loaded_instruments(sets)
        for key, choices in (("intended_use", m.AssessmentVersion.Purpose.values), ("form_kind", m.AssessmentVersion.Kind.values),
                             ("access", m.AssessmentAccess.Availability.values), ("license", m.AssessmentAccess.License.values)):
            if key in params and params[key] not in choices:
                raise ValidationError({key: "Unknown Assessment filter value."})
        if "construct" in params:
            value = params["construct"].strip()
            if not re.fullmatch(r"[a-z0-9_-]{1,120}", value) or not sets["versions"].filter(construct=value).exists():
                raise ValidationError({"construct": "Unknown reviewed construct descriptor."})
            versions = versions.filter(construct=value)
        for key in ("intended_use", "form_kind"):
            if key in params:
                versions = versions.filter(**{key: params[key]})
        if "language" in params:
            language = params["language"]
            if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z]{2})?", language) or not sets["forms"].filter(language=language).exists():
                raise ValidationError({"language": "Unknown reviewed language form."})
            versions = versions.filter(Exists(sets["forms"].filter(version_id=OuterRef("pk"), language=language)))
        if "access" in params or "license" in params:
            access = sets["access"].filter(version_id=OuterRef("pk"))
            if "language" in params:
                access = access.filter(language_form__language=params["language"], language_form__in=sets["forms"])
            for key, field in (("access", "availability"), ("license", "license_status")):
                if key in params:
                    access = access.filter(**{field: params[key]})
            versions = versions.filter(Exists(access))
        if set(params) & {"construct", "intended_use", "form_kind", "language", "access", "license"}:
            qs = qs.filter(Exists(versions))
        q = params.get("q", "").strip()
        if len(q) > 255:
            raise ValidationError({"q": "Search text must be at most 255 characters."})
        if q:
            aliases = sets["aliases"].filter(instrument_id=OuterRef("pk"))
            return ranked_public_search(qs, q, aliases, ("name_en", "name_fa", "slug"),
                extra_match=Exists(versions.filter(icontains_any(("label", "key"), q))))
        return qs.order_by("name_en", "id")


class AssessmentDetailView(generics.RetrieveAPIView):
    serializer_class = AssessmentSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return loaded_instruments(public_sets(), detail=True)

    def get_serializer_context(self):
        return dict(super().get_serializer_context(), detail=True)
