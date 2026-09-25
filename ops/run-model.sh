#!/usr/bin/env bash
# Usage: bash ops/run-model.sh /absolute/path/to/trusted-profile.env [--dry-run]
set -euo pipefail
[[ $# -ge 1 && $# -le 2 ]] || { echo 'Usage: run-model.sh PROFILE [--dry-run]' >&2; exit 2; }
PROFILE=$1
[[ $# -eq 1 || "$2" == --dry-run ]] || { echo 'Unknown option' >&2; exit 2; }
DRY_RUN=${2:-}
# A profile is trusted shell code, never source profiles received from a model/API.
source "$PROFILE"
: "${ENGINE:?}" "${MODEL_PATH:?}" "${MODEL_ID:?}" "${PYTHON_BIN:?}" "${TP:?}" "${MAX_MODEL_LEN:?}"
HOST=${HOST:-127.0.0.1}; PORT=${PORT:-18080}; MAX_NUM_SEQS=${MAX_NUM_SEQS:-1}
MAX_BATCHED_TOKENS=${MAX_BATCHED_TOKENS:-2048}; GPU_MEMORY=${GPU_MEMORY:-0.90}
[[ "$MODEL_PATH" = /* && "$PYTHON_BIN" = /* ]] || { echo 'Use absolute model/Python paths' >&2; exit 2; }
for n in "$TP" "$PORT" "$MAX_MODEL_LEN" "$MAX_NUM_SEQS" "$MAX_BATCHED_TOKENS"; do
 [[ "$n" =~ ^[1-9][0-9]*$ ]] || { echo 'Numeric parameters must be positive integers' >&2; exit 2; }
done
(( PORT <= 65535 )) || exit 2
if [[ -z "$DRY_RUN" ]]; then
 [[ -x "$PYTHON_BIN" && -f "$MODEL_PATH/config.json" ]] || { echo 'Python executable or model/config.json missing' >&2; exit 1; }
fi
case "$ENGINE" in
 vllm)
  cmd=("$PYTHON_BIN" -m vllm.entrypoints.openai.api_server --model "$MODEL_PATH"
    --served-model-name "$MODEL_ID" --host "$HOST" --port "$PORT"
    --tensor-parallel-size "$TP" --max-model-len "$MAX_MODEL_LEN"
    --max-num-seqs "$MAX_NUM_SEQS" --max-num-batched-tokens "$MAX_BATCHED_TOKENS"
    --gpu-memory-utilization "$GPU_MEMORY")
  [[ -z "${QUANTIZATION:-}" ]] || cmd+=(--quantization "$QUANTIZATION")
  [[ ${EAGER:-1} != 1 ]] || cmd+=(--enforce-eager)
  [[ -z "${TOKENIZER_MODE:-}" ]] || cmd+=(--tokenizer-mode "$TOKENIZER_MODE")
  [[ -z "${ENGRAM_PATH:-}" ]] || {
    [[ -n "$DRY_RUN" || -f "$ENGRAM_PATH/model.safetensors.index.json" ]] || { echo 'Engram index missing' >&2; exit 1; }
    overrides=$(python3 -c 'import json,sys;print(json.dumps({"engram_table_dir":sys.argv[1]}))' "$ENGRAM_PATH")
    cmd+=(--hf-overrides "$overrides")
  }
  [[ -z "${TOOL_PARSER:-}" ]] || cmd+=(--tool-call-parser "$TOOL_PARSER" --enable-auto-tool-choice)
  ;;
 sglang)
  cmd=("$PYTHON_BIN" -m sglang.launch_server --model-path "$MODEL_PATH"
    --served-model-name "$MODEL_ID" --host "$HOST" --port "$PORT"
    --tp-size "$TP" --context-length "$MAX_MODEL_LEN"
    --max-running-requests "$MAX_NUM_SEQS" --chunked-prefill-size "$MAX_BATCHED_TOKENS"
    --mem-fraction-static "$GPU_MEMORY")
  [[ -z "${EP:-}" ]] || cmd+=(--ep-size "$EP")
  [[ -z "${QUANTIZATION:-}" ]] || cmd+=(--quantization "$QUANTIZATION")
  [[ ${EAGER:-1} != 1 ]] || cmd+=(--disable-cuda-graph)
  [[ -z "${TOOL_PARSER:-}" ]] || cmd+=(--tool-call-parser "$TOOL_PARSER")
  ;;
 *) echo "Unsupported engine: $ENGINE" >&2; exit 2;;
esac
[[ -z "${REASONING_PARSER:-}" ]] || cmd+=(--reasoning-parser "$REASONING_PARSER")
[[ ${TRUST_REMOTE_CODE:-0} != 1 ]] || cmd+=(--trust-remote-code)
if declare -p EXTRA_ARGS &>/dev/null; then cmd+=(${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}); fi
if [[ -n "$DRY_RUN" ]]; then
 printf '%q ' "${cmd[@]}"; printf '\n'
else
 exec "${cmd[@]}"
fi
