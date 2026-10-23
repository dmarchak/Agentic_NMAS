#!/usr/bin/env python3
"""Lab 9, s5: whether a switch routes IP, read over its console, READ-ONLY (2026-10-23, C1606).

LAB TOOLING. The static out-of-band path gives a switch `ip default-gateway`, which IOS uses
only while `ip routing` is OFF; a switch that routes ignores it and has no route off its own
subnet (s5's retry take: its copy's TFTP request never reached the config server). This reads
which from `show ip route`'s first lines: "Default gateway is ..." when routing is off,
"Gateway of last resort ..." when it is on.

The only inputs it ever sends, each only after the reply it expects:
  RETURN, "enable" (only at a user prompt), "terminal length 0" (this session's pager only),
  "show ip route".
Nothing is configured or saved. It STOPS, sending nothing more, on: "Username:" or "Password:"
anywhere; the setup dialog question; "--More--"; a prompt it does not recognise; a reply not
arriving in time. It prints only the lines that say how the switch routes. The raw transcript
is written to a root-only file.

    python3 console-show-routing.py <host> <port> <transcript file>
"""

import os
import re
import socket
import sys
import time

STOP_WORDS = (b"Username:", b"Password:", b"--More--", b"initial configuration dialog")
USER = rb"[\r\n][A-Za-z0-9._-]+>\s*$"
PRIV = rb"[\r\n][A-Za-z0-9._-]+#\s*$"
SAYS = re.compile(r"^\s*(Default gateway is.*|Gateway of last resort.*|IP routing table.*)\s*$")


def strip_telnet(data):
    out, i = bytearray(), 0
    while i < len(data):
        if data[i] == 0xFF and i + 2 < len(data):
            i += 3
            continue
        out.append(data[i])
        i += 1
    return bytes(out)


class Session:
    def __init__(self, host, port, path):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.sock.settimeout(1)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        self.log = os.fdopen(fd, "ab", buffering=0)
        self.buf = b""

    def send(self, text):
        print(f"{time.strftime('%H:%M:%SZ', time.gmtime())} send {text!r}")
        self.log.write(f"\n>>> send {text!r}\n".encode())
        self.sock.sendall(text.encode())
        self.buf = b""

    def wait_for(self, patterns, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                data = b""
            if data:
                self.log.write(data)
                self.buf += strip_telnet(data)
            for word in STOP_WORDS:
                if word in self.buf:
                    return "stop", self.buf
            for i, pattern in enumerate(patterns):
                if re.search(pattern, self.buf):
                    return i, self.buf
        return None, self.buf


def stop(why, code=2):
    print(f"STOPPED, nothing more sent: {why}")
    sys.exit(code)


def ask(s, command, seconds=30):
    s.send(command + "\r")
    got, text = s.wait_for([PRIV], seconds)
    if got != 0:
        stop(f"{command!r} did not return to the privileged prompt ({got!r})")
    return text.decode("ascii", "replace")


def main(argv):
    if len(argv) != 4:
        stop("usage: console-show-routing.py <host> <port> <transcript file>")
    s = Session(argv[1], int(argv[2]), argv[3])
    s.send("\r")
    got, text = s.wait_for([USER, PRIV], 20)
    if got == "stop":
        stop(f"the console showed {text!r}")
    if got is None:
        stop("no prompt within 20 s of RETURN")
    if got == 0:
        s.send("enable\r")
        got, text = s.wait_for([PRIV], 20)
        if got != 0:
            stop(f"enable did not reach the privileged prompt ({got!r})")
    ask(s, "terminal length 0")
    out = ask(s, "show ip route", 60)
    lines = [ln.strip() for ln in out.splitlines() if SAYS.match(ln)]
    for ln in lines:
        print(f"says: {ln}")
    routes = any(ln.startswith("Gateway of last resort") for ln in lines)
    gateway = any(ln.startswith("Default gateway is") for ln in lines)
    print("routing: " + ("ON (ip default-gateway is ignored)" if routes and not gateway else
                         "OFF (ip default-gateway applies)" if gateway and not routes else
                         "UNKNOWN (neither, or both, printed)"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
