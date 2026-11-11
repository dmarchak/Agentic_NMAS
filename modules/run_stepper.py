"""THE progress display: one stepper for every multi-step or multi-device operation (the
operator, 2026-10-12: Save All's stepper, C605, "was agreed as THE progress display for every
multi-step or multi-device operation, but only Save All uses it").

Boards: `SaveProgress.dc.html` (C605, the desk: a row per device, its declared steps laid out
across with the time in each, an overall bar, counts by state, the operation's own last row
such as the commit; from 25 rows grouped, collapsed, with Find a device) and
`StepperPhone.dc.html` ("the one stepper at phone width: vertical": below about 640 px each
row's steps run down, the current one with what it waits on). Drawn by ONE macro,
`templates/v2/_run_stepper.html` (`run_stepper`), its styles under `.run` in nmas-v2.css, and
its live clock by `static/js/nmas_stepper.js`.

Each operation keeps its own step names (`(key, words, waits, names)` tuples beside its code:
`pipeline.STEPPER_STEPS`, `save_op.DEVICE_STEPS`, `reload_op`, `rotate_op`, `adopt`, ...) and
hands this module rows built from them (`device_actions.stepper`). What the card draws is
decided here, never in a template: a row's group, the counts, the bar, the groups at scale.
tests/test_one_stepper.py holds that no operation page draws progress any other way.

**A run that records its own steps** (the operator, 2026-11-11: "a long operation shows a
stepper, with the current step, each step done, failed or pending, live waits with a countdown,
and each verify read as it happens"; "every operation and heal ends with a visible outcome on
its card ... with the steps taken"). An operation that keeps its steps in its own record
(``{"step", "result", "words", "at"}``: a re-subscribe's run, a heal's decision and act) is
drawn from that list by `from_record`, while it runs and after it ended, from the same list:
each DECLARED step done, running, failed, pending, not reached or not needed; the step to act
on leading (`lead`: a failed step first, else the running one); a wait with its declared
length and when it began; each read a step made (its ``reads``, else its ``checks``); and every
step as it was recorded, in order (`trail`: "the steps taken"). Nothing is invented: a step
the run never recorded is never drawn done, and a result this module does not know is amber,
never green.
"""

import calendar
import logging
import re
import time

log = logging.getLogger(__name__)

#: A row's group, in the order the card leads with: what to act on first, then what moves.
#: (key, words, chip kind)
GROUPS = (("failed", "failed", "danger"), ("partial", "done, its verify did not pass", "warn"),
          ("running", "running", "info"), ("waiting", "waiting their turn", "muted"),
          ("not_reached", "not reached: the run stopped before them", "muted"),
          ("done", "done", "ok"))
#: The counts line's order (board C605: "2 through their turn · 6 running · 1 waiting · 0
#: failed"); the groups at scale lead with what to act on (`GROUPS`).
TALLY_ORDER = ("done", "partial", "running", "waiting", "not_reached", "failed")
#: From this many rows the card groups and collapses them, with Find above; fewer read at a
#: glance, every row on its stepper (board C605).
GROUP_FROM = 25
#: A step's states. `not_reached`: the run stopped before it (drawn struck through).
#: `skipped`: the run went past it without needing it (a rollback when nothing failed).
STEP_STATES = ("done", "running", "waiting", "failed", "partial", "not_reached", "skipped")
#: Each state in words, for a reader the colour does not reach and for the steps taken.
STATE_WORDS = {"done": "done", "running": "running now", "waiting": "pending",
               "failed": "failed", "partial": "not fully done",
               "not_reached": "not reached: the run stopped before it",
               "skipped": "not needed in this run"}
#: A recorded step's result -> its state. Done is an ALLOWLIST (these, and the results an
#: operation names as its good ones): any other result is drawn amber, never green.
DONE_RESULTS = ("ok", "pass", "done")
FAILED_RESULTS = ("failed", "fail", "refused", "error")
#: A read's or a check's result, in words.
READ_WORDS = {"pass": "pass", "fail": "fail", "unreadable": "unreadable",
              "cant_tell": "unreadable", "waiting": "not yet"}
#: Worst first: a step recorded several times is drawn as its worst record.
_WORST = ("failed", "partial", "running", "done", "skipped")


def step(key: str, words: str, state: str, *, took_s=None, note: str = "",
         since: str = "") -> dict:
    """One step on a row. *note*: what a running step waits on, or a failed step's reason."""
    if state not in STEP_STATES:
        raise ValueError(f"a step's state is one of {STEP_STATES}, not {state!r}")
    return {"key": key, "words": words, "state": state, "took_s": took_s, "note": note,
            "since": since}


