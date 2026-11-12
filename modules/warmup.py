"""Mercury's warm-up at start, and the readiness `/health` reports from it (C2465).

`/health` said a restarted process was up 0.1 s after the restart, while its first requests
waited behind the first read of the record of AI calls: on the host on 2026-11-04 (471 MB,
36,156 rows) the first AI chip took 36.6 s, the first Needs attention count 37.3 s and two
`/v2/` 40.8 and 21.1 s, all finishing within a second of each other, and the next chip 49 ms.
Every page that draws AI spend waits on the one kept read (`records_migrate._tail_rows_kept`,
under its lock), so whichever request came first paid the parse and the rest queued behind it.

The operator's ruling (2026-11-04): ready only when Mercury can serve. So the first-request
work is done here, at start, on one background thread, as declared steps (`STEPS`), and
`/health` says `ready` only once every step has finished without an error. Each step records
its state, its start and end, its seconds and its error. A step that raises is recorded and
the warm-up goes on to the next; readiness then stays false and names the failed step and its
error, never ready: the step's work was not done, so the first request that needs it pays it
again or meets the same error (the operator's rule is "ready only when Mercury can serve").

Started by the app's own start-up (`app._start_background_daemons`, when the program is RUN),
never by importing anything (C36): a process that never started it says so, not ready.
"""
import datetime
import logging
import threading
import time

log = logging.getLogger(__name__)


def _ai_calls() -> None:
    """The record of AI calls read once into the kept rows (`calls.warm`): what the AI chip,
    Needs attention's caps and History's AI calls read first."""
    from modules.ai import calls

    calls.warm()


def _needs_attention() -> None:
    """Needs attention's sources computed once for the installation's current network, into
    the background store every page's sidebar badge and Needs attention read
    (`attention_store.refresh`, C3166): until it lands they draw "Reading …"."""
    from modules import attention_store
    from modules.config import get_current_list_name

    attention_store.ensure(get_current_list_name())


#: The declared steps, in order: ``(name, what it warms, the function)``. Measured on a cold
#: start on the laptop against a planted 475 MB record (36,156 rows), 2026-11-05: ai-calls
#: 3.9 to 4.2 s, needs-attention 0.05 s after it; every v2 page's first request after both
#: was at most 0.26 s, so no other step is declared (tests/test_warmup.py's row in
#: docs/TESTING.md). Needs attention is the operator's ruling's own step: on the host it
#: gathers real sources the planted store had none of.
STEPS = (
    ("ai-calls", "the record of AI calls, read once into the kept rows", _ai_calls),
    ("needs-attention", "Needs attention's sources, gathered once", _needs_attention),
)

#: The longest an error is said in `/health` (which is ungated): its first line, masked.
ERROR_CHARS = 300

_lock = threading.Lock()
_run = None


def _iso(epoch: float) -> str:
    return (datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)
            .isoformat(timespec="milliseconds").replace("+00:00", "Z"))


def _said(exc: BaseException) -> str:
    """*exc* as `/health` may say it: its kind and first line, masked, bounded."""
    from modules.redact import redact_text

    first = (str(exc).strip().splitlines() or [""])[0]
    text = f"{type(exc).__name__}: {first}" if first else type(exc).__name__
    try:
        text = redact_text(text)
    except Exception:                                   # noqa: BLE001 (never unmasked)
        text = type(exc).__name__
    return text[:ERROR_CHARS]


def start(steps=None, spawn=None) -> bool:
    """Run the warm-up's *steps* (`STEPS`) on a background task, once a process: False when it
    was already started. *spawn* starts ``spawn(target)`` (the app passes SocketIO's
    `start_background_task`); a daemon thread by default."""
    global _run
    with _lock:
        if _run is not None:
            return False
        steps = tuple(STEPS if steps is None else steps)
        _run = {"rows": [{"step": name, "what": what, "state": "waiting", "started_at": None,
                          "ended_at": None, "seconds": None, "error": ""}
                         for name, what, _fn in steps],
                "fns": [fn for _n, _w, fn in steps], "begun": {}}
    (spawn or _thread)(_go)
    return True


def _thread(target) -> None:
    threading.Thread(target=target, name="nmas-warmup", daemon=True).start()


def _go() -> None:
    run = _run
    for i, fn in enumerate(run["fns"]):
        t0, began = time.monotonic(), time.time()
        with _lock:
            run["rows"][i].update(state="running", started_at=_iso(began))
            run["begun"][i] = t0
        error = ""
        try:
            fn()
        except Exception as exc:                        # noqa: BLE001 (recorded, then on)
            error = _said(exc)
            log.error("warm-up: the step %s failed: %s", run["rows"][i]["step"], error)
        secs = round(time.monotonic() - t0, 2)
        with _lock:
            run["rows"][i].update(state="failed" if error else "done", ended_at=_iso(time.time()),
                                  seconds=secs, error=error)
        log.info("warm-up: %s %s in %.2f s", run["rows"][i]["step"],
                 "FAILED" if error else "done", secs)
    # The warm-up's end moves Needs attention's readiness row and announces nothing: the
    # sources that read it are marked (C3166), so the row clears within one debounce.
    try:
        from modules import attention_store
        attention_store.mark(("app_version",), "warm-up")
    except Exception as exc:                            # noqa: BLE001 (its cadence reads it)
        log.warning("warm-up: Needs attention's store was not told the warm-up ended: %s", exc)


def status() -> dict:
    """``{"ready", "warming", "not_ready"}``: *ready* true only once every step has finished
    without an error; *warming* each step's row (a running step's seconds so far); *not_ready*
    the sentence saying why not, "" when ready."""
    with _lock:
        run = _run
        if run is None:
            return {"ready": False, "warming": [],
                    "not_ready": "the warm-up has not started in this process"}
        rows = [dict(r) for r in run["rows"]]
        now = time.monotonic()
        for i, r in enumerate(rows):
            if r["state"] == "running":
                r["seconds"] = round(now - run["begun"][i], 2)
    failed = [r for r in rows if r["state"] == "failed"]
    pending = [r for r in rows if r["state"] in ("waiting", "running")]
    if failed:
        why = "; ".join(f"the warm-up step {r['step']} failed: {r['error']}" for r in failed)
    elif pending:
        running = [r for r in rows if r["state"] == "running"]
        why = (f"warming: {running[0]['step']} running for {running[0]['seconds']} s"
               if running else f"warming: {pending[0]['step']} not begun")
        why += f" ({len(pending)} of {len(rows)} steps to finish)"
    else:
        why = ""
    return {"ready": not failed and not pending, "warming": rows, "not_ready": why}
