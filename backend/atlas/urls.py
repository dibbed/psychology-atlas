from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import dsm_views, views, v3_views, v4_views

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view()),
    path("auth/login/", TokenObtainPairView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
    path("auth/logout/", views.logout),
    path("auth/me/", views.me),

    path("categories/", views.categories),
    path("disorders/", views.DisorderListView.as_view()),
    path("disorders/compare/", views.compare_disorders),
    path("disorders/<slug:slug>/", views.DisorderDetailView.as_view()),

    path("quizzes/", views.QuizListView.as_view()),
    path("quizzes/<slug:slug>/", views.QuizDetailView.as_view()),
    path("quizzes/<slug:slug>/submit/", views.quiz_submit),

    path("cases/", views.ClinicalCaseListView.as_view()),
    path("cases/<slug:slug>/", views.ClinicalCaseDetailView.as_view()),
    path("cases/<slug:slug>/submit/", views.case_submit),

    path("bookmarks/", views.bookmarks),
    path("bookmarks/<slug:slug>/", views.bookmark_delete),
    path("progress/<slug:slug>/view/", views.progress_view),
    path("notes/", views.notes),
    path("notes/<slug:slug>/", views.note_detail),
    path("dashboard/", views.dashboard),

    path("concepts/", v3_views.ConceptListView.as_view()),
    path("concepts/<slug:slug>/", v3_views.ConceptDetailView.as_view()),
    path("concepts/<slug:slug>/view/", v3_views.concept_view),
    path("concepts/<slug:slug>/neighborhood/", v4_views.concept_neighborhood),
    path("concept-bookmarks/", v3_views.concept_bookmarks),
    path("concept-bookmarks/<slug:slug>/", v3_views.concept_bookmark_delete),
    path("concept-notes/", v3_views.concept_notes),
    path("concept-notes/<slug:slug>/", v3_views.concept_note_detail),
    path("flashcards/", v3_views.FlashcardListView.as_view()),
    path("flashcards/review-queue/", v3_views.review_queue),
    path("flashcards/<slug:slug>/review/", v3_views.flashcard_review),
    path("daily-challenge/", v3_views.daily_challenge),
    path("study/overview/", v3_views.study_overview),
    path("search/", v3_views.global_search),
    path("atlas-overview/", v3_views.atlas_overview),
    path("concept-map/", v4_views.concept_map_v2),
    path("concept-map/path/", v4_views.graph_path),
    path("cognitive-distortions/overview/", v4_views.cognitive_distortions_overview),
    path("cognitive-distortions/practice/", v4_views.distortion_practice_queue),
    path("cognitive-distortions/practice/<slug:slug>/submit/", v4_views.distortion_practice_submit),

    path("dsm/overview/", dsm_views.dsm_overview),
    path("dsm/metadata/", dsm_views.dsm_metadata),
    path("dsm/study-kit/", dsm_views.dsm_study_kit),
    path("dsm/graph/", dsm_views.dsm_graph),
    path("dsm/records/", dsm_views.DSMRecordListView.as_view()),
    path("dsm/records/by-disorder/<slug:slug>/", dsm_views.dsm_record_by_disorder),
    path("dsm/records/<str:master_id>/", dsm_views.DSMRecordDetailView.as_view()),
]
