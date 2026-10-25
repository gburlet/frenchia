# Verb & Vocabulary Station API (Phase 6)

All endpoints are session-authenticated JSON under `/api/` (same client as the rest of the
SPA: `src/lib/api/client.ts`, CSRF handled there). Grading is deterministic; no endpoint here
calls the LLM.

## Verb Station

Tense keys: `indicatif.present`, `indicatif.futur_proche`, `indicatif.passe_compose`,
`indicatif.imparfait`, `indicatif.futur_simple`, `imperatif.present`, `conditionnel.present`,
`indicatif.plus_que_parfait`, `subjonctif.present`, `conditionnel.passe`,
`indicatif.futur_anterieur`, `subjonctif.passe`, `indicatif.passe_simple` (tables only,
`drill: false`). Persons: `je tu il nous vous ils` (impératif: `tu nous vous`).

### `GET /api/verbs`
```jsonc
{
  "tenses": [{ "key": "indicatif.present", "label": "Présent", "label_en": "Present",
               "level": "A1", "mood": "Indicatif", "compound": false, "drill": true }],
  "sets": [{ "id": "essentiels", "title": "Les essentiels", "title_en": "The essentials",
             "level": "A1", "description": "…", "verbs": ["être", "avoir", …],
             "tenses": ["indicatif.present", …] }],          // suggested tenses for the set
  "verbs": [{ "infinitive": "aller", "slug": "aller", "en": "to go" /* or null */,
              "group": 3, "auxiliary": "être" /* avoir|être|both */, "pronominal": false,
              "sentences": 14 /* context sentences available */, "sets": ["essentiels"] }]
}
```
~330 verbs, sorted alphabetically ignoring accents and `se`.

### `GET /api/verbs/<slug>` (slug: `etre`, `se-lever`, `s-asseoir`) → 404 if unknown
```jsonc
{ /* everything in the verbs[] summary */,
  "note": "One English usage note" /* or null */,
  "participle_past": "allé", "participle_present": "allant",
  "table": [{ "tense": "indicatif.present", "label": "Présent", "label_en": "Present",
              "mood": "Indicatif", "level": "A1",
              "rows": [{ "person": "je", "form": "vais", "variants": [],
                         "said": "je vais" /* with subject: speak this */ }] }],
  "examples": [{ "tense": "indicatif.passe_compose", "tense_label": "Passé composé",
                 "person": "il", "fr": "Ma blonde est allée au dépanneur.",
                 "en": "…", "form": "est allée", "region": "qc" /* or common */ }],
  "mastery": [{ "tense": "indicatif.present", "attempts": 4, "ewma": 0.81 }] }
```
Table order is pedagogical (présent, futur proche, passé composé, imparfait, futur simple,
impératif, conditionnel, plus-que-parfait, subjonctif, B2 compounds, passé simple last).

### `POST /api/verbs/drills`
Body: `{ "set"?: "essentiels", "verbs"?: ["aller"], "tenses": ["indicatif.present"],
"persons"?: ["je","nous"], "mode": "form" | "context" | "mixed" (default mixed),
"count": 1-40 (default 10) }`. Needs `set` and/or `verbs`.
400 `{ "detail": ["no context sentences for these verbs and tenses yet"] }` and similar.
```jsonc
{ "items": [{ "infinitive": "partir", "slug": "partir", "en": "to leave",
              "tense": "indicatif.passe_compose", "tense_label": "Passé composé",
              "person": "il", "subject": "il/elle/on" /* "" for impératif */,
              "mode": "form" | "context",
              "sentence": null | { "bank": "partir", "version": 2, "index": 0,
                                   "before": "Hier soir, ma blonde ", "after": " tard.",
                                   "en": "Last night my girlfriend left late.",
                                   "region": "qc" } }] }
```
Answers are never sent to the client before grading. Items favour weak/unseen (verb, tense).

