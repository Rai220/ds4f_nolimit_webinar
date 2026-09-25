#!/usr/bin/env python3
"""End-to-end check of a free-code launcher against a local model endpoint.

Runs the real client, not just HTTP: /v1/models, `--yolo` in --help, a Read round trip
in default mode, a Bash round trip under --yolo and (with --negative) the same Bash
request without --yolo, which must be refused. Every client run is a new session with
auto-memory off, in a fresh working directory. Exit code 0 only if every check passed.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

TOKEN = 'WEBINAR-CHECK-73921'


def summarize(lines):
    """Reduce stream-json lines to the fields the checks need."""
    s = {'model': None, 'permission_mode': None, 'version': None, 'tools': [],
         'is_error': None, 'subtype': None, 'turns': None, 'denials': [], 'result': ''}
    for line in lines:
        try:
            m = json.loads(line)
        except ValueError:
            continue
        if m.get('type') == 'system' and m.get('subtype') == 'init':
            s['model'] = m.get('model')
            s['permission_mode'] = m.get('permissionMode')
            s['version'] = m.get('claude_code_version')
        elif m.get('type') == 'assistant':
            for c in m.get('message', {}).get('content', []):
                if isinstance(c, dict) and c.get('type') == 'tool_use':
                    s['tools'].append(c.get('name'))
        elif m.get('type') == 'result':
            s['is_error'] = m.get('is_error')
            s['subtype'] = m.get('subtype')
            s['turns'] = m.get('num_turns')
            s['denials'] = [d.get('tool_name') for d in m.get('permission_denials') or []]
            s['result'] = m.get('result') or ''
    return s


def run_client(name, launcher, workdir, args, timeout):
    """Run one headless session; keep its stream-json and stderr as <name>.jsonl/.stderr."""
    env = dict(os.environ, CLAUDE_CODE_DISABLE_AUTO_MEMORY='1')
    cmd = [launcher, *args, '--no-session-persistence', '--output-format', 'stream-json', '--verbose']
    p = subprocess.run(cmd, cwd=workdir, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, timeout=timeout)
    (workdir / f'{name}.jsonl').write_text(p.stdout)
    (workdir / f'{name}.stderr').write_text(p.stderr)
    return p.returncode, summarize(p.stdout.splitlines())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--launcher', required=True, help='Launcher created by ops/configure-free-code.py, or the free-code command')
    ap.add_argument('--model', required=True)
    ap.add_argument('--base-url', required=True, help='Same as ANTHROPIC_BASE_URL, without /v1')
    ap.add_argument('--workdir', type=Path, help='New or empty directory; default: a temp dir')
    ap.add_argument('--negative', action='store_true', help='Also check that Bash is refused without --yolo')
    ap.add_argument('--timeout', type=int, default=600, help='Seconds per client run')
    ap.add_argument('--json', type=Path, help='Write the report here')
    a = ap.parse_args()

    work = a.workdir or Path(tempfile.mkdtemp(prefix='free-code-verify-'))
    work.mkdir(parents=True, exist_ok=True)
    if any(work.iterdir()):
        ap.error(f'{work} is not empty; choose a new directory')
    (work / 'check.txt').write_text(TOKEN + '\n')
    report = {'workdir': str(work), 'checks': []}

    def check(name, ok, **detail):
        report['checks'].append({'name': name, 'ok': bool(ok), **detail})
        print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else ' ' + json.dumps(detail, ensure_ascii=False)[:600]), flush=True)
        return ok

    try:
        with urllib.request.urlopen(a.base_url.rstrip('/') + '/v1/models', timeout=30) as r:
            ids = [m.get('id') for m in json.load(r).get('data', [])]
        check('api /v1/models', a.model in ids, ids=ids)
    except Exception as e:
        check('api /v1/models', False, error=str(e))
        return finish(report, a.json)

    h = subprocess.run([a.launcher, '--help'], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    v = subprocess.run([a.launcher, '--version'], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    report['version'] = v.stdout.strip()
    check('--yolo is a built-in flag', '--yolo' in h.stdout, version=report['version'])

    rc, s = run_client('read', a.launcher, work, [
        '-p', 'Read check.txt with the Read tool and return its contents.',
        '--tools', 'Read', '--allowedTools', 'Read', '--setting-sources', 'user', '--max-turns', '4'], a.timeout)
    check('read round trip (default mode)', rc == 0 and s['model'] == a.model and 'Read' in s['tools']
          and s['is_error'] is False and not s['denials'] and TOKEN in s['result'], rc=rc, **s)

    bash_prompt = ('Use the Bash tool to run exactly this command: cat check.txt > {f} && cat {f} . '
                   'Then reply with the command output only.')
    rc, s = run_client('yolo', a.launcher, work, [
        '--yolo', '-p', bash_prompt.format(f='made-yolo.txt'),
        '--tools', 'Bash', '--setting-sources', 'user', '--max-turns', '6'], a.timeout)
    made = work / 'made-yolo.txt'
    check('--yolo bash round trip', rc == 0 and s['permission_mode'] == 'bypassPermissions' and 'Bash' in s['tools']
          and s['is_error'] is False and not s['denials'] and made.is_file() and made.read_text().strip() == TOKEN
          and TOKEN in s['result'], rc=rc, file_created=made.is_file(), **s)

    if a.negative:
        # Bounded: a refused model may keep trying other ways to write for many turns.
        rc, s = run_client('default', a.launcher, work, [
            '-p', bash_prompt.format(f='made-default.txt'),
            '--tools', 'Bash', '--setting-sources', 'user', '--max-turns', '3'], a.timeout)
        check('without --yolo the write is refused', s['permission_mode'] == 'default'
              and not (work / 'made-default.txt').exists() and 'Bash' in s['denials'], rc=rc, **s)
    return finish(report, a.json)


def finish(report, path):
    report['ok'] = bool(report['checks']) and all(c['ok'] for c in report['checks'])
    if path:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('ALL PASS' if report['ok'] else 'FAILED', '-', report['workdir'])
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
