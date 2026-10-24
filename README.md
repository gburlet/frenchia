# Frenchia

A local-first French learning app (A1→B2, Québec-first), with a local LLM tutor and Kokoro text-to-speech. Everything runs on this Mac. There are no paid inference APIs.

- Architecture and roadmap: [docs/architecture.md](docs/architecture.md)
- UI style guide: [docs/style-guide.md](docs/style-guide.md)
- Decisions: [docs/adr/](docs/adr/)

## Requirements

macOS on Apple Silicon, Docker Desktop, [just](https://just.systems), [uv](https://docs.astral.sh/uv/), Node 26 and npm, and openssl.

## Quick start

```bash
just setup    # creates .env with generated secrets, builds images, migrates, creates your login
just start    # starts the stack, waits for health, prints URLs
```

Open http://localhost:5173 and log in with the credentials that `just setup` printed. They are stored in `.env`.

| Command | What it does |
|---|---|
| `just start` / `just stop` / `just restart [svc]` | Manage the stack. Other Docker projects are never touched. |
| `just logs [svc]` / `just status` / `just doctor` | Logs, health, and environment diagnostics (ports, memory, competing containers). |
| `just check` | Backend ruff, mypy and pytest (in Docker), plus frontend typecheck, lint and Vitest. |
| `just smoke` | Calls the live LLM (plain and structured) and TTS through Django's provider layer. |
| `just setup-native` | Installs the pinned Ollama binary (sha256-verified), the TTS environment and the models. |
| `just logs llm` / `just logs tts` | Logs for the native services (`var/log/`). |
| `just manage <cmd>` / `just shell` / `just psql` | Django and database access. |
| `just backup` / `just restore [file]` | Learner data backups in `var/backups/`. Content lives in git. |

## Services

| Service | Where | Address |
|---|---|---|
| frontend (Vite) | Docker | http://localhost:5173 (proxies `/api`, `/admin`, `/static`) |
| backend (Django ASGI) | Docker | http://localhost:8000 |
| worker (django-tasks-db) | Docker | n/a |
| db (PostgreSQL 18) | Docker | 127.0.0.1:5435 |
| llm (Ollama 0.40.11, Metal) | native, launchd `ca.amii.frenchia.llm` | 127.0.0.1:11435 (OpenAI-compatible `/v1`) |
| tts (Kokoro-82M, MLX) | native, launchd `ca.amii.frenchia.tts` | 127.0.0.1:8791 (`/v1/audio/speech`) |

The native services run outside Docker for Metal acceleration. They bind to loopback only, and
containers reach them via `host.docker.internal`. Their launchd plists are generated into
`var/launchd/`, so nothing starts at login, and `just stop` only unloads Frenchia's own jobs.
Ollama runs with `OLLAMA_NO_CLOUD=1`, and Django refuses cloud model names.

**Memory:** this machine has 16 GB of unified memory. Stop other projects' Docker stacks before running the local LLM. `just doctor` lists them.

## Repository layout

```
backend/      Django project (uv)
frontend/     React + Vite + Tailwind + shadcn/ui
services/     native inference: llm/ (pinned Ollama config), tts/ (Kokoro FastAPI service)
evals/        curated French/Québec eval set and the LLM bake-off harness
scripts/      setup/doctor/status/backup helpers used by the justfile
docs/         architecture, ADRs, style guide, curriculum sources
benchmarks/   Kokoro ONNX-vs-MLX benchmark (informed the TTS decision)
var/          local state: logs, audio cache, backups (gitignored)
```
