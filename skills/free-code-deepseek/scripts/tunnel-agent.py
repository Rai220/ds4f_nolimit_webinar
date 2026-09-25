#!/usr/bin/env python3
"""Write a user-level service that keeps the laptop -> server API tunnel alive.

macOS: a LaunchAgent plist; Linux: a systemd --user unit. Two modes:
  exec    ops/ssh-exec-tunnel.py; for gateways that do not pass `ssh -L` (Cloud.ru Jupyter);
  forward ops/tunnel.sh; a plain `ssh -L` for ordinary SSH servers (Vast and others).
Never overwrites a file and never loads the service: it prints the commands to do that.
The tunnel script must be a stable copy outside a checkout that may move.
"""
import argparse
import os
from pathlib import Path
import plistlib
import re
import sys

UNSAFE_SYSTEMD = re.compile(r'["\\$%\s]')


def build(a):
    """Return (program argv, environment) for the chosen mode."""
    if a.mode == 'exec':
        if not a.remote_bridge:
            raise ValueError('--remote-bridge is required in exec mode')
        argv = [a.python, a.tunnel_script, '--local-port', str(a.local_port), '--ssh-target', a.ssh_target,
                '--ssh-port', str(a.ssh_port), '--remote-bridge', a.remote_bridge, '--remote-port', str(a.remote_port)]
        if a.ssh_key:
            argv += ['--ssh-key', a.ssh_key]
        return argv, {}
    env = {'SSH_TARGET': a.ssh_target, 'SSH_PORT': str(a.ssh_port),
           'LOCAL_PORT': str(a.local_port), 'REMOTE_PORT': str(a.remote_port)}
    if a.ssh_key:
        env['SSH_KEY'] = a.ssh_key
    return ['/bin/bash', a.tunnel_script], env


def launchd(a, argv, env):
    d = {'Label': a.label, 'ProgramArguments': argv, 'RunAtLoad': True, 'KeepAlive': True,
         'ThrottleInterval': 10,
         'StandardOutPath': str(Path(a.log_dir) / 'tunnel.log'),
         'StandardErrorPath': str(Path(a.log_dir) / 'tunnel-error.log')}
    if env:
        d['EnvironmentVariables'] = env
    return plistlib.dumps(d).decode()


def systemd(a, argv, env):
    for v in [*argv, *env.values()]:
        if UNSAFE_SYSTEMD.search(v):
            raise ValueError(f'Value not safe for a systemd unit without escaping: {v!r}')
    lines = ['[Unit]', f'Description=API tunnel {a.label}', 'After=network-online.target', '',
             '[Service]', *[f'Environment="{k}={v}"' for k, v in env.items()],
             'ExecStart=' + ' '.join(argv), 'Restart=always', 'RestartSec=10', '',
             '[Install]', 'WantedBy=default.target', '']
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--mode', choices=['exec', 'forward'], required=True)
    p.add_argument('--label', required=True, help='e.g. local.free-code-deepseek-tunnel')
    p.add_argument('--tunnel-script', type=Path, required=True,
                   help='Stable copy of ops/ssh-exec-tunnel.py (exec) or ops/tunnel.sh (forward)')
    p.add_argument('--local-port', type=int, required=True)
    p.add_argument('--ssh-target', required=True, help='user@host')
    p.add_argument('--ssh-port', type=int, default=22)
    p.add_argument('--ssh-key', help='Private key path; default: ssh config/agent')
    p.add_argument('--remote-port', type=int, required=True, help='Server loopback API port, e.g. 18080')
    p.add_argument('--remote-bridge', help='exec: absolute path of ops/tcpbridge.py on the server')
    p.add_argument('--python', default='/usr/bin/python3', help='Interpreter for exec mode')
    p.add_argument('--platform', choices=['launchd', 'systemd'],
                   default='launchd' if sys.platform == 'darwin' else 'systemd')
    p.add_argument('--log-dir', type=Path, help='launchd only; default ~/Library/Logs/<label>')
    p.add_argument('--out', type=Path, help='Default: the standard user service directory')
    p.add_argument('--print', action='store_true', help='Print instead of writing')
    a = p.parse_args()

    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', a.label):
        p.error('Label: letters, digits, dot, dash, underscore')
    if a.ssh_target.startswith('-') or not re.fullmatch(r'[^\s\'"]+', a.ssh_target):
        p.error('Bad --ssh-target')
    if not all(0 < x < 65536 for x in (a.local_port, a.ssh_port, a.remote_port)):
        p.error('Bad port')
    script = a.tunnel_script.expanduser().resolve()
    if not script.is_file():
        p.error(f'Tunnel script not found: {script}')
    a.tunnel_script = str(script)
    if a.ssh_key:
        a.ssh_key = str(Path(a.ssh_key).expanduser())
    home = Path.home()
    a.log_dir = str((a.log_dir or home / 'Library/Logs' / a.label).expanduser())
    try:
        argv, env = build(a)
        text = launchd(a, argv, env) if a.platform == 'launchd' else systemd(a, argv, env)
    except ValueError as e:
        p.error(str(e))
    if a.print:
        sys.stdout.write(text)
        return
    out = a.out or (home / 'Library/LaunchAgents' / f'{a.label}.plist' if a.platform == 'launchd'
                    else home / '.config/systemd/user' / f'{a.label}.service')
    out = out.expanduser()
    if out.exists() or out.is_symlink():
        p.error(f'{out} exists; inspect it, then unload and remove it yourself or choose another label')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    os.chmod(out, 0o644)
    print('Written:', out)
    if a.platform == 'launchd':
        Path(a.log_dir).mkdir(parents=True, exist_ok=True)
        print(f'Load:   launchctl bootstrap gui/$(id -u) {out}')
        print(f'State:  launchctl print gui/$(id -u)/{a.label} | grep -E "state|pid"')
        print(f'Unload: launchctl bootout gui/$(id -u)/{a.label}')
        print(f'Logs:   {a.log_dir}/tunnel-error.log')
    else:
        print(f'Load:   systemctl --user daemon-reload && systemctl --user enable --now {a.label}.service')
        print(f'State:  systemctl --user status {a.label}.service')
        print(f'Unload: systemctl --user disable --now {a.label}.service')
        print(f'Logs:   journalctl --user -u {a.label}.service')


if __name__ == '__main__':
    main()
