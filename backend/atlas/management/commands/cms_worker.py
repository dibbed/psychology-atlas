import time

from django.core.management.base import BaseCommand, CommandError

from atlas.cms_jobs import run_once
from atlas.cms_policy import CMSFailure


class Command(BaseCommand):
    help = "Poll durable, registered CMS jobs; no arbitrary commands or canonical promotion."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process at most one eligible job and exit.")
        parser.add_argument("--poll-seconds", type=int, default=2)

    def handle(self, *args, **options):
        if not 1 <= options["poll_seconds"] <= 60:
            raise CommandError("poll-seconds must be between 1 and 60")
        while True:
            try:
                job = run_once()
            except CMSFailure as error:
                code = str(error.detail["code"])
                if code == "WORKER_UNAVAILABLE" and not options["once"]:
                    self.stderr.write("WORKER_UNAVAILABLE; polling paused")
                    time.sleep(options["poll_seconds"])
                    continue
                raise CommandError(code)
            if job:
                self.stdout.write(f"{job.pk} {job.status}")
            if options["once"]:
                return
            if job is None:
                time.sleep(options["poll_seconds"])
