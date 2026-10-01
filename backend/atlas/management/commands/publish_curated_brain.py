import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from atlas.brain_controlled_publication import DOSSIER_SHA, MANIFEST_SHA, encoded, publish


class Command(BaseCommand):
    help = "Dry-run or apply ONLY the pinned, scientifically and rights-approved v0.9.2C Brain selection."

    def add_arguments(self, parser):
        parser.add_argument("--expected-dossier-sha256", required=True)
        parser.add_argument("--expected-manifest-sha256", required=True)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true")
        mode.add_argument("--dry-run", action="store_true")
        parser.add_argument("--resolved-output", type=Path, help="Optional TARGET-SPECIFIC derivative; never a portable master.")

    def handle(self, *args, **options):
        if options["expected_dossier_sha256"] != DOSSIER_SHA or options["expected_manifest_sha256"] != MANIFEST_SHA:
            raise CommandError("The exact approved dossier and manifest hashes must be supplied.")
        output = options["resolved_output"]
        if output and output.exists():
            raise CommandError("Resolved output must be a new path; existing artifacts are preserved.")
        result, derived = publish(dry_run=not options["apply"])
        if output:
            # Dry-run allocations are tentative; only an applied derivative can be reused.
            result["resolution_allocation_status"] = "COMMITTED" if options["apply"] else "TENTATIVE_ROLLED_BACK"
            output.write_bytes(encoded(derived).encode("utf-8"))
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
