"""P21 read-only release gates distinguish local evidence from human/production approval."""
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings

from .cms_content import digest
from .cms_content_models import ContentState
from .cms_worker_pulse import record_successful_poll
from .tests_v100_p01 import BASE, SecurityFixture


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OwnerReleaseReadinessTests(SecurityFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.owner_client = self.sign_in(self.owner)

    def test_recorded_migrations_with_missing_runtime_table_block_http_and_cli(self):
        import io
        import json
        from unittest.mock import patch
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from .cms_release_readiness import atlas_runtime_table_evidence

        real = atlas_runtime_table_evidence()
        self.assertTrue(real["runtime_tables_present"])
        self.assertGreaterEqual(real["required_runtime_table_count"], 6)
        from django.db import connection
        with patch.object(connection.introspection, "table_names", return_value=[]):
            absent = atlas_runtime_table_evidence()
        self.assertFalse(absent["runtime_tables_present"])
        self.assertEqual(absent["missing_runtime_table_count"],
                         real["required_runtime_table_count"])
        missing = {**real, "runtime_tables_present": False,
                   "missing_runtime_table_count": 1}
        with patch("atlas.cms_release_readiness.atlas_runtime_table_evidence",
                   return_value=missing):
            response = self.owner_client.get(BASE + "operations/release-readiness/")
            self.assertEqual(response.status_code, 503, response.content[:400])
            self.assertEqual(response.json()["code"], "ATLAS_RUNTIME_TABLES_MISSING")
            self.assertTrue(response.json()["database"]["migration_history_matches_files"])
            self.assertFalse(response.json()["public_apply_authorized"])
            self.assertIn("atlas_runtime_tables_missing", response.json()["hard_blockers"])
            report = io.StringIO()
            with self.assertRaises(CommandError):
                call_command("cms_release_gate", stdout=report, stderr=io.StringIO())
            parsed = json.loads(report.getvalue())
            self.assertIn("atlas_runtime_tables_missing", parsed["hard_blockers"])
            self.assertIsNone(parsed["preparation"]["recorded_dossiers"])
            self.assertFalse(parsed["public_apply_authorized"])

    def test_missing_essential_column_fails_closed_even_with_applied_migrations(self):
        """P21 must inspect columns as well as table names on the disposable DB."""
        import io
        import json
        from unittest.mock import patch
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from django.db import connection
        from .cms_release_readiness import atlas_runtime_table_evidence

        clean = atlas_runtime_table_evidence()
        self.assertTrue(clean["runtime_columns_present"])
        self.assertGreater(clean["required_runtime_column_count"], 10)
        original = connection.introspection.get_table_description
        table_name = ContentState._meta.db_table

        def omit_column(cursor, name):
            columns = original(cursor, name)
            if name == table_name:
                return [col for col in columns if col.name != "canonical_digest"]
            return columns

        with patch.object(connection.introspection, "get_table_description",
                          side_effect=omit_column):
            broken = atlas_runtime_table_evidence()
            self.assertTrue(broken["runtime_tables_present"])
            self.assertFalse(broken["runtime_columns_present"])
            self.assertEqual(broken["missing_runtime_column_count"], 1)
            response = self.owner_client.get(BASE + "operations/release-readiness/")
            self.assertEqual(response.status_code, 503, response.content[:350])
            data = response.json()
            self.assertEqual(data["code"], "ATLAS_RUNTIME_COLUMNS_MISSING")
            self.assertIn("atlas_runtime_columns_missing", data["hard_blockers"])
            self.assertFalse(data["public_apply_authorized"])
            stream = io.StringIO()
            with self.assertRaises(CommandError):
                call_command("cms_release_gate", stdout=stream, stderr=io.StringIO())
            report = json.loads(stream.getvalue())
            self.assertIn("atlas_runtime_columns_missing", report["hard_blockers"])
            self.assertIsNone(report["preparation"]["recorded_dossiers"])
            self.assertFalse(report["release_ready"])

    def test_missing_idempotency_unique_key_blocks_readiness_and_cli(self):
        """Migration history and columns can match while idempotency is unsafe."""
        import io
        import json
        from unittest.mock import patch
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from django.db import connection
        from .cms_release_readiness import atlas_runtime_table_evidence
        from .cms_publication_preparation_models import PublicationPreparationDossier

        clean = atlas_runtime_table_evidence()
        self.assertTrue(clean["runtime_idempotency_uniques_present"])
        self.assertGreaterEqual(clean["required_runtime_idempotency_unique_count"], 3)
        original = connection.introspection.get_constraints
        target = PublicationPreparationDossier._meta.db_table

        def hide_unique(cursor, table_name):
            constraints = original(cursor, table_name)
            if table_name == target:
                return {
                    name: info for name, info in constraints.items()
                    if not (info.get("unique") and
                            set(info.get("columns") or ()) == {"request_key"})
                }
            return constraints

        with patch.object(connection.introspection, "get_constraints",
                          side_effect=hide_unique):
            broken = atlas_runtime_table_evidence()
            self.assertTrue(broken["runtime_tables_present"])
            self.assertTrue(broken["runtime_columns_present"])
            self.assertFalse(broken["runtime_idempotency_uniques_present"])
            self.assertEqual(broken["missing_runtime_idempotency_unique_count"], 1)
            response = self.owner_client.get(BASE + "operations/release-readiness/")
            self.assertEqual(response.status_code, 503, response.content[:350])
            self.assertEqual(response.json()["code"], "ATLAS_RUNTIME_UNIQUES_MISSING")
            self.assertFalse(response.json()["public_apply_authorized"])
            stream = io.StringIO()
            with self.assertRaises(CommandError):
                call_command("cms_release_gate", stdout=stream, stderr=io.StringIO())
            report = json.loads(stream.getvalue())
            self.assertIn("atlas_runtime_idempotency_constraints_missing",
                          report["hard_blockers"])
            self.assertIsNone(report["preparation"]["recorded_dossiers"])

    def test_partial_unique_index_does_not_satisfy_idempotency_gate(self):
        import io
        import json
        from unittest.mock import patch
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from django.db import connection
        from .cms_publication_preparation_models import PublicationPreparationDossier
        from .cms_release_readiness import atlas_runtime_table_evidence

        target = PublicationPreparationDossier._meta.db_table
        original = connection.introspection.get_constraints
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE qa_partial_unique (request_key varchar(36) NOT NULL)")
            cursor.execute("CREATE UNIQUE INDEX qa_partial_fixture_idx ON qa_partial_unique "
                           "(request_key) WHERE request_key <> '00000000-0000-0000-0000-000000000000'")
            cursor.execute("INSERT INTO qa_partial_unique VALUES "
                           "('00000000-0000-0000-0000-000000000000'), "
                           "('00000000-0000-0000-0000-000000000000')")
            cursor.execute(f'CREATE UNIQUE INDEX qa_partial_gate_idx ON "{target}" '
                           "(request_key) WHERE request_key <> '00000000-0000-0000-0000-000000000000'")
            cursor.execute(f'CREATE UNIQUE INDEX qa_full_gate_idx ON "{target}" (request_key)')

        def only_index(index_name):
            def replace_unique(cursor, table_name):
                constraints = original(cursor, table_name)
                if table_name == target:
                    constraints = {name: info for name, info in constraints.items()
                                   if not (info.get("unique") and
                                           set(info.get("columns") or ()) == {"request_key"})
                                   or name == index_name}
                return constraints
            return replace_unique

        try:
            with patch.object(connection.introspection, "get_constraints",
                              side_effect=only_index("qa_partial_gate_idx")):
                evidence = atlas_runtime_table_evidence()
                self.assertFalse(evidence["runtime_idempotency_uniques_present"])
                self.assertEqual(evidence["missing_runtime_idempotency_unique_count"], 1)
                response = self.owner_client.get(BASE + "operations/release-readiness/")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["code"], "ATLAS_RUNTIME_UNIQUES_MISSING")
                output = io.StringIO()
                with self.assertRaises(CommandError):
                    call_command("cms_release_gate", stdout=output, stderr=io.StringIO())
                self.assertIn("atlas_runtime_idempotency_constraints_missing",
                              json.loads(output.getvalue())["hard_blockers"])
            with patch.object(connection.introspection, "get_constraints",
                              side_effect=only_index("qa_full_gate_idx")):
                self.assertTrue(atlas_runtime_table_evidence()["runtime_idempotency_uniques_present"])
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP INDEX qa_partial_gate_idx")
                cursor.execute("DROP INDEX qa_full_gate_idx")
                cursor.execute("DROP TABLE qa_partial_unique")

    def test_nullable_idempotency_key_does_not_satisfy_uniqueness_gate(self):
        import io
        import json
        from unittest.mock import patch
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from django.db import connection
        from .cms_job_models import AdminJob
        from .cms_publication_preparation_models import PublicationPreparationDossier
        from .cms_publication_selection_models import PublicationCandidateSelection
        from .cms_release_readiness import atlas_runtime_table_evidence

        original = connection.introspection.get_table_description
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE qa_nullable_unique "
                           "(actor_ref varchar(64), request_key varchar(36), UNIQUE(actor_ref, request_key))")
            cursor.execute("INSERT INTO qa_nullable_unique VALUES (NULL, 'same'), (NULL, 'same')")
            cursor.execute("SELECT COUNT(*) FROM qa_nullable_unique WHERE actor_ref IS NULL")
            self.assertEqual(cursor.fetchone()[0], 2)

        try:
            for model, name in ((AdminJob, "actor_ref"), (AdminJob, "request_key"),
                                (PublicationCandidateSelection, "request_key"),
                                (PublicationPreparationDossier, "request_key")):
                with self.subTest(model=model.__name__, column=name):
                    def nullable_key(cursor, table):
                        columns = original(cursor, table)
                        return [column._replace(null_ok=True)
                                if table == model._meta.db_table and column.name == name else column
                                for column in columns]

                    with patch.object(connection.introspection, "get_table_description", side_effect=nullable_key):
                        broken = atlas_runtime_table_evidence()
                        self.assertTrue(broken["runtime_columns_present"])
                        self.assertFalse(broken["runtime_idempotency_uniques_present"])
                        self.assertEqual(broken["missing_runtime_idempotency_unique_count"], 1)
                        response = self.owner_client.get(BASE + "operations/release-readiness/")
                        self.assertEqual(response.status_code, 503)
                        self.assertEqual(response.json()["code"], "ATLAS_RUNTIME_UNIQUES_MISSING")
                        output = io.StringIO()
                        with self.assertRaises(CommandError):
                            call_command("cms_release_gate", stdout=output, stderr=io.StringIO())
                        self.assertIn("atlas_runtime_idempotency_constraints_missing",
                                      json.loads(output.getvalue())["hard_blockers"])
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DROP TABLE qa_nullable_unique")

    def test_missing_essential_foreign_key_blocks_http_and_cli(self):
        """A damaged relation must fail closed despite complete migration records."""
        import io
        import json
        from unittest.mock import patch
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from django.db import connection
        from .cms_release_readiness import atlas_runtime_table_evidence
        from .cms_publication_preparation_models import PublicationPreparationDossier

        clean = atlas_runtime_table_evidence()
        self.assertTrue(clean["runtime_foreign_keys_present"])
        self.assertGreater(clean["required_runtime_foreign_key_count"], 0)
        original = connection.introspection.get_constraints
        target = PublicationPreparationDossier._meta.db_table

        def hide_selection_fk(cursor, table_name):
            constraints = original(cursor, table_name)
            if table_name == target:
                return {
                    name: info for name, info in constraints.items()
                    if not (info.get("foreign_key")
                            and info.get("columns") == ["selection_id"])
                }
            return constraints

        with patch.object(connection.introspection, "get_constraints",
                          side_effect=hide_selection_fk):
            broken = atlas_runtime_table_evidence()
            self.assertTrue(broken["runtime_tables_present"])
            self.assertTrue(broken["runtime_columns_present"])
            self.assertTrue(broken["runtime_idempotency_uniques_present"])
            self.assertFalse(broken["runtime_foreign_keys_present"])
            self.assertEqual(broken["missing_runtime_foreign_key_count"], 1)
            response = self.owner_client.get(BASE + "operations/release-readiness/")
            self.assertEqual(response.status_code, 503, response.content[:350])
            self.assertEqual(response.json()["code"], "ATLAS_RUNTIME_FOREIGN_KEYS_MISSING")
            self.assertFalse(response.json()["public_apply_authorized"])
            self.assertIn("atlas_runtime_foreign_keys_missing",
                          response.json()["hard_blockers"])
            stream = io.StringIO()
            with self.assertRaises(CommandError):
                call_command("cms_release_gate", stdout=stream, stderr=io.StringIO())
            report = json.loads(stream.getvalue())
            self.assertIn("atlas_runtime_foreign_keys_missing", report["hard_blockers"])
            self.assertIsNone(report["preparation"]["recorded_dossiers"])
            self.assertFalse(report["release_ready"])

    def test_wrong_foreign_key_target_is_missing_essential_relation(self):
        """A similarly named FK pointing at the wrong table cannot pass."""
        from unittest.mock import patch
        from django.db import connection
        from .cms_release_readiness import atlas_runtime_table_evidence
        from .cms_publication_preparation_models import PublicationPreparationDossier

        target = PublicationPreparationDossier._meta.db_table
        original = connection.introspection.get_constraints

        def retarget_selection_fk(cursor, table_name):
            constraints = original(cursor, table_name)
            if table_name != target:
                return constraints
            return {
                name: {**info, "foreign_key": ("auth_user", "id")}
                if info.get("foreign_key") and info.get("columns") == ["selection_id"]
                else info for name, info in constraints.items()
            }

        with patch.object(connection.introspection, "get_constraints",
                          side_effect=retarget_selection_fk):
            result = atlas_runtime_table_evidence()
            self.assertFalse(result["runtime_foreign_keys_present"])
            self.assertEqual(result["missing_runtime_foreign_key_count"], 1)
            self.assertEqual(
                self.owner_client.get(
                    BASE + "operations/release-readiness/").status_code, 503)

    def test_release_readiness_is_consistent_redacted_and_never_claims_prod_approval(self):
        private = ContentState.objects.create(kind="brain-anatomical-entity",
                                              canonical_digest=digest({}))
        before = self.owner_client.get(BASE + "operations/release-readiness/")
        self.assertEqual(before.status_code, 200, before.content[:600])
        data = before.json()
        self.assertEqual(data["scope"], "owner_only_operational_release_gate_observations")
        self.assertFalse(data["release_ready"])
        self.assertFalse(data["public_apply_authorized"])
        self.assertIn(data["database"]["vendor"], ("sqlite", "postgresql"))
        self.assertEqual(data["database"]["pending_atlas_migrations"], 0)
        self.assertTrue(data["database"]["migration_history_matches_files"])
        self.assertFalse(data["database"]["schema_integrity_proven"])
        self.assertEqual(data["preparation"]["recorded_dossiers"], 0)
        self.assertEqual(data["preparation"]["publication_approved_dossiers"], 0)
        self.assertEqual(data["worker"]["successful_polls_recorded"], 0)
        self.assertFalse(data["worker"]["alive_confirmed"])
        self.assertFalse(data["worker"]["poll_recently_observed"])
        self.assertEqual(data["backup"]["state"], "unavailable")
        for gate in ("real_scientific_rights_attestation", "multidomain_public_apply",
                     "retention_legal_hold_approval", "live_worker_supervision",
                     "representative_backup_restore", "production_tls_secrets",
                     "hosted_ci_and_full_db_acceptance", "explicit_release_authorization"):
            self.assertIn(gate, data["hard_blockers"])
        self.assertNotIn("username", before.content.decode().lower())
        self.assertNotIn("email", before.content.decode().lower())
        self.assertFalse(ContentState.objects.get(pk=private.pk).publication == "published")

        record_successful_poll()
        after = self.owner_client.get(BASE + "operations/release-readiness/")
        self.assertEqual(after.status_code, 200, after.content[:300])
        self.assertTrue(after.json()["worker"]["poll_recently_observed"])
        self.assertFalse(after.json()["worker"]["alive_confirmed"])
        self.assertFalse(after.json()["release_ready"])

    def test_missing_database_migration_fails_closed_before_new_model_queries(self):
        from django.db.migrations.recorder import MigrationRecorder

        # Only test DB migration metadata is modified; never touch canonical.
        self.assertEqual(MigrationRecorder.Migration.objects.filter(
            app="atlas", name="0056_v100_p18_worker_poll_observation").count(), 1)
        MigrationRecorder.Migration.objects.filter(
            app="atlas", name="0056_v100_p18_worker_poll_observation").delete()
        response = self.owner_client.get(BASE + "operations/release-readiness/")
        self.assertEqual(response.status_code, 503, response.content[:450])
        data = response.json()
        self.assertFalse(data["release_ready"])
        self.assertEqual(data["code"], "ATLAS_MIGRATIONS_PENDING")
        self.assertGreaterEqual(data["database"]["pending_atlas_migrations"], 1)
        self.assertFalse(data["public_apply_authorized"])

    def test_cli_release_gate_emits_redacted_machine_readable_blocked_result(self):
        import io
        import json
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from .cms_worker_pulse import CmsWorkerPulse

        report = io.StringIO()
        with self.assertRaises(CommandError):
            call_command("cms_release_gate", stdout=report, stderr=io.StringIO())
        data = json.loads(report.getvalue())
        self.assertFalse(data["release_ready"])
        self.assertFalse(data["public_apply_authorized"])
        self.assertEqual(data["scope"], "local_release_blocker_evidence_not_deployment")
        self.assertEqual(data["database"]["pending_atlas_migrations"], 0)
        self.assertTrue(data["database"]["migration_history_matches_files"])
        self.assertFalse(data["database"]["schema_integrity_proven"])
        self.assertIn("real_scientific_rights_attestation", data["hard_blockers"])
        self.assertIn("representative_backup_restore", data["hard_blockers"])
        self.assertFalse(data["backup"]["real_adapter_verified"])
        self.assertFalse(data["worker"]["alive_confirmed"])
        self.assertFalse(data["production_release_gate_passed"])
        for secret in ("SECRET_KEY", "DATABASE_URL", "password", "actor_ref",
                       "storage_key", "sqlite3", "dsn"):
            self.assertNotIn(secret, report.getvalue())
        self.assertFalse(CmsWorkerPulse.objects.exists())

    def test_cli_release_gate_blocks_missing_migration_history_without_new_table_queries(self):
        import io
        import json
        from django.core.management import call_command
        from django.core.management.base import CommandError
        from django.db.migrations.recorder import MigrationRecorder

        MigrationRecorder.Migration.objects.filter(
            app="atlas", name="0056_v100_p18_worker_poll_observation").delete()
        stream = io.StringIO()
        with self.assertRaises(CommandError):
            call_command("cms_release_gate", stdout=stream, stderr=io.StringIO())
        report = json.loads(stream.getvalue())
        self.assertFalse(report["release_ready"])
        self.assertGreater(report["database"]["pending_atlas_migrations"], 0)
        self.assertFalse(report["database"]["migration_history_matches_files"])
        self.assertIn("atlas_migration_history_not_current", report["hard_blockers"])
        self.assertFalse(report["public_apply_authorized"])

    def test_readiness_is_owner_only_query_closed_and_nonmutating(self):
        non_owner = self.user("p21-readiness-denied", staff=True,
                              caps=("cms_enter", "cms_dashboard"))
        denied = self.sign_in(non_owner)
        target = BASE + "operations/release-readiness/"
        self.assertEqual(denied.get(target).status_code, 403)
        self.assertEqual(self.owner_client.get(target + "?force=true").status_code, 400)
        self.assertEqual(self.post(self.owner_client, "operations/release-readiness/",
                                  {"release": True}).status_code, 405)
        self.assertEqual(self.owner_client.get(target).status_code, 200)
        perm = Permission.objects.get(codename="cms_owner",
                                      content_type__model="rolepolicy")
        perm.user_set.remove(self.owner)
        self.assertEqual(self.owner_client.get(target).status_code, 403)