### `POST /api/verbs/answers`
Body: `{ "answers": [ { "infinitive", "tense", "person", "answer": "je suis allé",
"mode": "form" | "table" | "context", "sentence"?: {bank, version, index} /* echo the item's */,
"time_spent_ms"?: 4200 } ] }` (1-12 answers: one drill item, or a whole table).
The subject pronoun is optional in answers (`suis allé` = `je suis allé`).
```jsonc
{ "results": [{ "result": "correct" | "accent" | "incorrect", "correct": false,
                "expected": "je suis allé" /* context mode: the form only */,
                "accepted": ["suis allé", "suis allée"],
                "diagnosis": "" | "accents" | "infinitive" | "wrong_person" | "wrong_tense"
                           | "wrong_auxiliary" | "auxiliary_form" | "participle"
                           | "agreement" | "spelling" | "incorrect",
                "message": "aller takes être in compound tenses: suis allé.",
                "said": "je suis allé" /* text to speak: form with subject, or the full
                                          sentence in context mode */ }] }
```
400 when a context sentence changed since the drill was built (start a new drill).

### `GET /api/verbs/progress`
`{ "attempts": 120, "correct": 97, "verbs_practiced": 18,
   "weak_spots": [{ "infinitive", "slug", "tense", "tense_label", "attempts", "ewma" }] }`

## Vocabulary Station

### `GET /api/vocab/sets`
```jsonc
{ "sets": [{ "slug": "a1-hiver", "kind": "theme" | "lesson", "level": "A1",
             "title": "La météo et l'hiver", "title_en": "Weather and winter",
             "lesson": null | "a2-imparfait", "size": 22,
             "in_deck": 22 /* words added */, "seen": 10, "due": 4 }],
  "stats": { "cards": 44, "words": 22, "due_now": 4, "due_today": 9, "new_waiting": 20,
             "new_remaining_today": 11, "reviews_today": 16, "mature": 0 } }
```
Theme sets are ordered by level then theme; lesson sets (vocabulary from published lessons)
come after them.

### `GET /api/vocab/sets/<slug>`
`{ slug, kind, level, title, title_en, lesson, "words": [Lexeme & { "status": "not_started" |
"new" | "learning" | "due" }] }`

Lexeme:
```jsonc
{ "id": 12, "fr": "tuque", "display": "la tuque" /* with article for nouns */,
  "article": "la" | "le" | "l'" | "", "en": "winter hat", "pos": "noun" /* verb adjective
  adverb expression other */, "gender": "f" | "m" | null, "plural": null | "yeux",
  "region": "qc" | "fr" | "common", "formality": "standard" | "familiar" | "formal",
  "example_fr": "…" | null, "example_en": "…" | null,
  "note": "France: un bonnet" | null, "set": "a2-vetements" }
```

### `POST /api/vocab/sets/<slug>/learn` → `{ "added": 20, "skipped": 2 }`
Adds every word as two cards: `recognize` (French → English) and `recall` (English → French).
Words already in the deck from another set are skipped.

### `GET /api/vocab/review?limit=20&ahead=1`
```jsonc
{ "cards": [{ "id": 7, "direction": "recognize" | "recall", "is_new": true,
              "due": "2026-10-25T02:08:26Z", "lexeme": Lexeme,
              "previews": { "1": 60, "2": 360, "3": 600, "4": 1036800 } }],
  "due_count": 4, "new_remaining_today": 11, "next_due": "…" | null }
```
Due cards first, then new cards (daily limit: profile `daily_new_cards`, default 15). A word's
recall card is only offered after its recognition card has been seen once. `previews` gives the
seconds until the next review for each rating (1 Again, 2 Hard, 3 Good, 4 Easy); show them
on the rating buttons ("1 min", "10 min", "12 d"). `ahead=1` includes learning cards due in
the next 20 minutes. When `cards` is empty and `next_due` is near, offer "learn ahead".

### `POST /api/vocab/cards/<id>/check` `{ "answer": "le tuque" }` (recall cards)
`{ "result": "correct" | "accent" | "article" | "gender" | "incorrect", "correct": false,
   "expected": "la tuque", "message": "tuque is feminine: la tuque.", "suggested_rating": 1 }`
Nouns need their article (or un/une) so gender is practised. The learner still picks the
rating; pre-select `suggested_rating`.

### `POST /api/vocab/cards/<id>/review`
`{ "rating": 1-4, "duration_ms"?: 5300, "answer"?: "…", "check_result"?: "gender" }` →
`{ "id": 7, "due": "…", "interval_seconds": 600 }`
