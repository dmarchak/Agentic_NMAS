"""recheck.py — Needs attention's **Run the check again** (the operator's overnight item 9,
2026-11-12: "A fix made through Mercury re-runs the check that raised its row; the row offers
'Run the check again'").

A row a reader raised stands on that reader's stored value, and a reader may read hourly
(NetBox's stored credentials, the credential health) or every 30 minutes (the scheduled
workflows): a fix made outside Mercury's operations (GitHub re-ran the workflow, NetBox came
back) leaves the row up until the reader's next run. A fix made through Mercury already wakes
the reader (modules/reader_wakes.py); this is the person's own way to ask the same.

**Where it sits.** On the row's evidence, one level down: the Details line that says when
the reading the row stands on was taken ("read 5 min ago · netbox_secrets"), never beside the
row's one action on its line (a Needs attention row names one action). It is offered only on
a row whose reading is a reader's (`attention.assemble` carries the row's `reader`).

**The run is the reader's own** (`reader_job.request_run`, recorded `request` with the person,
announced whatever it found, rule 13), never a second read path: it reads live, keeps its own
bounds, and stores where every consumer reads. The press returns at once (202); the row is
redrawn when the run's value has been assembled (the store's own announcement), with the new
reading's age, cleared if the fresh read no longer finds it.

**Refused, naming both operands** (409, drawn in place):
- the reader is already running in this process (`reader_job.in_progress`, a scheduled run,
  one on request or one after an operation): a second would read the same moment again;
- it began a read less than its minimum spacing ago (`spacing_s`): that reading is as fresh as
  a new one;
- its last read found its dependency not answering and its backoff's next try is still ahead
  (reader_job rule 14): a press does not jump the backoff;
- the readers do not run in this process, or no reader has that name.

**Busy on itself until the answer is drawn** (`mark`, for each request, from memory only): a
run not yet done, or done and stored whose value the held list has not assembled yet (the
row's reading older than the press), is drawn busy; a run that failed is drawn idle with
"The check failed" and its error; a press's state older than `SETTLE_S` past its end is not
drawn at all. The list is told to redraw when the run ends (`announce`, the key `attention`),
so a run whose answer moved nothing the store compares is still drawn.
"""

import logging
import time

log = logging.getLogger(__name__)

#: The shortest time between two reads of one reader a press may ask: rule 14's first retry
#: (`reader_job.BACKOFF_FIRST_SECONDS`, 15 s), the shortest wait Mercury itself leaves before
#: asking a source again; a reader whose own interval is shorter (reachability's and the logs
#: tail's 5 s) is spaced by its interval, since its schedule reads sooner than a press would.
def spacing_s(reader) -> int:
    from modules import reader_job
    return int(min(reader_job.BACKOFF_FIRST_SECONDS, reader.interval_seconds))


#: How long after a run ends its press may still be drawn busy, waiting for the held list to
#: take its value: about 2.5x the store's 2 s debounce plus its measured warm recompute of
#: about 1 s (C3166, 2026-11-12), 7.5 s. Past it the control is drawn as it is.
SETTLE_S = 7.5

#: Who the list's redraw at a run's end is announced by (`invalidation.ANNOUNCERS`).
ANNOUNCER = "recheck"
ANNOUNCE_KEYS = ("attention",)

#: reader name -> what its last press's run ended with, in this process: ``{"run", "ok",
#: "error", "at"}`` (`_done`). Memory only.
_ENDED: dict = {}


def _base(name: str) -> str:
    """A configuration's store (`grafana-alerts@<id>`) is its reader's run."""
    return str(name or "").split("@", 1)[0]


def _reader(name: str):
    from modules import reader_job
    return next((r for r in reader_job.readers() if r.name == name), None)


def _iso(epoch) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _done(entry: dict) -> None:
    """The run's end (`request_run`'s *on_done*): what it stored, from its own store, then the
    list told to redraw."""
    from modules import invalidation, reader_job

    name = entry.get("reader") or ""
    ok, error = False, ""
    if entry.get("raised"):
        error = "its result could not be stored (the app log names why)"
    else:
        doc = reader_job.read_cached(name).get("doc") or {}
        attempt = doc.get("last_attempt") or {}
        if (attempt.get("trigger") or {}).get("run") == entry.get("run"):
            ok, error = bool(attempt.get("ok")), str(attempt.get("error") or "")
        else:
            error = "its stored answer is not this run's"
    _ENDED[name] = {"run": entry.get("run"), "ok": ok, "error": error, "at": time.time()}
    try:
        invalidation.announce(list(ANNOUNCE_KEYS), by=ANNOUNCER)
    except Exception as exc:                          # noqa: BLE001 (no socket: nobody to tell)
        log.warning("recheck: the list was not told %s's run ended: %s", name, exc)


