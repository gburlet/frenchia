from typing import Any

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from . import services
from .models import VocabCard, VocabSet


def _user(request: Request) -> User:
    assert isinstance(request.user, User)
    return request.user


class SetListView(APIView):
    @extend_schema(operation_id="vocab_sets", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        user = _user(request)
        return Response({"sets": services.set_summaries(user), "stats": services.stats(user)})


class SetDetailView(APIView):
    @extend_schema(operation_id="vocab_set_detail", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request, slug: str) -> Response:
        vocab_set = get_object_or_404(VocabSet, slug=slug)
        return Response(services.set_detail(_user(request), vocab_set))


class LearnSetView(APIView):
    @extend_schema(
        operation_id="vocab_set_learn", request=None, responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request: Request, slug: str) -> Response:
        vocab_set = get_object_or_404(VocabSet, slug=slug)
        return Response(services.learn_set(_user(request), vocab_set))


class QueueView(APIView):
    @extend_schema(
        operation_id="vocab_queue",
        parameters=[
            OpenApiParameter("limit", int, required=False),
            OpenApiParameter("ahead", bool, required=False),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        try:
            limit = max(1, min(int(request.query_params.get("limit", 20)), 50))
        except ValueError:
            limit = 20
        ahead = request.query_params.get("ahead") in ("1", "true")
        return Response(services.queue(_user(request), limit=limit, learn_ahead=ahead))


class CheckInput(serializers.Serializer[dict[str, Any]]):
    answer = serializers.CharField(max_length=200, allow_blank=True)


class CheckView(APIView):
    @extend_schema(
        operation_id="vocab_card_check", request=CheckInput, responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request: Request, card_id: int) -> Response:
        card = get_object_or_404(
            VocabCard.objects.select_related("lexeme"), pk=card_id, user=_user(request)
        )
        data = CheckInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(services.check_recall(card.lexeme, data.validated_data["answer"]))


class ReviewInput(serializers.Serializer[dict[str, Any]]):
    rating = serializers.IntegerField(min_value=1, max_value=4)
    duration_ms = serializers.IntegerField(required=False, min_value=0, max_value=3_600_000)
    answer = serializers.CharField(required=False, allow_blank=True, max_length=200)
    check_result = serializers.CharField(required=False, allow_blank=True, max_length=12)


class ReviewView(APIView):
    @extend_schema(
        operation_id="vocab_card_review", request=ReviewInput, responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request: Request, card_id: int) -> Response:
        user = _user(request)
        get_object_or_404(VocabCard, pk=card_id, user=user)
        data = ReviewInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(services.review(user, card_id, **data.validated_data))
