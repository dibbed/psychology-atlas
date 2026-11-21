"""P16 read-only editorial proposal inventory for Brain and Assessment."""
from django.test import TestCase, override_settings

from .cms_content import digest
from .cms_content_models import ContentRevision, ContentState
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DomainProposalPreflightTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_client = self.sign_in(self.owner)
        self.brain = self.proposal(
            "brain-anatomical-entity", {"name_en": "P16 PRIVATE BRAIN TITLE - DO NOT LEAK"},
        )
        self.assessment = self.proposal(
            "assessment-instrument", {"name_en": "P16 PRIVATE ASSESSMENT TITLE - DO NOT LEAK"},
        )
        self.legacy = self.proposal("brain-network", {"name_en": "Legacy only"}, status="legacy")

    def proposal(self, kind, payload, status="draft"):
        state = ContentState.objects.create(
            kind=kind, canonical_pk=None, canonical_digest=digest({}),
            publication=ContentState.Publication.NEVER,
        )
        rev = ContentRevision.objects.create(
            state=state, sequence=1, base_version=0, base_digest=digest({}),
            payload=payload, payload_digest=digest(payload), dependency_digest=digest({}),
            status=status, schema_version=2, actor=self.owner,
        )
        state.version = 1
        state.current_revision = rev
        state.save(update_fields=("version", "current_revision"))
        return state

    def get(self, domain):
        return self.owner_client.get(BASE + f"publication/preflight/?domain={domain}&page_size=5&page=1")

    def test_brain_and_assessment_drafts_have_version_bound_private_proposal_envelopes(self):
        for domain, state in (("brain", self.brain), ("assessment", self.assessment)):
            with self.subTest(domain=domain):
                response = self.get(domain)
                self.assertEqual(response.status_code, 200, response.content[:500])
                body = response.json()
                self.assertEqual(body["domain"], domain)
                self.assertEqual(body["scope"], "private_editorial_proposals_only")
                self.assertFalse(body["publication_available"])
                self.assertEqual(body["count"], 1)
                item, = body["results"]
                self.assertEqual(item["resource_id"], str(state.pk))
                self.assertEqual(item["version"], 1)
                self.assertEqual(item["revision_status"], "draft")
                self.assertEqual(len(item["proposal_digest"]), 64)
                self.assertEqual(len(item["dependency_digest"]), 64)
                self.assertFalse(item["eligible"])
                self.assertIn("P16_MANIFEST_AND_RECEIPT_REQUIRED", item["blockers"])
                self.assertIn("SOURCE_DEPENDENCIES_NOT_REVALIDATED", item["blockers"])
                self.assertNotIn("PRIVATE", response.content.decode())
        self.assertEqual(self.get("brain").json()["results"][0]["proposal_digest"],
                         self.get("brain").json()["results"][0]["proposal_digest"])
        self.assertEqual(ContentState.objects.get(pk=self.brain.pk).publication, "never_published")
        self.assertEqual(ContentRevision.objects.count(), 3)

    def test_immutable_revision_edit_changes_only_the_current_proposal_envelope(self):
        before = self.get("assessment").json()["results"][0]
        state = self.assessment
        updated = {"name_en": "Other private synthetic metadata"}
        rev = ContentRevision.objects.create(
            state=state, sequence=2, base_version=1, base_digest=digest({}),
            payload=updated, payload_digest=digest(updated), dependency_digest=digest({}),
            status="approved", actor=self.owner,
        )
        state.version = 2
        state.current_revision = rev
        state.save(update_fields=("version", "current_revision"))
        after = self.get("assessment").json()["results"][0]
        self.assertNotEqual(before["proposal_digest"], after["proposal_digest"])
        self.assertEqual(after["revision_status"], "approved")
        self.assertFalse(after["eligible"])
        self.assertFalse(self.get("assessment").json()["publication_available"])

    def test_independent_domain_capabilities_and_strict_read_contract(self):
        restricted = self.user("p16-only-brain", staff=True,
                               caps=("cms_enter", "cms_brain_view", "cms_publication_validate_brain"))
        client = self.sign_in(restricted)
        self.assertEqual(client.get(BASE + "publication/preflight/?domain=brain").status_code, 200)
        ready = client.get(BASE + "me/")
        self.assertEqual(ready.status_code, 200, ready.content[:300])
        self.assertIn("cms_publication_validate_brain", ready.json()["ready_capabilities"])
        self.assertNotIn("cms_publication_apply_brain", ready.json()["ready_capabilities"])
        for domain in ("brain", "assessment"):
            self.assertIn("cms_publication_validate_" + domain,
                          self.owner_client.get(BASE + "me/").json()["ready_capabilities"])
        self.assertEqual(client.get(BASE + "publication/preflight/?domain=assessment").status_code, 403)
        self.assertEqual(client.get(BASE + "publication/preflight/?domain=learning").status_code, 403)
        self.assertEqual(self.get("unknown").status_code, 400)
        self.assertEqual(self.owner_client.get(BASE + "publication/preflight/?domain=brain&user_id=2").status_code, 400)
        self.assertEqual(self.post(self.owner_client, "publication/preflight/", {"domain": "brain"}).status_code, 405)