def _for_count(words: str, n: int) -> str:
    """A group's words for its count: one row waits ITS turn, several wait THEIR turn (C741:
    "1 waiting their turn" where board C605 says "its")."""
    if n != 1:
        return words
    return re.sub(r"\btheir\b", "its", re.sub(r"\bthem\b", "it", words))


def from_stepper(rows: list) -> list:
    """`device_actions.stepper`'s rows as this card's steps (its running step's note is what
    it waits on, and the last thing it did). A row already in this card's shape (a `note` and
    no `waits`: a route that hands its template only what it draws, C1579) keeps its note."""
    out = []
    for s in rows or []:
        note = "" if "waits" in s else (s.get("note") or "")
        if s.get("state") == "running":
            note = f"waits on {s['waits']}" if s.get("waits") else ""
            if s.get("last"):
                # A finished part of the running step, in words (C741: never its code name).
                note += f" (last done: {s['last'].replace('_', ' ')})"
        out.append(step(s.get("key", ""), s.get("words", ""), s.get("state", "waiting"),
                        took_s=s.get("took_s"), note=note, since=s.get("since", "")))
    return out


def row(name: str, group: str, steps: list = None, *, device: bool = True, href: str = "",
        detail: str = "", elapsed_s=None, elapsed_words: str = "", since: str = "") -> dict:
    """One row: a device (or the operation's one subject), its group, its steps. A row with no
    steps says *detail* in their place (waiting its turn, or why it never started). A device's
    row links to its page (built by the template, so a model needs no request); another
    subject links to *href* when given."""
    if group not in dict((g, w) for g, w, _k in GROUPS):
        raise ValueError(f"a row's group is one of {[g for g, _w, _k in GROUPS]}, not {group!r}")
    return {"name": name, "group": group, "steps": list(steps or []), "device": device,
            "href": href, "detail": detail, "elapsed_s": elapsed_s,
            "elapsed_words": elapsed_words, "since": since}


def finished(steps: list, outcome: str, partial_at: str = "") -> list:
    """*steps* as a finished row draws them: all done for a good outcome; for a failed one, the
    step it stopped in failed and the rest not reached. A partial one marks its last step
    partial, or the step keyed *partial_at* when the row has one: the step that did not pass
    (a deploy's verify, C1541), never drawn done beside it."""
    if outcome in ("done", "partial"):
        at = next((i for i, s in enumerate(steps) if partial_at and s.get("key") == partial_at),
                  len(steps) - 1)
        return [dict(s, state=("partial" if outcome == "partial" and i == at else "done"))
                for i, s in enumerate(steps)]
    out, stopped = [], False
    for s in steps:
        if stopped:
            out.append(dict(s, state="not_reached"))
        elif s["state"] in ("running", "failed"):
            out.append(dict(s, state="failed"))
            stopped = True
        elif s["state"] == "waiting":
            out.append(dict(s, state="not_reached"))
            stopped = True
        else:
            out.append(s)
    return out


def summary(value: int, total: int, *, label: str, parts: list) -> dict:
    """The card's bar and counts alone (`run_summary`), for a run whose per-device rows are its
    own answers rather than steps (Show commands' answers grouped where alike, the
    logging-path test's arrivals): *value* of *total* through, *parts* the counts line as
    ``[(n, words, kind)]``, a failed kind drawn red when any."""
    return {"label": label, "bar": {"max": total or 1, "value": value,
                                    "words": f"{value} of {total} {label.lower()}"},
            "tally": [{"group": kind, "n": n, "words": words, "kind": kind}
                      for n, words, kind in parts]}


def at_step(name: str, label: str, steps: tuple, current: int, *, elapsed_s=None,
            note: str = "", device: bool = True) -> dict:
    """A one-row card for an operation that knows which of its declared *steps* (``(key,
    words)``) it is on but notes no trail (a read that holds no device, as Capture's preview;
    a NetBox job, whose subject is a list, ``device=False``): the steps before *current*
    done, *current* running for *elapsed_s*, the rest waiting."""
    rows = [step(k, w, "done" if i < current else "running" if i == current else "waiting",
                 took_s=elapsed_s if i == current else None,
                 note=note if i == current else "")
            for i, (k, w) in enumerate(steps)]
    return card([row(name, "running", rows, device=device)], label=label,
                key=label.lower().replace(" ", "-"))


