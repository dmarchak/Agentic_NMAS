#!/usr/bin/env python3
"""Lab 9, s5 (docs/LAB9_PLAN.md, challenge 1): a scripted console session that sends ONLY fixed
inputs, each only after the reply it expects, and stops on anything else.

LAB TOOLING. The operator's procedure (2026-10-22): the vIOS-L2 base image appears to hold a
startup configuration, so a reload alone proves nothing; erase it and reload, to simulate an
out-of-box switch (as Lab 8's R6 and R7 were erased).

The only inputs it ever sends, in order:
  RETURN, "enable", "dir nvram:", then (only if nvram holds a startup file of size > 0)
  "write erase", RETURN (its confirm), "reload", "no" (only at the save question), RETURN (the
  reload confirm).
It STOPS, sending nothing more, on: "Username:" or "Password:" anywhere; the setup dialog
question; "--More--"; a prompt it does not recognise; a reply not arriving in time; nvram holding
no startup file, or one of size 0.

**`--never-saved` (C1572, 2026-10-23):** for a device that never saved (s5 after an out-of-band
first pass stopped before Verify; its startup file was measured 0 bytes on 2026-10-22), nvram with
no startup file, or one of size 0, is reloaded WITHOUT an erase: RETURN, "enable" (only at ">"),
"dir nvram:", "reload", "no" (only at the save question), RETURN. A startup file over 0 bytes is
still erased first. Every stop above holds; an argument other than this flag is refused before
anything is sent.

It prints only its own step lines and, from "dir nvram:", the size and name of each entry: never
a configuration's contents. The raw transcript is written to a root-only file for the record.

    python3 s5-erase-session.py <host> <port> <transcript file> [--never-saved]
"""

import os
import re
import socket
import sys
import time

PROMPT = re.compile(rb"(?:^|[\r\n])([A-Za-z0-9._-]+)([>#]) ?$")
STOP_WORDS = (b"Username:", b"Password:", b"--More--", b"initial configuration dialog")


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
        self.log.write(f"\n=== {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} session ===\n".encode())
        self.buf = b""

    def send(self, text):
        print(f"{time.strftime('%H:%M:%SZ', time.gmtime())} send {text!r}")
        self.log.write(f"\n>>> send {text!r}\n".encode())
        self.sock.sendall(text.encode())
        self.buf = b""

    def wait_for(self, patterns, seconds):
        """Read until one of *patterns* (bytes regexes) matches the text since the last send, or
        a stop word appears. Returns (index or None, text)."""
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
            for i, pattern in enumerate(patterns):
                if re.search(pattern, self.buf):
                    return (i, self.buf)
        return (None, self.buf)


def stop(why, code=2):
    print(f"STOPPED, nothing more sent: {why}")
    sys.exit(code)


def main(argv):
    never_saved = "--never-saved" in argv[4:]
    if [a for a in argv[4:] if a != "--never-saved"]:
        stop(f"unknown arguments {argv[4:]!r}: only --never-saved is accepted", 2)
    s = Session(argv[1], int(argv[2]), argv[3])
    s.send("\r")
    got, text = s.wait_for([rb"[\r\n][A-Za-z0-9._-]+>\s*$", rb"[\r\n][A-Za-z0-9._-]+#\s*$",
                            rb"[\r\n][A-Za-z0-9._-]+\(config[a-z-]*\)#\s*$"], 20)
    if got == "stop":
        stop(f"the console showed {text!r}")
    if got is None:
        stop("no prompt within 20 s of RETURN")
    if got == 2:
        # Left in configuration mode (a kick-start stopped there, 2026-10-23): `end` leaves it,
        # changing nothing, and saves nothing.
        print("configuration mode prompt: leaving it with end (nothing saved)")
        s.send("end\r")
        got, text = s.wait_for([rb"[\r\n][A-Za-z0-9._-]+#\s*$"], 20)
        if got == "stop":
            stop(f"end answered {text!r}")
        if got is None:
            stop("no privileged prompt within 20 s of end")
        got = 1
    print(f"prompt reached: {'user EXEC (>)' if got == 0 else 'privileged (#)'}")
    if got == 0:
        s.send("enable\r")
        got, text = s.wait_for([rb"[\r\n][A-Za-z0-9._-]+#\s*$"], 20)
        if got == "stop":
            stop(f"enable answered {text!r}: the image's configuration sets an enable password")
        if got is None:
            stop("no privileged prompt within 20 s of enable")
        print("privileged prompt reached (no enable password)")
    s.send("dir nvram:\r")
    got, text = s.wait_for([rb"bytes free[^\r\n]*[\r\n]+[A-Za-z0-9._-]+#\s*$"], 30)
    if got == "stop":
        stop(f"dir nvram: answered {text!r}")
    if got is None:
        stop("dir nvram: did not finish within 30 s")
    entries = re.findall(rb"^\s*\d+\s+[-a-z]+\s+(\d+)\s+.*?(\S+)\s*$", text, re.M)
    for size, name in entries:
        print(f"nvram entry: {name.decode()} {int(size)} bytes")
    total = re.search(rb"(\d+) bytes total \((\d+) bytes free\)", text)
    if total:
        print(f"nvram: {total.group(1).decode()} bytes total, {total.group(2).decode()} free")
    startup = [int(size) for size, name in entries if re.fullmatch(rb"startup.config", name)]
    if not startup or startup[0] == 0:
        if not never_saved:
            stop("nvram holds no startup file: the indication was wrong" if not startup else
                 "nvram's startup file is 0 bytes: the indication was wrong", 3)
        # C1572: a device that never saved boots configless from a reload alone; nothing to erase.
        print("nvram holds no startup configuration (never saved): reloading without an erase")
        return reload(s)
    print(f"the image's nvram holds a startup file of {startup[0]} bytes: erasing")
    s.send("write erase\r")
    got, text = s.wait_for([rb"\[confirm\]"], 20)
    if got != 0:
        stop(f"write erase did not ask to confirm ({got!r})")
    s.send("\r")
    got, text = s.wait_for([rb"complete", rb"\[OK\]"], 60)
    if got is None or got == "stop":
        stop(f"the erase did not report completion ({got!r})")
    got, text = s.wait_for([rb"[\r\n][A-Za-z0-9._-]+#\s*$"], 20)
    if got != 0:
        stop("no prompt after the erase")
    print("nvram erased")
    return reload(s)


def reload(s):
    """`reload`, `no` only at the save question, RETURN at the reload confirm; nothing else."""
    s.send("reload\r")
    got, text = s.wait_for([rb"Save\? \[yes/no\]:", rb"Proceed with reload\? \[confirm\]"], 30)
    if got == 0:
        s.send("no\r")
        got, text = s.wait_for([rb"Proceed with reload\? \[confirm\]"], 30)
        if got != 0:
            stop("no reload confirm after answering no to save")
    elif got != 1:
        stop(f"reload asked neither to save nor to confirm ({got!r})")
    s.send("\r")
    time.sleep(2)
    print("reload confirmed; the session closes now")
    s.sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
