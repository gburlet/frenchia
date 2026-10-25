from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from contentkit.conjugation import PERSONS

from . import services
from .services import DrillError


def _user(request: Request) -> User:
    assert isinstance(request.user, User)
    return request.user


class CatalogView(APIView):
    @extend_schema(operation_id="verbs_catalog", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        cat = services.catalog()
        return Response(
            {
                "tenses": services.tense_list(),
                "sets": [s.model_dump(mode="json") for s in cat.sets],
                "verbs": [services.verb_summary(cat, v) for v in cat.verbs()],
            }
        )


class VerbDetailView(APIView):
    @extend_schema(operation_id="verb_detail", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request, slug: str) -> Response:
        cat = services.catalog()
        infinitive = cat.by_slug(slug)
        if infinitive is None:
            raise NotFound("unknown verb")
        return Response(services.verb_detail(cat, infinitive, _user(request)))


class DrillInput(serializers.Serializer[dict[str, Any]]):
    set = serializers.CharField(required=False)
    verbs = serializers.ListField(child=serializers.CharField(), required=False, max_length=60)
    tenses = serializers.ListField(child=serializers.CharField(), min_length=1, max_length=12)
    persons = serializers.ListField(
        child=serializers.ChoiceField(choices=PERSONS), required=False, max_length=6
    )
    mode = serializers.ChoiceField(choices=["form", "context", "mixed"], default="mixed")
    count = serializers.IntegerField(min_value=1, max_value=services.MAX_DRILL, default=10)


class DrillView(APIView):
    @extend_schema(
        operation_id="verb_drill_create", request=DrillInput, responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request: Request) -> Response:
        data = DrillInput(data=request.data)
        data.is_valid(raise_exception=True)
        params = data.validated_data
        verbs = list(params.get("verbs", []))
        if set_id := params.get("set"):
            verb_set = next((s for s in services.catalog().sets if s.id == set_id), None)
            if verb_set is None:
                raise ValidationError({"set": ["unknown verb set"]})
            verbs += verb_set.verbs
        try:
            items = services.build_drill(
                _user(request),
                verbs=verbs,
                tenses=params["tenses"],
                persons=params.get("persons"),
                mode=params["mode"],
                count=params["count"],
            )
        except DrillError as exc:
            raise ValidationError({"detail": [str(exc)]}) from exc
        return Response({"items": items})


class AnswerInput(serializers.Serializer[dict[str, Any]]):
    infinitive = serializers.CharField(max_length=60)
    tense = serializers.CharField(max_length=40)
    person = serializers.ChoiceField(choices=PERSONS)
    answer = serializers.CharField(max_length=200, allow_blank=True, trim_whitespace=True)
    mode = serializers.ChoiceField(choices=["form", "table", "context"], default="form")
    sentence = serializers.DictField(required=False, allow_null=True)
    time_spent_ms = serializers.IntegerField(required=False, min_value=0, max_value=3_600_000)


class AnswersInput(serializers.Serializer[dict[str, Any]]):
    answers = AnswerInput(many=True, min_length=1, max_length=12)  # type: ignore[call-arg]


class AnswersView(APIView):
    """Grade one or more typed forms (a drill item, or a whole conjugation table)."""

    @extend_schema(
        operation_id="verb_answers", request=AnswersInput, responses={200: OpenApiTypes.OBJECT}
    )
    def post(self, request: Request) -> Response:
        data = AnswersInput(data=request.data)
        data.is_valid(raise_exception=True)
        user = _user(request)
        results = []
        try:
            for answer in data.validated_data["answers"]:
                results.append(services.check_answer(user, **answer))
        except DrillError as exc:
            raise ValidationError({"detail": [str(exc)]}) from exc
        return Response({"results": results})


class ProgressView(APIView):
    @extend_schema(operation_id="verb_progress", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        return Response(services.progress(_user(request)))
