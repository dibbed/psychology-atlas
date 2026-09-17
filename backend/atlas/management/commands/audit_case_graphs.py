from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from atlas.case_graph import validate_case_revision_graph
from atlas.models import (
    CaseAttempt,
    CaseAttemptAnswer,
    CaseAttemptEvent,
    CaseRevision,
    CaseScoringDimension,
    CaseStep,
    CaseTransition,
    ClinicalCase,
)


class Command(BaseCommand):
    help = "Audit branching Clinical Case revision graphs and attempt-state integrity without mutating data."

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

        duplicate_active = (
            CaseAttempt.objects.filter(status=CaseAttempt.Status.IN_PROGRESS)
            .values("user_id", "case_id")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
        )
        for row in duplicate_active:
            failures.append(
                f"attempts:user={row['user_id']}:case={row['case_id']}:in_progress_count={row['total']}"
            )

        attempts = CaseAttempt.objects.select_related("case", "revision", "current_step")
        for attempt in attempts:
            if attempt.revision.case_id != attempt.case_id:
                failures.append(f"attempt:{attempt.id}:revision_case_mismatch")
            if attempt.status == CaseAttempt.Status.IN_PROGRESS and attempt.current_step_id is None:
                failures.append(f"attempt:{attempt.id}:current_step_missing")
            if attempt.current_step_id:
                if attempt.current_step.case_id != attempt.case_id:
                    failures.append(f"attempt:{attempt.id}:current_step_case_mismatch")
                if attempt.current_step.revision_id != attempt.revision_id:
                    failures.append(f"attempt:{attempt.id}:current_step_revision_mismatch")
            if attempt.status == CaseAttempt.Status.COMPLETED:
                if attempt.current_step_id is not None:
                    failures.append(f"attempt:{attempt.id}:completed_has_current_step")
                if attempt.completed_at is None:
                    failures.append(f"attempt:{attempt.id}:completed_at_missing")
            elif attempt.completed_at is not None:
                failures.append(f"attempt:{attempt.id}:in_progress_has_completed_at")

            events = list(attempt.events.order_by("state_version_before", "id"))
            if events:
                if attempt.revision.entry_step_id and events[0].step_id != attempt.revision.entry_step_id:
                    failures.append(f"attempt:{attempt.id}:first_event_not_revision_entry")
            elif (
                attempt.status == CaseAttempt.Status.IN_PROGRESS
                and attempt.revision.entry_step_id
                and attempt.current_step_id != attempt.revision.entry_step_id
            ):
                failures.append(f"attempt:{attempt.id}:initial_current_step_not_revision_entry")

            for expected_before, event in enumerate(events):
                if event.state_version_before != expected_before:
                    failures.append(
                        f"attempt:{attempt.id}:event:{event.id}:state_before={event.state_version_before}:expected={expected_before}"
                    )
                if event.state_version_after != event.state_version_before + 1:
                    failures.append(f"attempt:{attempt.id}:event:{event.id}:state_version_jump")
                if expected_before > 0:
                    previous = events[expected_before - 1]
                    if previous.outcome != CaseTransition.Outcome.CONTINUE:
                        failures.append(f"attempt:{attempt.id}:event_after_completion")
                    elif previous.next_step_id != event.step_id:
                        failures.append(
                            f"attempt:{attempt.id}:event:{event.id}:step_does_not_match_previous_target"
                        )
                if event.outcome == CaseTransition.Outcome.COMPLETE and expected_before != len(events) - 1:
                    failures.append(f"attempt:{attempt.id}:event:{event.id}:completion_not_terminal_in_history")

            expected_state_version = events[-1].state_version_after if events else 0
            if attempt.state_version != expected_state_version:
                failures.append(
                    f"attempt:{attempt.id}:state_version={attempt.state_version}:expected={expected_state_version}"
                )
            if events:
                final_event = events[-1]
                if attempt.status == CaseAttempt.Status.COMPLETED:
                    if final_event.outcome != CaseTransition.Outcome.COMPLETE:
                        failures.append(f"attempt:{attempt.id}:completed_without_terminal_event")
                elif final_event.outcome == CaseTransition.Outcome.COMPLETE:
                    failures.append(f"attempt:{attempt.id}:in_progress_after_completion_event")
                elif attempt.current_step_id != final_event.next_step_id:
                    failures.append(f"attempt:{attempt.id}:current_step_not_latest_event_target")

        event_node_kinds = {
            CaseAttemptEvent.EventType.DECISION: CaseStep.NodeKind.DECISION,
            CaseAttemptEvent.EventType.ADVANCE: CaseStep.NodeKind.INFORMATION,
            CaseAttemptEvent.EventType.TERMINAL_COMPLETE: CaseStep.NodeKind.TERMINAL,
        }
        for event in CaseAttemptEvent.objects.select_related(
            "attempt__revision",
            "step__revision",
            "question__step",
            "question__scoring_dimension",
            "scoring_dimension",
            "selected_choice__question",
            "transition__revision",
            "transition__source_step",
            "next_step__revision",
        ):
            if event.step.revision_id != event.attempt.revision_id:
                failures.append(f"event:{event.id}:step_revision_mismatch")
            expected_node_kind = event_node_kinds.get(event.event_type)
            if expected_node_kind is None:
                failures.append(f"event:{event.id}:unknown_event_type")
            elif event.step.node_kind != expected_node_kind:
                failures.append(f"event:{event.id}:event_node_kind_mismatch")

            snapshot = event.snapshot if isinstance(event.snapshot, dict) else {}
            if snapshot.get("step_key") != event.step.stable_key:
                failures.append(f"event:{event.id}:snapshot_step_key_mismatch")
            if expected_node_kind is not None and snapshot.get("node_kind") != expected_node_kind:
                failures.append(f"event:{event.id}:snapshot_node_kind_mismatch")
            if snapshot.get("outcome") != event.outcome:
                failures.append(f"event:{event.id}:snapshot_outcome_mismatch")
            expected_target_key = event.next_step.stable_key if event.next_step_id else None
            if snapshot.get("target_step_key") != expected_target_key:
                failures.append(f"event:{event.id}:snapshot_target_mismatch")
            if event.event_type == CaseAttemptEvent.EventType.DECISION:
                if not isinstance(snapshot.get("choice_text"), str) or not snapshot.get("choice_text"):
                    failures.append(f"event:{event.id}:snapshot_choice_text_missing")
            elif snapshot.get("choice_text") is not None:
                failures.append(f"event:{event.id}:non_decision_snapshot_has_choice_text")

            if event.question_id and event.question.step_id != event.step_id:
                failures.append(f"event:{event.id}:question_step_mismatch")
            if event.scoring_dimension_id:
                if event.scoring_dimension.revision_id != event.attempt.revision_id:
                    failures.append(f"event:{event.id}:scoring_dimension_revision_mismatch")
                if not event.question_id or event.question.scoring_dimension_id != event.scoring_dimension_id:
                    failures.append(f"event:{event.id}:scoring_dimension_question_mismatch")
                dimension_snapshot = event.snapshot.get("scoring_dimension") if isinstance(event.snapshot, dict) else None
                if not isinstance(dimension_snapshot, dict):
                    failures.append(f"event:{event.id}:scoring_dimension_snapshot_missing")
                else:
                    if dimension_snapshot.get("key") != event.scoring_dimension.stable_key:
                        failures.append(f"event:{event.id}:scoring_dimension_snapshot_key_mismatch")
                    if dimension_snapshot.get("label") != event.scoring_dimension.label:
                        failures.append(f"event:{event.id}:scoring_dimension_snapshot_label_mismatch")
            elif event.question_id and event.question.scoring_dimension_id:
                failures.append(f"event:{event.id}:scoring_dimension_missing")
            if event.selected_choice_id and event.selected_choice.question_id != event.question_id:
                failures.append(f"event:{event.id}:choice_question_mismatch")
            if event.transition_id:
                if event.transition.revision_id != event.attempt.revision_id:
                    failures.append(f"event:{event.id}:transition_revision_mismatch")
                if event.transition.source_step_id != event.step_id:
                    failures.append(f"event:{event.id}:transition_source_mismatch")
                if event.outcome != event.transition.outcome:
                    failures.append(f"event:{event.id}:transition_outcome_mismatch")
                if event.next_step_id != event.transition.target_step_id:
                    failures.append(f"event:{event.id}:transition_target_mismatch")
            if event.next_step_id and event.next_step.revision_id != event.attempt.revision_id:
                failures.append(f"event:{event.id}:next_step_revision_mismatch")

        for answer in CaseAttemptAnswer.objects.select_related(
            "attempt__revision",
            "question__step__revision",
            "question__scoring_dimension",
            "scoring_dimension",
            "selected_choice__question",
        ):
            if answer.selected_choice.question_id != answer.question_id:
                failures.append(f"answer:{answer.id}:choice_question_mismatch")
            if answer.question.step.revision_id != answer.attempt.revision_id:
                failures.append(f"answer:{answer.id}:question_revision_mismatch")
            if answer.scoring_dimension_id:
                if answer.scoring_dimension.revision_id != answer.attempt.revision_id:
                    failures.append(f"answer:{answer.id}:scoring_dimension_revision_mismatch")
                if answer.question.scoring_dimension_id != answer.scoring_dimension_id:
                    failures.append(f"answer:{answer.id}:scoring_dimension_question_mismatch")
            elif answer.question.scoring_dimension_id:
                failures.append(f"answer:{answer.id}:scoring_dimension_missing")

        self.stdout.write(
            f"Clinical case graph audit: cases={ClinicalCase.objects.count()} "
            f"revisions={revisions.count()} dimensions={CaseScoringDimension.objects.count()} "
            f"attempts={CaseAttempt.objects.count()} events={CaseAttemptEvent.objects.count()} "
            f"answers={CaseAttemptAnswer.objects.count()} "
            f"failures={len(failures)}"
        )
        if failures:
            raise CommandError("Clinical case graph audit FAILED\n- " + "\n- ".join(failures[:50]))
        self.stdout.write(self.style.SUCCESS("Clinical case graph audit PASS"))
