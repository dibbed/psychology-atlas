"""P21 disposable upgrade rehearsal; never a production restore or approval."""
import uuid

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from .cms_release_readiness import atlas_migration_evidence, atlas_runtime_table_evidence


class RecentMigrationUpgradeTests(TransactionTestCase):
    def test_upgrade_preserves_existing_selection_and_creates_runtime_tables(self):
        previous = ("atlas", "0054_v100_p16_review_selections")
        targets = MigrationExecutor(connection).loader.graph.leaf_nodes("atlas")
        self.assertEqual(len(targets), 1)
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([previous])
            old_apps = executor.loader.project_state([previous]).apps
            User = old_apps.get_model("auth", "User")
            Selection = old_apps.get_model("atlas", "PublicationCandidateSelection")
            owner = User.objects.create(username="p21-synthetic-upgrade-owner")
            selection = Selection.objects.create(
                domain="learning", request_key=uuid.uuid4(), request_digest="a" * 64,
                selection={"items": [{"kind": "quiz", "resource_id": 42}]},
                selection_digest="b" * 64, policy_version=3,
                actor=owner, actor_ref="c" * 64,
            )
            old_values = Selection.objects.filter(pk=selection.pk).values(
                "id", "domain", "request_key", "request_digest", "selection", "selection_digest",
                "policy_version", "actor_id", "actor_ref", "created_at").get()
            before_tables = set(connection.introspection.table_names())
            self.assertNotIn("atlas_publicationpreparationdossier", before_tables)
            self.assertNotIn("atlas_cmsworkerpulse", before_tables)

            executor = MigrationExecutor(connection)
            executor.migrate(targets)
            new_apps = executor.loader.project_state(targets).apps
            NewSelection = new_apps.get_model("atlas", "PublicationCandidateSelection")
            Dossier = new_apps.get_model("atlas", "PublicationPreparationDossier")
            Pulse = new_apps.get_model("atlas", "CmsWorkerPulse")
            self.assertEqual(NewSelection.objects.filter(pk=selection.pk).values(*old_values.keys()).get(),
                             old_values)
            dossier = Dossier.objects.create(
                selection_id=selection.pk, request_key=uuid.uuid4(),
                selection_digest=selection.selection_digest, dossier={"fixture": "synthetic"},
                dossier_digest="d" * 64, actor_id=owner.pk, actor_ref="c" * 64,
            )
            Pulse.objects.create(pk=1, last_successful_poll_at=timezone.now(), successful_polls=1)
            self.assertEqual(Dossier.objects.get(pk=dossier.pk).selection_id, selection.pk)
            self.assertEqual(Pulse.objects.get(pk=1).successful_polls, 1)
            self.assertTrue(atlas_migration_evidence()["migration_history_matches_files"])
            schema = atlas_runtime_table_evidence()
            for field in ("runtime_tables_present", "runtime_columns_present",
                          "runtime_idempotency_uniques_present", "runtime_foreign_keys_present"):
                self.assertTrue(schema[field], field)
        finally:
            # Keep the isolated Django test database at the current schema even
            # if an assertion or the forward migration fails.
            MigrationExecutor(connection).migrate(targets)
