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
"""

import logging

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
STEP_STATES = ("done", "running", "waiting", "failed", "partial", "not_reached")


def step(key: str, words: str, state: str, *, took_s=None, note: str = "",
         since: str = "") -> dict:
    """One step on a row. *note*: what a running step waits on, or a failed step's reason."""
    if state not in STEP_STATES:
        raise ValueError(f"a step's state is one of {STEP_STATES}, not {state!r}")
    return {"key": key, "words": words, "state": state, "took_s": took_s, "note": note,
            "since": since}


def from_stepper(rows: list) -> list:
    """`device_actions.stepper`'s rows as this card's steps (its running step's note is what
    it waits on, and the last thing it did)."""
    out = []
    for s in rows or []:
        note = ""
        if s.get("state") == "running":
            note = f"waits on {s['waits']}" if s.get("waits") else ""
            if s.get("last"):
                note += f" (last done: {s['last']})"
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


def finished(steps: list, outcome: str) -> list:
    """*steps* as a finished row draws them: all done for a good outcome; for a failed one, the
    step it stopped in failed and the rest not reached."""
    if outcome in ("done", "partial"):
        last = len(steps) - 1
        return [dict(s, state=("partial" if outcome == "partial" and i == last else "done"))
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


def single(steps: list, name: str, label: str) -> dict:
    """A one-device operation's card: its one row from `device_actions.stepper`'s rows (a
    deploy, a restore, a reload, a rotation, an adoption, holding the device). The row runs
    while any step runs, is done once every step is, and waits before the first begins."""
    mine = from_stepper(steps)
    states = {s["state"] for s in mine}
    group = ("running" if "running" in states else "failed" if "failed" in states
             else "done" if mine and states == {"done"} else "waiting")
    return card([row(name, group, mine)], label=label, key=label.lower().replace(" ", "-"))


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
    tally = [{"group": g, "n": counts[g], "words": words[g], "kind": kinds[g]}
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
