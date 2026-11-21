"""P11 contract tests: metadata only, rights scope, version identity, no items."""
import subprocess
import sys
import uuid

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.exceptions import ValidationError

from . import cms_content as content
from .cms_content_models import ContentRevision, ContentState
from .cms_domains import DOMAIN_SPECS, schema_data, validate_snapshot
from .assessment_publication import PROTECTED_KEYS
from .models import (AssessmentInstrument, AssessmentVersion, AssessmentLanguageForm,
                     AssessmentValidationStudy, AssessmentPsychometricEvidence,
                     AssessmentAccess, SourceReference)
from .tests_v100_p01 import SecurityFixture, BASE


class AssessmentImportOrderTests(SimpleTestCase):
    def test_assessment_domains_can_be_imported_first_or_second(self):
        for first, second in (
            ("atlas.cms_assessment_domains", "atlas.cms_domains"),
            ("atlas.cms_domains", "atlas.cms_assessment_domains"),
        ):
            with self.subTest(first=first):
                code = (
                    "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); "
                    "import django;django.setup();"
                    f"import {first};import {second};"
                    "from atlas.cms_domains import DOMAIN_SPECS;"
                    "assert len([v for v in DOMAIN_SPECS.values() if v['domain']=='assessment']) == 9"
                )
                proc = subprocess.run([sys.executable, "-c", code],
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(proc.returncode, 0, proc.stderr)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AssessmentEditorialTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = self.sign_in(self.owner)
        self.session = self.client.session["cms_session_id"]
        self.source = SourceReference.objects.create(
            title="P11 NON-SCIENTIFIC synthetic source",
            citation="Synthetic only, no authorship, medical proof or licensing authorization.",
            url="https://p11.invalid/fixture", verification_status="source_checked")
        self.family = AssessmentInstrument.objects.create(
            slug="p11-synthetic-instrument", name_en="P11 NON-SCIENTIFIC instrument")
        self.edition = AssessmentVersion.objects.create(
            instrument=self.family, key="p11-synthetic-edition", label="P11 unreviewed edition")
        self.form = AssessmentLanguageForm.objects.create(
            version=self.edition, key="p11-synthetic-fa", language="fa",
            label="P11 synthetic translation", form_kind="translation")

    def test_nine_typed_schemas_reject_protected_fields_and_preserve_identity(self):
        from .cms_assessment_domains import FIELDS
        self.assertEqual(len(FIELDS), 9)
        self.assertEqual({kind for kind, spec in DOMAIN_SPECS.items()
                          if spec["domain"] == "assessment"}, set(FIELDS))
        for kind, (model, label, writable, identities) in FIELDS.items():
            with self.subTest(kind=kind):
                self.assertIs(content.kind_entry(kind)[0], model)
                schema = schema_data(kind)
                names = {field["name"] for field in schema["fields"]}
                self.assertTrue(names.isdisjoint(PROTECTED_KEYS))
                self.assertNotIn("review_status", writable)
                self.assertNotIn("is_active", writable)
                self.assertNotIn("seed_managed", writable)
                self.assertTrue(all(next(f for f in schema["fields"] if f["name"] == key)["create_only"]
                                    for key in identities))
        schema = schema_data("assessment-instrument")
        self.assertNotIn("normalized_name", {f["name"] for f in schema["fields"]
                                              if not f.get("readonly_reason")})

    def test_metadata_draft_preview_and_write_does_not_mutate_canonical(self):
        kind = "assessment-instrument"
        before = content.canonical_snapshot(kind, self.family)
        state = ContentState.objects.create(
            kind=kind, canonical_pk=self.family.pk, legacy_origin=True,
            canonical_digest=content.digest(before), publication="current")
        payload = content.editable_snapshot(kind, self.family)
        revision = ContentRevision.objects.create(
            state=state, sequence=0, base_version=0, base_digest=state.canonical_digest,
            payload=payload, payload_digest=content.digest(payload),
            dependency_digest=content.dependencies(kind, self.family), status="legacy")
        state.current_revision = revision
        state.save(update_fields=("current_revision",))
        state, inspected = content.inspect_proposal(
            self.owner.pk, self.session, kind, str(state.pk), state.version, "preview")
        self.assertTrue(inspected["valid"])
        self.assertFalse(inspected["publication_available"])
        updated = content.propose(
            self.owner.pk, self.session, kind, str(state.pk),
            {"construct_overview": "P11 NON-SCIENTIFIC private candidate"},
            state.version, state.canonical_digest, "CONTENT_UPDATE", uuid.uuid4())
        self.assertEqual(updated.current_revision.status, "draft")
        self.family.refresh_from_db()
        self.assertEqual(content.canonical_snapshot(kind, self.family), before)

    def test_translation_status_does_not_infer_license_or_validity(self):
        self.assertEqual(self.form.authorization_status, "unknown")
        with self.assertRaises(ValidationError):
            validate_snapshot("assessment-language-form", {
                "version": self.edition.pk, "key": "p11-proposed-fa",
                "language": "fa", "label": "NON-SCIENTIFIC proposed form",
                "form_kind": "translation", "authorization_status": "authorized",
            })
        with self.assertRaises(ValidationError):
            validate_snapshot("assessment-access", {
                "key": "p11-false-licensing", "version": self.edition.pk,
                "language_form": self.form.pk, "material_type": "translation",
                "use": "redistribution", "source": self.source.pk,
                "source_note": "Synthetic locator", "terms": "Synthetic",
                "license_status": "explicit_permission",
            })
        with self.assertRaises(ValidationError):
            validate_snapshot("assessment-access", {
                "key": "p11-false-licensing", "version": self.edition.pk,
                "language_form": self.form.pk, "material_type": "translation",
                "use": "redistribution", "source": self.source.pk,
                "source_note": "Synthetic locator", "terms": "Synthetic",
                "verified_on": "2026-10-31",
                "license_status": "explicit_permission",
            })

    def test_no_item_scoring_or_diagnostic_material_can_be_proposed(self):
        safe = {"slug": "p11-proposed-unreviewed", "name_en": "P11 NON-SCIENTIFIC"}
        self.assertEqual(validate_snapshot("assessment-instrument", safe)["slug"], safe["slug"])
        for field in PROTECTED_KEYS:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate_snapshot("assessment-instrument", {**safe, field: ["PRIVATE"]})
        self.assertNotIn("items", content.editable_snapshot("assessment-instrument", self.family))
        self.assertEqual(self.family.review_status, "unreviewed")

    def test_scoped_source_review_and_private_route_are_not_publication(self):
        response = self.client.get(BASE + "content/schema/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len([x for x in response.json()["kinds"]
                              if x["domain"] == "assessment"]), 9)
        scoped = self.user("p11-scoped-view", staff=True,
                           caps=("cms_enter", "cms_assessment_view"))
        client = self.sign_in(scoped)
        self.assertEqual(client.get(BASE + "content/schema/").status_code, 200)
        self.assertFalse(any(x["domain"] == "brain" for x in
                             client.get(BASE + "content/schema/").json()["kinds"]))
        self.assertEqual(client.get(BASE + "content/assessment-version/").status_code, 200)
        self.assertEqual(client.post(BASE + "content/assessment-instrument/",
                                     data={"payload": {}}, content_type="application/json").status_code, 403)
