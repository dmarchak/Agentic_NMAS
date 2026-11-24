"""The Incidents page's fleet view (the GUI redesign brief §4.2, 2026-11-18): category tiles with
their open count and a 30-day trend, the period's outcome strip ("N self-healed · N AI-fixed
(approved) · N person-fixed · N open"), and each row's category and autonomy (Self-heal, AI +
approval, Manual).

Built from the rows `incidents_list.held` already holds, so it reads no store and costs no
request a device, NetBox or a provider: a row's group (`incidents_list._group`) says how it
was fixed, its ``since`` when it was detected, and its incident's triggers its category. Display
only. A category Mercury's incident store does not hold (SDN and telemetry incidents are Needs
attention's rows today) is drawn as what it needs (C3943)."""

import datetime
import logging

log = logging.getLogger(__name__)

#: The period the strip and the trends cover.
WINDOW_DAYS = 30
#: Each category: (key, words, the trigger kinds it holds), in the order the tiles are drawn.
CATEGORIES = (("interfaces", "Interfaces", ("errdisable",)),
              ("routing", "Routing", ("adjacency", "adjacency_log", "duplicate_router_id")),
              ("drift", "Config drift", ("config_change", "drift")),
              ("alerts", "Alerts", ("alert",)),
              ("other", "Other", ()))
#: The brief's categories the incident store holds none of, each with what it needs.
NEEDS = {"SDN": "SDN incidents in the incident store (they are Needs attention's rows today)",
         "Telemetry": "lost telemetry streams as incidents (they are Needs attention's rows "
                      "today)"}
#: A closed row's group and the outcome it counts under.
OUTCOME_OF = {"fixed_mercury": "self_healed", "fixed_script": "self_healed",
              "fixed_ai": "ai_fixed", "fixed_person": "person_fixed",
              "fixed": "fixed_unknown", "cleared": "closed_unfixed",
              "cancelled": "closed_unfixed", "closed_unconfirmed": "closed_unfixed"}
#: The strip's outcomes, in order: (key, words). One with no incidents is not drawn, but for
#: the first four, which the brief names.
OUTCOMES = (("self_healed", "self-healed"), ("ai_fixed", "AI-fixed (approved)"),
            ("person_fixed", "person-fixed"), ("open", "open"),
            ("fixed_unknown", "fixed, who is not recorded"),
            ("closed_unfixed", "closed without a fix"))
ALWAYS = ("self_healed", "ai_fixed", "person_fixed", "open")
#: A row's autonomy: how its fix is (or was) made.
SELF, AI, MANUAL = "Self-heal", "AI + approval", "Manual"
AUTONOMY_OF = {"self_healed": SELF, "ai_fixed": AI, "person_fixed": MANUAL}


def category(incident) -> str:
    """The category key of an incident record (`heal.incidents`): its first symptom's kind,
    else its first trigger's; ``other`` for none it names (or no record, a step-log row)."""
    kinds = [t.get("kind") for t in (incident or {}).get("triggers") or []
             if isinstance(t, dict)]
    from modules.heal.incidents import SYMPTOM_KINDS
    ordered = [k for k in kinds if k in SYMPTOM_KINDS] + kinds
    for kind in ordered:
        for key, _words, held in CATEGORIES:
            if kind in held:
                return key
    return "other"


def autonomy(row: dict) -> str:
    """A row's autonomy badge: a closed row's by how it was fixed (none for one closed without
    a fix); an open row's AI + approval while the AI has a part in it, Manual while it needs a
    person, else Self-heal (Mercury working or watching)."""
    if row.get("resolved"):
        return AUTONOMY_OF.get(OUTCOME_OF.get(row.get("group"), ""), "")
    if row.get("ai"):
        return AI
    if row.get("group") == "needs_person":
        return MANUAL
    return SELF


def _epoch(stamp) -> float:
    try:
        return datetime.datetime.strptime(str(stamp)[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=datetime.timezone.utc).timestamp()
    except ValueError:
        return 0.0


def board(rows: list, now: float) -> dict:
    """``{"days", "outcomes", "tiles", "needs"}`` for every row of a network (both tabs).
    *outcomes* the strip, every open incident and the closed among those detected in the last
    `WINDOW_DAYS`: ``{"key", "words", "n"}``; *tiles* each category with an incident: ``{"key",
    "words", "open", "total", "trend"}``, *trend* the detections per day, oldest first,
    `WINDOW_DAYS` long;
    *needs* the brief's categories the store holds none of."""
    start = now - WINDOW_DAYS * 86400
    counts = {k: 0 for k, _w in OUTCOMES}
    tiles = {k: {"key": k, "words": w, "open": 0, "total": 0, "trend": [0] * WINDOW_DAYS}
             for k, w, _h in CATEGORIES}
    for r in rows:
        at = _epoch(r.get("since"))
        tile = tiles.get(r.get("category") or "other", tiles["other"])
        if not r.get("resolved"):
            # Open counts every open incident, as the tile does; the window bounds only the
            # closed outcomes and the trend (C4033: "0 open" beside the tab's "Open · 1").
            tile["open"] += 1
            counts["open"] += 1
        if at < start or at > now:
            continue
        tile["total"] += 1
        tile["trend"][min(WINDOW_DAYS - 1, int((at - start) // 86400))] += 1
        key = OUTCOME_OF.get(r.get("group"), "") if r.get("resolved") else ""
        if key:
            counts[key] += 1
    outcomes = [{"key": k, "words": w, "n": counts[k]} for k, w in OUTCOMES
                if counts[k] or k in ALWAYS]
    drawn = [t for t in tiles.values() if t["open"] or t["total"]]
    for t in drawn:
        t["peak"] = max(t["trend"]) or 1
    return {"days": WINDOW_DAYS, "outcomes": outcomes, "tiles": drawn, "needs": dict(NEEDS)}
