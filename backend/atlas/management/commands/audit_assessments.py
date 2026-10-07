"""Deterministic integrity audit; uncertain permissions are debt, not fabricated grants."""
from collections import Counter, defaultdict
import json

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from atlas import models as m
from atlas.assessment_publication import MODELS, SCHEMA, protected_paths, verify_publication
from atlas.brain_source_resolution import normalized_text


def audit():
    issues, warnings = [], []
    counts = {name: model.objects.count() for name,model in MODELS.items() if name != "source"}
    for category,model in MODELS.items():
        if category == "source":
            continue
        for obj in model.objects.order_by("pk"):
            try:
                obj.full_clean()
            except (ValidationError, ObjectDoesNotExist, ValueError) as error:
                issues.append(f"{category}:{obj.pk}: {error}")
    for link in m.AssessmentSource.objects.order_by("pk"):
        try:
            link.full_clean()
        except (ValidationError, ObjectDoesNotExist) as error:
            issues.append(f"source_link:{link.pk}: {error}")
    names = defaultdict(list)
    for row in m.AssessmentInstrument.objects.order_by("pk"):
        names[normalized_text(row.name_en)].append(row.slug)
        if row.normalized_name != normalized_text(row.name_en):
            issues.append("instrument:" + row.slug + ": normalized identity mismatch")
    for name,slugs in sorted(names.items()):
        if len(slugs) > 1:
            issues.append("duplicate_instrument_identity:" + name + ":" + ",".join(slugs))
    aliases = defaultdict(set)
    for row in m.AssessmentAlias.objects.filter(is_active=True, review_status="reviewed").order_by("pk"):
        aliases[(row.language, normalized_text(row.text))].add(row.instrument_id)
        if row.normalized_text != normalized_text(row.text):
            issues.append(f"alias:{row.pk}: normalized identity mismatch")
    for key,owners in sorted(aliases.items()):
        if len(owners) > 1:
            warnings.append("ambiguous_alias:" + ":".join(key) + ":families=" + ",".join(map(str, sorted(owners))))
    for dataset in m.ResearchDataset.objects.filter(raw_document__schema_version=SCHEMA).order_by("key"):
        for path in protected_paths(dataset.raw_document):
            issues.append("protected_content:" + dataset.key + ":" + path)
        for record in dataset.records.order_by("external_id"):
            for path in protected_paths(record.payload):
                issues.append("protected_content_record:" + record.external_id + ":" + path)
        if dataset.ingestion_audit.get("assessment_publication"):
            try:
                verify_publication(dataset)
            except (CommandError, ValidationError, ObjectDoesNotExist, KeyError, ValueError) as error:
                issues.append("publication_manifest:" + dataset.key + ":" + str(error))
    access = m.AssessmentAccess.objects.filter(is_active=True, review_status="reviewed")
    licenses = dict(sorted(Counter(access.values_list("license_status", flat=True)).items()))
    availability = dict(sorted(Counter(access.values_list("availability", flat=True)).items()))
    source_ids = set(m.AssessmentSource.objects.values_list("source_id", flat=True))
    for model,field in ((m.AssessmentAlias, "source_id"), (m.AssessmentValidationStudy, "source_id"),
                       (m.AssessmentAccess, "source_id"), (m.AssessmentLanguageForm, "authorization_source_id")):
        source_ids.update(model.objects.exclude(**{field: None}).values_list(field, flat=True))
    return dict(status="PASS" if not issues else "FAIL", counts=counts, source_count=len(source_ids),
                license_distribution=licenses, access_distribution=availability,
                persian_forms=m.AssessmentLanguageForm.objects.filter(language="fa", is_active=True, review_status="reviewed").count(),
                persian_studies=m.AssessmentValidationStudy.objects.filter(language_form__language="fa", is_active=True, review_status="reviewed").count(),
                issues=sorted(set(issues)), warnings=sorted(set(warnings)))


class Command(BaseCommand):
    help = "Read-only audit of Assessment identity, evidence, rights, provenance and publication receipts."

    def handle(self, *args, **options):
        result = audit()
        self.stdout.write(json.dumps(result, sort_keys=True, ensure_ascii=False))
        if result["issues"]:
            raise CommandError(f"Assessment audit failed with {len(result['issues'])} issue(s).")
