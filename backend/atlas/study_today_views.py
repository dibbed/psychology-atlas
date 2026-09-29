"""Authenticated HTTP boundary for Study Today."""

from django.utils import timezone
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .study_today import build_today


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def today(request):
    if request.query_params:
        return Response({
            "code": "study_today_invalid_query",
            "detail": "Unexpected query parameters.",
        }, status=400)
    return Response(build_today(request.user, timezone.now()))
