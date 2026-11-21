"""Purpose-bound support interventions use learner services without learning evidence."""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone

from .cms_models import AdminAuditEvent
from .models import StudyPlan, StudyPlanScope, StudyBlock
from .study_planning import create_study_plan, transition_study_plan
from .study_sessions import start_session
from .tests_v100_p01 import BASE
from .tests_v100_p13_learning_io import LearningTransferFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class StudySupportActionsTests(LearningTransferFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.operator = self.user("study-support", staff=True, caps=("cms_enter", "cms_user_view",
            "cms_study_view", "cms_study_correct", "cms_privacy_sensitive_read"))
        self.client = self.sign_in(self.operator)
        self.plan = create_study_plan(self.normal, {"name": "Synthetic support plan"})
        self.scope = StudyPlanScope.objects.create(plan=self.plan, disorder=self.disorder)
        transition_study_plan(self.normal, self.plan.pk, "activate")
        self.plan.refresh_from_db()
        self.block = StudyBlock.objects.create(plan=self.plan, scope=self.scope,
            block_kind=StudyBlock.Kind.DISORDER_REVIEW, scheduled_date=timezone.localdate(), estimated_minutes=10,
            disorder=self.disorder, snapshot_title="Synthetic", locked_by_user=True)
        self.route = f"users/{self.normal.pk}/study/operate/"
        self.reference = str(uuid.uuid4())

    def inspect(self, kind, identifier):
        scope = {"plan": "study_plans", "block": "study_blocks", "session": "study_sessions"}[kind]
        body = {"purpose": "SUPPORT_REQUEST", "case_ref": self.reference, "scope": scope, "page": 1}
        self.step_up(self.client, self.operator, "privacy_read", self.normal.pk, body)
        response = self.post(self.client, f"users/{self.normal.pk}/privacy/read/", body)
        self.assertEqual(response.status_code, 200, response.content[:300])
        row = next(row for row in response.json()["results"] if row["id"] == identifier)
        self.assertIn("operations", row)
        return row["operations"]

    def intent(self, kind="plan", identifier=None, action="pause", **extra):
        identifier = identifier or self.plan.pk
        snapshot = self.inspect(kind, identifier)
        self.assertIn(action, snapshot["actions"])
        return {"kind": kind, "target_id": identifier, "action": action, "etag": snapshot["etag"],
            "purpose": "SUPPORT_REQUEST", "case_ref": self.reference, "reason": "STUDY_SUPPORT",
            "request_key": str(uuid.uuid4()), **extra}

    def authorize(self, body):
        self.step_up(self.client, self.operator, "study_correct", self.normal.pk, body)

    def apply(self, body, *, route=None):
        return self.post(self.client, route or self.route, body, etag=body["etag"])

    def test_all_six_services_preserve_evidence_and_receipts_reconcile(self):
        for action in ("pause", "resume"):
            body = self.intent(action=action)
            self.authorize(body)
            response = self.apply(body)
            self.assertEqual(response.status_code, 200, response.content[:300])
            self.assertEqual(self.apply(body).json(), response.json())
        for action in ("reschedule", "unlock", "skip"):
            extra = {"scheduled_date": (timezone.localdate()+timedelta(days=1)).isoformat()} if action == "reschedule" else {}
            body = self.intent("block", self.block.pk, action, **extra)
            self.authorize(body)
            response = self.apply(body)
            self.assertEqual(response.status_code, 200, response.content[:300])
            self.assertEqual(self.apply(body).json(), response.json())
        self.block.refresh_from_db()
        self.assertEqual(self.block.status, "skipped")
        self.assertIsNone(self.block.completed_at)
        other = StudyBlock.objects.create(plan=self.plan, scope=self.scope, block_kind=StudyBlock.Kind.DISORDER_REVIEW,
            scheduled_date=timezone.localdate(), estimated_minutes=10, disorder=self.disorder, snapshot_title="Synthetic")
        session, _ = start_session(self.normal, other.pk, uuid.uuid4())
        body = self.intent("session", session.pk, "abandon")
        self.authorize(body)
        response = self.apply(body)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(self.apply(body).json(), response.json())
        session.refresh_from_db()
        self.assertEqual(session.status, "abandoned")
        self.assertIsNone(session.completed_at)
        other.refresh_from_db()
        self.assertEqual(other.status, "pending")
        from .cms_study_operation_models import StudyOperationReceipt
        self.assertEqual(StudyOperationReceipt.objects.count(), 6)
        self.assertEqual(AdminAuditEvent.objects.filter(action="study.operated").count(), 6)
        self.assertEqual(self.history(), self.before)
        safe = str(list(AdminAuditEvent.objects.filter(action="study.operated").values()))
        self.assertNotIn(self.reference, safe)
        receipt = StudyOperationReceipt.objects.first()
        with self.assertRaises(ValidationError):
            receipt.delete()

    def test_no_proof_binding_conflict_stale_header_and_audit_rollback(self):
        body = self.intent()
        self.assertEqual(self.apply(body).status_code, 403)
        self.authorize(body)
        self.assertEqual(self.apply({**body, "case_ref": str(uuid.uuid4())}).status_code, 403)
        self.assertEqual(self.post(self.client, self.route, body).status_code, 428)
        with patch("atlas.cms_study_actions.AdminAuditEvent.objects.create", side_effect=DatabaseError("synthetic audit outage")):
            self.assertEqual(self.apply(body).status_code, 503)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "active")
        self.assertEqual(self.apply(body).status_code, 200)
        self.assertEqual(self.apply({**body, "case_ref": str(uuid.uuid4())}).status_code, 409)
        stale = {**body, "request_key": str(uuid.uuid4())}
        self.authorize(stale)
        self.assertEqual(self.apply(stale).status_code, 412)
        self.assertEqual(self.history(), self.before)

    def test_current_permissions_ownership_and_closed_actions(self):
        body = self.intent()
        self.authorize(body)
        foreign = f"users/{self.scoped.pk}/study/operate/"
        self.assertEqual(self.apply(body, route=foreign).status_code, 404)
        for change in ({"action": "complete"}, {"kind": "activity"}, {"target_id": True},
                       {"reason": "free text"}, {"request_key": str(uuid.UUID(int=0))}, {"scheduled_date": "2020-01-01"}):
            self.assertEqual(self.apply({**body, **change}).status_code, 400, change)
        self.operator.user_permissions.remove(self.operator.user_permissions.get(codename="cms_study_correct"))
        self.assertEqual(self.apply(body).status_code, 403)
        self.assertNotIn("operations", self._read_without_operation())
        self.assertEqual(self.history(), self.before)

    def _read_without_operation(self):
        body = {"purpose": "SUPPORT_REQUEST", "case_ref": self.reference, "scope": "study_plans", "page": 1}
        self.step_up(self.client, self.operator, "privacy_read", self.normal.pk, body)
        return self.post(self.client, f"users/{self.normal.pk}/privacy/read/", body).json()["results"][0]

    def test_public_changes_stale_the_tag_and_resume_cannot_activate_a_draft(self):
        body = self.intent()
        self.authorize(body)
        transition_study_plan(self.normal, self.plan.pk, "pause")
        self.assertEqual(self.apply(body).status_code, 412)
        fresh = self.intent(action="resume")
        self.authorize(fresh)
        StudyPlan.objects.filter(pk=self.plan.pk).update(status="draft")
        self.assertEqual(self.apply(fresh).status_code, 412)
        draft = self.inspect("plan", self.plan.pk)
        self.assertEqual(draft["actions"], [])
        fresh = {**fresh, "etag": draft["etag"], "request_key": str(uuid.uuid4())}
        self.authorize(fresh)
        self.assertEqual(self.apply(fresh).status_code, 409)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "draft")
        self.assertEqual(self.history(), self.before)

    def test_session_expiry_at_row_admission_blocks_effects(self):
        from . import cms_study_actions as service
        from .cms_models import AdminSession
        body = self.intent()
        self.authorize(body)
        original = service._locked_target
        def expire(*args):
            row = original(*args)
            AdminSession.objects.filter(user=self.operator).update(expires_at=timezone.now()-timedelta(seconds=1))
            return row
        with patch.object(service, "_locked_target", side_effect=expire):
            self.assertEqual(self.apply(body).status_code, 403)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "active")
        self.assertEqual(self.history(), self.before)

    @skipUnlessDBFeature("has_select_for_update")
    def test_canonical_block_services_lock_only_supported_rows(self):
        from .study_scheduler import reschedule_study_block, unlock_study_block, skip_study_block
        rescheduled = reschedule_study_block(self.normal, self.block.pk,
            {"scheduled_date": timezone.localdate().isoformat()})
        self.assertTrue(rescheduled.locked_by_user)
        self.assertFalse(unlock_study_block(self.normal, self.block.pk).locked_by_user)
        self.assertEqual(skip_study_block(self.normal, self.block.pk).status, "skipped")

    @skipUnlessDBFeature("has_select_for_update")
    def test_two_connections_same_key_create_one_receipt(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections
        from .cms_study_actions import operate
        from .cms_study_operation_models import StudyOperationReceipt
        body = self.intent()
        self.authorize(body)
        sid = self.client.session["cms_session_id"]
        barrier = Barrier(2)
        def submit():
            try:
                barrier.wait(timeout=15)
                return operate(self.operator.pk, sid, self.normal.pk, body, body["etag"], uuid.uuid4())
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=25) for future in [pool.submit(submit), pool.submit(submit)]]
        self.assertEqual(results[0], results[1])
        self.assertEqual(StudyOperationReceipt.objects.count(), 1)

    @skipUnlessDBFeature("has_select_for_update")
    def test_public_writer_waits_for_the_same_plan_row_and_then_stales_the_operator(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from time import monotonic, sleep
        from django.db import connection, connections, transaction
        from .cms_study_actions import operate
        from .cms_policy import CMSFailure
        body = self.intent()
        self.authorize(body)
        sid = self.client.session["cms_session_id"]
        admitted, backend_pid = Event(), []
        def submit():
            try:
                connection.ensure_connection()
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    backend_pid.append(cursor.fetchone()[0])
                admitted.set()
                return operate(self.operator.pk, sid, self.normal.pk, body, body["etag"], uuid.uuid4())
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                StudyPlan.objects.select_for_update().get(pk=self.plan.pk)
                future = pool.submit(submit)
                self.assertTrue(admitted.wait(timeout=5))
                deadline, waiting = monotonic()+10, False
                while monotonic() < deadline and not waiting:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid=%s", backend_pid)
                        waiting = cursor.fetchone() == ("Lock",)
                    if not waiting:
                        sleep(0.02)
                self.assertTrue(waiting, "Operator must actually wait on PostgreSQL before the public commit")
                # Exercise the real public service while the operator waits on this row.
                transition_study_plan(self.normal, self.plan.pk, "pause")
                self.assertFalse(future.done())
            with self.assertRaises(CMSFailure) as stale:
                future.result(timeout=20)
        self.assertEqual(stale.exception.status_code, 412)
        self.assertEqual(self.history(), self.before)
