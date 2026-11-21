"""Read-only CI/operator gate: always block until true release evidence exists.

No --force, --approve or release side effects. JSON is written to stdout
before nonzero exit, even when the migration history is behind. Never emit
secrets, database paths, actor data, private content or user credentials.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.utils import timezone

from atlas import cms_release_readiness as readiness


class Command(BaseCommand):
    help = "Emit fail-closed local release evidence as JSON, exit nonzero while approval is absent."

    def handle(self, *args, **options):
        report = {
            "scope": "local_release_blocker_evidence_not_deployment",
            "release_ready": False,
            "public_apply_authorized": False,
            "production_release_gate_passed": False,
            "hard_blockers": list(readiness._PENDING_EXTERNAL_GATES),
            "manual_decision_required": True,
            "database": {
                "vendor": "unknown",
                "pending_atlas_migrations": None,
                "unknown_atlas_migrations": None,
                "migration_history_matches_files": False,
                "schema_integrity_proven": False,
            },
            "worker": {
                "alive_confirmed": False,
                "poll_recently_observed": False,
                "successful_polls_recorded": None,
            },
            "backup": {"real_adapter_verified": False, "state": "unavailable"},
            "preparation": {"recorded_dossiers": None, "publication_approved_dossiers": 0},
            "notice": "LOCAL_EVIDENCE_ONLY_NO_APPROVAL_OR_PRODUCTION_DEPLOY",
        }
        try:
            migration = readiness.atlas_migration_evidence()
            report["database"] = migration
            if not migration["migration_history_matches_files"]:
                report["hard_blockers"].append("atlas_migration_history_not_current")
            else:
                # Migration records alone do not prove physical tables exist.
                # Do not access any CMS models if a critical table is missing.
                tables = readiness.atlas_runtime_table_evidence()
                report["database"].update(tables)
                if not tables["runtime_tables_present"]:
                    report["hard_blockers"].append("atlas_runtime_tables_missing")
                elif not tables["runtime_columns_present"]:
                    report["hard_blockers"].append("atlas_runtime_columns_missing")
                elif not tables["runtime_idempotency_uniques_present"]:
                    report["hard_blockers"].append("atlas_runtime_idempotency_constraints_missing")
                elif not tables["runtime_foreign_keys_present"]:
                    report["hard_blockers"].append("atlas_runtime_foreign_keys_missing")
                else:
                    from atlas.cms_worker_pulse import observation
                    from atlas.cms_publication_preparation_models import PublicationPreparationDossier
                    report["worker"] = observation(timezone.now())
                    report["preparation"]["recorded_dossiers"] = (
                        PublicationPreparationDossier.objects.count()
                    )
        except DatabaseError:
            # Never pass through an OperationalError string, DSN, or path.
            report["hard_blockers"].append("database_observation_unavailable")
            report["database"]["migration_history_matches_files"] = False
        self.stdout.write(json.dumps(report, ensure_ascii=True, sort_keys=True))
        raise CommandError("RELEASE_BLOCKED")
