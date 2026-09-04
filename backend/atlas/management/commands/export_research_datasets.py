import hashlib
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from atlas.models import ResearchDataset


class Command(BaseCommand):
    help = "Recreate imported research JSON files exactly from ResearchDataset.raw_text."

    def add_arguments(self, parser):
        parser.add_argument("output_dir", help="Directory to write reconstructed research JSON files into.")
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Allow replacing files that already exist in the output directory.",
        )

    def handle(self, *args, **options):
        output_dir = Path(options["output_dir"]).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        overwrite = options["overwrite"]

        datasets = list(ResearchDataset.objects.filter(is_active=True).order_by("id"))
        if not datasets:
            raise CommandError("No active ResearchDataset rows are available to export.")

        for dataset in datasets:
            if not dataset.raw_text:
                raise CommandError(
                    f"ResearchDataset {dataset.pk} ({dataset.source_filename}) has no raw_text; "
                    "re-import the original source before deleting it."
                )
            raw_bytes = dataset.raw_text.encode("utf-8")
            digest = hashlib.sha256(raw_bytes).hexdigest()
            if digest != dataset.source_sha256:
                raise CommandError(
                    f"SHA-256 mismatch for ResearchDataset {dataset.pk}: "
                    f"expected {dataset.source_sha256}, got {digest}."
                )

            destination = output_dir / dataset.source_filename
            if destination.exists() and not overwrite:
                raise CommandError(f"Destination already exists: {destination}")
            destination.write_bytes(raw_bytes)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Exported {dataset.source_filename} · {len(raw_bytes)} bytes · sha256={digest}"
                )
            )
