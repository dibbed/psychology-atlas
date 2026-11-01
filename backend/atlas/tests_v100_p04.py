"""P04 acceptance: real MFA sessions/CSRF, immutable evidence, rollback and races."""
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, close_old_connections, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from .cms_content import canonical_snapshot, digest
from .cms_content_models import ContentRevision, ContentState
from .cms_models import AdminAuditEvent, AdminSession, RolePolicy
from .cms_policy import CMSFailure, effective_permissions, mutate_role, policy_lock
from .cms_review import checked_evidence, decide_review, subject_hash
from .cms_review_models import ReviewDecision, ReviewPolicy, ReviewPolicyRevision, ReviewTask
from .models import Category, Disorder, DisorderSource, ScientificReviewStatus, SourceReference
from .tests_v100_p01 import BASE
from .tests_v100_p02 import ContentFixture


SOURCE_CAP = "cms_review_decide_core_source"
SCIENCE_CAP = "cms_review_decide_core_scientific"
REVIEW_CAPS = ("cms_enter", "cms_core_view", SOURCE_CAP, SCIENCE_CAP)


class ReviewFixture(ContentFixture):
    def setUp(self):
        super().setUp()
        # TransactionTestCase flush removes the singleton initialized by 0040.
        ReviewPolicy.objects.get_or_create(pk=1)
        self.source = self.make_source("Synthetic cited source")
        self.source_reviewer = self.user("source-reviewer", staff=True, caps=REVIEW_CAPS)
        self.science_reviewer = self.user("science-reviewer", staff=True, caps=REVIEW_CAPS)
        self.editor = self.user("editor", staff=True,
            caps=(*REVIEW_CAPS, "cms_core_edit", "cms_core_submit"))
        self.clients = {self.owner.pk: self.client}

    def make_source(self, title, **values):
        return SourceReference.objects.create(title=title, citation="Synthetic citation only",
            url="https://example.org", verification_status="source_checked", **values)

    def signed(self, user):
        if user.pk not in self.clients:
            self.clients[user.pk] = self.sign_in(user)
        return self.clients[user.pk]

    def review_path(self, state=None, suffix=""):
        state = state or self.state
        return f"reviews/{state.kind}/{state.pk}/" + suffix

    def detail(self, state=None, client=None):
        response = (client or self.client).get(BASE + self.review_path(state))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        return response.json()

    def action(self, action, data=None, state=None, client=None, version=None):
        state = state or self.state
        state.refresh_from_db()
        return self.post(client or self.client, self.review_path(state, action + "/"), data,
            etag='"%s"' % (state.version if version is None else version))

    def ok(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        if "record" in response.json():
            self.assertEqual(response["ETag"], '"%s"' % response.json()["record"]["version"])
        return response.json()

    def draft(self, state=None, client=None, values=None):
        state = state or self.state
        state.refresh_from_db()
        response = self.post(client or self.client, f"content/{state.kind}/{state.pk}/revisions/",
            {"payload": values or {"name_fa": "Synthetic proposal"}, "base_digest": state.canonical_digest},
            etag='"%s"' % state.version)
        self.ok(response)
        state.refresh_from_db()
        return state.current_revision

    def evidence(self, state=None):
        state = state or self.state
        state.refresh_from_db()
        return [{"source_id": self.source.pk, "locator": "Synthetic section 1",
            "fields": [key for key, value in state.current_revision.payload.items() if value]}]

    def submit(self, state=None, evidence=None, client=None):
        return self.ok(self.action("submit", {"evidence": self.evidence(state) if evidence is None else evidence},
            state=state, client=client))

    def task(self, review_type, state=None):
        state = state or self.state
        return ReviewTask.objects.filter(subject__state=state, review_type=review_type).order_by("-pk").first()

    def assign(self, review_type, reviewer=None, state=None):
        reviewer = reviewer or (self.source_reviewer if review_type == "source" else self.science_reviewer)
        task = self.task(review_type, state)
        return self.action("assign", {"task_id": task.pk, "task_version": task.version,
            "reviewer_id": reviewer.pk}, state=state)

    def decide(self, review_type, user=None, state=None, **values):
        user = user or (self.source_reviewer if review_type == "source" else self.science_reviewer)
        task = self.task(review_type, state)
        return self.action("decide", {"task_id": task.pk, "task_version": task.version,
            "outcome": "approve", "reason": "SOURCE_VERIFIED" if review_type == "source" else "SCIENCE_VERIFIED",
            "fields": [], **values}, state=state, client=self.signed(user))

    def prepared(self, state=None):
        self.draft(state)
        self.submit(state)
        self.ok(self.assign("source", state=state))
        self.ok(self.assign("scientific", state=state))

    def approved(self, state=None):
        self.prepared(state)
        self.ok(self.decide("source", state=state))
        return self.ok(self.decide("scientific", state=state))

    def policy_change(self, mode, reason="TEAM_POLICY"):
        data = {"mode": mode, "reason": reason}
        self.step_up(self.client, self.owner, "review_policy", 1, data)
        policy = ReviewPolicy.objects.get(pk=1)
        return self.post(self.client, "reviews/policy/", data, etag='"%s"' % policy.version)

    def snapshot(self):
        return {
            "states": list(ContentState.objects.order_by("pk").values()),
            "revisions": list(ContentRevision.objects.order_by("pk").values()),
            "tasks": list(ReviewTask.objects.order_by("pk").values()),
            "decisions": list(ReviewDecision.objects.order_by("pk").values()),
            "policy": list(ReviewPolicy.objects.values()),
            "policy_history": list(ReviewPolicyRevision.objects.order_by("pk").values()),
            "success_audits": list(AdminAuditEvent.objects.filter(outcome="success").order_by("pk").values()),
            "category": canonical_snapshot("category", Category.objects.get(pk=self.category.pk)),
            "disorder": canonical_snapshot("disorder", Disorder.objects.get(pk=self.disorder.pk)),
        }


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReviewAPITests(ReviewFixture, TransactionTestCase):
    def test_source_then_science_approves_each_kind_without_publishing(self):
        for state, obj in ((self.state, self.disorder), (self.category_state, self.category)):
            with self.subTest(kind=state.kind):
                before = canonical_snapshot(state.kind, obj)
                subject = self.draft(state)
                submitted = self.submit(state)
                self.assertEqual(submitted["record"]["revision_status"], "submitted")
                self.assertEqual(submitted["scientific_status"], ScientificReviewStatus.UNREVIEWED)
                tasks = ReviewTask.objects.filter(subject=subject)
                self.assertCountEqual(tasks.values_list("review_type", flat=True), ["source", "scientific"])
                self.assertTrue(all(task.status == "queued" and task.version == 0 for task in tasks))
                self.ok(self.assign("source", state=state))
                self.ok(self.assign("scientific", state=state))
                self.code(self.decide("scientific", state=state), "SOURCE_CHECK_REQUIRED", 409)
                checked = self.ok(self.decide("source", state=state))
                self.assertEqual(checked["scientific_status"], ScientificReviewStatus.SOURCE_CHECKED)
                self.assertFalse(checked["approval"]["eligible"])
                approved = self.ok(self.decide("scientific", state=state))
                self.assertEqual(approved["scientific_status"], ScientificReviewStatus.REVIEWED)
                self.assertEqual(approved["record"]["revision_status"], "approved")
                self.assertEqual(approved["approval"], {"eligible": True, "blockers": []})
                self.assertEqual(approved["record"]["publication"], "pending_update")
                obj.refresh_from_db()
                self.assertEqual(canonical_snapshot(state.kind, obj), before)
                self.assertEqual(tasks.count(), 2)
                self.assertEqual(ReviewDecision.objects.filter(task__subject=subject, outcome="approve").count(), 2)

    def test_decision_history_is_append_only_hash_bound_and_retained_after_actor_erasure(self):
        self.approved()
        rows = list(ReviewDecision.objects.filter(task__subject__state=self.state).order_by("pk"))
        self.assertEqual([row.outcome for row in rows], ["assigned", "assigned", "approve", "approve"])
        for row in rows:
            subject = row.task.subject
            self.assertEqual(row.revision_hash, subject_hash(subject))
            self.assertEqual(row.dependency_digest, row.task.dependency_digest)
            self.assertEqual(row.evidence, row.task.evidence)
            self.assertEqual((row.policy_mode, row.policy_version), ("solo_owner", 0))
            self.assertRegex(row.actor_ref, r"^[0-9a-f]{64}$")
            self.assertRegex(row.assignee_ref, r"^[0-9a-f]{64}$")
            self.assertFalse(row.self_review)
            previous = next((item for item in reversed(rows) if item.task_id == row.task_id and item.pk < row.pk), None)
            self.assertEqual(row.supersedes_id, previous.pk if previous else None)
        decision = rows[-1]
        before = ReviewDecision.objects.filter(pk=decision.pk).values().get()
        for write in (
            lambda: decision.save(), lambda: decision.delete(),
            lambda: ReviewDecision.objects.filter(pk=decision.pk).update(reason="CORRECTION_REQUIRED"),
            lambda: ReviewDecision.objects.filter(pk=decision.pk).delete(),
            lambda: ReviewDecision.objects.bulk_update([decision], ["reason"]),
            lambda: ReviewDecision.objects.bulk_create([decision]),
        ):
            with self.assertRaises(ValidationError):
                write()
        self.assertEqual(ReviewDecision.objects.filter(pk=decision.pk).values().get(), before)
        history = self.client.get(BASE + self.review_path(suffix="history/")).json()["results"]
        self.assertEqual([row["id"] for row in history], [row.pk for row in reversed(rows)])
        actor_ref, assignee_ref = decision.actor_ref, decision.assignee_ref
        self.science_reviewer.delete()
        decision.refresh_from_db()
        self.assertIsNone(decision.actor_id)
        self.assertEqual((decision.actor_ref, decision.assignee_ref), (actor_ref, assignee_ref))
        self.assertEqual(ReviewDecision.objects.count(), 4)
        self.assertIn("REVIEWER_UNAVAILABLE", self.detail()["approval"]["blockers"])

    def test_legacy_is_unreviewed_and_cannot_submit_or_auto_create_decisions(self):
        for state in (self.state, self.category_state):
            with self.subTest(kind=state.kind):
                detail = self.detail(state)
                self.assertEqual(detail["record"]["revision_status"], "legacy")
                self.assertEqual(detail["scientific_status"], "unreviewed")
                self.assertFalse(detail["approval"]["eligible"])
                self.code(self.action("submit", {"evidence": self.evidence(state)}, state=state), "INVALID_TRANSITION", 409)
                self.code(self.action("reopen", state=state), "INVALID_TRANSITION", 409)
                self.assertEqual(state.revisions.count(), 1)
        self.assertFalse(ReviewTask.objects.exists())
        self.assertFalse(ReviewDecision.objects.exists())

    def test_transition_matrix_rejects_queued_decisions_duplicate_submit_and_terminal_writes(self):
        self.draft()
        self.code(self.action("reopen"), "INVALID_TRANSITION", 409)
        self.submit()
        self.code(self.action("submit", {"evidence": self.evidence()}), "INVALID_TRANSITION", 409)
        self.code(self.decide("source"), "REVIEWER_CONFLICT", 409)
        self.code(self.save_proposal({"name_en": "Synthetic forbidden"}, version=self.state.version), "INVALID_TRANSITION", 409)
        self.ok(self.assign("source"))
        self.ok(self.assign("scientific"))
        self.code(self.action("submit", {"evidence": self.evidence()}), "INVALID_TRANSITION", 409)
        self.ok(self.decide("source"))
        self.code(self.decide("source"), "INVALID_TRANSITION", 409)
        self.ok(self.decide("scientific"))
        for response in (self.assign("source"), self.decide("scientific"),
            self.action("submit", {"evidence": self.evidence()}),
            self.save_proposal({"name_en": "Synthetic forbidden"}, version=self.state.version)):
            self.code(response, "INVALID_TRANSITION", 409)
        self.draft(self.category_state)
        self.category_state.refresh_from_db()
        self.code(self.post(self.client, f"content/category/{self.category_state.pk}/discard/",
            {"base_digest": self.category_state.canonical_digest}, etag='"%s"' % self.category_state.version), "INVALID_TRANSITION", 409)
        created = self.post(self.client, "content/category/", {"payload": {"name_en": "Synthetic discardable draft"}})
        self.assertEqual(created.status_code, 201, created.content)
        state = ContentState.objects.get(pk=created.json()["id"])
        self.assertIsNone(state.canonical_pk)
        self.ok(self.post(self.client, f"content/category/{state.pk}/discard/",
            {"base_digest": state.canonical_digest}, etag='"%s"' % state.version))
        self.code(self.action("submit", {"evidence": self.evidence(state)}, state=state), "INVALID_TRANSITION", 409)
        self.code(self.action("reopen", state=state), "INVALID_TRANSITION", 409)

    def test_rejection_requires_reason_and_fields_then_new_draft_before_resubmission(self):
        self.prepared()
        self.signed(self.source_reviewer)
        before = self.snapshot()
        cases = (
            {"reason": None, "fields": ["overview"]}, {"reason": "", "fields": ["overview"]},
            {"reason": "Synthetic private reason", "fields": ["overview"]},
            {"reason": {"note": "Synthetic private reason"}, "fields": ["overview"]},
            {"reason": "CORRECTION_REQUIRED", "fields": []},
        )
        for values in cases:
            with self.subTest(values=values):
                response = self.decide("source", outcome="reject", **values)
                self.code(response, "REJECTION_REASON_REQUIRED", 400)
                self.assertNotIn("Synthetic private", response.content.decode())
                self.assertEqual(self.snapshot(), before)
        for fields in (["is_active"], [True], "overview", {"overview": True}):
            self.code(self.decide("source", outcome="reject", reason="CORRECTION_REQUIRED", fields=fields), "INVALID_FIELDS", 400)
        old_subject = self.task("source").subject_id
        rejected = self.ok(self.decide("source", outcome="reject", reason="CORRECTION_REQUIRED", fields=["overview"]))
        self.assertEqual(rejected["record"]["revision_status"], "changes_requested")
        self.assertEqual(self.task("source").status, "rejected")
        self.assertEqual(self.task("scientific").status, "cancelled")
        self.code(self.action("submit", {"evidence": self.evidence()}), "INVALID_TRANSITION", 409)
        self.code(self.action("reopen"), "INVALID_TRANSITION", 409)
        self.draft(values={"overview": "Synthetic correction"})
        self.submit()
        self.assertNotEqual(self.task("source").subject_id, old_subject)
        self.assertEqual(ReviewTask.objects.filter(subject__state=self.state).count(), 4)
        self.assertEqual(ReviewDecision.objects.filter(task__subject_id=old_subject).count(), 3)
        decision = ReviewDecision.objects.get(outcome="reject")
        self.assertEqual((decision.reason, decision.fields), ("CORRECTION_REQUIRED", ["overview"]))
        task = self.task("source")
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReviewTask.objects.create(subject=task.subject, review_type="source", revision_hash=task.revision_hash,
                dependency_digest=task.dependency_digest, evidence=task.evidence, policy_version=0, policy_mode="solo_owner")

    def test_reopen_approved_appends_two_versions_cancels_tasks_and_preserves_history(self):
        self.approved()
        self.state.refresh_from_db()
        version = self.state.version
        old_revision_ids = list(self.state.revisions.values_list("pk", flat=True))
        history = list(ReviewDecision.objects.order_by("pk").values())
        tasks = list(ReviewTask.objects.order_by("pk").values("pk", "version"))
        reopened = self.ok(self.action("reopen"))
        self.assertEqual(reopened["record"]["version"], version + 2)
        self.assertEqual(list(self.state.revisions.filter(sequence__gt=version).order_by("sequence").values_list("status", flat=True)), ["superseded", "draft"])
        self.assertEqual(list(self.state.revisions.filter(sequence__lte=version).values_list("pk", flat=True)), old_revision_ids)
        self.assertEqual(list(ReviewDecision.objects.filter(pk__in=[row["id"] for row in history]).order_by("pk").values()), history)
        for old in tasks:
            task = ReviewTask.objects.get(pk=old["pk"])
            self.assertEqual((task.status, task.version), ("cancelled", old["version"] + 1))
            invalidated = task.decisions.latest("pk")
            self.assertEqual(invalidated.outcome, "invalidated")
            self.assertEqual(invalidated.supersedes.outcome, "approve")
        self.assertEqual(reopened["scientific_status"], "unreviewed")
        self.assertFalse(reopened["approval"]["eligible"])
        self.state.refresh_from_db()
        new_subject = self.state.current_revision_id
        self.submit()
        self.assertEqual(ReviewTask.objects.filter(subject_id=new_subject).count(), 2)
        self.assertEqual(ReviewTask.objects.count(), 4)
        self.code(self.action("decide", {"task_id": tasks[0]["pk"], "task_version": tasks[0]["version"],
            "outcome": "approve", "reason": "SOURCE_VERIFIED"}), "NOT_FOUND", 404)

    def test_reopen_pending_appends_one_draft_and_keeps_assignment_decisions(self):
        self.prepared()
        self.state.refresh_from_db()
        version = self.state.version
        assignments = list(ReviewDecision.objects.order_by("pk").values())
        self.ok(self.action("reopen"))
        self.state.refresh_from_db()
        self.assertEqual(self.state.version, version + 1)
        self.assertEqual(self.state.current_revision.status, "draft")
        self.assertFalse(self.state.revisions.filter(status="superseded").exists())
        self.assertEqual(list(ReviewDecision.objects.filter(outcome="assigned").order_by("pk").values()), assignments)
        self.assertEqual(ReviewDecision.objects.filter(outcome="reopened").count(), 2)
        self.assertEqual(set(ReviewTask.objects.values_list("status", flat=True)), {"cancelled"})

    def test_review_status_patch_and_arbitrary_protected_fields_fail_closed(self):
        before = self.snapshot()
        for field in ("review_status", "scientific_status", "is_active", "seed_managed", "slug", "category_id",
            "actor", "password", "model", "note"):
            with self.subTest(field=field):
                self.code(self.save_proposal({field: "Synthetic protected value"}), "INVALID_FIELDS", 400)
        csrf = self.csrf(self.client)
        for path in (self.review_path(), f"content/disorder/{self.state.pk}/"):
            response = self.client.patch(BASE + path, json.dumps({"review_status": "reviewed"}),
                content_type="application/json", HTTP_X_CSRFTOKEN=csrf, HTTP_IF_MATCH='"0"')
            self.assertEqual(response.status_code, 405, response.content)
        self.draft()
        for field in ("review_status", "actor_id", "payload", "policy_mode", "dependency_digest", "model"):
            self.code(self.action("submit", {"evidence": self.evidence(), field: "Synthetic private"}), "INVALID_FIELDS", 400)
        self.assertEqual(ReviewTask.objects.count(), 0)
        self.assertEqual(ReviewDecision.objects.count(), 0)
        self.assertEqual(self.snapshot()["disorder"], before["disorder"])

    def test_evidence_validates_shape_ids_allowed_fields_and_complete_coverage(self):
        self.draft()
        good = self.evidence()[0]
        for evidence, code in (
            (None, "EVIDENCE_REQUIRED"), ([], "EVIDENCE_REQUIRED"), ({}, "EVIDENCE_REQUIRED"),
            ([good] * 21, "EVIDENCE_REQUIRED"), ([None], "INVALID_EVIDENCE"),
            ([{**good, "source_id": True}], "INVALID_EVIDENCE"),
            ([{**good, "source_id": 2**63}], "INVALID_EVIDENCE"),
            ([{**good, "source_id": self.source.pk + 1000000}], "INVALID_EVIDENCE"),
            ([{**good, "locator": "   "}], "INVALID_EVIDENCE"),
            ([{**good, "fields": ["review_status"]}], "INVALID_EVIDENCE"),
            ([{**good, "fields": [True]}], "INVALID_EVIDENCE"),
            ([{**good, "fields": []}], "INVALID_EVIDENCE"),
            ([{**good, "note": "Synthetic protected note"}], "INVALID_EVIDENCE"),
            ([{**good, "fields": ["overview"]}], "EVIDENCE_COVERAGE_REQUIRED"),
        ):
            with self.subTest(evidence=evidence):
                self.code(self.action("submit", {"evidence": evidence}), code, 400)
                self.assertFalse(ReviewTask.objects.exists())
        normalized = {**good, "locator": "  Synthetic section 1  ", "fields": good["fields"] * 2}
        response = self.submit(evidence=[normalized])
        self.assertEqual(response["evidence"], [{**good, "fields": sorted(set(good["fields"]))}])

    def test_source_approval_checks_explicit_citations_without_requiring_inherited_links_resolved(self):
        inherited = self.make_source("Synthetic inherited source")
        inherited.verification_status = "unreviewed"
        inherited.save(update_fields=("verification_status",))
        DisorderSource.objects.create(disorder=self.disorder, source=inherited, note="Synthetic inherited link")
        self.prepared()
        self.ok(self.decide("source"))
        self.ok(self.decide("scientific"))
        self.assertTrue(self.detail()["approval"]["eligible"])
        self.ok(self.action("reopen"))
        self.submit(evidence=[{**self.evidence()[0], "source_id": inherited.pk}])
        self.ok(self.assign("source"))
        self.code(self.decide("source"), "SOURCE_UNRESOLVED", 409)
        self.assertEqual(self.task("source").status, "assigned")
        self.assertEqual(ReviewDecision.objects.filter(task=self.task("source"), outcome="approve").count(), 0)

    def test_source_disappearing_after_initial_evidence_check_rolls_back_submission_and_deletion(self):
        second = self.make_source("Synthetic disappearing cited source")
        self.draft()
        evidence = self.evidence()
        evidence.append({**evidence[0], "source_id": second.pk, "locator": "Synthetic section 2"})
        before = self.snapshot()
        source_before = SourceReference.objects.filter(pk=second.pk).values().get()

        def delete_after_initial_check(*args):
            checked = checked_evidence(*args)
            self.assertEqual({item["source_id"] for item in checked}, {self.source.pk, second.pk})
            deleted, _ = SourceReference.objects.filter(pk=second.pk).delete()
            self.assertEqual(deleted, 1)
            self.assertFalse(SourceReference.objects.filter(pk=second.pk).exists())
            return checked

        with patch("atlas.cms_review.checked_evidence", side_effect=delete_after_initial_check) as initial_check:
            response = self.action("submit", {"evidence": evidence})
        self.assertEqual(initial_check.call_count, 1)
        self.code(response, "INVALID_EVIDENCE", 400)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(SourceReference.objects.filter(pk=second.pk).values().get(), source_before)
        self.assertTrue(SourceReference.objects.filter(pk=self.source.pk).exists())
        self.assertFalse(ReviewTask.objects.exists())
        self.assertFalse(ReviewDecision.objects.exists())
        self.assertFalse(AdminAuditEvent.objects.filter(action="review.submitted", outcome="success").exists())
        denial = AdminAuditEvent.objects.get(request_id=response.json()["request_id"])
        self.assertEqual((denial.action, denial.outcome, denial.error_code),
            ("api.security_denial", "denied", "INVALID_EVIDENCE"))

    def test_deleting_explicit_source_after_approval_invalidates_eligibility_and_retains_history(self):
        second = self.make_source("Synthetic approved second cited source")
        self.draft()
        evidence = self.evidence()
        evidence.append({**evidence[0], "source_id": second.pk, "locator": "Synthetic section 2"})
        self.submit(evidence=evidence)
        self.ok(self.assign("source"))
        self.ok(self.assign("scientific"))
        self.ok(self.decide("source"))
        self.assertTrue(self.ok(self.decide("scientific"))["approval"]["eligible"])
        before = self.snapshot()
        history_url = BASE + self.review_path(suffix="history/")
        history = self.client.get(history_url).json()
        deleted, _ = SourceReference.objects.filter(pk=second.pk).delete()
        self.assertEqual(deleted, 1)
        detail = self.detail()
        self.assertFalse(detail["approval"]["eligible"])
        self.assertIn("EVIDENCE_MISSING", detail["approval"]["blockers"])
        self.assertEqual(detail["scientific_status"], "unreviewed")
        self.assertEqual(detail["record"]["revision_status"], "approved")
        self.assertEqual({task["status"] for task in detail["tasks"]}, {"approved"})
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.client.get(history_url).json(), history)
        self.assertEqual(ReviewDecision.objects.filter(outcome="approve").count(), 2)
        self.assertTrue(SourceReference.objects.filter(pk=self.source.pk).exists())
        self.assertFalse(SourceReference.objects.filter(pk=second.pk).exists())

    def test_owner_self_review_requires_explicit_boolean_ack_and_records_it(self):
        self.draft()
        self.submit()
        self.ok(self.assign("source", self.owner))
        for ack in (False, None, "true", 1):
            with self.subTest(ack=ack):
                self.code(self.decide("source", self.owner, self_review_ack=ack), "SELF_REVIEW_ACK_REQUIRED", 400)
        self.ok(self.decide("source", self.owner, self_review_ack=True))
        self.ok(self.assign("scientific", self.owner))
        self.code(self.decide("scientific", self.owner), "SELF_REVIEW_ACK_REQUIRED", 400)
        approved = self.ok(self.decide("scientific", self.owner, self_review_ack=True))
        self.assertTrue(approved["approval"]["eligible"])
        self.assertEqual(list(ReviewDecision.objects.filter(outcome="approve").values_list("self_review", flat=True)), [True, True])

    def test_nonowner_prior_contributor_cannot_review_even_after_another_editor_takes_over(self):
        self.draft(client=self.signed(self.editor))
        prior = self.state.current_revision_id
        self.draft(values={"name_fa": "Synthetic owner continuation"})
        self.submit()
        self.assertNotEqual(self.task("source").subject_id, prior)
        self.assertCountEqual(self.task("source").authors, [self.owner.pk, self.editor.pk])
        for review_type in ("source", "scientific"):
            self.code(self.assign(review_type, self.editor), "REVIEWER_CONFLICT", 409)
        self.ok(self.assign("source"))
        self.ok(self.decide("source"))

    def test_two_person_policy_prevents_owner_superuser_and_any_prior_contributor_bypass(self):
        self.ok(self.policy_change("two_person"))
        superuser = self.user("synthetic-superuser", staff=True)
        superuser.is_superuser = True
        superuser.save(update_fields=("is_superuser",))
        for user in (self.editor, superuser, self.owner):
            self.draft(client=self.signed(user), values={"name_fa": "Synthetic contributor " + user.username})
        self.submit()
        self.assertCountEqual(self.task("source").authors, [self.editor.pk, superuser.pk, self.owner.pk])
        for user in (self.owner, superuser, self.editor):
            for review_type in ("source", "scientific"):
                with self.subTest(user=user.username, review_type=review_type):
                    self.code(self.assign(review_type, user), "TWO_PERSON_REQUIRED", 409)
        self.ok(self.assign("source"))
        self.ok(self.assign("scientific"))
        self.ok(self.decide("source"))
        self.assertTrue(self.ok(self.decide("scientific"))["approval"]["eligible"])

    def test_wrong_assignee_review_type_and_boolean_task_ids_cannot_decide(self):
        self.prepared()
        source_only = self.user("synthetic-source-only", staff=True, caps=("cms_enter", "cms_core_view", SOURCE_CAP))
        self.signed(self.science_reviewer)
        self.signed(source_only)
        before = self.snapshot()
        self.code(self.decide("source", self.science_reviewer), "REVIEWER_CONFLICT", 409)
        self.code(self.decide("scientific", source_only), "PERMISSION_DENIED")
        for task_id in (True, False, "1", self.task("source").pk + 100000):
            self.code(self.action("decide", {"task_id": task_id, "task_version": 1,
                "outcome": "approve", "reason": "SOURCE_VERIFIED"}), "NOT_FOUND", 404)
        for reviewer_id in (True, str(self.source_reviewer.pk), self.normal.pk, self.staff.pk):
            task = self.task("source")
            self.code(self.action("assign", {"task_id": task.pk, "task_version": task.version,
                "reviewer_id": reviewer_id}), "INVALID_REVIEWER", 400)
        self.assertEqual(self.snapshot(), before)

    def test_task_version_and_content_if_match_are_independent_preconditions(self):
        self.prepared()
        self.state.refresh_from_db()
        task = self.task("source")
        data = {"task_id": task.pk, "task_version": task.version, "outcome": "approve", "reason": "SOURCE_VERIFIED"}
        client = self.signed(self.source_reviewer)
        self.code(self.post(client, self.review_path(suffix="decide/"), data), "PRECONDITION_REQUIRED", 428)
        for etag in ("0", 'W/"0"', '"-1"', '"true"'):
            self.code(self.post(client, self.review_path(suffix="decide/"), data, etag=etag), "INVALID_PRECONDITION", 400)
        self.code(self.action("decide", data, client=client, version=self.state.version - 1), "STALE_REVISION", 412)
        for task_version in (task.version - 1, True, str(task.version), None):
            self.code(self.action("decide", {**data, "task_version": task_version}, client=client), "STALE_DECISION", 412)
        self.ok(self.action("decide", data, client=client))
        self.code(self.action("decide", data, client=client, version=self.state.version - 1), "STALE_REVISION", 412)
        self.assertEqual(ReviewDecision.objects.filter(outcome="approve").count(), 1)

    def test_policy_requires_owner_settings_authority_and_preserves_append_only_history(self):
        settings_user = self.user("synthetic-settings", staff=True, caps=("cms_enter", "cms_core_view", "cms_settings_edit"))
        self.assertIn("cms_settings_edit", effective_permissions(settings_user))
        self.assertNotIn("cms_owner", effective_permissions(settings_user))
        data = {"mode": "two_person", "reason": "TEAM_POLICY"}
        for user in (settings_user, self.source_reviewer):
            client = self.signed(user)
            self.code(self.post(client, "reviews/policy/", data, etag='"0"'), "PERMISSION_DENIED")
            self.code(self.post(client, "auth/step-up/", {"method": "recovery", "token": self.backup(user),
                "action": "review_policy", "target_id": 1, "payload": data}), "PERMISSION_DENIED")
        self.assertEqual(ReviewPolicy.objects.get(pk=1).version, 0)
        self.ok(self.policy_change("two_person"))
        revision = ReviewPolicyRevision.objects.get(version=1)
        self.assertEqual((revision.previous_mode, revision.mode, revision.reason, revision.actor_id),
            ("solo_owner", "two_person", "TEAM_POLICY", self.owner.pk))
        for write in (lambda: revision.save(), lambda: revision.delete(),
            lambda: ReviewPolicyRevision.objects.filter(pk=revision.pk).update(mode="solo_owner"),
            lambda: ReviewPolicyRevision.objects.filter(pk=revision.pk).delete()):
            with self.assertRaises(ValidationError):
                write()
        self.assertEqual(AdminAuditEvent.objects.get(action="review.policy").diff, ["mode"])

    def test_policy_step_up_binds_session_target_payload_reason_and_is_consumed_once(self):
        data = {"mode": "two_person", "reason": "TEAM_POLICY"}
        self.code(self.post(self.client, "reviews/policy/", data, etag='"0"'), "STEP_UP_REQUIRED")
        self.code(self.post(self.client, "auth/step-up/", {"method": "recovery", "token": self.backup(self.owner),
            "action": "review_policy", "target_id": 2, "payload": data}), "NOT_FOUND", 404)
        self.step_up(self.client, self.owner, "user", self.owner.pk, data)
        self.code(self.post(self.client, "reviews/policy/", data, etag='"0"'), "STEP_UP_REQUIRED")
        self.step_up(self.client, self.owner, "review_policy", 1, data)
        other_session = self.sign_in(self.owner)
        self.code(self.post(other_session, "reviews/policy/", data, etag='"0"'), "STEP_UP_REQUIRED")
        self.code(self.post(self.client, "reviews/policy/", {**data, "reason": "SENSITIVE_DOMAIN"}, etag='"0"'), "STEP_UP_REQUIRED")
        self.code(self.post(self.client, "reviews/policy/", data, etag='"1"'), "STALE_REVISION", 412)
        self.code(self.post(self.client, "reviews/policy/", data), "PRECONDITION_REQUIRED", 428)
        for values in ({**data, "reason": {"private": "Synthetic"}}, {**data, "reason": "Synthetic"},
            {**data, "mode": "unknown"}):
            self.code(self.post(self.client, "reviews/policy/", values, etag='"0"'), "INVALID_POLICY", 400)
        self.code(self.post(self.client, "reviews/policy/", {**data, "scope": "brain"}, etag='"0"'), "INVALID_FIELDS", 400)
        self.ok(self.post(self.client, "reviews/policy/", data, etag='"0"'))
        self.assertEqual(AdminSession.objects.get(pk=self.client.session["cms_session_id"]).step_up, {})
        self.code(self.post(self.client, "reviews/policy/", {"mode": "solo_owner", "reason": "OWNER_OPERATION"}, etag='"1"'), "STEP_UP_REQUIRED")
        self.code(self.post(self.client, "reviews/policy/", data, etag='"1"'), "POLICY_UNCHANGED", 409)
        self.assertEqual(ReviewPolicyRevision.objects.count(), 1)

    def test_policy_version_invalidates_approvals_and_toggling_back_never_revives_them(self):
        self.approved()
        decisions = list(ReviewDecision.objects.order_by("pk").values())
        self.ok(self.policy_change("two_person"))
        self.assertIn("POLICY_CHANGED", self.detail()["approval"]["blockers"])
        self.ok(self.policy_change("solo_owner", "OWNER_OPERATION"))
        detail = self.detail()
        self.assertEqual(detail["policy"]["version"], 2)
        self.assertEqual(detail["scientific_status"], "unreviewed")
        self.assertFalse(detail["approval"]["eligible"])
        self.assertIn("POLICY_CHANGED", detail["approval"]["blockers"])
        self.assertEqual(list(ReviewDecision.objects.order_by("pk").values()), decisions)
        self.ok(self.action("reopen"))
        self.assertEqual(ReviewDecision.objects.filter(outcome="invalidated", reason="POLICY_CHANGED").count(), 2)
        self.submit()
        self.assertEqual(self.task("source").policy_version, 2)
        self.ok(self.assign("source"))
        self.ok(self.assign("scientific"))
        self.ok(self.decide("source"))
        self.assertTrue(self.ok(self.decide("scientific"))["approval"]["eligible"])

    def test_every_cited_source_snapshot_field_invalidates_decisions_but_timestamps_do_not(self):
        self.prepared()
        values = {"title": "Synthetic changed title", "organization": "Synthetic organization",
            "citation": "Synthetic changed citation", "url": "https://example.org/changed",
            "publication_year": 2001, "source_type": "synthetic", "authors": ["Synthetic author"],
            "doi": "10.1234/synthetic", "pmid": "1234", "verification_status": "unreviewed",
            "metadata": {"synthetic": True}}
        original = SourceReference.objects.get(pk=self.source.pk)
        task = self.task("source")
        for field, value in values.items():
            with self.subTest(field=field):
                setattr(self.source, field, value)
                self.source.save(update_fields=(field,))
                response = self.decide("source")
                self.code(response, "STALE_DECISION", 409)
                self.assertIn("DEPENDENCY_CHANGED", response.json()["blockers"])
                self.assertEqual(self.task("source").version, task.version)
                self.assertFalse(ReviewDecision.objects.filter(outcome="approve").exists())
                setattr(self.source, field, getattr(original, field))
                self.source.save(update_fields=(field,))
        SourceReference.objects.filter(pk=self.source.pk).update(created_at=timezone.now() - timedelta(days=1), updated_at=timezone.now())
        self.ok(self.decide("source"))

    def test_inherited_link_note_and_uncited_source_snapshot_changes_invalidate_review(self):
        source = self.make_source("Synthetic inherited evidence")
        link = DisorderSource.objects.create(disorder=self.disorder, source=source, note="Synthetic original link")
        self.prepared()
        for field, value in (("note", "Synthetic changed link"), ("metadata", {"synthetic": "changed"})):
            with self.subTest(field=field):
                if field == "note":
                    DisorderSource.objects.filter(pk=link.pk).update(note=value)
                else:
                    source.metadata = value
                    source.save(update_fields=(field,))
                response = self.decide("source")
                self.code(response, "STALE_DECISION", 409)
                self.assertIn("DEPENDENCY_CHANGED", response.json()["blockers"])
                DisorderSource.objects.filter(pk=link.pk).update(note="Synthetic original link")
                source.metadata = {}
                source.save(update_fields=("metadata",))
        self.ok(self.decide("source"))

    def test_link_membership_source_reassignment_and_identity_changes_invalidate_review(self):
        first = self.make_source("Synthetic inherited first")
        second = self.make_source("Synthetic inherited second")
        link = DisorderSource.objects.create(disorder=self.disorder, source=first, note="Synthetic link")
        self.prepared()
        DisorderSource.objects.filter(pk=link.pk).update(source=second)
        self.code(self.decide("source"), "STALE_DECISION", 409)
        DisorderSource.objects.filter(pk=link.pk).update(source=first)
        added = DisorderSource.objects.create(disorder=self.disorder, source=second, note="Synthetic added member")
        self.code(self.decide("source"), "STALE_DECISION", 409)
        added.delete()
        old_pk = link.pk
        link.delete()
        self.code(self.decide("source"), "STALE_DECISION", 409)
        replacement = DisorderSource.objects.create(disorder=self.disorder, source=first, note="Synthetic link")
        self.assertNotEqual(replacement.pk, old_pk)
        response = self.decide("source")
        self.code(response, "STALE_DECISION", 409)
        self.assertIn("DEPENDENCY_CHANGED", response.json()["blockers"])
        self.assertFalse(ReviewDecision.objects.filter(outcome="approve").exists())

    def test_parent_category_snapshot_and_canonical_drift_make_decision_stale(self):
        self.prepared()
        for field, value in (("name_en", "Synthetic changed parent"), ("description", "Synthetic parent description"),
            ("sort_order", 11), ("is_active", False)):
            with self.subTest(field=field):
                original = getattr(self.category, field)
                Category.objects.filter(pk=self.category.pk).update(**{field: value})
                response = self.decide("source")
                self.code(response, "STALE_DECISION", 409)
                self.assertIn("DEPENDENCY_CHANGED", response.json()["blockers"])
                Category.objects.filter(pk=self.category.pk).update(**{field: original})
        Disorder.objects.filter(pk=self.disorder.pk).update(clinical_features="Synthetic external canonical writer")
        response = self.decide("source")
        self.code(response, "STALE_DECISION", 409)
        self.assertIn("CANONICAL_RECONCILIATION_REQUIRED", response.json()["blockers"])
        self.assertFalse(ReviewDecision.objects.filter(outcome="approve").exists())

    def test_corrupted_subject_or_current_payload_cannot_authorize_a_decision(self):
        self.prepared()
        self.state.refresh_from_db()
        # Simulate an out-of-band writer bypassing the append-only ORM protections.
        for revision in (self.task("source").subject, self.state.current_revision):
            with self.subTest(revision=revision.pk):
                original = json.dumps(revision.payload)
                table = connection.ops.quote_name(ContentRevision._meta.db_table)
                with connection.cursor() as cursor:
                    cursor.execute(f"UPDATE {table} SET payload = %s WHERE id = %s",
                        [json.dumps({**revision.payload, "overview": "Synthetic tampered payload"}), revision.pk])
                response = self.decide("source")
                self.code(response, "STALE_DECISION", 409)
                self.assertIn("PAYLOAD_CHANGED", response.json()["blockers"])
                with connection.cursor() as cursor:
                    cursor.execute(f"UPDATE {table} SET payload = %s WHERE id = %s", [original, revision.pk])
        self.ok(self.decide("source"))

    def test_permission_revocation_invalidates_prior_approval_before_science_decision(self):
        self.prepared()
        self.ok(self.decide("source"))
        permissions = ["cms_enter", "cms_core_view", SCIENCE_CAP]
        self.ok(self.post(self.client, f"roles/users/{self.source_reviewer.pk}/", {"permissions": permissions}, etag=self.etag()))
        response = self.decide("scientific")
        self.code(response, "STALE_DECISION", 409)
        self.assertIn("REVIEWER_PERMISSION_CHANGED", response.json()["blockers"])
        self.assertEqual(self.detail()["scientific_status"], "unreviewed")
        self.assertEqual(ReviewDecision.objects.filter(outcome="approve").count(), 1)

    def test_mutable_task_badges_need_matching_append_only_approval_decisions(self):
        self.prepared()
        source_task = self.task("source")
        ReviewTask.objects.filter(pk=source_task.pk).update(status="approved")
        response = self.decide("scientific")
        self.code(response, "STALE_DECISION", 409)
        self.assertIn("DECISION_REQUIRED", response.json()["blockers"])
        self.assertEqual(self.detail()["scientific_status"], "unreviewed")
        ReviewTask.objects.filter(pk=source_task.pk).update(status="assigned")
        self.ok(self.decide("source"))
        self.ok(self.decide("scientific"))
        source_task.refresh_from_db()
        for field, value in (("assignee_id", self.science_reviewer.pk), ("revision_hash", "0" * 64),
            ("dependency_digest", "1" * 64), ("evidence", [{**source_task.evidence[0], "locator": "Synthetic forged locator"}]),
            ("policy_version", 99)):
            with self.subTest(field=field):
                original = getattr(source_task, field)
                ReviewTask.objects.filter(pk=source_task.pk).update(**{field: value})
                detail = self.detail()
                self.assertFalse(detail["approval"]["eligible"])
                self.assertEqual(detail["scientific_status"], "unreviewed")
                self.assertIn("DECISION_REQUIRED", detail["approval"]["blockers"])
                ReviewTask.objects.filter(pk=source_task.pk).update(**{field: original})
        self.assertTrue(self.detail()["approval"]["eligible"])

    def test_real_session_csrf_jwt_origin_and_revoked_submit_authority_fail_closed(self):
        self.draft()
        path = self.review_path(suffix="submit/")
        data = {"evidence": self.evidence()}
        self.code(self.post(Client(enforce_csrf_checks=True), path, data, etag='"1"'), "UNAUTHENTICATED")
        token = RefreshToken.for_user(self.owner)
        self.code(self.post(Client(enforce_csrf_checks=True), path, data, etag='"1"',
            HTTP_AUTHORIZATION=f"Bearer {token.access_token}"), "UNAUTHENTICATED")
        self.code(self.client.post(BASE + path, json.dumps(data), content_type="application/json", HTTP_IF_MATCH='"1"'), "CSRF_FAILED")
        self.code(self.post(self.client, path, data, etag='"1"', HTTP_ORIGIN="https://foreign.invalid"), "CSRF_FAILED")
        editor_client = self.signed(self.editor)
        permission = Permission.objects.get(content_type__app_label="atlas", content_type__model="rolepolicy", codename="cms_core_submit")
        self.editor.user_permissions.remove(permission)
        self.code(self.post(editor_client, path, data, etag='"1"'), "PERMISSION_DENIED")
        self.assertFalse(ReviewTask.objects.exists())
        self.assertFalse(ReviewDecision.objects.exists())

    def test_queue_history_reviewers_sources_and_policy_have_bounded_pagination_and_scopes(self):
        self.prepared()
        self.draft(self.category_state)
        self.submit(self.category_state)
        queue = self.client.get(BASE + "reviews/?page_size=1&page=1")
        self.assertEqual(queue.status_code, 200, queue.content)
        self.assertEqual((queue.json()["count"], len(queue.json()["results"])), (2, 1))
        second = self.client.get(BASE + "reviews/?page_size=1&page=2").json()
        self.assertNotEqual(queue.json()["results"][0]["record"]["id"], second["results"][0]["record"]["id"])
        filtered = self.client.get(BASE + "reviews/?kind=disorder&status=in_review&q=Synthetic").json()
        self.assertEqual([row["record"]["id"] for row in filtered["results"]], [str(self.state.pk)])
        mine = self.signed(self.source_reviewer).get(BASE + "reviews/?mine=1").json()
        self.assertEqual([row["record"]["id"] for row in mine["results"]], [str(self.state.pk)])
        history_path = self.review_path(suffix="history/")
        history = self.client.get(BASE + history_path + "?page_size=1").json()
        self.assertEqual((history["count"], len(history["results"])), (2, 1))
        reviewers_path = self.review_path(suffix="reviewers/")
        reviewers = self.client.get(BASE + reviewers_path + "?review_type=source&page_size=1")
        self.assertEqual(reviewers.status_code, 200, reviewers.content)
        self.assertEqual(len(reviewers.json()["results"]), 1)
        self.assertGreater(reviewers.json()["count"], 1)
        self.make_source("Synthetic second searchable source")
        sources = self.client.get(BASE + "reviews/sources/?q=Synthetic&page_size=1").json()
        self.assertEqual((sources["count"], len(sources["results"])), (2, 1))
        self.assertEqual(set(sources["results"][0]), {"id", "title", "doi", "pmid", "verification_status"})
        paths = ("reviews/", history_path, reviewers_path + "?review_type=source&", "reviews/sources/", "reviews/policy/")
        for path in paths:
            separator = "" if path.endswith("&") else "?"
            for query in ("page=0", "page_size=101", "page=abc", "model=UserNote"):
                self.code(self.client.get(BASE + path + separator + query), "INVALID_QUERY", 400)
        self.code(self.client.get(BASE + "reviews/?kind=brain"), "INVALID_QUERY", 400)
        self.code(self.client.get(BASE + "reviews/?mine=true"), "INVALID_QUERY", 400)
        self.code(self.client.get(BASE + reviewers_path + "?review_type=wrong"), "INVALID_REVIEW_TYPE", 400)
        scoped = self.sign_in(self.scoped)
        for target in (self.state.pk, uuid.uuid4()):
            self.code(scoped.get(BASE + f"reviews/disorder/{target}/"), "NOT_FOUND", 404)
            self.code(scoped.get(BASE + f"reviews/disorder/{target}/history/"), "NOT_FOUND", 404)
        # P10 makes this test actor a Brain-domain viewer: it can inspect only
        # its empty scoped review queue and shared policy, not Core tasks/sources.
        scoped_queue = scoped.get(BASE + "reviews/")
        self.assertEqual(scoped_queue.status_code, 200, scoped_queue.content)
        self.assertEqual(scoped_queue.json()["count"], 0)
        self.assertEqual(scoped_queue.json()["results"], [])
        scoped_core = scoped.get(BASE + "reviews/?kind=disorder")
        self.assertEqual(scoped_core.status_code, 200, scoped_core.content)
        self.assertEqual(scoped_core.json()["results"], [])
        scoped_policy = scoped.get(BASE + "reviews/policy/")
        self.assertEqual(scoped_policy.status_code, 200, scoped_policy.content)
        self.code(scoped.get(BASE + "reviews/sources/"), "PERMISSION_DENIED")
        for kind in ("UserNote", "user", "brain", "atlas.Disorder"):
            self.code(self.client.get(BASE + f"reviews/{kind}/{self.state.pk}/"), "NOT_FOUND", 404)
        self.code(self.client.get(BASE + f"reviews/category/{self.state.pk}/"), "NOT_FOUND", 404)

    def test_public_api_legacy_visibility_is_unchanged_through_draft_review_and_reopen(self):
        public = Client()
        paths = ("/api/categories/", "/api/disorders/", f"/api/disorders/{self.disorder.slug}/")
        before = {path: public.get(path).json() for path in paths}
        self.assertEqual(self.detail()["scientific_status"], "unreviewed")
        self.draft(values={"overview": "Synthetic private proposed overview"})
        self.submit()
        self.ok(self.assign("source"))
        self.ok(self.assign("scientific"))
        for action in (lambda: None, lambda: self.ok(self.decide("source")),
            lambda: self.ok(self.decide("scientific")), lambda: self.ok(self.action("reopen"))):
            action()
            for path in paths:
                self.assertEqual(public.get(path).json(), before[path])
                self.assertNotIn("Synthetic private proposed overview", public.get(path).content.decode())
        response = self.post(self.client, "content/disorder/", {"payload": {"name_en": "Synthetic unpublished proposal"}})
        self.assertEqual(response.status_code, 201, response.content)
        created = response.json()
        self.assertIsNone(created["canonical_pk"])
        state = ContentState.objects.get(pk=created["id"])
        self.submit(state)
        self.ok(self.assign("source", state=state))
        self.ok(self.assign("scientific", state=state))
        self.ok(self.decide("source", state=state))
        detail = self.ok(self.decide("scientific", state=state))
        self.assertTrue(detail["approval"]["eligible"])
        self.assertFalse(detail["canonical_public_eligible"])
        for path in paths:
            self.assertEqual(public.get(path).json(), before[path])

    def test_actual_public_gate_category_active_with_active_disorder_and_disorder_active_only(self):
        public = Client()
        for category_active, disorder_active in ((True, True), (True, False), (False, True), (False, False)):
            with self.subTest(category=category_active, disorder=disorder_active):
                Category.objects.filter(pk=self.category.pk).update(is_active=category_active)
                Disorder.objects.filter(pk=self.disorder.pk).update(is_active=disorder_active)
                category_detail = self.detail(self.category_state)
                disorder_detail = self.detail()
                self.assertEqual(category_detail["public_gate"], "is_active + active_disorder")
                self.assertEqual(disorder_detail["public_gate"], "is_active")
                self.assertEqual(category_detail["canonical_public_eligible"], category_active and disorder_active)
                self.assertEqual(disorder_detail["canonical_public_eligible"], disorder_active)
                categories = public.get("/api/categories/").json()
                self.assertEqual(self.category.slug in {row["slug"] for row in categories}, category_active and disorder_active)
                response = public.get(f"/api/disorders/{self.disorder.slug}/")
                self.assertEqual(response.status_code, 200 if disorder_active else 404)
                rows = public.get("/api/disorders/").json()
                rows = rows["results"] if isinstance(rows, dict) else rows
                self.assertEqual(self.disorder.slug in {row["slug"] for row in rows}, disorder_active)
        empty = Category.objects.create(slug="synthetic-empty-category", name_en="Synthetic empty category", is_active=True)
        state = self.anchor("category", empty)
        self.assertFalse(self.detail(state)["canonical_public_eligible"])
        self.assertNotIn(empty.slug, {row["slug"] for row in public.get("/api/categories/").json()})

    def test_audit_failure_rolls_back_submit_assignment_decision_reopen_and_policy_in_full(self):
        original = AdminAuditEvent.objects.create

        def failed_write(action, write):
            before = self.snapshot()

            def fail(**values):
                if values["action"] == action:
                    raise DatabaseError("Synthetic private audit storage failure")
                return original(**values)

            with patch.object(AdminAuditEvent.objects, "create", side_effect=fail):
                response = write()
            self.code(response, "WRITE_FAILED", 503)
            self.assertNotIn("Synthetic private", response.content.decode())
            self.assertEqual(self.snapshot(), before)
            event = AdminAuditEvent.objects.get(request_id=response.json()["request_id"])
            self.assertEqual((event.outcome, event.error_code), ("failed", "WRITE_FAILED"))

        self.draft()
        failed_write("review.submitted", lambda: self.action("submit", {"evidence": self.evidence()}))
        self.submit()
        failed_write("review.assigned", lambda: self.assign("source"))
        self.ok(self.assign("source"))
        self.ok(self.assign("scientific"))
        # Establish the real reviewer session before snapshotting successful audit events.
        self.signed(self.source_reviewer)
        failed_write("review.decided", lambda: self.decide("source"))
        self.ok(self.decide("source"))
        self.ok(self.decide("scientific"))
        for action in ("review.invalidated", "review.reopened"):
            failed_write(action, lambda: self.action("reopen"))
        data = {"mode": "two_person", "reason": "TEAM_POLICY"}
        self.step_up(self.client, self.owner, "review_policy", 1, data)
        session_id = self.client.session["cms_session_id"]
        proof = AdminSession.objects.get(pk=session_id).step_up
        failed_write("review.policy", lambda: self.post(self.client, "reviews/policy/", data, etag='"0"'))
        self.assertEqual(AdminSession.objects.get(pk=session_id).step_up, proof)
        with patch.object(AdminAuditEvent.objects, "create", side_effect=DatabaseError("Synthetic unavailable audit")):
            response = self.action("reopen")
        self.code(response, "AUDIT_UNAVAILABLE", 503)
        self.assertTrue(self.detail()["approval"]["eligible"])


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReviewConcurrencyTests(ReviewFixture, TransactionTestCase):
    def test_postgres_source_deleted_between_initial_check_and_locked_snapshot_rejects_submit(self):
        if connection.vendor != "postgresql":
            self.skipTest("SQLite IMMEDIATE prevents the concurrent deletion; same-connection regression covers rejection.")
        second = self.make_source("Synthetic concurrently deleted cited source")
        self.draft()
        evidence = self.evidence()
        evidence.append({**evidence[0], "source_id": second.pk, "locator": "Synthetic section 2"})
        before = self.snapshot()
        version = self.state.version
        path = self.review_path(suffix="submit/")
        initial_checked, deletion_committed = Barrier(2), Event()
        submit_connections = []

        def wait_after_initial_check(*args):
            checked = checked_evidence(*args)
            self.assertEqual({item["source_id"] for item in checked}, {self.source.pk, second.pk})
            submit_connections.append(connection.connection)
            initial_checked.wait(timeout=15)
            self.assertTrue(deletion_committed.wait(timeout=15), "Synthetic source deletion did not commit")
            self.assertFalse(SourceReference.objects.filter(pk=second.pk).exists())
            return checked

        def submit():
            close_old_connections()
            try:
                return self.post(self.client, path, {"evidence": evidence}, etag='"%s"' % version)
            finally:
                connection.close()

        def delete():
            close_old_connections()
            connection.ensure_connection()
            writer_connection = connection.connection
            try:
                initial_checked.wait(timeout=15)
                with transaction.atomic():
                    deleted, _ = SourceReference.objects.filter(pk=second.pk).delete()
                    self.assertEqual(deleted, 1)
                deletion_committed.set()
                return writer_connection
            finally:
                deletion_committed.set()
                connection.close()

        with patch("atlas.cms_review.checked_evidence", side_effect=wait_after_initial_check) as initial_check:
            with ThreadPoolExecutor(max_workers=2) as pool:
                submission = pool.submit(submit)
                deletion = pool.submit(delete)
                response = submission.result(timeout=30)
                writer_connection = deletion.result(timeout=30)
        self.assertEqual(initial_check.call_count, 1)
        self.assertEqual(len(submit_connections), 1)
        self.assertIsNot(submit_connections[0], writer_connection)
        self.code(response, "INVALID_EVIDENCE", 400)
        self.assertEqual(self.snapshot(), before)
        self.assertTrue(SourceReference.objects.filter(pk=self.source.pk).exists())
        self.assertFalse(SourceReference.objects.filter(pk=second.pk).exists())
        self.assertFalse(ReviewTask.objects.exists())
        self.assertFalse(ReviewDecision.objects.exists())
        self.assertFalse(AdminAuditEvent.objects.filter(action="review.submitted", outcome="success").exists())
        denial = AdminAuditEvent.objects.get(request_id=response.json()["request_id"])
        self.assertEqual((denial.action, denial.outcome, denial.error_code),
            ("api.security_denial", "denied", "INVALID_EVIDENCE"))

    def test_two_actual_connections_deciding_same_versions_commit_exactly_once(self):
        self.prepared()
        self.state.refresh_from_db()
        task = self.task("source")
        version = self.state.version
        session_id = self.signed(self.source_reviewer).session["cms_session_id"]
        barrier = Barrier(2)

        def worker(_):
            close_old_connections()
            connection.ensure_connection()
            identity = id(connection.connection)
            try:
                barrier.wait(timeout=15)
                state = decide_review(self.source_reviewer.pk, session_id, "disorder", str(self.state.pk),
                    version, task.pk, task.version, "approve", "SOURCE_VERIFIED", [], False, uuid.uuid4())
                return identity, state.version
            except CMSFailure as error:
                return identity, str(error.detail["code"])
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertEqual(len({identity for identity, _ in results}), 2)
        self.assertCountEqual([result for _, result in results], [version + 1, "STALE_REVISION"])
        task.refresh_from_db()
        self.assertEqual((task.status, task.version), ("approved", 2))
        self.assertEqual(ReviewDecision.objects.filter(task=task, outcome="approve").count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="review.decided", outcome="success").count(), 1)
        self.assertEqual(self.state.revisions.count(), version + 2)

    def test_role_revocation_holds_shared_lock_and_waiting_decision_rechecks_permission(self):
        self.prepared()
        self.state.refresh_from_db()
        task = self.task("source")
        version = self.state.version
        reviewer_session = self.signed(self.source_reviewer).session["cms_session_id"]
        owner_session = self.client.session["cms_session_id"]
        role_version = RolePolicy.objects.get(pk=1).version
        lock_held, decision_started, release = Event(), Event(), Event()

        def revoke():
            close_old_connections()
            connection.ensure_connection()
            identity = id(connection.connection)
            try:
                with policy_lock():
                    mutate_role(self.owner.pk, "user", self.source_reviewer.pk,
                        {"permissions": ["cms_enter", "cms_core_view", SCIENCE_CAP]}, role_version, owner_session)
                    lock_held.set()
                    if not release.wait(timeout=15):
                        raise AssertionError("Synthetic revocation release timeout")
                return identity, "revoked"
            finally:
                connection.close()

        def decide():
            close_old_connections()
            connection.ensure_connection()
            identity = id(connection.connection)
            try:
                decision_started.set()
                decide_review(self.source_reviewer.pk, reviewer_session, "disorder", str(self.state.pk),
                    version, task.pk, task.version, "approve", "SOURCE_VERIFIED", [], False, uuid.uuid4())
                return identity, "unexpected commit"
            except CMSFailure as error:
                return identity, str(error.detail["code"])
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            revocation = pool.submit(revoke)
            try:
                self.assertTrue(lock_held.wait(timeout=15))
                decision = pool.submit(decide)
                self.assertTrue(decision_started.wait(timeout=15))
            finally:
                release.set()
            results = [revocation.result(timeout=20), decision.result(timeout=20)]
        self.assertEqual(len({identity for identity, _ in results}), 2)
        self.assertEqual([result for _, result in results], ["revoked", "PERMISSION_DENIED"])
        self.state.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(self.state.version, version)
        self.assertEqual((task.status, task.version), ("assigned", 1))
        self.assertFalse(ReviewDecision.objects.filter(outcome="approve").exists())
        self.assertFalse(AdminAuditEvent.objects.filter(action="review.decided").exists())
        self.assertEqual(RolePolicy.objects.get(pk=1).version, role_version + 1)


