import json

from django.core.management.base import BaseCommand

from atlas.brain_staging import validate_brain_staging


class Command(BaseCommand):
    help = "Validate Brain promotion candidates without writing canonical content. Publication is data-blocked."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", help="Explicit archived Brain dataset key.")

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(validate_brain_staging(options.get("dataset")), ensure_ascii=False, sort_keys=True))
