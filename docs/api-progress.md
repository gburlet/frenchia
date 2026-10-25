# Progress API (Phase 7)

All endpoints need a logged-in session; POSTs need `X-CSRFToken`. See ADR 0006 for the rules.

## Dashboard

`GET /api/dashboard`
```json
{"today": "2026-10-25",
 "streak": {"current": 3, "longest": 7, "studied_today": true},
 "minutes": {"today": 9, "week": 41},
 "accuracy_week": {"graded": 20, "accuracy": 0.75},
 "history": [{"date": "2026-10-12", "items": 4, "minutes": 2,
              "by_kind": {"exercises": 3, "verbs": 1}}],
 "lessons": {"published": 6, "completed": 2},
 "vocab": { /* same as the "stats" object of GET /api/vocab/sets */ },
 "topics": [{"id": "passe-compose-etre", "title": "...", "level": "A2", "attempts": 6,
             "accuracy": 0.42, "last_practiced": "..."}],
 "weak_topics": [{"id": "...", "title": "...", "level": "A2", "accuracy": 0.42, "attempts": 6,
                  "recent_mistakes": 2, "reason": "42% recent accuracy over 6 tries; ..."}],
 "verb_tenses": [{"tense": "passe_compose", "label": "Passé composé", "attempts": 10,
                  "accuracy": 0.6}],
 "mistakes": [{"category": "auxiliary", "count": 3}],
 "review": {"id": 3, "items": 9, "answered": 4, "extras": "running"} | null}
```
- `history` covers the last 14 local days, oldest first.
- `topics` are ordered weakest first.
- `accuracy` is `null` when nothing was graded.

## Review sets

`GET /api/review` returns `{"current": ReviewSet | null, "weak_topics": [...]}`.

`POST /api/review` starts a new set, closing any unfinished one, and returns 201 with the
`ReviewSet`. It returns 404 `{"detail": "Nothing to review yet: ..."}` when the learner has no
weak topics and hasn't opened any lesson.

`GET /api/review/{id}` returns the `ReviewSet`. `POST /api/review/{id}/complete` marks it done.

```json
{"id": 3, "created_at": "...", "completed_at": null,
 "topics": [ /* weak topics at creation */ ],
 "extras": "none" | "queued" | "running" | "ready" | "failed",
 "items": [{"exercise": { /* public exercise, as in the lesson API */ },
            "topic": {"id": "...", "title": "..."},
            "source": "missed" | "unseen" | "refresh" | "generated",
            "source_label": "answered wrong last time",
            "ai_generated": false,
            "lesson": {"id": "...", "title": "..."},
            "result": "correct" | "acceptable" | "incorrect" | "pending" | null}]}
```

Answer items with the usual `POST /api/exercise-revisions/{id}/attempts`. `result` is the
latest verdict since the set was created. Poll while `extras` is `queued` or `running`:
generated items are appended at the end.
