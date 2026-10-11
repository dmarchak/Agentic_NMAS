"""The network's syslog as it arrives, for the sidebar's Logs (C675; the operator, 2026-10-11:
"a LIVE TAIL"; board D on the canvas's History, Query page, `LogsTail.dc.html`).

**Why a reader, every 5 s.** The operator asked for lines polled every few seconds, over a fixed
window, with no per-device work per request. A page that asked Loki itself would ask once per
viewer per poll; this asks ONCE per Loki configuration every 5 s (one `query_range` over the
last 15 minutes, every device at once), keeps the window, and announces `logs` only when a
newer line arrived, so every open Logs page redraws from the store (rule 9: no polling).

**What is kept:** the newest ``WINDOW_LIMIT`` lines received in the last ``WINDOW_SECONDS``,
newest first, each ``{at, ts, dev, sev, mn, text}`` (the collector's receive time, never the
device's clock; heartbeats left out, as everywhere), the text masked by `redact_text` on the
way in; ``truncated`` when the read returned exactly its limit (more arrived than are kept,
said on the page); ``read_at``.
"""

import logging
import time

from modules import reader_job

log = logging.getLogger(__name__)

READER_NAME = "logs-tail"
#: The operator's "every few seconds"; a 15-minute read of the lab's Loki takes well under a
#: second (logs-summary measured a whole day's count at 0.45 s, 2026-10-10).
INTERVAL_SECONDS = 5
#: The window on screen; anything older is History › Query's.
WINDOW_SECONDS = 900
#: The most lines kept: the lab writes about 230 in 15 minutes (board D's count, 2026-10-11).
WINDOW_LIMIT = 1000
KEEPALIVE_SECONDS = 300


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def line_of(ns, raw: str) -> dict:
    """One received line's fields, its text masked."""
    from modules import device_logs
    from modules.readers.logs_summary import _fields_of
    from modules.redact import redact_text

    ts = int(ns) / 1e9
    dev, sev = _fields_of(raw)
    p = device_logs.parse(raw, dev) if dev else {"mnemonic": "", "sev": None, "text": raw}
    return {"at": _iso(ts), "ts": ts, "dev": dev, "sev": p.get("sev", sev),
            "mn": p.get("mnemonic", ""), "text": redact_text(p.get("text", raw) or "")}


def read(list_name: str = "", loki=None, clock=time.time) -> dict:
    """One configuration's last ``WINDOW_SECONDS`` of lines, newest first."""
    from modules.readers.logs_summary import _Loki, selector

    loki = loki or _Loki(list_name)
    if not loki.configured():
        return {"configured": False}
    now = clock()
    got = loki.ask("loki/api/v1/query_range", query=selector(), limit=WINDOW_LIMIT,
                   start=str(int((now - WINDOW_SECONDS) * 1e9)), end=str(int(now * 1e9)),
                   direction="backward")
    lines = [line_of(ns, raw) for stream in got for ns, raw in stream.get("values") or []]
    lines.sort(key=lambda l: l["ts"], reverse=True)
    return {"configured": True, "lines": lines[:WINDOW_LIMIT],
            "truncated": len(lines) >= WINDOW_LIMIT, "window_seconds": WINDOW_SECONDS,
            "read_at": _iso(now), "read_at_ts": now}


def changed(previous, value) -> bool:
    """Announce when a newer line arrived or lines left the window, never for the read's time."""
    def key(v):
        lines = (v or {}).get("lines") or []
        return (bool((v or {}).get("configured")), len(lines),
                lines[0]["ts"] if lines else 0, (v or {}).get("truncated"))
    return key(previous) != key(value)


def _default() -> str:
    from modules.list_settings import DEFAULT_LIST
    return DEFAULT_LIST


READER = reader_job.register(reader_job.Reader(
    name=READER_NAME,
    what="the network's syslog as it arrives, the last 15 minutes, for the sidebar's Logs (C675)",
    endpoints=("Loki: GET /loki/api/v1/query_range (the last 15 minutes, every device in one "
               "query, newest first, at most 1000 lines)",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the operator's design, 2026-10-11: recent lines as they arrive, read every "
                    "few seconds over a fixed window"),
    read=read,
    invalidates=("logs",),
    remedy="Read the error above: it names what Loki answered",
    window="the 15 minutes before each read",
    per_group=("loki",),
    read_for=lambda list_name: read(list_name=list_name),
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
