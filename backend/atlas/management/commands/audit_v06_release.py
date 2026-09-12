from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q

from atlas import models as atlas_models


WEAK_VERIFICATION_STATUS = "citation_from_model_knowledge"

ENTITY_MODELS = (
    (atlas_models.Psychologist, "Psychologist"),
    (atlas_models.Theory, "Theory"),
    (atlas_models.TimelineEvent, "TimelineEvent"),
)

RELATION_MODELS = (
    (atlas_models.PsychologistTheory, "PsychologistTheory"),
    (atlas_models.PsychologistConcept, "PsychologistConcept"),
    (atlas_models.PsychologistTherapy, "PsychologistTherapy"),
    (atlas_models.PsychologistPsychologist, "PsychologistPsychologist"),
    (atlas_models.TheoryConcept, "TheoryConcept"),
    (atlas_models.TheoryTherapy, "TheoryTherapy"),
    (atlas_models.TheoryTechnique, "TheoryTechnique"),
    (atlas_models.TheoryTheory, "TheoryTheory"),
    (atlas_models.TimelinePsychologist, "TimelinePsychologist"),
    (atlas_models.TimelineTheory, "TimelineTheory"),
    (atlas_models.TimelineTherapy, "TimelineTherapy"),
    (atlas_models.TimelineTechnique, "TimelineTechnique"),
    (atlas_models.TimelineConcept, "TimelineConcept"),
)


def provenance_metrics(queryset):
    annotated = queryset.annotate(
        source_count=Count("source_links", distinct=True),
        independently_supported_count=Count(
            "source_links",
            filter=~Q(source_links__source__verification_status=WEAK_VERIFICATION_STATUS),
            distinct=True,
        ),
    )
    return {
        "active": queryset.count(),
        "gaps": annotated.filter(source_count=0).count(),
        "weak_only": annotated.filter(source_count__gt=0, independently_supported_count=0).count(),
        "weak_reviewed": annotated.filter(
            source_count__gt=0,
            independently_supported_count=0,
            review_status=atlas_models.ScientificReviewStatus.REVIEWED,
        ).count(),
    }


def timeline_precision_issues():
    issues = []
    for event in atlas_models.TimelineEvent.objects.filter(is_active=True).only(
        "slug", "date_precision", "year_start", "year_end", "exact_date"
    ):
        errors = []
        if event.date_precision == atlas_models.TimelineEvent.DatePrecision.EXACT_DATE and event.exact_date is None:
            errors.append("exact_date_missing")
        if event.date_precision != atlas_models.TimelineEvent.DatePrecision.EXACT_DATE and event.exact_date is not None:
            errors.append("non_exact_has_exact_date")
        if event.date_precision in {
            atlas_models.TimelineEvent.DatePrecision.YEAR,
            atlas_models.TimelineEvent.DatePrecision.YEAR_RANGE,
            atlas_models.TimelineEvent.DatePrecision.APPROXIMATE_YEAR,
        } and event.year_start is None:
            errors.append("year_start_missing")
        if event.date_precision == atlas_models.TimelineEvent.DatePrecision.YEAR_RANGE and event.year_end is None:
            errors.append("year_end_missing")
        if event.year_start is not None and event.year_end is not None and event.year_end < event.year_start:
            errors.append("year_order_invalid")
        if errors:
            issues.append((event.slug, errors))
    return issues


class Command(BaseCommand):
    help = (
        "Audit v0.6 scientific-release invariants without mutating data. "
        "Weak archival citations are reported as review debt; only provenance gaps, "
        "weak-only rows incorrectly marked reviewed, or invalid Timeline precision fail the command."
    )

    def handle(self, *args, **options):
        failures = []
        weak_entity_total = 0
        weak_relation_total = 0

        self.stdout.write("v0.6 release scientific audit")
        self.stdout.write("Entities:")
        for model, label in ENTITY_MODELS:
            metrics = provenance_metrics(model.objects.filter(is_active=True))
            weak_entity_total += metrics["weak_only"]
            self.stdout.write(
                f"  {label}: active={metrics['active']} gaps={metrics['gaps']} "
                f"weak_only={metrics['weak_only']} weak_reviewed={metrics['weak_reviewed']}"
            )
            if metrics["gaps"]:
                failures.append(f"{label} has {metrics['gaps']} active provenance gaps")
            if metrics["weak_reviewed"]:
                failures.append(
                    f"{label} has {metrics['weak_reviewed']} weak-only rows incorrectly marked reviewed"
                )

        self.stdout.write("Relations:")
        relation_total = 0
        for model, label in RELATION_MODELS:
            metrics = provenance_metrics(model.objects.filter(is_active=True))
            relation_total += metrics["active"]
            weak_relation_total += metrics["weak_only"]
            self.stdout.write(
                f"  {label}: active={metrics['active']} gaps={metrics['gaps']} "
                f"weak_only={metrics['weak_only']} weak_reviewed={metrics['weak_reviewed']}"
            )
            if metrics["gaps"]:
                failures.append(f"{label} has {metrics['gaps']} active provenance gaps")
            if metrics["weak_reviewed"]:
                failures.append(
                    f"{label} has {metrics['weak_reviewed']} weak-only rows incorrectly marked reviewed"
                )

        precision_issues = timeline_precision_issues()
        self.stdout.write(
            f"Summary: relations={relation_total} weak_entities={weak_entity_total} "
            f"weak_relations={weak_relation_total} timeline_precision_issues={len(precision_issues)}"
        )
        if precision_issues:
            failures.append(
                "Timeline precision issues: "
                + "; ".join(f"{slug}={','.join(errors)}" for slug, errors in precision_issues[:10])
            )

        if failures:
            raise CommandError("v0.6 release audit FAILED\n- " + "\n- ".join(failures))

        self.stdout.write(self.style.SUCCESS("v0.6 release audit PASS"))
        if weak_entity_total or weak_relation_total:
            self.stdout.write(
                self.style.WARNING(
                    "Scientific review debt remains visible: weak-only archival citations are not treated as independently verified."
                )
            )
