from typing import Any

from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from curriculum.api import progress_dict
from curriculum.models import Lesson
from exercises.models import ExerciseAttempt
from exercises.public import public_exercise

from . import review as rules
from . import stats
from .models import LessonProgress, ReviewItem, ReviewSet


class ProgressInput(serializers.Serializer[dict[str, bool]]):
    completed = serializers.BooleanField(required=False, default=False)


class LessonProgressView(APIView):
    @extend_schema(
        operation_id="lesson_progress", request=ProgressInput, responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request: Request, slug: str) -> Response:
        assert isinstance(request.user, User)
        lesson = get_object_or_404(Lesson, slug=slug, published_revision__isnull=False)
        data = ProgressInput(data=request.data)
        data.is_valid(raise_exception=True)
        progress, _ = LessonProgress.objects.get_or_create(user=request.user, lesson=lesson)
        if data.validated_data["completed"] and progress.status != LessonProgress.Status.COMPLETED:
            progress.status = LessonProgress.Status.COMPLETED
            progress.completed_at = timezone.now()
            progress.completed_revision = lesson.published_revision
            progress.save()
        return Response(progress_dict(progress))


class DashboardView(APIView):
    @extend_schema(operation_id="dashboard", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        assert isinstance(request.user, User)
        return Response(stats.dashboard(request.user))


def review_detail(review: ReviewSet) -> dict[str, Any]:
    latest: dict[int, str] = {}
    for revision_id, verdict in (
        ExerciseAttempt.objects.filter(
            user=review.user,
            exercise_revision__review_items__review_set=review,
            created_at__gte=review.created_at,
        )
        .order_by("created_at")
        .values_list("exercise_revision", "verdict")
    ):
        latest[revision_id] = verdict or "pending"
    items = review.items.select_related("exercise_revision__lesson_revision__lesson__unit", "topic")
    return {
        "id": review.pk,
        "created_at": review.created_at.isoformat(),
        "completed_at": review.completed_at.isoformat() if review.completed_at else None,
        "topics": review.topics,
        "extras": review.extras,
        "items": [
            {
                "exercise": public_exercise(item.exercise_revision),
                "topic": {"id": item.topic_id, "title": item.topic.title},
                "source": item.source,
                "source_label": item.get_source_display(),
                "ai_generated": item.source == ReviewItem.Source.GENERATED,
                "lesson": {
                    "id": item.exercise_revision.lesson_revision.lesson.slug,
                    "title": item.exercise_revision.lesson_revision.lesson.title,
                },
                "result": latest.get(item.exercise_revision_id),
            }
            for item in items
        ],
    }


def _own_review(request: Request, review_id: int) -> ReviewSet:
    return get_object_or_404(ReviewSet, pk=review_id, user=request.user)


class ReviewView(APIView):
    @extend_schema(operation_id="review_current", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        assert isinstance(request.user, User)
        current = rules.current_set(request.user)
        return Response(
            {
                "current": None if current is None else review_detail(current),
                "weak_topics": [w.as_dict() for w in rules.weak_topics(request.user)],
            }
        )

    @extend_schema(operation_id="review_create", request=None, responses={201: OpenApiTypes.OBJECT})
    def post(self, request: Request) -> Response:
        assert isinstance(request.user, User)
        try:
            created = rules.build_set(request.user)
        except rules.ReviewUnavailable as exc:
            raise NotFound(str(exc)) from exc
        return Response(review_detail(created), status=status.HTTP_201_CREATED)


class ReviewDetailView(APIView):
    @extend_schema(operation_id="review_detail", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request, review_id: int) -> Response:
        return Response(review_detail(_own_review(request, review_id)))


class ReviewCompleteView(APIView):
    @extend_schema(
        operation_id="review_complete", request=None, responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request: Request, review_id: int) -> Response:
        current = _own_review(request, review_id)
        if current.completed_at is None:
            current.completed_at = timezone.now()
            current.save(update_fields=["completed_at"])
        return Response(review_detail(current))
