from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.db import transaction
from django.db.models import F, Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from . import models


MAX_PLAN_NOTES_LENGTH = 12_000
MAX_PLAN_SCOPES = 200

SCOPE_TARGETS = {
    "disorder": ("disorder", models.Disorder),
    "concept": ("concept", models.Concept),
    "therapy": ("therapy", models.Therapy),
    "theory": ("theory", models.Theory),
    "psychologist": ("psychologist", models.Psychologist),
    "timeline_event": ("timeline_event", models.TimelineEvent),
    "quiz": ("quiz", models.Quiz),
    "clinical_case": ("clinical_case", models.ClinicalCase),
}


class StudyPlanningError(Exception):
    def __init__(self, code: str, detail: str, *, status_code: int = 400, errors=None):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code
        self.errors = errors


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _reject_unknown_fields(payload, allowed):
    unknown = sorted(set(payload) - set(allowed))
    if unknown:
        raise StudyPlanningError(
            "study_plan_invalid",
            "فیلد ناشناخته در درخواست وجود دارد.",
            errors={"unknown_fields": unknown},
        )


def _require_text(value, *, field, max_length):
    if not isinstance(value, str):
        raise StudyPlanningError(
            "study_plan_invalid",
            "مقدار متنی نامعتبر است.",
            errors={field: "must_be_string"},
        )
    value = value.strip()
    if not value:
        raise StudyPlanningError(
            "study_plan_invalid",
            "این فیلد نمی‌تواند خالی باشد.",
            errors={field: "required"},
        )
    if len(value) > max_length:
        raise StudyPlanningError(
            "study_plan_invalid",
            "طول متن بیشتر از حد مجاز است.",
            errors={field: "too_long"},
        )
    return value


