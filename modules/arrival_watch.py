"""The combined deploy's ARRIVAL WATCH (Coverage's artboard A2; decided by the operator,
2026-10-03): after the batch, each deployed device's sent templates are watched for their
first data, for 15 minutes, never blocking and never rolling back.

**Why after the batch, and not in each device's verify.** The heartbeat fires every 5
minutes and Coverage's reader reads once a minute, so waiting per device would add 5 to 6
minutes to each; and SNMP's scrape target exists only once the batch's golden commit has
regenerated the targets, after the last device. The configuration that read back stays: a
scrape that has not arrived is not a reason to remove what landed.

**What it reads.** Nothing of its own: Coverage's not-reporting reader
(`readers.coverage_reporting`) stores, each minute, when each device's SNMP and IP SLA
targets were last scraped, its telemetry last streamed, and its last syslog line and
heartbeat. A cell has ARRIVED once that time is at or after the batch ended; the first time
the watch sees it is kept (the reader keeps only the last). NTP and LLDP are device state,
not an arrival, and are said as not read here. A source the reader could not ask leaves its
cells waiting and says why; at the deadline a cell still waiting is MISSING, named with the
device tab where its cause is looked for.

**The bound** (`WATCH_SECONDS`): about 2.5x the 6-minute worst case (a heartbeat period and
a reader cycle). The operator's next real Coverage deploy measures the real arrival times,
which the result shows as seconds after the batch, and the bound is revisited against them.

In memory, like the batch job it belongs to: a restart loses it, and the page says so.
"""

import logging
import threading
import time

log = logging.getLogger(__name__)

#: The watch's length: 2.5x the 6-minute worst case (a 5-minute heartbeat and a 1-minute
#: reader cycle), decided by the operator 2026-10-03, to be revisited against the arrival
#: times the first real Coverage deploy measures.
WATCH_SECONDS = 15 * 60
ANNOUNCER = "arrival-watch"
#: The batch's own key: the result card re-reads on it.
KEYS = ("deploy_job",)
#: The columns whose arrival Coverage's reader stores.
READ = ("snmp", "ip_sla", "telemetry", "syslog", "heartbeat")
WORDS = {"snmp": "SNMP", "syslog": "Syslog", "heartbeat": "Heartbeat", "ntp": "NTP",
         "lldp": "LLDP", "telemetry": "Telemetry", "ip_sla": "IP SLA", "cdp": "CDP"}

_watches: dict = {}
_lock = threading.Lock()


def _every() -> float:
    """The re-read interval: the reader's own (a faster re-read sees nothing new)."""
    from modules.readers.coverage_reporting import INTERVAL_SECONDS
    return float(INTERVAL_SECONDS)


def _hhmm(ts: float) -> str:
    return time.strftime("%H:%M:%S UTC", time.gmtime(ts))


def arrival(column: str, host: str, value, since: float) -> tuple:
    """``(at, why)``: when *column*'s data for *host* arrived at or after *since*, from
    Coverage's stored reading *value*, or ``(None, why)`` (why empty when simply not yet)."""
    from modules.readers import coverage_reporting as CR

    if value is None:
        return None, "Coverage's reading is not stored yet"
    if column in ("snmp", "ip_sla"):
        down = CR._source_down(value, "targets")
        if down:
            return None, f"the targets could not be read ({down})"
        mine = [t for t in (value.get("targets") or {}).get(host) or []
                if (t.get("file") == CR.IPSLA_FILE) == (column == "ip_sla")]
        if not mine:
            return None, "Prometheus has no target for it yet"
        seen = [t["last_scrape"] for t in mine
                if t.get("last_scrape") is not None and t["last_scrape"] >= since]
        return (min(seen), "") if seen else (None, "")
    down = CR._source_down(value, column)
    if down:
        return None, f"its source could not be read ({down})"
    at = (value.get(column) or {}).get(host)
    return (at, "") if at is not None and at >= since else (None, "")


