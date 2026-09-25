#!/usr/bin/env bash
# Start vLLM from a trusted profile, detached from the SSH session, and wait for /v1/models.
# Usage: bash skills/ds4-fp8-vllm/scripts/serve.sh PROFILE LOG [TIMEOUT_S]
set -euo pipefail
[[ $# -ge 2 && $# -le 3 ]] || { echo 'Usage: serve.sh PROFILE LOG [TIMEOUT_S]' >&2; exit 2; }
KIT=$(cd "$(dirname "$0")/../../.." && pwd)
PROFILE=$(realpath "$1"); LOG=$2; TIMEOUT=${3:-900}
# A profile is trusted shell code, never source profiles received from a model/API.
source "$PROFILE"
HOST=${HOST:-127.0.0.1}; PORT=${PORT:-18080}
if ss -ltn | awk '{print $4}' | grep -qE "[:.]$PORT\$"; then
 echo "Port $PORT is already listening: stop the old server or pick another PORT" >&2; exit 1
fi
# A crashed start can leave workers holding VRAM; a new start would then fail on memory.
busy=$(nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits \
  ${CUDA_VISIBLE_DEVICES:+-i "$CUDA_VISIBLE_DEVICES"} | awk -F', ' '$2 > 1024 {print $1}')
[[ -z "$busy" ]] || { echo "GPUs already in use: $(echo $busy)" >&2; exit 1; }
mkdir -p "$(dirname "$LOG")" "${TMPDIR:-/tmp}"
setsid nohup bash "$KIT/ops/run-model.sh" "$PROFILE" > "$LOG" 2>&1 < /dev/null &
pid=$!
echo "server pid $pid, log $LOG"
start=$(date +%s)
until curl -sf "http://$HOST:$PORT/v1/models" > /dev/null; do
 if ! kill -0 "$pid" 2>/dev/null; then
  echo "Server exited during startup; last log lines:" >&2; tail -40 "$LOG" >&2; exit 1
 fi
 if (( $(date +%s) - start > TIMEOUT )); then
  echo "No /v1/models after ${TIMEOUT}s; server left running (pid $pid), see $LOG" >&2; exit 1
 fi
 sleep 5
done
echo "ready after $(( $(date +%s) - start ))s"
curl -s "http://$HOST:$PORT/v1/models"; echo
