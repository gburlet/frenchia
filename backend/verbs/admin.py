from django.contrib import admin

from .models import ConjugationAttempt, VerbMastery


@admin.register(ConjugationAttempt)
class ConjugationAttemptAdmin(admin.ModelAdmin[ConjugationAttempt]):
    list_display = ["created_at", "user", "infinitive", "tense", "person", "answer", "result"]
    list_filter = ["result", "mode", "tense"]
    search_fields = ["infinitive", "answer"]
    readonly_fields = [f.name for f in ConjugationAttempt._meta.fields]


@admin.register(VerbMastery)
class VerbMasteryAdmin(admin.ModelAdmin[VerbMastery]):
    list_display = ["user", "infinitive", "tense", "attempts", "ewma", "last_practiced"]
    list_filter = ["tense"]
    search_fields = ["infinitive"]
