from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from . import views

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
]
