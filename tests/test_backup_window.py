"""Every guard on the hypervisor's nightly backup window states the same window, in the zone
the job is scheduled in (C2613).

The job runs at 02:30 in the hypervisor's local time, America/Denver, every night (measured
2026-11-06 from the hypervisor's task list: 02:30 MDT through 2026-10-31, 02:30 MST from
2026-11-01, 33 to 37 minutes each). Every guard written before then held 08:30 to 09:10 UTC, so
from 2026-11-01 each guarded an hour the backup no longer ran in and let a start through at
09:30 UTC, inside it. The window is now stated as the job states it, 02:30 to 03:30
America/Denver, and converted at the instant asked: 08:30 to 09:30 UTC under MDT, 09:30 to
10:30 UTC under MST. A machine that cannot read the zone refuses.

The population is defined by the property, a guard: a tracked file under scripts/ or
.github/workflows/ that names the backup window AND decides on it (a host step's
`echo inside`, a probe's `in_backup_window`, the workflow's `ok=false`). The scan has a floor
and a planted case.
"""

import calendar
import os
import re
import subprocess
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The window as the job states it (CLAUDE.md, standing facts; C2613).
ZONE, START, END = "America/Denver", "02:30", "03:30"

#: What makes a file a guard on the window, beside naming it.
_DECIDES = re.compile(r"echo inside|in_backup_window|ok=false")
#: A clock read in UTC deciding the window: the shape every guard had before C2613.
_UTC_ONLY = re.compile(r"date -u \+%H|-ge 0?830\b|-ge 510\b|BACKUP_WINDOW = \(\(8, 30\)")

#: Floor: the workflow, the two probes and the four host steps (2026-11-06).
FLOOR = 7


def _tracked():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "scripts", ".github/workflows"],
                         check=True, capture_output=True, text=True).stdout.split()
    return [p for p in out if os.path.isfile(os.path.join(ROOT, p))]


def guard_problems(text: str) -> list:
    """Why *text*, a guard on the backup window, does not state the job's window."""
    problems = []
    if ZONE not in text:
        problems.append(f"does not name the zone {ZONE}")
    if START not in text or END not in text:
        problems.append(f"does not name {START} to {END}")
    if _UTC_ONLY.search(text):
        problems.append("decides on a UTC clock alone (" + _UTC_ONLY.search(text).group(0) + ")")
    return problems


def guards():
    found = {}
    for path in _tracked():
        try:
            with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
                text = fh.read()
        except (UnicodeDecodeError, OSError):
            continue
        if re.search(r"backup window", text, re.I) and _DECIDES.search(text):
            found[path] = text
    return found


class TestEveryGuard:
    def test_every_guard_states_the_jobs_window_in_its_zone(self):
        found = guards()
        assert len(found) >= FLOOR, sorted(found)
        bad = {p: guard_problems(t) for p, t in found.items() if guard_problems(t)}
        assert not bad, bad

    def test_the_scan_finds_a_guard_written_the_old_way(self):
        planted = ("check \"outside the backup window (08:30 to 09:10 UTC)\" eq \"outside\" \\\n"
                   "    'm=$((10#$(date -u +%H) * 60 + 10#$(date -u +%M))); "
                   "[ $m -ge 510 ] && [ $m -lt 550 ] && echo inside || echo outside'\n")
        assert _DECIDES.search(planted)
        got = guard_problems(planted)
        assert any("zone" in g for g in got) and any("UTC clock" in g for g in got), got


def _host_step_checks():
    """Each host step's window check: (path, its shell expression)."""
    out = []
    for path, text in guards().items():
        if not path.startswith("scripts/host-steps/"):
            continue
        m = re.search(r"check \"outside the (?:nightly )?backup window[^\"]*\" eq \"outside\" "
                      r"\\\n\s+'([^\n]*)'\n", text)
        assert m, f"{path}: its window check is not the one shape"
        out.append((path, m.group(1)))
    assert len(out) >= 4, out
    return out


@pytest.mark.parametrize("utc, answer", [
    ("2026-10-30T08:29:00Z", "outside"), ("2026-10-30T08:30:00Z", "inside"),
    ("2026-10-30T09:29:00Z", "inside"), ("2026-10-30T09:30:00Z", "outside"),      # MDT
    ("2026-11-06T08:30:00Z", "outside"), ("2026-11-06T09:29:00Z", "outside"),
    ("2026-11-06T09:30:00Z", "inside"), ("2026-11-06T10:29:00Z", "inside"),
    ("2026-11-06T10:30:00Z", "outside")])                                         # MST
def test_each_host_steps_check_answers_in_both_seasons(utc, answer):
    at = calendar.timegm(time.strptime(utc, "%Y-%m-%dT%H:%M:%SZ"))
    for path, expr in _host_step_checks():
        assert expr.startswith("t=$(date +%s);"), path
        got = subprocess.run(["bash", "-c", expr.replace("t=$(date +%s);", f"t={at};", 1)],
                             check=True, capture_output=True, text=True).stdout.strip()
        assert got == answer, (path, utc, got)


def test_a_host_step_that_cannot_read_the_zone_is_not_outside():
    noon = calendar.timegm((2026, 11, 6, 12, 0, 0, 0, 0, 0))
    for path, expr in _host_step_checks():
        script = expr.replace("t=$(date +%s);", f"t={noon};", 1).replace(
            "TZ=America/Denver", "TZ=Nowhere/Invalid")
        got = subprocess.run(["bash", "-c", script], check=True, capture_output=True,
                             text=True).stdout.strip()
        assert got == "zone unreadable", (path, got)
