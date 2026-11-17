"""Frozen P00 V1 permission vocabulary; readiness is separate from authorization."""

CAPABILITIES = frozenset({
    'cms_analytics_view',
    'cms_artifact_download',
    'cms_artifact_upload',
    'cms_assessment_archive',
    'cms_assessment_create',
    'cms_assessment_delete_preview',
    'cms_assessment_edit',
    'cms_assessment_export',
    'cms_assessment_preview',
    'cms_assessment_submit',
    'cms_assessment_validate',
    'cms_assessment_view',
    'cms_audit_export',
    'cms_audit_view',
    'cms_brain_archive',
    'cms_brain_create',
    'cms_brain_delete_preview',
    'cms_brain_edit',
    'cms_brain_export',
    'cms_brain_preview',
    'cms_brain_submit',
    'cms_brain_validate',
    'cms_brain_view',
    'cms_cases_archive',
    'cms_cases_create',
    'cms_cases_delete_preview',
    'cms_cases_delete_unused',
    'cms_cases_edit',
    'cms_cases_export',
    'cms_cases_preview',
    'cms_cases_submit',
    'cms_cases_validate',
    'cms_cases_view',
    'cms_catalog',
    'cms_core_archive',
    'cms_core_create',
    'cms_core_delete_preview',
    'cms_core_delete_unused',
    'cms_core_edit',
    'cms_core_export',
    'cms_core_preview',
    'cms_core_submit',
    'cms_core_validate',
    'cms_core_view',
    'cms_dashboard',
    'cms_dsm_archive',
    'cms_dsm_create',
    'cms_dsm_delete_preview',
    'cms_dsm_delete_unused',
    'cms_dsm_edit',
    'cms_dsm_export',
    'cms_dsm_preview',
    'cms_dsm_submit',
    'cms_dsm_validate',
    'cms_dsm_view',
    'cms_emergency_lock_import',
    'cms_emergency_revoke_sessions',
    'cms_emergency_withdraw',
    'cms_enter',
    'cms_history_archive',
    'cms_history_create',
    'cms_history_delete_preview',
    'cms_history_delete_unused',
    'cms_history_edit',
    'cms_history_export',
    'cms_history_preview',
    'cms_history_submit',
    'cms_history_validate',
    'cms_history_view',
    'cms_learning_archive',
    'cms_learning_create',
    'cms_learning_delete_preview',
    'cms_learning_delete_unused',
    'cms_learning_edit',
    'cms_learning_export',
    'cms_learning_preview',
    'cms_learning_submit',
    'cms_learning_validate',
    'cms_learning_view',
    'cms_operations_backup',
    'cms_owner',
    'cms_privacy_correct',
    'cms_privacy_erase',
    'cms_privacy_export',
    'cms_privacy_sensitive_read',
    'cms_publication_apply_assessment',
    'cms_publication_apply_brain',
    'cms_publication_apply_cases',
    'cms_publication_apply_core',
    'cms_publication_apply_dsm',
    'cms_publication_apply_history',
    'cms_publication_apply_learning',
    'cms_publication_apply_source',
    'cms_publication_apply_therapy',
    'cms_publication_approve_assessment',
    'cms_publication_approve_brain',
    'cms_publication_approve_cases',
    'cms_publication_approve_core',
    'cms_publication_approve_dsm',
    'cms_publication_approve_history',
    'cms_publication_approve_learning',
    'cms_publication_approve_source',
    'cms_publication_approve_therapy',
    'cms_publication_freeze_assessment',
    'cms_publication_freeze_brain',
    'cms_publication_freeze_cases',
    'cms_publication_freeze_core',
    'cms_publication_freeze_dsm',
    'cms_publication_freeze_history',
    'cms_publication_freeze_learning',
    'cms_publication_freeze_source',
    'cms_publication_freeze_therapy',
    'cms_publication_reinstate_assessment',
    'cms_publication_reinstate_brain',
    'cms_publication_reinstate_cases',
    'cms_publication_reinstate_core',
    'cms_publication_reinstate_dsm',
    'cms_publication_reinstate_history',
    'cms_publication_reinstate_learning',
    'cms_publication_reinstate_source',
    'cms_publication_reinstate_therapy',
    'cms_publication_select_assessment',
    'cms_publication_select_brain',
    'cms_publication_select_cases',
    'cms_publication_select_core',
    'cms_publication_select_dsm',
    'cms_publication_select_history',
    'cms_publication_select_learning',
    'cms_publication_select_source',
    'cms_publication_select_therapy',
    'cms_publication_validate_assessment',
    'cms_publication_validate_brain',
    'cms_publication_validate_cases',
    'cms_publication_validate_core',
    'cms_publication_validate_dsm',
    'cms_publication_validate_history',
    'cms_publication_validate_learning',
    'cms_publication_validate_source',
    'cms_publication_validate_therapy',
    'cms_publication_verify_assessment',
    'cms_publication_verify_brain',
    'cms_publication_verify_cases',
    'cms_publication_verify_core',
    'cms_publication_verify_dsm',
    'cms_publication_verify_history',
    'cms_publication_verify_learning',
    'cms_publication_verify_source',
    'cms_publication_verify_therapy',
    'cms_publication_withdraw_assessment',
    'cms_publication_withdraw_brain',
    'cms_publication_withdraw_cases',
    'cms_publication_withdraw_core',
    'cms_publication_withdraw_dsm',
    'cms_publication_withdraw_history',
    'cms_publication_withdraw_learning',
    'cms_publication_withdraw_source',
    'cms_publication_withdraw_therapy',
    'cms_research_defer',
    'cms_research_derive',
    'cms_research_export',
    'cms_research_intake',
    'cms_research_map',
    'cms_research_promote',
    'cms_research_raw_read',
    'cms_research_reject',
    'cms_research_retire',
    'cms_research_view',
    'cms_review_decide_assessment_rights',
    'cms_review_decide_assessment_scientific',
    'cms_review_decide_assessment_source',
    'cms_review_decide_assessment_terminology',
    'cms_review_decide_brain_rights',
    'cms_review_decide_brain_scientific',
    'cms_review_decide_brain_source',
    'cms_review_decide_brain_terminology',
    'cms_review_decide_cases_rights',
    'cms_review_decide_cases_scientific',
    'cms_review_decide_cases_source',
    'cms_review_decide_cases_terminology',
    'cms_review_decide_core_rights',
    'cms_review_decide_core_scientific',
    'cms_review_decide_core_source',
    'cms_review_decide_core_terminology',
    'cms_review_decide_dsm_rights',
    'cms_review_decide_dsm_scientific',
    'cms_review_decide_dsm_source',
    'cms_review_decide_dsm_terminology',
    'cms_review_decide_history_rights',
    'cms_review_decide_history_scientific',
    'cms_review_decide_history_source',
    'cms_review_decide_history_terminology',
    'cms_review_decide_learning_rights',
    'cms_review_decide_learning_scientific',
    'cms_review_decide_learning_source',
    'cms_review_decide_learning_terminology',
    'cms_review_decide_source_rights',
    'cms_review_decide_source_scientific',
    'cms_review_decide_source_source',
    'cms_review_decide_source_terminology',
    'cms_review_decide_therapy_rights',
    'cms_review_decide_therapy_scientific',
    'cms_review_decide_therapy_source',
    'cms_review_decide_therapy_terminology',
    'cms_rights_decide',
    'cms_rights_revoke',
    'cms_roles_edit',
    'cms_roles_grant_owner',
    'cms_roles_view',
    'cms_search',
    'cms_settings_edit',
    'cms_source_archive',
    'cms_source_create',
    'cms_source_delete_preview',
    'cms_source_delete_unused',
    'cms_source_edit',
    'cms_source_export',
    'cms_source_preview',
    'cms_source_submit',
    'cms_source_validate',
    'cms_source_view',
    'cms_study_correct',
    'cms_study_view',
    'cms_terminology_decide',
    'cms_therapy_archive',
    'cms_therapy_create',
    'cms_therapy_delete_preview',
    'cms_therapy_delete_unused',
    'cms_therapy_edit',
    'cms_therapy_export',
    'cms_therapy_preview',
    'cms_therapy_submit',
    'cms_therapy_validate',
    'cms_therapy_view',
    'cms_user_change_status',
    'cms_user_correct',
    'cms_user_recovery',
    'cms_user_revoke_sessions',
    'cms_user_view',
})

