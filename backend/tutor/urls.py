from django.urls import path

from . import views

urlpatterns = [
    path("tutor/threads", views.ThreadListView.as_view(), name="tutor-threads"),
    path("tutor/threads/<int:thread_id>", views.ThreadDetailView.as_view(), name="tutor-thread"),
    path("tutor/threads/<int:thread_id>/messages", views.stream_message, name="tutor-message"),
    path("tutor/messages/<int:message_id>/retry", views.retry_message, name="tutor-retry"),
]
