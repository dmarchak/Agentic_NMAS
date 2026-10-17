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

**A planned window quiets what it covers, and only while it lasts** (the operator's B3, W2
walk, 2026-10-17: r6's reload raised "r6 is not answering" CRITICAL and four Grafana alerts
inside its own declared window). Declaring one sets a Grafana silence on its devices' alerts
(`put_silence`: the `device` label and the polled `instance` address), as the person who
declared it and with their reason, until the window's end plus `SETTLE_SECONDS`; its id is
kept on the window, and a silence that could not be set is said on the result, never
dropped. While it lasts, Needs attention says the device is restarting as planned instead of
raising a row (`holding`); once it ends with the device still down, the row is raised, naming
the window. A reload that is back ends its window early (`end_window`), which moves the
silence's end to then plus the settle margin.

Stores, all in the data folder, append-only, 0600 (a person's name and reason are in them):
`restarts.jsonl` (every restart seen, planned or not), `planned_restarts.jsonl`, and
`planned_restart_ends.jsonl` (a window ended early, and by what).
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
#: How long after a planned window ends its devices' Grafana alerts stay silenced and held:
#: the alerts outlast the device's return. MEASURED on r6's reload (W2, 2026-10-17): verified
#: at about 00:14:26Z, its telemetry no_data alerts (101, 102) still firing at 00:16Z
#: (screenshot 69) and nothing firing at 00:22Z (75), so they cleared within 454 s of the
#: return, an upper bound. 2.5 times it, rounded up to the minute. Tightened once a reload's
#: Grafana alert history gives the clear time itself.
SETTLE_SECONDS = 1140

#: How a window's silence names its person in Mercury's Grafana write record (C1089): the
#: window keeps who declared it, not how they were established, so the record says whose
#: window it is rather than guess a verification.
WINDOW_PERSON = "the planned-restart window's declarer"

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
                   list_name: str = "", correction: str = "",
                   new_host_keys: bool = False) -> dict:
    """Record that *devices* (``["*"]`` for every device of *list_name*) will restart between
    *start* and *end* (epoch seconds), on purpose. Refuses a record with no person, no reason
    or an end before its start, because a planned window is what keeps an alert quiet.

    *new_host_keys* says the devices come back with NEW SSH host keys (a rebuild from fresh
    disks, as a lab redeploy is: each device generates its key as it boots).
    Mercury then keeps one new key per device met inside the window instead of refusing it
    (`modules/host_keys.py`, C906); a window says it before the change, or it accepts
    nothing.

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
    if new_host_keys:
        row["new_host_keys"] = True
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
    # The silence, before the row is written, so the row carries its id (B3). A window that
    # has already ended (a correction for the past) silences nothing.
    silence = silence_window(row)
    row["silence"] = silence
    path = _data("planned_restarts.jsonl")
    try:
        with PathLock(path):
            with open_secure(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception:
        # The window was not recorded, so its silence must not outlive it unrecorded.
        _move_silences(row, time.time(), "the window could not be recorded")
        raise
    return {"ok": True, "record": row, "covered": covered, "silence": silence,
            "silence_words": silence_words(silence)}


# ---------------------------------------------------------------------------
# A window's Grafana silence, and what it holds on Needs attention (B3)
# ---------------------------------------------------------------------------

def _grafana(list_name: str):
    """The Grafana client FOR *list_name* (its own, or the one it inherits): the one place a
    window reaches Grafana, so a test replaces it here."""
    from modules.integrations.grafana import GrafanaIntegration

    return GrafanaIntegration(list_name=list_name) if list_name else GrafanaIntegration()


def _inventory_of(list_name: str) -> list:
    """*list_name*'s devices, read without creating its folder."""
    from modules.config import list_data_path
    from modules.device import load_saved_devices

    return load_saved_devices(os.path.join(list_data_path(list_name), "devices.csv"))


def _targets(p: dict) -> tuple:
    """``(names, addresses)`` the window's silence matches: its devices (every device of its
    network for ``"*"``) and each one's management address, the `instance` an SNMP rule
    carries."""
    devices = list(p.get("devices") or [])
    inventory = _inventory_of(p.get("list", "")) if p.get("list") else []
    if "*" in devices:
        names = sorted(d["hostname"] for d in inventory if d.get("hostname"))
    else:
        names = sorted(set(devices))
    ips = sorted({d["ip"] for d in inventory if d.get("hostname") in names and d.get("ip")})
    return names, ips


