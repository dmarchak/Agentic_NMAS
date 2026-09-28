"""C92: device reachability as a reader job, the sixth instance of
modules/reader_job.py.

**What it replaces.** The online dot was ONE probe, five seconds old at best,
and a single miss drew "offline" (C92, the operator, 2026-09-27). Measured over
106 hours of the host's own transition log: 2,946 offline runs, and 93% of
them ended at the very next probe. Worse, r2's dot went offline right after a
restore changed its core link: noisy in a way indistinguishable from the
failure people fear most, at the moment they most expect it.

**What it keeps, per device:** the last result, WHICH probe answered (ICMP from
the NMAS, or a TCP connection to port 22; on the deployment host ICMP is not
permitted for the service's user, so the honest claim there is the TCP one),
when it was checked, the consecutive-miss count, since when the current state
has held, and the threshold it was judged against. "Answering" means fewer
consecutive misses than the threshold; one miss is "missed a probe", never
"offline".

**One owner for the answer every consumer already reads.** `STATUS` is the
dict the app has always handed to the dot, Refresh Hostnames, Auto-Create,
the topology link reads, the agent's device context and the NetBox sync (as
`device_status_cache`). The reader keeps it current, so each of those now
acts on the thresholded answer without being edited.

**The population is every list's inventory**, not only the active list's: a
device on another list, or a NetBox-sourced list with no CSV, was never
probed and drew as offline (§14).

**Announcing** (rule 9, with the keepalive this reader needed): the value
moves every cycle (a probe time), so it announces when who is answering
CHANGES, and at least once a minute regardless, so a page never mistakes the
reader's silence for nothing having changed.
"""

import ipaddress
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor

from modules import reader_job

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 5
KEEPALIVE_SECONDS = 60

#: address -> answering (bool): the dict every consumer already reads.
STATUS: dict = {}

CLAIM_ICMP = "answered ICMP from the NMAS within 2 s"
CLAIM_TCP = "accepted a TCP connection on port 22 within 2 s"
CLAIM_NONE = "answered neither ICMP nor TCP 22 within 2 s each"


def miss_threshold(list_name: str = "", hostname: str = "") -> int:
    """How many consecutive misses before a device is "not answering".

    THE ONE PLACE this is decided, so P.8 (per-list settings) can make it per
    network without the reader changing: the operator's own example of a
    per-network value (another fleet converges and answers differently).

    3, from C92's measurement of the host's transition log (106 h, 2026-09-23
    to 09-27): offline runs fall from 2,946 at one miss to 195 at two and 99
    at three; genuine outages run past 60 s, several devices at once. At a 5 s
    cycle, 3 misses name a real outage within about 15 s.
    """
    return 3


def probe(ip: str) -> tuple:
    """(answered, claim). The claim says which probe answered."""
    try:
        from ping3 import ping
        response = ping(ip, timeout=2, unit="ms")
        if response and response > 0:
            return True, CLAIM_ICMP
    except Exception:                                   # noqa: BLE001
        log.debug("reachability: ICMP to %s not possible or failed", ip, exc_info=True)
    import socket
    try:
        with socket.create_connection((ip, 22), timeout=2):
            return True, CLAIM_TCP
    except Exception:                                   # noqa: BLE001
        return False, CLAIM_NONE


def population() -> list:
    """[(address, hostname, list)] across every registered list, one entry
    per address (a device on two lists is probed once)."""
    from modules.config import LISTS_DIR
    from modules.device import get_device_lists, load_saved_devices

    out, seen = [], set()
    for entry in get_device_lists():
        path = os.path.join(LISTS_DIR, entry.get("filename") or "", "devices.csv")
        try:
            devices = load_saved_devices(path)
        except Exception as exc:                        # noqa: BLE001
            log.error("reachability: list %s could not be read: %s", entry.get("name"), exc)
            continue
        for d in devices:
            ip = (d.get("ip") or "").strip()
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if addr.is_unspecified or addr.is_multicast or ip in seen:
                continue
            seen.add(ip)
            out.append((ip, d.get("hostname") or "", entry.get("name") or ""))
    return out


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def read(probe_fn=None, targets=None, previous=None, clock=time.time) -> dict:
    probe_fn = probe_fn or probe
    targets = population() if targets is None else targets
    if previous is None:
        got = reader_job.read_cached("reachability")
        previous = (((got.get("doc") or {}).get("last_good") or {}).get("value") or {}
                    ).get("devices") or {}
    now = clock()
    results = {}
    if targets:
        with ThreadPoolExecutor(max_workers=min(20, len(targets))) as pool:
            futures = {ip: pool.submit(probe_fn, ip) for ip, _, _ in targets}
            for ip, fut in futures.items():
                try:
                    results[ip] = fut.result()
                except Exception as exc:                # noqa: BLE001
                    results[ip] = (False, f"the probe raised {type(exc).__name__}")
    devices = {}
    for ip, hostname, list_name in targets:
        answered, claim = results.get(ip, (False, CLAIM_NONE))
        prev = previous.get(ip) or {}
        misses = 0 if answered else int(prev.get("consecutive_misses") or 0) + 1
        threshold = miss_threshold(list_name, hostname)
        answering = misses < threshold
        held = prev and prev.get("answering") == answering and prev.get("since")
        devices[ip] = {"address": ip, "hostname": hostname, "list": list_name,
                       "answering": answering, "last_result": "answered" if answered else "missed",
                       "claim": claim, "checked_at": _iso(now), "consecutive_misses": misses,
                       "threshold": threshold, "since": held or _iso(now)}
        if prev and prev.get("answering") != answering:
            # The transition log C92 was measured from keeps its shape.
            log.info("reachability: %s (%s) answering=%s after %d miss(es)",
                     ip, hostname, answering, misses)
    # Update the shared dict in place, key by key: consumers read it from
    # other threads, and a clear-then-fill would show every device as
    # unknown for a moment.
    for ip, d in devices.items():
        STATUS[ip] = d["answering"]
    for ip in [k for k in STATUS if k not in devices]:
        STATUS.pop(ip, None)
    counts = {"answering": sum(1 for d in devices.values() if d["answering"]),
              "not_answering": sum(1 for d in devices.values() if not d["answering"]),
              "missed_last_probe": sum(1 for d in devices.values()
                                       if d["last_result"] == "missed")}
    return {"devices": devices, "counts": counts}


def changed(previous: dict, value: dict) -> bool:
    """Who is answering changed (the announcement's trigger)."""
    before = {ip: d.get("answering") for ip, d in ((previous or {}).get("devices") or {}).items()}
    after = {ip: d.get("answering") for ip, d in ((value or {}).get("devices") or {}).items()}
    return before != after


READER = reader_job.register(reader_job.Reader(
    name="reachability",
    what="whether each device answers the NMAS, judged over consecutive probes (C92)",
    endpoints=("ICMP, then TCP 22, to each device's management address",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the dot's own 5 s cycle, kept; a state change is judged over "
                    "consecutive probes (threshold from C92's 106 h measurement)"),
    read=read,
    invalidates=("reachability",),
    remedy="Read the error above: it names what the probe cycle could not do",
    window="the last probe of each device, with the misses counted since its last answer",
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
