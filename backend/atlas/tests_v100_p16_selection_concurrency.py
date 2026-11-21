"""Native PostgreSQL source-writer contention against sealed dependency rechecks."""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

from django.db import connection, connections, transaction
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature

from .cms_content import digest
from .cms_content_models import ContentRevision, ContentState
from .cms_publication_selection import verify_selection
from .cms_publication_selection_models import PublicationCandidateSelection
from .cms_review_models import ReviewPolicy
from .models import BrainAnatomicalEntity, SourceReference, lock_brain_curation
from .tests_v100_p01 import BASE, SecurityFixture


@skipUnlessDBFeature("has_select_for_update")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PublicationDependencyRaceTests(SecurityFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        ReviewPolicy.objects.get_or_create(pk=1)

    def test_recheck_waits_for_canonical_source_writer_and_observes_committed_change(self):
        owner_client = self.sign_in(self.owner)
        source = SourceReference.objects.create(title="Synthetic source race",
            citation="Synthetic citation before writer", doi="10.1234/fake.p16.race",
            verification_status="source_checked")
        parent = BrainAnatomicalEntity.objects.create(slug="p16-race-parent", name_en="Synthetic race parent",
            kind="region", laterality="not_established", is_active=False)
        payload = {"entity": parent.pk, "source": source.pk, "text": "Synthetic private alias",
            "language": "en", "alias_type": "alternative"}
        state = ContentState.objects.create(kind="brain-anatomical-alias", canonical_digest=digest({}))
        revision = ContentRevision.objects.create(state=state, sequence=1, base_version=0,
            base_digest=digest({}), payload=payload, payload_digest=digest(payload),
            dependency_digest=digest({}), schema_version=2, status="draft", actor=self.owner)
        state.current_revision, state.version = revision, 1
        state.save(update_fields=("current_revision", "version"))
        inventory = owner_client.get(BASE + "publication/preflight/?domain=brain").json()
        candidate = next(row for row in inventory["results"] if row["resource_id"] == str(state.pk))
        selected = self.post(owner_client, "publication/selections/", {"domain": "brain",
            "entries": [{"kind": state.kind, "resource_id": str(state.pk),
                         "expected_digest": candidate["proposal_digest"]}], "request_key": str(uuid.uuid4())})
        self.assertEqual(selected.status_code, 201, selected.content[:300])
        selection_id = selected.json()["id"]
        session_id = owner_client.session["cms_session_id"]
        writer_admitted, release_writer, reader_connected = Event(), Event(), Event()
        reader_pid = []

        def write_source():
            try:
                with transaction.atomic():
                    lock_brain_curation(connection.alias)
                    changed = SourceReference.objects.select_for_update().get(pk=source.pk)
                    changed.citation = "Synthetic citation after committed writer"
                    changed.save(update_fields=("citation",))
                    writer_admitted.set()
                    if not release_writer.wait(15):
                        raise TimeoutError("Synthetic writer release timed out")
            finally:
                connections.close_all()

        def recheck():
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    reader_pid.append(cursor.fetchone()[0])
                reader_connected.set()
                return verify_selection(self.owner.pk, session_id, selection_id)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(write_source)
            try:
                self.assertTrue(writer_admitted.wait(10))
                reader = pool.submit(recheck)
                self.assertTrue(reader_connected.wait(10))
                observed_lock = False
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and not reader.done():
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", reader_pid)
                        row = cursor.fetchone()
                    if row and row[0] == "Lock":
                        observed_lock = True
                        break
                    time.sleep(0.02)
                self.assertTrue(observed_lock, "PostgreSQL did not observe the source-writer lock wait")
            finally:
                release_writer.set()
            writer.result(timeout=15)
            result = reader.result(timeout=15)
        self.assertFalse(result["all_snapshots_current"])
        self.assertEqual(result["items"][0]["snapshot_state"], "matching")
        self.assertEqual(result["items"][0]["dependency_state"], "stale")
        self.assertFalse(result["approved"])
        self.assertEqual(PublicationCandidateSelection.objects.count(), 1)

    def test_learning_preparation_waits_for_committed_rights_restriction(self):
        from django.utils import timezone
        from .cms_governance import create_governance, mutate_governance, resource_binding
        from .cms_models import AdminSession
        from .cms_policy import CMSFailure
        from .cms_publication_preparation import prepare_selection, verify_preparation
        from .cms_publication_preparation_models import PublicationPreparationDossier
        from .models import Category, Disorder, Quiz, QuizChoice, QuizQuestion

        owner_client = self.sign_in(self.owner)
        editor = self.user("p16-race-rights-editor", staff=True,
                           caps=("cms_enter", "cms_core_view", "cms_core_edit"))
        self.sign_in(editor)
        owner_session = AdminSession.objects.get(user=self.owner).pk
        editor_session = AdminSession.objects.get(user=editor).pk
        category = Category.objects.create(slug="p16-rights-race", name_en="Synthetic")
        disorder = Disorder.objects.create(category=category, slug="p16-rights-race",
                                            name_en="Synthetic", is_active=True)
        quiz = Quiz.objects.create(slug="p16-rights-race", title="Synthetic",
                                   disorder=disorder, is_active=False, seed_managed=False)
        question = QuizQuestion.objects.create(quiz=quiz, prompt="Synthetic question")
        QuizChoice.objects.create(question=question, text="Yes", is_correct=True)
        QuizChoice.objects.create(question=question, text="No", is_correct=False)
        source = SourceReference.objects.create(title="Synthetic race source",
            citation="Synthetic fixture", url="https://example.org/race",
            verification_status="source_checked")
        inventory = owner_client.get(BASE + "publication/preflight/?domain=learning")
        self.assertEqual(inventory.status_code, 200)
        candidate = next(row for row in inventory.json()["results"]
                         if row["kind"] == "quiz" and row["resource_id"] == quiz.pk)
        response = self.post(owner_client, "publication/selections/", {
            "domain": "learning", "request_key": str(uuid.uuid4()),
            "entries": [{"kind": "quiz", "resource_id": quiz.pk,
                         "expected_digest": candidate["content_digest"]}],
        })
        self.assertEqual(response.status_code, 201, response.content[:300])
        selected = response.json()
        initial, created = prepare_selection(self.owner.pk, owner_session, selected["id"], {
            "request_key": str(uuid.uuid4()), "selection_digest": selected["selection_digest"],
        }, str(uuid.uuid4()))
        self.assertTrue(created)
        self.assertTrue(verify_preparation(self.owner.pk, owner_session, initial.pk)["snapshot_current"])

        writer_admitted, release_writer, reader_connected = Event(), Event(), Event()
        reader_pid = []

        def restrict_rights():
            try:
                with transaction.atomic():
                    evidence = [{"source_id": source.pk, "locator": "Synthetic race"}]
                    record = create_governance(editor.pk, editor_session, "rights", {
                        "resource_type": "disorder", "resource_id": disorder.pk,
                        "resource_version": resource_binding("disorder", disorder.pk)["resource_version"],
                        "material": "metadata", "intended_use": "public_display", "status": "restricted",
                        "rightsholder": "Synthetic holder", "holder_identification": "Synthetic evidence",
                        "holder_evidence": evidence, "evidence": evidence, "public_access": "public",
                        "reviewed_on": timezone.localdate().isoformat(),
                        "effective_on": timezone.localdate().isoformat(), "expires_on": None,
                        "review_on": None, "limitations": "Synthetic scope", "territory": "",
                        "conflict_note": "", "reason": "CORRECTION_REQUIRED",
                    }, str(uuid.uuid4()))
                    record = mutate_governance(self.owner.pk, owner_session, "rights", record.pk,
                        record.version, "assign", {"reviewer_id": self.owner.pk}, str(uuid.uuid4()))
                    mutate_governance(self.owner.pk, owner_session, "rights", record.pk, record.version,
                        "decide", {"outcome": "approve", "reason": "RIGHTS_SCOPE_VERIFIED",
                                   "self_review_ack": False}, str(uuid.uuid4()))
                    writer_admitted.set()
                    if not release_writer.wait(15):
                        raise TimeoutError("Synthetic rights writer release timed out")
            finally:
                connections.close_all()

        def prepare_after_writer():
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    reader_pid.append(cursor.fetchone()[0])
                reader_connected.set()
                try:
                    prepare_selection(self.owner.pk, owner_session, selected["id"], {
                        "request_key": str(uuid.uuid4()),
                        "selection_digest": selected["selection_digest"],
                    }, str(uuid.uuid4()))
                except CMSFailure as exc:
                    return str(exc.detail.get("code", ""))
                return "UNEXPECTED_PREPARATION"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(restrict_rights)
            try:
                self.assertTrue(writer_admitted.wait(10))
                reader = pool.submit(prepare_after_writer)
                self.assertTrue(reader_connected.wait(10))
                observed_lock = False
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and not reader.done():
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", reader_pid)
                        row = cursor.fetchone()
                    if row and row[0] == "Lock":
                        observed_lock = True
                        break
                    time.sleep(0.02)
                self.assertTrue(observed_lock, "PostgreSQL did not observe the rights-writer lock wait")
            finally:
                release_writer.set()
            writer.result(timeout=15)
            self.assertEqual(reader.result(timeout=15), "PREPARATION_NOT_CURRENT")
        self.assertEqual(PublicationPreparationDossier.objects.count(), 1)
        self.assertFalse(verify_preparation(self.owner.pk, owner_session, initial.pk)["snapshot_current"])
