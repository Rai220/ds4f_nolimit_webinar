#!/usr/bin/env python3
"""Pin HF weights, download exact snapshots, and verify full hashes. Stdlib except HF calls."""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath


def safe_path(root, name):
    rel = PurePosixPath(name)
    if not name or rel.is_absolute() or '..' in rel.parts or '\\' in name:
        raise ValueError(f'Unsafe manifest filename: {name!r}')
    root = Path(root).resolve()
    path = (root / name).resolve()
    if path == root or root not in path.parents:
        raise ValueError('File escapes destination, including via symlink')
    return path


def select(manifest, repo=None, engram=False):
    if engram:
        spec = manifest['exl3_engram_source']
    elif 'models' in manifest:
        matches = [x for x in manifest['models'] if x['repo'] == repo]
        if len(matches) != 1:
            raise ValueError('Combined manifest requires an exact --repo')
        spec = matches[0]
    else:
        spec = manifest
        if repo and repo != spec['repo']:
            raise ValueError('Repo differs from manifest')
    if not re.fullmatch(r'[0-9a-f]{40}', spec['revision']):
        raise ValueError('Expected a pinned 40-character HF revision')
    if not spec['files']:
        raise ValueError('No weight files in manifest')
    names = set()
    for f in spec['files']:
        safe_path('/manifest-check', f['name'])
        if f['name'] in names or not isinstance(f['size'], int) or f['size'] < 0:
            raise ValueError('Duplicate filename or invalid size')
        if not re.fullmatch(r'[0-9a-f]{64}', f['sha256']):
            raise ValueError('Missing/invalid SHA256')
        names.add(f['name'])
    for name in spec.get('also_required', []):
        safe_path('/manifest-check', name)
    return spec


def verify(spec, dest):
    checked = []
    for f in spec['files']:
        path = safe_path(dest, f['name'])
        if path.stat().st_size != f['size']:
            raise ValueError(f'Size mismatch: {f["name"]}')
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(16 * 1024 * 1024), b''):
                h.update(block)
        if h.hexdigest() != f['sha256']:
            raise ValueError(f'SHA256 mismatch: {f["name"]}')
        checked.append(dict(f))
        print('SHA256 OK', f['name'], flush=True)
    for name in spec.get('also_required', []):
        if not safe_path(dest, name).is_file():
            raise ValueError(f'Missing support file: {name}')
    return {'repo': spec['repo'], 'revision': spec['revision'], 'verified_weights': checked,
            'note': 'Full hashes of listed weights; support files presence only.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    pin = sub.add_parser('pin', help='Query HF metadata; never downloads weights')
    pin.add_argument('--repo', required=True)
    pin.add_argument('--revision', required=True, help='A tag/branch is resolved to an immutable SHA')
    pin.add_argument('--output', required=True)
    for command in ['download', 'verify']:
        c = sub.add_parser(command)
        c.add_argument('--manifest', required=True)
        c.add_argument('--repo')
        c.add_argument('--engram', action='store_true')
        c.add_argument('--dest', required=True)
        if command == 'verify':
            c.add_argument('--report')
    a = p.parse_args()
    if a.command == 'pin':
        from huggingface_hub import HfApi
        if Path(a.output).exists():
            raise ValueError('Output exists; use a new manifest filename')
        info = HfApi().model_info(a.repo, revision=a.revision, files_metadata=True)
        files = []
        for f in info.siblings:
            if f.rfilename.endswith(('.safetensors', '.gguf', '.bin', '.pt', '.pth')):
                if not f.lfs:
                    raise ValueError(f'No LFS SHA256 for {f.rfilename}; investigate format manually')
                files.append({'name': f.rfilename, 'size': f.size, 'sha256': f.lfs.sha256})
        manifest = {'repo': a.repo, 'revision': info.sha, 'files': files,
                    'note': 'HF metadata, not local verification. Multiple quant variants may need selection.'}
        select(manifest)
        Path(a.output).write_text(json.dumps(manifest, indent=2)+'\n')
        print(f'Pinned {len(files)} weight files; {sum(f["size"] for f in files)} bytes')
        return
    spec = select(json.loads(Path(a.manifest).read_text()), a.repo, a.engram)
    if a.command == 'download':
        from huggingface_hub import snapshot_download
        # Complete checkpoint normally; secondary Engram snapshot only needs its selected files.
        patterns = [f['name'] for f in spec['files']] + spec.get('also_required', []) if a.engram else None
        for f in spec['files']:
            safe_path(a.dest, f['name'])
        for name in spec.get('also_required', []):
            safe_path(a.dest, name)
        snapshot_download(repo_id=spec['repo'], revision=spec['revision'], local_dir=a.dest,
                          allow_patterns=patterns, max_workers=8)
        print('Download complete. Run verify before serving.')
    else:
        report = verify(spec, a.dest)
        if a.report:
            Path(a.report).write_text(json.dumps(report, indent=2)+'\n')
        print(f'PASS: {len(report["verified_weights"])} weights verified')


if __name__ == '__main__':
    main()
