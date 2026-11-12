"""The network's syslog as it arrives, for the sidebar's Logs (C675; the operator, 2026-10-11:
"a LIVE TAIL"; board D on the canvas's History, Query page, `LogsTail.dc.html`).

**Why a reader, every 5 s.** The operator asked for lines polled every few seconds, over a fixed
window, with no per-device work per request. A page that asked Loki itself would ask once per
viewer per poll; this asks ONCE per Loki configuration every 5 s (every device at once), keeps
the window, and announces `logs` only when a newer line arrived, so every open Logs page
redraws from the store (rule 9: no polling).

**What is kept:** the newest ``WINDOW_LIMIT`` lines received in the last ``WINDOW_SECONDS``,
newest first, each ``{at, ts, dev, sev, mn, text}`` (the collector's receive time, never the
device's clock; heartbeats left out, as everywhere), the text masked by `redact_text` on the
way in; ``truncated`` when more arrived in the window than are kept (said on the page);
``read_at``.

**Filled incrementally (C3166, the operator's addition 2, 2026-11-12: "one query for all devices
since the last line's timestamp ... not 13 overlapping 15-minute queries every 5 s").** The
first read asks the window; every later read asks only from `OVERLAP_SECONDS` before the newest
line it holds (a line can reach Loki a little after the time it carries), so a read covers about
a minute, not 15. The same reads fill each device's buffer (modules/logs_buffer.py: its lines
for 24 h, its heartbeats, its configuration changes for 30 days), which the device's Logs tab,
its drift row and History › Query › Syslog by device draw, never asking Loki on a page load. The
heartbeats are one more query a minute; until the buffer reaches back as far as each kind is
kept, a read asks one older page more (`BACKFILL_LIMIT` lines, every device at once). A read
that returns its limit going forward covers only from its oldest line: older than that is a
hole, so the kind starts again from there and fills back. ``buffer`` in the value says what the
buffer covers (``{kind: {"from", "to"}}``, nanoseconds) and how many queries the read asked.
"""

import logging
import re
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
#: How far before the newest line held each later read asks from. Not measured yet (C3203): the
#: collector stamps a line when it receives it and ships in batches (Alloy's loki.write waits 1 s
#: by default), so a line reaches Loki seconds after its time; a minute is the margin.
OVERLAP_SECONDS = 60
#: The heartbeats are asked once a minute: a device sends one every 5 minutes (the heartbeat
#: applet), and the Logs tab draws their count and the last one.
BEATS_EVERY = 60
#: One older page a read while the buffer fills back: every device at once, newest first.
BACKFILL_LIMIT = 1000

_WINDOW_KEYS = ("at", "ts", "dev", "sev", "mn", "text")
_HELD_KEYS = ("ns", "at", "sev", "mn", "text", "devts", "unsync")
_CHANGE = []


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


def entry(ns, raw: str) -> dict:
    """One received line as the buffer keeps it: `line_of`'s fields, its nanoseconds, and the
    device's own time and whether IOS marks that time unsynchronised."""
    from modules import device_logs

    e = line_of(ns, raw)
    p = device_logs.parse(raw, e["dev"]) if e["dev"] else {}
    e.update(ns=int(ns), devts=p.get("devts", ""), unsync=bool(p.get("unsync")))
    return e


def queries(loki) -> dict:
    """Each kind's one query for every device: the lines but heartbeats, the heartbeats, and the
    configuration and restart lines. Raises `device_logs.NoSyslogJob` when no job is known."""
    from modules import device_logs
    from modules.readers.logs_summary import _job, selector

    lines = selector(loki)
    return {"lines": lines,
            "beats": f'{{{_job(loki)}}} |~ `{device_logs.HEARTBEAT_LINE}`',
            "changes": f"{lines} |~ `{device_logs.CHANGE_PATTERN}`"}


def _ask(loki, query: str, start_ns: int, end_ns: int, limit: int) -> tuple:
    """``([(ns, raw)], cut)``: one query_range, newest first; *cut* when it returned its limit."""
    got = loki.ask("loki/api/v1/query_range", query=query, limit=limit, start=str(start_ns),
                   end=str(end_ns), direction="backward")
    raw = [(int(ns), line) for stream in got for ns, line in stream.get("values") or []]
    return raw, len(raw) >= limit


