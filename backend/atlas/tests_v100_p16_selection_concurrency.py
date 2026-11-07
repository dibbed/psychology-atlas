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
