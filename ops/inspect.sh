#!/usr/bin/env bash
# Read-only. No environment dump, process arguments, tokens or billing requests.
set -u
run() { printf '\n$'; printf ' %q' "$@"; printf '\n'; "$@" 2>&1 || true; }
run date -u
run uname -sm
run nvidia-smi --query-gpu=index,name,memory.total,memory.free,driver_version --format=csv
run nvidia-smi topo -m
run nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv
run free -h
for p in /sys/fs/cgroup/memory.max /sys/fs/cgroup/cpu.max /sys/fs/cgroup/memory/memory.limit_in_bytes; do
 [[ ! -f "$p" ]] || run cat "$p"
done
run df -h "${1:-.}"
run findmnt -T "${1:-.}"
run nvcc --version
run ss -ltn
for tool in python3 uv docker supervisorctl ninja g++; do
 command -v "$tool" || true
done
# Docker availability is not permission to modify host services.
