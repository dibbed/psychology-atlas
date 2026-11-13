"""P21 owner-only live release blockers, explicitly NOT a release authorization.

This is a read-only operational evidence index for follow-up work. The
absence of detected structural anomalies never substitutes for scientific or
rights review, production backups, CI, or a human release decision.
"""
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from rest_framework.response import Response

from .cms_operations_health import OperationsHealthView
from .cms_policy import CMSFailure, policy_lock, require
from .cms_publication_preparation_models import PublicationPreparationDossier


# Not configurable from HTTP/JSON. Only independent, externally validated
# proofs can close these gates in a separate future release decision process.
_PENDING_EXTERNAL_GATES = (
    "real_scientific_rights_attestation",
    "multidomain_public_apply",
    "retention_legal_hold_approval",
    "live_worker_supervision",
    "representative_backup_restore",
    "production_tls_secrets",
    "hosted_ci_and_full_db_acceptance",
    "explicit_release_authorization",
)


def atlas_migration_evidence():
    """Source-backed registry comparison; not a physical schema verifier."""
    loader = MigrationLoader(connection)
    leaves = loader.graph.leaf_nodes("atlas")
    pending = set()
    for leaf in leaves:
        pending.update(node for node in loader.graph.forwards_plan(leaf)
                       if node[0] == "atlas" and node not in loader.applied_migrations)
    unknown = {node for node in loader.applied_migrations
               if node[0] == "atlas" and node not in loader.disk_migrations}
    return {
        "vendor": connection.vendor,
        "atlas_expected_leaf_count": len(leaves),
        "pending_atlas_migrations": len(pending),
        "unknown_atlas_migrations": len(unknown),
        "migration_history_matches_files": bool(len(leaves) == 1 and not pending and not unknown),
        "schema_integrity_proven": False,
    }


def _unconditional_unique_indexes(cursor, table):
    if connection.vendor == "sqlite":
        cursor.execute(f"PRAGMA index_list({connection.ops.quote_name(table)})")
        return {row[1] for row in cursor.fetchall()
                if len(row) >= 5 and row[2] and not row[4]}
    if connection.vendor == "postgresql":
        cursor.execute("""
            SELECT idx.relname FROM pg_catalog.pg_index AS i
            JOIN pg_catalog.pg_class AS idx ON idx.oid = i.indexrelid
            WHERE i.indrelid = pg_catalog.to_regclass(%s)
              AND i.indisunique AND i.indisvalid AND i.indisready AND i.indimmediate
              AND i.indpred IS NULL AND i.indexprs IS NULL
        """, [table])
        return {row[0] for row in cursor.fetchall()}
    return set()


