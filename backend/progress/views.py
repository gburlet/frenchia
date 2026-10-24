from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from curriculum.api import progress_dict
from curriculum.models import Lesson

from .models import LessonProgress


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
