"""Owner-scoped StudySession lifecycle; sessions never write learning evidence."""

import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, OperationalError, connection, transaction
from django.utils import timezone

from . import models
from .learning import challenge_attempt_for_today, today_challenge
from .study_scheduler import (
    CANONICAL_EVIDENCE_KINDS, _SQLITE_LOCK_RETRY_DELAYS, _block_href,
    _block_queryset, _block_target_active,
)


class StudySessionError(Exception):
    def __init__(self, code, detail, status_code=400, errors=None):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.errors = errors


def _error(code, detail, status_code=409):
    raise StudySessionError(code, detail, status_code)


def _session_query(user):
    return models.StudySession.objects.filter(user=user)


def get_current_session(user):
    return _session_query(user).filter(status=models.StudySession.Status.IN_PROGRESS).first()


def get_session(user, session_id):
    session = _session_query(user).filter(pk=session_id).first()
    if session is None:
        _error("study_session_not_found", "Study session not found.", 404)
    return session


def _study_date(user, now):
    row = models.UserStudySettings.objects.filter(user=user).only("study_timezone").first()
    name = row.study_timezone if row else settings.TIME_ZONE
    try:
        zone = ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        zone = ZoneInfo(settings.TIME_ZONE)
    return now.astimezone(zone).date()


def _minutes_limits(user):
    row = models.UserStudySettings.objects.filter(user=user).only(
        "default_session_minutes", "default_daily_minutes"
    ).first()
    if row is not None:
        return row.default_session_minutes, row.default_daily_minutes
    return (
        models.UserStudySettings._meta.get_field("default_session_minutes").get_default(),
        models.UserStudySettings._meta.get_field("default_daily_minutes").get_default(),
    )


def _target_active(user, block, now):
    if not _block_target_active(block):
        return False
    if block.block_kind == models.StudyBlock.Kind.DAILY_CHALLENGE_OPTIONAL:
        app_date = timezone.localtime(now).date()
        return (
            block.scheduled_date == _study_date(user, now)
            and today_challenge(app_date) is not None
            and challenge_attempt_for_today(user, app_date) is None
        )
    return True


def _actionable(user, block, now):
    return (
        block.plan.status == models.StudyPlan.Status.ACTIVE
        and block.status in (models.StudyBlock.Status.PENDING, models.StudyBlock.Status.IN_PROGRESS)
        and _target_active(user, block, now)
    )


def block_action_href(block):
    if block.block_kind == models.StudyBlock.Kind.NOTES_REVIEW:
        return "/notes"
    if block.block_kind == models.StudyBlock.Kind.DAILY_CHALLENGE_OPTIONAL:
        return "/study#daily-challenge"
    return _block_href(block)


def _block_payload(user, block, now):
    target_active = _target_active(user, block, now)
    href = None
    if _actionable(user, block, now):
        href = block_action_href(block)
    return {
        "id": block.id,
        "plan_id": block.plan_id,
        "block_kind": block.block_kind,
        "status": block.status,
        "scheduled_date": block.scheduled_date.isoformat(),
        "estimated_minutes": block.estimated_minutes,
        "snapshot_title": block.snapshot_title,
        "action_href": href,
        "target_active": target_active,
        "evidence_required": block.block_kind in CANONICAL_EVIDENCE_KINDS,
    }


def _elapsed(start, end):
    raw = max(0, int((end - start).total_seconds()))
    return min(raw, 86400), raw > 86400


def serialize_session(user, session, *, as_of=None):
    as_of = as_of or timezone.now()
    if session.status == models.StudySession.Status.IN_PROGRESS:
        elapsed_seconds, elapsed_capped = _elapsed(session.started_at, as_of)
    else:
        end = session.completed_at or session.abandoned_at
        _, elapsed_capped = _elapsed(session.started_at, end)
        elapsed_seconds = session.actual_seconds
    block = None
    if session.primary_block_id is not None:
        owned = _block_queryset().filter(
            pk=session.primary_block_id, plan_id=session.plan_id, plan__user=user
        ).first()
        if owned is not None:
            block = _block_payload(user, owned, as_of)
    return {
        "id": session.id,
        "status": session.status,
        "plan_id": session.plan_id,
        "primary_block_id": session.primary_block_id,
        "block_id_at_start": session.block_id_at_start,
        "planned_minutes": session.planned_minutes,
        "started_at": session.started_at.isoformat(),
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        "abandoned_at": session.abandoned_at.isoformat() if session.abandoned_at else None,
        "actual_seconds": session.actual_seconds,
        "elapsed_seconds": elapsed_seconds,
        "elapsed_capped": elapsed_capped,
        "as_of": as_of.isoformat(),
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "primary_block": block,
    }


def _replay_or_active(user, block_id, event_id, explicit_minutes, effective_minutes=None):
    replay = _session_query(user).filter(client_event_id=event_id).first()
    if replay is not None:
        if (replay.block_id_at_start != block_id or
                (explicit_minutes is not None and replay.planned_minutes != explicit_minutes)):
            _error("study_session_event_conflict", "Event ID belongs to another start request.")
        return replay
    active = get_current_session(user)
    if active is not None:
        if (effective_minutes is not None and active.block_id_at_start == block_id
                and active.planned_minutes == effective_minutes):
            return active
        _error("study_session_active", "Another study session is already active.")
    return None