def ask(name: str, by: str, now: float = None) -> dict:
    """Run *name*'s reader again now for *by*, or say why not. ``{"ok", "started", "reader",
    "run", "since", "bound_seconds", "bound_basis"}``, or ``{"ok": False, "refused", "reason",
    "operands"}`` naming the comparison it made."""
    from modules import reader_job

    now = time.time() if now is None else now
    name = _base(name)
    reader = _reader(name) if name else None
    if reader is None:
        return {"ok": False, "refused": "unknown", "reader": name,
                "reason": f"no check named {name or '(none given)'} is registered",
                "operands": {"asked": name, "registered": len(reader_job.readers())}}
    if not reader_job.running(name):
        return {"ok": False, "refused": "not_here", "reader": name,
                "reason": (f"the checks do not run in this process, so nothing was asked; "
                           f"{name} runs every {reader.interval_seconds} s where they run"),
                "operands": {}}
    running = reader_job.in_progress(name) or reader_job.request_in_flight(name)
    if running:
        return {"ok": False, "refused": "running", "reader": name,
                "reason": f"{name} is already running", "operands": {
                    "since": _iso(running["since"]),
                    "cause": reader_job.trigger_words(
                        {"kind": running.get("kind") or "request", "by": running.get("by")},
                        by)}}
    doc = reader_job.read_cached(name).get("doc") or {}
    attempt = doc.get("last_attempt") or {}
    last = reader_job._parse_iso(attempt.get("at"))
    retry = (doc.get("retry") or {}).get("in_seconds")
    if last is not None and isinstance(retry, (int, float)) and now < last + retry:
        return {"ok": False, "refused": "backoff", "reader": name,
                "reason": (f"{name}'s last read found nothing answering, and its next try is "
                           "on its backoff (reader_job rule 14), which a press does not jump"),
                "operands": {"last": _iso(last), "next": _iso(last + retry),
                             "retry_seconds": int(retry)}}
    gap = spacing_s(reader)
    if last is not None and now - last < gap:
        return {"ok": False, "refused": "spacing", "reader": name,
                "reason": (f"{name} began a read {int(now - last)} s ago, within its minimum "
                           f"spacing of {gap} s"),
                "operands": {"last": _iso(last), "next": _iso(last + gap), "spacing": gap,
                             "ago": int(now - last)}}
    bound = reader_job.answer_bound(name)
    # The last press's end forgotten BEFORE the run starts: a fast run ends on its own thread
    # before `request_run` returns, and its end must not be the one forgotten.
    _ENDED.pop(name, None)
    got = reader_job.request_run(reader, by, announce=reader_job.announce_via_page,
                                 on_done=lambda e: _done(dict(e, reader=name)))
    if not got.get("started"):
        # Started by another press between the two checks: the same refusal.
        return {"ok": False, "refused": "running", "reader": name,
                "reason": f"{name} is already running",
                "operands": {"since": _iso(got["since"]), "cause": reader_job.trigger_words(
                    {"kind": "request", "by": got.get("by")}, by)}}
    log.info("recheck: %s run again by %s (run %s)", name, by or "nobody identified",
             got["run"])
    return {"ok": True, "started": True, "reader": name, "run": got["run"],
            "since": _iso(got["since"]), "bound_seconds": bound["seconds"],
            "bound_basis": bound["basis"]}


def state(name: str, read_at: str = None, now: float = None) -> dict:
    """What a row whose reading is *name*'s draws for its control, from memory only: ``None``
    (idle, nothing to say), or ``{"busy": True, "since"}`` or ``{"failed": words, "at"}``.
    *read_at* is the reading the held row stands on."""
    from modules import reader_job

    now = time.time() if now is None else now
    name = _base(name)
    entry = reader_job.last_request(name)
    if entry is None:
        return None
    if not entry.get("done"):
        return {"busy": True, "since": _iso(entry["since"])}
    ended = _ENDED.get(name) or {}
    if ended.get("run") != entry.get("run"):
        # Not a press of this control (an operation's wake, a host job): nothing to draw.
        return None
    if now - (ended.get("at") or 0) > SETTLE_S:
        return None
    if not ended.get("ok"):
        return {"failed": ended.get("error") or "the read failed", "at": _iso(ended["at"])}
    shown = reader_job._parse_iso(read_at) if read_at else None
    if shown is not None and shown < int(entry["since"]):
        # Stored, not yet in the held list: still the answer this press waits for.
        return {"busy": True, "since": _iso(entry["since"])}
    return None


def mark(rows: list, now: float = None) -> None:
    """Each row (and each folded under one) with a reader gets its control's `recheck` state
    for this request, from memory only (`state`); idle rows get none."""
    for r in rows or []:
        for x in [r] + list(r.get("folded") or []):
            if x.get("reader"):
                got = state(x["reader"], x.get("read_at"), now)
                if got:
                    x["recheck"] = got
