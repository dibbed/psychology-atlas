"""P10 Brain editorial contracts; synthetic fixtures only; no canonical publisher."""
import importlib
import subprocess
import sys
import uuid

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.exceptions import ValidationError

from . import cms_content as content
from .cms_content_models import ContentRevision, ContentState
from .cms_domains import DOMAIN_SPECS, schema_data, validate_snapshot
from .models import BrainAnatomicalEntity, BrainHierarchyLink
from .tests_v100_p01 import SecurityFixture, BASE


class BrainImportOrderTests(SimpleTestCase):
    def test_brain_spec_import_has_no_cycle(self):
        for first, second in (("atlas.cms_brain_domains", "atlas.cms_domains"),
                              ("atlas.cms_domains", "atlas.cms_brain_domains")):
            with self.subTest(first=first):
                code = ("import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings'); "
                        "import django; django.setup(); "
                        f"import {first}; import {second}; "
                        "from atlas.cms_domains import DOMAIN_SPECS; "
                        "assert len([x for x in DOMAIN_SPECS.values() if x['domain']=='brain']) == 13")
                proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
                self.assertEqual(proc.returncode, 0, proc.stderr)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BrainCMSContracts(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.client = self.sign_in(self.owner)
        self.session = self.client.session["cms_session_id"]
        self.root = BrainAnatomicalEntity.objects.create(
            slug="p10-synthetic-root", name_en="P10 NON-SCIENTIFIC root",
            kind="whole_brain", laterality="bilateral")
        self.left = BrainAnatomicalEntity.objects.create(
            slug="p10-synthetic-left", name_en="P10 NON-SCIENTIFIC left",
            kind="cortical_region", laterality="left")
        self.right = BrainAnatomicalEntity.objects.create(
            slug="p10-synthetic-right", name_en="P10 NON-SCIENTIFIC right",
            kind="cortical_region", laterality="right")
        self.link = BrainHierarchyLink.objects.create(
            child=self.left, parent=self.root, source_version="P10 synthetic fixture")

    def test_all_thirteen_models_and_immutable_operators(self):
        from .cms_brain_domains import FIELDS
        self.assertEqual(len(FIELDS), 13)
        self.assertEqual({kind for kind, spec in DOMAIN_SPECS.items() if spec["domain"] == "brain"}, set(FIELDS))
        for kind, (model, label, fields, identities) in FIELDS.items():
            with self.subTest(kind=kind):
                self.assertIs(content.kind_entry(kind)[0], model)
                schema = schema_data(kind)
                self.assertTrue(all(next(f for f in schema["fields"] if f["name"] == ident)["create_only"]
                                    for ident in identities))
                self.assertTrue(all(next(f for f in schema["fields"] if f["name"] == key)["readonly_reason"]
                                    for key in ("review_status",) if key in
                                    {f["name"] for f in schema["fields"]}))
                self.assertEqual(schema["domain"], "brain")

    def test_private_tree_before_after_and_capability_scope(self):
        path = BASE + "content/brain/tree/"
        result = self.client.get(path)
        self.assertEqual(result.status_code, 200, result.content[:300])
        rows = {x["id"]: x for x in result.json()["results"]}
        self.assertEqual(rows[self.left.pk]["parent_id"], self.root.pk)
        self.assertFalse(result.json()["publication_available"])
        impact = self.client.get(path, {"child": self.left.pk, "parent": self.right.pk})
        self.assertEqual(impact.status_code, 200, impact.content[:300])
        self.assertEqual(impact.json()["before"]["parent_id"], self.root.pk)
        self.assertEqual(impact.json()["after"]["parent_id"], self.right.pk)
        self.assertFalse(impact.json()["after"]["valid"])
        self.assertIn("LATERALITY_CONFLICT", impact.json()["after"]["blockers"])
        self.link.refresh_from_db()
        self.assertEqual(self.link.parent_id, self.root.pk)
        self.assertIn("CYCLE", self.client.get(path, {"child": self.root.pk, "parent": self.left.pk}).json()
                      ["after"]["blockers"])
        scoped = self.user("p10-no-brain", staff=True, caps=("cms_enter", "cms_core_view"))
        scoped_client = self.sign_in(scoped)
        self.assertEqual(scoped_client.get(path).status_code, 403)
        self.assertEqual(scoped_client.get(BASE + "content/schema/").status_code, 200)
        self.assertFalse(any(x["domain"] == "brain"
                             for x in scoped_client.get(BASE + "content/schema/").json()["kinds"]))

    def test_legacy_proposal_preview_never_changes_canonical(self):
        canonical = content.canonical_snapshot("brain-anatomical-entity", self.left)
        state = ContentState.objects.create(kind="brain-anatomical-entity", canonical_pk=self.left.pk,
            canonical_digest=content.digest(canonical), legacy_origin=True, publication="current")
        payload = content.editable_snapshot("brain-anatomical-entity", self.left)
        rev = ContentRevision.objects.create(state=state, sequence=0, base_version=0,
            base_digest=state.canonical_digest, payload=payload, payload_digest=content.digest(payload),
            dependency_digest=content.dependencies(state.kind, self.left), status="legacy")
        state.current_revision = rev
        state.save(update_fields=["current_revision"])
        state, inspection = content.inspect_proposal(self.owner.pk, self.session,
            "brain-anatomical-entity", str(state.pk), state.version, "preview")
        self.assertTrue(inspection["valid"])
        self.assertFalse(inspection["publication_available"])
        updated = content.propose(self.owner.pk, self.session, state.kind, str(state.pk),
            {"description_en": "P10 NON-SCIENTIFIC unreviewed proposed change"},
            state.version, state.canonical_digest, "CONTENT_UPDATE", uuid.uuid4())
        self.assertEqual(updated.current_revision.status, "draft")
        self.left.refresh_from_db()
        self.assertEqual(content.canonical_snapshot(state.kind, self.left), canonical)

    def test_hierarchy_validation_rejects_cycle_and_laterality(self):
        with self.assertRaises(ValidationError):
            validate_snapshot("brain-hierarchy-link", {
                "child": self.root.pk, "parent": self.left.pk, "source_version": "P10 synthetic"})
        with self.assertRaises(ValidationError):
            validate_snapshot("brain-hierarchy-link", {
                "child": self.left.pk, "parent": self.right.pk, "source_version": "P10 synthetic"})
