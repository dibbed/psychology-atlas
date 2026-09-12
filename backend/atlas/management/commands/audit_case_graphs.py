from django.core.management.base import BaseCommand, CommandError

from atlas.case_graph import validate_case_revision_graph
from atlas.models import CaseAttempt, CaseAttemptAnswer, CaseRevision, ClinicalCase


class Command(BaseCommand):
    help = "Audit branching Clinical Case revision graphs without mutating data."

    def handle(self, *args, **options):
        failures = []
        revisions = CaseRevision.objects.select_related("case", "entry_step").order_by("case__slug", "version")

        for case in ClinicalCase.objects.filter(is_active=True).select_related("current_revision"):
            if case.current_revision_id is None:
                failures.append(f"case:{case.slug}:current_revision_missing")
                continue
            if case.current_revision.case_id != case.id:
                failures.append(f"case:{case.slug}:current_revision_case_mismatch")
            if case.current_revision.status != CaseRevision.Status.PUBLISHED:
                failures.append(f"case:{case.slug}:current_revision_not_published")
            if case.current_revision.entry_step_id is None:
                failures.append(f"case:{case.slug}:current_revision_entry_missing")
            published_count = case.revisions.filter(status=CaseRevision.Status.PUBLISHED).count()
            if published_count != 1:
                failures.append(f"case:{case.slug}:published_revision_count={published_count}")

        for revision in revisions:
            issues = validate_case_revision_graph(revision)
            if issues:
                failures.extend(f"revision:{revision.case.slug}:v{revision.version}:{issue}" for issue in issues)

        for attempt in CaseAttempt.objects.select_related("case", "revision"):
            if attempt.revision.case_id != attempt.case_id:
                failures.append(f"attempt:{attempt.id}:revision_case_mismatch")

        for answer in CaseAttemptAnswer.objects.select_related(
            "attempt__revision",
            "question__step__revision",
            "selected_choice__question",
        ):
            if answer.selected_choice.question_id != answer.question_id:
                failures.append(f"answer:{answer.id}:choice_question_mismatch")
            if answer.question.step.revision_id != answer.attempt.revision_id:
                failures.append(f"answer:{answer.id}:question_revision_mismatch")

        self.stdout.write(
            f"Clinical case graph audit: cases={ClinicalCase.objects.count()} "
            f"revisions={revisions.count()} attempts={CaseAttempt.objects.count()} "
            f"answers={CaseAttemptAnswer.objects.count()} failures={len(failures)}"
        )
        if failures:
            raise CommandError("Clinical case graph audit FAILED\n- " + "\n- ".join(failures[:50]))
        self.stdout.write(self.style.SUCCESS("Clinical case graph audit PASS"))
