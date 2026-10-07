import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from atlas.assessment_publication import ingest_document, validate_staging


class Command(BaseCommand):
    help = "Archive safe Assessment metadata losslessly; never publish generic research mentions."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        path = Path(options["path"])
        with transaction.atomic():
            dataset, created = ingest_document(path.read_text(encoding="utf-8"), path.name)
            result = validate_staging(dataset)
            result.update(archive_created=created, dry_run=options["dry_run"])
            if options["dry_run"]:
                transaction.set_rollback(True)
            self.stdout.write(json.dumps(result, sort_keys=True))