def _matchers(names: list, ips: list) -> list:
    """One matcher set per silence: Alertmanager ANDs the matchers in one silence, so the
    `device` label and the `instance` address are two silences, each a regular expression
    over every name (Grafana anchors it)."""
    out = []
    if names:
        out.append([{"name": "device", "isRegex": True,
                     "value": "|".join(re.escape(n) for n in names)}])
    if ips:
        out.append([{"name": "instance", "isRegex": True,
                     "value": "(" + "|".join(re.escape(i) for i in ips) + ")(:[0-9]+)?"}])
    return out


def silence_window(p: dict, now: float = None) -> dict:
    """Set the window's Grafana silences: ``{"state": "set"|"failed"|"not_configured"|
    "not_needed", "silences": [{"id", "matcher", "starts_at", "ends_at"}], "ends_at",
    "error"}``. Never raises: a window is recorded whether or not Grafana took the silence,
    and the result says which."""
    now = time.time() if now is None else now
    start, end = _epoch(p["from"]), _epoch(p["until"]) + SETTLE_SECONDS
    if end <= now:
        return {"state": "not_needed", "silences": [], "ends_at": _iso(end),
                "error": "the window and its settle margin have already passed"}
    try:
        client = _grafana(p.get("list", ""))
        if not client.is_configured():
            return {"state": "not_configured", "silences": [], "ends_at": "",
                    "error": "Grafana is not configured for this network"}
        names, ips = _targets(p)
    except Exception as exc:                     # noqa: BLE001 - said on the window
        return {"state": "failed", "silences": [], "ends_at": "",
                "error": f"{type(exc).__name__}: {exc}"}
    sets = _matchers(names, ips)
    if not sets:
        return {"state": "failed", "silences": [], "ends_at": "",
                "error": f"no device of {p.get('list') or 'the network'} to name"}
    starts_at = _iso(min(start, now))
    comment = (f"Mercury planned-restart window ({p.get('via', '')}): {p.get('why', '')}"
               f" (until {p['until']}, plus {SETTLE_SECONDS // 60} min to settle)")
    done, errors = [], []
    for matchers in sets:
        got = client.put_silence(matchers=matchers, starts_at=starts_at, ends_at=_iso(end),
                                 created_by=p.get("by", ""), comment=comment,
                                 via=f"planned-restart window ({p.get('via') or 'declared'})",
                                 verified=WINDOW_PERSON)
        words = f"{matchers[0]['name']}=~{matchers[0]['value']}"
        if got.get("ok"):
            done.append({"id": got["id"], "matcher": words, "starts_at": starts_at,
                         "ends_at": _iso(end)})
        else:
            errors.append(f"{words}: {got.get('error')}")
    if errors:
        log.warning("restarts: a planned window's Grafana silence was not set: %s",
                    "; ".join(errors))
    return {"state": "failed" if errors else "set", "silences": done, "ends_at": _iso(end),
            "error": "; ".join(errors)}


def silence_words(s: dict) -> str:
    """The window's result, said: what Grafana's alerts are doing."""
    s = s or {}
    state = s.get("state")
    if state == "set":
        return (f"Grafana's alerts on its devices are silenced until {s.get('ends_at')} "
                f"(silence {', '.join(x['id'] for x in s.get('silences') or [])})")
    if state == "not_configured":
        return "Grafana is not configured for this network, so no alert of its was silenced"
    if state == "not_needed":
        return "no Grafana silence: the window and its settle margin have already passed"
    set_ = [x["id"] for x in s.get("silences") or []]
    return ("Grafana's alerts are NOT silenced: " + (s.get("error") or "no reason recorded")
            + (f" (silence {', '.join(set_)} was set for the rest)" if set_ else ""))


def window_id(p: dict) -> str:
    """A window's identity: what it declared and when, never its silence."""
    import hashlib

    key = {k: p.get(k) for k in ("devices", "list", "from", "until", "by", "why",
                                 "recorded_at")}
    return hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:16]


