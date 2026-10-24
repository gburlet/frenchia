#!/usr/bin/env bash
# Dump learner data (PostgreSQL) to var/backups. Learning content lives in git, not here.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p var/backups
out="var/backups/frenchia-$(date +%Y%m%d-%H%M%S).dump"
docker compose -p frenchia exec -T db sh -c 'pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"' >"$out"
echo "• Wrote $out ($(du -h "$out" | cut -f1))"
