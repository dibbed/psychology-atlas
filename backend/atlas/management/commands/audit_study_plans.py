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

        self.stdout.write(
            "Study plan audit: "
            f"settings={counters['settings']} "
            f"plans={counters['plans']} "
            f"scopes={counters['scopes']} "
            f"blocks={counters['blocks']} "
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
