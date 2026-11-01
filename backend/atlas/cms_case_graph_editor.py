"""Bounded, atomic CaseRevision draft graph replacement for the private CMS."""
import json
import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from .case_graph import validate_case_revision_graph
from .cms_case_editor import _lock_revision, revision_etag
from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_sessions import current_session
from .models import (
    CaseAttempt, CaseChoice, CaseQuestion, CaseRevision, CaseScoringDimension,
    CaseStep, CaseTransition,
)

_COLLECTIONS = {
    "steps": (200, {"key", "kind", "title", "narrative", "is_active"}),
    "scoring_dimensions": (50, {"key", "label", "description", "is_active"}),
    "questions": (800, {"key", "step_key", "prompt", "explanation", "dimension_key", "is_active"}),
    "choices": (2000, {"key", "question_key", "text", "score_value", "feedback", "is_active"}),
    "transitions": (2000, {"source_key", "choice_key", "target_key", "outcome", "is_active"}),
}
_KEYS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,119}$")
_TEXT_LIMITS = {"title": 255, "narrative": 20000, "label": 160, "description": 20000,
                "prompt": 20000, "explanation": 20000, "text": 20000, "feedback": 20000}


def _invalid():
    raise CMSFailure("INVALID_GRAPH", 400)


def _graph_contract(payload):
    if type(payload) is not dict or set(payload) != {"entry_step_key", "rubric_version", *_COLLECTIONS}:
        _invalid()
    if type(payload["rubric_version"]) is not int or not 0 <= payload["rubric_version"] <= 1:
        _invalid()
    if len(json.dumps(payload, ensure_ascii=False)) > 750000:
        raise CMSFailure("GRAPH_LIMIT", 400)
    collections = {}
    for name, (maximum, allowed) in _COLLECTIONS.items():
        rows = payload[name]
        if type(rows) is not list or len(rows) > maximum:
            _invalid()
        keys = set()
        for row in rows:
            if type(row) is not dict or set(row) != allowed:
                _invalid()
            for field, value in row.items():
                if field == "key":
                    if type(value) is not str or not _KEYS.fullmatch(value) or value in keys:
                        _invalid()
                    keys.add(value)
                elif field.endswith("_key"):
                    if value is not None and (type(value) is not str or not _KEYS.fullmatch(value)):
                        _invalid()
                elif field == "is_active":
                    if type(value) is not bool:
                        _invalid()
                elif field == "score_value":
                    if type(value) is not int or abs(value) > 10000:
                        _invalid()
                elif field in _TEXT_LIMITS:
                    if type(value) is not str or len(value) > _TEXT_LIMITS[field]:
                        _invalid()
                elif field == "kind":
                    if value not in CaseStep.NodeKind.values:
                        _invalid()
                elif field == "outcome":
                    if value not in CaseTransition.Outcome.values:
                        _invalid()
                else:
                    _invalid()
        collections[name] = rows

    steps = {row["key"]: row for row in collections["steps"]}
    dims = {row["key"]: row for row in collections["scoring_dimensions"]}
    questions = {row["key"]: row for row in collections["questions"]}
    choices = {row["key"]: row for row in collections["choices"]}
    entry = payload["entry_step_key"]
    if entry is not None and (type(entry) is not str or entry not in steps):
        _invalid()
    for row in collections["questions"]:
        if row["step_key"] not in steps or (row["dimension_key"] is not None
            and (row["dimension_key"] not in dims or payload["rubric_version"] == 0)):
            _invalid()
    for row in collections["choices"]:
        if row["question_key"] not in questions:
            _invalid()
    auto_sources, used_choice_keys = set(), set()
    for row in collections["transitions"]:
        if row["source_key"] not in steps:
            _invalid()
        if row["outcome"] == "continue":
            if row["target_key"] not in steps:
                _invalid()
        elif row["target_key"] is not None:
            _invalid()
        if row["choice_key"] is not None:
            if row["choice_key"] not in choices:
                _invalid()
            question = questions[choices[row["choice_key"]]["question_key"]]
            if question["step_key"] != row["source_key"] or row["choice_key"] in used_choice_keys:
                _invalid()
            used_choice_keys.add(row["choice_key"])
        elif row["is_active"]:
            if row["source_key"] in auto_sources:
                _invalid()
            auto_sources.add(row["source_key"])
    return collections


