"""Authenticated, owner-scoped HTTP boundary for Recommendation V2."""

import json
import re
import time
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import RequestDataTooBig
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.utils import timezone
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import RecommendationFeedback
from .recommendations_v2 import build_candidates


KEY_PATTERN = re.compile(r"^r2_[0-9a-f]{64}$", re.ASCII)
LIMIT_PATTERN = re.compile(r"^[0-9]+$", re.ASCII)
VALUES = {"helpful", "not_helpful", "dismissed"}
MAX_BODY_BYTES = 1024


def _error(code, detail, http_status):
    return Response({"code": code, "detail": detail}, status=http_status)


def _feedback_payload(row, now):
    if row is None or (row.value == "dismissed" and row.suppressed_until <= now):
        return {"value": None, "suppressed_until": None}
    return {
        "value": row.value,
        "suppressed_until": row.suppressed_until.isoformat() if row.suppressed_until else None,
    }


def _latest_by_key(user, keys):
    rows = RecommendationFeedback.objects.filter(
        user=user, recommendation_key__in=keys
    ).annotate(
        latest_rank=Window(
            expression=RowNumber(),
            partition_by=[F("recommendation_key")],
            order_by=[F("created_at").desc(), F("id").desc()],
        )
    ).filter(latest_rank=1)
    return {row.recommendation_key: row for row in rows}


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def recommendations(request):
    params = request.query_params
    if set(params) - {"limit"} or len(params.getlist("limit")) > 1:
        return _error("recommendation_invalid_query", "Invalid recommendation query.", 400)
    raw_limit = params.get("limit", "8")
    if not isinstance(raw_limit, str) or len(raw_limit) > 4 or not LIMIT_PATTERN.fullmatch(raw_limit):
        return _error("recommendation_invalid_query", "Invalid recommendation query.", 400)
    limit = int(raw_limit)
    if not 1 <= limit <= 20:
        return _error("recommendation_invalid_query", "Invalid recommendation query.", 400)

    now = timezone.now()
    candidates, truncated = build_candidates(request.user, now)
    latest = _latest_by_key(request.user, [item["key"] for item in candidates])
    items = []
    suppressed_count = 0
    for candidate in candidates:
        feedback = _feedback_payload(latest.get(candidate["key"]), now)
        if feedback["value"] == "dismissed":
            suppressed_count += 1
            continue
        if len(items) < limit:
            item = {key: value for key, value in candidate.items() if key not in {"context_ref", "_sort"}}
            item["feedback"] = feedback
            item["order"] = len(items) + 1
            items.append(item)
    return Response({
        "version": "v2",
        "as_of": now.isoformat(),
        "items": items,
        "returned_count": len(items),
        "suppressed_count": suppressed_count,
        "truncated_sources": truncated,
    })


def _parse_feedback(request, key):
    if not KEY_PATTERN.fullmatch(key):
        return None
    try:
        raw = request._request.body
    except RequestDataTooBig:
        return None
    if len(raw) > MAX_BODY_BYTES:
        return None
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or set(data) != {"value", "client_event_id"}:
        return None
    if not isinstance(data["value"], str) or data["value"] not in VALUES or not isinstance(data["client_event_id"], str):
        return None
    try:
        event_id = uuid.UUID(data["client_event_id"])
    except (ValueError, AttributeError):
        return None
    if str(event_id) != data["client_event_id"].lower():
        return None
    return data["value"], event_id


def _action_response(row):
    return Response({
        "key": row.recommendation_key,
        "feedback": {
            "value": row.value,
            "suppressed_until": row.suppressed_until.isoformat() if row.suppressed_until else None,
        },
        "recorded_at": row.created_at.isoformat(),
    })


def _record_feedback(user, key, value, event_id, now):
    # The owner row is a portable lock on PostgreSQL. SQLite's IMMEDIATE
    # transactions serialize writers before the first read.
    with transaction.atomic():
        get_user_model().objects.select_for_update().only("id").get(pk=user.pk)
        replay = RecommendationFeedback.objects.filter(user=user, client_event_id=event_id).first()
        if replay:
            if replay.recommendation_key != key or replay.value != value:
                return _error("recommendation_feedback_conflict", "Feedback event already used.", 409)
            return _action_response(replay)

        candidates, _ = build_candidates(user, now)
        candidate = next((item for item in candidates if item["key"] == key), None)
        if candidate is None:
            return _error("recommendation_not_found", "Recommendation not found.", 404)

        latest = RecommendationFeedback.objects.filter(
            user=user, recommendation_key=key
        ).order_by("-created_at", "-id").first()
        if latest and latest.value == value and (
            value != "dismissed" or latest.suppressed_until > now
        ):
            return _action_response(latest)

        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if RecommendationFeedback.objects.filter(user=user, created_at__gte=day_start).count() >= 100:
            return _error("recommendation_feedback_limit", "Daily feedback limit reached.", 429)
        row = RecommendationFeedback.objects.create(
            user=user,
            recommendation_key=key,
            recommendation_type=candidate["type"],
            target_type=candidate["target"]["type"],
            target_id=candidate["target"]["id"],
            reason_code=candidate["reason_codes"][0],
            context_ref=candidate["context_ref"],
            value=value,
            client_event_id=event_id,
            suppressed_until=now + timedelta(days=7) if value == "dismissed" else None,
            created_at=now,
        )
        return _action_response(row)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def recommendation_feedback(request, key):
    parsed = _parse_feedback(request, key)
    if parsed is None:
        return _error("recommendation_feedback_invalid", "Invalid feedback payload.", 400)
    value, event_id = parsed
    now = timezone.now()
    for attempt in range(3):
        try:
            return _record_feedback(request.user, key, value, event_id, now)
        except OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 2:
                raise
            time.sleep(0.05 * (attempt + 1))
        except IntegrityError:
            # A concurrent submission may have committed the unique event ID.
            row = RecommendationFeedback.objects.filter(
                user=request.user, client_event_id=event_id
            ).first()
            if row:
                if row.recommendation_key == key and row.value == value:
                    return _action_response(row)
                return _error("recommendation_feedback_conflict", "Feedback event already used.", 409)
            raise
