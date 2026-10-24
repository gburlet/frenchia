#!/usr/bin/env bash
# Create .env from .env.example, replacing __GENERATE__ placeholders with random secrets.
# Never overwrites an existing .env.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  # Append settings added to .env.example since .env was created; never touch existing ones.
  added=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^([A-Z_][A-Z0-9_]*)= ]] || continue
    key="${BASH_REMATCH[1]}"
    grep -q "^${key}=" .env && continue
    [[ "$line" == *=__GENERATE__ ]] && line="${line%__GENERATE__}$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 40)"
    printf '%s\n' "$line" >>.env
    echo "• Added ${key} to .env"
    added=1
  done <.env.example
  [[ $added == 1 ]] || echo "• .env is up to date"
  exit 0
fi

tmp=$(mktemp)
while IFS= read -r line || [[ -n "$line" ]]; do
  if [[ "$line" == *=__GENERATE__ ]]; then
    line="${line%__GENERATE__}$(openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 40)"
  fi
  printf '%s\n' "$line" >>"$tmp"
done <.env.example
mv "$tmp" .env
chmod 600 .env

user=$(grep '^FRENCHIA_ADMIN_USERNAME=' .env | cut -d= -f2-)
pass=$(grep '^FRENCHIA_ADMIN_PASSWORD=' .env | cut -d= -f2-)
echo "• Created .env with generated secrets"
echo "  Login: ${user} / ${pass}   (stored in .env; change it there and run 'just manage ensure_learner')"
