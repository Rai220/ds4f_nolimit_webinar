#!/usr/bin/env python3
"""Remote half of the SSH-exec tunnel: copy stdin/stdout to a loopback TCP port on the server.

Some SSH gateways (Cloud.ru Jupyter) answer `ssh -L` themselves and never reach the notebook,
while an exec channel works. Run by ops/ssh-exec-tunnel.py, one process per client connection.
After stdin EOF only the write side is shut down, so the rest of the reply is still delivered.
Usage: python3 -u tcpbridge.py PORT
"""
import os
import socket
import sys
import threading


def main():
    port = int(sys.argv[1])
    if not 0 < port < 65536:
        raise SystemExit("Bad port")
    sock = socket.create_connection(("127.0.0.1", port))

    def upstream():
        try:
            while True:
                data = os.read(0, 65536)
                if not data:
                    break
                sock.sendall(data)
        except OSError:
            pass
        finally:
            try:
                sock.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    threading.Thread(target=upstream, daemon=True).start()
    try:
        while True:
            data = sock.recv(65536)
            if not data:
                break
            view = memoryview(data)
            while view:
                view = view[os.write(1, view):]
    except OSError:
        pass
    sock.close()


if __name__ == "__main__":
    main()
