"""Tutor API (docs/api-tutor.md). Thread management is ordinary DRF; replies stream as
server-sent events from async Django views."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from asgiref.sync import sync_to_async
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from inference.errors import InferenceError
from inference.llm import Message
from inference.providers import get_chat_model

from .context import ContextError, build_context, thread_title, validate_ref
from .models import TutorMessage, TutorThread
from .prompts import PROMPT_VERSION, SYSTEM

logger = logging.getLogger(__name__)
HISTORY_TURNS = 8
MAX_HISTORY_CHARS = 600
MAX_QUESTION_CHARS = 2000


def _thread_json(thread: TutorThread, *, messages: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": thread.pk,
        "title": thread.title,
        "context": thread.context,
        "updated_at": thread.updated_at,
    }
    if messages:
        data["messages"] = [
            {
                "id": m.pk,
                "role": m.role,
                "content": m.content,
                "status": m.status,
                "created_at": m.created_at,
            }
            for m in thread.messages.exclude(status=TutorMessage.Status.STREAMING)
        ]
    return data


def _user(request: Request) -> User:
    assert isinstance(request.user, User)
    return request.user


class ThreadListView(APIView):
    @extend_schema(operation_id="tutor_threads", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        threads = TutorThread.objects.filter(user=_user(request))[:20]
        return Response({"threads": [_thread_json(t) for t in threads]})

    @extend_schema(
        operation_id="tutor_thread_create",
        request=OpenApiTypes.OBJECT,
        responses={201: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        try:
            data = request.data if isinstance(request.data, dict) else {}
            ref = validate_ref(_user(request), data.get("context"))
        except ContextError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        user = _user(request)
        thread = TutorThread.objects.create(user=user, context=ref, title=thread_title(ref, user))
        return Response(_thread_json(thread, messages=True), status=status.HTTP_201_CREATED)


class ThreadDetailView(APIView):
    @extend_schema(operation_id="tutor_thread", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request, thread_id: int) -> Response:
        thread = get_object_or_404(TutorThread, pk=thread_id, user=_user(request))
        return Response(_thread_json(thread, messages=True))


# --- streaming --------------------------------------------------------------------------


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _prepare(
    user: User, thread: TutorThread, question: str, before: TutorMessage | None
) -> tuple[list[Message], str]:
    """Model input: persona + current context, the recent history, then the question."""
    context = build_context(user, thread.context, question)
    history = thread.messages.exclude(status=TutorMessage.Status.STREAMING).exclude(content="")
    if before is not None:
        history = history.filter(pk__lt=before.pk)
    turns = list(history.order_by("-pk")[:HISTORY_TURNS])[::-1]
    messages = [Message("system", SYSTEM.format(context=context.text))]
    messages += [Message(m.role, m.content[:MAX_HISTORY_CHARS]) for m in turns]  # type: ignore[arg-type]
    messages.append(Message("user", question))
    return messages, context.text


async def _stream_reply(
    assistant: TutorMessage, messages: list[Message], user_message_id: int
) -> AsyncGenerator[str]:
    chat = get_chat_model()
    started = time.perf_counter()
    parts: list[str] = []
    assistant.model = chat.model
    yield _sse("start", {"user_message_id": user_message_id, "message_id": assistant.pk})
    try:
        async for delta in chat.stream(messages, temperature=0.3, max_tokens=700):
            if not parts:
                assistant.first_token_ms = round((time.perf_counter() - started) * 1000)
            parts.append(delta)
            yield _sse("delta", {"text": delta})
        assistant.status = TutorMessage.Status.COMPLETE
    except (asyncio.CancelledError, GeneratorExit):
        # The learner pressed Stop or left: depending on the server path the stream is
        # cancelled or closed. Keep the partial reply either way.
        assistant.status = TutorMessage.Status.STOPPED
        raise
    except InferenceError as exc:
        assistant.status = TutorMessage.Status.ERROR
        yield _sse(
            "error",
            {
                "message_id": assistant.pk,
                "code": f"{exc.service}_unavailable"
                if "unavailable" in type(exc).__name__.lower()
                else f"{exc.service}_error",
                "detail": str(exc),
            },
        )
    finally:
        assistant.content = "".join(parts)
        assistant.latency_ms = round((time.perf_counter() - started) * 1000)
        await asyncio.shield(assistant.asave())
    if assistant.status == TutorMessage.Status.COMPLETE:
        yield _sse("done", {"message_id": assistant.pk, "status": assistant.status})


def _event_stream(body: AsyncIterator[str]) -> StreamingHttpResponse:
    response = StreamingHttpResponse(body, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


async def _authenticated(request: HttpRequest) -> User | None:
    user = await request.auser()
    return user if isinstance(user, User) and user.is_authenticated else None


async def stream_message(
    request: HttpRequest, thread_id: int
) -> HttpResponse | StreamingHttpResponse:
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)
    user = await _authenticated(request)
    if user is None:
        return JsonResponse({"detail": "Authentication credentials were not provided."}, status=403)
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON."}, status=400)
    question = str(body.get("content", "")).strip()
    if not question or len(question) > MAX_QUESTION_CHARS:
        return JsonResponse(
            {"content": [f"Ask a question of 1-{MAX_QUESTION_CHARS} characters."]}, status=400
        )
    thread = await TutorThread.objects.filter(pk=thread_id, user=user).afirst()
    if thread is None:
        return JsonResponse({"detail": "Not found."}, status=404)
    if "context" in body:
        try:
            thread.context = await sync_to_async(validate_ref)(user, body["context"])
        except ContextError as exc:
            return JsonResponse({"detail": str(exc)}, status=400)
        thread.title = await sync_to_async(thread_title)(thread.context, user)
    await thread.asave()
    user_message = await TutorMessage.objects.acreate(
        thread=thread, role=TutorMessage.Role.USER, content=question, context=thread.context
    )
    messages, snapshot = await sync_to_async(_prepare)(user, thread, question, user_message)
    assistant = await TutorMessage.objects.acreate(
        thread=thread,
        role=TutorMessage.Role.ASSISTANT,
        status=TutorMessage.Status.STREAMING,
        context=thread.context,
        context_snapshot=f"[{PROMPT_VERSION}]\n{snapshot}",
    )
    return _event_stream(_stream_reply(assistant, messages, user_message.pk))


async def retry_message(
    request: HttpRequest, message_id: int
) -> HttpResponse | StreamingHttpResponse:
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed."}, status=405)
    user = await _authenticated(request)
    if user is None:
        return JsonResponse({"detail": "Authentication credentials were not provided."}, status=403)
    assistant = (
        await TutorMessage.objects.select_related("thread")
        .filter(pk=message_id, role=TutorMessage.Role.ASSISTANT, thread__user=user)
        .afirst()
    )
    if assistant is None:
        return JsonResponse({"detail": "Not found."}, status=404)
    question = (
        await assistant.thread.messages.filter(role=TutorMessage.Role.USER, pk__lt=assistant.pk)
        .order_by("-pk")
        .afirst()
    )
    if question is None:
        return JsonResponse({"detail": "Nothing to retry."}, status=400)
    messages, snapshot = await sync_to_async(_prepare)(
        user, assistant.thread, question.content, question
    )
    assistant.status, assistant.content = TutorMessage.Status.STREAMING, ""
    assistant.context_snapshot = f"[{PROMPT_VERSION}]\n{snapshot}"
    await assistant.asave()
    return _event_stream(_stream_reply(assistant, messages, question.pk))