DELEGATIONS = frozenset("cms_delegate_" + c[4:] for c in CAPABILITIES - {"cms_owner", "cms_roles_grant_owner"})
KNOWN_PERMISSIONS = CAPABILITIES | DELEGATIONS
READY_CAPABILITIES = frozenset({"cms_enter", "cms_catalog", "cms_dashboard", "cms_owner", "cms_roles_view", "cms_roles_edit", "cms_roles_grant_owner", "cms_user_revoke_sessions",
    "cms_core_view", "cms_core_create", "cms_core_edit", "cms_audit_view", "cms_core_submit",
    "cms_review_decide_core_source", "cms_review_decide_core_scientific", "cms_settings_edit"})

# P05 domain permissions authorize governance proposals; canonical editors keep their own readiness.
GOVERNANCE_DOMAINS = ("core", "dsm", "therapy", "history", "cases", "learning", "brain", "assessment", "source")
READY_CAPABILITIES |= frozenset({"cms_rights_decide", "cms_rights_revoke", "cms_terminology_decide",
    "cms_source_view", "cms_source_create", "cms_source_edit", "cms_source_archive", "cms_source_delete_preview",
    "cms_source_delete_unused", "cms_source_preview", "cms_source_validate", "cms_source_export"})
READY_CAPABILITIES |= frozenset(f"cms_{domain}_{operation}" for domain in GOVERNANCE_DOMAINS for operation in ("view", "edit"))
READY_CAPABILITIES |= frozenset(f"cms_review_decide_{domain}_{kind}" for domain in GOVERNANCE_DOMAINS for kind in ("rights", "terminology"))
READY_CAPABILITIES |= frozenset({"cms_artifact_upload", "cms_artifact_download", "cms_research_view",
    "cms_research_intake", "cms_research_export", "cms_research_map", "cms_research_derive", "cms_research_reject", "cms_research_defer", "cms_research_raw_read"})
