"""A person acknowledging an EVENT row on Needs attention (the operator, 2026-10-02).

Some rows are about something that HAPPENED and cannot un-happen: an unplanned restart, a
line authorised again and again. Nothing will ever make the condition resolve, so without
a person's word the row stays until time takes it. Acknowledging is that word: a reason
with the shape of one (the authorisation rule, `authorisation.SHAPE_RULE`), recorded with
who and when, and the row leaves Needs attention. The event itself stays where it is
recorded (a restart in the device's History, marked acknowledged, by whom and why).

**An acknowledgement covers ONE event and never a later one.** It is keyed on the row's
id AND its *event* (a restart's time; a repeated authorisation's latest authorisation), so
a new restart is a new row, and the same line authorised once more after the
acknowledgement raises the row again.

Which kinds a person acknowledges here is `attention.ACKNOWLEDGED_HERE`; every other kind
clears when its condition resolves, or by its own control (a host step said done, a held
push acknowledged on the Remote card), as `attention.CLEARS` says on the row.

Store: `acknowledgements.jsonl` in the data folder, append-only, 0600 (a person's name and
reason are in it).
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)


def _path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, "acknowledgements.jsonl")


def read() -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows": [...]}``. Unreadable is its own
    answer: a page that read it as "nothing acknowledged" would raise every acknowledged
    row again, and one that read it as "all acknowledged" would hide them."""
    path = _path()
    if not os.path.exists(path):
        return {"state": "absent", "rows": []}
    rows = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    rows.append(json.loads(line))
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [], "error": f"{type(exc).__name__}: {exc}"}
    return {"state": "ok", "rows": rows}


def covering(row_id: str, event: str, rows: list):
    """The acknowledgement of exactly this row's event, or None."""
    for a in reversed(rows):
        if a.get("row") == row_id and str(a.get("event")) == str(event):
            return a
    return None


def within_band(ack: dict, reading: dict = None) -> dict:
    """Whether a band acknowledgement holds now (C433; C533): THE judgement, for Needs
    attention and the device page alike. The band recorded with *ack* GOVERNS, never a band a
    reading carries from an older acknowledgement (the reader stores its last run's band until
    it runs again: on 2026-10-06 it held 3.235 from the day before while the newest
    acknowledgement said 3.72). The value is the newest measurement there is: the reader's
    reading, or the one taken with the acknowledgement, whichever was read later.

    ``{"band", "band_at", "value", "value_at", "value_from", "in_band"}``; ``in_band`` None when
    no value was ever read."""
    band = float(ack["band"])
    candidates = []
    if (reading or {}).get("value") is not None:
        candidates.append((str(reading.get("at") or ""), float(reading["value"]), "the reader"))
    if ack.get("value") is not None:
        candidates.append((str(ack.get("at") or ""), float(ack["value"]),
                           "the acknowledgement"))
    if not candidates:
        return {"band": band, "band_at": ack.get("at", ""), "value": None, "value_at": "",
                "value_from": "", "in_band": None,
                "why": (reading or {}).get("why") or "no value has been read"}
    at, value, source = max(candidates, key=lambda c: c[0])
    return {"band": band, "band_at": ack.get("at", ""), "value": value, "value_at": at,
            "value_from": source, "in_band": value <= band}


def devices_of(entry: dict, host_by_address: dict = None) -> list:
    """The devices an acknowledgement is about: its own `devices` (recorded since 2026-10-05),
    else read from its row (an authorisation's `authorisations:<list>:<device>:…`, an alert
    series' `instance=<address>`, through *host_by_address*), else none. History, Needs
    attention and the device page all ask this, so a kind is never readable in one and not
    another (C433's band acknowledgements were in none)."""
    if entry.get("devices"):
        return [str(d) for d in entry["devices"]]
    row = str(entry.get("row", ""))
    if row.startswith("authorisations:"):
        parts = row.split(":")
        return [parts[2]] if len(parts) > 2 and parts[2] else []
    if row.startswith("grafana:series:"):
        for pair in row.split("|", 1)[-1].split(","):
            key, _, val = pair.partition("=")
            if key in ("device", "hostname", "host") and val:
                return [val]
            if key == "instance" and val:
                host = (host_by_address or {}).get(val.split(":")[0])
                return [host] if host else []
    return []


def standing_bands(rows: list) -> list:
    """The band acknowledgements in force (C433): the newest per alert series. Each holds
    while its series' value stays at or under its band, firing or not, so a person can find
    and review it even when it hides nothing."""
    latest = {}
    for a in rows:
        if a.get("band") is not None:
            latest[a.get("row")] = a
    return sorted(latest.values(), key=lambda a: a.get("at", ""), reverse=True)


def record(row_id: str, event: str, *, why: str, by: str, verified: str,
           kind: str, what: str, band: float = None, value: float = None,
           devices: list = None) -> dict:
    """Append one acknowledgement. The caller has checked the row exists now and the
    reason's shape (`attention.acknowledge`, the one caller). *band* and *value* are a chronic
    alert's measured band and its value then (C433): it holds only within the band. *devices*
    are the row's devices, so History reads it on each device's timeline."""
    from modules.config import open_secure
    from modules.filestore import PathLock
    from modules.redact import redact_text

    # An audit record is masked AT REST: a row's words quote its source (an authorised
    # line), and a reason is a person's free text.
    entry = {"row": row_id, "event": str(event), "kind": kind, "what": redact_text(what),
             "why": redact_text(why.strip()), "by": by, "verified": verified,
             "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    if band is not None:
        entry["band"], entry["value"] = float(band), (None if value is None else float(value))
    if devices:
        entry["devices"] = [str(d) for d in devices]
    path = _path()
    with PathLock(path):
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    log.info("acknowledged %s (event %s) by %s", row_id, event, by)
    return entry
