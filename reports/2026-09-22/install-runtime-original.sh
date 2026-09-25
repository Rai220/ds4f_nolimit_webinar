#!/bin/bash
# Recipe assembled from the actual H200 deployment; clean-machine replay pending.
set -euo pipefail
ROOT=/workspace/ds41-exl3
UV=/opt/sglang/bin/uv
HERE=$(cd -- "$(dirname -- "$0")" && pwd)
mkdir -p "$ROOT"/{cache,logs,reports,scripts,model,engram}
export UV_CACHE_DIR=$ROOT/cache/uv
export CUDA_HOME=/usr/local/cuda
export TORCH_CUDA_ARCH_LIST=9.0a
export MAX_JOBS=16
export PATH=$ROOT/venv/bin:/usr/local/cuda/bin:$PATH
if [ ! -d "$ROOT/venv" ]; then "$UV" venv --python python3.12 "$ROOT/venv"; fi
"$UV" pip install --python "$ROOT/venv/bin/python" vllm==0.30.0 setuptools wheel ninja packaging psutil
if [ ! -d "$ROOT/exllamav3" ]; then
 git clone https://github.com/turboderp-org/exllamav3.git "$ROOT/exllamav3"
fi
git -C "$ROOT/exllamav3" checkout e648f1a131365aae15920073e761a3fa5a527654
"$UV" pip install --python "$ROOT/venv/bin/python" --no-build-isolation "$ROOT/exllamav3"
if [ ! -d "$ROOT/kit" ]; then
 git clone https://github.com/MiaAI-Lab/DeepSeek-v4.1-Flash-EXL3-2x-DGX-Sparks.git "$ROOT/kit"
fi
git -C "$ROOT/kit" checkout 6f7d1590ad49a2b8995188e45d7b9db31e677452
mkdir -p /opt/dsv41
cp "$ROOT"/kit/overlay/*.py "$ROOT"/kit/overlay/row_store.cpp /opt/dsv41/
cp "$ROOT"/kit/files/*.json "$ROOT"/kit/files/chat_template.jinja /opt/dsv41/
python - <<'PY'
from pathlib import Path
import shutil
import vllm
root=Path(vllm.__file__).parent
for p in Path('/opt/dsv41').glob('*.py'):
    p.write_text(p.read_text().replace('deepseek_v4_1','deepseek_v41'))
q=root/'model_executor/layers/quantization'
shutil.copyfile('/opt/dsv41/exl3.py',q/'exl3.py')
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
 python "/opt/dsv41/$patch.py"
done
g++ -O3 -shared -fPIC -pthread -o /opt/dsv41/librow_store.so /opt/dsv41/row_store.cpp
python "$HERE/adapt-engram-v030.py"
python -c 'import torch, exllamav3_ext; assert torch.cuda.device_count()==2; assert hasattr(exllamav3_ext,"exl3_moe")'
