# Frenchia: local AI-powered French learning.
# Docker services are always addressed as compose project "frenchia", so these recipes
# never start, stop or remove other projects' containers.

compose := "docker compose -p frenchia"

# List recipes
default:
    @just --list --unsorted

# One-time setup: secrets, images, database, learner account, host deps for editors
setup:
    ./scripts/init-env.sh
    ./scripts/doctor.sh
    {{compose}} build
    {{compose}} up -d --wait db
    {{compose}} run --rm backend python manage.py migrate --noinput
    {{compose}} run --rm backend python manage.py ensure_learner
    cd backend && uv sync --frozen
    cd frontend && npm ci --no-audit --no-fund
    ./scripts/setup-native.sh
    @echo "✓ Setup complete. Run 'just start'."

# Install/refresh native inference services (pinned Ollama, TTS venv, models)
setup-native:
    ./scripts/setup-native.sh

# Start everything and wait until healthy
start:
    @./scripts/doctor.sh --brief || true
    {{compose}} up -d --build --wait db
    {{compose}} run --rm backend python manage.py migrate --noinput
    {{compose}} up -d --build --wait --wait-timeout 300
    @python3 -I scripts/native.py up
    @./scripts/warm-llm.sh
    @./scripts/status.sh

# Stop Frenchia services (data is kept). Only this project's containers and launchd jobs.
stop:
    {{compose}} stop
    @python3 -I scripts/native.py down

# Restart all services, or the named ones (e.g. `just restart backend tts`)
restart *services:
    #!/usr/bin/env bash
    set -euo pipefail
    docker_svcs=(); native_svcs=()
    for s in {{services}}; do
      case "$s" in llm|tts) native_svcs+=("$s");; *) docker_svcs+=("$s");; esac
    done
    if [[ -z "{{services}}" || ${#docker_svcs[@]} -gt 0 ]]; then {{compose}} restart ${docker_svcs[@]+"${docker_svcs[@]}"}; fi
    if [[ -z "{{services}}" || ${#native_svcs[@]} -gt 0 ]]; then python3 -I scripts/native.py restart ${native_svcs[@]+"${native_svcs[@]}"}; fi

# Follow logs: Docker services by name, or `llm` / `tts` for the native services
logs *services:
    #!/usr/bin/env bash
    set -euo pipefail
    case "{{services}}" in
      llm|tts) exec tail -n 200 -F "var/log/{{services}}.log" ;;
      *) exec {{compose}} logs -f --tail=200 {{services}} ;;
    esac

# Validate content files (schemas, references, deterministic checks)
content-validate:
    {{compose}} exec backend python manage.py content_validate

# Import content/ into the database (idempotent); add --publish to make new versions live
content-import *args:
    {{compose}} exec backend python manage.py content_import {{args}}

# Generate a lesson draft with the local LLM, e.g. `just content-generate a2-imparfait`
content-generate lesson *args:
    {{compose}} exec backend python manage.py content_generate {{lesson}} {{args}}

# Write proof-reading prompts for generated lessons awaiting review (content/drafts/review/)
content-review-export *args:
    {{compose}} exec backend python manage.py content_review_export {{args}}

# Attach reviewer findings (job-N.findings.json); add --revise to queue LLM revisions from them
content-review-import reviewer="claude-haiku-5-5" *args:
    {{compose}} exec backend python manage.py content_review_import --reviewer {{reviewer}} {{args}}

# Publish (or roll back to) a lesson version, e.g. `just content-publish a2-imparfait --version 2`
content-publish lesson *args:
    {{compose}} exec backend python manage.py content_publish {{lesson}} {{args}}

# Export JSON Schemas for content files to content/schemas/
content-schemas:
    {{compose}} exec backend python -m contentkit schemas /content

# Rebuild deterministic reference data (conjugations, noun genders) from Lexique/verbecc
build-reference:
    uv run tools/reference/build_reference.py

# Call the live LLM and TTS through Django's provider layer
smoke:
    {{compose}} exec backend python manage.py inference_smoke

# Service state and health
status:
    @./scripts/status.sh

# Environment diagnostics (tools, ports, memory, competing containers)
doctor:
    @./scripts/doctor.sh

# Lint, type-check and test backend (in Docker) and frontend (on host)
check: check-backend check-frontend

check-backend:
    {{compose}} run --rm backend sh -c "ruff check . && ruff format --check . && mypy . && pytest -q"

check-frontend:
    cd frontend && npm run check

# Run backend tests (extra args go to pytest)
test *args:
    {{compose}} run --rm backend pytest {{args}}

# Auto-format backend code
fmt:
    {{compose}} run --rm backend sh -c "ruff check --fix . && ruff format ."

# Run a Django management command (e.g. `just manage createsuperuser`)
manage *args:
    {{compose}} exec backend python manage.py {{args}}

# Create migrations for changed models
makemigrations *apps:
    {{compose}} exec backend python manage.py makemigrations {{apps}}

# Django shell
shell:
    {{compose}} exec backend python manage.py shell

# psql into the database
psql:
    {{compose}} exec db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'

# Regenerate frontend API types from the running backend's OpenAPI schema
api-types:
    cd frontend && npm run api:types

# Back up learner data to var/backups
backup:
    ./scripts/backup.sh

# Restore learner data (defaults to the newest backup)
restore file="":
    ./scripts/restore.sh {{file}}

# Remove containers (keeps the database volume)
down:
    {{compose}} down

# Remove containers AND delete the database volume (asks first)
[confirm("Delete Frenchia's database and node_modules volumes? [y/N]")]
nuke:
    {{compose}} down -v
