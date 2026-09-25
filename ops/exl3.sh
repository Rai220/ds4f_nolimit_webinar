#!/usr/bin/env bash
# Stage runner for the recorded EXL3 deployment; does not rent, kill services or change the driver.
# Usage: exl3.sh PROFILE {preflight|deps|install|kernels|download|verify|serve|smoke}
set -euo pipefail
[[ $# == 2 ]] || { echo 'Usage: exl3.sh PROFILE STAGE' >&2; exit 2; }
BUNDLE=$(cd -- "$(dirname -- "$0")/.." && pwd)
PROFILE=$(cd -- "$(dirname -- "$1")" && pwd)/$(basename -- "$1")
STAGE=$2
case "$STAGE" in preflight|deps|install|kernels|download|verify|serve|smoke) ;; *) echo 'Unknown stage' >&2; exit 2;; esac
source "$PROFILE"
: "${ROOT:?}" "${MODEL_PATH:?}" "${ENGRAM_PATH:?}" "${MODEL_ID:?}"
[[ ${ENGINE:-} == vllm && ${QUANTIZATION:-} == exl3 ]] || { echo 'This deployment route requires the reviewed EXL3 profile' >&2; exit 2; }
[[ "$ROOT" = /* ]] || exit 2
UV=${UV_BIN:-uv}
MANIFEST=${MANIFEST_PATH:-$BUNDLE/quantized-manifest.json}
: "${MODEL_REPO:?Set exact EXL3 repo from the manifest}"
DOWNLOADER=$ROOT/download-venv/bin/python
mkdir -p "$ROOT/logs" "$ROOT/reports"
printf 'Stage: %s, started: ' "$STAGE"; date -u
SECONDS=0
case "$STAGE" in
 preflight)
  python3 "$BUNDLE/ops/preflight-exl3.py" --root "$ROOT" --model "$MODEL_PATH" --engram "$ENGRAM_PATH" \
    --manifest "$MANIFEST" --repo "$MODEL_REPO" --cuda-home "${CUDA_HOME:?}" \
    --arch "${TORCH_CUDA_ARCH_LIST:?}" --uv "$UV" --tp "${TP:?}" --port "${PORT:?}"
  ;;
 deps)
  bash "$BUNDLE/ops/exl3.sh" "$PROFILE" preflight
  command -v "$UV" >/dev/null
  [[ -d "$ROOT/download-venv" ]] || "$UV" venv --python "${PYTHON_VERSION:-3.12}" "$ROOT/download-venv"
  "$UV" pip install --python "$DOWNLOADER" huggingface_hub==1.30.0
  ;;
 install)
  bash "$BUNDLE/ops/exl3.sh" "$PROFILE" preflight
  export DS41_ROOT=$ROOT OVERLAY_DIR=$ROOT/overlay
  : "${TORCH_CUDA_ARCH_LIST:?Set architecture after inventory}"
  export TORCH_CUDA_ARCH_LIST
  bash "$BUNDLE/deploy/install-runtime.sh"
  ;;
 kernels)
  # Run before serving, one GPU at a time. No skip is accepted as a GPU test.
  [[ ${TP:-} == 2 ]] || { echo 'This kernel stage expects the recorded two-GPU profile' >&2; exit 2; }
  for gpu in 0 1; do
   CUDA_VISIBLE_DEVICES=$gpu "$PYTHON_BIN" -c 'import torch; assert torch.cuda.is_available()'
   CUDA_VISIBLE_DEVICES=$gpu EXL3_SELFCHECK_GPU=1 "$PYTHON_BIN" "$ROOT/overlay/test_exl3_overlay.py"
   CUDA_VISIBLE_DEVICES=$gpu "$PYTHON_BIN" "$ROOT/overlay/test_engram_dequant.py"
  done
  ;;
 download)
  bash "$BUNDLE/ops/exl3.sh" "$PROFILE" preflight
  [[ -x "$DOWNLOADER" ]] || { echo 'Run deps first' >&2; exit 1; }
  "$DOWNLOADER" "$BUNDLE/ops/weights.py" download --manifest "$MANIFEST" --repo "$MODEL_REPO" --dest "$MODEL_PATH"
  "$DOWNLOADER" "$BUNDLE/ops/weights.py" download --manifest "$MANIFEST" --engram --dest "$ENGRAM_PATH"
  ;;
 verify)
  python3 "$BUNDLE/ops/weights.py" verify --manifest "$MANIFEST" --repo "$MODEL_REPO" --dest "$MODEL_PATH" --report "$ROOT/reports/model-sha256.json"
  python3 "$BUNDLE/ops/weights.py" verify --manifest "$MANIFEST" --engram --dest "$ENGRAM_PATH" --report "$ROOT/reports/engram-sha256.json"
  ;;
 serve)
  # Foreground: Ctrl-C stops the model. Use the documented supervisor for persistence.
  exec bash "$BUNDLE/ops/run-model.sh" "$PROFILE"
  ;;
 smoke)
  python3 "$BUNDLE/ops/smoke.py" --base-url "http://127.0.0.1:${PORT:-18080}/v1" --model "$MODEL_ID" --no-thinking --tools
  ;;
esac
printf 'Stage: %s, completed in %s seconds\n' "$STAGE" "$SECONDS"
