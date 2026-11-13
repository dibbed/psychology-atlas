"""P16 draft-only Learning content fingerprints, not publication manifests.

Capture every bounded child (including inactive answer keys), explicit
dependency identities/current availability, and the parent itself. Nothing
from this snapshot authorizes publishing or upgrades scientific review.
"""
import hashlib
import json

from django.core.serializers.json import DjangoJSONEncoder

from . import models
from .cms_policy import CMSFailure
from .cms_public_rights import scope_visible


KIND_MODELS = {
    "quiz": models.Quiz,
    "flashcard": models.Flashcard,
    "daily_challenge": models.DailyChallenge,
    "distortion_practice": models.CognitiveDistortionPracticeItem,
}
PARENT_FIELDS = {
    "quiz": ("id", "slug", "title", "description", "disorder_id", "archived_at",
             "is_active", "seed_managed", "updated_at"),
    "flashcard": ("id", "slug", "front", "back", "hint", "difficulty", "concept_id",
                  "disorder_id", "archived_at", "is_active", "seed_managed", "updated_at"),
    "daily_challenge": ("id", "prompt", "explanation", "concept_id", "disorder_id",
                        "sort_order", "archived_at", "is_active", "seed_managed", "updated_at"),
    "distortion_practice": ("id", "slug", "prompt", "explanation", "difficulty",
                            "target_concept_id", "sort_order", "archived_at",
                            "is_active", "seed_managed", "updated_at"),
}
MAX_QUESTIONS = 100
MAX_CHOICES = 1000


def _fields(row, names):
    return {field: getattr(row, field) for field in names}


def _choices(rows, fields, *, limit):
    data = list(rows.order_by("sort_order", "pk").values(*fields)[:limit + 1])
    if len(data) > limit:
        raise CMSFailure("PREVIEW_LIMIT", 409)
    return data


def _dependencies(kind, item, children):
    ids = {"disorder": set(), "concept": set()}
    for name in ("disorder_id", "concept_id", "target_concept_id"):
        identifier = getattr(item, name, None)
        if identifier is not None:
            ids["concept" if name != "disorder_id" else "disorder"].add(identifier)
    if kind == "distortion_practice":
        ids["concept"].update(choice["concept_id"] for choice in children if choice["concept_id"])
    return {name: sorted(values) for name, values in ids.items() if values}


def _dependency_snapshot(dependency_ids):
    result, issues = {}, []
    for name, klass in (("concept", models.Concept), ("disorder", models.Disorder)):
        identifiers = dependency_ids.get(name, [])
        if not identifiers:
            continue
        rows = list(klass.objects.filter(pk__in=identifiers).order_by("pk").values(
            "id", "is_active", "updated_at"))
        result[name] = rows
        if len(rows) != len(identifiers):
            issues.append("DEPENDENCY_MISSING")
        if any(not row["is_active"] for row in rows):
            issues.append("INACTIVE_DEPENDENCY")
        if any(not scope_visible(name, row["id"]) for row in rows):
            issues.append("DEPENDENCY_PUBLIC_UNAVAILABLE")
    return result, issues