def _move_silences(p: dict, ends: float, why: str) -> list:
    """Move the end of every silence the window set to *ends*: ``[{"id", "ends_at", "ok",
    "error"}]``. The same start and matchers keep it the same silence in Grafana."""
    out = []
    silences = ((p.get("silence") or {}).get("silences")) or []
    if not silences:
        return out
    try:
        client = _grafana(p.get("list", ""))
    except Exception as exc:                     # noqa: BLE001
        return [{"id": s.get("id"), "ok": False, "error": f"{type(exc).__name__}: {exc}"}
                for s in silences]
    for s in silences:
        name, _sep, value = (s.get("matcher") or "").partition("=~")
        ends_at = _iso(max(ends, _epoch(s.get("starts_at", "")) + 1))
        got = client.put_silence(matchers=[{"name": name, "value": value, "isRegex": True}],
                                 starts_at=s.get("starts_at", ""), ends_at=ends_at,
                                 created_by=p.get("by", ""), silence_id=s.get("id", ""),
                                 via="planned-restart window ended", verified=WINDOW_PERSON,
                                 comment=f"Mercury planned-restart window: {p.get('why', '')}"
                                         f" ({why})")
        out.append({"id": got.get("id") or s.get("id"), "was": s.get("id"),
                    "ends_at": ends_at, "ok": bool(got.get("ok")), "error": got.get("error", "")})
    return out


def end_window(p: dict, at: float, why: str, by: str = "") -> dict:
    """End window *p* early, at *at* (a reload that is back): recorded in
    `planned_restart_ends.jsonl`, and its silences moved to end `SETTLE_SECONDS` later, since
    the alerts outlast the return. ``{"ok", "ended_at", "silences", "words", "error"}``."""
    from modules.config import open_secure
    from modules.filestore import PathLock

    moved = _move_silences(p, at + SETTLE_SECONDS, why)
    row = {"window": window_id(p), "ended_at": _iso(at), "why": why, "by": by,
           "silences": moved, "recorded_at": _iso(time.time())}
    path = _data("planned_restart_ends.jsonl")
    try:
        with PathLock(path):
            with open_secure(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    except Exception as exc:                     # noqa: BLE001 - said on the result
        log.error("restarts: the window's end was NOT recorded: %s", exc)
        return {"ok": False, "ended_at": row["ended_at"], "silences": moved,
                "error": f"the end was not recorded: {exc}",
                "words": f"the window's end was NOT recorded ({exc})"}
    bad = [m for m in moved if not m["ok"]]
    words = (f"window ended {row['ended_at']} ({why})"
             + (f"; Grafana's silence now ends {moved[0]['ends_at']}" if moved and not bad else "")
             + (f"; Grafana's silence was NOT moved: "
                + "; ".join(f"{m['was']}: {m['error']}" for m in bad) if bad else ""))
    return {"ok": True, "ended_at": row["ended_at"], "silences": moved, "words": words,
            "error": ""}


def ends() -> dict:
    """``{window id: ended_at epoch}``: every window ended early. An unreadable record ends
    none, so a window is held to its declared end, never cut short by a guess."""
    got = _read_jsonl(_data("planned_restart_ends.jsonl"))
    out = {}
    for r in got["rows"]:
        at = _epoch(r.get("ended_at", ""))
        if r.get("window") and at:
            out[r["window"]] = min(at, out.get(r["window"], at))
    return out


def window_end(p: dict, ended: dict) -> float:
    """When window *p* ends: its declared end, or earlier when it was ended early."""
    until = _epoch(p.get("until", ""))
    early = (ended or {}).get(window_id(p))
    return min(until, early) if early else until


def _names(p: dict, device: str, list_name: str) -> bool:
    """Whether window *p* names *device* of *list_name* (by name, or ``"*"`` for its list)."""
    return device in p.get("devices", []) or (
        "*" in p.get("devices", []) and (not p.get("list") or p.get("list") == list_name))


def holding(device: str, list_name: str, now: float, *, margin: float = 0,
            planned: list = None, ended: dict = None):
    """The planned window *device* of *list_name* is inside at *now* (its start to its end,
    plus *margin*), newest first, or None. ``{"window", "end", "words"}``: the end is the
    window's own (declared, or ended early)."""
    planned = planned_rows() if planned is None else planned
    ended = ends() if ended is None else ended
    for p in reversed(planned):
        if not _names(p, device, list_name):
            continue
        end = window_end(p, ended)
        if _epoch(p.get("from", "")) - 60 <= now <= end + margin:
            return {"window": p, "end": end,
                    "words": f"{device} is restarting as planned (until {_iso(end)}, by "
                             f"{p.get('by') or 'an unrecorded person'})"}
    return None


def ended_while_down(device: str, list_name: str, now: float, since: float, *,
                     planned: list = None, ended: dict = None):
    """The newest window for *device* that ENDED while it was down (after *since*, before
    *now*), or None: the one a not-answering row names."""
    planned = planned_rows() if planned is None else planned
    ended = ends() if ended is None else ended
    for p in reversed(planned):
        if _names(p, device, list_name) and since <= window_end(p, ended) < now:
            return p
    return None


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
    if not _names(p, device, list_name):
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
