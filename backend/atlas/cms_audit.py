"""Closed, payload-free audit metadata shared by CMS writers."""
import uuid

from django.db import DatabaseError, connection, transaction
from django.http import JsonResponse
from django.utils.crypto import salted_hmac


ACTIONS = frozenset({
    "session.login", "session.logout", "session.step_up", "session.revoke", "account.revoke",
    "roles.user", "roles.group", "roles.create_group", "roles.delete_group",
    "mfa.enroll", "mfa.recovery_codes", "mfa.revoke", "mfa.offline_owner_recovery",
    "api.security_denial", "api.failure", "revision.created", "revision.discarded",
    "review.submitted", "review.assigned", "review.decided", "review.reopened", "review.invalidated", "review.policy",
    "source.preview", "source.created", "source.updated", "source.archived", "source.deleted",
    "source.merged", "source.split", "source.successor",
})
ACTIONS |= frozenset({"artifact.upload", "artifact.validate", "artifact.revoke", "artifact.download",
    "artifact.cleanup",
    "research.intake", "research.raw", "research.decision", "job.enqueued", "job.claimed", "job.reconciled",
    "job.succeeded", "job.failed", "job.cancelled", "job.cancel_requested", "job.retried"})
CONTENT_REASONS = frozenset({"DRAFT_CREATION", "CONTENT_UPDATE", "EDITORIAL_CORRECTION"})
REVIEW_REASONS = frozenset({"EVIDENCE_INSUFFICIENT", "LOCATOR_INVALID", "CLAIM_UNSUPPORTED", "CORRECTION_REQUIRED"})
POLICY_REASONS = frozenset({"TEAM_POLICY", "SENSITIVE_DOMAIN", "OWNER_OPERATION"})
REASONS = CONTENT_REASONS | REVIEW_REASONS | POLICY_REASONS | frozenset({"", "DRAFT_DISCARD", "REVIEW_SUBMIT", "REVIEW_ASSIGN", "SOURCE_VERIFIED", "SCIENCE_VERIFIED", "REVIEW_REOPEN", "DEPENDENCY_CHANGED", "POLICY_CHANGED", "PAYLOAD_CHANGED",
    "SOURCE_CREATE", "SOURCE_UPDATE", "SOURCE_ARCHIVE", "SOURCE_DELETE", "SOURCE_MERGE", "SOURCE_SPLIT", "SOURCE_SUCCESSOR"})
REASONS |= frozenset({"RIGHTS_SCOPE_VERIFIED", "TERMINOLOGY_SELECTED"})
REASONS |= frozenset({"ARTIFACT_UPLOAD", "ARTIFACT_VALIDATE", "ARTIFACT_REVOKE", "ARTIFACT_DOWNLOAD",
    "ARTIFACT_CLEANUP",
    "RESEARCH_INTAKE", "RESEARCH_RAW", "RESEARCH_MAP", "RESEARCH_REJECT", "RESEARCH_DEFER", "RESEARCH_STAGE", "JOB_OPERATION"})