READY_CAPABILITIES |= frozenset(f"cms_{domain}_{operation}" for domain in ("core", "dsm")
    for operation in ("view", "create", "edit", "submit", "validate", "preview", "archive"))
READY_CAPABILITIES |= frozenset({"cms_review_decide_dsm_source", "cms_review_decide_dsm_scientific"})
# P08 editorial only; publication, withdrawal and destructive delete stay unavailable until P16.
READY_CAPABILITIES |= frozenset("cms_therapy_" + action for action in ("view", "create", "edit", "submit", "validate", "preview", "archive"))
READY_CAPABILITIES |= frozenset({"cms_review_decide_therapy_source", "cms_review_decide_therapy_scientific"})
# P09: history chronology and source-backed editorial drafts only, never P16 publication.
READY_CAPABILITIES |= frozenset("cms_history_" + action for action in ("view","create","edit","submit","validate","preview","archive"))
READY_CAPABILITIES |= frozenset({"cms_review_decide_history_source","cms_review_decide_history_scientific"})

# P10 only: real typed Brain authoring and source/scientific review.
# P16 publication, withdrawal, physical deletion and activation remain unavailable.
READY_CAPABILITIES |= frozenset("cms_brain_" + action for action in
    ("view", "create", "edit", "submit", "validate", "preview", "archive"))
READY_CAPABILITIES |= frozenset({"cms_review_decide_brain_source", "cms_review_decide_brain_scientific"})

# P12 first, read-only CaseRevision graph inspection; authoring/publication remain pending.
READY_CAPABILITIES |= frozenset({"cms_cases_view", "cms_cases_preview", "cms_cases_create", "cms_cases_edit", "cms_cases_validate"})

# P16 CaseRevision scientific, source and rights-gated publisher (still requires real human decisions).
READY_CAPABILITIES |= frozenset({
    "cms_review_decide_cases_source", "cms_review_decide_cases_scientific", "cms_review_decide_cases_rights",
    "cms_publication_freeze_cases", "cms_publication_approve_cases", "cms_publication_apply_cases",
    "cms_publication_verify_cases", "cms_publication_withdraw_cases", "cms_publication_reinstate_cases",
})

# P17 bounded authenticated slug-only CMS search; public search unchanged.
READY_CAPABILITIES |= frozenset({"cms_search"})

# P16 read-only unpublished candidate inventory; no Apply/approval/activation.
READY_CAPABILITIES |= frozenset({
    "cms_publication_validate_cases", "cms_publication_validate_learning",
    "cms_publication_validate_brain", "cms_publication_validate_assessment",
    "cms_publication_select_learning", "cms_publication_select_brain",
    "cms_publication_select_assessment",
})

# W16-02: safe frozen review manifests only; Approval and public Apply remain unready.
READY_CAPABILITIES |= frozenset(f"cms_publication_{operation}_{domain}"
    for domain in ("learning", "brain", "assessment") for operation in ("freeze", "verify"))

# P15 aggregate-only study telemetry; no private learner reads/corrections.
READY_CAPABILITIES |= frozenset({"cms_study_view"})

# P14 first redacted private account directory only. Sensitive reads/writes remain unready.
READY_CAPABILITIES |= frozenset({"cms_user_view"})

# P13 first bounded Quiz authoring/validation and write-free preview. No publication.
READY_CAPABILITIES |= frozenset({"cms_learning_view", "cms_learning_create", "cms_learning_edit", "cms_learning_validate", "cms_learning_preview"})

# P11 metadata-only Assessment proposals. P16 publication, item banks and test
# execution remain intentionally unavailable.
READY_CAPABILITIES |= frozenset("cms_assessment_" + action for action in
    ("view", "create", "edit", "submit", "validate", "preview", "archive"))
READY_CAPABILITIES |= frozenset({"cms_review_decide_assessment_source", "cms_review_decide_assessment_scientific"})

READY_CAPABILITIES |= frozenset({"cms_learning_archive"})
READY_CAPABILITIES |= frozenset({"cms_learning_export"})
READY_CAPABILITIES |= frozenset({"cms_privacy_sensitive_read"})
READY_CAPABILITIES |= frozenset({"cms_privacy_export"})
READY_CAPABILITIES |= frozenset({"cms_study_correct"})
