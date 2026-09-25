"""Validate all safetensors against the saved public HF manifest (full SHA256)."""
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest = json.loads((Path(__file__).resolve().parents[1] / 'model-manifest.json').read_text())
for item in manifest['files']:
    path = root / item['name']
    if path.stat().st_size != item['size']:
        raise SystemExit(f'Size mismatch: {item["name"]}')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(16 * 1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != item['sha256']:
        raise SystemExit(f'SHA256 mismatch: {item["name"]}')
    print(f'OK {item["name"]}', flush=True)
print(f'PASS: {len(manifest["files"])} safetensors verified')
