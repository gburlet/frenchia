import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from asgiref.sync import sync_to_async
from django.test import AsyncClient, Client

from accounts.models import User
from contentkit.tests.factories import make_repo
from curriculum.importer import import_content
from curriculum.models import ExerciseRevision
from exercises.models import ExerciseAttempt
from inference.errors import InferenceUnavailable
from inference.fakes import FakeChatModel
from inference.llm import Message
from tutor.context import build_context
from tutor.models import TutorMessage, TutorThread
from tutor.views import _stream_reply

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def setup(settings: Any, tmp_path: Path) -> dict[str, Any]:
    root = make_repo(tmp_path / "content")
    settings.CONTENT_DIR = root
    (root / "reference").mkdir()
    (root / "reference" / "quebec.yaml").write_text(
        "- {term: magasiner, match: ['\\bmagasin'], meaning: to go shopping,\n"
        "   france: faire du shopping, formality: standard}\n"
    )
    import_content(root, publish=True)
    user = User.objects.create_user("marie", password="pw-123456789")
    revision = ExerciseRevision.objects.get(exercise__stable_id="a2-passe-compose-er/ex-02")
    attempt = ExerciseAttempt.objects.create(
        user=user,
        exercise_revision=revision,
        answer="Nous sommes magasiné.",
        prompt_snapshot=revision.payload,
        status="graded",
        grading="llm",
        verdict="incorrect",
        score=50,
        feedback={
            "errors": [
                {
                    "category": "auxiliary",
                    "severity": "error",
                    "span": "sommes",
                    "explanation": "magasiner takes avoir",
                }
            ],
            "corrected": "Nous avons magasiné.",
        },
    )
    return {"user": user, "revision": revision, "attempt": attempt}


def events(raw: str) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for frame in raw.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


async def read(response: Any) -> str:
    return "".join(
        [
            chunk.decode() if isinstance(chunk, bytes) else chunk
            async for chunk in response.streaming_content
        ]
    )


def test_context_is_built_from_ids_with_ownership(setup: dict[str, Any]) -> None:
    ctx = build_context(setup["user"], {"attempt_id": setup["attempt"].pk}, "Pourquoi avoir ?")
    assert "Le passé composé des verbes en -er" in ctx.text
    assert "The learner answered: «Nous sommes magasiné.»" in ctx.text
    assert "auxiliary: «sommes»" in ctx.text and "can be wrong" in ctx.text
    assert "magasiner: to go shopping" in ctx.text  # lexicon matched from the exercise
    assert ctx.title == "PC -er · ex-02"  # curriculum outline title (the fixture abbreviates it)
    hint_only = build_context(setup["user"], {"exercise_revision_id": setup["revision"].pk})
    assert "NOT answered" in hint_only.text and "Accepted answers" in hint_only.text

    other = User.objects.create_user("paul", password="pw-123456789")
    client = Client()
    client.force_login(other)
    response = client.post(
        "/api/tutor/threads",
        {"context": {"attempt_id": setup["attempt"].pk}},
        content_type="application/json",
    )
    assert response.status_code == 400  # someone else's attempt


