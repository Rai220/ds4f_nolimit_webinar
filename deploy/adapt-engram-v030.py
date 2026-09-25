"""Adapt the pinned MiaAI Engram backend to vLLM 0.30 NVIDIA subclass layout."""
from pathlib import Path
import argparse
import vllm
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--overlay-dir",type=Path,required=True)
args=parser.parse_args()
assert vllm.__version__ == "0.30.0", "This adapter requires vLLM 0.30.0"
root = Path(vllm.__file__).parent
p = args.overlay_dir / 'engram_file_backend.py'
s = p.read_text()
assert '        cpu_offload: bool = False,' in s
assert '        del cpu_offload\n' in s
assert 'module.engram_head_shard_rank()' in s or 'from vllm.models.deepseek_v41.nvidia.engram import engram_head_shard_rank' in s
s = s.replace('        cpu_offload: bool = False,\n    ) -> None:', '        cpu_offload: bool = False,\n        dp_shared_memory: bool = False,\n    ) -> None:')
if 'self.dp_shared_memory = False' not in s:
    s = s.replace('        del cpu_offload\n', '        del cpu_offload\n        if dp_shared_memory:\n            raise ValueError("File backend does not implement shared-DP storage")\n        self.dp_shared_memory = False\n')
s = s.replace('        self.head_start = module.engram_head_shard_rank() * self.part_n_hash_cols', '        from vllm.models.deepseek_v41.nvidia.engram import engram_head_shard_rank\n        self.head_start = engram_head_shard_rank() * self.part_n_hash_cols')
anchor = '    paths = []\n'
both = '        for libdir in ("lib64", "lib"):\n            paths += glob.glob(os.path.join(os.environ["CUDA_HOME"], libdir, "libcudart.so*"))\n'
old_line = '        paths += glob.glob(os.path.join(os.environ["CUDA_HOME"], "lib64/libcudart.so*"))\n'
if 'for libdir in ("lib64", "lib")' in s:
    pass
elif old_line in s:
    s = s.replace(old_line, both)
else:
    assert s.count(anchor) == 1
    s = s.replace(anchor, anchor + '    if os.environ.get("CUDA_HOME"):\n' + both)
p.write_text(s)
p = root / 'models/deepseek_v41/nvidia/engram.py'
s = p.read_text()
needle = 'from engram_file_backend import install as _install_file_engram'
if needle not in s:
    s += '\nimport sys as _sys\nfrom engram_file_backend import install as _install_file_engram\n_install_file_engram(_sys.modules[__name__])\n'
p.write_text(s)
print('Adapted file-backed NVIDIA Engram for vLLM 0.30')

# Same correction as MiaAI patch_sm120_block64.py, without SM120-specific edits.
p = root / 'models/deepseek_v41/nvidia/model.py'
s = p.read_text()
old = '        aux_stream_list = [torch.cuda.Stream() for _ in range(3)]'
new = '        aux_stream_list = None  # EXL3 kernels share per-device locks; serialize attention projections'
assert s.count(old) == 1 or new in s, 'Unexpected attention stream layout'
p.write_text(s.replace(old, new))
print('Serialized EXL3 attention streams')
