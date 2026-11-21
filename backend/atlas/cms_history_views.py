"""P09 bounded private chronology and citation-debt projections.

These views never change public timeline/search/graph or treat a historical
association as authorship, scientific support or publication eligibility.
"""
from django.db.models import Count, Q
from rest_framework.response import Response

from .cms_content import resolve
from .cms_content_models import ContentState
from .cms_policy import CMSFailure, policy_lock, require
from .cms_provenance import lineage_for_many, provenance_data
from .cms_views import AdminAPIView, page
from .models import Psychologist, Theory, TimelineEvent


def _id_year(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or len(value) > 4:
        raise CMSFailure("INVALID_QUERY", 400)
    result = int(value)
    if not 1 <= result <= 9999:
        raise CMSFailure("INVALID_QUERY", 400)
    return result


def _debt(qs):
    # The source record is not scientific evidence until resolved. Do not
    # create automatic approval or reinterpret legacy flags.
    return qs.annotate(source_count=Count("source_links", distinct=True),
        checked_count=Count("source_links", filter=Q(source_links__source__verification_status="source_checked"), distinct=True))


class HistoryChronologyView(AdminAPIView):
    capability = "cms_history_preview"

    def get(self, request):
        with policy_lock():
            require(request.user, "cms_history_view")
            params = request.query_params
            q = params.get("q", "").strip()
            precision = params.get("precision", "")
            weak = params.get("weak_only", "")
            first, last = _id_year(params.get("year_min")), _id_year(params.get("year_max"))
            if len(q) > 200 or weak not in {"", "1"} or precision not in {"", *TimelineEvent.DatePrecision.values} or (
                first is not None and last is not None and first > last):
                raise CMSFailure("INVALID_QUERY", 400)
            rows = _debt(TimelineEvent.objects.all())
            if q:
                rows = rows.filter(Q(title_en__icontains=q) | Q(title_fa__icontains=q) | Q(slug__icontains=q))
            if precision:
                rows = rows.filter(date_precision=precision)
            if first is not None:
                rows = rows.filter(Q(year_start__gte=first) | Q(year_start__isnull=True, exact_date__year__gte=first))
            if last is not None:
                rows = rows.filter(Q(year_start__lte=last) | Q(year_start__isnull=True, exact_date__year__lte=last))
            if weak:
                rows = rows.filter(checked_count=0)
            meta, selection = page(request, rows.order_by("year_start", "exact_date", "pk"),
                extra=("q", "precision", "weak_only", "year_min", "year_max"))
            ids = [item.pk for item in selection]
            status = {state.canonical_pk: {"status": state.current_revision.status, "id": str(state.pk)} for state in
                ContentState.objects.filter(kind="timeline-event", canonical_pk__in=ids).select_related("current_revision")
                if state.current_revision_id}
            origins = lineage_for_many(request.user, "timeline-event", ids)
            results = [{"id":row.pk, "slug":row.slug, "title_en":row.title_en, "title_fa":row.title_fa,
                "event_type":row.event_type,"date_precision":row.date_precision,
                "date_text":row.date_text,"year_start":row.year_start,"year_end":row.year_end,
                "exact_date":row.exact_date,"source_count":row.source_count,
                "checked_source_count":row.checked_count,
                "citation_debt":row.checked_count == 0,
                "revision_status":status.get(row.pk,{}).get("status","not_anchored"),
                "cms_state_id":status.get(row.pk,{}).get("id"),
                "origin":origins[row.pk]} for row in selection]
            return Response({**meta, "results":results,
                "scope":"private_canonical_history_metadata",
                "date_inference":"none; unknown and approximate precisions remain explicit",
                "notice":"PRIVATE_PREVIEW_ONLY; SOURCE_COUNTS_ARE_NOT_APPROVAL; PUBLIC_TIMELINE_UNCHANGED"})


class HistoryProvenanceView(AdminAPIView):
    capability = "cms_history_view"

    def get(self, request, kind, target_id):
        if request.query_params:
            raise CMSFailure("INVALID_QUERY", 400)
        with policy_lock():
            require(request.user, "cms_history_view")
            state, obj = resolve(request.user, kind, target_id)
            return Response(provenance_data(request.user, kind, state, obj))


class HistoryCitationDebtView(AdminAPIView):
    capability = "cms_history_view"

    def get(self, request):
        with policy_lock():
            kind = request.query_params.get("kind", "")
            if kind not in {"psychologist", "theory", "timeline-event"}:
                raise CMSFailure("INVALID_QUERY", 400)
            model = {"psychologist":Psychologist,"theory":Theory,"timeline-event":TimelineEvent}[kind]
            qs = _debt(model.objects.all()).filter(checked_count=0).order_by("pk")
            meta, rows = page(request, qs, extra=("kind",))
            ids = [row.pk for row in rows]
            state_ids = {state.canonical_pk:{"status":state.current_revision.status,"id":str(state.pk)} for state in
                ContentState.objects.filter(kind=kind, canonical_pk__in=ids).select_related("current_revision")
                if state.current_revision_id}
            result = [{"id":row.pk,
                "name":str(getattr(row, "title_en" if kind=="timeline-event" else "name_en")),
                "source_count":row.source_count,"checked_source_count":row.checked_count,
                "revision_status":state_ids.get(row.pk,{}).get("status","not_anchored"),
                "cms_state_id":state_ids.get(row.pk,{}).get("id"),
                "citation_debt":True,"auto_approval":False} for row in rows]
            return Response({**meta,"kind":kind,"results":result,
                "notice":"LEGACY_CITATION_DEBT_ONLY; NO_SCIENTIFIC_OR_RIGHTS_APPROVAL"})
