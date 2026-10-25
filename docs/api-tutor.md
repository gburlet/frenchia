# Tutor API (Phase 5)

All endpoints need a logged-in session. POSTs need `X-CSRFToken`. The tutor uses the local LLM. When it
is down, streams end with an `error` event (see below) and the rest of the app keeps working.

## Context references

The browser never sends lesson text. It sends **IDs**, and the server builds the tutor's context
from them (lesson, exercise, your answer and its feedback, recurring mistakes, Québec usage):
```json
{"lesson_id": "a2-imparfait", "exercise_revision_id": 41, "attempt_id": 7}
```
All three are optional. Send whatever is in view. The `attempt_id` should be the latest graded attempt
on that exercise.

## Threads

`GET /api/tutor/threads` returns
`{"threads": [{"id", "title", "updated_at", "context": {...context ref...}}]}`, newest first, at most 20.

`GET /api/tutor/threads/{id}` returns
`{"id", "title", "context": {...}, "messages": [{"id", "role": "user"|"assistant", "content", "status": "complete"|"stopped"|"error", "created_at"}]}`.

`POST /api/tutor/threads` takes `{"context": {...context ref...}}` and returns 201 with the thread, with no messages. The title is
derived from the context, e.g. « L'imparfait · ex-04 ».

## Streaming a reply

`POST /api/tutor/threads/{id}/messages` takes `{"content": "Why is it « à » here?", "context": {...optional...}}`

The response is `text/event-stream` (server-sent events over the POST response; use `fetch` and read
the body, not `EventSource`). Events:
```
event: start
data: {"user_message_id": 10, "message_id": 11}

event: delta
data: {"text": "Because "}

event: done
data: {"message_id": 11, "status": "complete"}

event: error
data: {"message_id": 11, "code": "llm_unavailable", "detail": "The local AI tutor isn't running."}
```
- `context` updates the thread's context if it's given. Use this when the learner moves to another exercise and keeps chatting.
- **Stop:** abort the fetch. The server keeps the partial reply with `"status": "stopped"`.
- Errors before streaming starts (validation, unknown thread) are normal JSON 4xx responses.
- Replies are Markdown in English, with French examples.

`POST /api/tutor/messages/{assistant_message_id}/retry` regenerates that reply, streaming exactly as
above. It's for `error` and `stopped` messages, or to get another answer.
