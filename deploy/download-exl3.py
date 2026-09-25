import hashlib
import json
from pathlib import Path
from huggingface_hub import snapshot_download

root = Path('/workspace/ds41-exl3')
manifest = json.loads((root / 'quantized-manifest.json').read_text())
model = next(x for x in manifest['models'] if x['repo'].startswith('dealignai/'))
engram = manifest['exl3_engram_source']
for spec, subdir in [(model, 'model'), (engram, 'engram')]:
    patterns = None if subdir == 'model' else [x['name'] for x in spec['files']] + spec['also_required']
    snapshot_download(repo_id=spec['repo'], revision=spec['revision'], local_dir=str(root / subdir),
                      allow_patterns=patterns, max_workers=8)
    print('Downloaded', subdir, flush=True)
results = []
for spec, subdir in [(model, 'model'), (engram, 'engram')]:
    for f in spec['files']:
        p = root / subdir / f['name']
        if p.stat().st_size != f['size']:
            raise RuntimeError('Size mismatch: ' + str(p))
        h = hashlib.sha256()
        with p.open('rb') as stream:
            for chunk in iter(lambda: stream.read(32 * 1024 * 1024), b''):
                h.update(chunk)
        if h.hexdigest() != f['sha256']:
            raise RuntimeError('SHA256 mismatch: ' + str(p))
        results.append({'file':str(p.relative_to(root)), 'size':f['size'], 'sha256':h.hexdigest()})
        print('SHA256 OK', subdir, f['name'], flush=True)
(root / 'reports/weights-verified.json').write_text(json.dumps(results, indent=2) + '\n')
print('PASS: all 41 weight files verified', flush=True)