def start(job_id: str, sent: dict, *, started: float = None, thread: bool = True) -> None:
    """Watch *sent* (``{device: [column, ...]}``, the templates each deployed device was
    sent) from *started* (the batch's end) for `WATCH_SECONDS`."""
    from modules.readers.coverage_reporting import NOT_READ

    started = time.time() if started is None else started
    cells = {}
    for host, columns in sent.items():
        cells[host] = {}
        for col in columns:
            if col in READ:
                cells[host][col] = {"state": "waiting", "at": None, "words": "not yet"}
            else:
                cells[host][col] = {"state": "not_read", "at": None,
                                    "words": NOT_READ.get(col, "its arrival is not read here")}
    with _lock:
        # Nothing sent that stayed (no device deployed, or none sent a template): nothing
        # to watch, said as ended rather than a watch that never moves.
        _watches[job_id] = {"started": started, "deadline": started + WATCH_SECONDS,
                            "ended": not cells, "cells": cells}
    log.info("arrival watch %s: %d device(s), until %s", job_id, len(cells),
             _hhmm(started + WATCH_SECONDS))
    if thread and cells:
        threading.Thread(target=_loop, args=(job_id,), name=f"arrival-{job_id}",
                         daemon=True).start()


def observe(job_id: str, value=None, now: float = None, *, read=True) -> bool:
    """Read Coverage's stored reading once and move each waiting cell: ARRIVED (its first
    sighting kept), MISSING once the deadline has passed, else WAITING with any reason.
    True when anything moved (the caller announces)."""
    from modules.readers.coverage_reporting import WHERE

    now = time.time() if now is None else now
    if value is None and read:
        from modules.device_page import _cached
        from modules.readers.coverage_reporting import NAME
        value, _at, _why = _cached(NAME)
    moved = False
    with _lock:
        w = _watches.get(job_id)
        if w is None or w["ended"]:
            return False
        for host, cols in w["cells"].items():
            for col, cell in cols.items():
                if cell["state"] in ("arrived", "not_read"):
                    continue
                at, why = arrival(col, host, value, w["started"])
                if at is not None:
                    new = {"state": "arrived", "at": at,
                           "words": f"arrived by {_hhmm(at)}, "
                                    f"{int(round(at - w['started']))} s after the batch"}
                elif now >= w["deadline"]:
                    new = {"state": "missing", "at": None, "where": WHERE.get(col, "monitoring"),
                           "words": f"not arrived in {WATCH_SECONDS // 60} min"
                                    + (f" ({why})" if why else "")}
                else:
                    new = {"state": "waiting", "at": None,
                           "words": "not yet" + (f": {why}" if why else "")}
                if new != cell:
                    cell.clear()
                    cell.update(new)
                    moved = True
        if now >= w["deadline"]:
            w["ended"], moved = True, True
    return moved


def _announce(job_id: str) -> None:
    try:
        from modules import invalidation
        invalidation.announce(KEYS, by=ANNOUNCER)
    except Exception as exc:                            # noqa: BLE001
        log.info("arrival watch %s: not announced (%s); the page shows it when reloaded",
                 job_id, exc)


def _loop(job_id: str, sleep=time.sleep) -> None:
    while True:
        sleep(_every())
        try:
            moved = observe(job_id)
        except Exception as exc:                        # noqa: BLE001
            log.error("arrival watch %s: a read raised (%s); it reads again in a minute",
                      job_id, exc)
            moved = False
        if moved:
            _announce(job_id)
        with _lock:
            w = _watches.get(job_id)
            if w is None or w["ended"]:
                return


def state(job_id: str):
    """``{"started", "deadline", "ended", "rows", "arrived", "missing", "waiting"}``, each
    row ``{"device", "cells": [{"column", "label", "state", "words", "where"}]}``, or None
    when this server holds no watch for the job."""
    with _lock:
        w = _watches.get(job_id)
        if w is None:
            return None
        rows, counts = [], {"arrived": 0, "missing": 0, "waiting": 0}
        for host, cols in w["cells"].items():
            cells = []
            for col, cell in cols.items():
                cells.append({"column": col, "label": WORDS.get(col, col), **cell})
                if cell["state"] in counts:
                    counts[cell["state"]] += 1
            rows.append({"device": host, "cells": cells})
        return {"started": w["started"], "deadline": w["deadline"], "ended": w["ended"],
                "started_words": _hhmm(w["started"]), "deadline_words": _hhmm(w["deadline"]),
                "minutes": WATCH_SECONDS // 60, "rows": rows, **counts}
