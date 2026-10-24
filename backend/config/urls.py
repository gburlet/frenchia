from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from curriculum.api import CurriculumView, LessonView
from progress.views import LessonProgressView

from .health import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", HealthView.as_view(), name="health"),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("inference.urls")),
    path("api/", include("exercises.urls")),
    path("api/curriculum", CurriculumView.as_view(), name="curriculum"),
    path("api/lessons/<slug:slug>", LessonView.as_view(), name="lesson"),
    path("api/lessons/<slug:slug>/progress", LessonProgressView.as_view(), name="lesson-progress"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
]