def single(steps: list, name: str, label: str, *, device: bool = True) -> dict:
    """A one-device operation's card: its one row from `device_actions.stepper`'s rows (a
    deploy, a restore, a reload, a rotation, an adoption, holding the device). The row runs
    while any step runs, is done once every step is, and waits before the first begins.
    *device*: False for a device with no page to link to yet (a console survey before Create,
    C1579)."""
    mine = from_stepper(steps)
    states = {s["state"] for s in mine}
    group = ("running" if "running" in states else "failed" if "failed" in states
             else "done" if mine and states == {"done"} else "waiting")
    return card([row(name, group, mine, device=device)], label=label,
                key=label.lower().replace(" ", "-"))


def card(rows: list, *, label: str, final: dict = None, q: str = "", search: tuple = None,
         search_target: str = "", key: str = "run", noun: str = "device",
         group_from: int = GROUP_FROM,
         group_words: dict = None) -> dict:
    """The card's model: ``{"rows", "total", "counts", "tally", "bar", "groups", "grouped",
    "final", "label", "q", "search", "single"}``. *final*: the operation's own last row
    (the batch commit, a save, a reload's wait), ``{"name", "words", "state", "detail"}``,
    drawn after the rows. *q* filters the rows drawn, never the counts. *group_words*: an
    operation's own words for a group (Save's done rows are "through their turn, waiting for
    the commit")."""
    words = dict({g: w for g, w, _k in GROUPS}, **(group_words or {}))
    # Each row's state in words, for a reader the mark's colour does not reach.
    rows = [dict(r, state_words=words[r["group"]]) for r in rows]
    total = len(rows)
    counts = {g: sum(1 for r in rows if r["group"] == g) for g, _w, _k in GROUPS}
    q_ = (q or "").strip().lower()
    shown = [r for r in rows if not q_ or q_ in r["name"].lower()]
    grouped = total >= group_from
    groups = [{"name": g, "words": words[g], "kind": k, "count": counts[g],
               "rows": [r for r in shown if r["group"] == g],
               "open": g in ("failed", "partial", "running")}
              for g, _w, k in GROUPS if counts[g]]
    # The counts line in board C605's order: what is through, what moves, what waits, what
    # failed (red when any did). Done, running, waiting and failed always said (a zero is an
    # answer); a partial or a not-reached only when there is one.
    kinds = {g: k for g, _w, k in GROUPS}
    tally = [{"group": g, "n": counts[g], "words": _for_count(words[g], counts[g]),
              "kind": kinds[g]}
             for g in TALLY_ORDER if counts[g] or g not in ("partial", "not_reached")]
    through = counts["done"] + counts["partial"] + counts["failed"] + counts["not_reached"]
    return {"rows": shown, "total": total, "counts": counts, "tally": tally, "label": label,
            "bar": {"max": total or 1, "value": through,
                    "words": (f"{through} of {total} {noun}{'s' if total != 1 else ''} through, "
                              f"{counts['running']} running, {counts['waiting']} waiting, "
                              f"{counts['failed']} failed")},
            "groups": groups, "grouped": grouped, "final": final, "q": q,
            "search": search, "search_target": search_target, "key": key, "single": total == 1,
            "noun": noun}


# ── A run that records its own steps ────────────────────────────────────────────────────────

