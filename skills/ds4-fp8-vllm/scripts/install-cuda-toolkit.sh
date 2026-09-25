#!/usr/bin/env bash
# Consistent CUDA 13.0 toolkit for vLLM JIT (DeepGEMM, FlashInfer), kept outside the venv.
# Usage: bash skills/ds4-fp8-vllm/scripts/install-cuda-toolkit.sh ROOT   (after the venv exists)
set -euo pipefail
[[ $# -eq 1 ]] || { echo 'Usage: install-cuda-toolkit.sh ROOT' >&2; exit 2; }
ROOT=$1
export UV_CACHE_DIR=${UV_CACHE_DIR:-$ROOT/cache/uv} UV_LINK_MODE=copy TMPDIR=${TMPDIR:-$ROOT/cache/tmp}
mkdir -p "$TMPDIR"
# One CUDA release for everything: CCCL rejects nvcc and cudart headers of different versions.
# curand: FlashInfer sampling; cublas: FlashInfer GEMM headers. Same versions as the venv freeze.
uv pip install --python "$ROOT/venv/bin/python" --target "$ROOT/cuda13" \
  "cuda-toolkit[nvcc,cccl,curand,cublas]==13.0.3.0"
CH=$ROOT/cuda13/nvidia/cu13
# FlashInfer links with -L$CUDA_HOME/lib64 -lcudart -lcuda; the wheels ship lib/ and libcudart.so.13.
[[ -e "$CH/lib64" ]] || ln -s lib "$CH/lib64"
[[ -e "$CH/lib/libcudart.so" ]] || ln -s libcudart.so.13 "$CH/lib/libcudart.so"
# Compile and link the way the JIT does, before loading a 75 GiB model.
d=$(mktemp -d -p "$TMPDIR")
cat > "$d/k.cu" <<'K'
#include <cuda.h>
#include <cublasLt.h>
#include <curand.h>
#include <curand_kernel.h>
#include <cuda/std/cstdint>
__global__ void k(cuda::std::uint32_t *x) {
  curandStatePhilox4_32_10_t s; curand_init(0, threadIdx.x, 0, &s); x[threadIdx.x] = curand(&s);
}
K
"$CH/bin/nvcc" -std=c++17 -gencode arch=compute_90a,code=sm_90a -Xcompiler -fPIC -shared \
  "$d/k.cu" -L"$CH/lib64" -lcudart -lcuda -o "$d/k.so"
rm -rf "$d"
"$CH/bin/nvcc" --version | tail -2
echo "CUDA toolkit OK: export CUDA_HOME=$CH"
