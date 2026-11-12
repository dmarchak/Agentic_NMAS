"""Is a device DRAINED now? A reader job (C3166's slice 3, the operator's plan, 2026-11-12:
"a new drained reader: the device header (every tab) and Devices").

**One background owner.** The measurement itself is `modules/drained.py` (`measure`): one
golden `git grep` and five Prometheus instant queries for a whole network, and two range
queries per device it finds drained. This reader runs it for every network on its interval and
stores each network's verdicts; the device page's header (every tab), the header's badge alone
and Devices read the stored value (`drained.current`, `drained.held`) and draw its age. No page
asks Prometheus.

**Switched off** (`drained.ENABLED`, C552): while the measurement is off this reader asks
nothing at all, no network listed and no query sent, and stores that it is off; its value never
moves, so it announces only on a change, with a keepalive.

**A failed network keeps its last good verdicts** (reader_job rule 3), its error said beside
them: one network's Prometheus refusing never empties another's, and a page draws what it holds
with the failure. Every network failing is the read failing (the job-health row).

**Display only** (CLAUDE.md, the rule that no page load waits on a source, its Display only
clause): the heal pipeline and deploys never read this value.
"""

import json
import logging
import time

from modules import reader_job

log = logging.getLogger(__name__)

NAME = "drained"
#: The measurement looks back 3 minutes (`drained.QUIET_SECONDS`) over a 2-minute rate of the
#: 60 s SNMP scrape: read faster and the same samples are re-read; the badge it feeds moved at
#: most every 30 s before (a per-process cache of 30 s this replaces).
INTERVAL_SECONDS = 60
#: The keepalive for a value that does not move (rule 9): five intervals.
KEEPALIVE_SECONDS = 300


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _lists() -> list:
    from modules.device import get_device_lists
    return [e.get("name") or "" for e in get_device_lists() if e.get("name")]


def read(previous=None, clock=None, population=None, measure=None) -> dict:
    """``{"enabled": bool, "networks": {list: {"verdicts": {device: verdict}, "at": iso,
    "error": str}}}``: each network's devices measured drained now (only those), when, and
    why the newest measurement failed (its last good verdicts kept). Raises when every network
    failed, so the failure is the reader's own row."""
    from modules import drained as D

    if not D.ENABLED:
        return {"enabled": False, "networks": {}}
    if previous is None:
        got = reader_job.read_cached(NAME)
        previous = ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
    from modules.nsot import listref

    before = previous.get("networks") or {}
    measure = measure or D.measure
    networks, failed = {}, []
    for name in (population or _lists)():
        # Keyed by the network's one id (C1903), never its display name.
        if not listref.exists(name):
            log.warning("drained reader: no network answers to %s now: not measured", name)
            continue
        now = (clock or time.time)()
        try:
            got = {d: v for d, v in measure(name, now).items() if v.get("drained")}
            entry = {"verdicts": got, "at": _iso(now), "error": ""}
        except Exception as exc:                  # noqa: BLE001 (kept, said, never raised alone)
            log.warning("drained reader: %s could not be measured: %s", name, exc)
            kept = listref.keyed(before, name) or {}
            entry = {"verdicts": kept.get("verdicts") or {}, "at": kept.get("at", ""),
                     "error": str(exc) or type(exc).__name__}
            failed.append(f"{name}: {entry['error']}")
        networks[listref.network_id(name)] = entry
    if networks and len(failed) == len(networks):
        raise RuntimeError("no network could be measured: " + "; ".join(failed))
    return {"enabled": True, "networks": networks}


def _moved(previous, value) -> bool:
    """Announce when what a page draws moves: a verdict, or a network's error (never only a
    measurement's time)."""
    def drawn(v):
        # As JSON with sorted keys: the stored previous value was written that way.
        return json.dumps([bool((v or {}).get("enabled")),
                           {n: [x.get("verdicts") or {}, x.get("error", "")]
                            for n, x in ((v or {}).get("networks") or {}).items()}],
                          sort_keys=True, default=str)
    return drawn(previous) != drawn(value)


READER = reader_job.register(reader_job.Reader(
    name=NAME,
    what="whether each device is measured drained now (no host traffic but its management "
         "path), for the device page's header and Devices (C551, C3166)",
    endpoints=("Prometheus: GET /api/v1/query for ifOperStatus, the unicast rates in and out "
               "and their 3-minute peaks, for each network's devices; /api/v1/query_range for "
               "a drained device's since",
               "this host: each network's committed goldens (one git grep), for the "
               "management path"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the measurement's own window: a 2-minute rate of the 60 s SNMP scrape, "
                    "quiet for 3 minutes; faster re-reads the same samples (while switched "
                    "off, C552, a read asks nothing)"),
    read=read,
    invalidates=("drained",),
    remedy="Read the error above: it names what Prometheus or the repository answered",
    window="Prometheus's last 3 minutes of each device's interface counters",
    announce_if=_moved,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
