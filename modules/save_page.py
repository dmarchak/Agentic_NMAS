"""The Save page's cards (C593, board C, approved 2026-10-04): what Save would do for a
selection, before it runs; the run, in place, as each device ends; the result. Shaped from
`modules.nsot.save_op` only, so the page draws what the job does and nothing it guesses.

Board C led with "N not saved: startup differs". Nothing measures that: the hourly startup
check compares the `username` lines only. The summary says what IS measured (whether each
device's accounts are in startup, at the check's last reading) and says that the rest of startup
is not compared, so every device in the selection is saved whatever the check read.
"""

import logging

log = logging.getLogger(__name__)

#: The plan's groups as the page names them: (key, words, chip kind).
PLAN_GROUPS = (
    ("save", "to save", "info"),
    ("not_answering", "not answering: left out", "warn"),
    ("held", "held by another operation: left out", "warn"),
    ("refused", "cannot be saved from here: left out", "danger"),
)
#: What the hourly check last read of a device about to be saved: (key, words).
STARTUP_GROUPS = (
    ("not_persisted", "accounts not in startup"),
    ("persisted", "accounts in startup"),
    ("unknown", "the check could not read"),
    ("never", "not checked yet"),
)
#: A run's outcomes as the page names them: (key, words, chip kind), the ones to act on first.
OUTCOME_WORDS = (
    ("not_persisted", "saved; the read-back did not match: not recorded", "danger"),
    ("unread", "saved; not recorded", "danger"),
    ("held", "held by another operation", "warn"),
    ("not_answering", "not answering", "warn"),
    ("refused", "cannot be saved from here", "danger"),
    ("saved_recorded", "saved and recorded", "ok"),
    ("saved_unchanged", "saved; its golden already matched", "ok"),
)
#: What a running device is doing, as the card groups it.
LIVE_GROUPS = (("not_persisted", "failed"), ("unread", "failed"), ("held", "failed"),
               ("running", "running"), ("waiting", "waiting"), ("through", "through"),
               ("saved_recorded", "through"), ("saved_unchanged", "through"))
#: The run's groups, in the order the card leads with: what to act on, then what moves.
LIVE_ORDER = (("failed", "failed", "danger"), ("running", "running", "info"),
              ("waiting", "waiting their turn", "muted"),
              ("through", "through their turn, waiting for the commit", "ok"))
#: From this many devices the run's rows group and collapse, with Find a device above them;
#: fewer read at a glance, every row on its stepper (board C605, approved 2026-10-09).
SEARCH_FROM = 25


def _run_row(list_name: str, host: str, row: dict, now: float) -> dict:
    """One device's row on the run's stepper (`device_actions.stepper` over
    `save_op.DEVICE_STEPS`): read from its hold while it holds one, else from the trail it
    reached. A device that failed shows the step it stopped in as failed."""
    from modules import device_actions
    from modules.nsot import device_ops, save_op

    state, trail = row["state"], row.get("trail") or []
    if state == "running":
        held = ((device_ops.holder(list_name, host) or {}).get("progress") or {}).get("trail")
        trail = [[n, a] for n, a in held or [] if n in save_op._STEP_NAMES] or trail
    group = dict(LIVE_GROUPS).get(state, "running")
    steps = []
    if trail or state == "running":
        steps = device_actions.stepper(save_op.DEVICE_STEPS, {"trail": trail} if trail else None,
                                       now=now, starts=True)
    if state in save_op.GOOD:
        steps = [dict(s, state="done") for s in steps]
    elif group == "failed":
        steps = [dict(s, state="failed") if s["state"] == "running" else s for s in steps]
    started = trail[0][1] if trail else None
    return {"host": host, "state": state, "group": group, "steps": steps,
            "detail": row.get("detail", ""),
            "elapsed_s": round(max(0.0, now - started)) if started else None}
#: Outcomes a retry may help: the device answered nothing it should have, or was busy.
RETRYABLE = ("not_persisted", "unread", "held", "not_answering")


