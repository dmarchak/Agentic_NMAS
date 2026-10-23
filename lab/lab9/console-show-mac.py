#!/usr/bin/env python3
"""Lab 9, s5: read one switch's management SVI MAC over its console, READ-ONLY (2026-10-23).

LAB TOOLING. vIOS-L2 prints no base MAC in `show version`, and each SVI has its own MAC (the
chassis base with the VLAN in its low bits: s1's Vlan10 is ....800a), so the MAC a switch asks
DHCP from on Vlan1 is read from `show interfaces Vlan1` (the operator, 2026-10-23: the
out-of-band first pass continues with it typed into Add device; Mercury's own survey reads it
once its switch profile is fixed).

The only inputs it ever sends, each only after the reply it expects:
  RETURN, "terminal length 0" (this session's pager only: nothing is configured or saved),
  "show interfaces <interface>" (Vlan1 unless named).
It STOPS, sending nothing more, on: "Username:" or "Password:" anywhere; the setup dialog
question; "--More--"; a prompt it does not recognise; a reply not arriving in time.

It prints only the interface's state line and its `address is` line (the MAC it reads), never
anything else the console shows. The raw transcript is written to a root-only file.

    python3 console-show-mac.py <host> <port> <transcript file> [<interface>]
"""

import os
import re
import socket
import sys
import time

STOP_WORDS = (b"Username:", b"Password:", b"--More--", b"initial configuration dialog")
PROMPT = rb"[\r\n][A-Za-z0-9._-]+[>#]\s*$"
INTERFACE = re.compile(r"[A-Za-z][A-Za-z0-9/.-]{0,40}")
ADDRESS = re.compile(rb"^\s*Hardware is [^,\r\n]*, address is ([0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4}\."
                     rb"[0-9A-Fa-f]{4})", re.M)
#: `--stp`: on a blank switch no SVI exists yet (s5, 2026-10-23: `show interfaces Vlan1` is
#: invalid input), but spanning tree runs on VLAN 1; its Bridge ID's address shares the SVIs'
#: first four bytes (s1 and s2, measured 2026-10-23: bridge 0c00.6ce9.b700, SVIs 0c00.6ce9.80<vlan>).
BRIDGE = re.compile(rb"Bridge ID\s+Priority[^\r\n]*[\r\n]+\s*Address\s+([0-9A-Fa-f]{4}\."
                    rb"[0-9A-Fa-f]{4}\.[0-9A-Fa-f]{4})")


def strip_telnet(data):
    """Drop telnet negotiation (IAC sequences) from what was received, for matching only."""
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
        self.log.write(f"\n=== {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} session ===\n"
                       .encode())
        self.buf = b""

    def send(self, text):
        print(f"{time.strftime('%H:%M:%SZ', time.gmtime())} send {text!r}")
        self.log.write(f"\n>>> send {text!r}\n".encode())
        self.sock.sendall(text.encode())
        self.buf = b""

    def wait_for(self, pattern, seconds):
        """Read until *pattern* matches the text since the last send, or a stop word appears:
        ``("stop", word)``, ``(0, text)`` or ``(None, text)``."""
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
                    return ("stop", word.decode())
            if re.search(pattern, self.buf):
                return (0, self.buf)
        return (None, self.buf)


def stop(why, code=2):
    print(f"STOPPED, nothing more sent: {why}")
    sys.exit(code)


def main(argv):
    if len(argv) not in (4, 5):
        stop("usage: console-show-mac.py <host> <port> <transcript file> [<interface> | --stp]")
    stp = len(argv) == 5 and argv[4] == "--stp"
    interface = argv[4] if len(argv) == 5 and not stp else "Vlan1"
    if not INTERFACE.fullmatch(interface):
        stop(f"interface {interface!r} is not an interface name", 2)
    s = Session(argv[1], int(argv[2]), argv[3])
    if stp:
        return read_bridge(s)
    s.send("\r")
    got, text = s.wait_for(PROMPT, 20)
    if got == "stop":
        stop(f"the console showed {text!r}")
    if got is None:
        stop("no prompt within 20 s of RETURN")
    s.send("terminal length 0\r")
    got, text = s.wait_for(PROMPT, 20)
    if got != 0:
        stop(f"terminal length 0 did not return to a prompt ({got!r})")
    s.send(f"show interfaces {interface}\r")
    got, text = s.wait_for(PROMPT, 30)
    if got != 0:
        stop(f"show interfaces {interface} did not return to a prompt ({got!r})")
    state = next((ln.strip() for ln in text.decode("ascii", "replace").splitlines()
                  if ln.strip().startswith(f"{interface} is ")), "")
    m = ADDRESS.search(text)
    print(f"state: {state or '(no state line)'}")
    if not m:
        stop(f"no 'address is' line in show interfaces {interface}: the MAC is unknown", 3)
    print(f"{interface} MAC: {m.group(1).decode()}")
    s.sock.close()
    return 0


def read_bridge(s):
    """RETURN, `terminal length 0`, `show spanning-tree vlan 1`: the Bridge ID's address, and
    the Vlan1 SVI MAC it predicts (its first four bytes, then 8001), said to be a prediction."""
    s.send("\r")
    got, text = s.wait_for(PROMPT, 20)
    if got == "stop":
        stop(f"the console showed {text!r}")
    if got is None:
        stop("no prompt within 20 s of RETURN")
    s.send("terminal length 0\r")
    got, text = s.wait_for(PROMPT, 20)
    if got != 0:
        stop(f"terminal length 0 did not return to a prompt ({got!r})")
    s.send("show spanning-tree vlan 1\r")
    got, text = s.wait_for(PROMPT, 30)
    if got != 0:
        stop(f"show spanning-tree vlan 1 did not return to a prompt ({got!r})")
    m = BRIDGE.search(text)
    if not m:
        stop("no Bridge ID address in show spanning-tree vlan 1: the MAC is unknown", 3)
    bridge = m.group(1).decode().lower()
    print(f"bridge address: {bridge}")
    print(f"Vlan1 MAC predicted (bridge's first four bytes, then 8001; measured on 2 of 2 "
          f"switches, not on this one): {bridge[:10]}8001")
    s.sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
