"""Read-only integrity audit of durable Recommendation V2 feedback events."""

import hashlib
import json
import re
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from atlas.models import RecommendationFeedback


KEY_PATTERN = re.compile(r"^r2_[0-9a-f]{64}$")
IDENTITIES = {
    "overdue_block": ("study_block", "block_overdue", r"scheduled:\d{4}-\d{2}-\d{2}"),
    "plan_schedule_stale": ("study_plan", "schedule_stale", r"generation:\d+"),
    "plan_generate": ("study_plan", "schedule_missing", r"generation:0"),
    "srs_review": ("review_queue", "srs_due", r"due_day:\d{4}-\d{2}-\d{2}"),
    "plan_capacity": ("study_plan", "plan_capacity_gap", r"generation:\d+"),
    "case_resume": ("clinical_case", "case_in_progress", r"attempt:\d+"),
    "quiz_retry": ("quiz", "recent_incorrect_quiz_answers", r"attempt:\d+"),
    "distortion_practice": ("concept", "explicit_distortion_scope", r"plan:\d+:scope:\d+"),
    "concept_review": ("concept", "concept_progress_low", r"current_progress"),
    "disorder_review": ("disorder", "disorder_progress_low", r"current_progress"),
    "graph_explore": (
        "concept",
        "reviewed_explicit_relation",
        r"theoryconcept:\d+:[a-z0-9_]+:scope:\d+",
    ),
    "srs_start": ("review_queue", "srs_new", r"new_day:\d{4}-\d{2}-\d{2}"),
}


class Command(BaseCommand):
    help = "Read-only integrity audit of Recommendation V2 feedback events. Never repairs data."

    def handle(self, *args, **options):
        failures = []
        count = 0
        rows = RecommendationFeedback.objects.order_by("id").iterator(chunk_size=1000)
        for row in rows:
            count += 1
            identity = IDENTITIES.get(row.recommendation_type)
            if identity is None:
                failures.append(f"feedback:{row.id}:invalid_type")
            else:
                target_type, reason_code, context_pattern = identity
                if row.target_type != target_type or row.reason_code != reason_code:
                    failures.append(f"feedback:{row.id}:invalid_identity_fields")
                if re.fullmatch(context_pattern, row.context_ref, flags=re.ASCII) is None:
                    failures.append(f"feedback:{row.id}:invalid_context_ref")

            if (row.target_type == "review_queue") != (row.target_id is None):
                failures.append(f"feedback:{row.id}:invalid_target_id")
            elif row.target_id is not None and row.target_id < 1:
                failures.append(f"feedback:{row.id}:invalid_target_id")

            serialized = json.dumps(
                [
                    "rec-v2",
                    row.recommendation_type,
                    row.target_type,
                    row.target_id,
                    row.reason_code,
                    row.context_ref,
                ],
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8")
            expected_key = "r2_" + hashlib.sha256(serialized).hexdigest()
            if not KEY_PATTERN.fullmatch(row.recommendation_key) or row.recommendation_key != expected_key:
                failures.append(f"feedback:{row.id}:invalid_key")

            if row.value not in RecommendationFeedback.Value.values:
                failures.append(f"feedback:{row.id}:invalid_value")
            if row.value == RecommendationFeedback.Value.DISMISSED:
                if row.suppressed_until != row.created_at + timedelta(days=7):
                    failures.append(f"feedback:{row.id}:invalid_suppression")
            elif row.suppressed_until is not None:
                failures.append(f"feedback:{row.id}:invalid_suppression")

        self.stdout.write(f"Recommendation feedback audit: events={count} failures={len(failures)}")
        for failure in failures:
            self.stdout.write(f"FAIL {failure}")
        if failures:
            raise CommandError(f"Recommendation feedback audit failed with {len(failures)} failure(s).")
        self.stdout.write(self.style.SUCCESS("Recommendation feedback audit PASS"))
