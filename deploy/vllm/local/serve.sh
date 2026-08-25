#!/usr/bin/env bash
# Serve a local model over an OpenAI-compatible API that every example in this repo can call.
#
#   make serve-vllm                           # the normal way in
#   ./deploy/vllm/local/serve.sh              # vllm-metal (Apple Silicon)
#
# Model and tuning parameters live in deploy/engines.yaml, not in this file. Any of them
# can still be overridden per-run:
#
#   VLLM_MODEL=mlx-community/Qwen3-4B-4bit ./deploy/vllm/local/serve.sh
#
# Apple Silicon has no CUDA, so this uses the vllm-metal plugin (MLX compute backend).
# It installs into its OWN venv (~/.venv-vllm-metal) — deliberately not the repo .venv,
# because vllm-metal pins its own torch/vllm build.
set -euo pipefail

# Not hardcoded — deploy/engines.yaml is the one place these are set. engines.py renders
# it as `: "${KEY:=value}"` assignments, which leave an existing environment value alone,
# so a per-run override still wins.
DEPLOY="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONF="${ENGINES_YAML:-$DEPLOY/engines.yaml}"
PYTHON="${ENGINES_PYTHON:-$DEPLOY/../.venv/bin/python}"
if [[ -f "$CONF" && -x "$PYTHON" ]]; then
  eval "$("$PYTHON" "$DEPLOY/engines.py" --sh)"
else
  echo "warning: $CONF unreadable — falling back to built-in defaults" >&2
fi

MODEL="${VLLM_MODEL:-mlx-community/Qwen3-0.6B-4bit}"
PORT="${VLLM_PORT:-${LOCAL_PORT:-8000}}"
API_KEY="${VLLM_API_KEY:-${LOCAL_API_KEY:-cookbook-local}}"
MAX_LEN="${VLLM_MAX_MODEL_LEN:-8192}"
MAX_SEQS="${VLLM_MAX_NUM_SEQS:-64}"
GPU_UTIL="${VLLM_GPU_MEMORY_UTILIZATION:-0.92}"
VENV="${VLLM_METAL_VENV:-$HOME/.venv-vllm-metal}"

# --enable-prefix-caching / --no-enable-prefix-caching is a paired flag, not a value.
if [[ "${VLLM_ENABLE_PREFIX_CACHING:-1}" == "1" ]]; then
  PREFIX_FLAG="--enable-prefix-caching"
else
  PREFIX_FLAG="--no-enable-prefix-caching"
fi

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This script targets Apple Silicon. On a Linux GPU box use plain vLLM instead:"
  echo "  pip install vllm && vllm serve <model> --port $PORT --api-key $API_KEY"
  exit 1
fi

if [[ ! -x "$VENV/bin/vllm" ]]; then
  cat <<'MSG'
vllm-metal is not installed. Install it (into its own venv, ~/.venv-vllm-metal):

  curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash

Requires macOS 15 (Sequoia)+ and a native arm64 Python 3.12 — a Rosetta/x86_64
Python will fail. Model compatibility matrix: https://docs.vllm.ai/projects/vllm-metal/
MSG
  exit 1
fi

echo "Serving $MODEL on http://localhost:$PORT/v1 (api key: $API_KEY)"
echo "  max_model_len=$MAX_LEN max_num_seqs=$MAX_SEQS gpu_memory_utilization=$GPU_UTIL $PREFIX_FLAG"
echo "  (from $CONF)"
echo "Point the cookbook at it with these in .env:"
echo "  LOCAL_API_BASE=http://localhost:$PORT/v1"
echo "  LOCAL_API_KEY=$API_KEY"
echo

# shellcheck disable=SC2086  # VLLM_EXTRA_ARGS is deliberately word-split
exec "$VENV/bin/vllm" serve "$MODEL" \
  --port "$PORT" \
  --api-key "$API_KEY" \
  --max-model-len "$MAX_LEN" \
  --max-num-seqs "$MAX_SEQS" \
  --gpu-memory-utilization "$GPU_UTIL" \
  $PREFIX_FLAG \
  --served-model-name "$(basename "$MODEL")" \
  ${VLLM_EXTRA_ARGS:-}
