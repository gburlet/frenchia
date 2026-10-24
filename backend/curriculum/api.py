"""Learner-facing curriculum and lesson API (see docs/api-learning.md)."""

from typing import Any

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from exercises.public import public_exercise
from progress.models import LessonProgress

from .models import CurriculumLevel, GrammarTopic, Lesson, Unit


def progress_dict(progress: LessonProgress | None) -> dict[str, Any]:
    if progress is None:
        return {"status": "not_started", "completed_at": None}
    return {"status": progress.status, "completed_at": progress.completed_at}


def _user(request: Request) -> User:
    assert isinstance(request.user, User)
    return request.user


class CurriculumView(APIView):
    @extend_schema(operation_id="curriculum", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        progress = {p.lesson_id: p for p in LessonProgress.objects.filter(user=_user(request))}
        lessons_by_unit: dict[str, list[dict[str, Any]]] = {}
        for lesson in Lesson.objects.order_by("order"):
            lessons_by_unit.setdefault(lesson.unit_id, []).append(
                {
                    "id": lesson.slug,
                    "title": lesson.title,
                    "kind": lesson.kind,
                    "published": lesson.published_revision_id is not None,
                    "progress": progress_dict(progress.get(lesson.slug)),
                }
            )
        levels = []
        for level in CurriculumLevel.objects.order_by("code"):
            units = [
                {
                    "id": u.slug,
                    "title": u.title,
                    "objectives": u.objectives,
                    "lessons": lessons_by_unit.get(u.slug, []),
                }
                for u in Unit.objects.filter(level=level.code).order_by("order")
            ]
            levels.append(
                {
                    "level": level.code,
                    "title": level.title,
                    "summary": level.summary,
                    "units": units,
                }
            )
        return Response({"levels": levels})


class LessonView(APIView):
    @extend_schema(operation_id="lesson_detail", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request, slug: str) -> Response:
        lesson = get_object_or_404(
            Lesson.objects.select_related("unit", "published_revision"), slug=slug
        )
        revision = lesson.published_revision
        if revision is None:
            raise NotFound("This lesson has no published content yet.")
        payload = revision.payload
        topics = GrammarTopic.objects.filter(slug__in=payload.get("grammar_topics", []))
        exercises = {
            e.exercise.stable_id.split("/", 1)[1]: e
            for e in revision.exercise_revisions.select_related("exercise")
        }
        published = Lesson.objects.filter(published_revision__isnull=False).order_by("order")
        previous = published.filter(order__lt=lesson.order).last()
        following = published.filter(order__gt=lesson.order).first()
        progress = LessonProgress.objects.filter(user=_user(request), lesson=lesson).first()
        return Response(
            {
                "id": lesson.slug,
                "title": payload["title"],
                "title_en": payload["title_en"],
                "level": lesson.unit.level,
                "unit": {"id": lesson.unit_id, "title": lesson.unit.title},
                "objectives": payload["objectives"],
                "estimated_minutes": payload["estimated_minutes"],
                "grammar_topics": [{"id": t.slug, "title": t.title} for t in topics],
                "revision": {"id": revision.pk, "content_version": revision.content_version},
                "sections": payload["sections"],
                "exercises": [
                    public_exercise(exercises[e["id"]])
                    for e in payload["exercises"]
                    if e["id"] in exercises
                ],
                "progress": progress_dict(progress),
                "previous": {"id": previous.slug, "title": previous.title} if previous else None,
                "next": {"id": following.slug, "title": following.title} if following else None,
            }
        )
