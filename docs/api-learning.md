# Learning API (Phase 4)

All endpoints require a logged-in session. Send JSON, and send `X-CSRFToken` on POST.
Errors are `{"detail": "..."}`. Inference failures also carry `"code"`, e.g. `llm_unavailable`
(see `config/exceptions.py`).

## Curriculum

`GET /api/curriculum`
```json
{"levels": [{"level": "A2", "title": "Élémentaire", "summary": "...",
  "units": [{"id": "a2-u01-past", "title": "Raconter au passé", "objectives": ["..."],
    "lessons": [{"id": "a2-passe-compose-er", "title": "Le passé composé des verbes en -er",
                 "kind": "grammar", "published": true,
                 "progress": {"status": "in_progress", "completed_at": null}}]}]}]}
```
`progress.status` is one of `not_started`, `in_progress` or `completed`. Unpublished lessons are listed
with `"published": false`. They can't be opened yet.

## Lessons

`GET /api/lessons/{id}` returns 404 `{"detail": "..."}` when nothing is published.
```json
{"id": "...", "title": "...", "title_en": "...", "level": "A2",
 "unit": {"id": "...", "title": "..."}, "objectives": ["..."], "estimated_minutes": 33,
 "grammar_topics": [{"id": "passe-compose-avoir", "title": "Passé composé with avoir"}],
 "revision": {"id": 12, "content_version": 2},
 "sections": [ /* exactly as in content/schemas/lesson.schema.json (explanation, examples,
                  table, vocabulary, reading, regional_note) */ ],
 "exercises": [ /* public exercise objects, below */ ],
 "progress": {"status": "in_progress", "completed_at": null},
 "previous": {"id": "...", "title": "..."} | null,
 "next": {"id": "...", "title": "..."} | null}
```

**Public exercise objects never contain answers.** Answers are revealed in the attempt result.
```json
{"exercise_revision_id": 41, "id": "ex-04", "type": "fill_blank",
 "sentence": "Elle ___ à son ami.", "hint": "(parler)", "translation_en": "She spoke to her friend."}
{"exercise_revision_id": 42, "id": "ex-05", "type": "translate", "direction": "en_fr",
 "prompt": "I watched a movie last night.", "hint": "..."}
{"exercise_revision_id": 43, "id": "ex-09", "type": "multiple_choice",
 "question": "...", "options": ["...", "..."]}
{"exercise_revision_id": 44, "id": "ex-11", "type": "comprehension", "reading_id": "reading",
 "question": "...", "options": ["...", "..."]}
```

`POST /api/lessons/{id}/progress` takes `{"completed": true}`, or `{}` to mark the lesson in progress. It returns
the `progress` object.

## Attempts and grading

`POST /api/exercise-revisions/{exercise_revision_id}/attempts`

The body is `{"answer": "text"}` for translate and fill_blank, and `{"answer": 2}` (the option index) for
multiple_choice and comprehension. It can also include `"time_spent_ms": 12000`.

```json
{"attempt_id": 7, "status": "graded",
 "verdict": "correct" | "acceptable" | "incorrect" | null,
 "score": 0-100 | null,
 "grading": "deterministic" | "llm" | "pending",
 "correct_answer": "Elle a parlé à son ami.",
 "accepted_answers": ["..."],
 "correct_index": 1,
 "feedback": {
   "summary": "One short sentence.",
   "errors": [{"category": "preposition", "severity": "error", "span": "parlé son",
               "explanation": "parler takes à before a person"}],
   "corrected": "Elle a parlé à son ami." | null,
   "register_note": "..." | null,
   "accent_only": false},
 "explanation": "MCQ explanation" | null,
 "model": "gemma4:12b-it-qat" | null}
```
- `correct_index` is set only for choice types.
- **Translation grading usually takes a few seconds.** It returns immediately for an exact or accepted answer,
  or an accent-only mistake. Otherwise the local LLM grades it, which can take about 5–15 s, so show a
  "Checking your answer…" state.
- **If the LLM is down,** the response has `"status": "pending"`, `"grading": "pending"` and
  `verdict: null`, with the reference answers and a `feedback.summary` explaining the situation. Retry
  later with `POST /api/attempts/{attempt_id}/regrade`, which returns the same shape.

`POST /api/attempts/{attempt_id}/dispute` takes `{"comment": "optional"}` and returns `{"disputed": true}`. This
is "I think my answer is right": it puts the attempt in the Admin dispute queue, where the answer
can be added to the exercise's accepted answers.

## Translation Station

`GET /api/practice/translate/options`
```json
{"levels": ["A1", "A2"], "topics": [{"id": "passe-compose-avoir", "title": "...", "level": "A2", "count": 4}]}
```
`GET /api/practice/translate/next?level=A2&topic=passe-compose-avoir&direction=en_fr` returns one
public translate exercise, plus `"lesson": {"id", "title", "level"}`, the lesson it comes from.
Every query parameter is optional. If nothing matches, it returns 404 `{"detail": "..."}`. Exercises
the learner has never tried, or last got wrong, come first.
