import json
from django.core.management.base import BaseCommand
from atlas.assessment_publication import publish


class Command(BaseCommand):
    help = "Publish only the exact scientific/rights-reviewed Assessment metadata selection."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Default is an atomic rolled-back dry run.")

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(publish(apply=options["apply"]), sort_keys=True))
