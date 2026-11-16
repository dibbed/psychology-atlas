from django.urls import include, path

from . import cms_views as v
from . import cms_privacy as privacy
from . import cms_privacy_io as privacy_io
from . import cms_study_actions as study_actions
from . import cms_content_views as content
from . import cms_review_views as review
from . import cms_source_views as sources
from . import cms_governance_views as governance
from . import cms_job_views as jobs
from . import cms_artifact_views as artifacts
from . import cms_domain_views as domains
from . import cms_history_views as history
from . import cms_brain_views as brain
from . import cms_case_views as cases
from . import cms_case_editor_views as case_editor
from . import cms_case_simulation as case_simulation
from . import cms_case_catalog as case_catalog
from . import cms_case_validation as case_validation
from . import cms_quiz_editor as quiz_editor
from . import cms_flashcard_editor as flashcard_editor
from . import cms_practice_editor as practice_editor
from . import cms_learning_evidence as learning_evidence
from .cms_learning_lifecycle import LearningArchiveView
from . import cms_learning_io_views as learning_io
from . import cms_user_directory as user_directory
from . import cms_study_ops as study_ops
from . import cms_publication_preflight as publication_preflight
from . import cms_publication_selection_views as publication_selection
from . import cms_publication_preparation_views as publication_preparation
from . import cms_case_publication_views as case_publication
from . import cms_admin_search as admin_search
from . import cms_operations_health as operations_health
from . import cms_release_readiness as release_readiness
from . import cms_pipeline_analytics as pipeline_analytics
from . import cms_learning_evidence_history as evidence_history

