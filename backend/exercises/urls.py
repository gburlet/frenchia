from django.urls import path

from . import views

urlpatterns = [
    path("exercise-revisions/<int:revision_id>/attempts", views.AttemptCreateView.as_view()),
    path("attempts/<int:attempt_id>/regrade", views.RegradeView.as_view()),
    path("attempts/<int:attempt_id>/dispute", views.DisputeView.as_view()),
    path("practice/translate/options", views.TranslateOptionsView.as_view()),
    path("practice/translate/next", views.TranslateNextView.as_view()),
]
