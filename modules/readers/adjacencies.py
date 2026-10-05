"""Is every routing adjacency committed intent implies UP, fleet-wide? A reader
job (register C38's second consumer, after the device page's Neighbours tab).

**One implementation, two consumers** (the operator, 2026-09-29): the
expected set and the comparison are `modules/neighbours`, exactly what the tab
draws; this reader runs it over every list's inventory so Needs attention can
say "OSPF between r3 and r4 is down" without a page doing fleet work per
request. It reads PROMETHEUS (four instant queries for the whole fleet) and
committed intent (two git calls per list), never a device.

**A link is one row, named by its pair** (C38's point: an adjacency names a
PAIR, so one link failure would otherwise fire two rows): both sides'
reports sit on the one row. A peer outside management is its own row, seen
from one side.

**Down during a deploy is normal**, so a failure becomes a row only once it
has held for `PERSIST_READS` consecutive reads (each a minute apart, the
routing jobs' scrape interval since 2026-10-01): a settle window passes, a
broken link stays. Its `since` is the first read that saw it, carried across
reads.
"""

import logging
import os
import time

from modules import reader_job

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 60
#: Two reads a minute apart: longer than a scrape interval, so one stale
#: sample cannot raise a row alone.
PERSIST_READS = 2


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def prometheus_all(list_name: str = "") -> tuple:
    """``(configured, {device: {metric: rows}}, {device: {job: 0|1}})`` for
    the whole fleet. Raises when Prometheus is configured and cannot be read,
    so the failure is a job-health row, never "every adjacency up"."""
    from modules.integrations.prometheus import PrometheusIntegration
    from modules.neighbours import SERIES

    prom = PrometheusIntegration(list_name=list_name) if list_name else PrometheusIntegration()
    if not prom.is_configured():
        return False, {}, {}
    results, up = {}, {}
    for metric in [m for _j, m in SERIES.values()] + ["up"]:
        q = 'up{job=~"ospf|ospfv3|bgp"}' if metric == "up" else metric
        r = prom._get("api/v1/query", query=q)
        if not r.get("ok"):
            raise RuntimeError(f"Prometheus could not be asked for {metric}: {r.get('error')}")
        for row in (r["response"].json().get("data") or {}).get("result") or []:
            dev = (row.get("metric") or {}).get("device")
            if not dev:
                continue
            if metric == "up":
                try:
                    up.setdefault(dev, {})[row["metric"]["job"]] = int(float(row["value"][1]))
                except (KeyError, ValueError, IndexError, TypeError):
                    pass
            else:
                results.setdefault(dev, {}).setdefault(metric, []).append(row)
    return True, results, up


def lists() -> list:
    """``[(list name, ListRef, [hostname])]`` for every registered list."""
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists, load_saved_devices
    from modules.nsot import listref

    out = []
    for entry in get_device_lists():
        name = entry.get("name") or ""
        path = os.path.join(LISTS_DIR, entry.get("filename") or "", "devices.csv")
        hosts = [d.get("hostname") for d in load_saved_devices(path) if d.get("hostname")]
        out.append((name, listref.resolve(name), hosts))
    return out


def _key(list_name: str, host: str, row: dict) -> str:
    if row.get("managed") and row.get("peer"):
        a, b = sorted((host, row["peer"]))
        return f"{list_name}|{row['proto']}|{a}|{b}|{row.get('network', '')}"
    return f"{list_name}|{row['proto']}|{host}|{row.get('address', '')}"


def read(previous=None, clock=time.time, source=None, population=None) -> dict:
    from modules.neighbours import committed_intents, compare

    if previous is None:
        got = reader_job.read_cached("adjacencies")
        previous = ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
    # P.8 step 5: every network's Prometheus, once per configuration, merged by device.
    from modules import integration_groups as IG

    configured, results, up = (source or (lambda: IG.merged("prometheus", prometheus_all)))()
    if not configured:
        return {"configured": False, "adjacencies": {}, "unmeasured": [], "errors": [],
                "checked": 0, "devices": 0}
    now = clock()
    seen, unmeasured, errors, checked, devices = {}, [], [], 0, 0
    for list_name, ref, hosts in (population or lists)():
        intents, err = committed_intents(ref.repo_dir)
        if err:
            errors.append(f"{list_name}: {err}")
        for host in hosts:
            devices += 1
            view = compare(intents, host, results.get(host, {}), up.get(host, {}))
            for p in view["protocols"]:
                if not p["measured"] and any(r["state"] == "unknown" for r in p["rows"]):
                    unmeasured.append({"list": list_name, "device": host, "protocol": p["words"],
                                       "why": p["why"]})
                for r in p["rows"]:
                    if r["state"] in ("up", "down", "not_seen"):
                        checked += 1
                    if r["state"] not in ("down", "not_seen"):
                        continue
                    k = _key(list_name, host, r)
                    e = seen.setdefault(k, {"list": list_name, "protocol": p["words"],
                                            "devices": [], "managed": bool(r.get("managed")),
                                            "network": r.get("network", ""), "sides": []})
                    if host not in e["devices"]:
                        e["devices"].append(host)
                    if r.get("managed") and r.get("peer") and r["peer"] not in e["devices"]:
                        e["devices"].append(r["peer"])
                    e["sides"].append({"device": host, "via": r.get("via", ""),
                                       "address": r.get("address", ""), "state": r["state"],
                                       "words": r.get("words", "")})
    prev = previous.get("adjacencies") or {}
    for k, e in seen.items():
        before = prev.get(k) or {}
        e["reads"] = int(before.get("reads") or 0) + 1
        e["since"] = before.get("since") or _iso(now)
        e["devices"] = sorted(e["devices"])
    return {"configured": True, "adjacencies": seen, "unmeasured": unmeasured,
            "errors": errors, "checked": checked, "devices": devices}


READER = reader_job.register(reader_job.Reader(
    name="adjacencies",
    what="whether every routing adjacency committed intent implies is up (C38)",
    endpoints=("Prometheus: GET /api/v1/query for ospfNbrState, ospfv3NbrState, "
               "cbgpPeer2State and up{job=~\"ospf|ospfv3|bgp\"} (the whole fleet)",
               "this host: each list's committed host_vars at HEAD"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the routing jobs' scrape interval (60 s since 2026-10-01): a faster read "
                    "would only re-read the same sample, and a failure is raised after "
                    f"{PERSIST_READS} reads, so a deploy's settle window passes first"),
    read=read,
    invalidates=("adjacencies",),
    remedy="Read the error above: it names what Prometheus or the repository answered",
    window="Prometheus's last sample of each device's routing tables",
))
