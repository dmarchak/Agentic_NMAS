"""Two rotations at once never put back each other's row (CONCURRENCY_AUDIT R40; 2026-10-04).

The root helper `nmas-oxidized-cred` read the whole of `router.db`, replaced one row, validated
and `os.replace`d a temporary file, with no lock. Two rotations of different devices each hold
only their own device, so both could rewrite the file at once, and the later replace put the
other device's row back to its old password: Oxidized then fails to log in to that device.

Now the helper holds an exclusive `flock` beside `router.db` from its read to its replace, so
two writers queue (each write takes milliseconds). The lab sync script `oxidized-to-config.sh`
holds one too, so two fleet-wide syncs never share its staging folder.

Driven with the real helper as two concurrent loops of subprocesses, each writing its own row;
documentation addresses (RFC 5737).
"""

import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "scripts", "nmas-oxidized-cred")
ROUNDS = 25

LOOP = '''
import json, subprocess, sys
helper, path, ip, tag = sys.argv[1:5]
for i in range({rounds}):
    out = subprocess.run([sys.executable, helper, "--file", path, "--ip", ip, "--no-backup"],
                         input=json.dumps({{"username": "admin", "password": f"{{tag}}{{i}}"}}),
                         capture_output=True, text=True)
    if out.returncode != 0:
        print(out.stdout + out.stderr)
        sys.exit(1)
'''


def test_two_concurrent_rotations_each_keep_their_own_row(tmp_path):
    db = tmp_path / "router.db"
    db.write_text("192.0.2.11:ios:admin:Old1\n192.0.2.12:ios:admin:Old2\n", encoding="utf-8")
    procs = [subprocess.Popen([sys.executable, "-c", LOOP.format(rounds=ROUNDS), HELPER,
                               str(db), ip, tag], stdout=subprocess.PIPE, text=True)
             for ip, tag in (("192.0.2.11", "PwA"), ("192.0.2.12", "PwB"))]
    for p in procs:
        out, _err = p.communicate(timeout=300)
        assert p.returncode == 0, out[-800:]
    rows = db.read_text(encoding="utf-8").splitlines()
    assert rows == [f"192.0.2.11:ios:admin:PwA{ROUNDS - 1}",
                    f"192.0.2.12:ios:admin:PwB{ROUNDS - 1}"], rows


def test_the_lock_is_beside_router_db_and_leaves_no_backup_pattern(tmp_path):
    """The lock file never looks like a backup (`router.db.nmas-bak-<stamp>`), which the
    pruning would count."""
    db = tmp_path / "router.db"
    db.write_text("192.0.2.11:ios:admin:Old1\n", encoding="utf-8")
    out = subprocess.run([sys.executable, HELPER, "--file", str(db), "--ip", "192.0.2.11",
                          "--no-backup"], input='{"username": "admin", "password": "New1"}',
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    names = sorted(os.listdir(tmp_path))
    assert names == [".router.db.nmas-lock", "router.db"], names


HOLDER = '''
import fcntl, json, os, sys
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
if sys.argv[2] == "record":
    os.ftruncate(fd, 0)
    os.pwrite(fd, json.dumps({"pid": os.getpid(), "since": "2026-10-04T20:00:00Z",
                              "act": "rotate", "ip": "192.0.2.99"}).encode(), 0)
print("held", flush=True)
sys.stdin.read()
'''


def test_a_hung_holder_is_waited_for_a_bounded_time_then_named(tmp_path):
    """The operator, 2026-10-04: a hung helper made every later rotation wait forever. Now a
    waiter gives up after LOCK_WAIT_S, changes nothing, and names the lock and the holder its
    record names, or says none is recorded. Both kinds of holder, run at once (one bound)."""
    import time

    runs = {}
    for kind in ("record", "none"):
        folder = tmp_path / kind
        folder.mkdir()
        db = folder / "router.db"
        db.write_text("192.0.2.11:ios:admin:Old1\n", encoding="utf-8")
        lock = folder / ".router.db.nmas-lock"
        holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(lock), kind],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        assert holder.stdout.readline().strip() == "held"
        runs[kind] = (db, lock, holder)
    started = time.monotonic()
    waiters = {kind: subprocess.Popen(
        [sys.executable, HELPER, "--file", str(db), "--ip", "192.0.2.11", "--no-backup"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for kind, (db, _lock, _h) in runs.items()}
    outs = {kind: w.communicate('{"username": "admin", "password": "New1"}', timeout=60)
            for kind, w in waiters.items()}
    elapsed = time.monotonic() - started
    try:
        for kind, (out, err) in outs.items():
            db, lock, holder = runs[kind]
            assert waiters[kind].returncode == 1, (kind, out, err)
            error = json.loads(out)["error"]
            assert f"{lock} is still held after 5 s; nothing was changed" in error, error
            assert db.read_text(encoding="utf-8") == "192.0.2.11:ios:admin:Old1\n", kind
        assert (f"pid {runs['record'][2].pid} (running), rotate for 192.0.2.99"
                in json.loads(outs["record"][0])["error"])
        assert "No holder is recorded in it." in json.loads(outs["none"][0])["error"]
        assert 4.5 <= elapsed < 15, f"the waiters gave up after {elapsed:.1f} s, not the bound"
    finally:
        for _db, _lock, holder in runs.values():
            holder.communicate("", timeout=10)
    db, lock, _h = runs["record"]
    out = subprocess.run([sys.executable, HELPER, "--file", str(db), "--ip", "192.0.2.11",
                          "--no-backup"], input='{"username": "admin", "password": "New1"}',
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
    held = json.loads(lock.read_text(encoding="utf-8"))
    assert (held["act"], held["ip"]) == ("rotate", "192.0.2.11"), held


def test_the_sync_script_holds_one_lock_before_any_work():
    src = open(os.path.join(ROOT, "scripts", "oxidized-to-config.sh"), encoding="utf-8").read()
    lock = src.index('flock -w 600 8')
    assert lock < src.index('RAW="$(mktemp -d)"'), "the sync works before it holds its lock"
    assert 'exec 8<"$SYNC_LOCK"' in src
