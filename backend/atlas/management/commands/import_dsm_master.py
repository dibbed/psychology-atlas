from pathlib import Path

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from atlas.dsm_import import import_master_json


DEFAULT_RELATIVE_PATH = Path(
    "..",
    "DSM5TR_MASTER_2026-08-29_bundle",
    "DSM5TR_فارسی_MASTER_آموزشی_ممیزی‌شده_2026-08-29.json",
)


class Command(BaseCommand):
    help = "Import the audited DSM-5-TR Persian MASTER JSON into the normalized DSM reference layer."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default=str(DEFAULT_RELATIVE_PATH),
            help="Path to the MASTER JSON file. Defaults to the project bundle.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and execute the import inside a rolled-back transaction.",
        )

    def handle(self, *args, **options):
        json_path = Path(options["path"]).expanduser().resolve()
        if not json_path.exists():
            raise CommandError(f"MASTER JSON not found: {json_path}")

        try:
            result = import_master_json(json_path, dry_run=options["dry_run"])
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc

        if not options["dry_run"]:
            cache.delete("atlas_graph_v4")

        prefix = "DRY RUN · " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}DSM MASTER imported: {result['records']} records, "
                f"{result['linked_disorders']} canonical Disorder pages, {result['sources']} sources."
            )
        )
        self.stdout.write(f"Corpus: {result['key']}")
        self.stdout.write(f"SHA256: {result['sha256']}")
        catalog = result["diagnosis_catalog"]
        self.stdout.write(
            f"Diagnosis catalog: {catalog['diagnosis_records']} formal records -> "
            f"{catalog['disorders']} canonical pages; {catalog['duplicate_records_collapsed']} duplicate records collapsed; "
            f"{catalog['created']} created, {catalog['updated']} updated, {catalog['categories']} categories."
        )
        self.stdout.write(
            f"Relations: {result['relations']['nearby']} nearby, "
            f"{result['relations']['differential']} resolved differential."
        )
        for display_type, count in sorted(result["types"].items()):
            self.stdout.write(f"  {display_type}: {count}")
