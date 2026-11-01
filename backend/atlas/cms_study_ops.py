"""P15 read-only canonical operational counters; no per-learner diagnostics here."""
from django.db.models import Count
from django.utils import timezone
from rest_framework.response import Response

from .cms_policy import CMSFailure, policy_lock, require
from .cms_views import AdminAPIView
from .models import (
    RecommendationFeedback, StudyActivity, StudyBlock, StudyPlan, StudySession,
)


def _counts(model, field, valid):
    counts = dict(model.objects.order_by().values_list(field).annotate(count=Count("pk")))
    return {"total": sum(counts.values()),
            "by_status": {name: counts.get(name, 0) for name in valid}}


class StudyOperationsOverviewView(AdminAPIView):
    capability = "cms_study_view"

    def get(self, request):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_study_view")
            return Response({
                "scope": "aggregate_operational_counts",
                "as_of": timezone.now().isoformat(),
                "plans": _counts(StudyPlan, "status", StudyPlan.Status.values),
                "blocks": _counts(StudyBlock, "status", StudyBlock.Status.values),
                "sessions": _counts(StudySession, "status", StudySession.Status.values),
                "activities": _counts(StudyActivity, "activity_type", StudyActivity.Kind.values),
                "feedback": _counts(RecommendationFeedback, "value", RecommendationFeedback.Value.values),
                "mastery_inferred_from_session_completion": False,
                "notice": "COUNTS_ONLY; NO_PERSONAL_DATA; NO_LEARNING_EVIDENCE_GENERATED",
            })
