#!/usr/bin/env bash
# Restore a dump from var/backups (replaces current learner data after confirmation).
set -euo pipefail
cd "$(dirname "$0")/.."
file="${1:-}"
if [[ -z "$file" ]]; then
  file=$(ls -t var/backups/*.dump 2>/dev/null | head -1 || true)
fi
[[ -f "$file" ]] || { echo "No backup file found (usage: just restore var/backups/<file>.dump)"; exit 1; }
read -r -p "Restore $file? This replaces the current database contents. [y/N] " reply
[[ "$reply" == [yY] ]] || { echo "Aborted"; exit 1; }
docker compose -p frenchia stop backend worker
docker compose -p frenchia exec -T db sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <"$file"
docker compose -p frenchia start backend worker
echo "• Restored $file"
