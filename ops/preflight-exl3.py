#!/usr/bin/env python3
"""Conservative preflight for the recorded H200 route, not all EXL3 models."""
import argparse
import csv
import json
import platform
import shutil
import socket
import subprocess
from pathlib import Path
from weights import select, safe_path

GIB = 1024 ** 3


def remaining_bytes(spec, dest):
    remaining = 0
    for f in spec['files']:
        p = safe_path(dest, f['name'])
        size = p.stat().st_size if p.is_file() else 0
        # Size estimates disk budget, never integrity.
        remaining += max(0, f['size'] - size)
    return remaining


def check_gpus(output, tp):
    rows = list(csv.reader(output.strip().splitlines(), skipinitialspace=True))
    if len(rows) != tp or tp != 2:
        raise ValueError('Recorded route requires exactly two visible H200 GPUs; review another profile separately')
    for name, capability, total, free in rows:
        if 'H200' not in name or capability != '9.0':
            raise ValueError('This preflight covers only the recorded H200 architecture')
        if float(total) < 140000 or float(free) < 135000:
            raise ValueError('Insufficient free GPU memory for the recorded profile; inspect GPU processes')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['root', 'model', 'engram', 'manifest', 'repo', 'cuda-home', 'arch', 'uv']:
        p.add_argument('--' + key, required=True)
    p.add_argument('--tp', type=int, required=True)
    p.add_argument('--port', type=int, required=True)
    a = p.parse_args()
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise ValueError('Recorded installation requires Linux x86_64')
    if a.arch != '9.0a':
        raise ValueError('Recorded H200 build requires TORCH_CUDA_ARCH_LIST=9.0a')
    for tool in ['git', 'g++', 'nvidia-smi', a.uv]:
        if not shutil.which(tool):
            raise ValueError('Required executable missing: ' + tool)
    nvcc = subprocess.check_output([str(Path(a.cuda_home) / 'bin/nvcc'), '--version'], text=True)
    if 'release 13.0,' not in nvcc:
        raise ValueError('Recorded build uses CUDA toolkit 13.0; driver banner is not the toolkit version')
    gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=name,compute_cap,memory.total,memory.free', '--format=csv,noheader,nounits'], text=True)
    check_gpus(gpu, a.tp)
    with socket.socket() as s:
        s.bind(('127.0.0.1', a.port))
    manifest = json.loads(Path(a.manifest).read_text())
    root = Path(a.root).resolve()
    device = root.stat().st_dev
    remaining = 0
    for spec, dest in [(select(manifest, a.repo), a.model), (select(manifest, engram=True), a.engram)]:
        dest = Path(dest).resolve()
        if root not in dest.parents:
            raise ValueError('Stage runner expects model and Engram below ROOT')
        ancestor = dest
        while not ancestor.exists():
            ancestor = ancestor.parent
        if ancestor.stat().st_dev != device:
            raise ValueError('Separate mounts need a separate disk budget')
        remaining += remaining_bytes(spec, dest)
    free = shutil.disk_usage(root).free
    if free < remaining + 100 * GIB:
        raise ValueError(f'Disk: need {remaining / GIB:.1f} GiB remaining weights + 100 GiB reserve; free {free / GIB:.1f} GiB')
    print('PASS: tools, toolkit, H200/free VRAM, port, disk budget')
    print('Review inventory RAM/cgroup, NVLink and mount persistence separately. This is not an inference test.')


if __name__ == '__main__':
    main()