def _optional_notes(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise StudyPlanningError(
            "study_plan_invalid",
            "یادداشت برنامه باید متن باشد.",
            errors={"notes": "must_be_string"},
        )
    value = value.strip()
    if len(value) > MAX_PLAN_NOTES_LENGTH:
        raise StudyPlanningError(
            "study_plan_invalid",
            "یادداشت برنامه بیش از حد طولانی است.",
            errors={"notes": "too_long"},
        )
    return value


def _date_value(value, *, field, nullable=False):
    if value in (None, "") and nullable:
        return None
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise StudyPlanningError(
            "study_plan_invalid_date_range",
            "تاریخ برنامه نامعتبر است.",
            errors={field: "invalid_date"},
        )
    parsed = parse_date(value)
    if parsed is None:
        raise StudyPlanningError(
            "study_plan_invalid_date_range",
            "تاریخ برنامه باید با قالب YYYY-MM-DD ارسال شود.",
            errors={field: "invalid_date"},
        )
    return parsed


def _settings_timezone(value):
    if not isinstance(value, str):
        raise StudyPlanningError(
            "study_timezone_invalid",
            "منطقه زمانی باید یک نام معتبر IANA باشد.",
            errors={"study_timezone": "invalid_timezone"},
        )
    value = value.strip()
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise StudyPlanningError(
            "study_timezone_invalid",
            "منطقه زمانی باید یک نام معتبر IANA باشد.",
            errors={"study_timezone": "invalid_timezone"},
        )
    return value


def _bounded_int(value, *, field, minimum, maximum, code="study_plan_invalid"):
    if not _is_int(value) or value < minimum or value > maximum:
        raise StudyPlanningError(
            code,
            "مقدار عددی خارج از محدوده مجاز است.",
            errors={field: f"must_be_between_{minimum}_and_{maximum}"},
        )
    return value


def study_settings_for_user(user):
    obj, _ = models.UserStudySettings.objects.get_or_create(
        user=user,
        defaults={"study_timezone": settings.TIME_ZONE},
    )
    return obj


def study_settings_payload(obj):
    return {
        "study_timezone": obj.study_timezone,
        "default_daily_minutes": obj.default_daily_minutes,
        "default_session_minutes": obj.default_session_minutes,
        "week_starts_on": obj.week_starts_on,
        "created_at": obj.created_at.isoformat(),
        "updated_at": obj.updated_at.isoformat(),
    }


@transaction.atomic
def update_study_settings(user, payload):
    allowed = {
        "study_timezone",
        "default_daily_minutes",
        "default_session_minutes",
        "week_starts_on",
    }
    _reject_unknown_fields(payload, allowed)
    missing = sorted(allowed - set(payload))
    if missing:
        raise StudyPlanningError(
            "study_plan_invalid",
            "برای ذخیره تنظیمات، همه فیلدها را ارسال کن.",
            errors={"missing_fields": missing},
        )

    obj = study_settings_for_user(user)
    timezone_name = _settings_timezone(payload["study_timezone"])
    daily = _bounded_int(
        payload["default_daily_minutes"],
        field="default_daily_minutes",
        minimum=5,
        maximum=720,
    )
    session = _bounded_int(
        payload["default_session_minutes"],
        field="default_session_minutes",
        minimum=5,
        maximum=240,
    )
    week_start = _bounded_int(
        payload["week_starts_on"],
        field="week_starts_on",
        minimum=0,
        maximum=6,
    )
    if session > daily:
        raise StudyPlanningError(
            "study_plan_invalid",
            "مدت پیش‌فرض جلسه نمی‌تواند از ظرفیت روزانه بیشتر باشد.",
            errors={"default_session_minutes": "exceeds_daily_minutes"},
        )

    obj.study_timezone = timezone_name
    obj.default_daily_minutes = daily
    obj.default_session_minutes = session
    obj.week_starts_on = week_start
    obj.full_clean()
    obj.save()
    return obj


def local_date_for_user(user):
    settings_obj = study_settings_for_user(user)
    return timezone.now().astimezone(ZoneInfo(settings_obj.study_timezone)).date()


def _study_scope_queryset():
    return models.StudyPlanScope.objects.select_related(
        "disorder",
        "concept",
        "therapy",
        "therapy__family",
        "theory",
        "psychologist",
        "timeline_event",
        "quiz",
        "quiz__disorder",
        "clinical_case",
        "clinical_case__current_revision",
        "clinical_case__current_revision__primary_disorder",
        "clinical_case__current_revision__entry_step",
    ).order_by("sort_order", "id")


def _locked_user_plan(user, plan_id):
    if not _is_int(plan_id) or plan_id <= 0:
        raise StudyPlanningError("study_plan_not_found", "برنامه مطالعه پیدا نشد.", status_code=404)
    plan = (
        models.StudyPlan.objects.select_for_update()
        .filter(user=user, pk=plan_id)
        .first()
    )
    if plan is None:
        raise StudyPlanningError("study_plan_not_found", "برنامه مطالعه پیدا نشد.", status_code=404)
    return plan


def study_plan_queryset(user):
    return (
        models.StudyPlan.objects.filter(user=user)
        .prefetch_related("availability")
        .prefetch_related(
            Prefetch(
                "scopes",
                queryset=_study_scope_queryset(),
            )
        )
    )


def get_user_plan(user, plan_id):
    if not _is_int(plan_id) or plan_id <= 0:
        raise StudyPlanningError("study_plan_not_found", "برنامه مطالعه پیدا نشد.", status_code=404)
    plan = study_plan_queryset(user).filter(pk=plan_id).first()
    if plan is None:
        raise StudyPlanningError("study_plan_not_found", "برنامه مطالعه پیدا نشد.", status_code=404)
    return plan


def _scope_target(scope):
    for target_type, (field, _) in SCOPE_TARGETS.items():
        target = getattr(scope, field, None)
        if target is not None:
            return target_type, target
    return None, None


def _target_title(target_type, target):
    if target_type in {"disorder", "concept", "therapy", "theory", "psychologist"}:
        return getattr(target, "name_fa", "") or getattr(target, "name_en", "") or target.slug
    if target_type == "timeline_event":
        return target.title_fa or target.title_en or target.slug
    if target_type == "quiz":
        return target.title
    if target_type == "clinical_case":
        if target.current_revision_id and target.current_revision:
            return target.current_revision.title or target.title
        return target.title
    return getattr(target, "slug", "")


def _target_active(target_type, target):
    if target_type == "therapy":
        return bool(target.is_active and target.family_id and target.family.is_active)
    if target_type == "quiz":
        return bool(target.is_active and (target.disorder_id is None or target.disorder.is_active))
    if target_type == "clinical_case":
        revision = target.current_revision
        entry_step = revision.entry_step if revision is not None else None
        return bool(
            target.is_active
            and revision is not None
            and revision.case_id == target.id
            and revision.status == models.CaseRevision.Status.PUBLISHED
            and entry_step is not None
            and entry_step.is_active
            and entry_step.revision_id == revision.id
            and entry_step.case_id == target.id
            and (
                revision.primary_disorder_id is None
                or revision.primary_disorder.is_active
            )
        )
    return bool(getattr(target, "is_active", True))


def study_scope_payload(scope):
    target_type, target = _scope_target(scope)
    return {
        "id": scope.id,
        "target_type": target_type,
        "target_slug": target.slug if target is not None else None,
        "title": _target_title(target_type, target) if target is not None else "",
        "priority": scope.priority,
        "include_practice": scope.include_practice,
        "sort_order": scope.sort_order,
        "is_active": _target_active(target_type, target) if target is not None else False,
    }


def study_plan_payload(plan):
    availability = list(plan.availability.all())
    scopes = list(plan.scopes.all())
    weekly_minutes = sum(row.available_minutes for row in availability)
    return {
        "id": plan.id,
        "name": plan.name,
        "plan_kind": plan.plan_kind,
        "status": plan.status,
        "start_date": plan.start_date.isoformat(),
        "target_date": plan.target_date.isoformat() if plan.target_date else None,
        "notes": plan.notes,
        "generation_version": plan.generation_version,
        "last_generated_at": plan.last_generated_at.isoformat() if plan.last_generated_at else None,
        "archived_at": plan.archived_at.isoformat() if plan.archived_at else None,
        "completed_at": plan.completed_at.isoformat() if plan.completed_at else None,
        "weekly_available_minutes": weekly_minutes,
        "availability": [
            {
                "weekday": row.weekday,
                "available_minutes": row.available_minutes,
            }
            for row in sorted(availability, key=lambda item: item.weekday)
        ],
        "scopes": [study_scope_payload(scope) for scope in scopes],
        "created_at": plan.created_at.isoformat(),
        "updated_at": plan.updated_at.isoformat(),
    }


def _validate_plan_values(*, plan_kind, start_date, target_date):
    if plan_kind not in {value for value, _ in models.StudyPlan.Kind.choices}:
        raise StudyPlanningError(
            "study_plan_invalid",
            "نوع برنامه نامعتبر است.",
            errors={"plan_kind": "invalid_choice"},
        )
    if plan_kind == models.StudyPlan.Kind.EXAM and target_date is None:
        raise StudyPlanningError(
            "study_plan_invalid_date_range",
            "برای برنامه امتحان باید تاریخ هدف مشخص شود.",
            errors={"target_date": "required_for_exam"},
        )
    if target_date is not None and target_date < start_date:
        raise StudyPlanningError(
            "study_plan_invalid_date_range",
            "تاریخ هدف نمی‌تواند قبل از تاریخ شروع باشد.",
            errors={"target_date": "before_start_date"},
        )


@transaction.atomic
def create_study_plan(user, payload):
    allowed = {"name", "plan_kind", "start_date", "target_date", "notes"}
    _reject_unknown_fields(payload, allowed)

    name = _require_text(payload.get("name"), field="name", max_length=180)
    plan_kind = payload.get("plan_kind", models.StudyPlan.Kind.GENERAL)
    start = _date_value(payload.get("start_date") or local_date_for_user(user).isoformat(), field="start_date")
    target = _date_value(payload.get("target_date"), field="target_date", nullable=True)
    notes = _optional_notes(payload.get("notes", ""))
    _validate_plan_values(plan_kind=plan_kind, start_date=start, target_date=target)

    plan = models.StudyPlan(
        user=user,
        name=name,
        plan_kind=plan_kind,
        start_date=start,
        target_date=target,
        notes=notes,
        status=models.StudyPlan.Status.DRAFT,
    )
    plan.full_clean()
    plan.save()

    settings_obj = study_settings_for_user(user)
    models.StudyPlanAvailability.objects.bulk_create(
        [
            models.StudyPlanAvailability(
                plan=plan,
                weekday=weekday,
                available_minutes=settings_obj.default_daily_minutes,
            )
            for weekday in range(7)
        ]
    )
    return get_user_plan(user, plan.id)


@transaction.atomic
def update_study_plan(user, plan_id, payload):
    allowed = {"name", "plan_kind", "start_date", "target_date", "notes"}
    _reject_unknown_fields(payload, allowed)
    plan = _locked_user_plan(user, plan_id)
    if plan.status in {models.StudyPlan.Status.ARCHIVED, models.StudyPlan.Status.COMPLETED}:
        raise StudyPlanningError(
            "study_plan_archived" if plan.status == models.StudyPlan.Status.ARCHIVED else "study_plan_not_actionable",
            "این برنامه در وضعیت قابل ویرایش نیست.",
            status_code=409,
        )

    name = plan.name
    plan_kind = plan.plan_kind
    start = plan.start_date
    target = plan.target_date
    notes = plan.notes

    if "name" in payload:
        name = _require_text(payload["name"], field="name", max_length=180)
    if "plan_kind" in payload:
        plan_kind = payload["plan_kind"]
    if "start_date" in payload:
        start = _date_value(payload["start_date"], field="start_date")
    if "target_date" in payload:
        target = _date_value(payload["target_date"], field="target_date", nullable=True)
    if "notes" in payload:
        notes = _optional_notes(payload["notes"])

    _validate_plan_values(plan_kind=plan_kind, start_date=start, target_date=target)
    plan.name = name
    plan.plan_kind = plan_kind
    plan.start_date = start
    plan.target_date = target
    plan.notes = notes
    plan.full_clean()
    plan.save()
    return get_user_plan(user, plan.id)


def _editable_configuration_plan(user, plan_id):
    plan = _locked_user_plan(user, plan_id)
    if plan.status not in {models.StudyPlan.Status.DRAFT, models.StudyPlan.Status.PAUSED}:
        code = "study_plan_archived" if plan.status == models.StudyPlan.Status.ARCHIVED else "study_plan_not_actionable"
        raise StudyPlanningError(
            code,
            "برای تغییر دامنه یا زمان‌بندی، برنامه باید در حالت پیش‌نویس یا متوقف باشد.",
            status_code=409,
        )
    return plan


@transaction.atomic
def replace_plan_availability(user, plan_id, payload):
    _reject_unknown_fields(payload, {"availability"})
    plan = _editable_configuration_plan(user, plan_id)
    rows = payload.get("availability")
    if not isinstance(rows, list) or len(rows) != 7:
        raise StudyPlanningError(
            "study_plan_no_availability",
            "ظرفیت هفت روز هفته باید به‌طور کامل ارسال شود.",
            errors={"availability": "seven_days_required"},
        )

    parsed = {}
    for item in rows:
        if not isinstance(item, dict):
            raise StudyPlanningError(
                "study_plan_no_availability",
                "ساختار ظرفیت هفتگی نامعتبر است.",
                errors={"availability": "invalid_item"},
            )
        if set(item) != {"weekday", "available_minutes"}:
            raise StudyPlanningError(
                "study_plan_no_availability",
                "هر روز باید فقط weekday و available_minutes داشته باشد.",
                errors={"availability": "invalid_fields"},
            )
        weekday = _bounded_int(
            item["weekday"],
            field="weekday",
            minimum=0,
            maximum=6,
            code="study_plan_no_availability",
        )
        minutes = _bounded_int(
            item["available_minutes"],
            field="available_minutes",
            minimum=0,
            maximum=1440,
            code="study_plan_no_availability",
        )
        if weekday in parsed:
            raise StudyPlanningError(
                "study_plan_no_availability",
                "هر روز هفته فقط یک‌بار باید ارسال شود.",
                errors={"availability": "duplicate_weekday"},
            )
        parsed[weekday] = minutes

    if set(parsed) != set(range(7)):
        raise StudyPlanningError(
            "study_plan_no_availability",
            "ظرفیت همه روزهای هفته لازم است.",
            errors={"availability": "missing_weekday"},
        )

    for weekday, minutes in parsed.items():
        models.StudyPlanAvailability.objects.update_or_create(
            plan=plan,
            weekday=weekday,
            defaults={"available_minutes": minutes},
        )
    return get_user_plan(user, plan.id)


def study_scope_catalog(*, target_type, query="", limit=20):
    if target_type not in SCOPE_TARGETS:
        raise StudyPlanningError(
            "study_plan_scope_invalid",
            "نوع محتوای دامنه برنامه معتبر نیست.",
            errors={"target_type": "invalid_choice"},
        )
    limit = _bounded_int(
        limit,
        field="limit",
        minimum=1,
        maximum=50,
        code="study_plan_scope_invalid",
    )
    if not isinstance(query, str):
        raise StudyPlanningError(
            "study_plan_scope_invalid",
            "عبارت جست‌وجو نامعتبر است.",
            errors={"q": "must_be_string"},
        )
    query = query.strip()
    if len(query) > 200:
        raise StudyPlanningError(
            "study_plan_scope_invalid",
            "عبارت جست‌وجو بیش از حد طولانی است.",
            errors={"q": "too_long"},
        )
    qs = _active_scope_queryset(target_type)

    if query:
        if target_type in {"disorder", "concept", "therapy", "theory", "psychologist"}:
            fields = {
                "disorder": ("name_en", "name_fa", "slug", "short_description"),
                "concept": ("name_en", "name_fa", "slug", "simple_definition"),
                "therapy": ("name_en", "name_fa", "slug", "summary"),
                "theory": ("name_en", "name_fa", "slug", "summary_en", "summary_fa"),
                "psychologist": ("name_en", "name_fa", "slug", "summary_en", "summary_fa"),
            }[target_type]
            predicate = Q()
            for field in fields:
                predicate |= Q(**{f"{field}__icontains": query})
            qs = qs.filter(predicate)
        elif target_type == "timeline_event":
            qs = qs.filter(
                Q(title_en__icontains=query)
                | Q(title_fa__icontains=query)
                | Q(slug__icontains=query)
                | Q(date_text__icontains=query)
            )
        elif target_type == "quiz":
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(slug__icontains=query)
                | Q(description__icontains=query)
            )
        elif target_type == "clinical_case":
            qs = qs.filter(
                Q(title__icontains=query)
                | Q(slug__icontains=query)
                | Q(current_revision__title__icontains=query)
                | Q(current_revision__patient_summary__icontains=query)
            )

    order_field = "year_start" if target_type == "timeline_event" else (
        "title" if target_type in {"quiz", "clinical_case"} else "name_en"
    )
    rows = list(qs.distinct().order_by(order_field, "id")[:limit])
    items = []
    for target in rows:
        subtitle = ""
        if target_type == "disorder":
            subtitle = target.category.name_fa or target.category.name_en
        elif target_type == "concept":
            subtitle = target.get_kind_display()
        elif target_type == "therapy":
            subtitle = target.family.name_fa or target.family.name_en
        elif target_type == "theory":
            subtitle = target.domain
        elif target_type == "psychologist":
            subtitle = target.role_fa or target.role_en
        elif target_type == "timeline_event":
            subtitle = target.date_text
        elif target_type == "quiz" and target.disorder_id:
            subtitle = target.disorder.name_fa or target.disorder.name_en
        elif target_type == "clinical_case":
            subtitle = target.get_difficulty_display()

        items.append(
            {
                "target_type": target_type,
                "target_slug": target.slug,
                "title": _target_title(target_type, target),
                "subtitle": subtitle,
            }
        )
    return items