def replace_draft_graph(actor_id, session_id, case_id, revision_id, expected, data, request_id):
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_cases_edit")
        require(actor, "cms_cases_view")
        case, draft = _lock_revision(case_id, revision_id)
        if draft.status != CaseRevision.Status.DRAFT or draft.seed_managed or case.current_revision_id == draft.pk:
            raise CMSFailure("PUBLISHED_REVISION_IMMUTABLE", 409)
        if revision_etag(draft) != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if CaseAttempt.objects.filter(revision=draft).exists():
            raise CMSFailure("REVISION_IN_USE", 409)
        rows = _graph_contract(data)
        # Every delete is inside policy_lock's atomic transaction. No partial graph survives.
        CaseTransition.objects.filter(revision=draft).delete()
        CaseChoice.objects.filter(question__step__revision=draft).delete()
        CaseQuestion.objects.filter(step__revision=draft).delete()
        if draft.entry_step_id is not None:
            draft.entry_step = None
            draft.save(update_fields=["entry_step"])
        CaseStep.objects.filter(revision=draft).delete()
        CaseScoringDimension.objects.filter(revision=draft).delete()

        dimension_ids = {}
        for number, dim in enumerate(rows["scoring_dimensions"]):
            record = CaseScoringDimension.objects.create(
                revision=draft, stable_key=dim["key"], label=dim["label"],
                description=dim["description"], sort_order=number, is_active=dim["is_active"],
            )
            dimension_ids[dim["key"]] = record.pk
        step_ids = {}
        for number, step in enumerate(rows["steps"]):
            record = CaseStep.objects.create(
                case=case, revision=draft, stable_key=step["key"], node_kind=step["kind"],
                title=step["title"], narrative=step["narrative"], sort_order=number,
                is_active=step["is_active"],
            )
            step_ids[step["key"]] = record.pk
        question_ids = {}
        for number, q in enumerate(rows["questions"]):
            record = CaseQuestion.objects.create(
                step_id=step_ids[q["step_key"]], prompt=q["prompt"],
                explanation=q["explanation"], sort_order=number, is_active=q["is_active"],
                scoring_dimension_id=dimension_ids.get(q["dimension_key"]),
            )
            question_ids[q["key"]] = record.pk
        choice_ids = {}
        for number, choice in enumerate(rows["choices"]):
            record = CaseChoice.objects.create(
                question_id=question_ids[choice["question_key"]], text=choice["text"],
                feedback=choice["feedback"], score_value=choice["score_value"],
                sort_order=number, is_active=choice["is_active"],
            )
            choice_ids[choice["key"]] = record.pk
        for number, t in enumerate(rows["transitions"]):
            CaseTransition.objects.create(
                revision=draft, source_step_id=step_ids[t["source_key"]],
                choice_id=choice_ids.get(t["choice_key"]),
                target_step_id=step_ids.get(t["target_key"]),
                outcome=t["outcome"], sort_order=number, is_active=t["is_active"],
            )
        draft.entry_step_id = step_ids.get(data["entry_step_key"])
        draft.rubric_version = data["rubric_version"]
        draft.updated_at = max(timezone.now(), draft.updated_at + timedelta(microseconds=1))
        draft.save(update_fields=["entry_step", "rubric_version", "updated_at"])
        issues = validate_case_revision_graph(draft)
        AdminAuditEvent.objects.create(
            actor=actor, outcome="success", action="case.graph_updated",
            target_kind="clinical-case", target_id=case.pk, request_id=request_id,
            reason="CONTENT_UPDATE", base_revision=draft.version,
            new_revision=draft.version, diff=[],
        )
        return draft, issues