SAFE_FIELDS = frozenset({
    "name_en", "name_fa", "description", "short_description", "overview",
    "permissions", "groups", "is_active", "is_staff", "is_superuser",
    "mode",
    "title", "organization", "citation", "url", "publication_year", "source_type", "authors", "doi", "pmid",
    "verification_status", "resource_version",
})
SAFE_FIELDS |= frozenset({
    "academic_definition", "alias_type", "assessment", "assessment_overview", "assessment_tools", "category",
    "chapter_name_en", "chapter_name_fa", "chapter_number", "classification_status", "clinical_features", "clinical_note",
    "coding", "common_confusions", "comorbidity", "concept", "context_considerations", "copyright_note", "corpus",
    "counterexample", "course", "course_note", "cultural_note", "differential", "disorder", "display_type", "domain",
    "exam_tip", "example", "explanation", "group_name", "health_check", "homonym_info", "intent", "key", "key_features",
    "kind", "language", "linked_disorder", "management", "master_id", "metadata", "nearby_titles", "note", "official_status",
    "official_updates", "parent", "periodic_review", "pitfalls", "prevalence_numeric", "prevalence_policy", "prominence",
    "purpose", "quality", "quality_audit", "recognition_cues", "red_flags", "related_disorder", "relationship",
    "relationship_type", "release_updates", "risk_factors", "role", "root_section", "self_test", "simple_definition",
    "slug", "sort_index", "sort_order", "source", "source_concept", "source_keys", "source_registry", "specialization_level",
    "stats", "structural_path", "study_guide", "subtype", "summary", "symptom", "target", "target_concept", "text",
    "treatment_overview", "typical_onset", "urgent_warnings", "version_date", "version_name",
})
SAFE_FIELDS |= frozenset({"family", "classification", "clinical_role", "evidence_basis", "evidence_note", "historical_context", "core_principles", "typical_structure", "appropriate_contexts", "limitations", "safety_notes", "application_notes", "academic_definition"})
SAFE_FIELDS |= frozenset({"title_en","title_fa","description_en","description_fa","historical_importance_en","historical_importance_fa","summary_en","summary_fa","explanation_en","explanation_fa","birth_year","death_year","nationality_en","nationality_fa","year_start","year_end","date_precision","exact_date","date_text","event_type","academic_disciplines","contributions_en","contributions_fa","period_text","core_proposition_en","core_proposition_fa","related_psychologist","related_theory","psychologist","theory","event","modern_status"})
TARGET_KINDS = frozenset({"", "user", "group", "session", "category", "disorder", "symptom", "disorder-symptom",
    "differential-relationship", "disorder-source", "concept", "concept-relationship", "concept-alias",
    "concept-relationship-source", "concept-symptom", "concept-symptom-source", "disorder-concept", "concept-source",
    "dsm-corpus", "dsm-record", "dsm-record-relation",
    "therapy-family", "therapy-classification", "therapy", "technique", "therapy-classification-link", "therapy-disorder", "therapy-technique", "therapy-concept", "technique-concept", "therapy-alias", "technique-alias", "therapy-source", "technique-source", "therapy-technique-source", "therapy-disorder-source", "therapy-concept-source", "technique-concept-source",
    "psychologist", "psychologist-alias", "psychologist-source", "psychologist-theory", "psychologist-theory-source", "psychologist-concept", "psychologist-concept-source", "psychologist-therapy", "psychologist-therapy-source", "psychologist-psychologist", "psychologist-psychologist-source", "theory", "theory-alias", "theory-source", "theory-concept", "theory-concept-source", "theory-therapy", "theory-therapy-source", "theory-technique", "theory-technique-source", "theory-theory", "theory-theory-source", "timeline-event", "timeline-event-source", "timeline-psychologist", "timeline-psychologist-source", "timeline-theory", "timeline-theory-source", "timeline-therapy", "timeline-therapy-source", "timeline-technique", "timeline-technique-source", "timeline-concept", "timeline-concept-source"})

TARGET_KINDS |= frozenset(('brain-anatomical-entity', 'brain-network', 'brain-anatomical-alias', 'brain-network-alias', 'brain-anatomical-entity-source', 'brain-network-source', 'brain-external-identifier', 'brain-hierarchy-link', 'brain-hierarchy-link-source', 'brain-network-membership', 'brain-functional-association', 'brain-network-membership-source', 'brain-functional-association-source'))
SAFE_FIELDS |= frozenset(("laterality","source_version","evidence_key","namespace","identifier","source_note","entity","network","child","parent","method","qualifier","task_context","population_context","population_context","limitations","description_en","description_fa"))


TARGET_KINDS |= frozenset(('assessment-instrument', 'assessment-version', 'assessment-language-form', 'assessment-validation-study', 'assessment-psychometric-evidence', 'assessment-alias', 'assessment-access', 'assessment-relation', 'assessment-source'))
SAFE_FIELDS |= frozenset(("instrument","version","language_form","study","form_kind","measurement_property","sample_context","sample_size","administration","informant","statistic","value_text","units","uncertainty","finding","extraction_locator","material_type","use","license_status","authorization_status","authorization_source","authorization_note","jurisdiction","availability","terms","verified_on","expires_on","rightsholder","construct_overview","intended_use","design","population","comparator"))


