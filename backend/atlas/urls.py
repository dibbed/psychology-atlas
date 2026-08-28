from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views, v3_views

urlpatterns = [
    path("auth/register/", views.RegisterView.as_view()),
    path("auth/login/", TokenObtainPairView.as_view()),
    path("auth/refresh/", TokenRefreshView.as_view()),
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
    path("concept-map/", v3_views.concept_map),
]
