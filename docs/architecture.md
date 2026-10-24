# Frenchia: Architecture & Implementation Plan (approved 2026-10-24)

## Context

This is a greenfield, local-first French learning app for one learner who is at A2 and aiming for B2, with a **Québec-first** focus. It combines a structured CEFR curriculum with local LLM tutoring and Kokoro TTS. There are no paid inference APIs. Claude builds the software. The **local LLM** generates the learning content, and that content goes through deterministic validation and human review. STT and the Conversation Station are on the roadmap only.

The repo currently contains only `kokoro-benchmark/`, which is not a git repo. Its results: on this machine, native MLX Kokoro is 4–6× faster than Docker ONNX. RTF is about 0.05, a short phrase takes 0.13 s, 650 chars take 1.7 s, and peak memory is about 340 MB RSS plus 2.7 GB Metal.

### Environment findings (these differ from the brief)
| Item | Brief | Actual |
|---|---|---|
| Chip / RAM | M1/M2, 24 GB | **Apple M2 Pro (6P+4E CPU, 16-core GPU), 16 GB**, ~200 GB/s bandwidth |
| OS | macOS 27 | **macOS 26.4.1** (Metal 4) |
| Docker | — | Docker Desktop 29.4.1, VM capped at 7.75 GiB. Other projects (metaminer, bluedot, elasticsearch, about 4 GB) are running. Model Runner is disabled. |
| Tooling | — | just 1.50, uv 0.11.8, node 26.12, Homebrew, psql 18.4, python3 3.14. **No** Ollama, ffmpeg, or espeak-ng (Kokoro ships espeak via `espeakng-loader`). |
| Ports in use | — | 3000, 3001, 5000, 5433, 5434, 6379, 7000, 8001, 8080, 9200, 9300 |

**Decision (user):** other Docker stacks will be stopped while Frenchia is in use. That makes a 12B-class model viable if it wins the bake-off. `just start` will warn when non-Frenchia containers are running or memory pressure is high.

### Curriculum reference findings
learnfrenchwithclemence.com/course-curriculum is public and has no login wall. It exposes **titles only**: 180 day-lessons (30 per level, A1–C2) plus supplementary libraries such as word comparisons, false friends, ~90 vocab themes, and short stories. Several lists are truncated ("+16", "+90"), and C1/C2 are thematic, with no grammar labels. We use it **only as a structural reference** for topic ordering, for example A2: passé composé (avoir/être) → imparfait → PC vs imparfait → object pronouns → futur simple → impératif. No text is reproduced. This limitation goes into `docs/curriculum-sources.md`.

---

## A. Architecture

