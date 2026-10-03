"""Deterministic, read-only integrity and publication-debt audit."""

import json
from collections import Counter, defaultdict

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db.models.deletion import ProtectedError

from atlas import models
from atlas.brain_publication import source_is_resolved
from atlas.brain_staging import validate_brain_staging


ENTITY_MODELS = (("anatomy", models.BrainAnatomicalEntity), ("networks", models.BrainNetwork))
RELATION_MODELS = (("hierarchy", models.BrainHierarchyLink), ("memberships", models.BrainNetworkMembership),
                   ("functional_associations", models.BrainFunctionalAssociation))
SOURCE_MODELS = (models.BrainAnatomicalEntitySource, models.BrainNetworkSource, models.BrainHierarchyLinkSource,
                 models.BrainNetworkMembershipSource, models.BrainFunctionalAssociationSource)


class Command(BaseCommand):
    help = "Audit Brain identity, hierarchy, source integrity, review states, and publication debt without writes."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        errors = set()
        debt = set()
        counts = {}
        reviews = {}
        provenance = {}
        sources = models.SourceReference.objects.in_bulk()

        def fail(label, pk, code):
            errors.add(f"{label}:{pk}:{code}")

        for label, model in ENTITY_MODELS + RELATION_MODELS:
            rows = list(model.objects.order_by("pk").prefetch_related("source_links"))
            counts[label] = len(rows)
            reviews[label] = dict(sorted(Counter(row.review_status for row in rows).items()))
            metrics = Counter()
            identities = defaultdict(list)
            for row in rows:
                links = list(row.source_links.all())
                supported = [link for link in links if source_is_resolved(sources.get(link.source_id))
                             and (label in {"anatomy", "networks"} or link.note.strip())]
                metrics["resolved" if supported else "weak_only" if links else "unsourced"] += 1
                if row.review_status != models.ScientificReviewStatus.UNREVIEWED and not supported:
                    fail(label, row.pk, "missing_resolved_provenance")
                elif not supported:
                    debt.add(f"{label}:{row.pk}:unreviewed_provenance_debt")
                if row.review_status not in models.ScientificReviewStatus.values:
                    fail(label, row.pk, "unsupported_review_state")
                try:
                    row.full_clean()
                except (ValidationError, ProtectedError):
                    fail(label, row.pk, "invalid_model_state")
                if label in {"anatomy", "networks"}:
                    identities[row.slug.strip().casefold()].append(row.pk)
                if label == "hierarchy" and row.is_active:
                    endpoints = models.BrainAnatomicalEntity.objects.in_bulk([row.child_id, row.parent_id])
                    child, parent = endpoints.get(row.child_id), endpoints.get(row.parent_id)
                    if child is None or parent is None:
                        fail(label, row.pk, "orphan_endpoint")
                    elif not child.is_active or not parent.is_active:
                        fail(label, row.pk, "inactive_hierarchy")
                    elif models.BrainHierarchyLink.laterality_conflicts(child.laterality, parent.laterality):
                        fail(label, row.pk, "laterality_conflict")
            for pks in identities.values():
                if len(pks) > 1:
                    for pk in pks:
                        fail(label, pk, "duplicate_canonical_identity")
            provenance[label] = dict(sorted(metrics.items()))

        for model in (models.BrainAnatomicalAlias, models.BrainNetworkAlias, models.BrainExternalIdentifier) + SOURCE_MODELS:
            for row in model.objects.order_by("pk"):
                label = model._meta.model_name
                try:
                    row.full_clean()
                except (ValidationError, ProtectedError):
                    fail(label, row.pk, "invalid_alias" if "alias" in label else
                         "invalid_external_identifier" if model is models.BrainExternalIdentifier else "invalid_source_link")
                if model in SOURCE_MODELS:
                    owner_model = model._meta.get_field(model.owner_field).remote_field.model
                    if row.source_id not in sources or not owner_model.objects.filter(pk=getattr(row, f"{model.owner_field}_id")).exists():
                        fail(label, row.pk, "orphan_source_link")
                elif not source_is_resolved(sources.get(row.source_id)) or not row.source_note.strip():
                    if row.review_status == models.ScientificReviewStatus.UNREVIEWED:
                        debt.add(f"{label}:{row.pk}:unreviewed_provenance_debt")
                    else:
                        fail(label, row.pk, "unresolved_identifier_source" if model is models.BrainExternalIdentifier else "unresolved_alias_source")

        aliases = list(models.BrainAnatomicalAlias.objects.order_by("pk").select_related("source"))
        aliases.extend(models.BrainNetworkAlias.objects.order_by("pk").select_related("source"))
        counts["aliases"] = len(aliases)
        reviews["aliases"] = dict(sorted(Counter(row.review_status for row in aliases).items()))
        alias_sources = Counter("resolved" if source_is_resolved(row.source) and row.source_note.strip()
                                else "weak_only" if row.source_id else "unsourced" for row in aliases)
        provenance["aliases"] = dict(sorted(alias_sources.items()))

        identifiers = list(models.BrainExternalIdentifier.objects.order_by("pk").select_related("source"))
        counts["external_identifiers"] = len(identifiers)
        reviews["external_identifiers"] = dict(sorted(Counter(row.review_status for row in identifiers).items()))
        provenance["external_identifiers"] = dict(sorted(Counter(
            "resolved" if source_is_resolved(row.source) and row.source_note.strip() else "weak_only"
            for row in identifiers
        ).items()))

        parents = defaultdict(list)
        for link in models.BrainHierarchyLink.objects.filter(is_active=True).order_by("pk"):
            parents[link.child_id].append(link)
        for child, links in parents.items():
            if len(links) > 1:
                fail("hierarchy", child, "multiple_primary_parents")
            current, visited = child, set()
            while current in parents:
                if current in visited:
                    fail("hierarchy", child, "hierarchy_cycle")
                    break
                visited.add(current)
                current = parents[current][0].parent_id

        staging = validate_brain_staging()
        publication = "DATA BLOCKED: curated dossier required"
        from atlas.brain_controlled_publication import MANIFEST_SHA, verify_receipt
        for dataset in models.ResearchDataset.objects.filter(
                ingestion_audit__publication_manifest_sha256=MANIFEST_SHA):
            try:
                verify_receipt(dataset)
                publication = "PUBLISHED: pinned v0.9.2C manifest reconciled"
            except (CommandError, ValidationError, models.BrainAnatomicalEntity.DoesNotExist,
                    models.BrainNetwork.DoesNotExist):
                fail("publication_receipt", dataset.pk, "manifest_reconciliation_conflict")
        report = {"counts": counts, "reviews": reviews, "provenance": provenance, "errors": sorted(errors),
                  "review_debt": sorted(debt), "staging_candidates": staging["candidate_count"],
                  "staging_issues": len(staging["issues"]), "publication": publication}
        if options["as_json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            self.stdout.write("Brain atlas integrity audit: " + " ".join(f"{key}={value}" for key, value in counts.items()))
            self.stdout.write(report["publication"])
            self.stdout.write(f"reviews={json.dumps(reviews, sort_keys=True)} provenance={json.dumps(provenance, sort_keys=True)}")
            self.stdout.write(f"staging_candidates={staging['candidate_count']} staging_issues={len(staging['issues'])} review_debt={len(debt)}")
            for error in sorted(errors):
                self.stdout.write(f"FAIL {error}")
        if errors:
            raise CommandError(f"Brain audit failed with {len(errors)} integrity issue(s).")
