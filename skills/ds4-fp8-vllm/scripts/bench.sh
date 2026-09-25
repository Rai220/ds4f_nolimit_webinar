#!/usr/bin/env bash
# The fixed speed measurement: running server must match PROFILE exactly, smoke (= JIT warm-up),
# then bench-decode with the reference workload. Writes everything needed to quote the numbers.
# Usage: bash skills/ds4-fp8-vllm/scripts/bench.sh PROFILE SERVER_LOG OUT_DIR
set -euo pipefail
[[ $# -eq 3 ]] || { echo 'Usage: bench.sh PROFILE SERVER_LOG OUT_DIR' >&2; exit 2; }
KIT=$(cd "$(dirname "$0")/../../.." && pwd)
PROFILE=$(realpath "$1"); LOG=$(realpath "$2"); OUT=$3
[[ ! -e "$OUT" ]] || { echo "$OUT exists; use a new report directory" >&2; exit 1; }
expected=$(bash "$KIT/ops/run-model.sh" "$PROFILE" --dry-run)
source "$PROFILE"
HOST=${HOST:-127.0.0.1}; PORT=${PORT:-18080}; BASE="http://$HOST:$PORT/v1"
pid=$(ss -ltnp | awk -v p="$PORT" '$4 ~ "[:.]" p "$"' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
[[ -n "$pid" ]] || { echo "Nothing of ours listens on port $PORT" >&2; exit 1; }
mapfile -d '' -t argv < "/proc/$pid/cmdline"
actual=$(printf '%q ' "${argv[@]}")
if [[ "$actual" != "$expected" ]]; then
 printf 'Running server differs from the profile; restart it with serve.sh.\nexpected: %s\nactual:   %s\n' \
   "$expected" "$actual" >&2
 exit 1
fi
mkdir -p "$OUT"
cp "$PROFILE" "$OUT/profile.env"
printf '%s\n' "$actual" > "$OUT/command.txt"
{
 date -Is
 nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader \
   ${CUDA_VISIBLE_DEVICES:+-i "$CUDA_VISIBLE_DEVICES"}
 "$PYTHON_BIN" -c 'import torch, vllm; print("vllm", vllm.__version__, "torch", torch.__version__, "cuda", torch.version.cuda)'
} > "$OUT/versions.txt"
# The first requests compile Triton/TileLang kernels: smoke doubles as the warm-up.
python3 "$KIT/ops/smoke.py" --base-url "$BASE" --model "$MODEL_ID" --tools | tee "$OUT/smoke.txt"
[[ $(grep -c '^PASS' "$OUT/smoke.txt") -eq 3 ]] || { echo 'Smoke did not pass 3 checks' >&2; exit 1; }
n0=$(wc -l < "$LOG")
# Reference workload: 54-token Russian essay prompt, 1024 tokens incl. reasoning, temperature 0,
# ignore_eos. The first parallel=1 run is a warm-up; quote the second one and parallel=4.
python3 "$KIT/ops/bench-decode.py" --base-url "$BASE" --model "$MODEL_ID" \
  --parallel 1,1,4 --json "$OUT/bench.json" | tee "$OUT/bench.txt"
# vLLM logs acceptance stats every few seconds; give it one interval after the last request.
sleep 12
tail -n +"$((n0 + 1))" "$LOG" | grep 'SpecDecoding metrics' > "$OUT/spec-decoding.txt" || true
echo "report: $OUT"
