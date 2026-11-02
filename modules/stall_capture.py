"""modules/stall_capture.py — a page that shows its stale note records the stall itself (C2003;
the operator, 2026-11-02: "make the stall capture itself ... no live catching by me").

C2003: SDN › Responses stopped live-updating twice on the operator's Lab 8 walk and looked
current. The stale note (static/js/nmas_v2.js, `staleNote`) now says so; its CAUSE was never
measured, because a stall had to be caught live: its time, the tab, and the page's live
connection against the app's own view of it. So the page captures it: the moment a stale note
is shown, the page posts what it knows (when, which tab and page, the note's words and promise,
the live connection's state, its session id, transport, reconnect attempts, last error, the
last announcement and heartbeat it heard, and its recent live events), and the app adds its own
view of that connection (whether this process knows the session, the process, when it last sent
a heartbeat and an announcement and which keys). One row per shown note, kept here; History's
"Page stalls" kind reads it, for the UNKNOWN row that names it as its measurement.

What a page sends is DATA about itself, never instructions: only the declared fields are kept,
each a string, number or boolean of bounded length, so a page cannot fill the store; a field
not declared is dropped and counted. Installation-wide, one file in the data folder, as the
Grafana write record is; a row names the network the page was on.
"""

import calendar
import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

LOG = "page_stalls.jsonl"
_lock = threading.Lock()

#: The page's fields kept, each bounded. Anything else a page sends is dropped (counted).
PAGE_FIELDS = ("page", "tab", "shown_at", "drawn_at", "stale_at", "promise_s", "words",
               "region", "held")
LIVE_FIELDS = ("state", "since", "sid", "transport", "connected_at", "reconnect_attempts",
               "last_error", "last_error_at", "last_announce_at", "last_announce_keys",
               "last_heartbeat_at", "beat_seconds")
#: The page's recent live events kept (`NMAS.log()`: a socket state, an announcement's keys and
#: the panels it re-read), newest last, each one line.
EVENTS_KEPT = 20
MAX_TEXT = 300
#: A stall is a moment: a page that keeps posting (a tick bug) is held to this many rows a
#: minute from one tab, the rest refused by count.
PER_TAB_PER_MINUTE = 6


def _path() -> str:
    from modules import config
    return os.path.join(config.DATA_DIR, LOG)


def _scalar(value):
    """A kept value: a bounded string, a number or a boolean; anything else is its words."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return value
    return str(value)[:MAX_TEXT]


def _kept(sent: dict, fields) -> tuple:
    sent = sent if isinstance(sent, dict) else {}
    kept = {k: _scalar(sent[k]) for k in fields if k in sent}
    return kept, sorted(k for k in sent if k not in fields)


def server_view(sid: str, socketio=None) -> dict:
    """The app's own view of the page's live connection: whether this process knows its
    session (`unknown` when the socket server cannot be asked), this process's id, and when
    it last sent a heartbeat and an announcement (`invalidation.last_emits`)."""
    from modules import invalidation

    view = {"pid": os.getpid(), **invalidation.last_emits()}
    if not sid:
        view["session"] = "the page sent no session id"
    elif socketio is None:
        view["session"] = "unknown: no socket server in this process"
    else:
        try:
            known = socketio.server.manager.is_connected(sid, "/")
            view["session"] = ("connected to this process" if known else
                               "not connected to this process")
        except Exception as exc:                      # noqa: BLE001 (said on the row)
            view["session"] = f"unknown: {type(exc).__name__}: {exc}"[:MAX_TEXT]
    return view


def _recent_rows(tab: str, now: float) -> int:
    got = entries()
    return sum(1 for r in got["rows"][-200:]
               if r.get("page", {}).get("tab") == tab
               and now - _epoch(r.get("at", "")) < 60)


def _epoch(iso: str) -> float:
    try:
        return calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return 0.0


def record(sent: dict, *, actor: str, network: str, server: dict) -> dict:
    """Keep one stall: ``{"ok", "error", "entry"}``. Refused, saying why: a body that is not a
    stall (no page or no live state), or a tab past `PER_TAB_PER_MINUTE`. Never raises."""
    sent = sent if isinstance(sent, dict) else {}
    page, dropped = _kept(sent.get("page"), PAGE_FIELDS)
    live, dropped_live = _kept(sent.get("live"), LIVE_FIELDS)
    if not page.get("page") or not live.get("state"):
        return {"ok": False, "error": "a stall names its page and its live connection's state",
                "entry": None}
    now = time.time()
    if page.get("tab") and _recent_rows(page["tab"], now) >= PER_TAB_PER_MINUTE:
        return {"ok": False, "error": (f"this tab recorded {PER_TAB_PER_MINUTE} stalls in the "
                                       "last minute; the rest are not kept"), "entry": None}
    events = [(e if isinstance(e, str) else json.dumps(e, sort_keys=True))[:MAX_TEXT]
              for e in (sent.get("events") or []) if isinstance(e, (str, dict))][-EVENTS_KEPT:]
    entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), "by": actor,
             "network": network, "page": page, "live": live, "events": events,
             "server": {k: _scalar(v) if not isinstance(v, list) else [_scalar(x) for x in v]
                        for k, v in (server or {}).items()},
             "dropped": dropped + [f"live.{k}" for k in dropped_live]}
    try:
        with _lock, open(_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError as exc:
        log.error("stall_capture: COULD NOT RECORD a stall of %s (%s)", page.get("page"), exc)
        return {"ok": False, "error": f"{LOG} could not be written: {exc}", "entry": entry}
    log.warning("stall_capture: %s showed its stale note (live %s, server: %s)",
                page.get("page"), live.get("state"), entry["server"].get("session"))
    return {"ok": True, "error": "", "entry": entry}


def entries() -> dict:
    """Every stall, oldest first: ``{"rows", "error"}``; absent is no rows, unreadable says
    why (two different states)."""
    path = _path()
    if not os.path.exists(path):
        return {"rows": [], "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            return {"rows": [json.loads(line) for line in fh if line.strip()], "error": ""}
    except (OSError, ValueError) as exc:
        return {"rows": [], "error": f"{LOG} could not be read: {exc}"}
