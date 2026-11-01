"""Isolated, explicitly NON-SCIENTIFIC fixtures; real P04 MFA/CSRF/session reuse."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import DatabaseError, close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext

from . import models as m
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure
from .cms_source_models import SourceHistory, SourcePlan, SourcePlanReceipt, SourceState, SourceSuccessor
from .cms_sources import (MUTABLE_MODELS, SOURCE_FIELDS, apply_source_plan, preview_source,
    source_fingerprint, source_impact, source_snapshot)
from .tests_v100_p01 import BASE
from .tests_v100_p04 import ReviewFixture


SOURCE_CAPS = ("cms_enter", "cms_source_view", "cms_source_preview", "cms_source_validate", "cms_source_create",
    "cms_source_edit", "cms_source_archive", "cms_source_delete_preview", "cms_source_delete_unused", "cms_source_export")


class SourceFixture(ReviewFixture):
    def make_source(self, title, **values):
        # These reserved .invalid URLs and all claims are test data, never scientific evidence.
        defaults = {"citation": "NON-SCIENTIFIC synthetic citation", "url": "https://fixture.invalid/" + uuid.uuid4().hex,
            "verification_status": "source_checked"}
        return m.SourceReference.objects.create(title=title, **{**defaults, **values})

    def preview(self, operation="update", source=None, client=None, **values):
        data = {"operation": operation, "source_id": (source or self.source).pk}
        if operation == "create":
            data.pop("source_id")
        data.update(values)
        response = self.post(client or self.client, "sources/preview/", data)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response["ETag"], '"1"')
        self.assertEqual(response["Cache-Control"], "no-store")
        plan = response.json()
        self.assertEqual(SourcePlan.objects.get(pk=plan["id"]).fingerprint, plan["fingerprint"])
        return plan

    def apply(self, plan, client=None, version=1):
        return self.post(client or self.client, f"sources/plans/{plan['id']}/apply/", etag='"%s"' % version)

    def applied(self, plan):
        response = self.apply(plan)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["ETag"], '"2"')
        self.assertEqual(response.json()["status"], "applied")
        return response.json()["receipt"]

    def merge_values(self, survivor, candidates, move=True):
        snapshots = [source_snapshot(source) for source in [survivor, *candidates]]
        choices = {field: survivor.pk for field in SOURCE_FIELDS if any(s[field] != snapshots[0][field] for s in snapshots[1:])}
        mapping = []
        for source in candidates:
            impact = source_impact(source)
            for group in ("canonical", "review", "archives"):
                for item in impact[group]:
                    mapping.append({"key": item["key"], "action": "move", "target_id": survivor.pk}
                        if move and item["mutable"] else {"key": item["key"], "action": "retain"})
        return {"candidates": [source.pk for source in candidates], "field_choices": choices, "mapping": mapping}

    def protected_assessment(self):
        owner = m.AssessmentInstrument.objects.create(slug="non-scientific-fixture", name_en="NON-SCIENTIFIC family")
        link = m.AssessmentSource.objects.create(instrument=owner, source=self.source, note="NON-SCIENTIFIC claim")
        owner.review_status = "reviewed"
        owner.save()
        return owner, link


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SourceAPITests(SourceFixture, TransactionTestCase):
    def test_bibliography_list_does_not_scan_private_dependency_payloads(self):
        for index in range(30):
            self.make_source(f"NON-SCIENTIFIC paged source {index}")
        with CaptureQueriesContext(connection) as queries, patch("atlas.cms_sources.source_impact", side_effect=AssertionError("List must not load private impact")):
            response = self.client.get(BASE + "sources/", {"page_size": 30})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["results"]), 30)
        self.assertTrue(all(row["usage_count"] is None and row["impact_available"] is None for row in response.json()["results"]))
        self.assertLess(len(queries), 80)

    def test_create_normalization_persisted_preview_apply_and_exact_lookup(self):
        plan = self.preview("create", changes={"title": " NON-SCIENTIFIC source ", "doi": "https://doi.org/10.99999/SYNTHETIC.INVALID",
            "pmid": "PMID: 000000000", "url": "HTTPS://fixture.invalid/paper/?version=2&utm_source=synthetic", "resource_version": "2"})
        self.assertTrue(plan["preview"]["can_apply"])
        self.assertFalse(m.SourceReference.objects.filter(title="NON-SCIENTIFIC source").exists())
        receipt = self.applied(plan)
        source = m.SourceReference.objects.get(pk=receipt["source_ids"][0])
        self.assertEqual(source.doi, "10.99999/synthetic.invalid")
        self.assertEqual(source.url, "https://fixture.invalid/paper?version=2")
        self.assertEqual(SourceState.objects.get(source_pk=source.pk).resource_version, "2")
        self.code(self.apply(plan), "SOURCE_PLAN_APPLIED", 409)
        listed = self.client.get(BASE + "sources/", {"doi": "DOI: 10.99999/SYNTHETIC.INVALID"})
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual([row["id"] for row in listed.json()["results"]], [source.pk])
        self.assertEqual(self.client.get(BASE + "sources/", {"q": source.doi}).json()["count"], 0)
        self.code(self.client.get(BASE + "sources/", {"q": "source", "doi": source.doi}), "INVALID_QUERY", 400)

    def test_update_archive_delete_unused_retains_history_and_export_whitelist(self):
        original = source_snapshot(self.source)
        receipt = self.applied(self.preview(changes={"title": "NON-SCIENTIFIC corrected source", "resource_version": "synthetic-v1"}))
        self.assertEqual(receipt["counts"], {"moved": 0, "unchanged": 0, "blocked": 0})
        self.applied(self.preview("archive"))
        source_id = self.source.pk
        self.assertEqual(self.client.get(BASE + "sources/", {"archived": "1"}).json()["count"], 1)
        self.applied(self.preview("delete"))
        self.assertFalse(m.SourceReference.objects.filter(pk=source_id).exists())
        history = self.client.get(BASE + f"sources/{source_id}/history/")
        self.assertEqual(history.status_code, 200, history.content)
        self.assertEqual(history.json()["count"], 3)
        self.assertEqual(SourceHistory.objects.get(source_pk=source_id, version=1).before["title"], original["title"])
        self.assertNotIn("metadata", json.dumps(history.json()))
        other = self.make_source("NON-SCIENTIFIC export", metadata={"private_rights": "secret"})
        exported = self.client.get(BASE + "sources/export/", {"q": "export"})
        self.assertEqual(exported.status_code, 200, exported.content)
        self.assertEqual(exported.json()["results"][0]["id"], other.pk)
        self.assertNotIn("secret", exported.content.decode())
        self.assertNotIn("verification_status", exported.json()["results"][0])

    def test_full_runtime_consumer_inventory_is_covered_by_validated_adapters(self):
        current = {rel.related_model.__name__ for rel in m.SourceReference._meta.related_objects
            if rel.related_model.__module__ in {"atlas.models", "atlas.assessment_models"}}
        self.assertEqual(current, MUTABLE_MODELS)
        self.assertEqual(len(current), 39)

    def test_incoming_membership_note_claim_and_state_changes_stale_preview(self):
        plan = self.preview(changes={"citation": "NON-SCIENTIFIC changed claim"})
        link = m.DisorderSource.objects.create(disorder=self.disorder, source=self.source, note="NON-SCIENTIFIC incoming")
        self.code(self.apply(plan), "STALE_SOURCE_PLAN", 412)
        for mutate in (
            lambda: m.DisorderSource.objects.filter(pk=link.pk).update(note="NON-SCIENTIFIC new locator"),
            lambda: m.Disorder.objects.filter(pk=self.disorder.pk).update(overview="NON-SCIENTIFIC new context"),
            lambda: SourceState.objects.create(source_pk=self.source.pk, resource_version="new-synthetic-version"),
        ):
            plan = self.preview(changes={"citation": "NON-SCIENTIFIC proposed citation"})
            mutate()
            self.code(self.apply(plan), "STALE_SOURCE_PLAN", 412)
        self.assertEqual(SourcePlanReceipt.objects.count(), 0)

    def test_source_metadata_and_new_identity_competitor_stale_preview(self):
        plan = self.preview(changes={"doi": "10.99999/synthetic-collision.invalid"})
        self.make_source("NON-SCIENTIFIC competitor", doi="DOI:10.99999/SYNTHETIC-COLLISION.INVALID")
        self.code(self.apply(plan), "STALE_SOURCE_PLAN", 412)
        plan = self.preview(changes={"organization": "Synthetic organization"})
        fingerprint = source_fingerprint(self.source)
        self.source.metadata = {"legacy": "NON-SCIENTIFIC preserved provenance"}
        self.source.save()
        self.assertNotEqual(fingerprint, source_fingerprint(self.source))
        self.code(self.apply(plan), "STALE_SOURCE_PLAN", 412)

    def test_protected_assessment_cannot_change_source_typed_version_or_archive(self):
        owner, link = self.protected_assessment()
        for operation, changes in (("update", {"title": "NON-SCIENTIFIC change"}),
                                   ("update", {"resource_version": "new"}), ("archive", {}), ("delete", {})):
            plan = self.preview(operation, changes=changes)
            self.assertIn("SOURCE_PROTECTED", {b["code"] for b in plan["preview"]["blockers"]})
            self.code(self.apply(plan), "SOURCE_PLAN_BLOCKED", 409)
        owner.refresh_from_db()
        link.refresh_from_db()
        self.assertEqual(owner.review_status, "reviewed")
        self.assertEqual(link.source_id, self.source.pk)
        self.assertFalse(SourceState.objects.filter(source_pk=self.source.pk).exists())

    def test_reviewed_brain_alias_protection_and_safe_successor_without_downgrade(self):
        entity = m.BrainAnatomicalEntity.objects.create(slug="synthetic-brain", name_en="NON-SCIENTIFIC anatomy", kind="region", laterality="not_established")
        alias = m.BrainAnatomicalAlias.objects.create(entity=entity, text="NON-SCIENTIFIC alias", language="en", alias_type="alternative",
            source=self.source, source_note="NON-SCIENTIFIC spelling claim", review_status="reviewed")
        for operation, changes in (("update", {"resource_version": "new"}), ("archive", {})):
            plan = self.preview(operation, changes=changes)
            self.code(self.apply(plan), "SOURCE_PLAN_BLOCKED", 409)
        successor = self.make_source("NON-SCIENTIFIC correction")
        plan = self.preview("successor", candidates=[successor.pk])
        self.applied(plan)
        alias.refresh_from_db()
        self.assertEqual((alias.source_id, alias.review_status), (self.source.pk, "reviewed"))
        self.assertFalse(SourceState.objects.get(source_pk=self.source.pk).archived)
        self.assertEqual(SourceSuccessor.objects.get(plan_id=plan["id"]).successor_pk, successor.pk)

    def test_legacy_metadata_resource_version_pin_is_never_overwritten(self):
        self.source.metadata = {"source_version": "original-v7", "private": "NON-SCIENTIFIC preserved"}
        self.source.save()
        plan = self.preview(changes={"resource_version": "different-v8"})
        self.assertIn("RESOURCE_VERSION_CONFLICT", {b["code"] for b in plan["preview"]["blockers"]})
        self.code(self.apply(plan), "SOURCE_PLAN_BLOCKED", 409)
        self.applied(self.preview(changes={"title": "NON-SCIENTIFIC corrected title"}))
        self.source.refresh_from_db()
        self.assertEqual(self.source.metadata, {"source_version": "original-v7", "private": "NON-SCIENTIFIC preserved"})

    def test_merge_requires_identity_explicit_field_choices_and_mapping(self):
        self.source.doi = "10.99999/non-scientific.invalid"
        self.source.save()
        candidate = self.make_source("NON-SCIENTIFIC candidate", doi=self.source.doi)
        link = m.DisorderSource.objects.create(disorder=self.disorder, source=candidate, note="NON-SCIENTIFIC retained locator")
        missing = self.preview("merge", candidates=[candidate.pk])
        self.assertTrue({"MAPPING_REQUIRED", "FIELD_CHOICE_REQUIRED"} <= {b["code"] for b in missing["preview"]["blockers"]})
        values = self.merge_values(self.source, [candidate])
        plan = self.preview("merge", **values)
        self.assertTrue(plan["preview"]["can_apply"], plan)
        link.refresh_from_db()
        self.assertEqual(link.source_id, candidate.pk)
        receipt = self.applied(plan)
        link.refresh_from_db()
        self.assertEqual((link.source_id, link.note), (self.source.pk, "NON-SCIENTIFIC retained locator"))
        self.assertEqual(receipt["counts"]["moved"], 1)
        self.assertTrue(m.SourceReference.objects.filter(pk=candidate.pk).exists())
        retained = SourceHistory.objects.get(source_pk=candidate.pk)
        self.assertEqual(retained.before["usages"]["contexts"][0]["row"]["source_id"], candidate.pk)
        candidate.pmid = "000000001"
        candidate.save()
        self.source.pmid = "000000002"
        self.source.save()
        conflict = self.preview("merge", **self.merge_values(self.source, [candidate]))
        self.assertIn("IDENTITY_CONFLICT", {b["code"] for b in conflict["preview"]["blockers"]})

    def test_merge_uniqueness_conflict_does_not_deduplicate_or_delete_claims(self):
        self.source.doi = "10.99999/non-scientific.invalid"
        self.source.save()
        other = self.make_source("NON-SCIENTIFIC duplicate", doi=self.source.doi)
        a = m.DisorderSource.objects.create(disorder=self.disorder, source=self.source, note="NON-SCIENTIFIC note A")
        b = m.DisorderSource.objects.create(disorder=self.disorder, source=other, note="NON-SCIENTIFIC note B")
        plan = self.preview("merge", **self.merge_values(self.source, [other]))
        self.assertIn("UNIQUENESS_CONFLICT", {x["code"] for x in plan["preview"]["blockers"]})
        self.code(self.apply(plan), "SOURCE_PLAN_BLOCKED", 409)
        self.assertEqual(m.DisorderSource.objects.filter(pk__in=[a.pk, b.pk]).count(), 2)
        manual = self.preview("merge", **self.merge_values(self.source, [other], move=False))
        receipt = self.applied(manual)
        self.assertEqual(receipt["counts"]["unchanged"], 1)
        b.refresh_from_db()
        self.assertEqual((b.source_id, b.note), (other.pk, "NON-SCIENTIFIC note B"))

    def test_split_uses_complete_explicit_mapping_and_preserves_original_source(self):
        a = self.make_source("NON-SCIENTIFIC publication A", doi="10.99999/synthetic-a.invalid")
        b = self.make_source("NON-SCIENTIFIC publication B", doi="10.99999/synthetic-b.invalid")
        first = m.DisorderSource.objects.create(disorder=self.disorder, source=self.source, note="NON-SCIENTIFIC claim A")
        second_owner = m.Disorder.objects.create(category=self.category, slug="synthetic-second", name_en="NON-SCIENTIFIC second")
        second = m.DisorderSource.objects.create(disorder=second_owner, source=self.source, note="NON-SCIENTIFIC claim B")
        missing = self.preview("split", candidates=[a.pk, b.pk])
        self.code(self.apply(missing), "SOURCE_PLAN_BLOCKED", 409)
        plan = self.preview("split", candidates=[a.pk, b.pk], mapping=[
            {"key": f"DisorderSource:{first.pk}:source", "action": "move", "target_id": a.pk},
            {"key": f"DisorderSource:{second.pk}:source", "action": "move", "target_id": b.pk}])
        receipt = self.applied(plan)
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual((first.source_id, second.source_id), (a.pk, b.pk))
        self.assertEqual(receipt["counts"]["moved"], 2)
        self.assertTrue(m.SourceReference.objects.filter(pk=self.source.pk).exists())
        self.assertEqual(SourceSuccessor.objects.filter(source_pk=self.source.pk).count(), 2)

    def test_successor_cycle_is_blocked(self):
        other = self.make_source("NON-SCIENTIFIC successor")
        self.applied(self.preview("successor", candidates=[other.pk]))
        plan = self.preview("successor", source=other, candidates=[self.source.pk])
        self.assertIn("SUCCESSOR_CYCLE", {b["code"] for b in plan["preview"]["blockers"]})
        self.code(self.apply(plan), "SOURCE_PLAN_BLOCKED", 409)

    def test_archive_json_references_are_inventory_fingerprinted_and_manual_only(self):
        corpus = m.DSMCorpus.objects.create(key="non-scientific-corpus", title="NON-SCIENTIFIC archive", source_filename="synthetic.invalid.json",
            source_sha256="0" * 64, source_registry={"synthetic-key": {"عنوان": self.source.title, "نشانی": self.source.url}},
            raw_document={"NON-SCIENTIFIC": True})
        dataset = m.ResearchDataset.objects.create(key="non-scientific-dataset", source_filename="synthetic.invalid.json", source_sha256="1" * 64,
            raw_document={"sources": [{"title": self.source.title, "url": self.source.url}]})
        raw = m.ResearchRecord.objects.create(dataset=dataset, section="sources", external_id="external-synthetic",
            payload={"NON-SCIENTIFIC": True}, promoted_model="atlas.sourcereference", promoted_pk=self.source.pk)
        ref = m.ResearchRecord.objects.create(dataset=dataset, section="theories", external_id="synthetic-theory", source_ids=[raw.external_id],
            payload={"NON-SCIENTIFIC": True})
        impact = source_impact(self.source)
        self.assertTrue({"DSMCorpus", "ResearchDataset", "ResearchRecord"} <= {item["model"] for item in impact["archives"]})
        deleted = self.preview("delete")
        self.assertIn("SOURCE_IN_USE", {b["code"] for b in deleted["preview"]["blockers"]})
        plan = self.preview(changes={"citation": "NON-SCIENTIFIC proposed citation"})
        ref.payload = {"NON-SCIENTIFIC": "changed raw claim"}; ref.save()
        self.code(self.apply(plan), "STALE_SOURCE_PLAN", 412)
        self.source.doi = "10.99999/archive-synthetic.invalid"; self.source.save()
        survivor = self.make_source("NON-SCIENTIFIC survivor", doi=self.source.doi)
        values = self.merge_values(survivor, [self.source])
        values["mapping"][0] = {**values["mapping"][0], "action": "move", "target_id": survivor.pk}
        plan = self.preview("merge", source=survivor, **values)
        self.assertIn("IMMUTABLE_REFERENCE", {b["code"] for b in plan["preview"]["blockers"]})
        self.code(self.apply(plan), "SOURCE_PLAN_BLOCKED", 409)
        corpus.refresh_from_db()
        self.assertEqual(corpus.source_registry["synthetic-key"]["عنوان"], self.source.title)

    def test_p04_reviews_are_retained_and_new_decisions_stale_plan(self):
        self.approved()
        impact = source_impact(self.source)
        self.assertTrue({"ReviewTask", "ReviewDecision"} <= {item["model"] for item in impact["review"]})
        plan = self.preview(changes={"citation": "NON-SCIENTIFIC updated citation"})
        decisions = list(m.ReviewDecision.objects.order_by("pk").values()) if hasattr(m, "ReviewDecision") else []
        self.applied(plan)
        current = self.detail()
        self.assertFalse(current["approval"]["eligible"])
        if decisions:
            self.assertEqual(decisions, list(m.ReviewDecision.objects.order_by("pk").values()))

    def test_scope_denies_private_detail_plan_history_counts_and_domain_move(self):
        reader = self.user("source-only", staff=True, caps=SOURCE_CAPS)
        client = self.signed(reader)
        link = m.DisorderSource.objects.create(disorder=self.disorder, source=self.source, note="PRIVATE SYNTHETIC LOCATOR")
        owner_plan = self.preview(changes={"citation": "NON-SCIENTIFIC changed citation"})
        self.applied(owner_plan)
        for path in (f"sources/{self.source.pk}/", f"sources/{self.source.pk}/history/", f"sources/plans/{owner_plan['id']}/"):
            response = client.get(BASE + path)
            self.code(response, "SOURCE_IMPACT_SCOPE_DENIED")
            self.assertNotIn("PRIVATE", response.content.decode())
        self.code(self.apply(owner_plan, client), "SOURCE_IMPACT_SCOPE_DENIED")
        listed = client.get(BASE + "sources/")
        row = next(row for row in listed.json()["results"] if row["id"] == self.source.pk)
        self.assertIsNone(row["usage_count"])
        self.assertIsNone(row["impact_available"])
        self.grant(reader, "cms_core_view")
        self.source.doi = "10.99999/private-synthetic.invalid"; self.source.save()
        survivor = self.make_source("NON-SCIENTIFIC private merge", doi=self.source.doi)
        response = self.post(client, "sources/preview/", {"operation": "merge", "source_id": survivor.pk,
            **self.merge_values(survivor, [self.source])})
        self.code(response, "PERMISSION_DENIED")
        link.refresh_from_db()
        self.assertEqual(link.source_id, self.source.pk)

    def test_service_permission_recheck_and_revoked_session_prevent_apply(self):
        editor = self.user("source-editor", staff=True, caps=SOURCE_CAPS)
        client = self.signed(editor)
        plan = self.preview(changes={"title": "NON-SCIENTIFIC proposed title"}, client=client)
        session_id = client.session["cms_session_id"]
        editor.user_permissions.remove(Permission.objects.get(content_type__app_label="atlas", content_type__model="rolepolicy", codename="cms_source_edit"))
        with self.assertRaises(CMSFailure) as caught:
            apply_source_plan(editor.pk, session_id, plan["id"], 1, uuid.uuid4())
        self.assertEqual(str(caught.exception.detail["code"]), "PERMISSION_DENIED")
        self.assertFalse(SourcePlanReceipt.objects.exists())
        from .cms_sessions import revoke_account
        from .cms_policy import policy_lock
        self.grant(editor, "cms_source_edit")
        with policy_lock():
            revoke_account(editor)
        with self.assertRaises(CMSFailure) as caught:
            apply_source_plan(editor.pk, session_id, plan["id"], 1, uuid.uuid4())
        self.assertEqual(str(caught.exception.detail["code"]), "UNAUTHENTICATED")

    def test_real_csrf_and_required_apply_precondition(self):
        plan = self.preview(changes={"title": "NON-SCIENTIFIC proposed title"})
        path = BASE + f"sources/plans/{plan['id']}/apply/"
        self.code(self.client.post(path, "{}", content_type="application/json"), "CSRF_FAILED")
        self.code(self.post(self.client, path.removeprefix(BASE)), "PRECONDITION_REQUIRED", 428)
        self.code(self.apply(plan, version=0), "STALE_REVISION", 412)

    def test_audit_failure_rolls_back_mutation_history_state_and_receipt(self):
        plan = self.preview(changes={"title": "NON-SCIENTIFIC rollback candidate"})
        create = AdminAuditEvent.objects.create
        def fail_success_audit(**kwargs):
            if kwargs.get("action") == "source.updated":
                raise DatabaseError("Synthetic audit outage, never emitted")
            return create(**kwargs)
        with patch("atlas.cms_sources.AdminAuditEvent.objects.create", side_effect=fail_success_audit):
            response = self.apply(plan)
        self.code(response, "WRITE_FAILED", 503)
        self.source.refresh_from_db()
        self.assertEqual(self.source.title, "Synthetic cited source")
        self.assertFalse(SourceState.objects.exists())
        self.assertFalse(SourceHistory.objects.exists())
        self.assertFalse(SourcePlanReceipt.objects.exists())
        self.assertTrue(AdminAuditEvent.objects.filter(action="api.failure", error_code="WRITE_FAILED").exists())

    def test_append_only_plans_history_receipts_and_actor_erasure(self):
        plan = self.preview(changes={"title": "NON-SCIENTIFIC immutable change"})
        self.applied(plan)
        for model in (SourcePlan, SourceHistory, SourcePlanReceipt):
            row = model.objects.first()
            with self.assertRaises(ValidationError):
                row.save()
            with self.assertRaises(ValidationError):
                model.objects.all().update(actor=None)
            with self.assertRaises(ValidationError):
                model.objects.all().delete()
        reference = SourceHistory.objects.first().actor_ref
        self.owner.delete()
        row = SourceHistory.objects.first()
        self.assertIsNone(row.actor_id)
        self.assertEqual(row.actor_ref, reference)

    def test_duplicate_apply_across_connections_commits_once(self):
        plan = self.preview(changes={"title": "NON-SCIENTIFIC concurrent update"})
        barrier, session_id, actor_id = Barrier(2), self.client.session["cms_session_id"], self.owner.pk
        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=20)
                apply_source_plan(actor_id, session_id, plan["id"], 1, uuid.uuid4())
                return "success"
            except CMSFailure as failure:
                return str(failure.detail["code"])
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))
        self.assertCountEqual(results, ["success", "SOURCE_PLAN_APPLIED"])
        self.assertEqual(SourceHistory.objects.filter(source_pk=self.source.pk).count(), 1)
        self.assertEqual(SourcePlanReceipt.objects.filter(plan_id=plan["id"]).count(), 1)

    def test_governance_json_evidence_is_private_and_participates_in_fingerprint(self):
        from .cms_governance_models import GovernanceRecord, GovernanceRevision
        record = GovernanceRecord.objects.create(kind="rights", domain="assessment", resource_type="AssessmentInstrument", resource_id=999,
            resource_version="NON-SCIENTIFIC edition", material="synthetic", intended_use="synthetic")
        revision = GovernanceRevision.objects.create(record=record, sequence=1, payload={"holder_evidence": [{"source_id": self.source.pk,
            "locator": "PRIVATE NON-SCIENTIFIC RIGHTS"}]}, payload_digest="0" * 64, resource_digest="1" * 64, dependency_digest="2" * 64,
            source_ids=[self.source.pk], status="submitted", policy_version=0, policy_mode="solo_owner", actor_ref="synthetic", action="submit", reason="")
        impact = source_impact(self.source)
        self.assertIn("GovernanceRevision", {item["model"] for item in impact["review"]})
        reader = self.user("source-rights-reader", staff=True, caps=SOURCE_CAPS)
        self.code(self.signed(reader).get(BASE + f"sources/{self.source.pk}/"), "SOURCE_IMPACT_SCOPE_DENIED")
        plan = self.preview(changes={"citation": "NON-SCIENTIFIC changed citation"})
        GovernanceRevision.objects.create(record=record, sequence=2, payload={"evidence": [{"source_id": self.source.pk,
            "locator": "PRIVATE NEW NON-SCIENTIFIC LOCATOR"}]}, payload_digest="3" * 64, resource_digest="1" * 64, dependency_digest="4" * 64,
            source_ids=[], status="submitted", policy_version=0, policy_mode="solo_owner", actor_ref="synthetic", action="submit", reason="")
        self.code(self.apply(plan), "STALE_SOURCE_PLAN", 412)
        self.assertEqual(GovernanceRevision.objects.get(pk=revision.pk).source_ids, [self.source.pk])