def plan_card(list_name: str, hostnames: list, *, may: dict) -> dict:
    """The plan as the page draws it: ``{"state": "plan", "counts", "groups", "startup",
    "hash", "save", ...}``. Reads stored records only (`save_op.plan`)."""
    from modules.nsot import save_op

    p = save_op.plan(list_name, hostnames)
    by_group = {key: [d for d in p["devices"] if d["group"] == key] for key, _w, _k in PLAN_GROUPS}
    to_save = by_group["save"]
    startup = [(key, words, [d["host"] for d in to_save if d["startup"] == key])
               for key, words in STARTUP_GROUPS]
    return {"state": "plan" if hostnames else "empty", "list": list_name,
            "total": len(p["devices"]), "save": p["save"], "hash": p["hash"],
            "fleet": p["fleet"], "may": may,
            "groups": [{"key": key, "words": words, "kind": kind, "devices": by_group[key]}
                       for key, words, kind in PLAN_GROUPS if by_group[key]],
            "startup": [s for s in startup if s[2]],
            "startup_unreadable": p["startup_unreadable"]}


def _filtered(rows: list, q: str, outcome: str) -> list:
    q = (q or "").strip().lower()
    return [r for r in rows if (not q or q in r["host"].lower())
            and (not outcome or r["outcome"] == outcome)]


def job_card(list_name: str, job_id: str, got, *, q: str = "", outcome: str = "") -> dict:
    """The run's card from its job (`capture_job.get`, or None): running, with each device's
    state as `save_op.live` holds it; the result, grouped by outcome; or why there is none.
    *q* and *outcome* filter the groups drawn (never the counts)."""
    from modules.nsot import save_op

    card = {"list": list_name, "job": job_id, "q": q, "outcome": outcome}
    if got is None:
        return dict(card, state="unknown")
    if got["state"] == "running":
        import time

        now = time.time()
        rows = [_run_row(list_name, h, r, now) for h, r in save_op.live(job_id).items()]
        counts = {name: sum(1 for r in rows if r["group"] == name) for name, _w, _k in LIVE_ORDER}
        total = len(rows)
        shown = [r for r in rows if not q or q.strip().lower() in r["host"].lower()]
        groups = [{"name": name, "words": words, "kind": kind, "count": counts[name],
                   "rows": [r for r in shown if r["group"] == name],
                   "open": name in ("failed", "running")}
                  for name, words, kind in LIVE_ORDER if counts[name]]
        return dict(card, state="running", elapsed_s=got.get("elapsed_s"),
                    started_at=got.get("started_at"), total=total, counts=counts, rows=rows,
                    groups=groups, grouped=total >= SEARCH_FROM, cap=save_op.WORKERS,
                    # The commit is the run's own last row: it waits for every device's turn.
                    committing=total > 0 and not counts["running"] and not counts["waiting"])
    if got["state"] == "failed":
        return dict(card, state="failed", error=got.get("error") or "no reason was recorded")
    payload = got.get("payload") or {}
    if payload.get("state") == "refused":
        return dict(card, state="refused", error=payload.get("detail", ""))
    rows = payload.get("outcomes") or []
    words = {k: (w, kind) for k, w, kind in OUTCOME_WORDS}
    groups = []
    for key, w, kind in OUTCOME_WORDS:
        members = [r for r in rows if r["outcome"] == key]
        if members:
            groups.append({"key": key, "words": w, "kind": kind, "count": len(members),
                           "devices": _filtered(members, q, outcome),
                           "open": kind != "ok"})
    good = sum(1 for r in rows if r["outcome"] in save_op.GOOD)
    retry = [r["host"] for r in rows if r["outcome"] in RETRYABLE]
    level = {"done": "ok", "partial": "warn"}.get(payload.get("state"), "danger")
    save = payload.get("save") or {}
    return dict(card, state="result", level=level, total=len(rows), good=good,
                bad=len(rows) - good, words=words, groups=groups,
                chip={"done": "done", "partial": "partial"}.get(payload.get("state"), "failed"),
                commit=payload.get("commit", ""), baseline=save.get("baseline"),
                # The whole network's Save asks for a baseline; the result says what the
                # measurement decided, earned or the reasons it was not.
                fleet=bool(payload.get("fleet")),
                baseline_denied=[str(r) for r in save.get("baseline_denied") or []],
                source=save_op.SOURCE_FLEET if payload.get("fleet") else save_op.SOURCE,
                decision_only=bool(save.get("decision_only")),
                record_error=save.get("error", "") if save and not save.get("ok") else "",
                retry=retry, outcomes=[(k, w) for k, w, _kind in OUTCOME_WORDS])
