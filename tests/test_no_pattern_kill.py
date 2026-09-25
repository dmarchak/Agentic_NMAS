"""Stop a process by IDENTITY, never by pattern.

Three times in this project a `pkill -f "<pattern>"` killed the shell running
it, because the pattern was also text in that shell's own command line: a
lost heredoc edit, a lost file copy, and a probe teardown stopped half way.
The fix is `scripts/nmas-lab-tunnel` (a control socket is the tunnel's
identity) and, for anything else, a recorded PID or the unit's MainPID --
and this scan, so the next instance is refused where it is written down
rather than remembered by the next person.
"""

import os
import re
import socket
import stat
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERN_KILL = re.compile(
    r"\b(pkill|killall)\b|\bpgrep\s+(-\w*\s+)*-\w*f\b")


def _offenders_in(text: str, fenced_only: bool) -> list:
    out, fence = [], False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if fenced_only and not fence:
            continue
        code = line.split("#", 1)[0] if not fenced_only else line
        if PATTERN_KILL.search(code):
            out.append((n, line.strip()))
    return out


def _scan():
    found, scanned = [], 0
    for top, fenced in (("scripts", False), ("deploy", False), ("docs", True)):
        for base, _dirs, files in os.walk(os.path.join(ROOT, top)):
            if "__pycache__" in base:
                continue
            for f in files:
                if fenced and not f.endswith(".md"):
                    continue
                path = os.path.join(base, f)
                try:
                    text = open(path, encoding="utf-8").read()
                except (UnicodeDecodeError, OSError):
                    continue
                scanned += 1
                found += [(os.path.relpath(path, ROOT), n, l)
                          for n, l in _offenders_in(text, fenced)]
    return found, scanned


def test_the_scan_finds_something():
    """Floor, and a positive control: a scanner that can only say "clean"
    is indistinguishable from one that could not run."""
    _found, scanned = _scan()
    assert scanned >= 60, scanned
    assert _offenders_in('pkill -f "22051:x"\n', fenced_only=False)
    assert _offenders_in('```\nkill $(pgrep -f app)\n```\n', fenced_only=True)
    # A listing piped to grep READS; it stops and selects nothing, so it is
    # not the class -- `docker ps -a | grep onboard-c || echo gone` is fine.
    assert not _offenders_in("docker ps -a | grep x\n", fenced_only=False)
    assert not _offenders_in("# pkill -f is how it broke\n", fenced_only=False)


def test_nothing_written_down_stops_a_process_by_pattern():
    found, _ = _scan()
    assert not found, "stop by identity (nmas-lab-tunnel, a PID, MainPID): " \
        + "; ".join(f"{p}:{n}: {l}" for p, n, l in found)


def _fake_ssh(tmp_path, remove_socket_on_exit=True):
    """An `ssh` that records its argv and behaves like a control master:
    -M -S creates the socket, -O exit removes it (unless told not to)."""
    log = tmp_path / "ssh.log"
    fake = tmp_path / "bin" / "ssh"
    fake.parent.mkdir()
    fake.write_text(f"""#!/usr/bin/env python3
import os, socket, sys
a = sys.argv[1:]
open({str(log)!r}, "a").write(" ".join(a) + "\\n")
sock = a[a.index("-S") + 1] if "-S" in a else ""
if "-M" in a:
    s = socket.socket(socket.AF_UNIX); s.bind(sock)
elif "-O" in a and a[a.index("-O") + 1] == "exit":
    if {remove_socket_on_exit!r}: os.unlink(sock)
elif "-O" in a and a[a.index("-O") + 1] == "check":
    sys.exit(0 if os.path.exists(sock) else 255)
""")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PATH=f"{fake.parent}:{os.environ['PATH']}",
               XDG_RUNTIME_DIR=str(tmp_path))
    return env, log


def _tunnel(env, *args):
    return subprocess.run([os.path.join(ROOT, "scripts", "nmas-lab-tunnel"),
                           *args], env=env, capture_output=True, text=True)


def test_open_and_close_go_through_the_control_socket(tmp_path):
    env, log = _fake_ssh(tmp_path)
    r = _tunnel(env, "open", "probe", "u@h", "22051:10.0.0.51:22")
    assert r.returncode == 0, r.stderr
    r = _tunnel(env, "close", "probe", "u@h")
    assert r.returncode == 0 and "closed" in r.stdout, r.stderr
    calls = log.read_text().splitlines()
    assert "-M -S" in calls[-2] and "-L 22051:10.0.0.51:22" in calls[-2]
    assert "-O exit" in calls[-1]
    sock = calls[-2].split("-S ", 1)[1].split()[0]
    assert sock in calls[-1], "close must address the SAME master"


def test_a_master_that_does_not_stop_is_reported_not_killed(tmp_path):
    env, _log = _fake_ssh(tmp_path, remove_socket_on_exit=False)
    _tunnel(env, "open", "probe", "u@h", "22051:10.0.0.51:22")
    r = _tunnel(env, "close", "probe", "u@h")
    assert r.returncode == 1 and "STILL OPEN" in r.stderr
