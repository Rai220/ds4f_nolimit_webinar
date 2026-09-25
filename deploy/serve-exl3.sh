#!/bin/bash
set -euo pipefail
export PATH=/workspace/ds41-exl3/venv/bin:/usr/local/cuda/bin:$PATH
export CUDA_HOME=/usr/local/cuda
export TORCH_CUDA_ARCH_LIST=9.0a
export HF_HOME=/workspace/ds41-exl3/cache/hf
export XDG_CACHE_HOME=/workspace/ds41-exl3/cache
export TORCH_EXTENSIONS_DIR=/workspace/ds41-exl3/cache/torch_extensions
export VLLM_CACHE_ROOT=/workspace/ds41-exl3/cache/vllm
export DSV41_EXL3_SERIAL_STREAMS=1
export VLLM_DISABLE_SHARED_EXPERTS_STREAM=1
export EXL3_FAT_GROUPED=0
export DSV41_IO_THREADS=16
export NCCL_DEBUG=INFO
export NCCL_NVLS_ENABLE=0
export VLLM_ALLREDUCE_USE_FLASHINFER=0
export VLLM_ALLREDUCE_USE_SYMM_MEM=0
export NCCL_CUMEM_ENABLE=0
export NCCL_IB_DISABLE=1
export VLLM_SPARSE_INDEXER_MAX_LOGITS_MB=256
export PYTHONPATH=/opt/dsv41
exec python -m vllm.entrypoints.openai.api_server \
 --model /workspace/ds41-exl3/model \
 --served-model-name deepseek-v4.1-flash \
 --host 127.0.0.1 --port 18080 \
 --tensor-parallel-size 2 --quantization exl3 \
 --max-model-len 65536 --max-num-seqs 1 --max-num-batched-tokens 2048 \
 --gpu-memory-utilization 0.90 --enforce-eager --disable-custom-all-reduce \
 --hf-overrides '{"engram_table_dir":"/workspace/ds41-exl3/engram"}' \
 --tokenizer-mode deepseek_v41 --tool-call-parser deepseek_v41 \
 --reasoning-parser deepseek_v41 --enable-auto-tool-choice \
 --trust-remote-code
