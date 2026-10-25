from django.contrib import admin

from .models import LessonProgress, ReviewItem, ReviewSet, TopicMastery


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin[LessonProgress]):
    list_display = ["user", "lesson", "status", "started_at", "completed_at"]
    list_filter = ["status"]


@admin.register(TopicMastery)
class TopicMasteryAdmin(admin.ModelAdmin[TopicMastery]):
    list_display = ["user", "topic", "attempts", "correct", "ewma", "last_practiced"]
    ordering = ["ewma"]


class ReviewItemInline(admin.TabularInline[ReviewItem, ReviewSet]):
    model = ReviewItem
    fields = readonly_fields = ("order", "topic", "source", "exercise_revision")
    extra = 0
    can_delete = False


@admin.register(ReviewSet)
class ReviewSetAdmin(admin.ModelAdmin[ReviewSet]):
    list_display = ["id", "user", "created_at", "extras", "completed_at"]
    list_filter = ["extras"]
    readonly_fields = ["user", "topics", "extras", "extras_error", "extras_log", "created_at"]
    inlines = [ReviewItemInline]