def _active_scope_queryset(target_type):
    _, model = SCOPE_TARGETS[target_type]
    qs = model.objects.all()
    if target_type == "disorder":
        return qs.filter(is_active=True).select_related("category")
    if target_type in {"concept", "theory", "psychologist", "timeline_event"}:
        return qs.filter(is_active=True)
    if target_type == "therapy":
        return qs.filter(is_active=True, family__is_active=True).select_related("family")
    if target_type == "quiz":
        return qs.filter(is_active=True).filter(
            Q(disorder__isnull=True) | Q(disorder__is_active=True)
        ).select_related("disorder")
    if target_type == "clinical_case":
        return (
            qs.filter(
                is_active=True,
                current_revision__isnull=False,
                current_revision__case_id=F("id"),
                current_revision__status=models.CaseRevision.Status.PUBLISHED,
                current_revision__entry_step__isnull=False,
                current_revision__entry_step__is_active=True,
                current_revision__entry_step__revision_id=F("current_revision_id"),
                current_revision__entry_step__case_id=F("id"),
            )
            .filter(
                Q(current_revision__primary_disorder__isnull=True)
                | Q(current_revision__primary_disorder__is_active=True)
            )
            .select_related(
                "current_revision",
                "current_revision__primary_disorder",
                "current_revision__entry_step",
            )
        )
    return qs.none()