def atlas_runtime_table_evidence():
    """Check essential runtime tables, not a complete DB schema or release proof.

    This check intentionally runs only after the migration recorder matches
    the code. It catches a restored or manually damaged DB whose recorder
    claims migrations were applied but critical CMS relations are absent.
    """
    from .cms_content_models import ContentState
    from .cms_job_models import AdminJob
    from .cms_models import AdminAuditEvent
    from .cms_publication_selection_models import PublicationCandidateSelection
    from .cms_worker_pulse import CmsWorkerPulse

    models = (ContentState, AdminJob, AdminAuditEvent,
              PublicationCandidateSelection, PublicationPreparationDossier,
              CmsWorkerPulse)
    expected = {model._meta.db_table for model in models}
    existing = set(connection.introspection.table_names())
    # A matching migration recorder and table name can hide a damaged restore
    # with missing critical columns. Inspect the concrete ORM column set
    # without exposing identifiers, values, SQL or private data in the result.
    # These UNIQUE keys are part of the durable retry/idempotency boundary.
    # An old or damaged schema can report every expected migration as applied
    # while silently accepting duplicated requests.
    unique_keys = {
        AdminJob: (("actor_ref", "request_key"),),
        PublicationCandidateSelection: (("request_key",),),
        PublicationPreparationDossier: (("request_key",),),
    }
    column_count = missing_columns = missing_uniques = 0
    required_foreign_keys = missing_foreign_keys = 0
    with connection.cursor() as cursor:
        for model in models:
            fields = model._meta.concrete_fields
            required = {field.column for field in fields}
            column_count += len(required)
            must_be_unique = unique_keys.get(model, ())
            # Check the physical FK definition, not just the presence of its
            # local *_id column. Only db-enforced ORM relations are expected.
            foreign_keys = {
                (field.column, (field.target_field.model._meta.db_table,
                                field.target_field.column))
                for field in fields
                if field.is_relation and (field.many_to_one or field.one_to_one)
                and field.db_constraint
            }
            required_foreign_keys += len(foreign_keys)
            if model._meta.db_table not in existing:
                missing_columns += len(required)
                missing_uniques += len(must_be_unique)
                missing_foreign_keys += len(foreign_keys)
                continue
            actual = {column.name for column in connection.introspection.get_table_description(
                cursor, model._meta.db_table)}
            missing_columns += len(required - actual)
            if must_be_unique or foreign_keys:
                constraints = connection.introspection.get_constraints(cursor, model._meta.db_table)
                unique_indexes = (_unconditional_unique_indexes(cursor, model._meta.db_table)
                                  if must_be_unique else set())
                available_uniques = {frozenset(info.get("columns") or ())
                                     for name, info in constraints.items()
                                     if info.get("unique") and (
                                         name in unique_indexes or
                                         (connection.vendor == "sqlite" and not info.get("index")))}
                missing_uniques += sum(frozenset(key) not in available_uniques
                                       for key in must_be_unique)
                available_foreign_keys = {
                    (columns[0], tuple(info["foreign_key"]))
                    for info in constraints.values() if info.get("foreign_key")
                    for columns in [info.get("columns") or ()]
                    if len(columns) == 1
                }
                missing_foreign_keys += len(foreign_keys - available_foreign_keys)
    return {
        "required_runtime_table_count": len(expected),
        "missing_runtime_table_count": len(expected - existing),
        "runtime_tables_present": expected <= existing,
        "required_runtime_column_count": column_count,
        "missing_runtime_column_count": missing_columns,
        "runtime_columns_present": missing_columns == 0,
        "required_runtime_idempotency_unique_count": sum(
            len(keys) for keys in unique_keys.values()),
        "missing_runtime_idempotency_unique_count": missing_uniques,
        "runtime_idempotency_uniques_present": missing_uniques == 0,
        "required_runtime_foreign_key_count": required_foreign_keys,
        "missing_runtime_foreign_key_count": missing_foreign_keys,
        "runtime_foreign_keys_present": missing_foreign_keys == 0,
        # Metadata only: neither orphan-free rows nor FK enforcement flags
        # during live sessions are proven by introspection.
        # No data, type, other index/constraint or live-traffic proof is implied.
        "schema_integrity_proven": False,
    }


