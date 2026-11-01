"""P16 case publishing: real guarded routes, synthetic educational fixtures only."""
import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from .cms_case_publication_models import CasePublicationPlan, CasePublicationReceipt, CasePublicationReview
from .models import (CaseAttempt, CaseRevision, CaseStep, CaseTransition,
                     ClinicalCase, SourceReference, StudyActivity)
from .services import start_or_resume_case_attempt
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CasePublicationContractTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
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

    def approve_reviews(self):
        for kind in ("source","scientific","rights"):
            r=self.review(kind,rights=self.permission() if kind=="rights" else None)
            self.assertEqual(r.status_code,201,r.content[:450])

    def freeze(self):
        return self.post(self.client_owner,self.root()+"freeze/",etag=self.client_owner.get(
            BASE+f"cases/{self.case.pk}/revisions/{self.rev.pk}/graph/")["ETag"])

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

    def test_pinned_historical_attempt_completes_after_actual_reviewed_apply(self):
        from .services import advance_case_attempt
        old = CaseRevision.objects.create(
            case=self.case, version=0, status=CaseRevision.Status.PUBLISHED,
            title="Earlier fictional revision",
            patient_summary="Old synthetic story",
            educational_objective="Previously approved fictional learning")
        old_first = CaseStep.objects.create(case=self.case, revision=old,
            stable_key="old-intro", node_kind=CaseStep.NodeKind.INFORMATION,
            title="Old start", narrative="Prior synthetic content", sort_order=0)
        old_end = CaseStep.objects.create(case=self.case, revision=old,
            stable_key="old-end", node_kind=CaseStep.NodeKind.TERMINAL,
            title="Old end", narrative="Prior synthetic ending", sort_order=1)
        CaseTransition.objects.create(revision=old, source_step=old_first,
            target_step=old_end, outcome="continue")
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
            choice_id=None,state_version=0)
        self.assertFalse(retry)
        self.assertEqual(first.current_step_id,old_end.pk)
        done,event,retry=advance_case_attempt(
            user=self.normal,attempt=first,step_id=old_end.pk,
            choice_id=None,state_version=1)
        self.assertFalse(retry)
        self.assertEqual(done.revision_id,old.pk)
        self.assertEqual(done.status,CaseAttempt.Status.COMPLETED)
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