@transaction.atomic
def replace_plan_scopes(user, plan_id, payload):
    _reject_unknown_fields(payload, {"scopes"})
    plan = _editable_configuration_plan(user, plan_id)
    rows = payload.get("scopes")
    if not isinstance(rows, list):
        raise StudyPlanningError(
            "study_plan_scope_invalid",
            "دامنه برنامه باید به‌صورت فهرست ارسال شود.",
            errors={"scopes": "must_be_list"},
        )
    if len(rows) > MAX_PLAN_SCOPES:
        raise StudyPlanningError(
            "study_plan_scope_invalid",
            "تعداد موارد انتخاب‌شده بیش از حد مجاز است.",
            errors={"scopes": "too_many_items"},
        )

    normalized = []
    slugs_by_type = {target_type: set() for target_type in SCOPE_TARGETS}
    seen = set()

    for index, item in enumerate(rows):
        if not isinstance(item, dict):
            raise StudyPlanningError(
                "study_plan_scope_invalid",
                "ساختار دامنه برنامه نامعتبر است.",
                errors={"scopes": f"invalid_item_{index}"},
            )

        allowed = {"target_type", "target_slug", "priority", "include_practice", "sort_order"}
        unknown = set(item) - allowed
        if unknown:
            raise StudyPlanningError(
                "study_plan_scope_invalid",
                "فیلد ناشناخته در دامنه برنامه وجود دارد.",
                errors={"scopes": {"index": index, "unknown_fields": sorted(unknown)}},
            )

        target_type = item.get("target_type")
        slug = item.get("target_slug")
        if target_type not in SCOPE_TARGETS or not isinstance(slug, str) or not slug.strip():
            raise StudyPlanningError(
                "study_plan_scope_invalid",
                "نوع یا شناسه محتوای انتخاب‌شده نامعتبر است.",
                errors={"scopes": {"index": index, "target": "invalid"}},
            )

        slug = slug.strip()
        key = (target_type, slug)
        if key in seen:
            raise StudyPlanningError(
                "study_plan_scope_duplicate",
                "یک محتوای تکراری در دامنه برنامه وجود دارد.",
                errors={"scopes": {"index": index, "target": key}},
            )
        seen.add(key)

        priority = _bounded_int(
            item.get("priority", 3),
            field="priority",
            minimum=1,
            maximum=5,
            code="study_plan_scope_invalid",
        )
        include_practice = item.get("include_practice", True)
        if not isinstance(include_practice, bool):
            raise StudyPlanningError(
                "study_plan_scope_invalid",
                "include_practice باید مقدار بولی باشد.",
                errors={"scopes": {"index": index, "include_practice": "must_be_boolean"}},
            )

        sort_order = item.get("sort_order", index)
        if not _is_int(sort_order) or sort_order < 0 or sort_order > 1_000_000:
            raise StudyPlanningError(
                "study_plan_scope_invalid",
                "ترتیب دامنه نامعتبر است.",
                errors={"scopes": {"index": index, "sort_order": "invalid"}},
            )

        normalized.append(
            {
                "index": index,
                "target_type": target_type,
                "slug": slug,
                "priority": priority,
                "include_practice": include_practice,
                "sort_order": sort_order,
            }
        )
        slugs_by_type[target_type].add(slug)

    target_maps = {}
    for target_type, slugs in slugs_by_type.items():
        if not slugs:
            continue
        target_maps[target_type] = (
            _active_scope_queryset(target_type)
            .filter(slug__in=slugs)
            .in_bulk(field_name="slug")
        )

    resolved = []
    for row in normalized:
        target = target_maps.get(row["target_type"], {}).get(row["slug"])
        if target is None:
            raise StudyPlanningError(
                "study_plan_scope_invalid",
                "محتوای انتخاب‌شده وجود ندارد یا غیرفعال است.",
                errors={"scopes": {"index": row["index"], "target": "not_found_or_inactive"}},
            )

        field, _ = SCOPE_TARGETS[row["target_type"]]
        scope = models.StudyPlanScope(
            plan=plan,
            priority=row["priority"],
            include_practice=row["include_practice"],
            sort_order=row["sort_order"],
            **{field: target},
        )
        scope.clean()
        resolved.append(scope)

    plan.scopes.all().delete()
    if resolved:
        models.StudyPlanScope.objects.bulk_create(resolved)
    return get_user_plan(user, plan.id)


