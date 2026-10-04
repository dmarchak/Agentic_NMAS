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


def test_the_sync_script_holds_one_lock_before_any_work():
    src = open(os.path.join(ROOT, "scripts", "oxidized-to-config.sh"), encoding="utf-8").read()
    lock = src.index('flock -w 600 8')
    assert lock < src.index('RAW="$(mktemp -d)"'), "the sync works before it holds its lock"
    assert 'exec 8<"$SYNC_LOCK"' in src
