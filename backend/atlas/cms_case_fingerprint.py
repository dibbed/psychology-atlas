"""Immutable, server-computed fingerprint of the complete CaseRevision content.

This is a content identity for future P16 manifest/review binding, NOT a
scientific approval or authorization to publish. Never log the snapshot.
"""
import hashlib
import json

from .cms_policy import CMSFailure
from .models import CaseChoice, CaseQuestion, CaseScoringDimension, CaseStep, CaseTransition


_PARTS = (
    ("steps", CaseStep, "revision_id", 200, (
        "id", "case_id", "stable_key", "node_kind", "title", "narrative",
        "sort_order", "is_active",
    )),
    ("scoring_dimensions", CaseScoringDimension, "revision_id", 50, (
        "id", "stable_key", "label", "description", "sort_order", "is_active",
    )),
    ("questions", CaseQuestion, "step__revision_id", 800, (
        "id", "step_id", "scoring_dimension_id", "prompt", "explanation",
        "sort_order", "is_active",
    )),
    ("choices", CaseChoice, "question__step__revision_id", 2000, (
        "id", "question_id", "text", "score_value", "feedback",
        "sort_order", "is_active",
    )),
    ("transitions", CaseTransition, "revision_id", 2000, (
        "id", "source_step_id", "choice_id", "target_step_id", "outcome",
        "sort_order", "is_active",
    )),
)


def case_revision_fingerprint(revision):
    """SHA-256 of all revision-bound content, including inactive graph rows.

    Canonical PKs are deliberately included: rebuilding a graph invalidates
    prior review even if its visible text happens to remain the same.
    Publication status, timestamps and derived hash are excluded to keep a
    reviewed content identity stable when only lifecycle metadata changes.
    """
    content = {
        "schema": "case-revision-content-v1",
        "case_id": revision.case_id,
        "revision_id": revision.pk,
        "version": revision.version,
        "title": revision.title,
        "patient_summary": revision.patient_summary,
        "educational_objective": revision.educational_objective,
        "difficulty": revision.difficulty,
        "primary_disorder_id": revision.primary_disorder_id,
        "rubric_version": revision.rubric_version,
        "entry_step_id": revision.entry_step_id,
        "seed_managed": revision.seed_managed,
    }
    for label, model, lookup, maximum, fields in _PARTS:
        query = model.objects.filter(**{lookup: revision.pk}).order_by("pk")
        rows = list(query.values(*fields)[:maximum + 1])
        if len(rows) > maximum:
            raise CMSFailure("PREVIEW_LIMIT", 400)
        content[label] = rows
    raw = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
