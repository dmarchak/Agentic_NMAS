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

**Stages: progress, not mechanics** (the operator, 2026-11-12, after the F1 self-heal smoke test
on a lab router: "TOO MANY STEPS: a person cares about progress, not mechanics. The stepper shows FIVE
stages ... each with one plain sentence, its time and its state ... Each stage expands to its
detailed steps ... A failure names its stage and why, in one line. Apply the same five-stage
pattern to every operation's stepper"). An operation declares its stages and which of its
steps fall under each (``((key, name, step keys), ...)``: the heal's in
`heal.run_card.heal_stage_table`, the re-subscribe's `run_card.RESUB_STAGES`); `stages` draws
a record card as them: each stage's state, time and sentence from its steps (its operation's
own sentence where it says one), its steps one level down, and a step's own sub-steps under it
(the deploy's stages inside a heal's Apply: "ONE stepper"). Every record card is drawn so;
every other operation's stepper keeps its rows until it declares its stages (C3163's rest).
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


def _read_line(r: dict) -> dict:
    state = str(r.get("result") or "")
    return {"what": str(r.get("check") or r.get("command") or ""), "state": state,
            "state_words": READ_WORDS.get(state, state or "not said"),
            "words": str(r.get("words") or ""), "at": str(r.get("at") or "")}


def reads_words(reads: list) -> str:
    """A step's reads in one line: how many, of what when they are of one command, about how
    far apart (the median gap between the reads of one check or command), how many passed,
    failed or could not be read, and the newest one's words."""
    reads = [r for r in reads or [] if isinstance(r, dict)]
    if not reads:
        return ""
    commands = {str(r.get("command") or "") for r in reads} - {""}
    keyed = {}
    for r in reads:
        keyed.setdefault(str(r.get("check") or r.get("command") or ""), []).append(
            _epoch(r.get("at")))
    gaps = sorted(b - a for ats in keyed.values()
                  for a, b in zip(ats, ats[1:]) if a is not None and b is not None)
    apart = f", about {round(gaps[len(gaps) // 2])} s apart" if gaps else ""
    counts = [(sum(1 for r in reads if r.get("result") == k), w)
              for k, w in (("pass", "pass"), ("fail", "fail"), ("unreadable", "unreadable"))]
    other = len(reads) - sum(n for n, _w in counts)
    said = ", ".join(f"{n} {w}" for n, w in counts + [(other, "not said")] if n)
    last = str(reads[-1].get("words") or "")
    return (f"{len(reads)} read{'s' if len(reads) != 1 else ''}"
            + (f" of `{next(iter(commands))}`" if len(commands) == 1 else "")
            + f"{apart}: {said}" + (f"; the last: {last}" if last else ""))


def _lines(event: dict, running: bool = False) -> tuple:
    """What a step read, compactly (a verify makes up to 120 reads: never one long expanded
    list on a card): ``(lines, reads)``.

    - *lines*, the few drawn in place (``{"what", "state", "state_words", "words", "at"}``):
      an ENDED step's final ``checks`` (``{name: {"state", "words"}}``: three for a verify);
      for a step still *running*, or one that keeps no checks, the NEWEST read of each check
      (a read's ``check``, else its ``command``); then, when the step kept reads, ONE line
      saying them (`reads_words`, its ``what`` empty and ``summary`` true).
    - *reads*: every read the step kept (``{"at", "command", "result", "words", "check"}``,
      a non-dict entry skipped), newest first, for a closed list one level down."""
    reads = [r for r in event.get("reads") or [] if isinstance(r, dict)] \
        if isinstance(event.get("reads"), list) else []
    checks = event.get("checks") if isinstance(event.get("checks"), dict) else {}
    out = []
    if checks and not running:
        for name, c in checks.items():
            if not isinstance(c, dict):
                continue
            state = {"cant_tell": "unreadable", "waiting": "fail"}.get(c.get("state"),
                                                                       str(c.get("state") or ""))
            out.append({"what": str(name), "state": state,
                        "state_words": READ_WORDS.get(state, state or "not said"),
                        "words": str(c.get("words") or ""), "at": str(event.get("at") or "")})
    elif reads:
        newest = {}
        for r in reads:
            newest[str(r.get("check") or r.get("command") or "")] = r
        out += [_read_line(r) for r in newest.values()]
    if reads:
        out.append({"what": "", "state": "", "state_words": "", "summary": True,
                    "words": reads_words(reads), "at": ""})
    return out, [_read_line(r) for r in reversed(reads)]


