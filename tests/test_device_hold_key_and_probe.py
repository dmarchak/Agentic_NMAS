"""Device holds: one key per list, and a probe never refuses a real acquire
(CONCURRENCY_AUDIT R26, its code half; 2026-10-04).

- The key was the lowercased list name with `-` and `.` kept, while list folders use
  `config.list_slug`, which collapses them to `_`. So a command-line tool given the slug and the
  app given the display name took two locks for one device. Now every place `device_ops` names
  a list's folder or its in-process key uses `list_slug`.
- The holder probe (`holder()`, polled by the in-flight panel) takes a SHARED `flock` for an
  instant. An acquire meeting it failed at once and read the holder record, still empty, as
  operation "?" by "unknown". Now an acquire that finds an EMPTY record retries for up to
  ~100 ms: a probe lets go in microseconds, and a real holder has written its record.

Not this half: a lease, and a recorded release by an administrator (R26's other half). The
release needs a control on a screen, so it waits for the operator's decision and a mockup.
"""

import os
import subprocess
import sys

import pytest

from modules.nsot import device_ops as D

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HOLD = '''
import sys
sys.path.insert(0, {root!r})
from modules.nsot import device_ops as D
D.acquire(sys.argv[1], "r9", "deploy", "operator@example.invalid")
print("held", flush=True)
sys.stdin.readline()
'''

PROBE = '''
import sys, time
sys.path.insert(0, {root!r})
from modules.nsot import device_ops as D
print("probing", flush=True)
end = time.time() + float(sys.argv[1])
while time.time() < end:
    D.holder("rcn-lab", "r9")
'''


def test_the_display_name_and_the_slug_are_one_device():
    p = subprocess.Popen([sys.executable, "-c", HOLD.format(root=ROOT), "rcn_lab"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "held"
        with pytest.raises(D.DeviceBusy) as got:
            D.acquire("rcn-lab", "r9", "restore", "b@example.invalid")
        assert "deploy" in str(got.value)
        assert D.holder("rcn-lab", "r9")["operation"] == "deploy"
    finally:
        p.communicate("\n", timeout=30)


def test_a_probe_in_another_process_never_refuses_an_acquire():
    p = subprocess.Popen([sys.executable, "-c", PROBE.format(root=ROOT), "6"],
                         stdout=subprocess.PIPE, text=True)
    refused = []
    try:
        assert p.stdout.readline().strip() == "probing"
        for _ in range(300):
            try:
                D.acquire("rcn-lab", "r9", "deploy", "a@example.invalid")
            except D.DeviceBusy as exc:
                refused.append(str(exc))
                continue
            D.release("rcn-lab", "r9")
    finally:
        p.communicate(timeout=30)
    assert refused == [], f"{len(refused)} acquire(s) refused by a probe: {refused[:1]}"
