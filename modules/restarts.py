"""Device restarts: noticed, told planned from unplanned, and kept (the operator, 2026-10-02).

Five devices restarted in a day and the tool noticed none of them: r3 crashed during the
nightly backup ("Critical software exception", a crash file saved) and four switches reloaded
for "Unknown reason". The operator found r3's only because a comment line went missing.

**A restart is the device's uptime counter going BACKWARDS** (SNMP `sysUpTime`, already
scraped), found where the counter dropped. Never a boot time computed as now minus uptime:
s3's clock runs at about 0.55 of real time and s4's at 0.75, so a computed boot time drifts
forward all day and would invent a restart every read.

**Planned or not.** A restart is planned when the tool performed it (its reload records one)
or was told about it beforehand (`record_planned()`, which the lab's redeploy and a person on
the host use, `scripts/nmas-planned-restart`). Anything else is unplanned, including a
`reload` a person typed on the device: the device's own reason says so, and the tool was not
told.

**The reason is the device's own**, read once per restart (`show version | include
reason|returned|uptime`, the read-only allowlist's command), with the crash file IOS-XE names
when it saved one. A reason that could not be read is said, never guessed.

Stores, both in the data folder, append-only, 0600 (a person's name and reason are in them):
`restarts.jsonl` (every restart seen, planned or not) and `planned_restarts.jsonl`.
"""

import json
import logging
import os
import re
import time

log = logging.getLogger(__name__)

#: How close a restart must fall to a planned window's edges to count as that window's.
#: A planned reload's own boot takes minutes (a vIOS 2 to 6, measured on the lab's
#: redeploy), so a restart up to this long after the window's end is still the plan's.
PLANNED_SLACK_SECONDS = 900
#: Two drops of one device closer than this are one restart, seen twice (a read window
#: overlaps the last one, and the drop's time is computed from the device's own ticks).
SAME_RESTART_SECONDS = 600
#: How long an unplanned restart stays a Needs attention row, said on the row.
ATTENTION_DAYS = 7

_REASON = re.compile(r"^\s*Last reload reason:\s*(.+?)\s*$", re.M | re.I)
_RETURNED = re.compile(r"^\s*System returned to ROM by\s+(.+?)\s*$", re.M | re.I)
_CRASH = re.compile(r"check\s+((?:bootflash|flash|harddisk|crashinfo):\S*crashinfo\S*)", re.I)
_CRASH_ANY = re.compile(r"((?:bootflash|flash|harddisk|crashinfo):\S*crashinfo\S*)", re.I)

#: The command the reason is read with: a `show` with an `include` filter, which the
#: read-only allowlist passes (modules/readonly_commands.py).
REASON_COMMAND = "show version | include reason|returned to|uptime is"


def _data(name: str) -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, name)


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _epoch(iso: str) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Detection: where the counter dropped
# ---------------------------------------------------------------------------

def drops(values: list) -> list:
    """``[{"at", "last_seen", "seen_at", "uptime_after"}]`` for every point in a
    ``[[ts, ticks], ...]`` series where the counter fell. *last_seen* is the last sample
    before (the device still up), *seen_at* the first after. *at* is when it came back up:
    the first sample after, less the uptime it then read, KEPT INSIDE that gap, because the
    uptime is the device's own ticks and a slow clock understates it (s3 runs at 0.56:
    2026-10-02, "restarts" read off now-minus-uptime on the switches were the redeploy,
    hours earlier, measured)."""
    out = []
    pts = [(float(t), float(v)) for t, v in values if v is not None]
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if v1 < v0:
            at = min(max(t1 - v1 / 100.0, t0), t1)
            out.append({"at": at, "last_seen": t0, "seen_at": t1, "uptime_after": v1 / 100.0})
    return out


def reason_from(text: str) -> dict:
    """``{"reason", "crash_file"}`` from a device's `show version` lines. IOS-XE says
    ``Last reload reason: Critical software exception, check bootflash:<file>``; vIOS says
    ``Last reload reason: Unknown reason`` or ``System returned to ROM by <why>``."""
    text = text or ""
    m = _REASON.search(text)
    reason = m.group(1) if m else ""
    if not reason:
        r = _RETURNED.search(text)
        reason = r.group(1) if r else ""
    c = _CRASH.search(text) or _CRASH_ANY.search(text)
    crash = c.group(1).rstrip(",.") if c else ""
    if crash and ", check" in reason:
        reason = reason.split(", check")[0]
    return {"reason": reason.strip(), "crash_file": crash}


