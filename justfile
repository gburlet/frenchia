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
    @echo "✓ Setup complete. Run 'just start'."

# Start everything and wait until healthy
start:
    @./scripts/doctor.sh --brief || true
    {{compose}} up -d --build --wait db
    {{compose}} run --rm backend python manage.py migrate --noinput
    {{compose}} up -d --build --wait --wait-timeout 300
    @./scripts/status.sh

# Stop Frenchia services (data is kept)
stop:
    {{compose}} stop

# Restart all services, or the named ones (e.g. `just restart backend`)
restart *services:
    {{compose}} restart {{services}}

# Follow logs for all services, or the named ones
logs *services:
    {{compose}} logs -f --tail=200 {{services}}

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
