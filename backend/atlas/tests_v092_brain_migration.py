from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class BrainRelationMigrationTests(TransactionTestCase):
    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_v091_upgrade_and_reverse_preserve_foundation_and_legacy_data(self):
        previous = ("atlas", "0033_v091_brain_foundation")
        current = ("atlas", "0034_v092_brain_relation_support")
        executor = MigrationExecutor(connection)
        executor.migrate([previous])
        apps = executor.loader.project_state([previous]).apps
        entity = apps.get_model("atlas", "BrainAnatomicalEntity").objects.create(
            slug="migration-test", name_en="Synthetic Migration", kind="structure", laterality="bilateral")
        source = apps.get_model("atlas", "SourceReference").objects.create(title="Synthetic migration reference")
        apps.get_model("atlas", "BrainAnatomicalEntitySource").objects.create(entity_id=entity.pk, source_id=source.pk)
        with connection.cursor() as cursor:
            tables = sorted(t for t in connection.introspection.table_names(cursor) if t.startswith("atlas_"))
            before = {}
            for table in tables:
                cursor.execute(f'SELECT * FROM "{table}"')
                before[table] = sorted(cursor.fetchall(), key=repr)
        for target in (current, previous):
            MigrationExecutor(connection).migrate([target])
            with connection.cursor() as cursor:
                for table, rows in before.items():
                    cursor.execute(f'SELECT * FROM "{table}"')
                    self.assertEqual(sorted(cursor.fetchall(), key=repr), rows, table)
