"""Self-healing's fold window against Grafana's alert rules (the operator, 2026-11-08, after H11:
"warn if any alert rule's pending period plus evaluation interval exceeds the window").

A standing incident takes in a symptom on another device for `incidents.FOLD_STANDING_S`
(250 s) after its decision (C2813). An alert fires at the latest one evaluation interval after
its condition first holds plus its pending period (`for`): a rule whose pending period plus its
group's interval is past the window can fire after the window has closed, so its symptom is
judged on its own (a can't-fix of its own) where it belonged to the change that caused it.
H11's longest measured gap was 117 s (an IP SLA alert in W3's re-run), inside the window.

`check` judges Grafana's rules as the `grafana-alerts` reader stored them (its ``rules``: each
rule's ``for_seconds`` from the ruler and ``interval_seconds`` from its group in the rules
view), reading nothing else. Three states, never two:
- ``ok``: every rule's pending period plus interval is within the window;
- ``past``: the rules past it, each with both numbers, their sum and the window;
- ``unread``: rules whose numbers the stored read does not hold (a rule the ruler does not
  list, so its pending period is not known; a read stored before the reader kept the
  interval), each named. Unread is never "fine": its row says so, and clears at the next read
  that holds them.

Where it is drawn: one Needs attention row of the self-healing source (`attention.heal_source`,
`_heal_fold_rows`, kind ``heal``/``fold_window``) while self-healing is on for the network on
screen, naming each rule, both numbers and the window, and how it clears; with self-healing
off nothing folds, so nothing is checked, and the source says so. It is read on every page and
count (a startup included), from the reader's last read, never from Grafana.
Not counted: an absence rule's query window (a heartbeat rule looks back 750 s before its
condition holds), which the operator's formula leaves out (registered, C2869).
"""

import logging

log = logging.getLogger(__name__)


def _window() -> float:
    from modules.heal.incidents import FOLD_STANDING_S

    return float(FOLD_STANDING_S)


def check(value: dict, window: float = None) -> dict:
    """``{"state", "window", "past", "unread", "rules"}`` for the reader's stored *value*
    (`grafana_alerts.parse`'s): *past* and *unread* are lists of ``{"uid", "title", "group",
    "for_seconds", "interval_seconds", "total"}`` (an unread rule's missing number None);
    *rules* the count judged. *state*: ``past`` when any rule is past the window, else
    ``unread`` when any rule's numbers are not held, else ``ok``."""
    window = _window() if window is None else float(window)
    past, unread = [], []
    rules = list((value or {}).get("rules") or [])
    for r in rules:
        item = {"uid": r.get("uid"), "title": r.get("title") or r.get("uid") or "?",
                "group": r.get("group") or "", "for_seconds": None, "interval_seconds": None,
                "total": None}
        held_for = r.get("configured") is not False and isinstance(r.get("for_seconds"), int)
        held_interval = isinstance(r.get("interval_seconds"), int) and r["interval_seconds"] > 0
        if held_for:
            item["for_seconds"] = r["for_seconds"]
        if held_interval:
            item["interval_seconds"] = r["interval_seconds"]
        if not (held_for and held_interval):
            unread.append(item)
            continue
        item["total"] = item["for_seconds"] + item["interval_seconds"]
        if item["total"] > window:
            past.append(item)
    state = "past" if past else ("unread" if unread else "ok")
    return {"state": state, "window": window, "past": past, "unread": unread,
            "rules": len(rules)}


def words(item: dict, window: float) -> str:
    """One rule as the row names it: its title, both numbers, their sum and the window."""
    def n(v):
        return "not in the stored read" if v is None else f"{v} s"

    head = f"{item['title']}" + (f" ({item['group']})" if item.get("group") else "")
    if item.get("total") is None:
        return (f"{head}: pending period {n(item['for_seconds'])}, its group's evaluation "
                f"interval {n(item['interval_seconds'])}")
    return (f"{head}: pending period {item['for_seconds']} s plus its group's evaluation "
            f"interval {item['interval_seconds']} s is {item['total']} s, past the "
            f"{int(window)} s window")
