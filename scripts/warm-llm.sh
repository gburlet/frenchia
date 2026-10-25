#!/usr/bin/env bash
# Load the configured LLM into memory so the first real request is fast.
set -euo pipefail
cd "$(dirname "$0")/.."
model=$(grep '^INFERENCE_LLM_MODEL=' .env | cut -d= -f2)
host=$(grep '^OLLAMA_HOST=' services/llm/ollama.env | cut -d= -f2)
start=$(date +%s)
if curl -fsS --max-time 180 "http://${host}/api/generate" \
     -d "{\"model\":\"${model}\",\"prompt\":\"\",\"keep_alive\":\"2h\"}" >/dev/null; then
  echo "✓ llm: ${model} loaded in $(( $(date +%s) - start ))s"
else
  echo "⚠ llm: could not load ${model} (is it pulled? run 'just setup-native')"
fi