def draft_fingerprint(kind, item):
    """Return a closed, read-only preflight snapshot with no educational text."""
    if kind not in KIND_MODELS or not isinstance(item, KIND_MODELS[kind]):
        raise CMSFailure("INVALID_KIND", 400)
    issues = []
    if kind in {"quiz", "flashcard"} and any(
        not scope_visible(kind, item.pk, material) for material in ("metadata", "item")
    ):
        issues.append("CONTENT_PUBLIC_UNAVAILABLE")
    parent = _fields(item, PARENT_FIELDS[kind])
    children = []

    if kind == "quiz":
        questions = list(item.questions.order_by("sort_order", "pk").values(
            "id", "prompt", "explanation", "is_active", "sort_order", "updated_at")[:MAX_QUESTIONS + 1])
        if len(questions) > MAX_QUESTIONS:
            raise CMSFailure("PREVIEW_LIMIT", 409)
        if not item.title.strip():
            issues.append("TITLE_MISSING")
        if not any(question["is_active"] for question in questions):
            issues.append("NO_ACTIVE_QUESTIONS")
        question_ids = [question["id"] for question in questions]
        all_choices = list(models.QuizChoice.objects.filter(
            question_id__in=question_ids,
        ).order_by("question_id", "sort_order", "pk").values(
            "id", "question_id", "text", "is_correct", "is_active", "sort_order",
        )[:MAX_CHOICES + 1])
        if len(all_choices) > MAX_CHOICES:
            raise CMSFailure("PREVIEW_LIMIT", 409)
        by_question = {identifier: [] for identifier in question_ids}
        for choice in all_choices:
            by_question[choice["question_id"]].append(choice)
        for question in questions:
            choices = by_question[question["id"]]
            if len(choices) > 10:
                raise CMSFailure("PREVIEW_LIMIT", 409)
            children.append({"question": question, "choices": choices})
            if question["is_active"]:
                active = [choice for choice in choices if choice["is_active"]]
                if any(not choice["text"].strip() for choice in active):
                    issues.append("CHOICE_TEXT_MISSING")
                if not question["prompt"].strip() or not 2 <= len(active) <= 10:
                    issues.append("QUESTION_INVALID")
                if sum(bool(choice["is_correct"]) for choice in active) != 1:
                    issues.append("QUIZ_ANSWER_KEY_INVALID")
    elif kind == "flashcard":
        if not item.front.strip() or not item.back.strip():
            issues.append("CONTENT_MISSING")
        if item.difficulty not in models.Flashcard.Difficulty.values:
            issues.append("DIFFICULTY_INVALID")
    elif kind == "daily_challenge":
        children = _choices(item.choices.all(),
                            ("id", "text", "is_correct", "is_active", "sort_order"), limit=20)
        active = [choice for choice in children if choice["is_active"]]
        if any(not choice["text"].strip() for choice in active):
            issues.append("CHOICE_TEXT_MISSING")
        if not item.prompt.strip():
            issues.append("CONTENT_MISSING")
        if not 2 <= len(active) <= 10:
            issues.append("CHOICES_INSUFFICIENT")
        if sum(bool(choice["is_correct"]) for choice in active) != 1:
            issues.append("ANSWER_KEY_INVALID")
    else:
        children = _choices(item.choices.all(),
                            ("id", "concept_id", "text", "is_correct", "is_active", "sort_order"), limit=20)
        active = [choice for choice in children if choice["is_active"]]
        if any(not choice["text"].strip() for choice in active):
            issues.append("CHOICE_TEXT_MISSING")
        if not item.prompt.strip() or not item.explanation.strip():
            issues.append("CONTENT_MISSING")
        if not 2 <= len(active) <= 10:
            issues.append("CHOICES_INSUFFICIENT")
        if sum(bool(choice["is_correct"]) for choice in active) != 1 or any(
            choice["is_correct"] and choice["concept_id"] != item.target_concept_id
            for choice in active
        ):
            issues.append("ANSWER_KEY_INVALID")
        if item.target_concept.subtype != models.Concept.Subtype.COGNITIVE_DISTORTION:
            issues.append("TARGET_INVALID")

    dependency_ids = _dependencies(kind, item, children)
    if not dependency_ids:
        issues.append("TARGET_REQUIRED")
    dependency_state, dependency_issues = _dependency_snapshot(dependency_ids)
    issues.extend(dependency_issues)
    document = {
        "schema": "learning-draft-preflight-v1",
        "kind": kind, "parent": parent, "children": children,
        "dependencies": dependency_state,
    }
    digest = hashlib.sha256(json.dumps(
        document, ensure_ascii=False, sort_keys=True, allow_nan=False,
        separators=(",", ":"), cls=DjangoJSONEncoder,
    ).encode("utf-8")).hexdigest()
    return {"content_digest": digest, "fingerprint_version": document["schema"],
            "dependency_ids": dependency_ids, "content_issues": sorted(set(issues))}