class ReviewMigrationTests(TransactionTestCase):
    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_0039_0040_forward_reverse_preserves_canonical_revisions_audit_and_legacy_without_decisions(self):
        old_tip = ("atlas", "0039_v100_p02_audit_revisions")
        new_tip = ("atlas", "0040_v100_p04_review_workflow")
        executor = MigrationExecutor(connection)
        executor.migrate([old_tip])
        apps = executor.loader.project_state([old_tip]).apps
        category = apps.get_model("atlas", "Category").objects.create(slug="synthetic-p04-migration-category", name_en="Synthetic preserved category")
        disorder = apps.get_model("atlas", "Disorder").objects.create(category_id=category.pk,
            slug="synthetic-p04-migration-disorder", name_en="Synthetic preserved disorder", overview="Synthetic preserved overview")
        source = apps.get_model("atlas", "SourceReference").objects.create(title="Synthetic preserved source",
            citation="Synthetic preserved citation", url="https://example.org", verification_status="source_checked")
        apps.get_model("atlas", "DisorderSource").objects.create(disorder_id=disorder.pk, source_id=source.pk, note="Synthetic preserved link")
        actor = apps.get_model("auth", "User").objects.create(username="synthetic-p04-migration-actor")
        state = apps.get_model("atlas", "ContentState").objects.create(kind="disorder", canonical_pk=disorder.pk,
            legacy_origin=True, canonical_digest="a" * 64, publication="current")
        payload = {"name_en": disorder.name_en, "overview": disorder.overview}
        revision = apps.get_model("atlas", "ContentRevision").objects.create(state_id=state.pk, sequence=0,
            base_version=0, base_digest="a" * 64, payload=payload, payload_digest=digest(payload),
            dependency_digest="b" * 64, status="legacy")
        apps.get_model("atlas", "ContentState").objects.filter(pk=state.pk).update(current_revision_id=revision.pk)
        event = apps.get_model("atlas", "AdminAuditEvent").objects.create(actor_id=actor.pk, actor_ref="c" * 64,
            action="revision.created", outcome="success", target_kind="disorder", target_key=str(state.pk),
            reason="CONTENT_UPDATE", diff=["overview"], base_revision=0, new_revision=1)
        names = ("Category", "Disorder", "SourceReference", "DisorderSource", "ContentState", "ContentRevision", "AdminAuditEvent")

        def retained(apps):
            return {name: list(apps.get_model("atlas", name).objects.order_by("pk").values()) for name in names}

        before = retained(apps)
        executor = MigrationExecutor(connection)
        executor.migrate([new_tip])
        upgraded = executor.loader.project_state([new_tip]).apps
        self.assertEqual(retained(upgraded), before)
        policy = upgraded.get_model("atlas", "ReviewPolicy").objects.get(pk=1)
        self.assertEqual((policy.mode, policy.version), ("solo_owner", 0))
        self.assertFalse(upgraded.get_model("atlas", "ReviewTask").objects.exists())
        self.assertFalse(upgraded.get_model("atlas", "ReviewDecision").objects.exists())
        self.assertFalse(upgraded.get_model("atlas", "ReviewPolicyRevision").objects.exists())
        self.assertEqual(upgraded.get_model("atlas", "ContentRevision").objects.get(pk=revision.pk).status, "legacy")
        expected = ["legacy", "draft", "submitted", "in_review", "changes_requested", "approved", "superseded", "discarded"]
        for model in (ContentRevision, upgraded.get_model("atlas", "ContentRevision")):
            field = model._meta.get_field("status")
            self.assertEqual(field.default, "draft")
            self.assertEqual([value for value, _ in field.choices], expected)
        self.assertEqual(list(ScientificReviewStatus.values), ["unreviewed", "source_checked", "reviewed"])
        executor = MigrationExecutor(connection)
        executor.migrate([old_tip])
        reversed_apps = executor.loader.project_state([old_tip]).apps
        self.assertEqual(retained(reversed_apps), before)
        self.assertEqual(reversed_apps.get_model("atlas", "AdminAuditEvent").objects.get(pk=event.pk).created_at, event.created_at)
        self.assertEqual(reversed_apps.get_model("atlas", "ContentState").objects.get(pk=state.pk).current_revision_id, revision.pk)
        self.assertNotIn("atlas_reviewdecision", connection.introspection.table_names())
        executor = MigrationExecutor(connection)
        executor.migrate([new_tip])
        self.assertFalse(ReviewDecision.objects.exists())
        self.assertEqual(ReviewPolicy.objects.get(pk=1).version, 0)
