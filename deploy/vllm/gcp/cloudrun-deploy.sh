#!/usr/bin/env bash
# Deploy vLLM to Cloud Run with a GPU. Scale-to-zero is the reason to start here.
#
#   PROJECT_ID=my-proj HF_TOKEN=hf_xxx ./deploy/vllm/gcp/cloudrun-deploy.sh
#
# Requires: gcloud authenticated, Cloud Run API enabled, and approved GPU quota in REGION.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-vllm}"
MODEL="${VLLM_MODEL:-Qwen/Qwen3-8B}"
API_KEY="${VLLM_API_KEY:?set VLLM_API_KEY — an unauthenticated GPU endpoint gets mined}"
IMAGE="${IMAGE:-vllm/vllm-openai:latest}"
GPU_TYPE="${GPU_TYPE:-nvidia-l4}"
# Set from your measured knee (examples/07_inference/03_load_sweep.py), not from a guess.
CONCURRENCY="${CONCURRENCY:-8}"
MIN_INSTANCES="${MIN_INSTANCES:-0}"

if [[ "$MIN_INSTANCES" == "0" ]]; then
  echo "min-instances=0: scale-to-zero is on, so the first request after idle pays the full"
  echo "model download. Set MIN_INSTANCES=1 to trade cost for latency."
fi

gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$IMAGE" \
  --gpu 1 --gpu-type "$GPU_TYPE" --no-gpu-zonal-redundancy \
  --cpu 8 --memory 32Gi \
  --port 8000 \
  --concurrency "$CONCURRENCY" \
  --min-instances "$MIN_INSTANCES" \
  --max-instances "${MAX_INSTANCES:-3}" \
  --timeout 3600 \
  --no-allow-unauthenticated \
  --set-env-vars "HF_HOME=/root/.cache/huggingface,HUGGING_FACE_HUB_TOKEN=${HF_TOKEN:-}" \
  --args "--model=$MODEL,--port=8000,--api-key=$API_KEY,--max-model-len=${MAX_MODEL_LEN:-8192}"

URL="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" --region "$REGION" --format='value(status.url)')"
cat <<MSG

Deployed. Point the cookbook at it:

  HOSTED_VLLM_API_BASE=$URL/v1
  HOSTED_VLLM_API_KEY=$API_KEY
  VLLM_MODEL=$MODEL

First request after a cold start downloads the weights — expect minutes.
MSG
