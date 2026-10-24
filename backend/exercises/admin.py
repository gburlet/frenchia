from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import ExerciseAttempt, MistakeOccurrence
from .services import AttemptError, accept_disputed_answer


@admin.register(ExerciseAttempt)
class ExerciseAttemptAdmin(admin.ModelAdmin[ExerciseAttempt]):
    list_display = [
        "id",
        "exercise_revision",
        "answer",
        "verdict",
        "grading",
        "score",
        "disputed",
        "created_at",
    ]
    list_filter = ["disputed", "verdict", "grading", "status"]
    search_fields = ["answer", "exercise_revision__exercise__stable_id"]
    readonly_fields = [f.name for f in ExerciseAttempt._meta.fields]
    actions = ["accept_answer"]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    @admin.action(
        description="Accept the learner's answer (adds it to the exercise's accepted answers)"
    )
    def accept_answer(self, request: HttpRequest, queryset: QuerySet[ExerciseAttempt]) -> None:
        for attempt in queryset:
            try:
                path = accept_disputed_answer(attempt)
            except AttemptError as exc:
                self.message_user(request, f"Attempt {attempt.pk}: {exc}", messages.ERROR)
            else:
                self.message_user(
                    request,
                    f"Attempt {attempt.pk}: answer added to {path.name} (commit it with git).",
                    messages.SUCCESS,
                )


@admin.register(MistakeOccurrence)
class MistakeOccurrenceAdmin(admin.ModelAdmin[MistakeOccurrence]):
    list_display = ["created_at", "category", "grammar_topic", "span", "explanation"]
    list_filter = ["category", "grammar_topic"]
    readonly_fields = [f.name for f in MistakeOccurrence._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