@transaction.atomic
def transition_study_plan(user, plan_id, action):
    plan = _locked_user_plan(user, plan_id)

    if action == "archive":
        if plan.status != models.StudyPlan.Status.ARCHIVED:
            plan.status = models.StudyPlan.Status.ARCHIVED
            plan.archived_at = timezone.now()
            plan.save(update_fields=("status", "archived_at", "updated_at"))
        return get_user_plan(user, plan.id)

    if plan.status == models.StudyPlan.Status.ARCHIVED:
        raise StudyPlanningError(
            "study_plan_archived",
            "برنامه بایگانی‌شده قابل فعال‌سازی یا توقف نیست.",
            status_code=409,
        )
    if plan.status == models.StudyPlan.Status.COMPLETED:
        raise StudyPlanningError(
            "study_plan_not_actionable",
            "برنامه تکمیل‌شده بدون اقدام صریح جدید دوباره فعال نمی‌شود.",
            status_code=409,
        )

    if action == "pause":
        if plan.status == models.StudyPlan.Status.PAUSED:
            return get_user_plan(user, plan.id)
        if plan.status != models.StudyPlan.Status.ACTIVE:
            raise StudyPlanningError(
                "study_plan_not_actionable",
                "فقط برنامه فعال را می‌توان متوقف کرد.",
                status_code=409,
            )
        plan.status = models.StudyPlan.Status.PAUSED
        plan.save(update_fields=("status", "updated_at"))
        return get_user_plan(user, plan.id)

    if action == "activate":
        if plan.status == models.StudyPlan.Status.ACTIVE:
            return get_user_plan(user, plan.id)
        if plan.status not in {models.StudyPlan.Status.DRAFT, models.StudyPlan.Status.PAUSED}:
            raise StudyPlanningError(
                "study_plan_not_actionable",
                "این برنامه در وضعیت قابل فعال‌سازی نیست.",
                status_code=409,
            )
        scopes = list(_study_scope_queryset().filter(plan=plan))
        if not scopes:
            raise StudyPlanningError(
                "study_plan_scope_invalid",
                "برای فعال‌سازی حداقل یک موضوع به برنامه اضافه کن.",
                status_code=409,
            )
        for scope in scopes:
            target_type, target = _scope_target(scope)
            if target is None or not _target_active(target_type, target):
                raise StudyPlanningError(
                    "study_plan_scope_invalid",
                    "یکی از موضوع‌های برنامه دیگر فعال یا قابل اجرا نیست.",
                    status_code=409,
                )

        availability = list(
            plan.availability.order_by("weekday").values_list("weekday", "available_minutes")
        )
        if len(availability) != 7 or {weekday for weekday, _ in availability} != set(range(7)):
            raise StudyPlanningError(
                "study_plan_no_availability",
                "ظرفیت هفت روز هفته کامل نیست.",
                status_code=409,
            )
        if not any(minutes > 0 for _, minutes in availability):
            raise StudyPlanningError(
                "study_plan_no_availability",
                "برای فعال‌سازی حداقل یک روز با زمان مطالعه لازم است.",
                status_code=409,
            )
        plan.status = models.StudyPlan.Status.ACTIVE
        plan.save(update_fields=("status", "updated_at"))
        return get_user_plan(user, plan.id)

    raise StudyPlanningError(
        "study_plan_not_actionable",
        "عملیات برنامه مطالعه شناخته‌شده نیست.",
        status_code=400,
    )