# P12 editorial actions: only safe IDs and field names, never case narrative content.
ACTIONS |= frozenset({"case.draft_created", "case.draft_cloned", "case.draft_updated", "case.graph_updated",
    "case.review_decided", "case.publication_frozen", "case.publication_approved",
    "case.publication_applied", "case.publication_withdrawn"})
TARGET_KINDS |= frozenset({"clinical-case"})

# P16 private review selection and sealed preparation evidence only.
# Neither operation is a rights/science approval or canonical publication.
ACTIONS |= frozenset({"publication.selection_created", "publication.preparation_created"})
TARGET_KINDS |= frozenset({"publication-selection", "publication-preparation"})

# P13 private quiz drafts; never audit question prompts or answer text.
ACTIONS |= frozenset({"quiz.draft_created", "quiz.draft_updated"})
TARGET_KINDS |= frozenset({"quiz"})
SAFE_FIELDS |= frozenset({"questions"})

ACTIONS |= frozenset({"flashcard.draft_created", "flashcard.draft_updated"})
TARGET_KINDS |= frozenset({"flashcard"})

ACTIONS |= frozenset({"practice.draft_created", "practice.draft_updated"})
TARGET_KINDS |= frozenset({"learning-practice"})


def attribution(actor_id):
    return salted_hmac("cms-audit-actor-v1", str(actor_id), algorithm="sha256").hexdigest() if actor_id else ""


def changed_fields(before, after):
    # Values, text lengths and hashes of private text never enter the audit channel.
    return sorted(k for k in SAFE_FIELDS if before.get(k) != after.get(k))


def security_event(actor, code, status, request_id=None):
    """Called after the business transaction has exited, never via on_commit."""
    from .cms_models import AdminAuditEvent
    if any(not getattr(block, "_from_testcase", False) for block in connection.atomic_blocks):
        raise RuntimeError("Security events require an independent transaction")
    with transaction.atomic():
        return AdminAuditEvent.objects.create(
            actor=actor if actor and actor.is_authenticated else None,
            action="api.failure" if status >= 500 else "api.security_denial",
            outcome="failed" if status >= 500 else "denied", error_code=code,
            request_id=request_id or uuid.uuid4(),
        )


def failure_response(request, exc):
    """Package MFA views use the same independent, sanitized failure channel."""
    from .cms_policy import CMSFailure
    request_id = uuid.uuid4()
    code = str(exc.detail["code"]) if isinstance(exc, CMSFailure) else "INTERNAL_ERROR"
    status = exc.status_code if isinstance(exc, CMSFailure) else 503
    try:
        security_event(getattr(request, "user", None), code, status, request_id)
    except DatabaseError:
        code, status = "AUDIT_UNAVAILABLE", 503
    return JsonResponse({"code": code, "request_id": str(request_id)}, status=status)

ACTIONS |= frozenset({"learning.archived"})
ACTIONS |= frozenset({"learning.imported", "learning.exported", "learning.transfer_prepared"})
ACTIONS |= frozenset("privacy.read." + scope for scope in (
    "disorder_notes", "concept_notes", "therapy_notes", "disorder_progress", "concept_progress", "flashcard_srs",
    "quiz_attempts", "quiz_answers", "case_attempts", "case_events", "daily_attempts", "distortion_attempts",
    "study_plans", "study_scopes", "study_blocks", "study_sessions", "study_availability",
    "recommendations", "activities", "recommendation_feedback",
    "disorder_bookmarks", "concept_bookmarks", "therapy_bookmarks", "study_settings"))
REASONS |= frozenset({"PRIVACY_SUPPORT"})
ACTIONS |= frozenset({"privacy.export_requested", "privacy.exported"})
REASONS |= frozenset({"PRIVACY_REQUEST"})
ACTIONS |= frozenset({"study.operated"})
REASONS |= frozenset({"STUDY_SUPPORT"})
REASONS |= frozenset({"LEARNING_TRANSFER"})
REASONS |= frozenset({"CONTENT_ARCHIVE"})
TARGET_KINDS |= frozenset({"daily", "distortions"})
SAFE_FIELDS |= frozenset({"archived_at"})
