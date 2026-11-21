"""W13: real two-connection evidence writes; PostgreSQL rejects one stale writer.

SQLite cannot serialize concurrent writers using SELECT FOR UPDATE; its sequential
ETag/replay policy is covered by tests_v100_w13_evidence. This test uses two
independent Django connections and real MFA/CSRF admin clients on PostgreSQL.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase, override_settings

from .cms_learning_evidence_models import LearningEvidenceRevision, LearningEvidenceSource
from .cms_models import AdminAuditEvent
from .models import Flashcard, SourceReference
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class EvidenceConcurrencyTests(SecurityFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.sign_in(self.owner)
        self.card = Flashcard.objects.create(
            slug="synthetic-w13-concurrent", front="Synthetic question",
            back="Synthetic answer", is_active=False, seed_managed=False)
        self.source = SourceReference.objects.create(
            title="NON-SCIENTIFIC concurrent source")
        self.url = BASE + f"learning/evidence/flashcard/{self.card.pk}/"
        self.etag = self.admin.get(self.url)["ETag"]

    def test_two_live_connections_preserve_one_revision_and_audit(self):
        if connection.vendor != "postgresql":
            self.skipTest("SQLite has no row locks; sequential ETag covered separately")
        csrf = self.csrf(self.admin)
        cookies = {key: value.value for key, value in self.admin.cookies.items()}
        barrier = Barrier(2)

        def submit(name):
            close_old_connections()
            client = Client(enforce_csrf_checks=True)
            for key, value in cookies.items():
                client.cookies[key] = value
            barrier.wait(timeout=10)
            try:
                response = client.post(
                    self.url,
                    data=json.dumps({"sources": [{"source_id": self.source.pk,
                                                 "locator": "NON-SCIENTIFIC " + name}]}),
                    content_type="application/json",
                    HTTP_IF_MATCH=self.etag,
                    HTTP_X_CSRFTOKEN=csrf,
                )
                return response.status_code, response.content[:200].decode(errors="replace")
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcome = list(executor.map(submit, ("first", "second")))
        self.assertEqual(sorted(code for code, _ in outcome), [200, 412], outcome)
        self.assertEqual(LearningEvidenceRevision.objects.count(), 1)
        self.assertEqual(LearningEvidenceSource.objects.count(), 1)
        self.assertEqual(AdminAuditEvent.objects.filter(
            action="learning.evidence_revised", target_id=self.card.pk).count(), 1)
        saved = self.admin.get(self.url)
        self.assertEqual(saved.status_code, 200)
        self.assertIn(saved.json()["links"][0]["locator"],
                      {"NON-SCIENTIFIC first", "NON-SCIENTIFIC second"})
