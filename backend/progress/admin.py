from django.contrib import admin

from .models import LessonProgress, TopicMastery


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin[LessonProgress]):
    list_display = ["user", "lesson", "status", "started_at", "completed_at"]
    list_filter = ["status"]


@admin.register(TopicMastery)
class TopicMasteryAdmin(admin.ModelAdmin[TopicMastery]):
    list_display = ["user", "topic", "attempts", "correct", "ewma", "last_practiced"]
    ordering = ["ewma"]
