"""P16 case publishing: real guarded routes, synthetic educational fixtures only."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone

from .cms_case_publication_models import CasePublicationPlan, CasePublicationReceipt, CasePublicationReview
from .cms_review_models import ReviewPolicy
from .models import (CaseAttempt, CaseAttemptAnswer, CaseRevision, CaseStep, CaseTransition,
                     CaseQuestion, CaseChoice, CaseScoringDimension,
                     ClinicalCase, SourceReference, StudyActivity)
from .services import start_or_resume_case_attempt
from .tests_v100_p01 import BASE, SecurityFixture


class CasePublicationFixture(SecurityFixture):
    def setUp(self):
        super().setUp()
        ReviewPolicy.objects.get_or_create(pk=1)
        self.client_owner = self.sign_in(self.owner)
        self.case = ClinicalCase.objects.create(slug="p16-synthetic-new-case",
            title="Fictional educational scenario", patient_summary="Fictional only",
            educational_objective="Learn fictional reasoning", is_active=False,
            structure_mode="branching", seed_managed=False)
        self.rev = CaseRevision.objects.create(case=self.case, version=1,
            status=CaseRevision.Status.DRAFT, title=self.case.title,
            patient_summary=self.case.patient_summary,
            educational_objective=self.case.educational_objective)
        first = CaseStep.objects.create(case=self.case, revision=self.rev, stable_key="intro",
            node_kind=CaseStep.NodeKind.INFORMATION, title="Synthetic beginning",
            narrative="Fictional scene", sort_order=0)
        last = CaseStep.objects.create(case=self.case, revision=self.rev, stable_key="finish",
            node_kind=CaseStep.NodeKind.TERMINAL, title="Synthetic ending",
            narrative="Fictional ending", sort_order=1)
        CaseTransition.objects.create(revision=self.rev, source_step=first,
            target_step=last, outcome="continue")
        self.rev.entry_step=first
        self.rev.save(update_fields=["entry_step"])
        self.source=SourceReference.objects.create(title="Synthetic peer-reviewed paper",
            citation="Fictional synthetic citation for isolated test data",
            doi="10.1234/fake.p16.case", verification_status="source_checked")

    def root(self):
        return f"publication/cases/{self.case.pk}/revisions/{self.rev.pk}/"

    def review(self, kind, *, outcome="approved", evidence=None, rights=None, client=None, etag=None):
        data={"kind":kind,"outcome":outcome,"evidence":evidence if evidence is not None else [
            {"source_id":self.source.pk,"locator":"Synthetic page 1 / claim 1"}],
            "self_review_ack": True}
        if rights is not None:
            data["rights"]=rights
        return self.post(client or self.client_owner,self.root()+"reviews/",data,
            etag=etag or self.client_owner.get(BASE+f"cases/{self.case.pk}/revisions/{self.rev.pk}/graph/")["ETag"])

    def permission(self):
        return {"rightsholder":"Synthetic creator with written permission",
            "holder_basis":"Explicit fictional holder declaration",
            "permission_statement":"Synthetic written authorization for digital public educational text",
            "territory":"Worldwide synthetic fixture", "material":"text", "intended_use":"public_display",
            "review_on":(timezone.localdate()+timedelta(days=120)).isoformat(),
            "expires_on":(timezone.localdate()+timedelta(days=180)).isoformat()}

    def approve_reviews(self, rights_client=None):
        for kind in ("source","scientific","rights"):
            r=self.review(kind,rights=self.permission() if kind=="rights" else None,
                          client=rights_client if kind=="rights" else None)
            self.assertEqual(r.status_code,201,r.content[:450])

    def freeze(self):
        return self.post(self.client_owner,self.root()+"freeze/",etag=self.client_owner.get(
            BASE+f"cases/{self.case.pk}/revisions/{self.rev.pk}/graph/")["ETag"])

    def prepared_apply(self, rights_client=None):
        self.approve_reviews(rights_client)
        frozen = self.freeze()
        self.assertEqual(frozen.status_code, 201, frozen.content[:450])
        plan = frozen.json()
        endpoint = f"publication/cases/plans/{plan['plan_id']}/"
        self.assertEqual(self.post(self.client_owner, endpoint + "approve/", {
            "manifest_digest": plan["manifest_digest"], "self_review_ack": True,
        }).status_code, 200)
        self.step_up(self.client_owner, self.owner, "case_publish", self.rev.pk,
                     {"manifest_digest": plan["manifest_digest"]})
        return endpoint, {"manifest_digest": plan["manifest_digest"], "idempotency_key": str(uuid.uuid4())}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CasePublicationContractTests(CasePublicationFixture, TestCase):
    def rights_reviewer(self):
        reviewer = self.user("scoped-rights-reviewer", staff=True, caps=(
            "cms_enter", "cms_cases_view", "cms_review_decide_cases_rights", "cms_rights_decide"))
        return reviewer, self.sign_in(reviewer)

    def revoke_rights_authority(self, reviewer):
        from django.contrib.auth.models import Permission
        reviewer.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atlas", content_type__model="rolepolicy", codename="cms_rights_decide"))

    def test_revoked_rights_authority_blocks_freeze(self):
        reviewer, client = self.rights_reviewer()
        self.approve_reviews(client)
        self.revoke_rights_authority(reviewer)
        self.assertEqual(self.freeze().status_code, 409)
        self.assertFalse(CasePublicationPlan.objects.exists())

    def test_revoked_rights_authority_blocks_apply(self):
        reviewer, client = self.rights_reviewer()
        endpoint, body = self.prepared_apply(client)
        self.revoke_rights_authority(reviewer)
        self.assertEqual(self.post(self.client_owner, endpoint + "apply/", body).status_code, 409)
        self.case.refresh_from_db()
        self.assertFalse(self.case.is_active)
        self.assertFalse(CasePublicationReceipt.objects.exists())

    def test_revoked_rights_authority_hides_published_case_and_prevents_new_attempts(self):
        from rest_framework.exceptions import ValidationError
        from .views import public_available_clinical_cases
        reviewer, client = self.rights_reviewer()
        endpoint, body = self.prepared_apply(client)
        self.assertEqual(self.post(self.client_owner, endpoint + "apply/", body).status_code, 200)
        self.case.refresh_from_db()
        self.assertTrue(public_available_clinical_cases().filter(pk=self.case.pk).exists())
        historical, _ = start_or_resume_case_attempt(user=self.normal, clinical_case=self.case)
        self.revoke_rights_authority(reviewer)
        self.assertFalse(public_available_clinical_cases().filter(pk=self.case.pk).exists())
        with self.assertRaises(ValidationError):
            start_or_resume_case_attempt(user=self.owner, clinical_case=self.case)
        resumed, created = start_or_resume_case_attempt(user=self.normal, clinical_case=self.case)
        self.assertFalse(created)
        self.assertEqual(resumed.pk, historical.pk)

    def test_receipt_failure_rolls_back_apply_and_allows_same_key_retry(self):
        from .cms_models import AdminAuditEvent
        endpoint, body = self.prepared_apply()
        before = (list(CaseAttempt.objects.values()), list(StudyActivity.objects.values()))
        with patch("atlas.cms_case_publication._receipt", side_effect=RuntimeError("Synthetic receipt failure")):
            self.assertEqual(self.post(self.client_owner, endpoint + "apply/", body).status_code, 503)
        self.case.refresh_from_db()
        self.rev.refresh_from_db()
        self.assertFalse(self.case.is_active)
        self.assertIsNone(self.case.current_revision_id)
        self.assertEqual(self.rev.status, CaseRevision.Status.DRAFT)
        self.assertIsNone(self.rev.published_at)
        self.assertEqual(CasePublicationPlan.objects.get(revision=self.rev).status, "approved")
        self.assertFalse(CasePublicationReceipt.objects.exists())
        self.assertFalse(AdminAuditEvent.objects.filter(action="case.publication_applied").exists())
        self.assertEqual(before, (list(CaseAttempt.objects.values()), list(StudyActivity.objects.values())))
        retry = self.post(self.client_owner, endpoint + "apply/", body)
        self.assertEqual(retry.status_code, 200, retry.content[:450])
        self.assertTrue(retry.json()["newly_applied"])
        self.assertEqual(CasePublicationReceipt.objects.count(), 1)

    def test_receipt_failure_rolls_back_withdrawal_and_allows_retry(self):
        endpoint, body = self.prepared_apply()
        self.assertEqual(self.post(self.client_owner, endpoint + "apply/", body).status_code, 200)
        self.step_up(self.client_owner, self.owner, "case_withdraw", self.rev.pk,
                     {"manifest_digest": body["manifest_digest"]})
        body["idempotency_key"] = str(uuid.uuid4())
        with patch("atlas.cms_case_publication._receipt", side_effect=RuntimeError("Synthetic receipt failure")):
            self.assertEqual(self.post(self.client_owner, endpoint + "withdraw/", body).status_code, 503)
        self.case.refresh_from_db()
        self.assertTrue(self.case.is_active)
        self.assertEqual(CasePublicationPlan.objects.get(revision=self.rev).status, "applied")
        self.assertEqual(CasePublicationReceipt.objects.count(), 1)
        retry = self.post(self.client_owner, endpoint + "withdraw/", body)
        self.assertEqual(retry.status_code, 200, retry.content[:450])
        self.assertTrue(retry.json()["newly_withdrawn"])
        self.assertEqual(CasePublicationReceipt.objects.count(), 2)

    def test_publication_requires_real_revision_bound_review_and_stepup(self):
        self.assertEqual(self.freeze().status_code,409)
        self.assertFalse(self.case.is_active)
        self.assertEqual(CasePublicationPlan.objects.count(),0)
        self.approve_reviews()
        validation=self.client_owner.get(BASE+
            f"cases/{self.case.pk}/revisions/{self.rev.pk}/validate/")
        self.assertEqual(validation.status_code,200)
        self.assertTrue(validation.json()["publication_eligible"],validation.json())
        queue=self.client_owner.get(BASE+"publication/preflight/?domain=cases")
        self.assertEqual(queue.status_code,200)
        candidate=next(row for row in queue.json()["results"] if row["resource_id"]==self.rev.pk)
        self.assertTrue(candidate["eligible"],candidate)
        self.assertEqual(candidate["revision_digest"],validation.json()["revision_digest"])
        frozen=self.freeze()
        self.assertEqual(frozen.status_code,201,frozen.content[:450])
        plan=frozen.json()
        key=str(uuid.uuid4())
        endpoint=f"publication/cases/plans/{plan['plan_id']}/"
        self.assertEqual(self.post(self.client_owner,endpoint+"apply/",{
            "manifest_digest":plan["manifest_digest"],"idempotency_key":key}).status_code,409)
        accepted=self.post(self.client_owner,endpoint+"approve/",{
            "manifest_digest":plan["manifest_digest"],"self_review_ack":True})
        self.assertEqual(accepted.status_code,200,accepted.content[:450])
        self.assertEqual(self.post(self.client_owner,endpoint+"apply/",{
            "manifest_digest":plan["manifest_digest"],"idempotency_key":key}).status_code,403)
        self.step_up(self.client_owner,self.owner,"case_publish",self.rev.pk,
                     {"manifest_digest":plan["manifest_digest"]})
        before=(CaseAttempt.objects.count(),StudyActivity.objects.count())
        applied=self.post(self.client_owner,endpoint+"apply/",{
            "manifest_digest":plan["manifest_digest"],"idempotency_key":key})
        self.assertEqual(applied.status_code,200,applied.content[:450])
        self.assertTrue(applied.json()["newly_applied"])
        self.case.refresh_from_db()
        self.rev.refresh_from_db()
        self.assertEqual(self.case.current_revision_id,self.rev.pk)
        self.assertTrue(self.case.is_active)
        self.assertEqual(self.rev.status,CaseRevision.Status.PUBLISHED)
        self.assertEqual(before,(CaseAttempt.objects.count(),StudyActivity.objects.count()))
        repeated=self.post(self.client_owner,endpoint+"apply/",{
            "manifest_digest":plan["manifest_digest"],"idempotency_key":key})
        self.assertEqual(repeated.status_code,200,repeated.content[:450])
        self.assertFalse(repeated.json()["newly_applied"])
        self.assertEqual(CasePublicationReceipt.objects.filter(event_type="applied").count(),1)
        self.assertEqual(self.post(self.client_owner,endpoint+"apply/",{
            "manifest_digest":plan["manifest_digest"],"idempotency_key":str(uuid.uuid4())}).status_code,409)
        detailed=self.client_owner.get(BASE+endpoint)
        self.assertEqual(detailed.status_code,200)
        self.assertEqual(len(detailed.json()["receipts"]),1)
        attempt,started=start_or_resume_case_attempt(user=self.normal,clinical_case=self.case)
        self.assertTrue(started)
        self.assertEqual(attempt.revision_id,self.rev.pk)
        self.assertEqual(CaseAttempt.objects.count(),1)

        withdrawal_key=str(uuid.uuid4())
        self.step_up(self.client_owner,self.owner,"case_withdraw",self.rev.pk,
                     {"manifest_digest":plan["manifest_digest"]})
        withdrawn=self.post(self.client_owner,endpoint+"withdraw/",{
            "manifest_digest":plan["manifest_digest"],"idempotency_key":withdrawal_key})
        self.assertEqual(withdrawn.status_code,200,withdrawn.content[:450])
        self.case.refresh_from_db()
        self.assertFalse(self.case.is_active)
        self.assertEqual(CasePublicationReceipt.objects.count(),2)
        resumed,new=start_or_resume_case_attempt(user=self.normal,clinical_case=self.case)
        self.assertFalse(new)
        self.assertEqual(resumed.pk,attempt.pk)
        self.assertEqual(self.post(self.client_owner,endpoint+"withdraw/",{
            "manifest_digest":plan["manifest_digest"],"idempotency_key":withdrawal_key}).status_code,200)

    def test_withdrawn_revision_reinstates_only_with_fresh_approval_and_mfa(self):
        from .views import public_available_clinical_cases
        endpoint, body = self.prepared_apply()
        applied = self.post(self.client_owner, endpoint + "apply/", body)
        self.assertEqual(applied.status_code, 200, applied.content[:450])
        self.rev.refresh_from_db()
        published_at = self.rev.published_at
        self.step_up(self.client_owner, self.owner, "case_withdraw", self.rev.pk,
                     {"manifest_digest": body["manifest_digest"]})
        withdrawn = self.post(self.client_owner, endpoint + "withdraw/", {
            "manifest_digest": body["manifest_digest"],
            "idempotency_key": str(uuid.uuid4())})
        self.assertEqual(withdrawn.status_code, 200, withdrawn.content[:450])

        # The applied revision is no longer a draft, so it cannot be re-frozen.
        self.assertEqual(self.freeze().status_code, 409)

        reinstated = self.post(self.client_owner, endpoint + "reinstate/", {
            "manifest_digest": body["manifest_digest"]})
        self.assertEqual(reinstated.status_code, 201, reinstated.content[:450])
        plan = reinstated.json()
        self.assertEqual(plan["status"], "frozen")
        self.assertEqual(plan["manifest"]["action"], "reinstate_case_revision")
        self.assertIn(plan["reinstates_plan_id"], endpoint)
        repeated = self.post(self.client_owner, endpoint + "reinstate/", {
            "manifest_digest": body["manifest_digest"]})
        self.assertEqual(repeated.status_code, 200, repeated.content[:450])
        self.assertEqual(repeated.json()["plan_id"], plan["plan_id"])

        new_endpoint = f"publication/cases/plans/{plan['plan_id']}/"
        # The withdrawn plan's earlier approval is not reused.
        self.assertEqual(self.post(self.client_owner, new_endpoint + "apply/", {
            "manifest_digest": plan["manifest_digest"],
            "idempotency_key": str(uuid.uuid4())}).status_code, 409)
        self.assertEqual(self.post(self.client_owner, new_endpoint + "approve/", {
            "manifest_digest": plan["manifest_digest"], "self_review_ack": True,
        }).status_code, 200)
        # A fresh MFA step-up bound to the reinstatement manifest is required.
        self.assertEqual(self.post(self.client_owner, new_endpoint + "apply/", {
            "manifest_digest": plan["manifest_digest"],
            "idempotency_key": str(uuid.uuid4())}).status_code, 403)
        self.step_up(self.client_owner, self.owner, "case_publish", self.rev.pk,
                     {"manifest_digest": plan["manifest_digest"]})
        reapplied = self.post(self.client_owner, new_endpoint + "apply/", {
            "manifest_digest": plan["manifest_digest"],
            "idempotency_key": str(uuid.uuid4())})
        self.assertEqual(reapplied.status_code, 200, reapplied.content[:450])
        self.case.refresh_from_db()
        self.rev.refresh_from_db()
        self.assertTrue(self.case.is_active)
        self.assertEqual(self.case.current_revision_id, self.rev.pk)
        self.assertEqual(self.rev.published_at, published_at)
        self.assertTrue(public_available_clinical_cases().filter(pk=self.case.pk).exists())
        self.assertEqual(CasePublicationReceipt.objects.filter(event_type="applied").count(), 2)
        self.assertEqual(CasePublicationReceipt.objects.filter(event_type="withdrawn").count(), 1)
        # After reinstatement the withdrawal is spent; a third state needs a new withdrawal.
        self.assertEqual(self.post(self.client_owner, endpoint + "reinstate/", {
            "manifest_digest": body["manifest_digest"]}).status_code, 409)

    def test_pinned_historical_attempt_completes_after_actual_reviewed_apply(self):
        from .services import advance_case_attempt
        old = CaseRevision.objects.create(
            case=self.case, version=0, status=CaseRevision.Status.PUBLISHED,
            rubric_version=1,
            title="Earlier fictional revision",
            patient_summary="Old synthetic story",
            educational_objective="Previously approved fictional learning")
        old_first = CaseStep.objects.create(case=self.case, revision=old,
            stable_key="old-intro", node_kind=CaseStep.NodeKind.DECISION,
            title="Old start", narrative="Prior synthetic content", sort_order=0)
        old_end = CaseStep.objects.create(case=self.case, revision=old,
            stable_key="old-end", node_kind=CaseStep.NodeKind.TERMINAL,
            title="Old end", narrative="Prior synthetic ending", sort_order=1)
        dimension = CaseScoringDimension.objects.create(revision=old, stable_key="reasoning", label="Original rubric")
        question = CaseQuestion.objects.create(step=old_first, prompt="Original question", scoring_dimension=dimension)
        choice = CaseChoice.objects.create(question=question, text="Original scored answer", score_value=3)
        CaseTransition.objects.create(revision=old, source_step=old_first,
            choice=choice, target_step=old_end, outcome="continue")
        old.entry_step=old_first
        old.save(update_fields=["entry_step"])
        self.case.current_revision=old
        self.case.is_active=True
        self.case.save(update_fields=["current_revision", "is_active"])
        prior, started=start_or_resume_case_attempt(user=self.normal,clinical_case=self.case)
        self.assertTrue(started)
        self.assertEqual(prior.revision_id, old.pk)
        self.approve_reviews()
        validation=self.client_owner.get(BASE+
            f"cases/{self.case.pk}/revisions/{self.rev.pk}/validate/")
        self.assertEqual(validation.status_code,200)
        self.assertTrue(validation.json()["publication_eligible"],validation.json())
        queue=self.client_owner.get(BASE+"publication/preflight/?domain=cases")
        self.assertEqual(queue.status_code,200)
        candidate=next(row for row in queue.json()["results"] if row["resource_id"]==self.rev.pk)
        self.assertTrue(candidate["eligible"],candidate)
        self.assertEqual(candidate["revision_digest"],validation.json()["revision_digest"])
        frozen=self.freeze()
        self.assertEqual(frozen.status_code,201,frozen.content[:350])
        data=frozen.json()
        plan_id=data["plan_id"]
        self.assertEqual(self.post(self.client_owner,
            f"publication/cases/plans/{plan_id}/approve/", {
            "manifest_digest":data["manifest_digest"],
            "self_review_ack":True}).status_code,200)
        self.step_up(self.client_owner,self.owner,"case_publish",self.rev.pk,
                     {"manifest_digest":data["manifest_digest"]})
        published=self.post(self.client_owner,
            f"publication/cases/plans/{plan_id}/apply/",{
                "manifest_digest":data["manifest_digest"],
                "idempotency_key":str(uuid.uuid4())})
        self.assertEqual(published.status_code,200,published.content[:350])
        self.assertEqual(CasePublicationReceipt.objects.filter(
            plan_id=plan_id,event_type="applied").count(),1)
        first,event,retry=advance_case_attempt(
            user=self.normal,attempt=prior,step_id=old_first.pk,
            choice_id=choice.pk,state_version=0)
        self.assertFalse(retry)
        self.assertEqual(first.current_step_id,old_end.pk)
        done,event,retry=advance_case_attempt(
            user=self.normal,attempt=first,step_id=old_end.pk,
            choice_id=None,state_version=1)
        self.assertFalse(retry)
        self.assertEqual(done.revision_id,old.pk)
        self.assertEqual(done.status,CaseAttempt.Status.COMPLETED)
        self.assertEqual((done.score, done.max_score), (3, 3))
        answer = CaseAttemptAnswer.objects.get(attempt=done)
        self.assertEqual((answer.question_id, answer.selected_choice_id, answer.scoring_dimension_id,
                          answer.awarded_score), (question.pk, choice.pk, dimension.pk, 3))
        self.assertEqual([item.step_id for item in done.events.order_by(
            "state_version_before")],[old_first.pk,old_end.pk])
        newer,started=start_or_resume_case_attempt(user=self.normal,clinical_case=self.case)
        self.assertTrue(started)
        self.assertEqual(newer.revision_id,self.rev.pk)
        self.assertNotEqual(newer.current_step_id,old_first.pk)
        old.refresh_from_db()
        self.assertEqual(old.status,CaseRevision.Status.PUBLISHED)

    def test_revision_and_source_changes_invalidate_frozen_manifest(self):
        self.approve_reviews()
        first=self.freeze()
        self.assertEqual(first.status_code,201)
        plan=first.json()
        self.source.citation="Changed synthetic citation"
        self.source.save(update_fields=["citation"])
        attempted=self.post(self.client_owner,f"publication/cases/plans/{plan['plan_id']}/approve/",{
            "manifest_digest":plan["manifest_digest"],"self_review_ack":True})
        self.assertEqual(attempted.status_code,409,attempted.content[:500])
        self.assertFalse(CasePublicationPlan.objects.get(pk=plan["plan_id"]).approved_by_id)
        self.rev.patient_summary="Different synthetic summary"
        self.rev.save(update_fields=["patient_summary"])
        self.assertEqual(self.freeze().status_code,409)
        self.assertFalse(self.case.is_active)

    def test_permissions_are_independent_and_wrong_case_not_found(self):
        reader=self.user("p16-case-reader",staff=True,caps=("cms_enter","cms_cases_view","cms_cases_validate"))
        reader_client=self.sign_in(reader)
        self.assertEqual(reader_client.get(BASE+self.root()+"reviews/").status_code,200)
        self.assertEqual(self.review("source",client=reader_client).status_code,403)
        self.assertEqual(self.post(reader_client,self.root()+"freeze/").status_code,403)
        self.assertEqual(self.post(self.client_owner,
            f"publication/cases/{self.case.pk+444}/revisions/{self.rev.pk}/freeze/").status_code,428)
        self.assertEqual(CasePublicationReview.objects.count(),0)

    def test_published_case_fails_closed_on_source_drift_and_rights_revocation(self):
        from rest_framework.exceptions import ValidationError
        from .views import public_available_clinical_cases
        self.approve_reviews()
        frozen=self.freeze()
        self.assertEqual(frozen.status_code,201)
        plan=frozen.json()
        plan_url=f"publication/cases/plans/{plan['plan_id']}/"
        self.assertEqual(self.post(self.client_owner,plan_url+"approve/",{
            "manifest_digest":plan["manifest_digest"],"self_review_ack":True}).status_code,200)
        self.step_up(self.client_owner,self.owner,"case_publish",self.rev.pk,
                     {"manifest_digest":plan["manifest_digest"]})
        self.assertEqual(self.post(self.client_owner,plan_url+"apply/",{
            "manifest_digest":plan["manifest_digest"],
            "idempotency_key":str(uuid.uuid4())}).status_code,200)
        self.case.refresh_from_db()
        self.assertTrue(public_available_clinical_cases().filter(pk=self.case.pk).exists())
        attempt,started=start_or_resume_case_attempt(user=self.normal,clinical_case=self.case)
        self.assertTrue(started)
        self.source.citation="Edited fictional bibliographic fact"
        self.source.save(update_fields=["citation"])
        self.assertFalse(public_available_clinical_cases().filter(pk=self.case.pk).exists())
        with self.assertRaises(ValidationError):
            start_or_resume_case_attempt(user=self.owner,clinical_case=self.case)
        resumed,created=start_or_resume_case_attempt(user=self.normal,clinical_case=self.case)
        self.assertFalse(created)
        self.assertEqual(attempt.pk,resumed.pk)
        revoke=self.review("rights",outcome="revoked",evidence=[])
        self.assertEqual(revoke.status_code,201,revoke.content[:450])
        self.case.refresh_from_db()
        self.assertFalse(self.case.is_active)
        self.assertEqual(CasePublicationPlan.objects.get(pk=plan["plan_id"]).status,"withdrawn")
        self.assertEqual(CasePublicationReceipt.objects.filter(
            plan_id=plan["plan_id"],event_type="withdrawn").count(),1)
        self.assertFalse(public_available_clinical_cases().filter(pk=self.case.pk).exists())

    def test_two_person_policy_requires_distinct_reviewers_and_approver(self):
        from .cms_review_models import ReviewPolicy
        policy=ReviewPolicy.objects.get(pk=1)
        policy.mode="two_person"
        policy.version+=1
        policy.save(update_fields=["mode","version"])
        separate=self.user("p16-independent-reviewer",staff=True,caps=(
            "cms_enter","cms_cases_view","cms_cases_validate",
            "cms_review_decide_cases_scientific","cms_publication_approve_cases"))
        second_client=self.sign_in(separate)
        self.assertEqual(self.review("source").status_code,201)
        self.assertEqual(self.review("scientific").status_code,201)
        self.assertEqual(self.review("rights",rights=self.permission()).status_code,201)
        self.assertEqual(self.freeze().status_code,409)
        self.assertEqual(self.review("scientific",client=second_client).status_code,201)
        frozen=self.freeze()
        self.assertEqual(frozen.status_code,201,frozen.content[:300])
        plan=frozen.json()
        endpoint=f"publication/cases/plans/{plan['plan_id']}/approve/"
        data={"manifest_digest":plan["manifest_digest"],"self_review_ack":True}
        self.assertEqual(self.post(self.client_owner,endpoint,data).status_code,409)
        self.assertEqual(self.post(second_client,endpoint,data).status_code,200)
        self.step_up(self.client_owner,self.owner,"case_publish",self.rev.pk,
                     {"manifest_digest":plan["manifest_digest"]})
        applied=self.post(self.client_owner,
            f"publication/cases/plans/{plan['plan_id']}/apply/",{
                "manifest_digest":plan["manifest_digest"],
                "idempotency_key":str(uuid.uuid4())})
        self.assertEqual(applied.status_code,200,applied.content[:300])
        self.assertTrue(self.case.current_revision_id is None)
        self.case.refresh_from_db()
        self.assertEqual(self.case.current_revision_id,self.rev.pk)

    def test_invalid_rights_or_missing_resolved_source_fail_closed(self):
        self.assertEqual(self.review("scientific").status_code,409)
        self.assertEqual(self.review("source", evidence=[]).status_code,400)
        source=self.review("source")
        self.assertEqual(source.status_code,201,source.content[:450])
        bad=self.permission();bad["review_on"]=(timezone.localdate()-timedelta(days=1)).isoformat()
        self.assertEqual(self.review("rights",rights=bad).status_code,400)
        self.assertFalse(self.case.is_active)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CasePublicationConcurrencyTests(CasePublicationFixture, TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_apply_with_same_key_commits_once(self):
        from .cms_case_publication import apply_plan
        from .cms_models import AdminAuditEvent
        self.assertTrue(ReviewPolicy.objects.filter(pk=1).exists(), "Case fixture needs its seeded review policy")
        self.prepared_apply()
        plan = CasePublicationPlan.objects.get(revision=self.rev)
        session_id = self.client_owner.session["cms_session_id"]
        key = str(uuid.uuid4())
        barrier = Barrier(2)

        def worker(_):
            close_old_connections()
            connection.ensure_connection()
            identity = id(connection.connection)
            try:
                barrier.wait(timeout=15)
                receipt, created = apply_plan(self.owner.pk, session_id, plan.pk,
                    plan.manifest_digest, key, uuid.uuid4())
                return identity, receipt.pk, created
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(worker, range(2)))
        self.assertEqual(len({identity for identity, _, _ in results}), 2)
        self.assertEqual(len({receipt for _, receipt, _ in results}), 1)
        self.assertCountEqual([created for _, _, created in results], [True, False])
        self.assertEqual(CasePublicationReceipt.objects.count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="case.publication_applied").count(), 1)
        self.case.refresh_from_db()
        self.assertEqual(self.case.current_revision_id, self.rev.pk)