def _wait(event: dict, now: float, running: bool):
    """A step's declared wait, ``{"began", "length_s", "bound", "words"}``, or None: the
    length the operation declared (``wait_s``) and when the step began (``began``, else its
    ``at``). The countdown the page draws is of these two, sent by the server; ``words`` says
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
    # A fixed wait counts down its length; a bound (wait_bound) is the longest the step
    # waits, and it may end sooner.
    bound = bool(event.get("wait_bound"))
    return {"began": began, "length_s": n, "bound": bound,
            "words": ((f"up to {n} s: {left} s left" if bound else f"{left} s left of {n} s")
                      if running and left else
                      f"its {n} s are up; waiting for the next step" if running else
                      (f"waited up to {n} s" if bound else f"a wait of {n} s"))}


def labels_for(table: dict, **fields) -> dict:
    """An operation's short step labels (two to four words each, declared beside its steps:
    ``STEP_LABELS``) with this run's own names filled in (``{device}``, ``{subs}``)."""
    return {k: str(v).format(**fields) for k, v in (table or {}).items()}


def from_record(declared, steps, *, ended: bool, now: float = None, good=(), bad=(),
                conditional=(), prefix: str = "", cut_short: bool = False,
                labels: dict = None) -> dict:
    """A run's own recorded *steps* (``{"step", "result", "words", "at"}``, in the order they
    were written) against the steps it *declared* (``(key, words)``, in order): ``{"steps",
    "lead", "trail", "at", "of"}``.

    - ``steps``: one per declared step, for the stepper. Recorded: its worst record's state
      (a step still ``running`` is running only while it is the run's newest step and the run
      has not *ended*; one a later step followed is done, unless a later record of the same
      step says otherwise; a run that ended inside it failed there). Never recorded: pending
      while the run goes on; once it *ended*, not reached when a step before it failed or was
      not fully done, else not needed (also every step named in *conditional*, a rollback);
      with *cut_short* (a run that stopped without recording its end), every step after the
      last one it recorded is not reached.
    - ``lead``: the step to read first: the first failed one, else the running one, else
      (ended) the first not fully done; None when every step is done. A failed or partial
      lead carries ``why`` (each such record's own words: the failure, said once on the
      card); a running one what it is reading (``lines``, ``more``).
    - ``trail``: every step as recorded, in order, ONE line each: its state, its one-line
      outcome (left out for the step the lead already says), its time; and, under a step
      that did not pass, what it read (``checks``, ``more``), for a closed list.
    - *labels*: the operation's short label for each step (``{key: words}``, two to four
      words): the step's column says the label, its hover the declared words.
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
            elif cut_short and i > reached:
                state = "not_reached"               # the run stopped before it got here
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
            lines, more, why = [], [], []
            for j, (st, _n, e) in enumerate(got):
                of = f"{j + 1} of {len(got)}" if len(got) > 1 else ""
                said = str(e.get("words") or "")
                if st == "failed" and e.get("result") == "running":
                    said = (said + ". " if said else "") + "The run ended in this step"
                if st in ("failed", "partial") and said:
                    # Why, said ONCE on the card: under "Failed at", never again in the list.
                    why.append((f"{of}: " if of else "") + said)
                if st != "running":
                    continue
                # What a step still running is reading (the newest read of each check).
                if of:
                    lines.append({"what": of, "state": st, "state_words": STATE_WORDS[st],
                                  "words": said, "at": str(e.get("at") or "")})
                drawn, every = _lines(e, True)
                lines += drawn
                if every:
                    more.append({"title": f"The {len(every)} read"
                                          f"{'s' if len(every) != 1 else ''}"
                                          + (f" of {of}" if of else ""), "reads": every})
            extra = {"wait": wait, "lines": lines, "more": more, "why": why}
        # The column says the step in two to four words (the operation's own short label);
        # its long words are its hover, and the list below says what each step did.
        label = (labels or {}).get(k) or words[k]
        # What the step's newest record said, and when it began and last moved: a stage
        # (`stages`) lists its steps with these, one line each.
        said = str(got[-1][2].get("words") or "") if got else ""
        first_rec = got[0][2] if got else {}
        last_at = str(got[-1][2].get("at") or "") if got else ""
        # Only a running step carries what it is doing on its column (its hover, and under
        # it on a phone): a step that ended says its outcome ONCE, in the list below, and a
        # failed one in the lead.
        note = note if state == "running" else ""
        one = dict(step(prefix + k, label, state, took_s=took, note=note, since=since),
                   long=words[k], title=words[k] + (f": {note}" if note else ""),
                   state_words=STATE_WORDS[state], wait=extra.get("wait"),
                   lines=extra.get("lines") or [], more=extra.get("more") or [],
                   why=extra.get("why") or [], said=said, at=last_at,
                   began=str(first_rec.get("began") or first_rec.get("at") or ""))
        out.append(one)
    for want in ("failed", "running") + (("partial",) if ended else ()):
        lead = next((s for s in out if s["state"] == want), None)
        if lead:
            break
    # The steps taken: each recorded step ONE line (its state and its one-line outcome). The
    # step the lead says is not said again here; what a step that did not pass read (its
    # final checks, one line of its reads, every read one level further down) sits under
    # that step alone, closed. A step that passed shows no checks.
    said_above = (lead["key"][len(prefix):], lead["state"]) if lead and lead["why"] else None
    trail = []
    for n, s in enumerate(steps):
        st = state_of(n, s) or "done"
        key = str(s.get("step") or "")
        drawn, every = _lines(s, False) if st in ("failed", "partial") else ([], [])
        trail.append({"key": key, "step_key": prefix + key,
                      "words": (labels or {}).get(key) or words.get(key) or key or "a step",
                      "long": words.get(key) or "",
                      "state": st, "state_words": STATE_WORDS[st],
                      "said": "" if said_above == (key, st) else str(s.get("words") or ""),
                      "at": str(s.get("at") or ""),
                      "checks": drawn,
                      "more": ([{"title": f"The {len(every)} read"
                                          f"{'s' if len(every) != 1 else ''}",
                                 "reads": every}] if every else [])})
    at = keys.index(steps[newest]["step"]) + 1 if steps and steps[newest].get("step") in keys \
        else max(reached + 1, 0)
    return {"steps": out, "lead": lead, "trail": trail, "at": at, "of": len(keys)}


def current_words(declared, steps, labels: dict = None) -> str:
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
    said = (labels or {}).get(key) or words.get(key) or str(key or "a step")
    place = f" · step {keys.index(key) + 1} of {len(keys)}" if key in keys else ""
    return said + ("" if state == "running" else f": {STATE_WORDS[state]}") + place


#: A run's outcome level -> the least its row's group may be ("never green over a partial").
_LEVEL_GROUP = {"ok": "done", "warn": "partial", "danger": "failed"}


def record_card(name: str, label: str, phases: list, *, ended: bool, level: str = "",
                device: bool = True, href: str = "", detail: str = "", key: str = "",
                summarised: bool = False) -> dict:
    """A one-row card for a run drawn from its own record: *phases* are `from_record`'s
    answers, in order (a heal's decision, then its act; any other run has one). The row's group
    is its steps' worst, and never better than the outcome's *level* (``ok``, ``warn``,
    ``danger``) once the run *ended*. The card carries ``lead``, ``trail`` and ``ended``, which
    its operation's stages (`stages`) are drawn from: every record card is drawn as its stages
    (C3163). *summarised*: the card this is drawn on already says why the run failed, in its
    own summary (a result's red box, a row's cause), so the failed stage names the step and
    does not say the failure a second time."""
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
            "ended": ended, "summarised": bool(summarised)}


# ── Stages: progress, not mechanics ─────────────────────────────────────────────────────────

#: A stage's state in words, for a reader the colour does not reach.
STAGE_WORDS = {"done": "done", "running": "in progress", "waiting": "not started",
               "failed": "failed", "partial": "not fully done",
               "not_reached": "not reached: the run stopped before it",
               "skipped": "not needed in this run"}


def duration_words(seconds) -> str:
    """*seconds* as a person reads a duration: ``45 s``, ``4 min 12 s``, ``1 h 3 min``."""
    s = int(round(max(0.0, float(seconds or 0))))
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} min {s} s" if s else f"{m} min"
    h, m = divmod(m, 60)
    return f"{h} h {m} min" if m else f"{h} h"


def stage_state(states, ended: bool) -> str:
    """A stage's state from its steps' *states*: failed when one failed, in progress when one
    runs (or, before the run *ended*, when some are done and the rest pending: it is between
    two of them), not fully done when one is; done only when every step is done or not
    needed and one is done; pending when none has begun. Done is never drawn beside a step
    that is not."""
    st = set(states)
    if not st:
        return "skipped"
    for worst in ("failed", "running", "partial"):
        if worst in st:
            return worst
    if st <= {"done", "skipped"}:
        return "done" if "done" in st else "skipped"
    if st <= {"waiting", "skipped"}:
        return "waiting"
    if st <= {"not_reached", "skipped"}:
        return "not_reached"
    if not ended and "waiting" in st:
        return "running"
    return "partial"


def _stage_lead(steps: list, state: str):
    """The step a stage's sentence is about: its failed one, else its running one, else the
    one not fully done; for a stage between two steps, the next one pending."""
    for want in ("failed", "running", "partial"):
        got = next((s for s in steps if s["state"] == want), None)
        if got:
            return got
    if state == "running":
        return next((s for s in steps if s["state"] == "waiting"), None)
    return None


def _first_said(text: str) -> str:
    text = str(text or "").strip()
    return text[:1].upper() + text[1:] if text else ""


def _generic_sentence(g: dict, summarised: bool = False) -> str:
    """A stage's one plain sentence when its operation says none: what its last step said
    once done; the step it is on while it runs; the step that failed and why, in one line."""
    lead, state = g["lead"], g["state"]
    if state == "done":
        said = next((s["said"] for s in reversed(g["steps"]) if s.get("said")), "")
        return _first_said(said) or "Done"
    if state == "running":
        return f"{lead['words']}…" if lead else "In progress…"
    if state in ("failed", "partial"):
        why = "" if summarised else (
            (lead or {}).get("why") or [(lead or {}).get("said") or ""])[0]
        head = (lead or {}).get("words") or g["name"]
        return (f"{head} failed" if state == "failed" else f"{head} not fully done") + (
            f": {why}" if why else "")
    return {"waiting": "Not started yet", "not_reached": "Not reached: the run stopped before it",
            "skipped": "Not needed in this run"}[state]


def stages(card: dict, declared, *, ended: bool, now: float = None, sentence=None,
           nested: dict = None) -> dict:
    """*card* (`record_card`'s) drawn as its operation's STAGES (the operator, 2026-11-12:
    "TOO MANY STEPS: a person cares about progress, not mechanics. The stepper shows FIVE
    stages: Detected → Decided → Fixing → Checking → Done, each with one plain sentence, its
    time and its state (e.g. "Applying 3 lines to <device>…", "Waiting for <device>'s heartbeat:
    120 s left", "Healed and verified in 4 min 12 s"). Each stage expands to its detailed steps
    (today's labels, and the deploy's stages under Fixing). A failure names its stage and why,
    in one line. Apply the same five-stage pattern to every operation's stepper").

    *declared*: ``((key, name, step keys), ...)``, the operation's stages in order and the
    keys of the card's steps under each (as the card keys them: a phase's prefix included).
    A step no stage names joins the stage of the step before it, so nothing recorded is
    hidden; a stage with no step on this card (a Re-add's, which removes nothing) is left
    out. Each stage: its ``state`` from its steps (`stage_state`), when it began (``began``,
    its first step's) and how long it took once it ended (``took_words``), or since when it
    runs (``since``); its ``sentence``, the operation's own (*sentence*, called with the
    stage, may return "" for the generic one), else `_generic_sentence`; while it waits on a
    declared wait, that wait (``wait``, the page's countdown); and its ``steps``, each step's
    label, state, time and one-line outcome, with what a step that did not pass read
    (``read``: each such record's ``checks`` and ``more``) and, under a step *nested* names, that step's own sub-steps
    (``substeps``: the deploy's stages under a heal's Apply, C3160). The card carries ``stages``
    (and the place of the stage it is on, ``stage_at`` of ``stage_of``); the macro then draws
    them as its one stepper, a single row that wraps, in place of the row, the lead and the
    steps taken."""
    now = time.time() if now is None else now
    steps = list((card.get("rows") or [{}])[0].get("steps") or [])
    trail = card.get("trail") or []
    # A card that already says why its run failed (a result's red box, a row's cause:
    # `record_card`'s *summarised*): its failed stage names the step, and the why stays there.
    summarised = bool(card.get("summarised"))
    owner = {}
    for i, (_k, _n, keys) in enumerate(declared):
        for key in keys:
            owner.setdefault(key, i)
    groups, last = [[] for _ in declared], 0
    for s in steps:
        last = owner.get(s["key"], last)
        groups[last].append(s)
    # What each record of a step that did not pass read (a verify per subscription: each its
    # own checks), under that step alone.
    checked = {}
    for t in trail:
        if t.get("state") in ("failed", "partial") and (t.get("checks") or t.get("more")):
            checked.setdefault(t.get("step_key") or t.get("key"), []).append(t)
    out = []
    for (key, name, _keys), group in zip(declared, groups):
        if not group:
            continue
        drawn = []
        for s in group:
            got = checked.get(s["key"]) or []
            drawn.append(dict(s, read=[{"of": f"{i + 1} of {len(got)}" if len(got) > 1 else "",
                                        "checks": t.get("checks") or [],
                                        "more": t.get("more") or []}
                                       for i, t in enumerate(got)],
                              substeps=list((nested or {}).get(s["key"]) or [])))
        state = stage_state([s["state"] for s in drawn], ended)
        # Its steps are recorded in the order they ran, which need not be the declared one
        # (a heal saves before it reads its symptom): it began at the earliest of them.
        starts = sorted((e, iso) for iso in (s.get("began") or s.get("at") for s in drawn)
                        if iso for e in [_epoch(iso)] if e is not None)
        began = starts[0][1] if starts else ""
        ends = [e for e in (_epoch(s.get("at")) for s in drawn if s.get("at")) if e is not None]
        b = starts[0][0] if starts else None
        took = (max(ends) - b if state in ("done", "partial", "failed") and ends and b is not None
                else None)
        lead = _stage_lead(drawn, state)
        g = {"key": key, "name": name, "state": state, "state_words": STAGE_WORDS[state],
             "began": began, "took_s": (round(now - b) if state == "running" and b is not None
                                        else round(took) if took is not None else None),
             "took_words": duration_words(took) if took is not None and took >= 1 else "",
             "since": began if state == "running" else "",
             "lead": lead, "lead_key": (lead or {}).get("key") if state != "waiting" else "",
             "wait": ((lead or {}).get("wait") if state == "running"
                      and (lead or {}).get("state") == "running" else None),
             "steps": drawn, "sentence": ""}
        g["sentence"] = (sentence(g) if sentence else "") or _generic_sentence(g, summarised)
        if lead and lead["state"] in ("failed", "partial") and lead.get("said") and (
                summarised or lead["said"] in g["sentence"]):
            # Why, said ONCE: in the sentence, or the summary the card already draws (a
            # result's red box: *summarised*), never again on its step's line.
            lead["said"] = ""
        out.append(g)
    # Never green over a partial or a failure: once the run ended, its last stage is no better
    # than the run's own outcome (`record_card`'s row: its steps' worst, capped by its level).
    group = ((card.get("rows") or [{}])[0]).get("group")
    if ended and out and group in ("failed", "partial") and out[-1]["state"] == "done":
        out[-1].update(state=group, state_words=STAGE_WORDS[group], took_words="")
    at = next((i for i, g in enumerate(out) if g["state"] in ("failed", "running")), None)
    if at is None:
        at = next((i for i, g in enumerate(out) if g["state"] == "partial"), len(out) - 1)
    # The trail is kept for what counts it (the In progress row's "N steps recorded"); its
    # key into the stages was this function's alone.
    # Its *summarised* is spent here: the stages say what it decided.
    card = {k: v for k, v in card.items() if k != "summarised"}
    return dict(card, stages=out, stage_at=at + 1 if out else 0, stage_of=len(out),
                trail=[{k: v for k, v in t.items() if k != "step_key"} for t in trail])
