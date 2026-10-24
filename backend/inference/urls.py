from django.urls import path

from . import views

urlpatterns = [
    path("audio", views.AudioView.as_view(), name="audio"),
    path("audio/<str:key>.wav", views.AudioFileView.as_view(), name="audio-file"),
]
