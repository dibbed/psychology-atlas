from django.core.management.base import BaseCommand
from django.db import transaction

from atlas.research_promotion import promote_research_staging


class Command(BaseCommand):
    help = (
        "Conservatively promote source-backed Psychology Atlas ResearchRecord staging "
        "into canonical Psychologist/Theory/Timeline models and explicit sourced relations."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Execute the complete promotion inside a rolled-back transaction.",
        )

    def handle(self, *args, **options):
        with transaction.atomic():
            report = promote_research_staging()
            if options["dry_run"]:
                transaction.set_rollback(True)

        mode = "DRY RUN" if options["dry_run"] else "COMMITTED"
        self.stdout.write(self.style.SUCCESS(f"Research staging promotion {mode}"))
        for key in sorted(report):
            self.stdout.write(f"  {key}: {report[key]}")
