from django.contrib import admin

from .models import TutorMessage, TutorThread


class TutorMessageInline(admin.TabularInline[TutorMessage, TutorThread]):
    model = TutorMessage
    fields = ("role", "status", "content", "first_token_ms", "latency_ms", "created_at")
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(TutorThread)
class TutorThreadAdmin(admin.ModelAdmin[TutorThread]):
    list_display = ["id", "title", "user", "updated_at"]
    inlines = [TutorMessageInline]
