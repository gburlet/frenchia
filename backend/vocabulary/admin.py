from django.contrib import admin

from .models import Lexeme, VocabCard, VocabReview, VocabSet


class LexemeInline(admin.TabularInline[Lexeme, VocabSet]):
    model = Lexeme
    fields = ["order", "fr", "gender", "en", "region", "retired"]
    readonly_fields = ["order", "fr", "gender", "en", "region", "retired"]
    extra = 0
    can_delete = False


@admin.register(VocabSet)
class VocabSetAdmin(admin.ModelAdmin[VocabSet]):
    list_display = ["slug", "kind", "level", "title", "content_version", "updated_at"]
    list_filter = ["kind", "level"]
    readonly_fields = ["content_hash", "source_path", "updated_at"]
    inlines = [LexemeInline]


@admin.register(VocabCard)
class VocabCardAdmin(admin.ModelAdmin[VocabCard]):
    list_display = ["user", "lexeme", "direction", "due", "reps", "lapses", "suspended"]
    list_filter = ["direction", "suspended"]
    search_fields = ["lexeme__fr"]
    raw_id_fields = ["lexeme"]


@admin.register(VocabReview)
class VocabReviewAdmin(admin.ModelAdmin[VocabReview]):
    list_display = ["reviewed_at", "card", "rating", "check_result", "was_new"]
    list_filter = ["rating", "was_new"]
    readonly_fields = [f.name for f in VocabReview._meta.fields]
