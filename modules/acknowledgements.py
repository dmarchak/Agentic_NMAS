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
push acknowledged in History's Remote set-up), as `attention.CLEARS` says on the row.

Store: `acknowledgements.jsonl` in the data folder, append-only, 0600 (a person's name and
reason are in it); or, once a person moves it on Settings › Installation › Connections, the
records database (K31: a line store, `records_migrate`, one for the installation). `read` and
`record` are its only seam, so both backends answer the same.
"""

import json
import logging
import os
import time

log = logging.getLogger(__name__)


#: The store's name on the records database (`records_db.STORES`).
STORE = "acknowledgements"

#: When a down/up cycle has settled (C2316): no event for this long after its last. About 2.5x
#: the outage-to-recovery times measured in blind session 6 (R3: the first ADJCHG DOWN at
#: 00:44:36 to the revert's recovery at 00:51:14, 6.6 min; R8: 01:22:36 to FULL at 01:28:26,
#: 5.8 min; 2026-11-03).
STABLE_SECONDS = 15 * 60

#: The longest planned quiet period one acknowledgement may name (C2316's "acknowledge for N
#: hours"): a day, the adjacency log's own window for a row.
MAX_HOURS = 24


def _epoch(text):
    import calendar
    try:
        return float(calendar.timegm(time.strptime(str(text)[:19], "%Y-%m-%dT%H:%M:%S")))
    except (TypeError, ValueError):
        return None


def covers(ack: dict, events, now: float = None) -> dict:
    """Whether *ack* covers a band row's *events* (their epochs), by the operator's rule
    (C2316, 2026-11-03): an acknowledgement covers the events up to its own time, and the
    down/up cycle under way then until it settles (no event for `STABLE_SECONDS`); any later
    event raises the row again. One given for N hours (*until*) covers every event to its
    expiry, a planned quiet period, and none after it.

    ``{"covered", "after", "until", "expired"}``: *after* the first event it does not cover,
    or None. An acknowledgement with no readable time covers nothing."""
    now = time.time() if now is None else now
    at = _epoch(ack.get("at"))
    until = _epoch(ack.get("until")) if ack.get("until") else None
    out = {"covered": False, "after": None, "until": ack.get("until") or "",
           "expired": bool(until is not None and now > until)}
    if at is None:
        return out
    events = sorted(float(e) for e in events or [])
    edge = until if until is not None else at
    before = [e for e in events if e <= edge]
    # The cycle under way at the acknowledgement: its last event within STABLE_SECONDS of it.
    # A planned quiet period ends at its expiry, so it carries no cycle past it.
    chain = before[-1] if (until is None and before and at - before[-1] < STABLE_SECONDS) \
        else None
    for e in events:
        if e <= edge:
            continue
        if chain is not None and e - chain < STABLE_SECONDS:
            chain = e
            continue
        out["after"] = e
        return out
    out["covered"] = True
    return out


def _path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, "acknowledgements.jsonl")


def files() -> dict:
    """``{"": path}`` when the file exists, else ``{}``: the store's files, as the records
    migration counts them (one for the installation)."""
    path = _path()
    return {"": path} if os.path.exists(path) else {}


def _on_database() -> bool:
    from modules import records_db

    return records_db.backend(STORE) == records_db.POSTGRES


def read() -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows": [...]}``. Unreadable is its own
    answer: a page that read it as "nothing acknowledged" would raise every acknowledged
    row again, and one that read it as "all acknowledged" would hide them. On the records
    database, one that does not answer is unreadable too."""
    if _on_database():
        from modules import records_migrate

        try:
            return {"state": "ok", "rows": records_migrate.table_lines("", store=STORE)}
        except Exception as exc:                      # noqa: BLE001 (said, never "none")
            first = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
            return {"state": "unreadable", "rows": [],
                    "error": f"the records database: {type(exc).__name__}: {first}"}
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


def current(rows: list, cut: dict = None) -> list:
    """*rows* without an acknowledgement made at or before the CUT of a device's name it is
    about (C1476): a row keyed by a name (an adjacency, an alert series' `device` label)
    acknowledged for a retired or abandoned device of the name is not the new device's, so it
    hides none of the new one's rows. It can only ever hide LESS: an acknowledgement dropped
    here covers nothing, and none is added. One whose devices cannot be named (an older
    series' `instance=` alone) is kept, as before. The record keeps every one (History reads
    them all). *cut*: `retire.name_cuts_everywhere`'s, read here when not given."""
    from modules.nsot import retire

    if not rows:
        return []
    cut = retire.name_cuts_everywhere() if cut is None else cut
    if not cut:
        return list(rows or [])
    return [a for a in rows or []
            if not any(retire.before_retirement(cut, d, a.get("at", ""))
                       for d in devices_of(a))]


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
           devices: list = None, disposition: str = "", hours: float = None) -> dict:
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
    if disposition:
        # What the person found (C2295): kept on the entry History draws.
        entry["disposition"] = disposition
    if hours:
        # A planned quiet period (C2316): every event to its expiry is covered, none after.
        entry["until"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime(time.time() + float(hours) * 3600))
    line = json.dumps(entry, sort_keys=True)
    if _on_database():
        from modules import records_migrate

        # Raises naming why when the database cannot take it: an acknowledgement that was not
        # kept is never answered as recorded.
        records_migrate.append_lines("", [line], store=STORE)
    else:
        path = _path()
        with PathLock(path):
            with open_secure(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    log.info("acknowledged %s (event %s) by %s", row_id, event, by)
    return entry
