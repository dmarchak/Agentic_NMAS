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

**A read the person did not start answers the press** (C3361, the operator's test of item 2,
2026-11-12: "When a read began or finished within the spacing, a first press should say
"Checked just now (HH:MM): <result>" and update the row's age, not read as a refusal. "Not
run again…" is only for a person's own repeat press"):
- a read in progress that the person did not start (the schedule's, another person's, an
  operation's wake) is joined: the answer is that it is reading now, the control is busy on
  itself until that run ends (`reader_job.when_run_ends`, never a timer), and the list is
  told to redraw then, as after a press's own run;
- a read that began within the minimum spacing (`spacing_s`) and that the person did not start
  is the answer: "Checked just now (HH:MM)" with that read's result in the row's words (still
  found, no longer found, or the check failed), busy only until the held list has taken it.

**Refused, naming both operands** (409, drawn in place), only for what a press cannot ask:
- the person's own run is still running (their press in another tab): a second would read
  the same moment again;
- the person's own read began less than its minimum spacing ago: that reading is as fresh as
  a new one;
- its last read found its dependency not answering and its backoff's next try is still ahead
  (reader_job rule 14): a press does not jump the backoff;
- the readers do not run in this process, or no reader has that name.

A person's own read is one whose recorded cause is a request by the same viewer
(`trigger.kind` ``request`` and ``by`` equal, an unidentified viewer's equal to another
unidentified one's, since nothing tells them apart).

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

#: reader name -> what the run a press waited for ended with, in this process: ``{"run",
#: "ok", "error", "at"}`` (`_done` for its own run, `_joined_end` for one it joined). Memory
#: only.
_ENDED: dict = {}

#: reader name -> the run in progress a press joined, one the person did not start (C3361):
#: ``{"run", "since", "at", "cause"}`` (`_join`). Memory only.
_JOINED: dict = {}

#: reader name -> the read within the spacing a press was answered with, one the person did
#: not start (C3361): ``{"at", "last", "ok", "error"}``. Memory only.
_CHECKED: dict = {}


def _own(trigger: dict, by: str) -> bool:
    """Was the read *trigger* records caused by *by*'s own request (their press, another tab's
    included)? An unidentified viewer's equals another unidentified one's: nothing tells them
    apart."""
    t = trigger or {}
    return t.get("kind") == "request" and (t.get("by") or "") == (by or "")


def _run_key(run: dict) -> str:
    """A run in progress as one key: its request's id, else its cause and start (a scheduled
    run records no id)."""
    return run.get("run") or f"{run.get('kind') or 'run'}@{run.get('since')}"


def _tell(name: str) -> None:
    """The list told to redraw (the key `attention`), so a run whose answer moved nothing the
    store compares is still drawn."""
    from modules import invalidation
    try:
        invalidation.announce(list(ANNOUNCE_KEYS), by=ANNOUNCER)
    except Exception as exc:                          # noqa: BLE001 (no socket: nobody to tell)
        log.warning("recheck: the list was not told about %s: %s", name, exc)


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
    from modules import reader_job

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
    _tell(name)


def _joined_end(name: str, key: str, since: float) -> None:
    """The end of a run a press joined (`reader_job.when_run_ends`): what it stored, when the
    stored attempt is that run's (begun at or after its start), then the list told to
    redraw."""
    from modules import reader_job

    attempt = (reader_job.read_cached(name).get("doc") or {}).get("last_attempt") or {}
    at = reader_job._parse_iso(attempt.get("at"))
    if at is not None and at >= int(since):
        ok, error = bool(attempt.get("ok")), str(attempt.get("error") or "")
    else:
        ok, error = False, "its stored answer is not this run's"
    _ENDED[name] = {"run": key, "ok": ok, "error": error, "at": time.time()}
    _tell(name)


def _join(name: str, running: dict, by: str, now: float):
    """Join *running*, a run of *name* the person did not start: answered as reading now, the
    control busy until it ends. None when it ended in between (its read is then the answer
    within the spacing)."""
    from modules import reader_job

    key = _run_key(running)
    cause = reader_job.trigger_words(
        {"kind": running.get("kind") or "request", "by": running.get("by")}, by)
    _JOINED[name] = {"run": key, "since": running["since"], "at": now, "cause": cause}
    hooked = reader_job.when_run_ends(name, lambda e: _joined_end(name, key, running["since"]))
    if hooked is None and not reader_job.request_in_flight(name):
        _JOINED.pop(name, None)
        return None
    log.info("recheck: %s's run in progress (%s) joined by %s", name, cause,
             by or "nobody identified")
    return {"ok": True, "started": False, "joined": True, "reader": name,
            "since": _iso(running["since"]), "cause": cause}


def ask(name: str, by: str, now: float = None) -> dict:
    """Run *name*'s reader again now for *by*, or answer with the read the person did not
    start, or say why not. ``{"ok", "started": True, "reader", "run", "since",
    "bound_seconds", "bound_basis"}`` (run now); ``{"ok", "started": False, "joined": True,
    "reader", "since", "cause"}`` (a run in progress joined); ``{"ok", "started": False,
    "checked": True, "reader", "at", "read_ok", "error", "cause"}`` (a read within the
    spacing); or ``{"ok": False, "refused", "reason", "operands"}`` naming the comparison it
    made."""
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
        if _own({"kind": running.get("kind") or "request", "by": running.get("by")}, by):
            return _refused_running(name, running, by)
        joined = _join(name, running, by, now)
        if joined is not None:
            _CHECKED.pop(name, None)
            return joined
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
        trigger = attempt.get("trigger") or {}
        if _own(trigger, by):
            return {"ok": False, "refused": "spacing", "reader": name,
                    "reason": (f"{name} began a read {int(now - last)} s ago on your request, "
                               f"within its minimum spacing of {gap} s"),
                    "operands": {"last": _iso(last), "next": _iso(last + gap), "spacing": gap,
                                 "ago": int(now - last)}}
        # A read the person did not start, as fresh as one a press would ask: the answer.
        ok, error = bool(attempt.get("ok")), str(attempt.get("error") or "")
        _JOINED.pop(name, None)
        _CHECKED[name] = {"at": now, "last": last, "ok": ok, "error": error}
        return {"ok": True, "started": False, "checked": True, "reader": name,
                "at": _iso(last), "read_ok": ok, "error": error,
                "cause": reader_job.trigger_words(trigger, by)}
    bound = reader_job.answer_bound(name)
    # The last press's end forgotten BEFORE the run starts: a fast run ends on its own thread
    # before `request_run` returns, and its end must not be the one forgotten.
    _ENDED.pop(name, None)
    _JOINED.pop(name, None)
    _CHECKED.pop(name, None)
    got = reader_job.request_run(reader, by, announce=reader_job.announce_via_page,
                                 on_done=lambda e: _done(dict(e, reader=name)))
    if not got.get("started"):
        # Started by another press between the two checks: the person's own is refused as
        # above, another person's joined.
        if _own({"kind": "request", "by": got.get("by")}, by):
            return _refused_running(name, got, by)
        return _join(name, got, by, now) or _refused_running(name, got, by)
    log.info("recheck: %s run again by %s (run %s)", name, by or "nobody identified",
             got["run"])
    return {"ok": True, "started": True, "reader": name, "run": got["run"],
            "since": _iso(got["since"]), "bound_seconds": bound["seconds"],
            "bound_basis": bound["basis"]}


def _refused_running(name: str, running: dict, by: str) -> dict:
    from modules import reader_job
    return {"ok": False, "refused": "running", "reader": name,
            "reason": f"{name} is already running", "operands": {
                "since": _iso(running["since"]),
                "cause": reader_job.trigger_words(
                    {"kind": running.get("kind") or "request", "by": running.get("by")}, by)}}


def _held_row(row_id: str):
    """The row *row_id* as the held list draws it now (a row folded under another included),
    or None: from the background's value, never computed for the press."""
    from modules import attention_store

    page = attention_store.read()
    for r in page.get("rows") or []:
        for x in [r] + list(r.get("folded") or []):
            if x.get("id") == row_id:
                return x
    return None


def checked_answer(got: dict, row_id: str) -> dict:
    """What a press answered with a read it did not start (`ask`'s ``checked``) draws on the
    row *row_id*, in the row's own words: ``{"checked": {"at", "failed"}}`` when that read
    failed; ``{"checked": {"at", "cleared": True}}`` when the held list no longer has the row
    (the list told to redraw, so it leaves); ``{"busy", "since", "taking"}`` while the held
    list has not taken that read yet; else ``{"checked": {"at"}}`` (still found). Without a
    row (a page drawn before rows were named), ``{"checked": {"at", "unnamed": True}}``."""
    from modules import reader_job

    if not got.get("read_ok"):
        return {"checked": {"at": got["at"], "failed": got.get("error") or "the read failed"}}
    if not row_id:
        return {"checked": {"at": got["at"], "unnamed": True}}
    held = _held_row(row_id)
    if held is None:
        _tell(got.get("reader") or "")
        return {"checked": {"at": got["at"], "cleared": True}}
    shown = reader_job._parse_iso(held.get("read_at"))
    if shown is not None and shown < reader_job._parse_iso(got["at"]):
        return {"busy": True, "since": got["at"], "taking": True}
    return {"checked": {"at": got["at"]}}


def state(name: str, read_at: str = None, now: float = None) -> dict:
    """What a row whose reading is *name*'s draws for its control, from memory only: ``None``
    (idle, nothing to say), ``{"busy": True, "since"}`` (with ``cause`` for a run joined,
    ``taking`` for a read the held list has not taken yet), ``{"failed": words, "at"}``, or
    ``{"checked": {"at"}}`` / ``{"checked": {"at", "failed"}}`` (a read the press was answered
    with). The latest press decides: its own run, a run it joined, or a read it was answered
    with. *read_at* is the reading the held row stands on."""
    from modules import reader_job

    now = time.time() if now is None else now
    name = _base(name)
    shown = reader_job._parse_iso(read_at) if read_at else None
    entry = reader_job.last_request(name)
    joined, checked = _JOINED.get(name), _CHECKED.get(name)
    pressed = [p for p in ((entry["since"], 0, "own") if entry else None,
                           (joined["at"], 1, "joined") if joined else None,
                           (checked["at"], 1, "checked") if checked else None) if p]
    if not pressed:
        return None
    latest = max(pressed)[2]
    if latest == "checked":
        if now - checked["at"] > SETTLE_S:
            return None
        if not checked["ok"]:
            return {"checked": {"at": _iso(checked["last"]),
                                "failed": checked["error"] or "the read failed"}}
        if shown is not None and shown < checked["last"]:
            # Read, not yet in the held list: drawn when it is.
            return {"busy": True, "since": _iso(checked["last"]), "taking": True}
        return {"checked": {"at": _iso(checked["last"])}}
    if latest == "joined":
        now_running = reader_job.in_progress(name) or reader_job.request_in_flight(name)
        if now_running and _run_key(now_running) == joined["run"]:
            return {"busy": True, "since": _iso(joined["since"]), "cause": joined["cause"]}
        return _settled(_ENDED.get(name) or {}, joined["run"], joined["since"], shown, now)
    if not entry.get("done"):
        return {"busy": True, "since": _iso(entry["since"])}
    return _settled(_ENDED.get(name) or {}, entry.get("run"), entry["since"], shown, now)


def _settled(ended: dict, run: str, since: float, shown, now: float):
    """A run a press waited for, once it ended: nothing to draw when the end is not that run's
    (an operation's wake, a host job) or is older than `SETTLE_S`; its failure; busy while the
    held list has not taken its value (the row's reading older than the run); else idle."""
    if ended.get("run") != run:
        return None
    if now - (ended.get("at") or 0) > SETTLE_S:
        return None
    if not ended.get("ok"):
        return {"failed": ended.get("error") or "the read failed", "at": _iso(ended["at"])}
    if shown is not None and shown < int(since):
        # Stored, not yet in the held list: still the answer this press waits for.
        return {"busy": True, "since": _iso(since)}
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
