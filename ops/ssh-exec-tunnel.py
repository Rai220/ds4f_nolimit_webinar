#!/usr/bin/env python3
"""Local loopback listener: every connection becomes `ssh TARGET python3 -u tcpbridge.py PORT`.

Use it where `ssh -L` does not reach the server (Cloud.ru Jupyter gateway answers
"target host connection failed"); elsewhere ops/tunnel.sh is simpler. Host keys are checked
strictly: add the key to known_hosts through a trusted channel first. Foreground; keep it alive
with launchd/systemd --user. Each connection pays one SSH handshake; HTTP keep-alive reuses it.
"""
import argparse
import socket
import subprocess
import threading


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--local-port", type=int, required=True, help="Listens on 127.0.0.1 only")
    p.add_argument("--ssh-target", required=True, help="user@host")
    p.add_argument("--ssh-port", type=int, default=22)
    p.add_argument("--ssh-key", help="Private key path; default: ssh config/agent")
    p.add_argument("--remote-bridge", required=True, help="Absolute path of tcpbridge.py on the server")
    p.add_argument("--remote-port", type=int, required=True, help="Server loopback port, e.g. 18080")
    a = p.parse_args()
    if a.ssh_target.startswith("-") or not all(0 < x < 65536 for x in (a.local_port, a.ssh_port, a.remote_port)):
        p.error("Bad target or port")
    cmd = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=20",
           "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3", "-p", str(a.ssh_port)]
    if a.ssh_key:
        cmd += ["-o", "IdentitiesOnly=yes", "-i", a.ssh_key]
    cmd += [a.ssh_target, "python3", "-u", a.remote_bridge, str(a.remote_port)]

    def handle(conn):
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        def upstream():
            try:
                while True:
                    data = conn.recv(65536)
                    if not data:
                        break
                    proc.stdin.write(data)
                    proc.stdin.flush()
            except OSError:
                pass
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass

        threading.Thread(target=upstream, daemon=True).start()
        try:
            while True:
                data = proc.stdout.read1(65536)
                if not data:
                    break
                conn.sendall(data)
        except OSError:
            pass
        finally:
            conn.close()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", a.local_port))
    server.listen(32)
    print(f"listening on 127.0.0.1:{a.local_port} -> {a.ssh_target} 127.0.0.1:{a.remote_port}", flush=True)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
