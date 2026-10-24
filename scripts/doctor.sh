#!/usr/bin/env bash
# Environment checks. `doctor.sh --brief` prints only warnings (used by `just start`).
set -uo pipefail
cd "$(dirname "$0")/.."

brief=false; [[ "${1:-}" == "--brief" ]] && brief=true
warn() { printf '\033[33m⚠ %s\033[0m\n' "$*"; }
ok()   { $brief || printf '\033[32m✓\033[0m %s\n' "$*"; }
fail() { printf '\033[31m✗ %s\033[0m\n' "$*"; status=1; }
status=0

if ! $brief; then
  for t in docker just uv node npm openssl; do
    if command -v "$t" >/dev/null; then ok "$t: $("$t" --version 2>&1 | head -1)"; else fail "$t is not installed"; fi
  done
  [[ -f .env ]] && ok ".env present" || fail ".env missing; run 'just setup'"
fi

if ! docker info >/dev/null 2>&1; then
  fail "Docker Desktop is not running"
  exit $status
fi
ok "Docker is running ($(docker info --format '{{.NCPU}} CPUs, {{.MemTotal}}' | awk '{printf "%s %s %.1f GiB", $1, $2, $3/1073741824}') VM)"

# Other projects' containers compete for the 16 GB of unified memory the LLM needs.
others=$(docker ps --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}' | awk -F'\t' '$2 != "frenchia" {print $1}')
if [[ -n "$others" ]]; then
  warn "$(echo "$others" | wc -l | tr -d ' ') non-Frenchia containers are running (they compete for memory with the local LLM):"
  echo "$others" | sed 's/^/    /' | head -20
else
  ok "No other containers running"
fi

# Ports Frenchia binds on 127.0.0.1 (skip ones already held by our own stack).
set -a; [[ -f .env ]] && source .env; set +a
for p in "${FRONTEND_HOST_PORT:-5173}" "${BACKEND_HOST_PORT:-8000}" "${POSTGRES_HOST_PORT:-5435}"; do
  holder=$(lsof -nP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null | awk 'NR==2{print $1}')
  owner=$(docker ps --filter "publish=$p" --format '{{.Label "com.docker.compose.project"}}' | head -1)
  if [[ -n "$holder" && "$owner" != "frenchia" ]]; then
    fail "Port $p is in use by ${owner:-$holder}"
  else
    ok "Port $p available"
  fi
done

# Native inference ports: fine if held by our own launchd jobs, a conflict otherwise.
for spec in "llm:11435" "tts:${TTS_PORT:-8791}"; do
  name=${spec%%:*}; port=${spec##*:}
  holder_pid=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null | head -1)
  our_pid=$(launchctl print "gui/$(id -u)/ca.amii.frenchia.$name" 2>/dev/null | awk '/^\tpid = /{print $3}')
  if [[ -n "$holder_pid" && "$holder_pid" != "$our_pid" ]]; then
    fail "Port $port ($name) is in use by $(ps -o comm= -p "$holder_pid")"
  else
    ok "Port $port ($name) available"
  fi
done
version=$(grep '^OLLAMA_VERSION=' services/llm/ollama.version | cut -d= -f2)
[[ -x ".tools/ollama/$version/ollama" ]] && ok "Ollama $version installed" || fail "Ollama $version missing; run 'just setup-native'"
[[ -x services/tts/.venv/bin/python ]] && ok "TTS environment present" || fail "TTS environment missing; run 'just setup-native'"

free_pct=$(memory_pressure 2>/dev/null | awk -F': ' '/free percentage/{gsub("%","",$2); print $2}')
swap_used=$(sysctl -n vm.swapusage | awk '{print $6}')
if [[ -n "$free_pct" && "$free_pct" -lt 25 ]]; then
  warn "System memory free is ${free_pct}% (swap used: ${swap_used}). LLM inference may swap."
else
  ok "Memory free ${free_pct:-?}% (swap used: ${swap_used})"
fi

exit $status