def _previous(list_name: str) -> dict:
    try:
        got = reader_job.read_cached_for(READER_NAME, list_name or _default())
    except Exception as exc:                            # noqa: BLE001 (a first read, said)
        log.warning("logs-tail: the previous value could not be read (%s): reading the window",
                    exc)
        return {}
    return ((got.get("doc") or {}).get("last_good") or {}).get("value") or {}


def _store(list_name: str) -> str:
    try:
        store, _refused = reader_job.store_for(READER_NAME, list_name or _default())
    except Exception:                                   # noqa: BLE001 (Default's store)
        store = None
    return store or READER_NAME


def _forward(loki, query, cover, now_ns, first_ns, floor_ns, limit) -> tuple:
    """``(raw, cover, cut)``: the lines since the newest held (from *first_ns* when none is
    held), and what the kind covers after them."""
    # Never further back than the first read's own window (C3330's hotfix, 2026-11-12): `cover`
    # moves only on a success, so after one failed read the range grew on every later read
    # toward the 24 h floor, each timed out against Loki, and the reader never recovered (no
    # read from 14:36:21 UTC on the NMAS host). A gap older than the window is the backfill's.
    start = first_ns if not cover else max(floor_ns, first_ns,
                                           cover["to"] - int(OVERLAP_SECONDS * 1e9))
    raw, cut = _ask(loki, query, start, now_ns, limit)
    got_from = min(ns for ns, _l in raw) if cut and raw else start
    if not cover or got_from > cover["to"]:
        # The first read, or more arrived than one read returns: whole only from its oldest.
        return raw, {"from": got_from, "to": now_ns}, cut
    return raw, {"from": cover["from"], "to": now_ns}, cut


def read(list_name: str = "", loki=None, clock=time.time, previous=None) -> dict:
    """One configuration's last ``WINDOW_SECONDS`` of lines, newest first, and each device's
    buffer filled with what arrived since the previous read (see the module)."""
    from modules import device_logs
    from modules import logs_buffer as B
    from modules.readers.logs_summary import _Loki

    loki = loki or _Loki(list_name)
    if not loki.configured():
        return {"configured": False}
    now = clock()
    now_ns = int(now * 1e9)
    if previous is None:
        previous = _previous(list_name)
    store = _store(list_name)
    pbuf = (previous.get("buffer") or {}) if previous.get("configured") else {}
    if pbuf.get("store") != store:
        pbuf = {}                                     # none yet, or another configuration's
    covers = {k: dict(pbuf[k]) for k in B.KINDS
              if isinstance(pbuf.get(k), dict) and pbuf[k].get("to")}
    floors = {k: int((now - B.HORIZON[k]) * 1e9) for k in B.KINDS}
    q = queries(loki)
    new = {k: [] for k in B.KINDS}

    first = int((now - WINDOW_SECONDS) * 1e9)
    raw, cover, cut = _forward(loki, q["lines"], covers.get("lines"), now_ns, first,
                               floors["lines"], WINDOW_LIMIT)
    asked = 1
    reset = cover["from"] != (covers.get("lines") or {}).get("from")
    covers["lines"] = cover
    new["lines"] = list(raw)
    # The configuration lines going forward are among the lines: the same read, filtered.
    if not _CHANGE:
        _CHANGE.append(re.compile(device_logs.CHANGE_PATTERN))
    new["changes"] = [(ns, l) for ns, l in raw if _CHANGE[0].search(l)]
    held = covers.get("changes")
    covers["changes"] = {"from": cover["from"] if reset or not held else held["from"],
                         "to": now_ns}
    if pbuf:
        # Once the window has been read once: the heartbeats a minute, then one older page.
        b = covers.get("beats")
        if not b or now_ns - b["to"] >= BEATS_EVERY * 1e9:
            new["beats"], covers["beats"], _cut = _forward(loki, q["beats"], b, now_ns, first,
                                                           floors["beats"], BACKFILL_LIMIT)
            asked += 1
        for kind in B.KINDS:
            c = covers.get(kind)
            if not c or c["from"] <= floors[kind]:
                continue
            older, cut_o = _ask(loki, q[kind], floors[kind], c["from"] + 1, BACKFILL_LIMIT)
            asked += 1
            oldest = min((ns for ns, _l in older), default=None)
            c["from"] = (min(oldest, c["from"] - 1) if cut_o and oldest is not None
                         else floors[kind])
            new[kind] += older
            break
    for kind, c in covers.items():
        c["from"] = max(c["from"], floors[kind])

    forward = {ns for ns, _l in raw}
    by_dev, window = {}, {}
    for kind in B.KINDS:
        for ns, line in new[kind]:
            e = entry(ns, line)
            if kind == "lines" and (ns in forward or e["ts"] >= now - WINDOW_SECONDS):
                window[(e["ns"], e["dev"], e["mn"], e["text"])] = {k: e[k] for k in _WINDOW_KEYS}
            if not e["dev"]:
                continue
            kept = by_dev.setdefault(e["dev"], {}).setdefault(kind, [])
            kept.append(e["ns"] if kind == "beats" else {k: e[k] for k in _HELD_KEYS})
    for line in (previous.get("lines") or []) if pbuf else []:
        if line.get("ts", 0) >= now - WINDOW_SECONDS:
            window.setdefault((int(round(line["ts"] * 1e9)), line.get("dev"), line.get("mn"),
                               line.get("text")), line)
    written = B.write(store, by_dev, now)
    lines = sorted(window.values(), key=lambda l: l["ts"], reverse=True)
    newest_beat = max([ns for d in by_dev.values() for ns in d.get("beats") or []]
                      + [pbuf.get("beats_newest") or 0])
    return {"configured": True, "lines": lines[:WINDOW_LIMIT],
            "truncated": len(lines) > WINDOW_LIMIT or (cut and cover["from"] > first),
            "window_seconds": WINDOW_SECONDS, "read_at": _iso(now), "read_at_ts": now,
            "buffer": dict(covers, store=store, asked=asked, written=written,
                           beats_newest=newest_beat)}


