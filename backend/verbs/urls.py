from django.urls import path

from . import views

urlpatterns = [
    path("verbs", views.CatalogView.as_view(), name="verbs"),
    path("verbs/drills", views.DrillView.as_view(), name="verb-drill"),
    path("verbs/answers", views.AnswersView.as_view(), name="verb-answers"),
    path("verbs/progress", views.ProgressView.as_view(), name="verb-progress"),
    path("verbs/<slug:slug>", views.VerbDetailView.as_view(), name="verb-detail"),
]
