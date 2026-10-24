#!/usr/bin/env bash
# Show Frenchia service state and health.
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; [[ -f .env ]] && source .env; set +a

docker compose -p frenchia ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}\t{{.Ports}}'
echo
python3 -I scripts/native.py status
echo
health=$(curl -s --max-time 3 "http://127.0.0.1:${BACKEND_HOST_PORT:-8000}/api/health" || true)
if [[ -n "$health" ]]; then
  echo "API health: $health"
else
  echo "API health: unreachable"
fi
echo
echo "App:   http://localhost:${FRONTEND_HOST_PORT:-5173}"
echo "Admin: http://localhost:${FRONTEND_HOST_PORT:-5173}/admin/"
