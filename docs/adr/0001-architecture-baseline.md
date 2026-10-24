# ADR 0001: Architecture baseline

- Status: accepted (2026-10-24)
- Context and full rationale: [architecture.md](../architecture.md)

## Decision

- **Modular monolith.** Django 6.1 + DRF on uvicorn (ASGI), PostgreSQL 18, and a django-tasks-db worker, all in Docker Compose under project name `frenchia`. A React/Vite SPA is proxied same-origin.
- **Native inference outside Docker.** LLM and TTS run on Metal as launchd user agents, bound to 127.0.0.1 and reached from containers via `host.docker.internal`:
  - LLM: Ollama 0.40.x (MLX runner and xgrammar constrained decoding).
  - TTS: Kokoro-82M through mlx-audio behind a thin FastAPI service.
- **Content as code.** Content is YAML validated by Pydantic schemas, and the database stores versioned, immutable revisions.
- **Session authentication** for the single local learner.

## Consequences

- `just stop` only affects compose project `frenchia` and our launchd labels (`ca.amii.frenchia.*`).
- The 16 GB of unified memory is the main constraint. The LLM model is chosen by a bake-off in Phase 2 (ADR 0002).
