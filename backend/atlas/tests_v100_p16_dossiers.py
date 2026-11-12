"""P16 immutable, non-authorizing preparation dossiers for later human review."""
import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from .cms_content import digest
from .cms_content_models import ContentRevision, ContentState
from .cms_models import AdminAuditEvent, RolePolicy
from .cms_publication_selection_models import PublicationCandidateSelection
from .models import Category, Disorder, Quiz, QuizQuestion, QuizChoice
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PublicationPreparationDossierTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_client = self.sign_in(self.owner)
        self.state = ContentState.objects.create(
            kind="brain-anatomical-entity", canonical_digest=digest({}),
        )
        payload = {"name_en": "PRIVATE_P16_PREPARATION_PROPOSAL"}
        rev = ContentRevision.objects.create(
            state=self.state, sequence=1, base_version=0, base_digest=digest({}),
            payload=payload, payload_digest=digest(payload),
            dependency_digest=digest({}), status="draft", actor=self.owner,
        )
        self.state.current_revision = rev
        self.state.version = 1
        self.state.save(update_fields=["current_revision", "version"])

    def select_brain(self):
        inventory = self.owner_client.get(BASE + "publication/preflight/?domain=brain")
        self.assertEqual(inventory.status_code, 200, inventory.content[:400])
        row = next(item for item in inventory.json()["results"]
                   if item["resource_id"] == str(self.state.pk))
        selection = self.post(self.owner_client, "publication/selections/", {
            "domain": "brain", "request_key": str(uuid.uuid4()),
            "entries": [{"kind": self.state.kind, "resource_id": str(self.state.pk),
                         "expected_digest": row["proposal_digest"]}],
        })
        self.assertEqual(selection.status_code, 201, selection.content[:500])
        return selection.json()

    def prepare(self, selected, *, key=None, client=None, **extra):
        return self.post(client or self.owner_client,
                         f'publication/selections/{selected["id"]}/prepare/', {
            "selection_digest": selected["selection_digest"],
            "request_key": str(key or uuid.uuid4()),
            **extra,
        })

    def test_explicit_historical_batch_recheck_is_ordered_scoped_and_read_only(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier
        selected = self.select_brain()
        first = self.prepare(selected).json()
        second = self.prepare(selected).json()
        base = BASE + "publication/preparations/recheck/?domain=brain"
        recent = self.owner_client.get(base + "&limit=1")
        self.assertEqual(recent.status_code, 200)
        self.assertEqual(recent.json()["results"][0]["id"], second["id"])
        explicit = self.owner_client.get(base + "&ids=" + first["id"])
        self.assertEqual(explicit.status_code, 200, explicit.content[:500])
        self.assertEqual(explicit.json()["results"][0]["id"], first["id"])
        self.assertEqual(explicit.json()["checked_count"], 1)
        self.assertTrue(explicit.json()["results"][0]["snapshot_current"])
        self.assertFalse(explicit.json()["publication_available"])
        for suffix in (
            "&ids=" + first["id"] + "," + first["id"],
            "&ids=" + first["id"] + "&limit=1",
            "&ids=" + first["id"] + "&ids=" + second["id"],
            "&ids=not-an-id", "&ids=",
            "&ids=" + ",".join([first["id"]] * 6),
        ):
            self.assertEqual(self.owner_client.get(base + suffix).status_code, 400, suffix)
        other = self.sign_in(self.user("p16-explicit-foreign", staff=True, caps=(
            "cms_enter", "cms_brain_view", "cms_publication_validate_brain",
            "cms_publication_select_brain",
        )))
        self.assertEqual(other.get(base + "&ids=" + first["id"]).status_code, 404)
        self.assertEqual(self.owner_client.get(
            BASE + "publication/preparations/recheck/?domain=assessment&ids=" + first["id"]
        ).status_code, 404)
        self.assertEqual(PublicationPreparationDossier.objects.count(), 2)

    def test_bounded_batch_recheck_detects_drift_without_publication_or_leakage(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier

        selected = self.select_brain()
        first = self.prepare(selected).json()
        second = self.prepare(selected).json()
        base = BASE + "publication/preparations/recheck/?domain=brain&limit=2"
        fresh = self.owner_client.get(base)
        self.assertEqual(fresh.status_code, 200, fresh.content[:450])
        data = fresh.json()
        self.assertEqual(data["scope"], "actor_owned_current_private_dossier_rechecks")
        self.assertEqual(data["checked_count"], 2)
        self.assertEqual(data["current_count"], 2)
        self.assertEqual(data["stale_count"], 0)
        self.assertEqual([row["id"] for row in data["results"]], [second["id"], first["id"]])
        self.assertTrue(all(row["snapshot_current"] for row in data["results"]))
        self.assertFalse(data["approved"])
        self.assertFalse(data["publication_available"])
        self.assertNotIn("PRIVATE_P16_PREPARATION_PROPOSAL", fresh.content.decode())

        payload = {"name_en": "PRIVATE_CHANGED_AFTER_BULK_SEAL"}
        rev = ContentRevision.objects.create(
            state=self.state, sequence=2, base_version=1, base_digest=digest({}),
            payload=payload, payload_digest=digest(payload),
            dependency_digest=digest({}), status="draft", actor=self.owner,
        )
        self.state.current_revision = rev
        self.state.version = 2
        self.state.save(update_fields=["current_revision", "version"])
        stale = self.owner_client.get(base)
        self.assertEqual(stale.status_code, 200, stale.content[:450])
        self.assertEqual(stale.json()["current_count"], 0)
        self.assertEqual(stale.json()["stale_count"], 2)
        self.assertFalse(any(row["snapshot_current"] for row in stale.json()["results"]))
        self.assertNotIn("PRIVATE_CHANGED_AFTER_BULK_SEAL", stale.content.decode())
        self.assertEqual(PublicationPreparationDossier.objects.count(), 2)
        self.assertEqual(ContentState.objects.get(pk=self.state.pk).publication, "never_published")

        foreign = self.sign_in(self.user("p16-batch-foreign", staff=True, caps=(
            "cms_enter", "cms_brain_view", "cms_publication_validate_brain",
            "cms_publication_select_brain",
        )))
        self.assertEqual(foreign.get(base).status_code, 200)
        self.assertEqual(foreign.get(base).json()["checked_count"], 0)
        not_authorized = self.sign_in(self.user("p16-batch-no-access", staff=True, caps=("cms_enter",)))
        self.assertEqual(not_authorized.get(base).status_code, 403)
        for query in (
            "domain=brain&limit=0", "domain=brain&limit=6",
            "domain=brain&limit=2&raw=true", "domain=brain&domain=assessment",
            "domain=cases", "limit=2", "domain=brain&limit=1&limit=2",
        ):
            self.assertEqual(self.owner_client.get(
                BASE + "publication/preparations/recheck/?" + query).status_code, 400, query)
        self.assertEqual(self.post(
            self.owner_client, "publication/preparations/recheck/", {}).status_code, 405)

    def test_preparation_inbox_is_owner_scoped_bounded_and_content_free(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier
        selection = self.select_brain()
        first = self.prepare(selection).json()
        second = self.prepare(selection).json()
        self.assertEqual(PublicationPreparationDossier.objects.count(), 2)
        url = BASE + "publication/preparations/?domain=brain&page=1&page_size=1"
        response = self.owner_client.get(url)
        self.assertEqual(response.status_code, 200, response.content[:400])
        body = response.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["page_size"], 1)
        self.assertEqual(len(body["results"]), 1)
        self.assertEqual(body["results"][0]["id"], second["id"])
        self.assertEqual(body["results"][0]["status"], "preparation_only")
        self.assertFalse(body["results"][0]["approved"])
        self.assertFalse(body["results"][0]["publication_available"])
        self.assertNotIn("PRIVATE_P16_PREPARATION_PROPOSAL", response.content.decode())
        page2 = self.owner_client.get(
            BASE + "publication/preparations/?domain=brain&page=2&page_size=1")
        self.assertEqual(page2.status_code, 200)
        self.assertEqual(page2.json()["results"][0]["id"], first["id"])
        self.assertEqual(self.owner_client.get(
            BASE + "publication/preparations/?domain=assessment").json()["count"], 0)
        self.assertEqual(self.owner_client.get(
            BASE + "publication/preparations/?domain=brain&page=3&page_size=1").status_code, 400)
        self.assertEqual(self.owner_client.get(
            BASE + "publication/preparations/?domain=brain&page_size=200").status_code, 400)
        self.assertEqual(self.owner_client.get(
            BASE + "publication/preparations/?domain=brain&debug=true").status_code, 400)
        self.assertEqual(self.owner_client.get(
            BASE + "publication/preparations/?domain=brain&domain=assessment").status_code, 400)
        self.assertEqual(self.owner_client.get(
            BASE + "publication/preparations/").status_code, 400)
        self.assertEqual(PublicationPreparationDossier.objects.count(), 2)

        other_actor = self.user("p16-inbox-foreign", staff=True, caps=(
            "cms_enter", "cms_brain_view", "cms_publication_validate_brain",
            "cms_publication_select_brain",
        ))
        other = self.sign_in(other_actor)
        foreign = other.get(url)
        self.assertEqual(foreign.status_code, 200)
        self.assertEqual(foreign.json()["count"], 0)
        self.assertNotIn(first["id"], foreign.content.decode())
        no_access = self.user("p16-inbox-no-grant", staff=True, caps=("cms_enter",))
        denied = self.sign_in(no_access)
        self.assertEqual(denied.get(url).status_code, 403)

    def test_prepare_creates_immutable_recoverable_non_authorizing_dossier(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier

        selected = self.select_brain()
        key = uuid.uuid4()
        result = self.prepare(selected, key=key)
        self.assertEqual(result.status_code, 201, result.content[:500])
        data = result.json()
        self.assertEqual(data["status"], "preparation_only")
        self.assertEqual(data["domain"], "brain")
        self.assertEqual(data["item_count"], 1)
        self.assertEqual(len(data["dossier_digest"]), 64)
        self.assertEqual(data["selection_digest"], selected["selection_digest"])
        self.assertFalse(data["approved"])
        self.assertFalse(data["publication_available"])
        self.assertNotIn("PRIVATE_P16_PREPARATION_PROPOSAL", result.content.decode())
        self.assertEqual(PublicationPreparationDossier.objects.count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(
            action="publication.preparation_created").count(), 1)
        dossier = PublicationPreparationDossier.objects.get()
        self.assertEqual(dossier.dossier["schema"], "cms-publication-preparation-v1")
        self.assertEqual(dossier.dossier["selection_snapshot"]["schema"], "cms-review-selection-v2")
        self.assertFalse(dossier.dossier["authority"]["publication_available"])
        self.assertEqual(dossier.dossier["recheck_at_seal"]["items"][0]["snapshot_state"], "matching")
        self.assertEqual(dossier.dossier_digest, digest(dossier.dossier))
        with self.assertRaises(ValidationError):
            dossier.save()
        with self.assertRaises(ValidationError):
            PublicationPreparationDossier.objects.filter(pk=dossier.pk).update(
                dossier_digest="0" * 64)
        with self.assertRaises(ValidationError):
            PublicationPreparationDossier.objects.filter(pk=dossier.pk).delete()

        recovered = self.prepare(selected, key=key)
        self.assertEqual(recovered.status_code, 200, recovered.content[:500])
        self.assertEqual(recovered.json()["id"], data["id"])
        self.assertTrue(recovered.json()["recovered"])
        self.assertEqual(PublicationPreparationDossier.objects.count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(
            action="publication.preparation_created").count(), 1)

        detail = self.owner_client.get(BASE + f'publication/preparations/{data["id"]}/')
        self.assertEqual(detail.status_code, 200, detail.content[:400])
        self.assertEqual(detail.json()["dossier_digest"], data["dossier_digest"])
        current = self.owner_client.get(BASE + f'publication/preparations/{data["id"]}/verify/')
        self.assertEqual(current.status_code, 200, current.content[:400])
        self.assertTrue(current.json()["snapshot_current"])
        self.assertFalse(current.json()["publication_available"])
        self.assertFalse(current.json()["approved"])
        self.assertNotIn("PRIVATE_P16_PREPARATION_PROPOSAL", current.content.decode())
        self.assertEqual(ContentState.objects.get(pk=self.state.pk).publication, "never_published")

    def test_unknown_outcome_retry_returns_same_dossier_after_source_drift(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier
        selected = self.select_brain()
        request_key = uuid.uuid4()
        first = self.prepare(selected, key=request_key)
        self.assertEqual(first.status_code, 201, first.content[:400])
        before_id = first.json()["id"]
        payload = {"name_en": "PRIVATE_P16_AFTER_LOST_RESPONSE"}
        revision = ContentRevision.objects.create(
            state=self.state, sequence=2, base_version=1, base_digest=digest({}),
            payload=payload, payload_digest=digest(payload),
            dependency_digest=digest({}), status="draft", actor=self.owner,
        )
        self.state.current_revision = revision
        self.state.version = 2
        self.state.save(update_fields=["current_revision", "version"])
        recovered = self.prepare(selected, key=request_key)
        self.assertEqual(recovered.status_code, 200, recovered.content[:300])
        self.assertTrue(recovered.json()["recovered"])
        self.assertEqual(recovered.json()["id"], before_id)
        self.assertEqual(recovered.json()["dossier_digest"], first.json()["dossier_digest"])
        self.assertEqual(self.prepare(selected).status_code, 409)
        self.assertEqual(PublicationPreparationDossier.objects.count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(
            action="publication.preparation_created").count(), 1)
        stale = self.owner_client.get(
            BASE + f"publication/preparations/{before_id}/verify/")
        self.assertEqual(stale.status_code, 200)
        self.assertFalse(stale.json()["snapshot_current"])
        self.assertFalse(stale.json()["approved"])
        self.assertNotIn("PRIVATE_P16_AFTER_LOST_RESPONSE", recovered.content.decode())

    def test_content_policy_and_live_review_change_marks_dossier_stale_without_rewriting(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier
        selected = self.select_brain()
        dossier_id = self.prepare(selected).json()["id"]
        original = PublicationPreparationDossier.objects.get().dossier_digest
        new_payload = {"name_en": "PRIVATE_P16_CHANGED_AFTER_SEAL"}
        new_rev = ContentRevision.objects.create(
            state=self.state, sequence=2, base_version=1, base_digest=digest({}),
            payload=new_payload, payload_digest=digest(new_payload),
            dependency_digest=digest({}), status="draft", actor=self.owner,
        )
        self.state.current_revision = new_rev
        self.state.version = 2
        self.state.save(update_fields=["current_revision", "version"])
        current = self.owner_client.get(BASE + f"publication/preparations/{dossier_id}/verify/")
        self.assertEqual(current.status_code, 200, current.content[:350])
        self.assertFalse(current.json()["snapshot_current"])
        self.assertFalse(current.json()["approved"])
        self.assertEqual(current.json()["recheck_summary"]["snapshot_counts"]["stale"], 1)
        self.assertNotIn("PRIVATE_P16_CHANGED_AFTER_SEAL", current.content.decode())
        self.assertEqual(PublicationPreparationDossier.objects.get().dossier_digest, original)

    def test_new_editorial_task_does_not_rewrite_old_review_evidence(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier
        from .cms_review_models import ReviewTask

        selected = self.select_brain()
        created = self.prepare(selected)
        self.assertEqual(created.status_code, 201)
        dossier_id = created.json()["id"]
        before = PublicationPreparationDossier.objects.get().dossier_digest
        current_before = self.owner_client.get(
            BASE + f"publication/preparations/{dossier_id}/verify/")
        self.assertTrue(current_before.json()["snapshot_current"])
        # Marking a task approved without a real append-only decision must
        # never turn the preparation record into a publication approval.
        ReviewTask.objects.create(
            subject=self.state.current_revision, review_type="source",
            assignee=self.owner, status="approved",
            revision_hash="0" * 64, dependency_digest="1" * 64,
            evidence=[], authors=[], policy_version=0, policy_mode="solo_owner",
        )
        changed = self.owner_client.get(
            BASE + f"publication/preparations/{dossier_id}/verify/")
        self.assertEqual(changed.status_code, 200, changed.content[:400])
        self.assertFalse(changed.json()["snapshot_current"])
        self.assertFalse(changed.json()["approved"])
        self.assertFalse(changed.json()["publication_available"])
        self.assertEqual(PublicationPreparationDossier.objects.get().dossier_digest, before)
        self.assertNotIn("PRIVATE_P16_PREPARATION_PROPOSAL", changed.content.decode())

    def test_valid_learning_and_assessment_snapshots_can_be_sealed_without_publication(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier

        category = Category.objects.create(slug="p16-preparation-category", name_en="Private fixture")
        disorder = Disorder.objects.create(
            category=category, slug="p16-preparation-disorder", name_en="Private fixture",
            is_active=True,
        )
        quiz = Quiz.objects.create(
            slug="p16-preparation-quiz", title="PRIVATE_P16_LEARNING_QUIZ",
            disorder=disorder, is_active=False, seed_managed=False,
        )
        q = QuizQuestion.objects.create(quiz=quiz, prompt="PRIVATE_P16_QUIZ_ANSWER")
        QuizChoice.objects.create(question=q, text="Private right answer", is_correct=True)
        QuizChoice.objects.create(question=q, text="Private wrong answer", is_correct=False)
        inventory = self.owner_client.get(BASE + "publication/preflight/?domain=learning")
        self.assertEqual(inventory.status_code, 200)
        row = next(item for item in inventory.json()["results"]
                   if item["kind"] == "quiz" and item["resource_id"] == quiz.pk)
        self.assertEqual(row["content_issues"], [])
        selection = self.post(self.owner_client, "publication/selections/", {
            "domain": "learning", "entries": [{"kind": "quiz", "resource_id": quiz.pk,
                "expected_digest": row["content_digest"]}], "request_key": str(uuid.uuid4()),
        })
        self.assertEqual(selection.status_code, 201)
        learning = self.prepare(selection.json())
        self.assertEqual(learning.status_code, 201, learning.content[:400])
        self.assertFalse(learning.json()["approved"])
        self.assertFalse(Quiz.objects.get(pk=quiz.pk).is_active)
        self.assertNotIn("PRIVATE_P16_LEARNING_QUIZ", learning.content.decode())

        assessment = ContentState.objects.create(
            kind="assessment-instrument", canonical_digest=digest({}),
        )
        payload = {"name_en": "PRIVATE_P16_ASSESSMENT"}
        revision = ContentRevision.objects.create(
            state=assessment, sequence=1, base_version=0,
            base_digest=digest({}), payload=payload, payload_digest=digest(payload),
            dependency_digest=digest({}), actor=self.owner, status="draft",
        )
        assessment.current_revision = revision
        assessment.version = 1
        assessment.save(update_fields=["current_revision", "version"])
        assessment_list = self.owner_client.get(BASE + "publication/preflight/?domain=assessment")
        self.assertEqual(assessment_list.status_code, 200)
        item = next(it for it in assessment_list.json()["results"]
                    if it["resource_id"] == str(assessment.pk))
        selected = self.post(self.owner_client, "publication/selections/", {
            "domain": "assessment", "entries": [{
                "kind": "assessment-instrument", "resource_id": str(assessment.pk),
                "expected_digest": item["proposal_digest"],
            }], "request_key": str(uuid.uuid4()),
        })
        self.assertEqual(selected.status_code, 201)
        sealed = self.prepare(selected.json())
        self.assertEqual(sealed.status_code, 201, sealed.content[:400])
        self.assertEqual(sealed.json()["domain"], "assessment")
        self.assertEqual(PublicationPreparationDossier.objects.count(), 2)
        self.assertEqual(ContentState.objects.get(pk=assessment.pk).publication, "never_published")
        self.assertNotIn("PRIVATE_P16_ASSESSMENT", sealed.content.decode())

    def test_content_issues_prevent_sealing_even_when_digests_match(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier

        category = Category.objects.create(slug="p16-prep-invalid", name_en="Fixture")
        disorder = Disorder.objects.create(
            category=category, slug="p16-prep-invalid-d", name_en="Fixture",
        )
        quiz = Quiz.objects.create(slug="p16-prep-invalid-q",
                                   title="PRIVATE_P16_INVALID", disorder=disorder,
                                   is_active=False, seed_managed=False)
        preflight = self.owner_client.get(BASE + "publication/preflight/?domain=learning")
        item = next(row for row in preflight.json()["results"]
                    if row["kind"] == "quiz" and row["resource_id"] == quiz.pk)
        self.assertIn("NO_ACTIVE_QUESTIONS", item["content_issues"])
        selected = self.post(self.owner_client, "publication/selections/", {
            "domain": "learning", "request_key": str(uuid.uuid4()),
            "entries": [{"kind": "quiz", "resource_id": quiz.pk,
                         "expected_digest": item["content_digest"]}],
        })
        self.assertEqual(selected.status_code, 201)
        verified = self.owner_client.get(
            BASE + f'publication/selections/{selected.json()["id"]}/verify/')
        self.assertTrue(verified.json()["all_snapshots_current"])
        self.assertEqual(self.prepare(selected.json()).status_code, 409)
        self.assertFalse(PublicationPreparationDossier.objects.exists())
        self.assertFalse(Quiz.objects.get(pk=quiz.pk).is_active)

    def test_stale_or_invalid_selection_cannot_be_prepared(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier
        selected = self.select_brain()
        bad = self.prepare(selected, apply=True)
        self.assertEqual(bad.status_code, 400)  # unknown keys cannot request Apply
        self.assertEqual(self.prepare({**selected, "selection_digest": "e" * 64}).status_code, 412)
        self.assertFalse(PublicationPreparationDossier.objects.exists())
        role = RolePolicy.objects.get(pk=1)
        role.version += 1
        role.save(update_fields=["version"])
        self.assertEqual(self.prepare(selected).status_code, 409)
        self.assertFalse(PublicationPreparationDossier.objects.exists())

    def test_request_key_conflict_permission_and_method_guards(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier

        selected = self.select_brain()
        key = uuid.uuid4()
        created = self.prepare(selected, key=key)
        self.assertEqual(created.status_code, 201)
        other_selection = self.select_brain()
        self.assertEqual(self.prepare(other_selection, key=key).status_code, 409)
        second = self.user("p16-dossier-other", staff=True, caps=(
            "cms_enter", "cms_brain_view", "cms_publication_validate_brain",
            "cms_publication_select_brain",
        ))
        other = self.sign_in(second)
        self.assertEqual(self.prepare(selected, key=key, client=other).status_code, 404)
        dossier_id = created.json()["id"]
        self.assertEqual(other.get(BASE + f"publication/preparations/{dossier_id}/").status_code, 404)
        self.assertEqual(other.get(BASE + f"publication/preparations/{dossier_id}/verify/").status_code, 404)
        self.assertEqual(self.owner_client.get(BASE + f"publication/preparations/{dossier_id}/?debug=1").status_code, 400)
        self.assertEqual(self.owner_client.get(BASE + f"publication/preparations/{dossier_id}/verify/?raw=1").status_code, 400)
        self.assertEqual(self.post(self.owner_client, f"publication/preparations/{dossier_id}/verify/", {}).status_code, 405)
        self.assertEqual(PublicationPreparationDossier.objects.count(), 1)
        # Revoke the P16 domain-specific capability on the existing owner
        # session; future dossier access must fail closed.
        from django.contrib.auth.models import Permission
        cap = Permission.objects.get(codename="cms_owner",
                                     content_type__model="rolepolicy")
        cap.user_set.remove(self.owner)
        self.assertEqual(self.owner_client.get(BASE + f"publication/preparations/{dossier_id}/").status_code, 403)

    def test_dossier_integrity_check_rejects_corrupted_persisted_bytes(self):
        from .cms_publication_preparation_models import PublicationPreparationDossier

        selected = self.select_brain()
        dossier_id = self.prepare(selected).json()["id"]
        # Bypass the append-only ORM *only in the disposable test DB* to
        # simulate external storage corruption.
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE atlas_publicationpreparationdossier SET dossier_digest = %s WHERE id = %s",
                ["0" * 64, uuid.UUID(dossier_id).hex if connection.vendor == "sqlite" else uuid.UUID(dossier_id)],
            )
            self.assertEqual(cursor.rowcount, 1)
        response = self.owner_client.get(BASE + f"publication/preparations/{dossier_id}/")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "DOSSIER_INTEGRITY_FAILED")
        self.assertEqual(PublicationPreparationDossier.objects.count(), 1)
