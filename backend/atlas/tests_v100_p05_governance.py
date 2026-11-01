"""Non-scientific .invalid fixtures; real P04 MFA/CSRF authority, exact scoped history."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import DatabaseError, close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from .cms_governance import (REGISTRY, governance_dependency_snapshot, mutate_governance,
    resource_binding, rights_eligibility)
from .cms_governance_models import GovernanceDecision, GovernanceRecord, GovernanceRevision
from .cms_models import AdminAuditEvent, AdminSession
from .cms_public_rights import public_rights
from .cms_review_models import ReviewPolicy
from .cms_source_models import SourcePlan, SourceState, SourceSuccessor
from .models import AssessmentInstrument, AssessmentLanguageForm, AssessmentVersion, Disorder, SourceReference
from .tests_v100_p01 import BASE
from .tests_v100_p04 import ReviewFixture


CAPS = ("cms_enter", "cms_core_view", "cms_core_edit", "cms_rights_decide", "cms_rights_revoke",
    "cms_terminology_decide", "cms_review_decide_core_rights", "cms_review_decide_core_terminology")


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class GovernanceTests(ReviewFixture, TransactionTestCase):
    def make_source(self, title, **values):
        return SourceReference.objects.create(title="NON-SCIENTIFIC " + title,
            citation="Isolated fixture; no legal or scientific evidence",
            url="https://governance-fixture.invalid/source", verification_status="source_checked", **values)

    def setUp(self):
        super().setUp()
        self.reviewer = self.user("governance-reviewer", staff=True, caps=CAPS)
        self.governance_editor = self.user("governance-editor", staff=True, caps=("cms_enter", "cms_core_view", "cms_core_edit"))
        self.rights_source = self.make_source("independent rights fixture")

    def proposal(self, kind="rights", resource_type="disorder", resource_id=None, **changes):
        resource_id = self.disorder.pk if resource_id is None else resource_id
        binding = resource_binding(resource_type, resource_id)
        evidence = [{"source_id": self.rights_source.pk, "locator": "Synthetic fixture section; no real permission"}]
        data = {"resource_type": resource_type, "resource_id": resource_id,
            "resource_version": binding["resource_version"], "evidence": evidence, "reason": "CORRECTION_REQUIRED"}
        if kind == "rights":
            data.update({"material": "metadata", "intended_use": "public_display", "status": "allowed",
                "rightsholder": "NON-SCIENTIFIC fixture holder", "holder_identification": "Isolated test identity only",
                "holder_evidence": evidence, "public_access": "unknown", "reviewed_on": timezone.localdate().isoformat(),
                "effective_on": timezone.localdate().isoformat(), "expires_on": None, "review_on": None,
                "limitations": "Only isolated synthetic tests, no legal claim", "territory": "", "conflict_note": ""})
        else:
            data.update({"term_kind": "display", "name_en": "NON-SCIENTIFIC fixture label", "name_fa": "نام ساختگی آزمون",
                "alternatives": ["گزینهٔ ساختگی"], "selection_note": "انتخاب فقط برای آزمون؛ بدون ادعای علمی"})
        return {**data, **changes}

    def create(self, kind="rights", client=None, data=None, **changes):
        response = self.post(client or self.client, f"governance/{kind}/", data if data is not None else self.proposal(kind, **changes))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        return response.json()["record"]

    def act(self, record, action, data=None, client=None, version=None):
        return self.post(client or self.client, f"governance/{record['kind']}/{record['id']}/{action}/", data,
            etag=f'"{record["version"] if version is None else version}"')

    def good(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        record = response.json()["record"]
        self.assertEqual(response["ETag"], f'"{record["version"]}"')
        self.assertEqual(response["Cache-Control"], "no-store")
        return record

    def approve(self, record, reviewer=None, ack=True):
        reviewer = reviewer or self.owner
        record = self.good(self.act(record, "assign", {"reviewer_id": reviewer.pk}))
        return self.good(self.act(record, "decide", {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED" if record["kind"] == "rights" else "TERMINOLOGY_SELECTED",
            "self_review_ack": ack}, client=self.signed(reviewer)))

    def rights_result(self, record, **changes):
        params = {"resource_type": record["resource_type"], "resource_id": record["resource_id"],
            "resource_version": resource_binding(record["resource_type"], record["resource_id"])["resource_version"],
            "material": record["material"], "intended_use": record["intended_use"]}
        return rights_eligibility(**{**params, **changes})

    def patch_record(self, record, data, client=None):
        client = client or self.client
        return client.patch(BASE + f"governance/{record['kind']}/{record['id']}/", json.dumps(data),
            content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf(client), HTTP_IF_MATCH=f'"{record["version"]}"')

    def test_registry_contains_actual_allowlisted_domains_and_never_private_user_targets(self):
        self.assertEqual({e[1] for e in REGISTRY.values()}, {"core", "dsm", "source", "brain", "assessment", "therapy", "history", "learning", "cases"})
        for resource_type, (model, _, en, fa, _, _) in REGISTRY.items():
            self.assertIsNotNone(model._meta.get_field(en), resource_type)
            if fa:
                self.assertIsNotNone(model._meta.get_field(fa), resource_type)
        for resource_type in ("user", "UserNote", "atlas.UserProgress", "__dict__"):
            response = self.post(self.client, "governance/rights/", {**self.proposal(), "resource_type": resource_type})
            self.code(response, "NOT_FOUND", 404)

    def test_unknown_can_be_genuinely_unestablished_and_never_permission(self):
        binding = resource_binding("disorder", self.disorder.pk)
        record = self.create(data={"resource_type": "disorder", "resource_id": self.disorder.pk,
            "resource_version": binding["resource_version"], "material": "metadata", "intended_use": "public_display"})
        payload = record["payload"]
        self.assertEqual(payload["status"], "unknown")
        self.assertEqual(payload["rightsholder"], "")
        self.assertEqual(payload["holder_identification"], "")
        self.assertEqual(payload["holder_evidence"], [])
        self.assertIsNone(payload["reviewed_on"])
        self.assertIsNone(payload["effective_on"])
        self.assertEqual(self.rights_result(record)["status"], "legacy")
        record = self.approve(record)
        result = self.rights_result(record)
        self.assertEqual(result["status"], "unknown")
        self.assertFalse(result["eligible"])
        self.assertFalse(result["permitted"])

    def test_allowed_requires_holder_identification_evidence_and_dates(self):
        for field, empty in (("rightsholder", ""), ("holder_identification", ""), ("holder_evidence", []), ("evidence", []),
                ("reviewed_on", None), ("effective_on", None), ("limitations", "")):
            data = self.proposal(**{field: empty})
            response = self.post(self.client, "governance/rights/", data)
            self.assertEqual(response.status_code, 400, (field, response.content))
        self.assertFalse(GovernanceRecord.objects.exists())

    def test_editor_proposals_and_rejections_never_withdraw_legacy_or_approved_material(self):
        editor = self.signed(self.governance_editor)
        record = self.create(client=editor, status="restricted")
        self.assertEqual(self.rights_result(record)["status"], "legacy")
        self.assertTrue(public_rights(Disorder.objects.all(), "disorder").filter(pk=self.disorder.pk).exists())
        assigned = self.good(self.act(record, "assign", {"reviewer_id": self.reviewer.pk}))
        rejected = self.good(self.act(assigned, "decide", {"outcome": "reject", "reason": "CORRECTION_REQUIRED", "self_review_ack": False}, client=self.signed(self.reviewer)))
        self.assertEqual(self.rights_result(rejected)["status"], "legacy")
        allowed = self.approve(self.create())
        pending = self.create(client=editor, status="unknown")
        self.assertTrue(self.rights_result(allowed)["permitted"])
        self.assertTrue(self.rights_result(pending)["eligible"])
        self.code(self.act(pending, "assign", {"reviewer_id": self.governance_editor.pk}, client=editor), "PERMISSION_DENIED")

    def test_exact_scope_unknown_conflict_and_revocation(self):
        allowed = self.approve(self.create())
        self.assertTrue(self.rights_result(allowed)["permitted"])
        for changes in ({"material": "item"}, {"intended_use": "translation"}, {"resource_id": self.disorder.pk + 500}):
            self.assertEqual(self.rights_result(allowed, **changes)["status"], "legacy")
        self.assertEqual(self.rights_result(allowed, resource_version="another-version")["status"], "stale")
        restricted = self.create(status="restricted")
        self.assertTrue(self.rights_result(allowed)["eligible"])
        restricted = self.approve(restricted)
        self.assertEqual(self.rights_result(allowed)["status"], "conflict")
        self.good(self.act(allowed, "revoke", {"reason": "CORRECTION_REQUIRED"}))
        self.assertFalse(self.rights_result(restricted)["eligible"])

    def test_only_exact_metadata_decisions_change_public_read_overlay(self):
        item = self.approve(self.create(material="item", status="restricted"))
        self.assertFalse(self.rights_result(item)["eligible"])
        self.assertTrue(public_rights(Disorder.objects.all(), "disorder").filter(pk=self.disorder.pk).exists())
        metadata = self.approve(self.create())
        self.assertTrue(public_rights(Disorder.objects.all(), "disorder").filter(pk=self.disorder.pk).exists())
        self.good(self.act(metadata, "revoke", {"reason": "CORRECTION_REQUIRED"}))
        self.assertFalse(public_rights(Disorder.objects.all(), "disorder").filter(pk=self.disorder.pk).exists())

    def test_reopen_retains_previous_effective_decision_until_explicit_new_decision(self):
        record = self.approve(self.create())
        before = self.rights_result(record)
        reopened = self.good(self.act(record, "reopen"))
        self.assertTrue(self.rights_result(reopened)["permitted"])
        changed = self.good(self.patch_record(reopened, {"status": "restricted"}))
        self.assertTrue(self.rights_result(changed)["permitted"])
        changed = self.approve(changed)
        self.assertEqual(self.rights_result(changed)["status"], "restricted")
        self.assertEqual(len(before["record_ids"]), 1)

    def test_revoked_does_not_revive_when_reopened(self):
        record = self.approve(self.create())
        record = self.good(self.act(record, "revoke", {"reason": "CORRECTION_REQUIRED"}))
        reopened = self.good(self.act(record, "reopen"))
        self.assertEqual(self.rights_result(reopened)["status"], "revoked")

    def test_expiry_effective_dates_and_overdue_queue_precede_pagination(self):
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        due = self.approve(self.create(review_on=today.isoformat()))
        expired = self.approve(self.create(expires_on=today.isoformat(), material="item"))
        self.assertTrue(self.rights_result(due)["permitted"])
        with patch("atlas.cms_governance.timezone.localdate", return_value=tomorrow):
            self.assertEqual(self.rights_result(due)["status"], "review_overdue")
            self.assertEqual(self.rights_result(expired)["status"], "expired")
            response = self.client.get(BASE + "governance/rights/?computed_status=review_overdue&page_size=1")
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.json()["count"], 1)
            self.assertEqual(response.json()["results"][0]["id"], due["id"])
        future = self.create(effective_on=tomorrow.isoformat())
        future = self.good(self.act(future, "assign", {"reviewer_id": self.owner.pk}))
        self.code(self.act(future, "decide", {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED", "self_review_ack": True}), "RIGHTS_NOT_ELIGIBLE", 409)

    def test_stale_etag_csrf_and_immutable_scope(self):
        record = self.create()
        self.code(self.post(self.client, f"governance/rights/{record['id']}/assign/", {"reviewer_id": self.owner.pk}), "PRECONDITION_REQUIRED", 428)
        self.code(self.act(record, "assign", {"reviewer_id": self.owner.pk}, version=0), "STALE_REVISION", 412)
        for values in ({"resource_id": self.disorder.pk + 1}, {"material": "item"}, {"assignee_id": self.owner.pk}, {"authorization_status": "authorized"}):
            self.code(self.patch_record(record, values), "INVALID_FIELDS", 400)
        response = self.client.patch(BASE + f"governance/rights/{record['id']}/", json.dumps({"status": "restricted"}), content_type="application/json", HTTP_IF_MATCH='"1"')
        self.code(response, "CSRF_FAILED")

    def test_domain_scoping_prevents_detail_history_lookup_and_count_leaks(self):
        record = self.create()
        client = self.signed(self.scoped)
        for suffix in ("", "history/", "reviewers/"):
            self.assertEqual(client.get(BASE + f"governance/rights/{record['id']}/" + suffix).status_code, 404)
        self.assertEqual(client.get(BASE + "governance/resources/?resource_type=disorder").status_code, 404)
        response = client.get(BASE + "governance/rights/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)
        self.assertNotIn(self.rights_source.title, response.content.decode())
        self.assertEqual(client.get(BASE + "governance/evidence/").status_code, 403)
        self.assertEqual(self.act(record, "reopen", client=client).status_code, 404)

    def test_generic_decide_or_wrong_domain_is_insufficient(self):
        generic = self.user("generic", staff=True, caps=("cms_enter", "cms_core_view", "cms_rights_decide", "cms_review_decide_brain_rights"))
        record = self.create()
        self.code(self.act(record, "assign", {"reviewer_id": generic.pk}, client=self.signed(generic)), "PERMISSION_DENIED")
        self.code(self.act(record, "assign", {"reviewer_id": generic.pk}), "INVALID_REVIEWER", 400)

    def test_current_assignee_and_solo_owner_ack_are_required(self):
        record = self.create()
        record = self.good(self.act(record, "assign", {"reviewer_id": self.owner.pk}))
        data = {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED", "self_review_ack": False}
        self.code(self.act(record, "decide", data), "SELF_REVIEW_ACK_REQUIRED", 400)
        self.code(self.act(record, "decide", {**data, "self_review_ack": True}, client=self.signed(self.reviewer)), "REVIEWER_CONFLICT", 409)
        record = self.good(self.act(record, "decide", {**data, "self_review_ack": True}))
        decision = GovernanceDecision.objects.filter(record_id=record["id"], outcome="approve").get()
        self.assertTrue(decision.self_review)
        self.assertEqual(decision.revision.payload_digest, decision.revision_hash)

    def test_two_person_excludes_all_contributors_including_owner(self):
        ReviewPolicy.objects.filter(pk=1).update(mode="two_person", version=1)
        record = self.create()
        self.code(self.act(record, "assign", {"reviewer_id": self.owner.pk}), "TWO_PERSON_REQUIRED", 409)
        record = self.good(self.patch_record(record, {"limitations": "Synthetic edited limitation"}, client=self.signed(self.reviewer)))
        self.code(self.act(record, "assign", {"reviewer_id": self.reviewer.pk}), "TWO_PERSON_REQUIRED", 409)
        independent = self.user("independent-reviewer", staff=True, caps=CAPS)
        record = self.approve(record, independent, ack=False)
        self.assertTrue(self.rights_result(record)["permitted"])

    def test_policy_toggle_does_not_revive_old_approval(self):
        record = self.approve(self.create())
        ReviewPolicy.objects.filter(pk=1).update(mode="two_person", version=1)
        self.assertIn("POLICY_CHANGED", self.rights_result(record)["blockers"])
        ReviewPolicy.objects.filter(pk=1).update(mode="solo_owner", version=2)
        self.assertFalse(self.rights_result(record)["eligible"])

    def test_live_reviewer_revocation_and_session_revocation_fail_closed(self):
        record = self.approve(self.create(), self.reviewer, False)
        self.reviewer.user_permissions.remove(*Permission.objects.filter(codename="cms_review_decide_core_rights"))
        self.assertIn("REVIEWER_PERMISSION_CHANGED", self.rights_result(record)["blockers"])
        pending = self.create()
        session_id = self.client.session["cms_session_id"]
        AdminSession.objects.filter(pk=session_id).update(revoked_at=timezone.now())
        response = self.act(pending, "assign", {"reviewer_id": self.owner.pk})
        self.code(response, "UNAUTHENTICATED")

    def test_all_source_canonical_fields_and_source_lifecycle_are_bound(self):
        record = self.approve(self.create())
        original = governance_dependency_snapshot([self.rights_source.pk])
        for field, value in (("organization", "Synthetic org"), ("authors", ["Synthetic author"]), ("metadata", {"fixture_only": "changed"})):
            setattr(self.rights_source, field, value)
            self.rights_source.save()
            self.assertNotEqual(original["digest"], governance_dependency_snapshot([self.rights_source.pk])["digest"])
            self.assertFalse(self.rights_result(record)["eligible"])
        reopened = self.good(self.act(record, "reopen"))
        reopened = self.approve(reopened)
        self.assertTrue(self.rights_result(reopened)["permitted"])
        SourceState.objects.create(source_pk=self.rights_source.pk, archived=True, version=1)
        self.assertIn("SOURCE_UNAVAILABLE", self.rights_result(reopened)["blockers"])
        denied = self.post(self.client, "governance/rights/", self.proposal())
        self.code(denied, "SOURCE_UNAVAILABLE", 409)

    def test_source_successor_lineage_alone_invalidates_exact_approval(self):
        record = self.approve(self.create())
        successor = self.make_source("successor")
        plan = SourcePlan.objects.create(operation="successor", source_pk=self.rights_source.pk, fingerprint="a" * 64,
            actor=self.owner, actor_ref="fixture")
        SourceSuccessor.objects.create(source_pk=self.rights_source.pk, successor_pk=successor.pk, plan=plan, operation="successor")
        self.assertIn("DEPENDENCY_CHANGED", self.rights_result(record)["blockers"])

    def test_missing_evidence_cannot_approve_or_remain_eligible(self):
        record = self.approve(self.create())
        self.rights_source.delete()
        self.assertIn("EVIDENCE_MISSING", self.rights_result(record)["blockers"])
        response = self.post(self.client, "governance/rights/", self.proposal())
        self.code(response, "INVALID_EVIDENCE", 400)

    def test_target_governance_changes_snapshot_without_scientific_evidence_overlap(self):
        source_only = governance_dependency_snapshot([self.source.pk])
        before = governance_dependency_snapshot([self.source.pk], resource_type="disorder", resource_id=self.disorder.pk)
        record = self.create()
        submitted = governance_dependency_snapshot([self.source.pk], resource_type="disorder", resource_id=self.disorder.pk)
        self.assertEqual(source_only["digest"], governance_dependency_snapshot([self.source.pk])["digest"])
        self.assertNotEqual(before["digest"], submitted["digest"])
        record = self.approve(record)
        approved = governance_dependency_snapshot([self.source.pk], resource_type="disorder", resource_id=self.disorder.pk)
        self.assertNotEqual(submitted["digest"], approved["digest"])
        self.good(self.act(record, "revoke", {"reason": "CORRECTION_REQUIRED"}))
        self.assertNotEqual(approved["digest"], governance_dependency_snapshot([self.source.pk], resource_type="disorder", resource_id=self.disorder.pk)["digest"])

    def assessment_form(self):
        instrument = AssessmentInstrument.objects.create(slug="non-scientific-fixture", name_en="NON-SCIENTIFIC instrument")
        version = AssessmentVersion.objects.create(instrument=instrument, key="fixture-v1", label="NON-SCIENTIFIC version", form_kind="original")
        form = AssessmentLanguageForm.objects.create(version=version, key="fixture-fa", language="fa", label="NON-SCIENTIFIC language label", form_kind="translation")
        return instrument, version, form

    def test_stable_assessment_version_separately_binds_target_digest(self):
        _, version, _ = self.assessment_form()
        before = resource_binding("assessment_version", version.pk)
        self.assertEqual(before["resource_version"], "fixture-v1")
        record = self.approve(self.create(data=self.proposal(resource_type="assessment_version", resource_id=version.pk)))
        version.label = "NON-SCIENTIFIC mutated version label"
        version.save()
        after = resource_binding("assessment_version", version.pk)
        self.assertEqual(before["resource_version"], after["resource_version"])
        self.assertNotEqual(before["resource_digest"], after["resource_digest"])
        self.assertIn("RESOURCE_CHANGED", self.rights_result(record)["blockers"])

    def test_terminology_exact_approval_rtl_alias_and_no_assessment_escalation(self):
        _, _, form = self.assessment_form()
        before = (form.label, form.authorization_status, form.review_status)
        record = self.approve(self.create("terminology", data=self.proposal("terminology", resource_type="assessment_language_form", resource_id=form.pk)))
        self.assertTrue(record["eligible"])
        self.assertEqual(record["preview"]["dir"], "rtl")
        self.assertEqual(record["preview"]["name_en_dir"], "ltr")
        self.assertEqual(record["term_kind"], "display")
        alias = self.create("terminology", term_kind="alias")
        self.assertEqual(alias["term_kind"], "alias")
        self.good(self.act(record, "reopen"))
        form.refresh_from_db()
        self.assertEqual((form.label, form.authorization_status, form.review_status), before)
        self.assertEqual(form.authorization_status, "unknown")
        self.assertEqual(form.review_status, "unreviewed")
        self.assertEqual(GovernanceDecision.objects.filter(record_id=record["id"], outcome="approve").count(), 1)

    def test_terminology_source_target_policy_and_reviewer_changes_are_stale(self):
        record = self.approve(self.create("terminology"), self.reviewer, False)
        self.rights_source.citation = "NON-SCIENTIFIC changed term evidence"
        self.rights_source.save()
        response = self.client.get(BASE + f"governance/terminology/{record['id']}/")
        self.assertFalse(response.json()["record"]["eligible"])
        self.assertIn("DEPENDENCY_CHANGED", response.json()["record"]["blockers"])
        reopened = self.good(self.act(record, "reopen"))
        changed = self.good(self.patch_record(reopened, {"name_fa": "نام ساختگی جدید"}))
        self.assertFalse(changed["eligible"])
        approved = self.approve(changed, self.reviewer, False)
        self.disorder.overview = "NON-SCIENTIFIC changed target"
        self.disorder.save()
        self.assertFalse(self.client.get(BASE + f"governance/terminology/{approved['id']}/").json()["record"]["eligible"])

    def test_plain_text_preview_and_same_domain_candidate_conflicts(self):
        other = Disorder.objects.create(category=self.category, slug="non-scientific-other", name_en="NON-SCIENTIFIC other")
        first = self.create("terminology", name_fa="<script>fixture only</script>")
        second = self.create("terminology", data=self.proposal("terminology", resource_id=other.pk, name_fa="<script>fixture only</script>"))
        self.assertEqual(second["preview"]["name_fa"], "<script>fixture only</script>")
        self.assertEqual(second["candidate_conflicts"][0]["id"], first["id"])
        self.assertEqual(second["candidate_conflicts"][0]["resource_type"], "disorder")

    def test_append_only_history_actor_erasure_and_audit_rollback(self):
        record = self.approve(self.create(), self.reviewer, False)
        decision = GovernanceDecision.objects.get(record_id=record["id"], outcome="approve")
        actor_ref = decision.actor_ref
        for model in (GovernanceRevision, GovernanceDecision):
            with self.assertRaises(ValidationError):
                model.objects.filter(pk=model.objects.first().pk).update(reason="CORRECTION_REQUIRED")
            with self.assertRaises(ValidationError):
                model.objects.first().delete()
        before = (GovernanceRecord.objects.count(), GovernanceRevision.objects.count())
        with patch("atlas.cms_governance.AdminAuditEvent.objects.create", side_effect=DatabaseError("synthetic failure")):
            response = self.post(self.client, "governance/rights/", self.proposal())
        self.code(response, "AUDIT_UNAVAILABLE", 503)
        self.assertEqual((GovernanceRecord.objects.count(), GovernanceRevision.objects.count()), before)
        self.reviewer.delete()
        decision.refresh_from_db()
        self.assertIsNone(decision.actor_id)
        self.assertEqual(decision.actor_ref, actor_ref)
        self.assertFalse(self.rights_result(record)["eligible"])
        history = self.client.get(BASE + f"governance/rights/{record['id']}/history/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["count"], 3)
        self.assertNotIn("governance-reviewer", history.content.decode())

    def test_mutable_status_alone_never_grants_permission(self):
        record = self.create()
        GovernanceRecord.objects.filter(pk=record["id"]).update(status="approved", assignee=self.owner)
        result = self.rights_result(record)
        self.assertFalse(result["permitted"])
        self.assertEqual(result["status"], "legacy")
        self.assertFalse(self.client.get(BASE + f"governance/rights/{record['id']}/").json()["record"]["eligible"])

    def test_same_version_concurrent_decisions_commit_once(self):
        if connection.vendor != "postgresql":
            self.skipTest("Real PostgreSQL separate connections required")
        record = self.create()
        record = self.good(self.act(record, "assign", {"reviewer_id": self.owner.pk}))
        actor_id, session_id = self.owner.pk, self.client.session["cms_session_id"]
        barrier = Barrier(2)
        def decide():
            close_old_connections()
            barrier.wait(timeout=10)
            try:
                mutate_governance(actor_id, session_id, "rights", uuid.UUID(record["id"]), record["version"], "decide",
                    {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED", "self_review_ack": True}, uuid.uuid4())
                return "ok"
            except Exception as error:
                return str(getattr(error, "detail", {}).get("code", type(error).__name__))
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: decide(), range(2)))
        self.assertCountEqual(outcomes, ["ok", "STALE_REVISION"])
        self.assertEqual(GovernanceDecision.objects.filter(record_id=record["id"], outcome="approve").count(), 1)
