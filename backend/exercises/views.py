import random
from typing import Any

from django.db.models import Count, F, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from curriculum.models import ExerciseRevision, GrammarTopic

from .models import ExerciseAttempt
from .public import attempt_result, public_exercise
from .services import AttemptError, dispute, regrade, submit_attempt


class AttemptInput(serializers.Serializer[dict[str, Any]]):
    answer = serializers.JSONField()
    time_spent_ms = serializers.IntegerField(required=False, min_value=0, max_value=3_600_000)


class DisputeInput(serializers.Serializer[dict[str, str]]):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)


def _user(request: Request) -> User:
    assert isinstance(request.user, User)
    return request.user


class AttemptCreateView(APIView):
    @extend_schema(
        operation_id="attempt_create", request=AttemptInput, responses={201: OpenApiTypes.OBJECT}
    )
    def post(self, request: Request, revision_id: int) -> Response:
        revision = get_object_or_404(
            ExerciseRevision.objects.select_related("lesson_revision__lesson__unit"), pk=revision_id
        )
        data = AttemptInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            attempt = submit_attempt(
                _user(request),
                revision,
                data.validated_data["answer"],
                data.validated_data.get("time_spent_ms"),
            )
        except AttemptError as exc:
            raise ValidationError({"answer": [str(exc)]}) from exc
        return Response(attempt_result(attempt), status=status.HTTP_201_CREATED)


def _own_attempt(request: Request, attempt_id: int) -> ExerciseAttempt:
    return get_object_or_404(ExerciseAttempt, pk=attempt_id, user=_user(request))


class RegradeView(APIView):
    @extend_schema(
        operation_id="attempt_regrade", request=None, responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request: Request, attempt_id: int) -> Response:
        return Response(attempt_result(regrade(_own_attempt(request, attempt_id))))


class DisputeView(APIView):
    @extend_schema(
        operation_id="attempt_dispute", request=DisputeInput, responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request: Request, attempt_id: int) -> Response:
        data = DisputeInput(data=request.data)
        data.is_valid(raise_exception=True)
        dispute(_own_attempt(request, attempt_id), data.validated_data.get("comment", ""))
        return Response({"disputed": True})


def _published_translations() -> Any:
    """Translate exercise revisions of currently published lesson versions."""
    return ExerciseRevision.objects.filter(
        payload__type="translate",
        origin=ExerciseRevision.Origin.CURRICULUM,
        lesson_revision__lesson__published_revision=F("lesson_revision"),
    ).select_related("lesson_revision__lesson__unit")


class TranslateOptionsView(APIView):
    @extend_schema(operation_id="practice_translate_options", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        revisions = list(_published_translations())
        levels = sorted({r.lesson_revision.lesson.unit.level for r in revisions})
        counts: dict[str, int] = {}
        for r in revisions:
            for topic in r.payload.get("grammar_topics", []):
                counts[topic] = counts.get(topic, 0) + 1
        topics = [
            {"id": t.slug, "title": t.title, "level": t.level, "count": counts[t.slug]}
            for t in GrammarTopic.objects.filter(slug__in=counts)
        ]
        return Response({"levels": levels, "topics": topics})


class TranslateNextView(APIView):
    @extend_schema(
        operation_id="practice_translate_next",
        parameters=[
            OpenApiParameter(p, str, required=False) for p in ("level", "topic", "direction")
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        qs = _published_translations()
        if level := request.query_params.get("level"):
            qs = qs.filter(lesson_revision__lesson__unit__level=level)
        if topic := request.query_params.get("topic"):
            qs = qs.filter(payload__grammar_topics__contains=[topic])
        if direction := request.query_params.get("direction"):
            qs = qs.filter(payload__direction=direction)
        user = _user(request)
        last_verdict = (
            ExerciseAttempt.objects.filter(
                user=user, exercise_revision__exercise=OuterRef("exercise")
            )
            .order_by("-created_at")
            .values("verdict")[:1]
        )
        candidates = list(
            qs.annotate(
                tries=Count(
                    "exercise__revisions__attempts",
                    filter=Q(exercise__revisions__attempts__user=user),
                ),
                last=Subquery(last_verdict),
            )
        )
        if not candidates:
            raise NotFound("No translation exercises match these filters yet.")
        # Never tried first, then last answered wrong, then everything else.
        for group in (
            [c for c in candidates if c.tries == 0],
            [c for c in candidates if c.last == ExerciseAttempt.Verdict.INCORRECT],
            candidates,
        ):
            if group:
                choice = random.choice(group)
                break
        lesson = choice.lesson_revision.lesson
        return Response(
            {
                **public_exercise(choice),
                "lesson": {"id": lesson.slug, "title": lesson.title, "level": lesson.unit.level},
            }
        )
