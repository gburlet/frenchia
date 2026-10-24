#!/usr/bin/env bash
# Install the native inference services: pinned Ollama binary (checksum-verified), the TTS
# service's Python environment, the configured LLM, and the Kokoro weights. Idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source services/llm/ollama.version; [[ -f .env ]] && source .env; set +a

dir=".tools/ollama/${OLLAMA_VERSION}"
if [[ -x "$dir/ollama" ]]; then
  echo "• Ollama ${OLLAMA_VERSION} already installed"
else
  echo "• Downloading Ollama ${OLLAMA_VERSION}"
  mkdir -p "$dir"
  curl -fsSL -o "$dir/ollama-darwin.tgz" \
    "https://github.com/ollama/ollama/releases/download/v${OLLAMA_VERSION}/ollama-darwin.tgz"
  actual=$(shasum -a 256 "$dir/ollama-darwin.tgz" | cut -d' ' -f1)
  if [[ "$actual" != "$OLLAMA_SHA256" ]]; then
    echo "✗ Checksum mismatch for ollama-darwin.tgz (got $actual)"; rm -rf "$dir"; exit 1
  fi
  tar -xzf "$dir/ollama-darwin.tgz" -C "$dir" && rm "$dir/ollama-darwin.tgz"
  echo "✓ Ollama ${OLLAMA_VERSION} installed (sha256 verified)"
fi

echo "• Syncing TTS service environment"
(cd services/tts && uv sync --frozen --quiet)

echo "• Fetching Kokoro weights (cached in ~/.cache/huggingface)"
HF_HUB_OFFLINE=0 services/tts/.venv/bin/python -c \
  "from huggingface_hub import snapshot_download; snapshot_download('${TTS_MODEL:-mlx-community/Kokoro-82M-bf16}')" >/dev/null

python3 -I scripts/native.py up llm
model="${INFERENCE_LLM_MODEL:?INFERENCE_LLM_MODEL missing from .env}"
case "$model" in *cloud*) echo "✗ Cloud models are not allowed: $model"; exit 1;; esac
echo "• Pulling LLM ${model} (several GB on first run)"
OLLAMA_HOST="$(grep '^OLLAMA_HOST=' services/llm/ollama.env | cut -d= -f2)" "$dir/ollama" pull "$model"
echo "✓ Native services ready"