async def test_streams_reply_and_persists(setup: dict[str, Any]) -> None:
    client = AsyncClient()
    await client.aforce_login(setup["user"])
    created = await client.post(
        "/api/tutor/threads",
        {"context": {"attempt_id": setup["attempt"].pk}},
        content_type="application/json",
    )
    thread_id = created.json()["id"]
    chat = FakeChatModel(lambda messages: "Magasiner prend avoir : nous avons magasiné.")
    with patch("tutor.views.get_chat_model", return_value=chat):
        response = await client.post(
            f"/api/tutor/threads/{thread_id}/messages",
            {"content": "Pourquoi « avoir » ?"},
            content_type="application/json",
        )
        assert response["Content-Type"] == "text/event-stream"
        frames = events(await read(response))
    kinds = [kind for kind, _ in frames]
    assert kinds[0] == "start" and kinds[-1] == "done" and kinds.count("delta") > 1
    assert (
        "".join(d["text"] for k, d in frames if k == "delta").strip()
        == "Magasiner prend avoir : nous avons magasiné."
    )
    sent = chat.calls[0]["messages"]
    assert sent[0].role == "system" and "Nous sommes magasiné." in sent[0].content
    assert sent[-1].content == "Pourquoi « avoir » ?"
    reply = await TutorMessage.objects.aget(pk=frames[0][1]["message_id"])
    assert (reply.status, reply.content.strip(), reply.model) == (
        "complete",
        "Magasiner prend avoir : nous avons magasiné.",
        "fake-llm",
    )
    detail = (await client.get(f"/api/tutor/threads/{thread_id}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]


async def test_llm_down_gives_error_event_then_retry(setup: dict[str, Any]) -> None:
    client = AsyncClient()
    await client.aforce_login(setup["user"])
    thread = await TutorThread.objects.acreate(user=setup["user"], title="t", context={})

    def down(messages: Sequence[Message]) -> str:
        raise InferenceUnavailable("llm", "The language model service is not running")

    with patch("tutor.views.get_chat_model", return_value=FakeChatModel(down)):
        frames = events(
            await read(
                await client.post(
                    f"/api/tutor/threads/{thread.pk}/messages",
                    {"content": "Bonjour ?"},
                    content_type="application/json",
                )
            )
        )
    assert frames[-1][0] == "error" and frames[-1][1]["code"] == "llm_unavailable"
    message_id = frames[-1][1]["message_id"]
    assert (await TutorMessage.objects.aget(pk=message_id)).status == "error"
    with patch("tutor.views.get_chat_model", return_value=FakeChatModel(lambda m: "Salut !")):
        frames = events(await read(await client.post(f"/api/tutor/messages/{message_id}/retry")))
    assert frames[-1] == ("done", {"message_id": message_id, "status": "complete"})
    assert (await TutorMessage.objects.aget(pk=message_id)).content.strip() == "Salut !"


async def test_stopping_keeps_the_partial_reply(setup: dict[str, Any]) -> None:
    thread = await TutorThread.objects.acreate(user=setup["user"], title="t", context={})
    assistant = await TutorMessage.objects.acreate(
        thread=thread, role="assistant", status="streaming"
    )

    async def slow(*args: Any, **kwargs: Any) -> AsyncIterator[str]:
        yield "Le passé "
        yield "composé "
        yield "se forme…"

    chat = FakeChatModel()
    with patch("tutor.views.get_chat_model", return_value=chat), patch.object(chat, "stream", slow):
        stream = _stream_reply(assistant, [Message("user", "?")], 1)
        await stream.__anext__()  # start
        await stream.__anext__()  # first delta
        await stream.aclose()  # the browser went away
    saved = await TutorMessage.objects.aget(pk=assistant.pk)
    assert (saved.status, saved.content) == ("stopped", "Le passé ")


async def test_validation_and_auth(setup: dict[str, Any]) -> None:
    anonymous = AsyncClient()
    assert (
        await anonymous.post(
            "/api/tutor/threads/1/messages", {"content": "x"}, content_type="application/json"
        )
    ).status_code == 403
    client = AsyncClient()
    await client.aforce_login(setup["user"])
    thread = await TutorThread.objects.acreate(user=setup["user"], title="t", context={})
    url = f"/api/tutor/threads/{thread.pk}/messages"
    assert (
        await client.post(url, {"content": ""}, content_type="application/json")
    ).status_code == 400
    assert (
        await client.post(
            url, {"content": "x", "context": {"attempt_id": 999}}, content_type="application/json"
        )
    ).status_code == 400
    assert (
        await client.post(
            "/api/tutor/threads/999/messages", {"content": "x"}, content_type="application/json"
        )
    ).status_code == 404
    assert await sync_to_async(TutorMessage.objects.count)() == 0


def test_verb_facts_ground_the_tutor(setup: dict[str, Any]) -> None:
    from contentkit.reference import Reference

    ref = Reference(Path("."))
    ref.verbs = {
        "aller": {
            "auxiliary": "être",
            "participle_past": "allé",
            "participle_present": "allant",
            "forms": {
                "indicatif.present": {"je": "vais", "nous": "allons"},
                "indicatif.passe_compose": {"je": "suis allé", "nous": "sommes allés"},
            },
        },
        "partir": {
            "auxiliary": "être",
            "participle_past": "parti",
            "participle_present": "partant",
            "forms": {
                "indicatif.present": {"je": "pars", "nous": "partons"},
                "indicatif.passe_compose": {"je": "suis parti", "nous": "sommes partis"},
            },
        },
    }
    assert ref.verbs_in("Hier, nous avons allé au parc.") == ["aller"]  # 'avons' is ignored
    assert ref.verbs_in("Elles sont parties tôt") == ["partir"]  # agreed participle
    assert ref.verb_facts("aller") == (
        "aller: auxiliary être; past participle allé; présent je vais, "
        "nous allons; passé composé je suis allé, nous sommes allés"
    )
    with patch("tutor.context.content.reference", return_value=ref):
        ctx = build_context(
            setup["user"], {"attempt_id": setup["attempt"].pk}, "Pourquoi pas « nous avons allé » ?"
        )
    assert "Verified verb facts" in ctx.text and "aller: auxiliary être" in ctx.text