def read_reason(dev: dict) -> dict:
    """The device's own reason for its last reload, read once. ``{"reason", "crash_file",
    "error"}``; a read that fails says so and guesses nothing."""
    from modules.connection import with_temp_connection
    from modules.readonly_commands import refusal

    why = refusal(REASON_COMMAND)
    if why:                                    # the allowlist is the authority, even here
        return {"reason": "", "crash_file": "", "error": f"not read: {why}"}
    try:
        # The literal, as REASON_COMMAND says it, so the program's command scans see a read.
        text = with_temp_connection(dev, lambda c: c.send_command(
            "show version | include reason|returned to|uptime is", read_timeout=60))
    except Exception as exc:                   # noqa: BLE001
        return {"reason": "", "crash_file": "", "error": f"{type(exc).__name__}: {exc}"}
    out = reason_from(text if isinstance(text, str) else "")
    out["error"] = "" if (out["reason"] or out["crash_file"]) else \
        "the device's `show version` named no reload reason"
    return out


# ---------------------------------------------------------------------------
# Planned restarts: what the tool did, or was told
# ---------------------------------------------------------------------------

def record_planned(devices, start: float, end: float, by: str, why: str, via: str,
                   list_name: str = "", correction: str = "") -> dict:
    """Record that *devices* (``["*"]`` for every device of *list_name*) will restart between
    *start* and *end* (epoch seconds), on purpose. Refuses a record with no person, no reason
    or an end before its start, because a planned window is what keeps an alert quiet.

    **A window declared AFTER a restart it would cover is refused** (the operator,
    2026-10-02: "don't let a planned-restart window declared after the fact clear an
    unplanned restart"), naming each restart, unless it is marked as a *correction* with
    its own reason: a window that was really planned and only recorded late. A correction
    is kept as one, and History says so."""
    from modules.config import open_secure
    from modules.filestore import PathLock

    devices = [d for d in (devices or []) if d]
    if not devices or not by or not (why or "").strip() or end < start:
        return {"ok": False, "error": "a planned restart names its devices, who planned it, "
                                      "why, and a window whose end is after its start"}
    row = {"devices": devices, "list": list_name, "from": _iso(start), "until": _iso(end),
           "by": by, "why": why.strip(), "via": via, "recorded_at": _iso(time.time())}
    seen = events()
    if seen["state"] == "unreadable":
        return {"ok": False, "error": "the restart record could not be read, so whether this "
                                      "window covers a restart already seen cannot be told "
                                      f"({seen.get('error')})"}
    covered = [r for r in seen["rows"] if _window_covers(row, r.get("device", ""),
                                                         _epoch(r.get("at", "")),
                                                         r.get("list", ""))]
    if covered and not (correction or "").strip():
        named = "; ".join(f"{r.get('device')} at {r.get('at')}" for r in covered[:10])
        more = f" and {len(covered) - 10} more" if len(covered) > 10 else ""
        return {"ok": False, "covered": covered, "error": (
            f"this window covers {len(covered)} restart(s) the tool has already seen ({named}"
            f"{more}): a window declared after the fact does not make them planned. If it was "
            "really planned and only recorded late, mark it as a correction with its reason; "
            "otherwise acknowledge each restart on Needs attention")}
    if correction:
        from modules.nsot.authorisation import MIN_CHARS, MIN_WORDS, reason_problem
        if reason_problem({"line": "", "reason": correction.strip()}):
            return {"ok": False, "error": (f"a correction needs its own reason: at least "
                                           f"{MIN_WORDS} words and {MIN_CHARS} characters "
                                           "saying why the window was recorded late")}
        row["correction"] = correction.strip()
    path = _data("planned_restarts.jsonl")
    with PathLock(path):
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    return {"ok": True, "record": row, "covered": covered}


def _read_jsonl(path: str) -> dict:
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


