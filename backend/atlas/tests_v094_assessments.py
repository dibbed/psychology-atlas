"""Curated publication integration plus explicitly synthetic negative fixtures."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import date, timedelta
import io
import json
from threading import Barrier
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import close_old_connections, connection
from django.db.models.query import QuerySet
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from . import models as m
from .assessment_publication import DOSSIER, MODELS, approved_artifacts, canonical_counts, ingest_document, parse_document, publish, validate_staging
from .management.commands.audit_assessments import audit


class CuratedFixture:
    @classmethod
    def setUpTestData(cls):
        publish(apply=True)
        cls.instrument = m.AssessmentInstrument.objects.get(slug="patient-health-questionnaire")
        cls.version = cls.instrument.versions.get(key="phq-9")
        cls.form = cls.version.language_forms.get(language="fa")
        cls.study = cls.version.validation_studies.get(sample_size=185)
        cls.finding = cls.study.findings.get()
        cls.source = cls.study.source

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    @classmethod
    def synthetic_instrument(cls, slug, name, **kwargs):
        obj = m.AssessmentInstrument.objects.create(slug=slug, name_en=name, **kwargs)
        m.AssessmentSource.objects.create(instrument=obj, source=cls.source, note="Synthetic identity, test only.")
        obj.review_status = "reviewed"
        obj.save()
        return obj


class AssessmentIdentityTests(CuratedFixture, TestCase):
    def test_family_and_version_remain_separate(self):
        family = m.AssessmentInstrument.objects.get(slug="beck-depression-inventory")
        self.assertEqual(family.versions.get().key, "bdi-ii-1996")
        self.assertEqual(family.aliases.get(version=None).text, "BDI")
        self.assertEqual(family.aliases.get(version__isnull=False).text, "BDI-II")
        self.assertFalse(family.versions.filter(key="bdi-1961").exists())

    def test_normalized_family_identity_collision(self):
        with self.assertRaises(ValidationError):
            m.AssessmentInstrument.objects.create(slug="synthetic-collision", name_en="PATIENT HEALTH QUESTIONNAIRE")

    def test_stable_instrument_slug(self):
        self.instrument.slug = "synthetic-replacement"
        self.instrument.review_status = "unreviewed"
        with self.assertRaises(ValidationError):
            self.instrument.save()

    def test_case_insensitive_version_collision(self):
        with self.assertRaises(ValidationError):
            m.AssessmentVersion.objects.create(instrument=self.instrument, key="PHQ-9", label="Synthetic collision")

    def test_short_and_full_forms_do_not_overwrite(self):
        family = m.AssessmentInstrument.objects.get(slug="depression-anxiety-stress-scales")
        full, short = family.versions.get(key="dass-42"), family.versions.get(key="dass-21")
        self.assertNotEqual(full.pk, short.pk)
        self.assertEqual(short.derived_from_id, full.pk)
        self.assertIsNone(short.publication_year)

    def test_unknown_version_not_assigned_latest(self):
        unknown = m.AssessmentVersion.objects.create(instrument=self.instrument, key="synthetic-unknown", label="Synthetic unresolved edition")
        self.assertEqual(unknown.form_kind, "unknown")
        self.assertIsNone(unknown.publication_year)

    def test_derivation_rejects_wrong_family(self):
        other = m.AssessmentVersion.objects.get(key="gad-7")
        with self.assertRaises(ValidationError):
            m.AssessmentVersion.objects.create(instrument=self.instrument, key="synthetic-short", label="Test only", derived_from=other)

    def test_derivation_rejects_self(self):
        obj = m.AssessmentVersion.objects.create(instrument=self.instrument, key="synthetic-self", label="Test only")
        obj.derived_from = obj
        with self.assertRaises(ValidationError):
            obj.save()

    def test_multiple_persian_forms_can_coexist(self):
        other = m.AssessmentLanguageForm.objects.create(version=self.version, key="synthetic-other-translation", language="fa", label="Test-only translation", form_kind="translation")
        self.assertNotEqual(other.pk, self.form.pk)
        self.assertEqual(other.authorization_status, "unknown")

    def test_display_translation_is_not_language_validation(self):
        bdi = m.AssessmentInstrument.objects.get(slug="beck-depression-inventory")
        self.assertTrue(bdi.name_fa)
        self.assertFalse(m.AssessmentLanguageForm.objects.filter(version__instrument=bdi, language="fa").exists())
        self.assertNotIn("is_validated", {field.name for field in m.AssessmentLanguageForm._meta.fields})

    def test_translation_and_adaptation_are_distinct(self):
        adapted = m.AssessmentLanguageForm.objects.create(version=self.version, key="synthetic-adaptation", language="fa", label="Test-only adaptation", form_kind="adaptation")
        self.assertEqual(self.form.form_kind, "translation")
        self.assertEqual(adapted.form_kind, "adaptation")
        self.assertFalse(adapted.validation_studies.exists())

    def test_authorization_requires_separate_provenance(self):
        with self.assertRaises(ValidationError):
            m.AssessmentLanguageForm.objects.create(version=self.version, key="synthetic-authorized", language="fa", label="Test only", form_kind="translation", authorization_status="authorized")

    def test_alias_collision_within_owner(self):
        with self.assertRaises(ValidationError):
            m.AssessmentAlias.objects.create(instrument=self.instrument, text="phq", language="en", alias_type="acronym", source=self.source, source_note="Synthetic test only")

    def test_ambiguous_acronym_remains_multiple_families(self):
        other = self.synthetic_instrument("synthetic-ambiguous", "Synthetic ambiguous family")
        m.AssessmentAlias.objects.create(instrument=other, text="PHQ", language="en", alias_type="acronym", source=self.source, source_note="Synthetic test only", review_status="reviewed")
        response = self.client.get("/api/assessments/?q=PHQ")
        self.assertEqual(response.data["count"], 2)
        self.assertTrue(any("ambiguous_alias" in warning for warning in audit()["warnings"]))

    def test_alias_version_must_belong_to_family(self):
        with self.assertRaises(ValidationError):
            m.AssessmentAlias.objects.create(instrument=self.instrument, version=m.AssessmentVersion.objects.get(key="gad-7"), text="Synthetic", language="en", alias_type="name", source=self.source, source_note="Test only")

    def test_bulk_writes_and_deletion_are_guarded(self):
        for operation in (lambda: m.AssessmentInstrument.objects.update(name_en="Synthetic replacement"),
                          lambda: m.AssessmentInstrument.objects.bulk_create([]),
                          lambda: m.AssessmentInstrument.objects.bulk_update([self.instrument], ["name_en"])):
            with self.assertRaises(ValidationError):
                operation()
        with self.assertRaises(ProtectedError):
            self.instrument.delete()
        with self.assertRaises(ProtectedError):
            self.instrument.source_links.all().delete()


class AssessmentEvidenceRightsTests(CuratedFixture, TestCase):
    def test_pilot_and_main_precision_and_context(self):
        studies = list(self.version.validation_studies.order_by("sample_size"))
        self.assertEqual([study.sample_size for study in studies], [46, 185])
        self.assertEqual([study.findings.get().value_text for study in studies], ["0.86", "0.873"])
        self.assertEqual(studies[0].language_form_id, studies[1].language_form_id)
        self.assertEqual(studies[0].source_id, self.source.pk)
        self.assertIn("not separately specified", studies[0].population)

    def test_evidence_has_no_universal_instrument_value(self):
        fields = {field.name for field in m.AssessmentInstrument._meta.fields}
        self.assertFalse(fields & {"reliability", "validity", "cutoff", "norms", "score"})

    def test_study_mismatched_version_rejected(self):
        self.study.version = m.AssessmentVersion.objects.get(key="gad-7")
        with self.assertRaises(ValidationError):
            self.study.save()

    def test_missing_population_rejected(self):
        self.study.population = " "
        self.study.review_status = "unreviewed"
        with self.assertRaises(ValidationError):
            self.study.save()

    def test_missing_finding_context_rejected(self):
        self.finding.method = " "
        self.finding.review_status = "unreviewed"
        with self.assertRaises(ValidationError):
            self.finding.save()

    def test_finding_requires_an_existing_study(self):
        with self.assertRaises(ValidationError):
            m.AssessmentPsychometricEvidence.objects.create(key="synthetic-orphan", study_id=999999, measurement_property="reliability", statistic="Test only", method="Test only", finding="Test only", limitations="Test only", extraction_locator="Test only")

    def test_review_requires_source(self):
        with self.assertRaises(ValidationError):
            m.AssessmentInstrument.objects.create(slug="synthetic-unsourced", name_en="Synthetic unsourced", review_status="reviewed")

    def test_expired_access_not_public(self):
        access = self.form.access_records.get()
        access.review_status = "unreviewed"
        access.save(update_fields=["review_status"])
        access.verified_on = date.today() - timedelta(days=10)
        access.expires_on = date.today() - timedelta(days=1)
        access.save()
        access.review_status = "reviewed"
        access.save(update_fields=["review_status"])
        detail = self.client.get("/api/assessments/" + self.instrument.slug + "/")
        rows = detail.data["versions"]["results"][0]["access"]["results"]
        self.assertFalse(any(row["key"] == access.key for row in rows))

    def test_nonfinite_numerical_value_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity", "unverified"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                m.AssessmentPsychometricEvidence.objects.create(key="synthetic-invalid", study=self.study, measurement_property="reliability", statistic="Synthetic coefficient", method="Test only", value_text=value, finding="Test only", limitations="Test only", extraction_locator="Synthetic paragraph")

    def test_deferred_cutoff_property_rejected(self):
        with self.assertRaises(ValidationError):
            m.AssessmentPsychometricEvidence.objects.create(key="synthetic-cutoff", study=self.study, measurement_property="cutoff", statistic="Test", method="Test", value_text="10", finding="Test", limitations="Test", extraction_locator="Test")

    def test_reviewed_claim_edits_require_rereview(self):
        self.finding.value_text = "0.90"
        with self.assertRaises(ValidationError):
            self.finding.save(update_fields=["value_text"])

    def test_partial_save_validates_only_persisted_fields(self):
        self.finding.value_text = "NaN"
        self.finding.is_active = False
        self.finding.save(update_fields=["is_active"])
        self.finding.refresh_from_db()
        self.assertEqual(self.finding.value_text, "0.873")
        self.assertFalse(self.finding.is_active)

    def test_checked_descendants_protect_study_context(self):
        self.study.review_status = "unreviewed"
        self.study.save(update_fields=["review_status"])
        self.study.population = "Synthetic different population"
        with self.assertRaises(ValidationError):
            self.study.save()

    def test_source_mutation_preserves_checked_findings(self):
        self.study.review_status = "unreviewed"
        self.study.save(update_fields=["review_status"])
        self.source.title = "Synthetic altered source"
        with self.assertRaises(ValidationError):
            self.source.save(update_fields=["title"])

    def test_stale_source_object_cannot_grant_review(self):
        cached = m.SourceReference.objects.create(title="Synthetic cached source", citation="Synthetic test only", url="https://example.org/synthetic", verification_status="source_checked")
        changed = m.SourceReference.objects.get(pk=cached.pk)
        changed.verification_status = "unverified"
        changed.save()
        with self.assertRaises(ValidationError):
            m.AssessmentAlias.objects.create(instrument=self.instrument, text="Synthetic stale alias", language="en", alias_type="name", source=cached, source_note="Test only", review_status="reviewed")

    def test_stale_parent_object_cannot_grant_review(self):
        cached = self.synthetic_instrument("synthetic-stale-parent", "Synthetic stale parent")
        changed = m.AssessmentInstrument.objects.get(pk=cached.pk)
        changed.is_active = False
        changed.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            m.AssessmentVersion.objects.create(instrument=cached, key="synthetic-stale-version", label="Test only")

    def test_source_link_cannot_be_reassigned_or_deleted(self):
        link = self.version.source_links.first()
        link.note = "Synthetic replacement"
        with self.assertRaises(ValidationError):
            link.save()
        with self.assertRaises(ProtectedError):
            link.delete()

    def test_cached_unreviewed_owner_cannot_modify_checked_provenance(self):
        cached = m.AssessmentInstrument.objects.create(slug="synthetic-cached-owner", name_en="Synthetic cached owner")
        m.AssessmentSource.objects.create(instrument=cached, source=self.source, note="Synthetic test identity")
        reviewed = m.AssessmentInstrument.objects.get(pk=cached.pk)
        reviewed.review_status = "reviewed"
        reviewed.save()
        link = m.AssessmentSource.objects.get(instrument=cached)
        link.instrument = cached
        link.note = "Synthetic altered provenance"
        with self.assertRaises(ValidationError):
            link.save()

    def test_rights_default_unknown_and_persian_validation_not_authorization(self):
        self.assertEqual(self.form.authorization_status, "unknown")
        access = self.form.access_records.get()
        self.assertEqual(access.license_status, "unknown")
        self.assertEqual(access.availability, "unknown")
        self.assertEqual(self.form.validation_studies.count(), 2)

    def test_dass_rights_do_not_cover_manual_or_translations(self):
        access = m.AssessmentAccess.objects.get(key="dass21-access")
        self.assertEqual(access.license_status, "public_domain")
        self.assertEqual(access.material_type, "questionnaire")
        self.assertEqual(access.language_form.language, "en")
        self.assertIn("manual and translations are separate", access.terms)

    def test_unknown_rights_never_become_free(self):
        self.assertEqual(m.AssessmentAccess.objects.filter(license_status="unknown").count(), 3)
        self.assertFalse(m.AssessmentAccess.objects.filter(license_status="free").exists())

    def test_unverified_translation_redistribution_rejected(self):
        with self.assertRaises(ValidationError):
            m.AssessmentAccess.objects.create(key="synthetic-fa-grant", version=self.version, language_form=self.form, material_type="translation", use="redistribution", license_status="public_domain", terms="Synthetic test-only claimed grant", source=self.source, source_note="Test only", verified_on=date.today())

    def test_invalid_license_and_dates_rejected(self):
        access = self.form.access_records.get()
        access.review_status = "unreviewed"
        access.license_status = "free"
        with self.assertRaises(ValidationError):
            access.save()
        access.license_status = "unknown"
        access.expires_on = access.verified_on - timedelta(days=1)
        with self.assertRaises(ValidationError):
            access.save()


class AssessmentPublicationTests(TestCase):
    def test_dry_run_has_zero_net_writes(self):
        before = (canonical_counts(), m.SourceReference.objects.count(), m.ResearchDataset.objects.count())
        self.assertEqual(publish()["status"], "DRY_RUN")
        self.assertEqual(before, (canonical_counts(), m.SourceReference.objects.count(), m.ResearchDataset.objects.count()))

    def test_apply_repeat_preserves_all_timestamps_and_pointers(self):
        first = publish(apply=True)
        before = {key: list(model.objects.order_by("pk").values()) for key,model in MODELS.items()}
        archive = list(m.ResearchRecord.objects.order_by("pk").values())
        second = publish(apply=True)
        self.assertEqual(first["canonical_writes"], 65)
        self.assertEqual(second["canonical_writes"], 0)
        self.assertEqual(second["status"], "ALREADY_PUBLISHED")
        self.assertEqual(before, {key: list(model.objects.order_by("pk").values()) for key,model in MODELS.items()})
        self.assertEqual(archive, list(m.ResearchRecord.objects.order_by("pk").values()))

    def test_archive_idempotency_and_validation_have_no_canonical_writes(self):
        dataset, created = ingest_document(DOSSIER.read_text(encoding="utf-8"), DOSSIER.name)
        self.assertTrue(created)
        self.assertEqual(validate_staging(dataset)["status"], "VALID")
        self.assertFalse(ingest_document(DOSSIER.read_text(encoding="utf-8"), DOSSIER.name)[1])
        self.assertEqual(sum(canonical_counts().values()), 0)
        self.assertEqual(m.SourceReference.objects.count(), 0)

    def test_generic_research_strings_are_rejected(self):
        with self.assertRaises(CommandError):
            parse_document(json.dumps({"measures": ["PHQ-9"]}))

    def test_malformed_metadata_shapes_rejected_before_archive_writes(self):
        for field, value in (("data", None), ("data", []), ("sources", None), ("sources", ["synthetic source"])):
            document, _ = approved_artifacts()
            document["records"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(CommandError):
                ingest_document(json.dumps(document), "synthetic-malformed.json")
        self.assertEqual(m.ResearchDataset.objects.count(), 0)

    def test_protected_content_rejected_even_in_staging(self):
        document, _ = approved_artifacts()
        for key in ("items", "item_bank", "questionnaire_text", "scoring_key", "manual_text", "official_translation_text"):
            corrupted = copy.deepcopy(document)
            corrupted["records"][0]["extra"] = {key: "Synthetic protected sentinel"}
            with self.subTest(key=key), self.assertRaises(CommandError):
                ingest_document(json.dumps(corrupted), "test-only.json")
        self.assertEqual(m.ResearchDataset.objects.count(), 0)

    def test_unsupported_fields_stay_staging_only(self):
        document, _ = approved_artifacts()
        document["records"][10]["data"]["reliability"] = "0.90"
        dataset, _ = ingest_document(json.dumps(document), "test-only.json")
        self.assertEqual(validate_staging(dataset)["status"], "BLOCKED")
        self.assertEqual(sum(canonical_counts().values()), 0)
        self.assertIn("reliability", dataset.raw_document["records"][10]["data"])

    def test_conflicting_family_is_not_overwritten(self):
        m.AssessmentInstrument.objects.create(slug="patient-health-questionnaire", name_en="Synthetic conflicting identity")
        with self.assertRaises(CommandError):
            publish(apply=True)
        self.assertEqual(m.SourceReference.objects.count(), 0)
        self.assertEqual(m.ResearchDataset.objects.count(), 0)
        self.assertEqual(m.AssessmentInstrument.objects.get().name_en, "Synthetic conflicting identity")

    def test_conflicting_doi_identity_blocks_publication(self):
        document, _ = approved_artifacts()
        fields = dict(document["records"][0]["data"], title="Synthetic conflicting title")
        m.SourceReference.objects.create(**fields, verification_status="source_checked")
        with self.assertRaises(CommandError):
            publish(apply=True)
        self.assertEqual(sum(canonical_counts().values()), 0)

    def test_ambiguous_source_identity_blocks_publication(self):
        document, _ = approved_artifacts()
        for _ in range(2):
            m.SourceReference.objects.create(**document["records"][0]["data"], verification_status="source_checked")
        with self.assertRaises(CommandError):
            publish(apply=True)

    def test_exact_existing_source_is_reused(self):
        document, _ = approved_artifacts()
        source = m.SourceReference.objects.create(**document["records"][0]["data"], verification_status="source_checked")
        publish(apply=True)
        self.assertEqual(m.SourceReference.objects.count(), 10)
        self.assertTrue(m.AssessmentSource.objects.filter(source=source).exists())

    def test_failure_mid_publication_rolls_back_every_boundary(self):
        with patch.object(m.AssessmentPsychometricEvidence, "save", side_effect=RuntimeError("Synthetic failure")):
            with self.assertRaises(RuntimeError):
                publish(apply=True)
        self.assertEqual(sum(canonical_counts().values()), 0)
        self.assertEqual(m.SourceReference.objects.count(), 0)
        self.assertEqual(m.ResearchRecord.objects.count(), 0)

    def test_forged_pointer_fails_repeat(self):
        publish(apply=True)
        record = m.ResearchRecord.objects.filter(promoted_model="atlas.AssessmentInstrument").first()
        record.promoted_pk = 999999
        record.save()
        with self.assertRaises(CommandError):
            publish(apply=True)
        self.assertTrue(any("pointer mismatch" in issue for issue in audit()["issues"]))

    def test_archive_payload_edit_is_detected(self):
        publish(apply=True)
        record = m.ResearchRecord.objects.first()
        record.payload = {"synthetic": "tampered"}
        record.save()
        with self.assertRaises(CommandError):
            publish(apply=True)

    def test_archive_digest_corruption_is_audited(self):
        publish(apply=True)
        dataset = m.ResearchDataset.objects.get()
        dataset.source_sha256 = "f" * 64
        dataset.save()
        self.assertTrue(any("archive changed" in issue.lower() for issue in audit()["issues"]))

    def test_deactivation_is_not_silently_reversed(self):
        publish(apply=True)
        obj = m.AssessmentInstrument.objects.first()
        obj.is_active = False
        obj.save(update_fields=["is_active"])
        with self.assertRaises(CommandError):
            publish(apply=True)
        obj.refresh_from_db()
        self.assertFalse(obj.is_active)

    def test_exact_manifest_pins_required(self):
        with patch("atlas.assessment_publication.DOSSIER_SHA", "0" * 64), self.assertRaises(CommandError):
            publish(apply=True)

    def test_publication_audit_deterministic_and_clean(self):
        publish(apply=True)
        first, second = io.StringIO(), io.StringIO()
        call_command("audit_assessments", stdout=first)
        call_command("audit_assessments", stdout=second)
        self.assertEqual(first.getvalue(), second.getvalue())
        self.assertEqual(json.loads(first.getvalue())["source_count"], 10)


class AssessmentAPITests(CuratedFixture, TestCase):
    def test_real_curated_list_detail_and_context(self):
        response = self.client.get("/api/assessments/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 4)
        names = [row["name_en"] for row in response.data["results"]]
        self.assertEqual(names, sorted(names))
        detail = self.client.get("/api/assessments/patient-health-questionnaire/")
        version = detail.data["versions"]["results"][0]
        studies = version["validation_studies"]["results"]
        self.assertEqual({row["sample_size"] for row in studies}, {46, 185})
        self.assertTrue(all(row["language"] == "fa" and row["source"]["doi"] == self.source.doi for row in studies))
        self.assertEqual({row["findings"]["results"][0]["value_text"] for row in studies}, {"0.86", "0.873"})

    def test_english_persian_variants_and_acronym_search(self):
        for q, count in (("Patient Health", 1), ("پرسش‌نامه", 2), ("بك", 1), ("PHQ-9", 1), ("BDI", 1), ("BDI-II", 1), ("unknown-synthetic", 0)):
            with self.subTest(q=q):
                response = self.client.get("/api/assessments/", {"q": q})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["count"], count)

    def test_filters_only_reviewed_version_form_rights(self):
        for params,count in (({"language": "fa"}, 1), ({"construct": "depression"}, 2), ({"intended_use": "screening"}, 2),
                             ({"form_kind": "short"}, 1), ({"access": "public_access"}, 1), ({"license": "restricted"}, 1),
                             ({"license": "unknown"}, 2), ({"construct": "depression", "language": "fa"}, 1)):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/assessments/", params).data["count"], count)

    def test_invalid_filters_and_oversized_query(self):
        for params in ({"review_status": "unreviewed"}, {"license": "free"}, {"access": "free"}, {"language": "zz"},
                       {"form_kind": "invented"}, {"construct": "invented"}, {"intended_use": "diagnoses"}, {"q": "x" * 256}):
            with self.subTest(params=params):
                self.assertEqual(self.client.get("/api/assessments/", params).status_code, 400)
        self.assertEqual(self.client.get("/api/assessments/?q=one&q=two").status_code, 400)

    def test_language_rights_filters_cannot_borrow_another_forms_permission(self):
        english = self.version.language_forms.get(language="en")
        m.AssessmentAccess.objects.create(key="synthetic-english-grant", version=self.version, language_form=english,
            material_type="questionnaire", use="redistribution", availability="public_access", license_status="public_domain",
            terms="Synthetic English-only test grant", source=self.source, source_note="Synthetic test only",
            verified_on=date.today(), review_status="reviewed")
        response = self.client.get("/api/assessments/", {"language": "fa", "license": "public_domain"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(self.client.get("/api/assessments/", {"language": "fa", "license": "unknown"}).data["count"], 1)

    def test_pagination_and_missing_slug(self):
        response = self.client.get("/api/assessments/?page_size=2")
        self.assertEqual(len(response.data["results"]), 2)
        self.assertTrue(response.data["next"])
        self.assertEqual(self.client.get("/api/assessments/?page=999").status_code, 404)
        self.assertEqual(self.client.get("/api/assessments/does-not-exist/").status_code, 404)

    def test_inactive_and_unreviewed_instrument_404(self):
        for field,value in (("is_active", False), ("review_status", "unreviewed")):
            self.instrument.is_active, self.instrument.review_status = True, "reviewed"
            setattr(self.instrument, field, value)
            self.instrument.save(update_fields=[field])
            self.assertEqual(self.client.get("/api/assessments/" + self.instrument.slug + "/").status_code, 404)

    def test_inactive_version_hides_forms_findings_and_alias_search(self):
        self.version.is_active = False
        self.version.save(update_fields=["is_active"])
        detail = self.client.get("/api/assessments/" + self.instrument.slug + "/")
        self.assertEqual(detail.data["versions"]["results"], [])
        self.assertEqual(self.client.get("/api/assessments/?q=PHQ-9").data["count"], 0)
        self.assertEqual(self.client.get("/api/assessments/?language=fa").status_code, 400)

    def test_inactive_form_hides_studies_and_rights(self):
        self.form.is_active = False
        self.form.save(update_fields=["is_active"])
        detail = self.client.get("/api/assessments/" + self.instrument.slug + "/")
        version = detail.data["versions"]["results"][0]
        self.assertEqual(version["validation_studies"]["results"], [])
        self.assertNotIn(self.form.key, [row["key"] for row in version["language_forms"]["results"]])
        self.assertFalse(any(row["language_form"] == self.form.key for row in version["access"]["results"]))

    def test_invalid_study_source_fails_closed_and_audit_detects(self):
        # Deliberately bypass model validation to represent a damaged legacy/admin database.
        QuerySet.update(m.SourceReference.objects.filter(pk=self.source.pk), verification_status="unverified")
        detail = self.client.get("/api/assessments/" + self.instrument.slug + "/")
        version = detail.data["versions"]["results"][0]
        self.assertEqual(version["validation_studies"]["results"], [])
        self.assertTrue(audit()["issues"])

    def test_protected_content_and_write_endpoints_absent(self):
        detail = self.client.get("/api/assessments/" + self.instrument.slug + "/")
        from .assessment_publication import protected_paths
        self.assertEqual(protected_paths(detail.data), [])
        self.assertEqual(self.client.post("/api/assessments/", {}).status_code, 405)
        self.assertEqual(self.client.post("/api/assessments/" + self.instrument.slug + "/", {}).status_code, 405)
        self.assertEqual(self.client.get("/api/assessments/" + self.instrument.slug + "/score/").status_code, 404)

    def test_observed_query_counts_do_not_grow_with_more_instruments(self):
        def count(url):
            with CaptureQueriesContext(connection) as captured:
                response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            return len(captured)
        baseline = count("/api/assessments/")
        for index in range(6):
            self.synthetic_instrument(f"synthetic-query-{index}", f"Synthetic query family {index}")
        self.assertEqual(count("/api/assessments/"), baseline)
        self.assertEqual(baseline, 7)
        self.assertEqual(count("/api/assessments/" + self.instrument.slug + "/"), 13)

    def test_nested_aliases_are_bounded_and_truncation_explicit(self):
        for index in range(32):
            m.AssessmentAlias.objects.create(instrument=self.instrument, text=f"Synthetic alias {index:02d}", language="en", alias_type="name", source=self.source, source_note="Synthetic test only", review_status="reviewed")
        detail = self.client.get("/api/assessments/" + self.instrument.slug + "/")
        self.assertEqual(len(detail.data["aliases"]["results"]), 30)
        self.assertTrue(detail.data["aliases"]["truncated"])


class AssessmentRelationTests(CuratedFixture, TestCase):
    def relation(self, predicate, **kwargs):
        obj = m.AssessmentRelation.objects.create(key="synthetic-relation", version=self.version, predicate=predicate,
            claim="Synthetic supported claim, test only", context="Synthetic study context", limitations="Screening is not diagnosis", **kwargs)
        m.AssessmentSource.objects.create(relation=obj, source=self.source, note="Synthetic specific predicate evidence")
        obj.review_status = "reviewed"
        obj.save()
        return obj

    def test_screens_for_preserves_semantics_and_provenance(self):
        category = m.Category.objects.create(slug="synthetic-category", name_en="Synthetic category")
        disorder = m.Disorder.objects.create(slug="synthetic-disorder", name_en="Synthetic disorder", category=category)
        self.relation("screens_for", disorder=disorder)
        detail = self.client.get("/api/assessments/" + self.instrument.slug + "/")
        relation = detail.data["versions"]["results"][0]["relations"]["results"][0]
        self.assertEqual(relation["predicate"], "screens_for")
        self.assertTrue(relation["sources"]["results"])
        self.assertIn("not diagnosis", relation["limitations"])
        disorder.is_active = False
        disorder.save(update_fields=["is_active"])
        detail = self.client.get("/api/assessments/" + self.instrument.slug + "/")
        self.assertEqual(detail.data["versions"]["results"][0]["relations"]["results"], [])

    def test_predicate_endpoint_rules_and_diagnoses_rejected(self):
        symptom = m.Symptom.objects.create(slug="synthetic-symptom", name_en="Synthetic symptom")
        for predicate in ("measures", "research_measure_of", "diagnostic_support_for", "diagnoses"):
            with self.subTest(predicate=predicate), self.assertRaises(ValidationError):
                self.relation(predicate, symptom=symptom)

    def test_symptom_without_active_field_uses_existing_contract(self):
        symptom = m.Symptom.objects.create(slug="synthetic-symptom", name_en="Synthetic symptom")
        self.relation("screens_for", symptom=symptom)
        detail = self.client.get("/api/assessments/" + self.instrument.slug + "/")
        self.assertEqual(detail.data["versions"]["results"][0]["relations"]["results"][0]["target"]["type"], "symptom")


class AssessmentConcurrentPublicationTests(TransactionTestCase):
    def test_postgres_concurrent_publication_has_one_effect(self):
        if connection.vendor != "postgresql":
            self.skipTest("Requires PostgreSQL advisory transaction locks.")
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=20)
                return publish(apply=True)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: worker(), range(2)))
        self.assertEqual(sorted(row["status"] for row in results), ["ALREADY_PUBLISHED", "PUBLISHED"])
        self.assertEqual(sum(row["canonical_writes"] for row in results), 65)
        self.assertEqual(m.AssessmentInstrument.objects.count(), 4)
        self.assertEqual(m.ResearchDataset.objects.count(), 1)
