"""Strict HTTP boundary for StudySession."""

import uuid

from django.core.exceptions import RequestDataTooBig
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ParseError, UnsupportedMediaType
from rest_framework.response import Response

from .study_sessions import (
    StudySessionError, abandon_session, complete_session, get_current_session,
    get_session, serialize_session, start_session,
)


def _invalid(detail="Invalid study session request.", errors=None):
    raise StudySessionError("study_session_invalid", detail, 400, errors)


def _query(request):
    if request.query_params:
        raise StudySessionError("study_session_invalid_query", "Unexpected query parameters.", 400)


def _body(request, *, start=False):
    try:
        raw = request._request.body
    except RequestDataTooBig:
        _invalid("Request body is too large.")
    if len(raw) > 1024:
        _invalid("Request body is too large.")
    if not raw and not start:
        return {}
    if request.content_type != "application/json":
        _invalid("Expected a JSON object.")
    try:
        payload = request.data
    except (ParseError, UnsupportedMediaType):
        _invalid("Malformed JSON object.")
    if not isinstance(payload, dict):
        _invalid("Expected a JSON object.")
    allowed = {"primary_block_id", "client_event_id", "planned_minutes"} if start else set()
    if set(payload) - allowed:
        _invalid("Unexpected fields.", {"unknown_fields": sorted(set(payload) - allowed)})
    if not start:
        return payload
    missing = {"primary_block_id", "client_event_id"} - set(payload)
    if missing:
        _invalid("Required fields are missing.", {"missing_fields": sorted(missing)})
    block_id = payload["primary_block_id"]
    if type(block_id) is not int or block_id <= 0:
        _invalid("Invalid primary block ID.", {"primary_block_id": "positive_integer_required"})
    token = payload["client_event_id"]
    if not isinstance(token, str):
        _invalid("Invalid client event ID.", {"client_event_id": "uuid_required"})
    try:
        event_id = uuid.UUID(token)
    except (ValueError, AttributeError):
        _invalid("Invalid client event ID.", {"client_event_id": "uuid_required"})
    minutes = payload.get("planned_minutes")
    if "planned_minutes" in payload and (
        type(minutes) is not int or not 5 <= minutes <= 240
    ):
        _invalid("Invalid planned minutes.", {"planned_minutes": "must_be_between_5_and_240"})
    return block_id, event_id, minutes


def _response_error(exc):
    result = {"code": exc.code, "detail": exc.detail}
    if exc.errors is not None:
        result["errors"] = exc.errors
    return Response(result, status=exc.status_code)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def sessions(request):
    try:
        _query(request)
        block_id, event_id, minutes = _body(request, start=True)
        session, created = start_session(request.user, block_id, event_id, minutes)
        return Response(
            {"session": serialize_session(request.user, session), "created": created},
            status=201 if created else 200,
        )
    except StudySessionError as exc:
        return _response_error(exc)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def current_session(request):
    try:
        _query(request)
        session = get_current_session(request.user)
        return Response({"session": serialize_session(request.user, session) if session else None})
    except StudySessionError as exc:
        return _response_error(exc)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def session_detail(request, session_id):
    try:
        _query(request)
        return Response({"session": serialize_session(request.user, get_session(request.user, session_id))})
    except StudySessionError as exc:
        return _response_error(exc)


def _transition(request, session_id, operation):
    try:
        _query(request)
        _body(request)
        session = operation(request.user, session_id)
        return Response({"session": serialize_session(request.user, session)})
    except StudySessionError as exc:
        return _response_error(exc)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def session_complete(request, session_id):
    return _transition(request, session_id, complete_session)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def session_abandon(request, session_id):
    return _transition(request, session_id, abandon_session)
