"""P16 selected-for-review batches, never publication manifests or approval."""
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from .cms_content import digest
from .cms_content_models import ContentState, ContentRevision
from .models import Category, Disorder, Quiz, QuizQuestion, QuizChoice, StudyActivity
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PublicationSelectionsTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_client = self.sign_in(self.owner)
        category = Category.objects.create(slug="p16-selection", name_en="P16 synthetic")
        disorder = Disorder.objects.create(
            category=category, slug="p16-selection-disorder",
            name_en="P16 synthetic only", is_active=True,
        )
        self.quiz = Quiz.objects.create(
            slug="p16-selection-quiz", title="Confidential draft question",
            disorder=disorder, is_active=False, seed_managed=False,
        )
        question = QuizQuestion.objects.create(quiz=self.quiz, prompt="Private hidden quiz body")
        QuizChoice.objects.create(question=question, text="Private correct answer", is_correct=True)
        QuizChoice.objects.create(question=question, text="Private wrong answer", is_correct=False)
        self.brain = self.proposal("brain-anatomical-entity", "P16 confidential brain")
        self.assessment = self.proposal("assessment-instrument", "P16 confidential assessment")

    def proposal(self, kind, name, payload=None):
        state = ContentState.objects.create(kind=kind, canonical_digest=digest({}))
        data = payload if payload is not None else {"name_en": name}
        revision = ContentRevision.objects.create(
            state=state, sequence=1, base_version=0, base_digest=digest({}),
            payload=data, payload_digest=digest(data), dependency_digest=digest({}),
            status="draft", actor=self.owner,
        )
        state.version, state.current_revision = 1, revision
        state.save(update_fields=("version", "current_revision"))
        return state

    def entry(self, domain, kind, identifier):
        response = self.owner_client.get(BASE + f"publication/preflight/?domain={domain}")
        self.assertEqual(response.status_code, 200, response.content[:300])
        row = next(v for v in response.json()["results"]
                   if v["kind"] == kind and str(v["resource_id"]) == str(identifier))
        return {"kind":kind,"resource_id":identifier,
                "expected_digest":row.get("content_digest") or row.get("proposal_digest")}

    def post_selection(self, domain, entries, *, key=None):
        return self.post(
            self.owner_client, "publication/selections/",
            {"domain":domain,"entries":entries,"request_key":str(key or uuid.uuid4())},
        )

    def test_learning_selection_is_immutable_audited_and_cannot_publish(self):
        entry = self.entry("learning", "quiz", self.quiz.pk)
        request_key = uuid.uuid4()
        first = self.post_selection("learning", [entry], key=request_key)
        self.assertEqual(first.status_code, 201, first.content[:400])
        body = first.json()
        self.assertEqual(body["status"], "review_selection_only")
        self.assertEqual(body["domain"], "learning")
        self.assertEqual(body["item_count"], 1)
        self.assertEqual(len(body["selection_digest"]), 64)
        self.assertFalse(body["publication_available"])
        self.assertFalse(body["approved"])
        self.assertNotIn("Private hidden quiz body", first.content.decode())
        self.assertNotIn("Private correct answer", first.content.decode())
        second = self.post_selection("learning", [entry], key=request_key)
        self.assertEqual(second.status_code, 200, second.content[:400])
        self.assertEqual(second.json()["id"], body["id"])
        self.assertEqual(second.json()["selection_digest"], body["selection_digest"])
        detail = self.owner_client.get(BASE + f'publication/selections/{body["id"]}/')
        self.assertEqual(detail.status_code, 200, detail.content[:400])
        self.assertEqual(detail.json()["selection_digest"], body["selection_digest"])
        self.assertFalse(Quiz.objects.get(pk=self.quiz.pk).is_active)
        self.assertEqual(StudyActivity.objects.count(), 0)
        from .cms_publication_selection_models import PublicationCandidateSelection
        from .cms_models import AdminAuditEvent
        self.assertEqual(PublicationCandidateSelection.objects.count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(action="publication.selection_created").count(), 1)
        row = PublicationCandidateSelection.objects.get()
        self.assertEqual(row.selection["items"][0]["content_digest"], entry["expected_digest"])
        with self.assertRaises(ValidationError):
            row.save()
        with self.assertRaises(ValidationError):
            PublicationCandidateSelection.objects.filter(pk=row.pk).update(domain="brain")
        with self.assertRaises(ValidationError):
            PublicationCandidateSelection.objects.filter(pk=row.pk).delete()

    def test_same_key_recovers_original_snapshot_after_content_changes(self):
        from .cms_publication_selection_models import PublicationCandidateSelection
        entry = self.entry("learning", "quiz", self.quiz.pk)
        key = uuid.uuid4()
        first = self.post_selection("learning", [entry], key=key)
        self.assertEqual(first.status_code, 201)
        self.quiz.title = "New private revision after lost response"
        self.quiz.save(update_fields=("title",))
        recovered = self.post_selection("learning", [entry], key=key)
        self.assertEqual(recovered.status_code, 200, recovered.content[:200])
        self.assertTrue(recovered.json()["recovered"])
        self.assertEqual(recovered.json()["selection_digest"], first.json()["selection_digest"])
        self.assertEqual(PublicationCandidateSelection.objects.count(), 1)
        self.assertNotIn("New private revision", recovered.content.decode())
        # A new request key must not accidentally accept an obsolete digest.
        self.assertEqual(self.post_selection("learning", [entry]).status_code, 412)

    def test_stale_second_item_rejects_entire_transaction(self):
        entry = self.entry("learning", "quiz", self.quiz.pk)
        wrong = dict(entry, expected_digest="a" * 64)
        failed = self.post_selection("learning", [entry, wrong])
        self.assertIn(failed.status_code, (400, 409, 412), failed.content[:400])
        from .cms_publication_selection_models import PublicationCandidateSelection
        self.assertFalse(PublicationCandidateSelection.objects.exists())
        self.quiz.title = "Changed private body"
        self.quiz.save(update_fields=["title"])
        failed = self.post_selection("learning", [entry])
        self.assertEqual(failed.status_code, 412, failed.content[:400])
        self.assertFalse(PublicationCandidateSelection.objects.exists())

    def test_brain_and_assessment_snapshots_are_not_approvals(self):
        from .cms_publication_selection_models import PublicationCandidateSelection
        for domain, kind, state in (
            ("brain","brain-anatomical-entity",self.brain),
            ("assessment","assessment-instrument",self.assessment),
        ):
            entry = self.entry(domain, kind, str(state.pk))
            response = self.post_selection(domain, [entry])
            self.assertEqual(response.status_code, 201, response.content[:300])
            self.assertFalse(response.json()["publication_available"])
            self.assertNotIn("confidential", response.content.decode())
            self.assertEqual(ContentState.objects.get(pk=state.pk).publication, "never_published")
        self.assertEqual(PublicationCandidateSelection.objects.count(), 2)

    def test_replay_conflict_closed_shapes_permission_revocation(self):
        from .cms_publication_selection_models import PublicationCandidateSelection
        entry = self.entry("learning", "quiz", self.quiz.pk)
        key = uuid.uuid4()
        self.assertEqual(self.post_selection("learning", [entry], key=key).status_code, 201)
        changed = dict(entry, expected_digest="a"*64)
        self.assertEqual(self.post_selection("learning", [changed], key=key).status_code, 409)
        assessment_entry = self.entry("assessment", "assessment-instrument", str(self.assessment.pk))
        self.assertEqual(self.post_selection("assessment", [assessment_entry], key=key).status_code, 409)
        denied = self.user("p16-selector-denied", staff=True,
                           caps=("cms_enter","cms_learning_view","cms_publication_validate_learning"))
        client = self.sign_in(denied)
        self.assertEqual(self.post(client, "publication/selections/", {
            "domain":"learning", "entries":[entry], "request_key":str(uuid.uuid4())}).status_code, 403)
        self.assertEqual(self.post_selection("learning", []).status_code, 400)
        malformed = self.post(self.owner_client, "publication/selections/", {
            "domain":"learning","entries":[entry],"request_key":str(uuid.uuid4()),"apply":True})
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(PublicationCandidateSelection.objects.count(), 1)

    def verify(self, selection_id, client=None, extra=""):
        return (client or self.owner_client).get(
            BASE + f"publication/selections/{selection_id}/verify/" + extra,
        )

    def test_verify_learning_snapshot_is_read_only_and_detects_edits(self):
        from .cms_models import AdminAuditEvent
        from .cms_publication_selection_models import PublicationCandidateSelection
        entry = self.entry("learning", "quiz", self.quiz.pk)
        selected = self.post_selection("learning", [entry])
        self.assertEqual(selected.status_code, 201, selected.content[:300])
        selection_id = selected.json()["id"]
        first = self.verify(selection_id)
        self.assertEqual(first.status_code, 200, first.content[:400])
        result = first.json()
        self.assertTrue(result["all_snapshots_current"])
        self.assertTrue(result["policy_matches"])
        self.assertEqual(result["items"][0]["snapshot_state"], "matching")
        self.assertEqual(result["status"], "review_selection_only")
        self.assertFalse(result["publication_available"])
        self.assertFalse(result["approved"])
        self.assertIn("SOURCE_SCIENCE_RIGHTS_UNVERIFIED", result["review_blockers"])
        self.assertNotIn("Private hidden quiz body", first.content.decode())
        self.assertNotIn("Private correct answer", first.content.decode())
        self.assertEqual(AdminAuditEvent.objects.filter(action="publication.selection_created").count(), 1)
        QuizChoice.objects.filter(question__quiz=self.quiz, is_correct=True).update(text="Changed private answer")
        stale = self.verify(selection_id)
        self.assertEqual(stale.status_code, 200, stale.content[:400])
        self.assertFalse(stale.json()["all_snapshots_current"])
        self.assertEqual(stale.json()["items"][0]["snapshot_state"], "stale")
        self.assertNotIn("Changed private answer", stale.content.decode())
        self.assertEqual(PublicationCandidateSelection.objects.count(), 1)
        self.assertFalse(Quiz.objects.get(pk=self.quiz.pk).is_active)

    def test_verify_dependency_and_archival_invalidation(self):
        from django.utils import timezone
        entry = self.entry("learning", "quiz", self.quiz.pk)
        selection_id = self.post_selection("learning", [entry]).json()["id"]
        self.quiz.disorder.is_active = False
        self.quiz.disorder.save(update_fields=["is_active"])
        stale = self.verify(selection_id)
        self.assertEqual(stale.status_code, 200, stale.content[:250])
        self.assertEqual(stale.json()["items"][0]["snapshot_state"], "stale")
        self.quiz.archived_at = timezone.now()
        self.quiz.save(update_fields=["archived_at"])
        unavailable = self.verify(selection_id)
        self.assertEqual(unavailable.status_code, 200)
        self.assertEqual(unavailable.json()["items"][0]["snapshot_state"], "unavailable")
        self.assertFalse(unavailable.json()["all_snapshots_current"])

    def test_verify_surfaces_real_editorial_review_blockers_without_publication(self):
        from .cms_review_models import ReviewTask
        entry = self.entry("brain", "brain-anatomical-entity", str(self.brain.pk))
        selection_id = self.post_selection("brain", [entry]).json()["id"]
        first = self.verify(selection_id)
        self.assertEqual(first.status_code, 200, first.content[:400])
        gate = first.json()["items"][0]["editorial_review"]
        self.assertEqual(gate["status"], "blocked")
        self.assertIn("REVIEW_REQUIRED", gate["blockers"])
        self.assertIn("APPROVAL_REQUIRED", gate["blockers"])
        self.assertFalse(first.json()["publication_available"])

        # A manually marked approved task is not valid evidence without its
        # append-only decision, current revision hash, and live permissions.
        revision = self.brain.current_revision
        ReviewTask.objects.create(
            subject=revision, review_type="source", assignee=self.owner,
            status="approved", revision_hash="0" * 64, dependency_digest="1" * 64,
            evidence=[], authors=[], policy_version=0, policy_mode="solo_owner",
        )
        bogus = self.verify(selection_id)
        self.assertEqual(bogus.status_code, 200, bogus.content[:400])
        bogus_gate = bogus.json()["items"][0]["editorial_review"]
        self.assertEqual(bogus_gate["status"], "blocked")
        self.assertIn("DECISION_REQUIRED", bogus_gate["blockers"])
        self.assertFalse(bogus.json()["publication_available"])
        self.assertFalse(bogus.json()["approved"])
        self.assertNotIn("P16 confidential brain", bogus.content.decode())

    def test_assessment_review_readiness_missing_policy_fails_closed(self):
        from .cms_review_models import ReviewPolicy
        entry = self.entry("assessment", "assessment-instrument", str(self.assessment.pk))
        selection_id = self.post_selection("assessment", [entry]).json()["id"]
        ReviewPolicy.objects.filter(pk=1).delete()
        result = self.verify(selection_id)
        self.assertEqual(result.status_code, 503, result.content[:400])
        self.assertEqual(result.json()["code"], "REVIEW_POLICY_UNAVAILABLE")
        self.assertNotIn("P16 confidential assessment", result.content.decode())

    def test_verify_editorial_revision_and_policy_change_never_approve(self):
        from .cms_models import RolePolicy
        entry = self.entry("brain", "brain-anatomical-entity", str(self.brain.pk))
        selection_id = self.post_selection("brain", [entry]).json()["id"]
        current = self.verify(selection_id)
        self.assertEqual(current.status_code, 200, current.content[:300])
        self.assertTrue(current.json()["all_snapshots_current"])
        self.assertIn("LIVE_SOURCE_RIGHTS_REVALIDATION_REQUIRED", current.json()["review_blockers"])
        policy = RolePolicy.objects.get(pk=1)
        policy.version += 1
        policy.save(update_fields=["version"])
        policy_changed = self.verify(selection_id)
        self.assertEqual(policy_changed.status_code, 200, policy_changed.content[:350])
        self.assertFalse(policy_changed.json()["policy_matches"])
        self.assertFalse(policy_changed.json()["all_snapshots_current"])
        self.assertEqual(policy_changed.json()["items"][0]["snapshot_state"], "matching")
        data = {"name_en": "New confidential proposed payload"}
        revision = ContentRevision.objects.create(
            state=self.brain, sequence=2, base_version=1,
            base_digest=digest({}), payload=data, payload_digest=digest(data),
            dependency_digest=digest({}), status="draft", actor=self.owner,
        )
        self.brain.current_revision = revision
        self.brain.version = 2
        self.brain.save(update_fields=["current_revision", "version"])
        stale = self.verify(selection_id)
        self.assertEqual(stale.status_code, 200, stale.content[:350])
        self.assertEqual(stale.json()["items"][0]["snapshot_state"], "stale")
        self.assertNotIn("confidential", stale.content.decode())
        self.assertEqual(ContentState.objects.get(pk=self.brain.pk).publication, "never_published")

    def test_verify_requires_actor_and_live_permissions_and_closed_query(self):
        from django.contrib.auth.models import Permission
        entry = self.entry("learning", "quiz", self.quiz.pk)
        selection_id = self.post_selection("learning", [entry]).json()["id"]
        independent = self.user("verify-other", staff=True,
            caps=("cms_enter", "cms_learning_view", "cms_publication_validate_learning",
                  "cms_publication_select_learning"))
        other_client = self.sign_in(independent)
        self.assertEqual(self.verify(selection_id, client=other_client).status_code, 404)
        self.assertEqual(self.verify(selection_id, extra="?leak=1").status_code, 400)
        own = self.post(other_client, "publication/selections/", {
            "domain": "learning", "entries": [entry],
            "request_key": str(uuid.uuid4()),
        })
        self.assertEqual(own.status_code, 201, own.content[:300])
        self.assertEqual(self.verify(own.json()["id"], client=other_client).status_code, 200)
        permission = Permission.objects.get(
            content_type__app_label="atlas", content_type__model="rolepolicy",
            codename="cms_publication_select_learning",
        )
        independent.user_permissions.remove(permission)
        self.assertEqual(self.verify(own.json()["id"], client=other_client).status_code, 403)
        self.assertEqual(self.verify(selection_id, client=other_client).status_code, 404)
        # Verification never creates another selection or event.
        from .cms_publication_selection_models import PublicationCandidateSelection
        self.assertEqual(PublicationCandidateSelection.objects.count(), 2)

    def test_verify_rechecks_session_after_waiting_for_candidate_snapshot(self):
        from datetime import timedelta
        from unittest.mock import patch
        from django.utils import timezone
        from .cms_models import AdminSession
        from .cms_publication_selection import _resolve

        entry = self.entry("learning", "quiz", self.quiz.pk)
        selection_id = self.post_selection("learning", [entry]).json()["id"]
        session_id = self.owner_client.session["cms_session_id"]

        def expire_during_resolution(*args, **kwargs):
            result = _resolve(*args, **kwargs)
            AdminSession.objects.filter(pk=session_id).update(expires_at=timezone.now() - timedelta(seconds=1))
            return result

        with patch("atlas.cms_publication_selection._resolve", side_effect=expire_during_resolution):
            response = self.verify(selection_id)
        self.assertEqual(response.status_code, 403, response.content[:300])
        self.assertEqual(response.json()["code"], "UNAUTHENTICATED")

    def source_proposal(self, domain):
        from .models import AssessmentInstrument, BrainAnatomicalEntity, SourceReference

        source = SourceReference.objects.create(title="Synthetic dependency evidence",
            citation="Synthetic private citation", doi="10.1234/fake.p16.dependency",
            verification_status="source_checked")
        if domain == "brain":
            parent = BrainAnatomicalEntity.objects.create(
                slug="p16-live-parent", name_en="Synthetic brain parent", is_active=False,
                kind="region", laterality="not_established")
            kind, parent_field = "brain-anatomical-alias", "entity"
        else:
            parent = AssessmentInstrument.objects.create(
                slug="p16-live-parent", name_en="Synthetic assessment parent", is_active=False)
            kind, parent_field = "assessment-alias", "instrument"
        proposal = self.proposal(kind, "", {parent_field: parent.pk, "source": source.pk,
            "text": "Synthetic private alias", "language": "en", "alias_type": "alternative"})
        entry = self.entry(domain, kind, str(proposal.pk))
        return source, parent, proposal, entry

    def test_rights_evidence_is_explicit_and_never_equivalent_to_publication_clearance(self):
        for domain in ("brain", "assessment"):
            with self.subTest(domain=domain):
                source, _, _, entry = self.source_proposal(domain)
                selected = self.post_selection(domain, [entry])
                self.assertEqual(selected.status_code, 201, selected.content[:300])
                result = self.verify(selected.json()["id"])
                self.assertEqual(result.status_code, 200, result.content[:300])
                row = result.json()["items"][0]["source_rights_evidence"]
                self.assertEqual(row["status"], "not_established")
                self.assertEqual(row["scope"], "source_metadata_public_display_only")
                self.assertEqual(row["source_count"], 1)
                self.assertEqual(row["permitted_count"], 0)
                self.assertEqual(row["unverified_count"], 1)
                self.assertFalse(row["publication_rights_cleared"])
                self.assertFalse(result.json()["approved"])
                self.assertFalse(result.json()["publication_available"])
                self.assertNotIn("Synthetic private citation", result.content.decode())
                self.assertNotIn(str(source.doi), result.content.decode())

    def test_approved_governance_scope_is_counted_but_never_licenses_the_proposal(self):
        from django.utils import timezone
        from .cms_governance import resource_binding
        source, _, _, entry = self.source_proposal("brain")
        selection_id = self.post_selection("brain", [entry]).json()["id"]
        evidence = [{"source_id": source.pk, "locator": "Synthetic rights worksheet section"}]
        binding = resource_binding("source_reference", source.pk)
        response = self.post(self.owner_client, "governance/rights/", {
            "resource_type": "source_reference", "resource_id": source.pk,
            "resource_version": binding["resource_version"], "evidence": evidence,
            "reason": "CORRECTION_REQUIRED", "material": "metadata",
            "intended_use": "public_display", "status": "allowed",
            "rightsholder": "Fictional holder", "holder_identification": "Synthetic only",
            "holder_evidence": evidence, "public_access": "unknown",
            "reviewed_on": timezone.localdate().isoformat(),
            "effective_on": timezone.localdate().isoformat(),
            "expires_on": None, "review_on": None,
            "limitations": "Test fixture no real rights", "territory": "", "conflict_note": "",
        })
        self.assertEqual(response.status_code, 201, response.content[:500])
        record = response.json()["record"]
        created = self.verify(selection_id)
        self.assertEqual(created.status_code, 200, created.content[:400])
        self.assertEqual(created.json()["items"][0]["source_rights_evidence"]["status"], "not_established")
        assigned = self.post(
            self.owner_client, f"governance/rights/{record['id']}/assign/",
            {"reviewer_id": self.owner.pk}, etag=f'"{record["version"]}"',
        )
        self.assertEqual(assigned.status_code, 200, assigned.content[:450])
        record = assigned.json()["record"]
        decided = self.post(
            self.owner_client, f"governance/rights/{record['id']}/decide/",
            {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED", "self_review_ack": True},
            etag=f'"{record["version"]}"',
        )
        self.assertEqual(decided.status_code, 200, decided.content[:450])
        current = self.verify(selection_id)
        self.assertEqual(current.status_code, 200, current.content[:500])
        coverage = current.json()["items"][0]["source_rights_evidence"]
        self.assertEqual(coverage["status"], "recorded")
        self.assertEqual(coverage["permitted_count"], 1)
        self.assertEqual(coverage["unverified_count"], 0)
        self.assertFalse(coverage["publication_rights_cleared"])
        self.assertFalse(current.json()["approved"])
        self.assertFalse(current.json()["publication_available"])
        self.assertFalse(current.json()["all_snapshots_current"])
        self.assertNotIn("Fictional holder", current.content.decode())

    def test_rights_evidence_never_treats_legacy_or_unapproved_as_permission(self):
        from unittest.mock import patch
        from .cms_publication_selection import _source_rights_coverage
        with patch("atlas.cms_publication_selection.resource_binding",
                   return_value={"resource_version": "fixed"}) as binding:
            with patch("atlas.cms_publication_selection.rights_eligibility",
                       return_value={"eligible": True, "permitted": False, "status": "legacy",
                                     "registered": False, "blockers": []}) as gate:
                result = _source_rights_coverage([10, 20])
        self.assertEqual(result["status"], "not_established")
        self.assertEqual(result["permitted_count"], 0)
        self.assertEqual(result["unverified_count"], 2)
        self.assertFalse(result["publication_rights_cleared"])
        self.assertEqual(binding.call_count, 2)
        self.assertEqual(gate.call_count, 2)

    def test_rights_evidence_reports_only_bounded_scope_and_safely_declines_large_closure(self):
        from unittest.mock import patch
        from .cms_publication_selection import _source_rights_coverage
        self.assertEqual(_source_rights_coverage([])["status"], "no_sources")
        with patch("atlas.cms_publication_selection.resource_binding") as binding:
            too_many = _source_rights_coverage(list(range(1, 33)))
        self.assertEqual(too_many["status"], "unverifiable")
        self.assertFalse(too_many["publication_rights_cleared"])
        binding.assert_not_called()
        budget = {"remaining": 1}
        with patch("atlas.cms_publication_selection.resource_binding",
                   return_value={"resource_version": "fixed"}) as scoped_binding:
            with patch("atlas.cms_publication_selection.rights_eligibility",
                       return_value={"registered": True, "permitted": True}) as gate:
                first = _source_rights_coverage([10], budget=budget)
                second = _source_rights_coverage([20], budget=budget)
        self.assertEqual(first["status"], "recorded")
        self.assertEqual(first["permitted_count"], 1)
        self.assertFalse(first["publication_rights_cleared"])
        self.assertEqual(second["status"], "unverifiable")
        self.assertEqual(second["unverified_count"], 1)
        self.assertEqual(budget["remaining"], 0)
        self.assertEqual(scoped_binding.call_count, 1)
        self.assertEqual(gate.call_count, 1)

    def test_rights_budget_counts_distinct_sources_across_a_selection_without_public_clearance(self):
        from unittest.mock import patch
        from .cms_publication_selection import _source_rights_coverage

        budget = {"remaining": 2}
        with patch("atlas.cms_publication_selection.resource_binding",
                   return_value={"resource_version": "synthetic"}) as binding:
            with patch("atlas.cms_publication_selection.rights_eligibility",
                       return_value={"registered": True, "permitted": True}) as gate:
                first = _source_rights_coverage([11, 12], budget=budget)
                repeated = _source_rights_coverage([12, 11, 12], budget=budget)
                over_budget = _source_rights_coverage([11, 13], budget=budget)
        self.assertEqual(first["status"], "recorded")
        self.assertEqual(repeated["status"], "recorded")
        self.assertEqual(repeated["source_count"], 2)
        self.assertEqual(repeated["permitted_count"], 2)
        self.assertEqual(over_budget["status"], "unverifiable")
        self.assertEqual(over_budget["unverified_count"], 2)
        self.assertFalse(first["publication_rights_cleared"])
        self.assertFalse(repeated["publication_rights_cleared"])
        self.assertFalse(over_budget["publication_rights_cleared"])
        self.assertEqual(binding.call_count, 2)
        self.assertEqual(gate.call_count, 2)
        self.assertEqual(budget["remaining"], 0)

    def test_shared_source_is_inspected_once_per_recheck_and_denominators_stay_item_based(self):
        from unittest.mock import patch
        from .cms_publication_selection_models import PublicationCandidateSelection

        source, parent, first, first_entry = self.source_proposal("brain")
        second = self.proposal("brain-anatomical-alias", "", {
            "entity": parent.pk, "source": source.pk,
            "text": "Second synthetic private alias", "language": "en",
            "alias_type": "alternative",
        })
        second_entry = self.entry("brain", "brain-anatomical-alias", str(second.pk))
        created = self.post_selection("brain", [first_entry, second_entry])
        self.assertEqual(created.status_code, 201, created.content[:300])
        with patch("atlas.cms_publication_selection.MAX_RIGHTS_SOURCES", 1):
            rechecked = self.verify(created.json()["id"])
        self.assertEqual(rechecked.status_code, 200, rechecked.content[:300])
        body = rechecked.json()
        self.assertEqual(body["item_count"], 2)
        self.assertEqual(body["recheck_summary"]["item_count"], 2)
        self.assertEqual(body["recheck_summary"]["source_rights_counts"]["not_established"], 2)
        self.assertEqual(sum(body["recheck_summary"]["source_rights_counts"].values()), 2)
        self.assertEqual([item["source_rights_evidence"]["status"]
                         for item in body["items"]], ["not_established", "not_established"])
        self.assertFalse(body["recheck_summary"]["publication_readiness_proven"])
        self.assertFalse(body["approved"])
        self.assertFalse(body["publication_available"])
        self.assertEqual(PublicationCandidateSelection.objects.count(), 1)
        self.assertNotIn("Second synthetic private alias", rechecked.content.decode())
        self.assertNotIn(str(source.doi), rechecked.content.decode())

    def test_review_selection_recheck_summary_keeps_freshness_separate_from_publication(self):
        from .cms_publication_selection_models import PublicationCandidateSelection
        entry = self.entry("brain", "brain-anatomical-entity", str(self.brain.pk))
        selected = self.post_selection("brain", [entry])
        self.assertEqual(selected.status_code, 201)
        count = PublicationCandidateSelection.objects.count()
        result = self.verify(selected.json()["id"])
        self.assertEqual(result.status_code, 200, result.content[:300])
        body = result.json()
        summary = body["recheck_summary"]
        self.assertEqual(summary["snapshot_counts"]["matching"], 1)
        self.assertEqual(summary["snapshot_counts"]["stale"], 0)
        self.assertEqual(summary["item_count"], 1)
        self.assertEqual(summary["editorial_review_counts"]["blocked"], 1)
        self.assertEqual(summary["source_rights_counts"]["no_sources"], 1)
        self.assertEqual(summary["content_issue_items"], 0)
        self.assertFalse(summary["publication_readiness_proven"])
        self.assertFalse(body["approved"])
        self.assertFalse(body["publication_available"])
        self.assertEqual(PublicationCandidateSelection.objects.count(), count)
        self.assertNotIn("P16 confidential brain", result.content.decode())

        from .cms_models import RolePolicy
        policy = RolePolicy.objects.get(pk=1)
        policy.version += 1
        policy.save(update_fields=["version"])
        changed = self.verify(selected.json()["id"])
        self.assertEqual(changed.status_code, 200)
        self.assertFalse(changed.json()["all_snapshots_current"])
        self.assertEqual(changed.json()["recheck_summary"]["snapshot_counts"]["matching"], 1)
        self.assertFalse(changed.json()["recheck_summary"]["publication_readiness_proven"])

    def test_editorial_selection_binds_live_sources_and_recovers_its_original_receipt(self):
        for domain in ("brain", "assessment"):
            with self.subTest(domain=domain):
                source, _, _, entry = self.source_proposal(domain)
                key = uuid.uuid4()
                created = self.post_selection(domain, [entry], key=key)
                self.assertEqual(created.status_code, 201, created.content[:300])
                selection_id = created.json()["id"]
                current = self.verify(selection_id)
                self.assertEqual(current.json()["items"][0]["dependency_state"], "matching")
                source.citation = "Synthetic confidential citation changed after selection"
                source.save(update_fields=("citation",))
                changed = self.verify(selection_id)
                self.assertEqual(changed.status_code, 200, changed.content[:300])
                row = changed.json()["items"][0]
                self.assertEqual(row["snapshot_state"], "matching")
                self.assertEqual(row["dependency_state"], "stale")
                self.assertFalse(changed.json()["all_snapshots_current"])
                self.assertNotIn("confidential citation", changed.content.decode())
                recovered = self.post_selection(domain, [entry], key=key)
                self.assertEqual(recovered.status_code, 200)
                self.assertEqual(recovered.json()["id"], selection_id)
                self.assertTrue(recovered.json()["recovered"])

    def test_editorial_selection_detects_parent_and_source_lifecycle_changes(self):
        from .cms_source_models import SourceState

        source, parent, _, entry = self.source_proposal("brain")
        selection_id = self.post_selection("brain", [entry]).json()["id"]
        parent.name_en = "A changed private parent name"
        parent.save(update_fields=("name_en",))
        changed = self.verify(selection_id)
        self.assertEqual(changed.json()["items"][0]["dependency_state"], "stale")
        SourceState.objects.create(source_pk=source.pk, archived=True)
        archived = self.verify(selection_id)
        self.assertEqual(archived.status_code, 200, archived.content[:300])
        self.assertIn("SOURCE_UNAVAILABLE", archived.json()["items"][0]["dependency_issues"])
        self.assertFalse(archived.json()["all_snapshots_current"])

    def test_editorial_selection_detects_rights_proposal_and_review_policy_changes(self):
        from django.utils import timezone
        from .cms_governance import resource_binding
        from .cms_review_models import ReviewPolicy

        source, _, _, entry = self.source_proposal("assessment")
        selection_id = self.post_selection("assessment", [entry]).json()["id"]
        binding = resource_binding("source_reference", source.pk)
        evidence = [{"source_id": source.pk, "locator": "Synthetic permission evidence only"}]
        rights = self.post(self.owner_client, "governance/rights/", {
            "resource_type": "source_reference", "resource_id": source.pk,
            "resource_version": binding["resource_version"], "evidence": evidence,
            "reason": "CORRECTION_REQUIRED", "material": "metadata", "intended_use": "public_display",
            "status": "allowed", "rightsholder": "Synthetic holder", "holder_identification": "Fictional test holder",
            "holder_evidence": evidence, "public_access": "unknown",
            "reviewed_on": timezone.localdate().isoformat(), "effective_on": timezone.localdate().isoformat(),
            "expires_on": None, "review_on": None, "limitations": "Synthetic data only",
            "territory": "", "conflict_note": "",
        })
        self.assertEqual(rights.status_code, 201, rights.content[:300])
        changed = self.verify(selection_id)
        self.assertEqual(changed.json()["items"][0]["dependency_state"], "stale")
        self.assertFalse(changed.json()["approved"])
        # A new snapshot binds the changed governance state, then policy drift invalidates it.
        newer_id = self.post_selection("assessment", [entry]).json()["id"]
        policy = ReviewPolicy.objects.get(pk=1)
        policy.version += 1
        policy.save(update_fields=("version",))
        changed_policy = self.verify(newer_id)
        self.assertEqual(changed_policy.json()["items"][0]["dependency_state"], "stale")
        self.assertFalse(changed_policy.json()["all_snapshots_current"])

    def test_legacy_selection_reports_missing_live_baseline_without_rewriting_history(self):
        from .cms_publication_selection_models import PublicationCandidateSelection

        entry = self.entry("brain", "brain-anatomical-entity", str(self.brain.pk))
        current_id = self.post_selection("brain", [entry]).json()["id"]
        current = PublicationCandidateSelection.objects.get(pk=current_id)
        manifest = {**current.selection, "schema": "cms-review-selection-v1",
            "items": [{key: value for key, value in row.items() if key != "live_dependencies"}
                      for row in current.selection["items"]]}
        legacy = PublicationCandidateSelection.objects.create(
            domain="brain", request_key=uuid.uuid4(), request_digest=digest({}),
            selection=manifest, selection_digest=digest(manifest),
            policy_version=current.policy_version, actor=self.owner, actor_ref=current.actor_ref)
        response = self.verify(legacy.pk)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(response.json()["items"][0]["dependency_state"], "baseline_missing")
        self.assertFalse(response.json()["all_snapshots_current"])
        self.assertIn("LIVE_DEPENDENCY_BASELINE_REQUIRED", response.json()["review_blockers"])
        legacy.refresh_from_db()
        self.assertEqual(legacy.selection_digest, digest(manifest))

    def test_dependency_limit_failure_keeps_a_current_baseline_unverifiable(self):
        from unittest.mock import patch
        from rest_framework.exceptions import ValidationError

        entry = self.entry("brain", "brain-anatomical-entity", str(self.brain.pk))
        selection_id = self.post_selection("brain", [entry]).json()["id"]
        with patch("atlas.cms_publication_selection.dependency_snapshot",
                   side_effect=ValidationError({"dependencies": "Private internal validation detail"})):
            response = self.verify(selection_id)
        self.assertEqual(response.status_code, 200, response.content[:300])
        row = response.json()["items"][0]
        self.assertEqual(row["snapshot_state"], "unverifiable")
        self.assertEqual(row["dependency_state"], "invalid")
        self.assertEqual(row["dependency_issues"], ["DEPENDENCY_UNVERIFIABLE"])
        self.assertNotIn("Private internal", response.content.decode())
        self.assertNotIn("LIVE_DEPENDENCY_BASELINE_REQUIRED", response.json()["review_blockers"])

    def test_mismatched_stored_payload_hash_fails_closed(self):
        payload = {"name_en": "Synthetic private damaged payload"}
        state = self.proposal("brain-network", "", payload)
        revision = ContentRevision.objects.create(state=state, sequence=2, base_version=1,
            base_digest=digest({}), payload=payload, payload_digest="0" * 64,
            dependency_digest=digest({}), status="draft", actor=self.owner)
        state.current_revision, state.version = revision, 2
        state.save(update_fields=("current_revision", "version"))
        entry = self.entry("brain", "brain-network", str(state.pk))
        response = self.post_selection("brain", [entry])
        self.assertEqual(response.status_code, 409, response.content[:300])
        self.assertEqual(response.json()["code"], "SELECTION_INTEGRITY_FAILED")
        self.assertNotIn("damaged payload", response.content.decode())
