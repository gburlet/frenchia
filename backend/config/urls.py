from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from .health import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health", HealthView.as_view(), name="health"),
    path("api/auth/", include("accounts.urls")),
    path("api/", include("inference.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
]