def _window_covers(p: dict, device: str, at: float, list_name: str) -> bool:
    if device not in p.get("devices", []) and not (
            "*" in p.get("devices", []) and (not p.get("list") or p.get("list") == list_name)):
        return False
    return _epoch(p["from"]) - 60 <= at <= _epoch(p["until"]) + PLANNED_SLACK_SECONDS


def planned_for(device: str, at: float, planned: list, list_name: str = "", seen=None):
    """The planned record covering a restart of *device* at *at*, or None. With *seen*
    (when the tool recorded the restart), a window recorded AFTER that counts only when it
    is a correction (`record_planned`): declared after the fact, it never clears one."""
    for p in planned:
        if not _window_covers(p, device, at, list_name):
            continue
        if seen is not None and not p.get("correction") and \
                _epoch(p.get("recorded_at", "")) > seen:
            continue
        return p
    return None


def seen_at(r: dict) -> float:
    """When the tool recorded restart *r*: its `recorded_at`, or, for a row written before
    that field existed, the sample it was found in (the earliest it could have been seen,
    so a window recorded later never passes as earlier)."""
    return _epoch(r.get("recorded_at") or r.get("seen_at") or r.get("at", ""))


# ---------------------------------------------------------------------------
# The record of every restart
# ---------------------------------------------------------------------------

def events(device: str = "", list_name: str = "") -> dict:
    """``{"state", "rows"}``: every restart recorded, newest first, filtered by device and
    list. *state* says absent (none recorded yet) or unreadable, never an empty list for
    either."""
    got = _read_jsonl(_data("restarts.jsonl"))
    rows = [r for r in got["rows"]
            if (not device or r.get("device") == device)
            and (not list_name or r.get("list") == list_name)]
    rows.sort(key=lambda r: _epoch(r.get("at", "")), reverse=True)
    return dict(got, rows=rows)


def judged(rows: list, planned: list) -> list:
    """*rows* with each one's planned verdict taken from the planned windows recorded now. A
    window recorded after the restart was seen counts only as a CORRECTION (its reason kept
    on the row); a restart the tool recorded as planned stays planned."""
    out = []
    for r in rows:
        r = dict(r)
        if not r.get("planned"):
            p = planned_for(r.get("device", ""), _epoch(r.get("at", "")), planned,
                            r.get("list", ""), seen=seen_at(r))
            if p:
                r.update(planned=True, planned_by=p.get("by", ""), planned_why=p.get("why", ""),
                         planned_correction=p.get("correction", ""))
        out.append(r)
    return out


def planned_rows() -> list:
    """The planned windows, or [] when none are recorded; an unreadable record raises, because
    reading it as "nothing planned" would raise a row for every planned restart."""
    got = _read_jsonl(_data("planned_restarts.jsonl"))
    if got["state"] == "unreadable":
        raise RuntimeError(f"the planned-restart record could not be read: {got.get('error')}")
    return got["rows"]


def known(device: str, at: float, rows: list, list_name: str = "") -> bool:
    return any(r.get("device") == device and r.get("list", "") == list_name
               and abs(_epoch(r.get("at", "")) - at) < SAME_RESTART_SECONDS for r in rows)


def append(row: dict) -> None:
    from modules.config import open_secure
    from modules.filestore import PathLock
    path = _data("restarts.jsonl")
    with PathLock(path):
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def words(r: dict) -> str:
    """"r3 restarted unexpectedly at 08:34 UTC — reason: critical software exception (crash
    file saved)"."""
    when = time.strftime("%H:%M UTC on %d %b", time.gmtime(_epoch(r.get("at", ""))))
    if r.get("last_seen"):
        when += time.strftime(" (last answered %H:%M)", time.gmtime(_epoch(r["last_seen"])))
    how = "restarted as planned" if r.get("planned") else "restarted unexpectedly"
    reason = (r.get("reason") or "").strip()
    tail = (f" — reason: {reason[0].lower() + reason[1:]}" if reason else
            f" — reason not read ({r.get('reason_error') or 'no answer'})")
    if r.get("crash_file"):
        tail += " (crash file saved)"
    return f"{r.get('device')} {how} at {when}{tail}"
