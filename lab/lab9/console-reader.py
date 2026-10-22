#!/usr/bin/env python3
"""A strictly ONE-WAY reader of a TCP console (Lab 9, docs/LAB9_PLAN.md): it connects, only ever
receives, and appends what it receives to a file, with a UTC stamp on each chunk.

LAB TOOLING. Written for s5's serial console (qemu's telnet server on port 5000 in s5's container),
so that anything the switch prints after the launcher released its console (AutoInstall, DHCP
messages) is on record, without a single byte reaching the console.

It cannot write to the port:
- nothing here calls `send`, `sendall`, `write` or `makefile` on the socket: it is created,
  connected, and then only `recv` is called on it;
- it reads nothing from stdin (run it with `< /dev/null`);
- the telnet negotiation qemu sends (IAC sequences) is recorded as received bytes and never
  answered; qemu's console needs no answer.
It does NOT half-close the socket (`shutdown(SHUT_WR)`), because that sends a FIN, and qemu ends
the console session on end-of-file.

    python3 console-reader.py <host> <port> <log file> [seconds]
"""

import socket
import sys
import time


def main(argv):
    host, port, path = argv[1], int(argv[2]), argv[3]
    bound = float(argv[4]) if len(argv) > 4 else 6 * 3600
    end = time.monotonic() + bound
    sock = socket.create_connection((host, port), timeout=10)
    sock.settimeout(30)
    with open(path, "ab", buffering=0) as log:
        log.write(f"\n=== {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} connected to "
                  f"{host}:{port}, receive only ===\n".encode())
        while time.monotonic() < end:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            if not data:
                log.write(f"\n=== {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} the console "
                          "closed the connection ===\n".encode())
                return 0
            log.write(f"\n--- {time.strftime('%H:%M:%SZ', time.gmtime())} ---\n".encode() + data)
        log.write(f"\n=== {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} bound reached "
                  f"({bound:.0f} s) ===\n".encode())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