def _epoch(iso):
    """An ISO time the records keep (``2026-11-11T16:38:02Z``) as an epoch, or None."""
    try:
        return calendar.timegm(time.strptime(str(iso or "")[:19], "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, OverflowError):
        return None


def result_state(result, good=(), bad=()) -> str:
    """A recorded step's *result* as a step's state. *good* and *bad* are the operation's own
    results (a heal's ``healed``, a decision's ``cant_fix``); a result nobody names is
    ``partial``: amber, never green by resemblance."""
    r = str(result or "")
    if r == "running":
        return "running"
    if r == "skipped":
        return "skipped"
    if r in DONE_RESULTS or r in good:
        return "done"
    if r in FAILED_RESULTS or r in bad:
        return "failed"
    return "partial"


def _lines(event: dict) -> list:
    """What a step read, one line per read: its ``reads`` as they were appended (``{"at",
    "command", "result", "words"}``), else its final ``checks`` (``{name: {"state",
    "words"}}``, a record written before reads were kept). ``[{"what", "state",
    "state_words", "words", "at"}]``."""
    out = []
    reads = event.get("reads")
    if isinstance(reads, list) and reads:
        for r in reads:
            if not isinstance(r, dict):
                continue
            state = str(r.get("result") or "")
            out.append({"what": str(r.get("command") or ""), "state": state,
                        "state_words": READ_WORDS.get(state, state or "not said"),
                        "words": str(r.get("words") or ""), "at": str(r.get("at") or "")})
        return out
    checks = event.get("checks")
    if isinstance(checks, dict):
        for name, c in checks.items():
            if not isinstance(c, dict):
                continue
            state = {"cant_tell": "unreadable", "waiting": "fail"}.get(c.get("state"),
                                                                       str(c.get("state") or ""))
            out.append({"what": str(name), "state": state,
                        "state_words": READ_WORDS.get(state, state or "not said"),
                        "words": str(c.get("words") or ""), "at": str(event.get("at") or "")})
    return out


def _wait(event: dict, now: float, running: bool):
    """A step's declared wait, ``{"began", "length_s", "left_s", "words"}``, or None: the
    length the operation declared (``wait_s``) and when the step began (``began``, else its
    ``at``). The countdown the page draws is of these two, sent by the server; ``left_s`` is
    what was left when this was drawn."""
    try:
        length = float(event.get("wait_s"))
    except (TypeError, ValueError):
        return None
    began = event.get("began") or event.get("at") or ""
    at = _epoch(began)
    if length <= 0 or at is None:
        return None
    left = max(0, round(at + length - now)) if running else 0
    n = int(length) if float(length).is_integer() else length
    return {"began": began, "length_s": n, "left_s": left,
            "words": (f"{left} s left of {n} s" if running and left else
                      f"its {n} s are up; waiting for the next step" if running else
                      f"a wait of {n} s")}


def from_record(declared, steps, *, ended: bool, now: float = None, good=(), bad=(),
                conditional=(), prefix: str = "") -> dict:
    """A run's own recorded *steps* (``{"step", "result", "words", "at"}``, in the order they
    were written) against the steps it *declared* (``(key, words)``, in order): ``{"steps",
    "lead", "trail", "at", "of"}``.

    - ``steps``: one per declared step, for the stepper. Recorded: its worst record's state
      (a step still ``running`` is running only while it is the run's newest step and the run
      has not *ended*; one a later step followed is done, unless a later record of the same
      step says otherwise; a run that ended inside it failed there). Never recorded: pending
      while the run goes on; once it *ended*, not reached when a step before it failed or was
      not fully done, else not needed (also every step named in *conditional*, a rollback).
    - ``lead``: the step to read first: the first failed one, else the running one, else
      (ended) the first not fully done; None when every step is done.
    - ``trail``: every step as recorded, in order, each with its state, its own words, its
      time and what it read (`_lines`).
    - ``at`` of ``of``: the newest recorded step's place among the declared ones."""
    now = time.time() if now is None else now
    steps = [s for s in steps or [] if isinstance(s, dict)]
    keys = [d[0] for d in declared]
    words = {d[0]: d[1] for d in declared}
    newest = len(steps) - 1
    events = {k: [] for k in keys}
    for n, s in enumerate(steps):
        if s.get("step") in events:
            events[s["step"]].append((n, s))

    def state_of(n, s):
        st = result_state(s.get("result"), good, bad)
        if st != "running" or (n == newest and not ended):
            return st
        if any(m > n for m, _x in events.get(s.get("step"), [])):
            return None                               # a later record of this step says
        return "failed" if n == newest else "done"

    by_key = {}
    for k in keys:
        got = [(st, n, s) for n, s in events[k] for st in [state_of(n, s)] if st]
        by_key[k] = got
    reached = max([i for i, k in enumerate(keys) if events[k]], default=-1)
    worst = {k: min((g[0] for g in by_key[k]), key=_WORST.index, default="")
             for k in keys}
    stop = next((i for i, k in enumerate(keys) if worst[k] in ("failed", "partial")), None)
    out, lead = [], None
    for i, k in enumerate(keys):
        got = by_key[k]
        note, since, took, extra = "", "", None, {}
        if not got:
            if k in conditional and (ended or i < reached):
                state = "skipped"
            elif not ended:
                state = "skipped" if i < reached else "waiting"
            else:
                state = "not_reached" if stop is not None and i > stop else "skipped"
        else:
            state = worst[k]
            _st, n, last = got[-1]
            note = str(last.get("words") or "")
            if state == "failed" and _st == "failed" and last.get("result") == "running":
                note = (note + ". " if note else "") + "The run ended in this step"
            first = got[0][2]
            a, b = _epoch(first.get("began") or first.get("at")), _epoch(last.get("at"))
            if state == "running":
                since = str(last.get("began") or last.get("at") or "")
                at = _epoch(since)
                took = round(max(0.0, now - at)) if at is not None else None
            elif a is not None and b is not None and first.get("began"):
                took = round(max(0.0, b - a))
            wait = _wait(last, now, state == "running")
            # A step recorded several times (a removal, a verify, for each subscription):
            # each record's own words lead what it read, so no read is drawn without the
            # record it belongs to.
            lines = []
            for i, (st, _n, e) in enumerate(got):
                if len(got) > 1:
                    lines.append({"what": f"{i + 1} of {len(got)}", "state": st,
                                  "state_words": STATE_WORDS[st],
                                  "words": str(e.get("words") or ""),
                                  "at": str(e.get("at") or "")})
                lines += _lines(e)
            extra = {"wait": wait, "lines": lines, "several": len(got) > 1}
        one = dict(step(prefix + k, words[k], state, took_s=took, note=note, since=since),
                   state_words=STATE_WORDS[state], wait=extra.get("wait"),
                   lines=extra.get("lines") or [], several=bool(extra.get("several")))
        out.append(one)
    for want in ("failed", "running") + (("partial",) if ended else ()):
        lead = next((s for s in out if s["state"] == want), None)
        if lead:
            break
    trail = []
    for n, s in enumerate(steps):
        st = state_of(n, s) or "done"
        trail.append({"key": str(s.get("step") or ""),
                      "words": words.get(s.get("step")) or str(s.get("step") or "a step"),
                      "state": st, "state_words": STATE_WORDS[st],
                      "said": str(s.get("words") or ""), "at": str(s.get("at") or ""),
                      "lines": _lines(s)})
    at = keys.index(steps[newest]["step"]) + 1 if steps and steps[newest].get("step") in keys \
        else max(reached + 1, 0)
    return {"steps": out, "lead": lead, "trail": trail, "at": at, "of": len(keys)}


def current_words(declared, steps) -> str:
    """The run's real current step, in words, for the In progress list: its newest recorded
    step by the words it declared, its state unless it is running, and its place ("Verify
    each within 290 s · step 9 of 11"); ``"started; no step recorded yet"`` before the
    first."""
    steps = [s for s in steps or [] if isinstance(s, dict)]
    if not steps:
        return "started; no step recorded yet"
    last = steps[-1]
    keys = [d[0] for d in declared]
    words = {d[0]: d[1] for d in declared}
    key = last.get("step")
    state = result_state(last.get("result"))
    said = words.get(key) or str(key or "a step")
    place = f" · step {keys.index(key) + 1} of {len(keys)}" if key in keys else ""
    return said + ("" if state == "running" else f": {STATE_WORDS[state]}") + place


#: A run's outcome level -> the least its row's group may be ("never green over a partial").
_LEVEL_GROUP = {"ok": "done", "warn": "partial", "danger": "failed"}


def record_card(name: str, label: str, phases: list, *, ended: bool, level: str = "",
                device: bool = True, href: str = "", detail: str = "", key: str = "") -> dict:
    """A one-row card for a run drawn from its own record: *phases* are `from_record`'s
    answers, in order (a heal's decision, then its act; any other run has one). The row's group
    is its steps' worst, and never better than the outcome's *level* (``ok``, ``warn``,
    ``danger``) once the run *ended*. The card carries ``lead``, ``trail`` and ``ended`` for
    the stepper to draw under the row."""
    steps = [s for p in phases for s in p["steps"]]
    trail = [t for p in phases for t in p["trail"]]
    states = {s["state"] for s in steps}
    group = ("failed" if "failed" in states else
             "running" if not ended else
             "partial" if "partial" in states else "done")
    if ended:
        want = _LEVEL_GROUP.get(level, "partial" if level else group)
        order = ("failed", "partial", "done")
        group = min(group, want, key=order.index)
    lead = None
    for wanted in ("failed", "running", "partial"):
        lead = next((p["lead"] for p in phases
                     if p["lead"] and p["lead"]["state"] == wanted), None)
        if lead:
            break
    words = {g: w for g, w, _k in GROUPS}
    one = dict(row(name, group, steps, device=device, href=href, detail=detail),
               state_words=words[group])
    # One row, so no bar, counts or groups: the card carries only what the stepper draws.
    for unused in ("elapsed_s", "since"):
        one.pop(unused, None)
    return {"rows": [one], "single": True, "grouped": False, "final": None, "label": label,
            "key": key or label.lower().replace(" ", "-"), "lead": lead, "trail": trail,
            "ended": ended}
