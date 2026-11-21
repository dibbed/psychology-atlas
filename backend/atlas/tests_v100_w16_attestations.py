"""W16-03 evidence-bound, independent human attestation receipts.

Test-only reviewer decisions are synthetic. Runtime attestations remain
different from public rights clearance or an authority to Apply.
"""
import uuid

from django.test import TestCase, override_settings

from .cms_content import digest
from .cms_content_models import ContentRevision, ContentState
from .cms_models import AdminAuditEvent
from .cms_review_models import ReviewPolicy
from .models import (BrainAnatomicalEntity, BrainAnatomicalEntitySource,
                     BrainAnatomicalAlias, SourceReference)
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GenericPublicationAttestationTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        review, _ = ReviewPolicy.objects.get_or_create(pk=1)
        review.mode = "two_person"
        review.save(update_fields=["mode"])
        self.writer = self.sign_in(self.owner)
        self.source = SourceReference.objects.create(
            title="Synthetic source, not licensed", citation="Synthetic reference",
            url="https://example.org/qa-only", verification_status="source_checked")
        self.parent = BrainAnatomicalEntity.objects.create(
            slug="w16-attestation-parent", name_en="Synthetic visible root",
            kind="structure", laterality="not_established", is_active=True)
        BrainAnatomicalEntitySource.objects.create(
            entity=self.parent, source=self.source, note="QA-only source")
        self.parent.review_status = "reviewed"
        self.parent.save(update_fields=["review_status"])
        self.state = ContentState.objects.create(
            kind="brain-anatomical-alias", canonical_digest=digest({}))
        data = {
            "entity": self.parent.pk,
            "source": self.source.pk, "text": "QA_PRIVATE_ALIAS_SOURCE_VALUE",
            "language": "en", "alias_type": "alternative",
            "source_note": "Synthetic claim-only metadata",
        }
        revision = ContentRevision.objects.create(
            state=self.state, sequence=1, base_version=0,
            base_digest=digest({}), payload=data, payload_digest=digest(data),
            dependency_digest=digest({}), actor=self.owner, status="draft")
        self.state.version, self.state.current_revision = 1, revision
        self.state.save(update_fields=["version", "current_revision"])
        inventory = self.writer.get(BASE + "publication/preflight/?domain=brain")
        self.assertEqual(inventory.status_code, 200)
        candidate = next(row for row in inventory.json()["results"]
                         if row["resource_id"] == str(self.state.pk))
        chosen = self.post(self.writer, "publication/selections/", {
            "domain": "brain", "request_key": str(uuid.uuid4()),
            "entries": [{"kind": self.state.kind, "resource_id": str(self.state.pk),
                         "expected_digest": candidate["proposal_digest"]}],
        })
        self.assertEqual(chosen.status_code, 201, chosen.content[:400])
        dossier = self.post(self.writer,
            f'publication/selections/{chosen.json()["id"]}/prepare/', {
                "request_key": str(uuid.uuid4()),
                "selection_digest": chosen.json()["selection_digest"]})
        self.assertEqual(dossier.status_code, 201, dossier.content[:400])
        plan = self.post(self.writer,
            f'publication/preparations/{dossier.json()["id"]}/freeze/', {
                "request_key": str(uuid.uuid4()),
                "dossier_digest": dossier.json()["dossier_digest"]})
        self.assertEqual(plan.status_code, 201, plan.content[:400])
        self.plan = plan.json()
        self.reviewer = self.user("reviewer-p16", staff=True, caps=(
            "cms_enter", "cms_brain_view", "cms_source_view", "cms_publication_verify_brain",
            "cms_publication_approve_brain", "cms_review_decide_brain_source",
            "cms_review_decide_brain_scientific", "cms_review_decide_brain_rights",
        ))
        self.reader = self.sign_in(self.reviewer)
        self.url = f'publication/plans/{self.plan["id"]}/attestations/'

    def attest(self, kind, outcome="attested", *, client=None, key=None, **changes):
        payload = {
            "kind": kind, "outcome": outcome,
            "manifest_digest": self.plan["manifest_digest"],
            "request_key": str(key or uuid.uuid4()),
            "evidence_source_ids": [self.source.pk] if outcome=="attested" else [],
            "rights_scope": ["metadata","text","translation"] if kind=="rights" and outcome=="attested" else [],
            "evidence_reference": "TEST_FIXTURE_PRIVATE_NO_REAL_LICENSE" if outcome=="attested" else "",
            "self_review_ack": True,
        }
        payload.update(changes)
        return self.post(client or self.reader, self.url, payload)

    def test_three_independent_attestations_are_append_only_but_not_public_approval(self):
        from .cms_publication_plan_models import PublicationManifestAttestation
        summary = self.reader.get(BASE + self.url)
        self.assertEqual(summary.status_code, 200, summary.content[:300])
        self.assertFalse(summary.json()["attestations_current"])
        self.assertFalse(summary.json()["publication_available"])
        for kind in ("source", "scientific", "rights"):
            response = self.attest(kind)
            self.assertEqual(response.status_code, 201, response.content[:400])
            self.assertEqual(response.json()["kind"], kind)
            self.assertNotIn("TEST_FIXTURE_PRIVATE_NO_REAL_LICENSE", response.content.decode())
            self.assertFalse(response.json()["publication_available"])
        check = self.reader.get(BASE + self.url)
        self.assertEqual(check.status_code, 200, check.content[:350])
        self.assertTrue(check.json()["attestations_current"])
        self.assertEqual(check.json()["status"], "attestations_recorded_not_publication_clearance")
        self.assertFalse(check.json()["publication_available"])
        self.assertFalse(check.json()["approved"])
        self.assertNotIn("QA_PRIVATE_ALIAS_SOURCE_VALUE", check.content.decode())
        self.assertNotIn("TEST_FIXTURE_PRIVATE_NO_REAL_LICENSE", check.content.decode())
        self.assertEqual(PublicationManifestAttestation.objects.count(), 3)
        self.assertEqual(AdminAuditEvent.objects.filter(
            action="publication.attestation_recorded").count(), 3)
        self.assertEqual(self.state.publication, "never_published")
        self.assertFalse(BrainAnatomicalAlias.objects.filter(
            text="QA_PRIVATE_ALIAS_SOURCE_VALUE").exists())
        self.assertFalse(self.writer.get(BASE + self.url).json()["publication_available"])

    def test_idempotency_revocation_and_last_decision_wins(self):
        from .cms_publication_plan_models import PublicationManifestAttestation
        key = uuid.uuid4()
        first = self.attest("source", key=key)
        self.assertEqual(first.status_code, 201, first.content[:250])
        recovered = self.attest("source", key=key)
        self.assertEqual(recovered.status_code, 200, recovered.content[:250])
        self.assertTrue(recovered.json()["recovered"])
        self.assertEqual(first.json()["id"], recovered.json()["id"])
        conflict = self.attest("rights", key=key)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(self.attest("source", outcome="revoked").status_code, 201)
        self.assertFalse(self.reader.get(BASE + self.url).json()["attestations_current"])
        self.assertEqual(self.reader.get(BASE + self.url).json()["states"]["source"], "revoked")
        self.assertEqual(PublicationManifestAttestation.objects.count(), 2)

    def test_two_person_and_per_kind_capability_are_enforced(self):
        self.assertEqual(self.attest("source", client=self.writer).status_code, 409)
        limited = self.sign_in(self.user("p16-approver-limited", staff=True, caps=(
            "cms_enter","cms_brain_view","cms_source_view","cms_publication_approve_brain",
            "cms_review_decide_brain_source",
        )))
        self.assertEqual(self.attest("source", client=limited).status_code, 201)
        self.assertEqual(self.attest("rights", client=limited).status_code, 403)
        no_scope = self.sign_in(self.user("p16-outsider", staff=True,
            caps=("cms_enter","cms_assessment_view","cms_publication_approve_assessment")))
        self.assertIn(self.attest("source", client=no_scope).status_code, (403, 404))

    def test_source_scope_and_rights_evidence_are_strict(self):
        other = SourceReference.objects.create(
            title="Unrelated external source", citation="Synthetic only",
            url="https://example.org/unrelated", verification_status="source_checked")
        self.assertEqual(self.attest("source", evidence_source_ids=[other.pk]).status_code, 409)
        self.assertEqual(self.attest("source", evidence_source_ids=[]).status_code, 409)
        self.assertEqual(self.attest("rights", rights_scope=["metadata"]).status_code, 400)
        self.assertEqual(self.attest("rights", evidence_reference="").status_code, 400)
        self.assertEqual(self.attest("rights", rights_scope=["metadata","text","translation","secret"]).status_code, 400)
        self.assertEqual(self.attest("scientific", garbage=True).status_code, 400)

    def test_attestation_status_turns_stale_when_source_changes(self):
        from django.db.models.query import QuerySet
        for kind in ("source", "scientific", "rights"):
            self.assertEqual(self.attest(kind).status_code, 201)
        self.assertTrue(self.reader.get(BASE + self.url).json()["attestations_current"])
        QuerySet.update(SourceReference.objects.filter(pk=self.source.pk),
                        title="UPDATED_REAL_SOURCE_DRIFT")
        status = self.reader.get(BASE + self.url)
        self.assertEqual(status.status_code, 200, status.content[:400])
        self.assertFalse(status.json()["attestations_current"])
        self.assertFalse(status.json()["snapshot_current"])
        self.assertFalse(status.json()["publication_available"])
        self.assertNotIn("UPDATED_REAL_SOURCE_DRIFT", status.content.decode())
        self.assertEqual(self.attest("source").status_code, 409)
        # Revocation is still legal even when the original evidence is stale.
        revoke = self.attest("source", outcome="revoked")
        self.assertEqual(revoke.status_code, 201, revoke.content[:300])
        self.assertEqual(self.reader.get(BASE + self.url).json()["states"]["source"],
                         "revoked")

    def test_review_policy_drift_invalidates_attested_status(self):
        for kind in ("source", "scientific", "rights"):
            self.assertEqual(self.attest(kind).status_code, 201)
        self.assertTrue(self.reader.get(BASE + self.url).json()["attestations_current"])
        row = ReviewPolicy.objects.get(pk=1)
        row.version += 1
        row.save(update_fields=["version"])
        status = self.reader.get(BASE + self.url)
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()["attestations_current"])
        self.assertEqual(self.attest("source").status_code, 409)

    def test_manifest_and_policy_drift_block_new_attestation(self):
        data = {"entity": self.parent.pk, "source": self.source.pk,
                "text": "NEW_CHANGED_HIDDEN_CONTENT",
                "language": "en","alias_type":"alternative"}
        new = ContentRevision.objects.create(
            state=self.state, sequence=2, base_version=1,
            base_digest=digest({}), payload=data, payload_digest=digest(data),
            dependency_digest=digest({}), actor=self.owner, status="draft")
        self.state.current_revision, self.state.version = new, 2
        self.state.save(update_fields=["current_revision","version"])
        failed = self.attest("source")
        self.assertEqual(failed.status_code, 409, failed.content[:400])
        self.assertNotIn("NEW_CHANGED_HIDDEN_CONTENT", failed.content.decode())
