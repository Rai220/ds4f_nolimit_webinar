#!/bin/bash
# EXL3 adapter for pinned vLLM 0.30.0. Portable form: clean-machine GPU replay pending.
set -euo pipefail
ROOT=${DS41_ROOT:?Set an absolute installation root}
UV=${UV_BIN:-uv}
OVERLAY_DIR=${OVERLAY_DIR:-$ROOT/overlay}
PYTHON_VERSION=${PYTHON_VERSION:-3.12}
: "${TORCH_CUDA_ARCH_LIST:?Set verified compute architecture, e.g. 9.0a on tested H200}"
: "${CUDA_HOME:?Set actual CUDA toolkit directory}"
[[ "$ROOT" = /* && "$OVERLAY_DIR" = /* ]] || { echo 'Use absolute paths' >&2; exit 2; }
[[ "$ROOT" =~ ^/[a-zA-Z0-9_./-]+$ && "$OVERLAY_DIR" =~ ^/[a-zA-Z0-9_./-]+$ ]] || { echo "Installer paths must contain only letters, digits, / . _ -" >&2; exit 2; }
command -v "$UV" >/dev/null
[[ -x "$CUDA_HOME/bin/nvcc" ]] || { echo 'nvcc missing' >&2; exit 1; }
# Do not apply source patches to a running/shared venv.
export OVERLAY_DIR CUDA_HOME
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$ROOT"/{cache,logs,reports,scripts,model,engram}
LOCK=$ROOT/.install-lock
mkdir "$LOCK" 2>/dev/null || { echo "Installation locked: $LOCK. Check for an active installer before removing a stale empty lock." >&2; exit 1; }
trap 'rmdir "$LOCK"' EXIT
export UV_CACHE_DIR=$ROOT/cache/uv
# Patches below edit vLLM files in place. uv's default hardlinks would carry the
# edits into the uv cache and into every later venv built from it (seen 2026-09-23).
export UV_LINK_MODE=copy
export MAX_JOBS=${MAX_JOBS:-16}
export PATH=$ROOT/venv/bin:$CUDA_HOME/bin:$PATH
# Conda/user toolkit keeps headers and libs under targets/, not CUDA_HOME/include.
tgt="$CUDA_HOME/targets/x86_64-linux"
if [ -d "$tgt/include" ]; then
  export CPATH="$tgt/include${CPATH:+:$CPATH}"
  export CPLUS_INCLUDE_PATH="$tgt/include${CPLUS_INCLUDE_PATH:+:$CPLUS_INCLUDE_PATH}"
fi
if [ -d "$tgt/lib" ]; then
  export LIBRARY_PATH="$tgt/lib${LIBRARY_PATH:+:$LIBRARY_PATH}"
  export LD_LIBRARY_PATH="$tgt/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
# Engram opens $CUDA_HOME/lib64/libcudart.so. A prefix may only have lib/.
if [ ! -e "$CUDA_HOME/lib64" ] && [ -d "$CUDA_HOME/lib" ]; then
  ln -s lib "$CUDA_HOME/lib64"
fi
if [ ! -d "$ROOT/venv" ]; then "$UV" venv --python "$PYTHON_VERSION" "$ROOT/venv"; fi
"$UV" pip install --python "$ROOT/venv/bin/python" --constraint "$HERE/runtime-constraints.txt" vllm==0.30.0 torch==2.13.0 setuptools wheel ninja packaging psutil
if [ ! -d "$ROOT/exllamav3" ]; then
 git clone https://github.com/turboderp-org/exllamav3.git "$ROOT/exllamav3"
fi
git -C "$ROOT/exllamav3" checkout e648f1a131365aae15920073e761a3fa5a527654
"$UV" pip install --python "$ROOT/venv/bin/python" --constraint "$HERE/runtime-constraints.txt" --no-build-isolation "$ROOT/exllamav3"
if [ ! -d "$ROOT/kit" ]; then
 git clone https://github.com/MiaAI-Lab/DeepSeek-v4.1-Flash-EXL3-2x-DGX-Sparks.git "$ROOT/kit"
fi
git -C "$ROOT/kit" checkout 6f7d1590ad49a2b8995188e45d7b9db31e677452
mkdir -p "$OVERLAY_DIR"
cp "$ROOT"/kit/overlay/*.py "$ROOT"/kit/overlay/row_store.cpp "$OVERLAY_DIR/"
cp "$ROOT"/kit/tests/test_exl3_overlay.py "$ROOT"/kit/tests/test_engram_dequant.py "$OVERLAY_DIR/"
cp "$ROOT"/kit/files/*.json "$ROOT"/kit/files/chat_template.jinja "$OVERLAY_DIR/"
python - <<'PY'
from pathlib import Path
import shutil
import os
import vllm
assert vllm.__version__ == "0.30.0", "This adapter requires vLLM 0.30.0"
overlay=Path(os.environ["OVERLAY_DIR"])
root=Path(vllm.__file__).parent
for p in overlay.glob('*.py'):
    p.write_text(p.read_text().replace('deepseek_v4_1','deepseek_v41').replace('/opt/dsv41',str(overlay)))
q=root/'model_executor/layers/quantization'
shutil.copyfile(overlay/'exl3.py',q/'exl3.py')
p=q/'__init__.py';s=p.read_text()
if '    "exl3",' not in s:
    anchor='QuantizationMethods = Literal[\n'
    assert s.count(anchor)==1
    s=s.replace(anchor,anchor+'    "exl3",\n')
if 'from .exl3 import Exl3Config' not in s:
    anchor='    method_to_config.update(_CUSTOMIZED_METHOD_TO_QUANT_CONFIG)'
    assert s.count(anchor)==1
    s=s.replace(anchor,'    from .exl3 import Exl3Config\n    method_to_config["exl3"] = Exl3Config\n'+anchor)
p.write_text(s)
PY
for patch in patch_model_overrides patch_exl3_packed_names patch_exl3_lm_head patch_engram_secondary patch_engram_file; do
 python "$OVERLAY_DIR/$patch.py"
done
g++ -O3 -shared -fPIC -pthread -o "$OVERLAY_DIR/librow_store.so" "$OVERLAY_DIR/row_store.cpp"
python "$HERE/adapt-engram-v030.py" --overlay-dir "$OVERLAY_DIR"
# CUDA graphs need the EXL3 GEMM pretune; TP x DP + EP needs the loader/dispatch fixes.
python "$HERE/patch-fast-path.py"
python -c 'import torch, exllamav3_ext; assert torch.cuda.device_count()>=1; assert hasattr(exllamav3_ext,"exl3_moe")'
"$UV" pip check --python "$ROOT/venv/bin/python"
"$UV" pip freeze --python "$ROOT/venv/bin/python" > "$ROOT/reports/pip-freeze.txt"
python - <<'PY'
import torch
assert torch.__version__ == "2.13.0+cu130", torch.__version__
assert torch.cuda.device_count() >= 1
for i in range(torch.cuda.device_count()):
    with torch.cuda.device(i):
        x = torch.ones((16, 16), device=f"cuda:{i}")
        assert torch.all(x @ x == 16).item()
        torch.cuda.synchronize()
print("PASS: small Torch operation on every visible GPU; EXL3/inference tests still required")
PY
