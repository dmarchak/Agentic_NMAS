"""Did a device restart? A reader job (the operator, 2026-10-02: five devices restarted in a
day and the tool noticed none). `modules/restarts.py` holds the rules; this is the read.

Each minute, ONE instant query asks Prometheus which devices' `sysUpTime` counter fell since
the last read (`resets(...) > 0`, so a fleet of thousands costs one query when nothing
restarted), then one range query per device that did, to find where it fell. A restart not
seen before is recorded (`restarts.jsonl`), judged planned against the planned windows, and
its reason read from the device once. The first read looks back `FIRST_LOOKBACK_SECONDS`,
so restarts from before the reader existed are found too; a read after a gap looks back
over the gap, at most `MAX_LOOKBACK_SECONDS`, and says when it was cut.
"""

import logging
import os
import re
import time

from modules import reader_job

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 60
#: Long enough to find the five restarts of 2026-10-01 and 02 on the first read, and
#: within Prometheus's retention (90 days).
FIRST_LOOKBACK_SECONDS = 48 * 3600
MAX_LOOKBACK_SECONDS = 48 * 3600
#: The range query's step: the SNMP scrape interval measured on the host (60 s), halved.
STEP_SECONDS = 30
_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def prometheus_series(window: int, now: float) -> tuple:
    """``(configured, {device: [[[ts, ticks], ...] per series]})`` for every device whose
    counter fell inside *window*. Raises when Prometheus is configured and cannot be read,
    so the failure is a job-health row, never "nothing restarted"."""
    from modules.integrations.prometheus import PrometheusIntegration

    prom = PrometheusIntegration()
    if not prom.is_configured():
        return False, {}
    r = prom._get("api/v1/query", query=f"resets(sysUpTime[{int(window)}s]) > 0")
    if not r.get("ok"):
        raise RuntimeError(f"Prometheus could not be asked for restarts: {r.get('error')}")
    devices = sorted({(row.get("metric") or {}).get("device", "")
                      for row in (r["response"].json().get("data") or {}).get("result") or []})
    out = {}
    for dev in devices:
        if not dev or not _NAME.match(dev):
            continue
        q = prom._get("api/v1/query_range", query=f'sysUpTime{{device="{dev}"}}',
                      start=now - window, end=now, step=STEP_SECONDS)
        if not q.get("ok"):
            raise RuntimeError(f"Prometheus could not be asked for {dev}'s uptime: {q.get('error')}")
        out[dev] = [row.get("values") or []
                    for row in (q["response"].json().get("data") or {}).get("result") or []]
    return True, out


def population() -> dict:
    """``{hostname: (list name, device dict)}`` over every registered list."""
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists, load_saved_devices

    out = {}
    for entry in get_device_lists():
        path = os.path.join(LISTS_DIR, entry.get("filename") or "", "devices.csv")
        for d in load_saved_devices(path):
            if d.get("hostname"):
                out.setdefault(d["hostname"], (entry.get("name") or "", d))
    return out


def read(previous=None, clock=time.time, source=None, devices=None, reason=None) -> dict:
    from modules import restarts as R

    if previous is None:
        got = reader_job.read_cached("restarts")
        previous = ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
    now = clock()
    last = R._epoch(previous.get("last_read_at", "")) if previous.get("last_read_at") else 0
    wanted = (now - last + 2 * INTERVAL_SECONDS) if last else FIRST_LOOKBACK_SECONDS
    window = int(min(max(wanted, 5 * INTERVAL_SECONDS), MAX_LOOKBACK_SECONDS))
    cut = wanted > MAX_LOOKBACK_SECONDS
    configured, series = (source or prometheus_series)(window, now)
    if not configured:
        return {"configured": False, "last_read_at": _iso(now), "new": [], "window": window}
    managed = (devices or population)()
    stored = R.events()
    if stored["state"] == "unreadable":
        raise RuntimeError(f"the restart record could not be read: {stored.get('error')}")
    planned = R._read_jsonl(R._data("planned_restarts.jsonl"))
    if planned["state"] == "unreadable":
        raise RuntimeError(f"the planned-restart record could not be read: {planned.get('error')}")
    rows, new, unmanaged = list(stored["rows"]), [], []
    for host, all_series in sorted(series.items()):
        list_name, dev = managed.get(host, ("", None))
        if dev is None:
            unmanaged.append(host)
            continue
        for values in all_series:
            for d in R.drops(values):
                if R.known(host, d["at"], rows, list_name):
                    continue
                p = R.planned_for(host, d["at"], planned["rows"], list_name)
                why = (reason or R.read_reason)(dev)
                row = {"device": host, "list": list_name, "at": _iso(d["at"]),
                       "last_seen": _iso(d["last_seen"]),
                       "seen_at": _iso(d["seen_at"]), "planned": bool(p),
                       "planned_by": (p or {}).get("by", ""), "planned_why": (p or {}).get("why", ""),
                       "reason": why.get("reason", ""), "crash_file": why.get("crash_file", ""),
                       "reason_error": why.get("error", ""), "found_by": "sysUpTime reset"}
                R.append(row)
                rows.append(row)
                new.append(row)
                log.warning("restarts: %s", R.words(row))
    horizon = now - R.ATTENTION_DAYS * 86400
    recent = [r for r in R.judged(rows, planned["rows"])
              if not r.get("planned") and R._epoch(r.get("at", "")) >= horizon]
    recent.sort(key=lambda r: R._epoch(r.get("at", "")), reverse=True)
    return {"configured": True, "last_read_at": _iso(now), "window": window, "cut": cut,
            "new": new, "recent_unplanned": recent, "unmanaged": sorted(set(unmanaged)),
            "devices": len(managed)}


READER = reader_job.register(reader_job.Reader(
    name="restarts",
    what="whether a device restarted, planned or not (the operator, 2026-10-02)",
    endpoints=("Prometheus: GET /api/v1/query resets(sysUpTime[window]) > 0, then "
               "/api/v1/query_range sysUpTime for each device that restarted",
               "the device that restarted, once: `" + "show version | include reason|returned to"
               "|uptime is` (read-only)",
               "this host: restarts.jsonl and planned_restarts.jsonl"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the SNMP scrape interval (60 s): a faster read would re-read the same "
                    "sample, and a restart is found within a minute of its first sample"),
    read=read,
    invalidates=("restarts",),
    remedy="Read the error above: it names what Prometheus or the record answered",
    window="Prometheus's sysUpTime samples since the last read",
))
