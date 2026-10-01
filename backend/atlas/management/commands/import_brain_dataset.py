from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from atlas.brain_staging import ingest_brain_document, validate_brain_staging


class Command(BaseCommand):
    help = "Archive explicit Brain JSON losslessly and validate staging only. Never promotes public content."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Explicit brain-staging-v1 JSON path; no default source file.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["path"]).expanduser().resolve()
        try:
            raw_text = path.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise CommandError(f"Cannot read Brain input: {error}") from error
        with transaction.atomic():
            dataset, created = ingest_brain_document(raw_text, path.name)
            report = validate_brain_staging(dataset.key)
            if options["dry_run"]:
                transaction.set_rollback(True)
        self.stdout.write(f"Brain staging {'DRY RUN' if options['dry_run'] else 'ARCHIVED'}: {dataset.key}; created={created}")
        self.stdout.write(f"candidates={report['candidate_count']} issues={len(report['issues'])} canonical_writes=0")
        self.stdout.write("Publication BLOCKED: approved curated dossier required.")
        for row in report["issues"]:
            self.stdout.write(f"  {row['record']}: {row['code']}")
