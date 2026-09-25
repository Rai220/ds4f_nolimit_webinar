"""Readiness and actual generation; run on laptop through SSH tunnel."""
import json
import sys
import urllib.request
from pathlib import Path

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:18080'
base = base.rstrip('/')
with urllib.request.urlopen(base + '/health', timeout=30) as response:
    if response.status != 200:
        raise SystemExit('Health check failed')
with urllib.request.urlopen(base + '/v1/models', timeout=30) as response:
    models = json.load(response)
if 'deepseek-v4.1-flash' not in [item['id'] for item in models['data']]:
    raise SystemExit('Expected model is absent')
payload = (Path(__file__).resolve().parents[1] / 'examples/chat.json').read_bytes()
request = urllib.request.Request(base + '/v1/chat/completions', data=payload,
                                 headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(request, timeout=600) as response:
    result = json.load(response)
choice = result['choices'][0]
content = (choice['message'].get('content') or '').strip()
if content != '323' or choice['finish_reason'] != 'stop':
    raise SystemExit('Generation did not pass: inspect response manually (content/finish_reason)')
print('PASS: health, model ID, completed generation 17 × 19 = 323')
print('usage:', json.dumps(result.get('usage'), ensure_ascii=False))
