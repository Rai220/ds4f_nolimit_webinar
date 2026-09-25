#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/config.sh
[[ "$DS41_ROOT" = /* ]] || { echo 'DS41_ROOT must be absolute' >&2; exit 1; }
[[ -f "$DS41_ROOT/model/config.json" ]] || { echo 'Download and verify the model first' >&2; exit 1; }
# Intentionally fails if a container with this name already exists.
docker run -d --name ds41-webinar \
  --gpus all --ipc=host --ulimit memlock=-1 \
  --restart=no \
  --log-opt max-size=20m --log-opt max-file=3 \
  -p 127.0.0.1:30000:30000 \
  -v "$DS41_ROOT/model:/model:ro" \
  -v "$DS41_ROOT/cache:/cache" \
  -e SGLANG_ENABLE_DSV41_ENGRAM_HOST_TABLE=1 \
  -e SGLANG_DSV41_ENGRAM_HOST_TABLE_LAYOUT=private \
  -e SGLANG_DEFAULT_THINKING=true \
  -e SGLANG_DSV41_REASONING_EFFORT=max \
  -e PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
  -e XDG_CACHE_HOME=/cache/xdg \
  -e SGLANG_CACHE_DIR=/cache/sglang \
  -e TILELANG_CACHE_DIR=/cache/tilelang \
  -e FLASHINFER_WORKSPACE_BASE=/cache/flashinfer \
  --entrypoint python3 "$SGLANG_IMAGE" -m sglang.launch_server \
  --model-path /model --served-model-name deepseek-v4.1-flash \
  --host 0.0.0.0 --port 30000 \
  --tp-size 8 --ep-size 8 \
  --context-length 262144 --mem-fraction-static 0.80 \
  --max-running-requests 8 --cuda-graph-max-bs-decode 8 \
  --chunked-prefill-size 4096 \
  --reasoning-parser deepseek-v41 --tool-call-parser deepseekv41 \
  --trust-remote-code