class ReleaseReadinessView(OperationsHealthView):
    """Live, owner-scoped, fixed-shape GET; no mutation or secrets."""

    def get(self, request):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        # Check the migration recorder before querying models introduced by
        # those migrations. A behind-schema deployment must fail closed,
        # without pretending to run a health audit against absent tables.
        with policy_lock():
            require(request.user, "cms_owner")
            migration = atlas_migration_evidence()
            history_matches = migration["migration_history_matches_files"]
            if not history_matches:
                return Response({
                    "code": "ATLAS_MIGRATIONS_PENDING",
                    "release_ready": False, "public_apply_authorized": False,
                    "database": migration,
                    "hard_blockers": [*_PENDING_EXTERNAL_GATES,
                                      "atlas_migration_history_not_current"],
                    "manual_decision_required": True,
                    "notice": "MIGRATION_HISTORY_GATE_BLOCKED_NO_MODEL_INSPECTION",
                }, status=503)
            tables = atlas_runtime_table_evidence()
            migration.update(tables)
            if not tables["runtime_tables_present"]:
                return Response({
                    "code": "ATLAS_RUNTIME_TABLES_MISSING",
                    "release_ready": False, "public_apply_authorized": False,
                    "database": migration,
                    "hard_blockers": [*_PENDING_EXTERNAL_GATES,
                                      "atlas_runtime_tables_missing"],
                    "manual_decision_required": True,
                    "notice": "RUNTIME_TABLE_GATE_BLOCKED_NO_MODEL_INSPECTION",
                }, status=503)
            if not tables["runtime_columns_present"]:
                return Response({
                    "code": "ATLAS_RUNTIME_COLUMNS_MISSING",
                    "release_ready": False, "public_apply_authorized": False,
                    "database": migration,
                    "hard_blockers": [*_PENDING_EXTERNAL_GATES,
                                      "atlas_runtime_columns_missing"],
                    "manual_decision_required": True,
                    "notice": "RUNTIME_COLUMN_GATE_BLOCKED_NO_MODEL_INSPECTION",
                }, status=503)
            if not tables["runtime_idempotency_uniques_present"]:
                return Response({
                    "code": "ATLAS_RUNTIME_UNIQUES_MISSING",
                    "release_ready": False, "public_apply_authorized": False,
                    "database": migration,
                    "hard_blockers": [*_PENDING_EXTERNAL_GATES,
                                      "atlas_runtime_idempotency_constraints_missing"],
                    "manual_decision_required": True,
                    "notice": "RUNTIME_IDEMPOTENCY_GATE_BLOCKED_NO_MODEL_INSPECTION",
                }, status=503)
            if not tables["runtime_foreign_keys_present"]:
                return Response({
                    "code": "ATLAS_RUNTIME_FOREIGN_KEYS_MISSING",
                    "release_ready": False, "public_apply_authorized": False,
                    "database": migration,
                    "hard_blockers": [*_PENDING_EXTERNAL_GATES,
                                      "atlas_runtime_foreign_keys_missing"],
                    "manual_decision_required": True,
                    "notice": "RUNTIME_FOREIGN_KEY_GATE_BLOCKED_NO_MODEL_INSPECTION",
                }, status=503)
        # Inherited owner checks and receipt/queue queries are now safe to
        # attempt after the migration-history gate. Schema integrity is still
        # not proven solely by migration records.
        observed = super().get(request).data
        with policy_lock():
            require(request.user, "cms_owner")
            dossiers = PublicationPreparationDossier.objects.count()

        drift = {
            "case_receipt_mismatches": observed["publication_receipts"]["total_observed_mismatches"],
            "source_receipt_mismatches": observed["source_plan_receipts"]["total_observed_mismatches"],
            "source_receipt_sample_complete": observed["source_plan_receipts"]["sample_complete"],
        }
        blockers = list(_PENDING_EXTERNAL_GATES)
        if not history_matches:
            blockers.append("atlas_migration_history_not_current")
        if drift["case_receipt_mismatches"] or drift["source_receipt_mismatches"]:
            blockers.append("observed_receipt_inconsistencies")
        if not drift["source_receipt_sample_complete"]:
            blockers.append("source_receipt_audit_sample_incomplete")

        return Response({
            "scope": "owner_only_operational_release_gate_observations",
            "as_of": observed["as_of"],
            "release_ready": False,
            "public_apply_authorized": False,
            "database": {
                "vendor": observed["database"]["vendor"],
                "connection": observed["database"]["connection"],
                "atlas_applied_migrations": observed["database"]["atlas_applied_migrations"],
                **migration,
            },
            "worker": observed["worker"],
            "jobs": {
                "ready_count": observed["jobs"]["queued_ready_count"],
                "scheduled_future_count": observed["jobs"]["queued_scheduled_count"],
                "expired_lease_count": observed["jobs"]["running_expired_lease_count"],
                "missing_lease_count": observed["jobs"]["running_missing_lease_count"],
            },
            "preparation": {
                "recorded_dossiers": dossiers,
                "publication_approved_dossiers": 0,
                "attestations_proven": False,
                "scope": "private_review_handoff_only_not_a_frozen_publication_manifest",
            },
            "receipt_observations": drift,
            "backup": observed["backup"],
            "hard_blockers": blockers,
            "manual_decision_required": True,
            "notice": "READ_ONLY_LOCAL_OBSERVATIONS_NOT_PRODUCTION_RELEASE_AUTHORIZATION",
        })