```
 Browser (React SPA, :5173)
   │  /api/*, /admin/*, /static/*  (Vite dev proxy → same origin)
   ▼
┌───────────── Docker Compose (project "frenchia", 127.0.0.1 only) ──────────────┐
│  frontend: Vite dev server ──proxy──▶ backend: Django 6.1 / DRF on uvicorn (ASGI)│
│                                         │  ▲                                     │
│  worker: same image, `manage.py db_worker` (django.tasks + django-tasks-db)      │
│                                         │  │ ORM                                 │
│  db: postgres:18 (not published; optional 127.0.0.1:5435)                       │
│  bind mounts: ./content (rw for ContentWriter), ./var/audio (TTS cache)          │
└─────────────────────────────────────────┼───────────────────────────────────────┘
                                          │ http://host.docker.internal:{11435,8791}
┌──────────── macOS host, launchd user agents (ca.amii.frenchia.*) ────────────────┐
│  llm: Ollama 0.40.x (pinned binary), 127.0.0.1:11435, MLX runner + xgrammar     │
│  tts: FastAPI + mlx-audio Kokoro-82M, 127.0.0.1:8791, OpenAI-style /v1/audio/speech│
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Key flows**
1. **Translation attempt:** React POSTs an answer. Django normalizes it and checks it deterministically against the accepted answers. On a miss, it calls the LLM with a JSON-schema-constrained evaluation, post-validates the result, and stores the `ExerciseAttempt` and `MistakeOccurrence` rows. It then updates `TopicMastery` and returns the feedback.
2. **TTS:** React POSTs `{text, speed}` to `/api/audio`. Django computes `sha256(norm_text|voice|speed|model_rev)`. On a cache hit it returns `/api/audio/<hash>.wav` straight away. On a miss it calls the TTS service, writes `var/audio/<hash>.wav` atomically, and returns the URL. The `<audio>` element plays it with immutable caching. Long passages are split per sentence, so playback starts quickly and the current sentence can be highlighted.
3. **Tutor:** the drawer sends `{thread_id, context_ref: {lesson_rev, exercise_rev, attempt_id}, message}`. Django builds the context **server-side** from the IDs, then streams SSE from an async view, which uses httpx to stream from Ollama. The finished message is persisted.
4. **Content pipeline:** the curriculum node and a versioned prompt go to the worker job. The LLM returns constrained JSON in small steps. The output goes through Pydantic validation, then deterministic quality checks. ContentWriter writes the YAML draft. The draft is reviewed in Admin (preview, diff, report), then approved, imported, and published. You commit with git.

## B. Technical decisions

| Area | Decision | Why |
|---|---|---|
| **LLM runtime** | **Ollama 0.40.11, a project-owned instance.** A pinned `ollama-darwin.tgz` with sha256 lives in `.tools/`. Settings: `OLLAMA_HOST=127.0.0.1:11435`, `MAX_LOADED_MODELS=1`, `NUM_PARALLEL=1`, `KEEP_ALIVE=30m`, `CONTEXT_LENGTH=8192`. | Since 0.40, Ollama runs Gemma 4 and Qwen 3.5 on **MLX by default**. Its MLX runner has **xgrammar constrained decoding** (verified in source), so JSON-schema output is reliable. It is OpenAI-compatible, streams, pulls and manages models, and is a single binary. **mlx-lm 0.32.2's server has no `response_format`/schema support** (verified). Docker Model Runner is tied to Docker Desktop's lifecycle and is disabled here. The non-default port keeps it separate from any global Ollama. The provider rejects `:cloud` models. |
| **LLM model** | A **bake-off gate in Phase 2**. Candidates: `gemma4:12b-it-qat` (7.2 GB, the provisional favourite now that the other stacks are stopped), `qwen3.5:9b` (6.6 GB), `ministral-3:8b` (6.0 GB, GGUF/llama.cpp runner), with `qwen3.5:4b` or `gemma4:e4b` as a fast fallback tier. All are Apache 2.0. Thinking is off for interactive calls. | Web sources contain no trustworthy French or Québec benchmarks for these sizes, so we measure ourselves against a curated eval. On a 16 GB machine, a 12B model (~8 GB with KV cache) plus Kokoro must fit under the ~10.7 GB default Metal working-set limit. Ollama's speed ceiling is about bandwidth ÷ weight size, so expect ~18–25 tok/s for 12B and ~25–30 tok/s for 9B. |
| **TTS service** | A thin **FastAPI wrapper (own code, about 200 lines) around `mlx_audio.tts.utils.load_model`**. Pins: Python 3.12 (misaki needs <3.13), `mlx-audio==0.6.1`, `mlx==0.32.4`, model `mlx-community/Kokoro-82M-bf16`, all locked with uv. Endpoints: `GET /health`, `GET /v1/audio/voices`, `POST /v1/audio/speech {model,input,voice=ff_siwis,speed 0.5–1.5,response_format=wav}`. Behaviour: load and warm up at startup, synthesize under a single lock, add our own sentence chunker (mlx-audio logs "chunking not implemented" for French), call `mx.set_cache_limit`, cap input length, return typed JSON errors. | The bundled `mlx_audio.server` brings in STT, websockets, VAD and on-demand HuggingFace downloads, all of which the MVP excludes. An OpenAI-style contract makes the service swappable with Ollama's new `/v1/audio/speech` or mlx-audio's server. Streaming isn't needed (RTF is about 0.05, and sentence chunks are below 1 s). **ff_siwis is Kokoro's only French voice (grade B−, France accent)**, which you have accepted. |
| **Process orchestration** | **launchd user agents.** Plists are rendered from `ops/launchd/*.plist.tmpl` into `var/launchd/`, not `~/Library/LaunchAgents`, so nothing starts at login. `just start` runs `launchctl bootstrap gui/$UID`, `just stop` runs `bootout` on our labels only, and `just restart` runs `kickstart -k`. Agents use `KeepAlive {SuccessfulExit:false}` and `ThrottleInterval`. Logs go to `var/log/{llm,tts}.log`. Docker is managed with `docker compose -p frenchia` only. | Crash restart and clean ownership, with no PID files. Unrelated containers and inference processes are never touched. |
| **Docker→host** | `host.docker.internal` reaches services bound to **host 127.0.0.1**. This is Docker Desktop's forwarding behaviour and is **verified first in Phase 2**. The fallback is binding to the vmnet bridge IP, never `0.0.0.0`. All published container ports bind to `127.0.0.1`. | Nothing is exposed to the LAN, and the inference services stay unauthenticated but loopback-only. |
| **Backend serving** | Django 6.1 + DRF 3.18 on **uvicorn (ASGI)** in Docker (Python 3.13). DRF views are sync. Only the SSE endpoints (tutor, generation progress) are async views using `httpx.AsyncClient`. | ASGI is justified by long-lived LLM streaming. Under WSGI, every 10–20 s LLM call pins a worker. |
| **Background jobs** | **Django Tasks (built into 6.x) + `django-tasks-db` 0.13** ORM backend. A `worker` compose service runs `db_worker`. | Covers content generation, audio pre-warming and personalized review sets with no Redis or Celery. Domain state lives in our `GenerationJob` model. |
| **Content format** | **YAML on disk** (block scalars give reviewable prose diffs). **Pydantic v2 models are the single source of truth** for schemas. They live in `backend/contentkit/`, a plain package with no Django imports. They export JSON Schema to `content/schemas/` for editor validation and Ollama `format`. LLMs emit JSON, and ContentWriter serializes canonical YAML. | Strong typing end to end. The same models are used by the generator, validator and importer. |
| **Import/publish** | Files are the source of truth, and the DB is a versioned projection (detailed in C and Phase 3). | Satisfies the ingestion rules: idempotency, versioning, rollback and history preservation. |
| **Frontend** | React 19 + TS + Vite, **React Router 7** (data/library mode), **TanStack Query** for server state, local React context only for UI state (tutor drawer, audio player). Tailwind v4 + shadcn/ui themed from the style guide as CSS variables. Lucide icons. **openapi-typescript** types generated from the drf-spectacular schema. | No global store is needed. Typed API end to end. |
| **Theme** | The style guide is dark-only, so MVP ships **dark only**, built on tokens so a light theme can be added later. Fonts: `"Avenir LT Pro", Avenir, "Helvetica Neue"…`. macOS ships Avenir (Heavy 800), so the design renders correctly with no font licensing. | Matches the style guide. |
| **Auth** | Custom `accounts.User` from day one, with Django **session auth + CSRF**. The SPA is same-origin via the proxy. `just setup` creates the learner/superuser from `.env`. | Simplest secure option, and Admin gets the same login. Multi-user stays possible later. |
| **TTS cache** | A content-addressed WAV file cache in `var/audio/` with no DB table. Lesson publication enqueues pre-warming. `just audio-prune` removes old entries. WAV only, so no ffmpeg. | Repeated lesson audio is instant, and the cache is trivially invalidated by model or voice changes. |
| **Conjugation data** | A deterministic reference at `content/reference/conjugations/*.json`, **built offline** by `just build-reference` from **verbecc 2.0.3 (LGPL)** for about 300 frequent verbs and **cross-checked against mlconjug3 (MIT)**. Disagreements go to a review list. | The runtime never asks the LLM whether a conjugation is correct. |
| **Lexical data** | **Lexique 3.83** (CC BY-SA; attribution recorded) for gender, POS and frequency checks on vocabulary. A **hand-curated `content/reference/quebec.yaml`** lexicon (QC term ↔ France term, register, notes; OQLF/BDL as the reference) is used for prompt grounding and for checking Québec claims. | This is the guard against 9–12B models hallucinating québécismes. |
| **SRS** | **FSRS via `fsrs` 6.3 (MIT)** with 4-button ratings. | A small, well-understood library that beats SM-2. Trivial to integrate. |

**Memory budget (16 GB, other stacks stopped):** macOS, browser and editor about 5 GB. Docker VM (pg, django, worker, vite) about 1.5–2 GB. Kokoro about 0.4 GB RSS plus ≤1 GB Metal with a cache limit. LLM 12B QAT about 8 GB or 9B about 7 GB. This is tight, so the bake-off measures swap and `memory_pressure` under real load, and that measurement drives the 12B vs 9B decision.

## C. Data model

**Version-controlled files** own: curriculum outline, grammar topics, lessons (sections + exercises), vocabulary sets/lexemes, reusable exercise banks, reading passages, reference data (conjugations, Québec lexicon) and prompt templates (`backend/inference/prompts/*.j2`, versioned).
**PostgreSQL** owns: users and preferences, attempts, scores, progress, SRS state, mistakes, tutor threads, generation jobs, import/publication state, revision snapshots, and personalized (ephemeral) practice.

**Content projection** (`curriculum`, `vocabulary`, `verbs` apps; read-only in Admin apart from publication actions):
- `Level(code, order)`; `Unit(slug, level, order, title, objectives)`; `GrammarTopic(slug, level, title, summary, related[])`
- `Lesson(slug PK-stable, unit, order, current_revision→LessonRevision)`
- `LessonRevision(lesson, content_version, content_hash, payload JSONB, source_path, status[draft|published|superseded], is_manually_edited, imported_at, published_at)`. This is an **immutable snapshot**, which makes rollback a pointer move.
- `Exercise(stable_id "lesson/ex-03", lesson, type)`; `ExerciseRevision(exercise, lesson_revision, content_version, content_hash, payload JSONB, origin[curriculum|personalized])`, which is **immutable**.
- `VocabSet`, `Lexeme(stable_id, lemma, pos, gender, article, plural, glosses_en[], region[qc|fr|common], register, frequency, content_hash)`
- `Verb(infinitive, group, auxiliary, pronominal, irregular, freq_rank)`, `VerbForm(verb, mood, tense, person, form)`
- `ContentImport(id, started_at, git_sha, dry_run, summary JSON, errors JSON)`

**Authoring** (`authoring` app): `GenerationJob(kind[lesson|exercise_set|vocab_examples|revision|review_set], target_id, params JSON, prompt_id@version, model, status[queued|running|failed|needs_review|approved|rejected], raw_output, validated_output, validation_report JSON, draft_path, reviewer_notes, parent_job, timings, token_counts)`

**Learner state:**
- `accounts.User`; `LearnerProfile(level, target_level=B2, region_pref=qc, explanation_lang=en, tts_speed, daily_goal)`
- `ExerciseAttempt(user, exercise_revision FK PROTECT, answer, prompt_snapshot JSON, grading[deterministic|llm|hybrid|pending], verdict, score, feedback JSON, model, prompt_id, latency_ms, time_spent_ms, disputed)`
- `MistakeOccurrence(attempt, category[enum taxonomy], grammar_topic, span, correction)`
- `TopicMastery(user, grammar_topic, attempts, correct, ewma, last_practiced)`, updated incrementally
- `LessonProgress(user, lesson, status, last_section, completed_revision)`
- `VocabCard(user, lexeme, direction, fsrs fields…)`; `VocabReview(card, rating, reviewed_at)`
- `ConjugationAttempt(user, verb_form, answer, correct, accent_only)`
- `StudySession(user, kind, started, duration)` for time spent and streaks
- `TutorThread(user, anchor_type, anchor_id)`; `TutorMessage(thread, role, content, context_snapshot JSON, model, prompt_id, tokens, latency_ms, status[streaming|complete|error])`

**Protection rules:**
- A regenerated exercise **must** bump `content_version` and gets a new `ExerciseRevision` row.
- Attempts keep pointing at the old revision through PROTECT, and they also carry a prompt snapshot.
- If the same id and version arrive with a different hash, the import is **refused**.
- Manual edits are detected by `provenance.generated_hash ≠ current hash`. Regenerating an edited file produces a **side-by-side draft** and never overwrites it.

## D. Repository layout

```
frenchia/
├── justfile  compose.yaml  .env.example  README.md
├── docs/            architecture.md, adr/0001-…md, content-authoring.md, curriculum-sources.md, roadmap.md
├── frontend/        Vite app: src/{app,routes,features/{lessons,translate,verbs,vocab,tutor,progress},components/ui,lib/api}
├── backend/         pyproject (uv), Dockerfile
│   ├── config/      settings (django-environ), asgi, urls
│   ├── contentkit/  Pydantic schemas, validators, YAML IO (no Django)
│   ├── accounts/ curriculum/ exercises/ vocabulary/ verbs/ progress/ tutor/ authoring/
│   └── inference/   providers (ChatModel/SpeechSynth protocols, OpenAI-compatible + fake impls), prompts/, audio cache
├── services/
│   ├── llm/         ollama.version + sha256, env, warmup script
│   └── tts/         FastAPI Kokoro service (py3.12, uv.lock), tests/
├── ops/launchd/     *.plist.tmpl
├── content/         schemas/ curriculum/{a1..b2}.yaml grammar/ lessons/{a1..b2}/ vocabulary/ exercises/ reference/ drafts/
├── evals/           french/*.yaml curated cases, bakeoff runner, scorecards
├── benchmarks/kokoro/  (moved from kokoro-benchmark/)
├── scripts/         launchd render, wait-healthy, doctor, backup/restore
└── var/             (gitignored) log/, audio/, launchd/, backups/
```

## E. Phased roadmap

**Phase 1: Foundation**
- **Scope:** `git init`; move the benchmark; set up compose with db, backend, worker and frontend; Django project with custom User, DRF, drf-spectacular, `/api/health`, session login; Vite app with router, Query, Tailwind and shadcn themed per the style guide, an app shell (header, nav, footer, drawer slot) and a login page; a justfile with `setup start stop restart logs status check backup restore doctor`; ruff, pyright/django-stubs, eslint, tsc, Vitest and pytest wired into `just check`.
- **Acceptance:** `just setup && just start` on a clean checkout brings up the shell at http://localhost:5173 and you can log in. `just stop` leaves other compose projects running. `just check` passes.
- **Risk:** Vite file-watching on bind mounts. Mitigation: VirtioFS, with polling as a fallback.

**Phase 2: Native inference** *(starts with spikes)*
- **Spikes:**
  1. Reach host-loopback services from a container.
  2. Ollama MLX: `response_format` json_schema compliance, think-off, tok/s, memory.
  3. **Bake-off**: about 80 curated cases covering grammar explanation, translation judging, generation JSON validity and Québec usage, on each candidate. The result is recorded in an ADR.
  4. Kokoro memory with a cache limit.
- **Scope:** TTS service, Ollama launchd agent, pinned download, `just start` health waits and model warm-up, `inference` providers (OpenAI-compatible and fake), retry/timeout/circuit-breaker, an `/api/audio` cache endpoint, and service status in `just status` and the UI.
- **Acceptance:** both services restart independently. Django can synthesize and complete through the providers. With a service killed, the API returns a typed "unavailable" error and the UI degrades.
- **Tests:** TTS WAV fixtures (24 kHz header, duration range, non-silent RMS), provider contract tests against the fakes, and a live health smoke test.

**Phase 3: Curriculum & content pipeline**
- **Scope:**
  - contentkit schemas: lesson section union = explanation, example_set, reading, vocab_callout, grammar_table, regional_note, exercise_ref. Exercise union = translate_en_fr, translate_fr_en, fill_blank, multiple_choice, comprehension.
  - Curriculum outline A1–B2.
  - Importer: `content_validate`, `content_import [--dry-run]`, `content_publish`, `content_rollback`.
  - Multi-step generation jobs; deterministic checks (references resolve, conjugations match reference, gender matches Lexique, blanks consistent, accepted answers distinct, Québec terms in the lexicon or else flagged, length/level heuristics); optional LLM critic flags.
  - ContentWriter, restricted to `content/` with ID-derived paths and atomic writes.
  - Admin: preview, diff vs published, validation report, approve, reject, and "revise with notes" (the local LLM revises).
- **Acceptance:** generate, review and publish one A2 lesson end to end. Re-importing is a no-op. Rollback works. Regeneration preserves old attempts.
- **Tests:** schema round-trips, idempotent import, version-bump refusal, manual-edit protection, path-escape attempts on the writer.

**Phase 4: Reading + Translation Station (vertical slice)**
- **Scope:**
  - Lesson reader with section rendering, per-sentence TTS and a progress marker.
  - Translation Station with level, topic and direction filters.
  - Grading pipeline:
    1. Normalize (NFC, apostrophes ’/', case, punctuation, whitespace).
    2. Exact or accepted-answer match.
    3. Accent-only diff, decided deterministically.
    4. LLM evaluation with the schema `{verdict, score, corrected, errors[{span, category, explanation}], naturalness, register/region note, alternatives}`.
    5. Post-validation: spans must be substrings of the answer, categories must be in the enum.
  - "I think I'm right" dispute queue for Admin, which can add accepted answers.
  - Mistakes and mastery updates.
  - A pending state when the LLM is down.
- **Acceptance:** the full slice works, from generated lesson to attempt, feedback, audio and progress. Verdict latency is measured, with a target of under 8 s.
- **Tests:** curated translation cases (gender agreement, tense choice, pronoun placement, articles, prepositions, multiple acceptable answers, QC variants), Playwright on fakes, and a `@live` subset.

**Phase 5: Contextual AI Tutor**
- **Scope:**
  - Right drawer with `useTutorContext()` registration per page.
  - Server-side context builder: lesson summary, exercise, answer, feedback, topics, level, top recurring mistakes, region pref; a token budget; history windowing.
  - SSE streaming with stop and retry.
  - Quick prompts such as "How would someone in Québec say this?" and "3 more examples".
  - Persistence.
- **Acceptance:** you can ask "why *à* here?" from a graded attempt without pasting anything, and the response streams in under 2 s to first token.

**Phase 6: Verb & Vocabulary Stations**
- **Scope:**
  - Verbs: tables, drills by tense, mood and verb set, fill-in-the-blank, deterministic grading with accent feedback, LLM context sentences validated to contain the target form, TTS.
  - Vocab: sets by theme, gender/article display, flashcards, recall, FSRS, TTS.
- **Acceptance:** drills grade with no LLM, and FSRS due queues persist.

**Phase 7: Adaptive learning & polish**
- **Scope:**
  - Dashboard: streak, time, accuracy by topic, due reviews, weak topics.
  - Rules-based review set generation: the top weak topics and recent mistakes produce personalized `ExerciseRevision`s, auto-validated and labelled "AI-generated".
  - Keyboard shortcuts, an a11y pass (axe), loading and error states, and performance work.

**Future (not in this plan):** Conversation Station with STT (Parakeet v3 MLX), microphone, push-to-talk, personas, pronunciation scoring.

The current design already prepares for it:
- The TTS and chat providers are reusable.
- The SSE streaming pattern exists.
- `TutorMessage` is generic.
- ASGI is in place, so adding Channels/WebSockets later is additive.

**Constraint:** STT (about 1–2 GB) on top of a 12B LLM will not fit in 16 GB. Conversation mode will likely need the 4B-class tier, or a model swap, which the provider abstraction supports.

## F. Open questions & risks

- **Need before Phase 3 (confirm when you approve):**
  - I propose that **Claude authors only the curriculum *skeleton***: IDs, unit and topic order, prerequisites, one-line objectives. The local LLM writes all prose.
  - The Québec lexicon seed is hand-curated, about 100 entries, reviewed by you.
- **Deferred:** light theme, C1–C2, multi-user, audio compression, and the LanguageTool grammar checker (Java, about 1 GB RAM; reconsider after the bake-off).
- **Prototype-worthy risks:**
  - Memory pressure on 16 GB.
  - Québec accuracy of 9–12B models.
  - Evaluation latency.
  - Docker→loopback reachability.
  - Fast-moving Ollama and mlx-audio releases (pinned exactly; upgrades are deliberate, done with `just eval`).
  - Kokoro French G2P and liaison quality.
- **Never block MVP:** advanced analytics, multiple voices, streaming TTS, LLM critic pass.
- **Licences:** verbecc LGPL and Lexique CC BY-SA are fine for personal use; attribution goes in `docs/`. The Clémence site is used as a structural reference only.

## G. Readiness & first milestone

- **Final stack:**
  - Infra: Docker Compose (pg18, Django 6.1/DRF on uvicorn, django-tasks-db worker, Vite).
  - Native launchd agents: Ollama 0.40.11 with the bake-off winner, and FastAPI + mlx-audio 0.6.1 Kokoro.
  - Frontend: React 19, RR7, TanStack Query, Tailwind v4, shadcn.
  - Content and learning: YAML content with Pydantic schemas; FSRS; verbecc/mlconjug3 + Lexique reference data.
- **Milestones in order:** Phase 1 → Phase 2 spikes (gate: model ADR) → Phase 2 → 3 → 4 → 5 → 6 → 7.
- **First milestone (ready to implement):** Phase 1 Foundation, as scoped above.

## Verification

- **Phase 1:** `just setup`, `just start`, then open :5173 and log in. `just status` shows healthy services. `just stop`, then `docker ps` shows the other stacks untouched. `just check` passes.
- **Each later phase:**
  - Its acceptance criteria.
  - `just check`: unit, API and contract tests, the OpenAPI snapshot, and the frontend tests.
  - `just e2e`: Playwright on fake providers.
  - `just eval`: the live LLM against curated French cases, producing a scorecard.
  - `just bench`: latency and memory.
