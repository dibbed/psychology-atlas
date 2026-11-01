"""P12 revision-safe editorial draft cloning and metadata mutations.

Canonical published revisions and learner evidence are never writable here.
Publication / activation remain a distinct later workflow.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Max
from django.utils import timezone

from .cms_models import AdminAuditEvent
from .cms_policy import CMSFailure, policy_lock, require
from .cms_sessions import current_session
from .models import (CaseAttempt, CaseChoice, CaseQuestion, CaseRevision,
                     CaseScoringDimension, CaseStep, CaseTransition, ClinicalCase, Disorder)


def revision_etag(revision):
    return int(revision.updated_at.timestamp() * 1_000_000)


def _lock_revision(case_id, revision_id):
    case = ClinicalCase.objects.select_for_update().filter(pk=case_id).first()
    if case is None:
        raise CMSFailure("NOT_FOUND", 404)
    revision = CaseRevision.objects.select_for_update().filter(
        pk=revision_id, case_id=case_id,
    ).first()
    if revision is None:
        raise CMSFailure("NOT_FOUND", 404)
    return case, revision


def clone_draft(actor_id, session_id, case_id, revision_id, expected, request_id):
    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_cases_create")
        require(actor, "cms_cases_view")
        case, source = _lock_revision(case_id, revision_id)
        if revision_etag(source) != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if source.status != CaseRevision.Status.PUBLISHED or case.current_revision_id != source.pk:
            raise CMSFailure("NOT_CURRENT_REVISION", 409)
        if CaseRevision.objects.filter(case=case, status=CaseRevision.Status.DRAFT).exists():
            raise CMSFailure("DRAFT_EXISTS", 409)
        numbers = CaseRevision.objects.filter(case=case).aggregate(max_version=Max("version"))
        draft = CaseRevision.objects.create(
            case=case, version=(numbers["max_version"] or 0) + 1,
            status=CaseRevision.Status.DRAFT, title=source.title,
            patient_summary=source.patient_summary,
            educational_objective=source.educational_objective, difficulty=source.difficulty,
            primary_disorder_id=source.primary_disorder_id,
            rubric_version=source.rubric_version,
            content_hash="", published_at=None, entry_step=None, seed_managed=False,
        )
        dim_map = {}
        for dim in source.scoring_dimensions.order_by("pk"):
            fresh = CaseScoringDimension.objects.create(
                revision=draft, stable_key=dim.stable_key, label=dim.label,
                description=dim.description, sort_order=dim.sort_order,
                is_active=dim.is_active, seed_managed=False,
            )
            dim_map[dim.pk] = fresh.pk
        step_map = {}
        for step in source.steps.order_by("pk"):
            fresh = CaseStep.objects.create(
                case=case, revision=draft, stable_key=step.stable_key,
                node_kind=step.node_kind, title=step.title, narrative=step.narrative,
                sort_order=step.sort_order, is_active=step.is_active,
            )
            step_map[step.pk] = fresh.pk
        choice_map = {}
        for question in CaseQuestion.objects.filter(step__revision=source).order_by("pk"):
            fresh_q = CaseQuestion.objects.create(
                step_id=step_map[question.step_id], prompt=question.prompt,
                explanation=question.explanation, sort_order=question.sort_order,
                scoring_dimension_id=dim_map.get(question.scoring_dimension_id),
                is_active=question.is_active,
            )
            for choice in question.choices.order_by("pk"):
                fresh_choice = CaseChoice.objects.create(
                    question=fresh_q, text=choice.text, score_value=choice.score_value,
                    feedback=choice.feedback, sort_order=choice.sort_order,
                    is_active=choice.is_active,
                )
                choice_map[choice.pk] = fresh_choice.pk
        for transition in source.transitions.order_by("pk"):
            CaseTransition.objects.create(
                revision=draft, source_step_id=step_map[transition.source_step_id],
                choice_id=choice_map.get(transition.choice_id),
                target_step_id=step_map.get(transition.target_step_id),
                outcome=transition.outcome, sort_order=transition.sort_order,
                is_active=transition.is_active, seed_managed=False,
            )
        if source.entry_step_id:
            draft.entry_step_id = step_map[source.entry_step_id]
            draft.save(update_fields=["entry_step"])
        AdminAuditEvent.objects.create(
            actor=actor, outcome="success", action="case.draft_cloned", target_kind="clinical-case",
            target_id=case.pk, request_id=request_id, reason="DRAFT_CREATION",
            base_revision=source.version, new_revision=draft.version, diff=[],
        )
        return draft


def update_draft_metadata(actor_id, session_id, case_id, revision_id, expected, data, request_id):
    allowed = {"title", "patient_summary", "educational_objective", "difficulty", "primary_disorder_id"}
    if not isinstance(data, dict) or not data or set(data) - allowed:
        raise CMSFailure("INVALID_FIELDS", 400)
    for name, limit in (("title", 255), ("patient_summary", 20000), ("educational_objective", 20000)):
        if name in data and (type(data[name]) is not str or len(data[name]) > limit):
            raise CMSFailure("INVALID_FIELDS", 400)
    if "difficulty" in data and data["difficulty"] not in ClinicalCase.Difficulty.values:
        raise CMSFailure("INVALID_FIELDS", 400)
    if "primary_disorder_id" in data and data["primary_disorder_id"] is not None and (
        type(data["primary_disorder_id"]) is not int or data["primary_disorder_id"] <= 0
    ):
        raise CMSFailure("INVALID_FIELDS", 400)

    with policy_lock():
        actor = get_user_model().objects.get(pk=actor_id)
        current_session(session_id, actor)
        require(actor, "cms_cases_edit")
        require(actor, "cms_cases_view")
        case, draft = _lock_revision(case_id, revision_id)
        if (draft.status != CaseRevision.Status.DRAFT or draft.seed_managed
                or case.current_revision_id == draft.pk):
            raise CMSFailure("PUBLISHED_REVISION_IMMUTABLE", 409)
        if revision_etag(draft) != expected:
            raise CMSFailure("STALE_REVISION", 412)
        if CaseAttempt.objects.filter(revision=draft).exists():
            raise CMSFailure("REVISION_IN_USE", 409)
        if "primary_disorder_id" in data and data["primary_disorder_id"] is not None:
            if not Disorder.objects.filter(pk=data["primary_disorder_id"], is_active=True).exists():
                raise CMSFailure("INVALID_REFERENCE", 400)
        changed = []
        for name, value in data.items():
            if getattr(draft, name) != value:
                changed.append(name)
                setattr(draft, name, value)
        if changed:
            # Include updated_at in the same atomic edit for stable If-Match comparisons.
            draft.updated_at = max(timezone.now(), draft.updated_at + timedelta(microseconds=1))
            draft.save(update_fields=[*changed, "updated_at"])
            AdminAuditEvent.objects.create(
                actor=actor, outcome="success", action="case.draft_updated", target_kind="clinical-case",
                target_id=case.pk, request_id=request_id, reason="CONTENT_UPDATE",
                base_revision=draft.version, new_revision=draft.version,
                diff=sorted(k for k in changed if k in {"title", "difficulty"}),
            )
        return draft