def changed(previous, value) -> bool:
    """Announce when a newer line arrived or lines left the window, a heartbeat arrived, or the
    buffer reached further back while it fills; never for the read's time."""
    from modules.logs_buffer import HORIZON, KINDS

    def key(v):
        v = v or {}
        lines = v.get("lines") or []
        buf = v.get("buffer") or {}
        now_ns = int((v.get("read_at_ts") or 0) * 1e9)
        filling = tuple((k, (buf.get(k) or {}).get("from")) for k in KINDS
                        if ((buf.get(k) or {}).get("from") or 0) > now_ns - HORIZON[k] * 10 ** 9)
        return (bool(v.get("configured")), len(lines), lines[0]["ts"] if lines else 0,
                v.get("truncated"), buf.get("beats_newest"), filling)
    return key(previous) != key(value)


def _default() -> str:
    from modules.list_settings import DEFAULT_LIST
    return DEFAULT_LIST


READER = reader_job.register(reader_job.Reader(
    name=READER_NAME,
    what=("the network's syslog as it arrives, the last 15 minutes, for the sidebar's Logs "
          "(C675), and each device's buffer for its Logs tab, drift row and Syslog by device "
          "(C3166)"),
    endpoints=("Loki: GET /loki/api/v1/query_range (every device in one query, newest first: "
               "the lines since the newest held, a minute's overlap, at most 1000; the "
               "heartbeats the same, once a minute; while the buffer fills back, one older "
               "page of at most 1000)",),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("the operator's design, 2026-10-11: recent lines as they arrive, read every "
                    "few seconds over a fixed window"),
    read=read,
    invalidates=("logs",),
    remedy="Read the error above: it names what Loki answered",
    window="the 15 minutes before each read; each device's buffer its last 24 h, and its "
           "configuration changes 30 days",
    per_group=("loki",),
    read_for=lambda list_name: read(list_name=list_name),
    announce_if=changed,
    announce_at_least_every=KEEPALIVE_SECONDS,
))
