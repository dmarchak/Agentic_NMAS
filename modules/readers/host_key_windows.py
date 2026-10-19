"""Has a planned window that expected new SSH host keys closed? A reader job (C906; the
operator, 2026-10-16: "record every key a window accepts").

A window declared with `new_host_keys` (`restarts.record_planned`, a lab redeploy) lets
Mercury keep one new key per device it meets inside the window, with no person looking at
each. Once the window can take no more (its end plus the 15-minute slack, or its early end),
this reader writes ONE summary of what it took (`host_keys.close_windows`): "<n> new host keys
accepted during '<reason>'", which Needs attention shows until a person acknowledges it.
Before that, it ENDS each open window every device of which has answered with its new key
(`host_keys.complete_windows`, C1389), so such a window is summed up within a minute of its
last key.

The close is observed HERE, by something that runs, and never inferred when a page is read:
a page read would write, and two page reads at once could write twice. The write is
idempotent (a window already summed up is skipped, under a lock across processes), so two
runs, or two processes, write it once. It is its own reader rather than a step of the
restarts reader because that one stops when Prometheus is not configured, and a window
closes whether or not anything measures restarts.
"""

import time

from modules import reader_job

INTERVAL_SECONDS = 60


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def read(clock=time.time) -> dict:
    from modules import host_keys

    now = clock()
    # First, end each open window every device of which has answered with its new key (C1389:
    # one covering nothing more must not stay open for a stray key or restart); then sum up
    # every window that has closed, those it just ended among them, so the summary appears
    # within a minute of the last key and not at the declared end plus the slack.
    done = host_keys.complete_windows(now=now)
    got = host_keys.close_windows(now=now)
    return {"read_at": _iso(now), "closed": got["closed"], "open": got["open"],
            "ended": done["ended"], "not_ended": done["skipped"],
            "written": [{"window": s["window"], "count": s["count"], "why": s["why"]}
                        for s in got["written"]]}


READER = reader_job.register(reader_job.Reader(
    name="host-key-windows",
    what=("whether a planned window that expected new SSH host keys has closed, and if so "
          "its one summary of the keys it took (C906)"),
    endpoints=("this host: planned_restarts.jsonl, planned_restart_ends.jsonl, "
               "ssh_host_keys.json and host_key_windows.jsonl",
               "the window's network's Grafana, only when it ends a window that set a silence "
               "(the silence's end moved, restarts.end_window)"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the restarts reader's interval (60 s), which judges the same windows: a "
                    "window's summary appears within a minute of its close, against a "
                    "15-minute slack after its end"),
    read=read,
    invalidates=("host_keys",),
    remedy="Read the error above: it names the record that could not be read",
    window="every planned window recorded",
))
