from collections import Counter

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from atlas import models
from atlas.study_scheduler import _block_target_active
from atlas.study_planning import _scope_target, _target_active


class Command(BaseCommand):
    help = "Read-only integrity audit for v0.8 Study Plans and Study Blocks. Never repairs data."

    def handle(self, *args, **options):
        failures = []
        warnings = []
        counters = Counter()

        settings_rows = models.UserStudySettings.objects.select_related("user").order_by("id")
        for row in settings_rows.iterator():
            counters["settings"] += 1
            try:
                row.full_clean(validate_unique=False, validate_constraints=False)
            except ValidationError as exc:
                failures.append(f"settings:{row.id}:invalid:{exc}")

        plans = (
            models.StudyPlan.objects.select_related("user")
            .prefetch_related("availability", "scopes")
            .order_by("id")
        )
        for plan in plans:
            counters["plans"] += 1
            availability = list(plan.availability.all())
            if len(availability) != 7 or {row.weekday for row in availability} != set(range(7)):
                failures.append(f"plan:{plan.id}:availability_not_seven_days")
            for row in availability:
                try:
                    row.full_clean(validate_unique=False, validate_constraints=False)
                except ValidationError as exc:
                    failures.append(f"availability:{row.id}:invalid:{exc}")

            try:
                plan.full_clean(validate_unique=False, validate_constraints=False)
            except ValidationError as exc:
                failures.append(f"plan:{plan.id}:invalid:{exc}")

            if plan.plan_kind == models.StudyPlan.Kind.EXAM:
                if plan.target_date is None:
                    failures.append(f"plan:{plan.id}:exam_without_target")
                elif plan.target_date < plan.start_date:
                    failures.append(f"plan:{plan.id}:target_before_start")

            scopes = list(plan.scopes.all())
            counters["scopes"] += len(scopes)
            if plan.status == models.StudyPlan.Status.ACTIVE:
                if not scopes:
                    failures.append(f"plan:{plan.id}:active_without_scope")
                if not any(row.available_minutes > 0 for row in availability):
                    failures.append(f"plan:{plan.id}:active_without_capacity")

            for scope in scopes:
                try:
                    scope.full_clean(validate_unique=False, validate_constraints=False)
                except ValidationError as exc:
                    failures.append(f"scope:{scope.id}:invalid:{exc}")
                    continue
                target_type, target = _scope_target(scope)
                if target is None:
                    failures.append(f"scope:{scope.id}:missing_target")
                elif not _target_active(target_type, target):
                    warnings.append(f"scope:{scope.id}:target_inactive")

        active_keys = set()
        blocks = (
            models.StudyBlock.objects.select_related(
                "plan",
                "scope",
                "disorder",
                "concept",
                "therapy",
                "therapy__family",
                "theory",
                "psychologist",
                "timeline_event",
                "quiz",
                "quiz__disorder",
                "clinical_case",
                "clinical_case__current_revision",
                "clinical_case__current_revision__primary_disorder",
                "clinical_case__current_revision__entry_step",
            )
            .order_by("id")
        )
        for block in blocks.iterator():
            counters["blocks"] += 1
            try:
                block.full_clean(validate_unique=False, validate_constraints=False)
            except ValidationError as exc:
                failures.append(f"block:{block.id}:invalid:{exc}")
                continue

            if block.generation_version > block.plan.generation_version:
                failures.append(f"block:{block.id}:generation_ahead_of_plan")
            if block.scope_id and block.scope.plan_id != block.plan_id:
                failures.append(f"block:{block.id}:scope_plan_mismatch")
            if not _block_target_active(block):
                warnings.append(f"block:{block.id}:target_inactive")

            metadata = block.metadata if isinstance(block.metadata, dict) else {}
            candidate_key = metadata.get("candidate_key")
            if (
                block.origin == models.StudyBlock.Origin.GENERATED
                and block.status
                not in {
                    models.StudyBlock.Status.SUPERSEDED,
                    models.StudyBlock.Status.SKIPPED,
                }
                and isinstance(candidate_key, str)
                and candidate_key
            ):
                key = (block.plan_id, candidate_key)
                if key in active_keys:
                    failures.append(
                        f"plan:{block.plan_id}:duplicate_active_candidate:{candidate_key}"
                    )
                active_keys.add(key)

        active_session_users = set()
        sessions = models.StudySession.objects.select_related(
            "plan", "primary_block", "primary_block__plan"
        ).order_by("id")
        for session in sessions.iterator():
            counters["sessions"] += 1
            if session.status == models.StudySession.Status.IN_PROGRESS:
                if session.user_id in active_session_users:
                    failures.append(f"session:{session.id}:duplicate_active_user")
                active_session_users.add(session.user_id)
            if session.plan.user_id != session.user_id:
                failures.append(f"session:{session.id}:foreign_plan")
            if session.primary_block_id is not None and (
                session.primary_block.plan_id != session.plan_id
                or session.primary_block.plan.user_id != session.user_id
                or session.primary_block_id != session.block_id_at_start
            ):
                failures.append(f"session:{session.id}:block_plan_mismatch")
            if not 5 <= session.planned_minutes <= 240 or not 0 <= session.actual_seconds <= 86400:
                failures.append(f"session:{session.id}:invalid_duration")
            if session.status == models.StudySession.Status.IN_PROGRESS:
                valid = (session.completed_at is None and session.abandoned_at is None
                         and session.actual_seconds == 0)
            elif session.status == models.StudySession.Status.COMPLETED:
                valid = (session.completed_at is not None and session.abandoned_at is None
                         and session.completed_at >= session.started_at)
                if valid:
                    valid = session.actual_seconds == min(
                        max(0, int((session.completed_at - session.started_at).total_seconds())), 86400
                    )
            elif session.status == models.StudySession.Status.ABANDONED:
                valid = (session.abandoned_at is not None and session.completed_at is None
                         and session.abandoned_at >= session.started_at)
                if valid:
                    valid = session.actual_seconds == min(
                        max(0, int((session.abandoned_at - session.started_at).total_seconds())), 86400
                    )
            else:
                valid = False
            if not valid or session.block_id_at_start <= 0:
                failures.append(f"session:{session.id}:invalid_lifecycle")

        self.stdout.write(
            "Study plan audit: "
            f"settings={counters['settings']} "
            f"plans={counters['plans']} "
            f"scopes={counters['scopes']} "
            f"blocks={counters['blocks']} "
            f"sessions={counters['sessions']} "
            f"warnings={len(warnings)} "
            f"failures={len(failures)}"
        )
        for item in warnings:
            self.stdout.write(f"WARNING {item}")
        for item in failures:
            self.stdout.write(f"FAIL {item}")

        if failures:
            raise CommandError(f"Study plan audit failed with {len(failures)} failure(s).")
        self.stdout.write(self.style.SUCCESS("Study plan audit PASS"))