urlpatterns = [
    path("learning/evidence/<str:kind>/<int:item_id>/history/", evidence_history.LearningEvidenceHistoryView.as_view()),
    path("learning/evidence/<str:kind>/<int:item_id>/", learning_evidence.LearningEvidenceView.as_view()),
    path("learning/transfer/", include(learning_io.urlpatterns)),
    path("learning/archive/<str:kind>/<int:item_id>/", LearningArchiveView.as_view()),
    path("", include(jobs.urlpatterns)),
    path("", include(artifacts.urlpatterns)),
    path("governance/", include(governance.urlpatterns)),
    path("sources/", sources.SourceListView.as_view()),
    path("sources/export/", sources.SourceExportView.as_view()),
    path("sources/preview/", sources.SourcePreviewView.as_view()),
    path("sources/plans/<uuid:plan_id>/", sources.SourcePlanView.as_view()),
    path("sources/plans/<uuid:plan_id>/apply/", sources.SourcePlanApplyView.as_view()),
    path("sources/<int:source_id>/", sources.SourceDetailView.as_view()),
    path("sources/<int:source_id>/history/", sources.SourceHistoryView.as_view()),
    path("reviews/", review.ReviewQueueView.as_view()),
    path("reviews/policy/", review.ReviewPolicyView.as_view()),
    path("reviews/sources/", review.ReviewSourcesView.as_view()),
    path("reviews/<str:kind>/<str:target_id>/", review.ReviewDetailView.as_view()),
    path("reviews/<str:kind>/<str:target_id>/history/", review.ReviewHistoryView.as_view()),
    path("reviews/<str:kind>/<str:target_id>/reviewers/", review.ReviewReviewerView.as_view()),
    path("reviews/<str:kind>/<str:target_id>/<str:action>/", review.ReviewActionView.as_view()),
    path("dashboard/", content.DashboardView.as_view()),
    path("content/schema/", content.ContentSchemaView.as_view()),
    path("content/options/<str:kind>/", domains.ContentOptionsView.as_view()),
    path("content/therapy/public-compare-preview/", domains.TherapyPublicComparePreviewView.as_view()),
    path("content/history/chronology/", history.HistoryChronologyView.as_view()),
    path("content/brain/tree/", brain.BrainTreeView.as_view()),
    path("learning/practice/<str:kind>/", practice_editor.PracticeCatalogView.as_view()),
    path("learning/practice/<str:kind>/<int:item_id>/", practice_editor.PracticeDetailView.as_view()),
    path("learning/practice/<str:kind>/<int:item_id>/edit/", practice_editor.PracticeEditView.as_view()),
    path("learning/practice/<str:kind>/<int:item_id>/simulate/", practice_editor.PracticeSimulationView.as_view()),
    path("learning/flashcards/", flashcard_editor.FlashcardCatalogView.as_view()),
    path("learning/flashcards/<int:card_id>/", flashcard_editor.FlashcardDetailView.as_view()),
    path("learning/flashcards/<int:card_id>/metadata/", flashcard_editor.FlashcardMetadataView.as_view()),
    path("learning/quizzes/", quiz_editor.QuizCatalogView.as_view()),
    path("learning/quizzes/<int:quiz_id>/", quiz_editor.QuizDetailView.as_view()),
    path("learning/quizzes/<int:quiz_id>/metadata/", quiz_editor.QuizMetadataView.as_view()),
    path("learning/quizzes/<int:quiz_id>/questions/replace/", quiz_editor.QuizReplaceView.as_view()),
    path("learning/quizzes/<int:quiz_id>/simulate/", quiz_editor.QuizSimulationView.as_view()),
    path("cases/", case_catalog.CaseCatalogView.as_view()),
    path("cases/<int:case_id>/revisions/", case_catalog.CaseRevisionHistoryView.as_view()),
    path("cases/<int:case_id>/revisions/<int:revision_id>/graph/", cases.CaseRevisionGraphView.as_view()),
    path("cases/<int:case_id>/revisions/<int:revision_id>/clone/", case_editor.CaseCloneDraftView.as_view()),
    path("cases/<int:case_id>/revisions/<int:revision_id>/metadata/", case_editor.CaseDraftMetadataView.as_view()),
    path("cases/<int:case_id>/revisions/<int:revision_id>/graph/edit/", case_editor.CaseDraftGraphEditView.as_view()),
    path("cases/<int:case_id>/revisions/<int:revision_id>/simulate/", case_simulation.CaseRevisionSimulationView.as_view()),
    path("cases/<int:case_id>/revisions/<int:revision_id>/validate/", case_validation.CaseRevisionValidationView.as_view()),
    path("content/history/citation-debt/", history.HistoryCitationDebtView.as_view()),
    path("content/dsm/tree/", domains.DSMTreeView.as_view()),
    path("content/dsm/compare/", domains.DSMCompareView.as_view()),
    path("content/dsm/graph/", domains.DSMGraphView.as_view()),
    path("content/dsm/study/", domains.DSMStudyView.as_view()),
    path("content/<str:kind>/", content.ContentCreateView.as_view()),
    path("content/<str:kind>/<str:target_id>/duplicates/", content.ContentDuplicatesView.as_view()),
    path("content/<str:kind>/<str:target_id>/archive-impact/", content.ContentArchiveImpactView.as_view()),
    path("content/<str:kind>/<str:target_id>/provenance/", history.HistoryProvenanceView.as_view()),
    path("content/<str:kind>/<str:target_id>/", content.ContentDetailView.as_view()),
    path("content/<str:kind>/<str:target_id>/revisions/", content.ContentRevisionView.as_view()),
    path("content/<str:kind>/<str:target_id>/discard/", content.ContentDiscardView.as_view()),
    path("content/<str:kind>/<str:target_id>/validate/", content.ContentValidateView.as_view()),
    path("content/<str:kind>/<str:target_id>/preview/", content.ContentPreviewView.as_view()),
    path("content/<str:kind>/<str:target_id>/archive/", content.ContentArchiveView.as_view()),
    path("content/<str:kind>/<str:target_id>/raw-preview/", domains.ContentRawView.as_view()),
    path("audit/", content.AuditView.as_view()),
    path("audit/<int:event_id>/", content.AuditView.as_view()),
    path("auth/csrf/", v.CSRFView.as_view()),
    path("auth/login/", v.LoginView.as_view()),
    path("auth/verify/", v.VerifyView.as_view()),
    path("auth/complete/", v.CompleteView.as_view()),
    path("auth/logout/", v.LogoutView.as_view()),
    path("auth/step-up/", v.StepUpView.as_view()),
    path("auth/mfa/revoke/", v.RevokeMFAView.as_view()),
    path("me/", v.MeView.as_view()),
    path("catalog/", v.CatalogView.as_view()),
    path("operations/health/", operations_health.OperationsHealthView.as_view()),
    path("operations/release-readiness/", release_readiness.ReleaseReadinessView.as_view()),
    path("analytics/overview/", pipeline_analytics.PipelineAnalyticsView.as_view()),
    path("analytics/overview/export.csv/", pipeline_analytics.PipelineAnalyticsCSVExportView.as_view()),
    path("search/", admin_search.AdminSearchView.as_view()),
    path("publication/preflight/", publication_preflight.PublicationPreflightView.as_view()),
    path("publication/selections/", publication_selection.PublicationSelectionView.as_view()),
    path("publication/selections/<uuid:selection_id>/", publication_selection.PublicationSelectionDetailView.as_view()),
    path("publication/selections/<uuid:selection_id>/verify/", publication_selection.PublicationSelectionVerifyView.as_view()),
    path("publication/selections/<uuid:selection_id>/prepare/", publication_preparation.PreparationCreateView.as_view()),
    path("publication/preparations/", publication_preparation.PreparationInboxView.as_view()),
    path("publication/preparations/recheck/", publication_preparation.PreparationBulkRecheckView.as_view()),
    path("publication/preparations/<uuid:dossier_id>/", publication_preparation.PreparationDetailView.as_view()),
    path("publication/preparations/<uuid:dossier_id>/verify/", publication_preparation.PreparationVerifyView.as_view()),
    path("publication/cases/<int:case_id>/revisions/<int:revision_id>/reviews/", case_publication.CasePublicationReviewView.as_view()),
    path("publication/cases/<int:case_id>/revisions/<int:revision_id>/freeze/", case_publication.CasePublicationFreezeView.as_view()),
    path("publication/cases/plans/<uuid:plan_id>/", case_publication.CasePublicationPlanView.as_view()),
    path("publication/cases/plans/<uuid:plan_id>/approve/", case_publication.CasePublicationApproveView.as_view()),
    path("publication/cases/plans/<uuid:plan_id>/apply/", case_publication.CasePublicationApplyView.as_view()),
    path("publication/cases/plans/<uuid:plan_id>/withdraw/", case_publication.CasePublicationWithdrawView.as_view()),
    path("publication/cases/plans/<uuid:plan_id>/reinstate/", case_publication.CasePublicationReinstateView.as_view()),
    path("study/overview/", study_ops.StudyOperationsOverviewView.as_view()),
    path("users/", user_directory.CMSUserDirectoryView.as_view()),
    path("users/privacy/schema/", privacy.PrivacySchemaView.as_view()),
    path("users/<int:user_id>/", user_directory.CMSUserDetailView.as_view()),
    path("users/<int:user_id>/privacy/read/", privacy.PrivacyReadView.as_view()),
    path("users/<int:user_id>/privacy/export/", privacy_io.PrivacyExportView.as_view()),
    path("users/<int:user_id>/study/operate/", study_actions.StudyOperationView.as_view()),
    path("roles/permissions/", v.PermissionsView.as_view()),
    path("roles/groups/", v.GroupsView.as_view()),
    path("roles/groups/<int:target_id>/", v.GroupView.as_view()),
    path("roles/groups/<int:target_id>/delete/", v.GroupDeleteView.as_view()),
    path("roles/users/<int:target_id>/", v.RoleUserView.as_view()),
    path("sessions/", v.SessionsView.as_view()),
    path("sessions/<uuid:session_id>/revoke/", v.RevokeSessionView.as_view()),
    path("users/<int:target_id>/revoke-sessions/", v.RevokeAccountView.as_view()),
]