def _is_session_unique_error(exc):
    constraint = getattr(getattr(exc, "__cause__", None), "diag", None)
    if getattr(constraint, "constraint_name", None) in {
        "uq_study_session_active_user", "uq_study_session_event"
    }:
        return True
    message = str(exc).lower()
    return connection.vendor == "sqlite" and (
        "unique constraint failed: atlas_studysession.user_id" in message
    )


def _is_sqlite_lock(exc):
    return connection.vendor == "sqlite" and any(
        marker in str(exc).lower()
        for marker in ("database is locked", "database table is locked")
    )


def _start_once(user, block_id, event_id, explicit_minutes):
    with transaction.atomic():
        replay = _session_query(user).filter(client_event_id=event_id).first()
        if replay is not None:
            return _replay_or_active(user, block_id, event_id, explicit_minutes), False

        # PostgreSQL serializes this owner's starts; SQLite uses the unique index and bounded retry.
        get_user_model().objects.select_for_update().get(pk=user.pk)
        locator = models.StudyBlock.objects.filter(
            pk=block_id, plan__user=user
        ).values("plan_id").first()
        if locator is None:
            _error("study_block_not_found", "Study block not found.", 404)
        plan = models.StudyPlan.objects.select_for_update().filter(
            pk=locator["plan_id"], user=user
        ).first()
        if plan is None:
            _error("study_block_not_found", "Study block not found.", 404)
        block = _block_queryset().select_for_update(of=("self",)).filter(
            pk=block_id, plan=plan, plan__user=user
        ).first()
        if block is None:
            _error("study_block_not_found", "Study block not found.", 404)
        default_minutes, daily_minutes = _minutes_limits(user)
        minutes = explicit_minutes if explicit_minutes is not None else default_minutes
        if minutes > daily_minutes:
            _error("study_session_invalid", "Session duration exceeds the daily limit.", 400)
        now = timezone.now()
        if not _actionable(user, block, now):
            _error("study_session_block_unavailable", "Study block is unavailable.")
        existing = _replay_or_active(user, block_id, event_id, explicit_minutes, minutes)
        if existing is not None:
            return existing, False
        session = models.StudySession.objects.create(
            user=user, plan=plan, primary_block=block, block_id_at_start=block.id,
            client_event_id=event_id, planned_minutes=minutes, started_at=now,
        )
        return session, True


def start_session(user, block_id, event_id, explicit_minutes=None):
    for retry_index in range(len(_SQLITE_LOCK_RETRY_DELAYS) + 1):
        try:
            return _start_once(user, block_id, event_id, explicit_minutes)
        except IntegrityError as exc:
            if not _is_session_unique_error(exc):
                raise
            # The failed atomic attempt has rolled back; re-read committed owner state.
            default_minutes, _ = _minutes_limits(user)
            minutes = explicit_minutes if explicit_minutes is not None else default_minutes
            existing = _replay_or_active(user, block_id, event_id, explicit_minutes, minutes)
            if existing is not None:
                return existing, False
            raise
        except OperationalError as exc:
            if not _is_sqlite_lock(exc) or retry_index >= len(_SQLITE_LOCK_RETRY_DELAYS):
                raise
            time.sleep(_SQLITE_LOCK_RETRY_DELAYS[retry_index])
    raise AssertionError("unreachable")


def _end_session_once(user, session_id, target):
    with transaction.atomic():
        session = _session_query(user).select_for_update().filter(pk=session_id).first()
        if session is None:
            _error("study_session_not_found", "Study session not found.", 404)
        if session.status == target:
            return session
        if session.status != models.StudySession.Status.IN_PROGRESS:
            _error("study_session_transition_conflict", "Session has another terminal status.")
        now = timezone.now()
        end = max(now, session.started_at)
        session.status = target
        if target == models.StudySession.Status.COMPLETED:
            session.completed_at = end
        else:
            session.abandoned_at = end
        session.actual_seconds, _ = _elapsed(session.started_at, end)
        session.save(update_fields=(
            "status", "completed_at", "abandoned_at", "actual_seconds", "updated_at"
        ))
        return session


def _end_session(user, session_id, target):
    for retry_index in range(len(_SQLITE_LOCK_RETRY_DELAYS) + 1):
        try:
            return _end_session_once(user, session_id, target)
        except OperationalError as exc:
            if not _is_sqlite_lock(exc) or retry_index >= len(_SQLITE_LOCK_RETRY_DELAYS):
                raise
            time.sleep(_SQLITE_LOCK_RETRY_DELAYS[retry_index])
    raise AssertionError("unreachable")


def complete_session(user, session_id):
    return _end_session(user, session_id, models.StudySession.Status.COMPLETED)


def abandon_session(user, session_id):
    return _end_session(user, session_id, models.StudySession.Status.ABANDONED)
