"""The Self-healing tab's model (board H, artboard A; docs/HEAL_TO_INTENT.md sections 5 to 7,
9 and 10): what `templates/v2/_heal.html` draws for one network, read from
`modules/heal/policy.py` (the mode now, the kinds, the hard stops, the kill switch) and
`modules/heal_notify.py` (who is told). Reads only; every write is those modules'.

- `view(network)`: the tab at rest, its cards in the board's order;
- `change(network, part, form)`: the change card for one part (the mode, the fix kinds, or
  one hard stop), with the values as the form holds them;
- `preview(network, plan)`: a plan put into the card's What this changes table and its
  confirm button's words.
"""

import calendar
import logging
import time

log = logging.getLogger(__name__)

#: Each fix kind as the tab's table names it (board A), by tier.
KIND_LABELS = {
    "missing_line": "Missing line: re-apply intent's line (merge)",
    "changed_line": "Changed line: set intent's value (merge)",
    "added_line": "Added line: remove it (a measured shape, one removal unit; never a security "
                  "control)",
    # C2839's per-network question (no by default): Tier 1 only where the network says yes.
    "security_revert": "A one-sided security change that broke an adjacency: put it back (only "
                       "where the network allows it; no by default)",
    "admin_down": "Admin down where intent says up: no shutdown",
    "process_reset": "Takes effect through a process reset (router-id)",
    "qos_policy": "QoS policy",
    "secret_added_back": "A secret added back",
    # The actions H20 built (19.4): configuration unchanged, inside the device's revert timer.
    "port_bounce": "Port bounce: a port down while admin up, its far end up (an action)",
    "ospf_reset": "OSPF adjacency reset: the bounce on its one-neighbour interface (an action)",
    # The action H21 built (19.4, N16): one named BGP neighbour, a measured privileged clear;
    # Auto only on a network marked lab, a proposal elsewhere: in both policy lists, drawn
    # once at the tier its network gives it (`_kinds`).
    "session_clear": "BGP session clear: one named neighbour, not Established in two reads "
                     "(Auto only on a network marked lab; an action)",
    # The proposal H22 built (19.4): a change to intent, a person's; its Approve is refused on
    # a platform where its rollback (the `interface.dampening` removal) is not measured.
    "dampening_proposal": "Dampening: a port still flapping after its one bounce gains "
                          "`dampening` in intent (a person approves; a change to intent)",
}
#: The kinds that are never settings, drawn fixed with why (section 5): C2839's security kinds
#: (Tier 2, always proposed), and Tiers 3 and 4.
FIXED_KINDS = (
    ("A security control removed or changed outside intent · any ACL", 2, "Always proposed",
     "A person removes it (back to intent) or keeps it (adds it to intent), C2839"),
    ("Physical or link down while admin up; unknown cause", 3, "Alert only",
     "Configuration cannot fix a cable, an optic or a far end"),
    ("Credentials and AAA · Mercury's management path · multi-device", 4,
     "Never automatic", "Section 13's never list: a person changes these, never a heal"),
)
#: The hard stops in the board's order: (label, keys, how a value is said, the unit's words).
GUARD_ROWS = (
    ("Grace: a change must persist", ("heal_grace_seconds",), "{0} s"),
    ("Heals per device per hour", ("heal_max_per_device_hour",), "{0}"),
    ("Heals per network per hour", ("heal_max_per_network_hour",), "{0}"),
    ("The same fix twice halts, within", ("heal_repeat_halts_hours",), "{0} h"),
    ("Devices departing at once: stop above", ("heal_max_devices_drifting",), "{0}"),
    ("Hold after a change or re-cabling nearby", ("heal_topology_hold_minutes",), "{0} min"),
    ("A person working: outside changes",
     ("heal_person_working_changes", "heal_person_working_minutes"), "{0} in {1} min"),
    ("Largest heal", ("heal_max_removed_units", "heal_max_units"),
     "{0} removal unit (an added line; one feature on one interface, N13), or {1} section "
     "re-applied"),
    # The action guards (19.4, H19): 13e's flap, measured from the logs; 13d's once. No bounce
    # is built yet (H20), and the row says so rather than look like one that runs.
    ("A flap: transitions of one interface within",
     ("heal_flap_transitions", "heal_flap_minutes"), "{0} in {1} min"),
    ("A port is bounced at most", ("heal_bounce_per_port_hour",),
     "{0} an hour; a second need within the repeat window is a proposal (no bounce is built "
     "yet: H20)"),
)
#: The guards that are always on, never settings (section 6).
ALWAYS = (("Planned work, held devices, no-change windows", "always: never during them"),
          ("A rolled-back heal", "always halts the policy until a person lifts it"))
#: What each mode means, the tab's Mode row.
MODE_MEANS = {
    "off": "Off: nothing heals and nothing is recorded",
    "dry_run": "Dry run: every step but the apply. Each record says what it would have done",
    "auto": "Auto: the Tier 1 kinds allowed below heal without a person, then dry run at the "
            "expiry",
}
#: The mode chip: (words, colour) by the mode now.
MODE_CHIP = {"off": ("off", "neutral"), "dry_run": ("dry run", "info"), "auto": ("Auto", "ok")}
#: The parts a change card edits.
PARTS = ("mode", "kinds")
#: Production's bar (section 7, PHASE8_PLAN section 7): days, events and the wrong rate.
PRODUCTION_BAR = "30 days and 100 dry-run events, at 1% wrong or fewer"
#: What the tab draws of the mode now (`heal.policy.current`): its kinds and guards are drawn
#: from their own rows, and whether Auto expired or is suspended is said in its words and chip.
CUR_DRAWN = ("state", "error", "words", "mode", "set", "confirmed", "stage", "fingerprint",
             "until")
#: How many of the policy's own records the tab lists under History of this policy.
HISTORY_ROWS = 10


def utc_words(iso: str) -> str:
    """``2026-11-20T18:00:00Z`` as the tab says it, ``20 Nov 18:00 UTC``; anything else as it
    is."""
    try:
        t = time.strptime(str(iso), "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        return str(iso or "")
    return f"{t.tm_mday} {time.strftime('%b %H:%M', t)} UTC"


def parse_until(text: str) -> str:
    """AUTO's expiry as typed (``2026-11-20 18:00 UTC``, ``2026-11-20 18:00``, or the stored
    ``2026-11-20T18:00:00Z``) as the policy keeps it; anything else is returned as typed, so
    the policy's refusal names it."""
    raw = " ".join(str(text or "").split())
    if raw.upper().endswith("UTC"):
        raw = raw[:-3].strip()
    if raw.endswith("Z"):
        raw = raw[:-1]
    raw = raw.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            epoch = calendar.timegm(time.strptime(raw, fmt))
        except ValueError:
            continue
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))
    return str(text or "").strip()


def _guard_value(row, values: dict) -> str:
    _label, keys, fmt = row
    return fmt.format(*[values.get(k) for k in keys])


def _guards(cur: dict, lab: bool) -> list:
    from modules.heal import policy as H
    from modules.settings_schema import DEFAULTS

    rows = []
    g = cur.get("guards") or {}
    for row in GUARD_ROWS:
        label, keys, _fmt = row
        now = {k: (g.get(k) or {}).get("value", DEFAULTS.get(k)) for k in keys}
        default = _guard_value(row, {k: DEFAULTS.get(k) for k in keys})
        lab_vals = {k: H.LAB_DEFAULTS.get(k, DEFAULTS.get(k)) for k in keys}
        if any(k in H.LAB_DEFAULTS for k in keys):
            default += f" ({_guard_value(row, lab_vals)} on a lab network)"
        sources = sorted({(g.get(k) or {}).get("source", "default") for k in keys})
        rows.append({"label": label, "keys": keys, "value": _guard_value(row, now),
                     "default": default, "source": ", ".join(sources), "part": keys[0],
                     "values": now})
    return rows


#: Each tier's policy list: (the current policy's key, the form's field, on and off words).
KIND_LISTS = {1: ("kinds_auto", "heal_kinds_auto", "Heal", "Dry run only"),
              2: ("kinds_propose", "heal_kinds_propose", "Propose", "Alert only")}


def _kinds(cur: dict, lab: bool) -> list:
    """One row per kind, at the tier this network gives it (`actions.tier_of`): a kind in
    both policy lists (the BGP session clear) is drawn once, Tier 1 on a network marked lab
    and Tier 2 elsewhere, and its setting in the other list is carried unchanged (``keep``,
    the other list's form field when the kind is on there)."""
    from modules.heal import actions
    from modules.heal import policy as H

    both = set(H.TIER1_KINDS) & set(H.TIER2_KINDS)
    rows = []
    for tier, kinds in ((1, H.TIER1_KINDS), (2, H.TIER2_KINDS)):
        key, _field, on_words, off_words = KIND_LISTS[tier]
        other_key, other_field = KIND_LISTS[3 - tier][:2]
        for k in kinds:
            if k in both and actions.tier_of(k, lab) != tier:
                continue
            keep = other_field if k in both and k in cur.get(other_key, []) else ""
            rows.append({"kind": k, "label": KIND_LABELS[k], "tier": tier,
                         "on": k in cur.get(key, []), "on_words": on_words,
                         "off_words": off_words, "keep": keep})
    return rows


def _chip(cur: dict) -> tuple:
    if cur["stopped"]["stopped"]:
        return ("stopped everywhere", "danger")
    if cur["state"] != "ok":
        return ("cannot be read: off", "danger")
    if cur["set"] not in ("", "off") and cur["confirmed"].get("fingerprint") != cur["fingerprint"]:
        return ("not in force: off", "warn")
    if cur["mode"] == "dry_run" and cur["set"] == "auto":
        return ("dry run (Auto " + ("expired" if cur["expired"] else "suspended") + ")", "warn")
    return MODE_CHIP.get(cur["mode"], (cur["mode"], "neutral"))


def _history(network: str) -> dict:
    """The policy's own records, newest first: Turn off, each confirmed change, AUTO's
    expiry, and Who is told's saves."""
    from modules import heal_notify
    from modules import list_settings as L
    from modules.heal import policy as H

    got = L.changes(network)
    kinds = H.RECORD_KINDS + (heal_notify.RECORD_KIND,)
    rows = [{"kind": r.get("kind", ""), "at": r.get("at", ""),
             "who": r.get("actor_label") or r.get("actor", ""), "before": r.get("before", ""),
             "mode": r.get("mode", ""), "until": r.get("until", ""),
             "policy_fingerprint": r.get("policy_fingerprint", ""),
             "reason": r.get("reason", "")}
            for r in got.get("rows") or [] if r.get("kind") in kinds][:HISTORY_ROWS]
    return {"state": got["state"], "error": got.get("error", ""), "rows": rows}


#: What each answer drawn in the tab carries: only the parts it says.
ANSWER_KEYS = {"saved": ("mode", "until", "policy_fingerprint", "changes", "recorded", "at"),
               "off": ("nothing", "words", "recorded", "at"),
               "told_saved": ("nothing", "team_name", "events", "recorded", "at"),
               "stopped_now": ("nothing", "words", "recorded", "at"),
               "resumed": ("recorded", "at")}


def answer(kind: str, out: dict) -> dict:
    """An action's answer as the tab draws it (`ANSWER_KEYS`)."""
    return {k: out.get(k) for k in ANSWER_KEYS[kind]}


def resuming(plan: dict, confirm: dict, reason: str = "") -> dict:
    """The resume card: each network's mode once resumed, the fingerprint its confirm sends,
    why, who is confirming, and the reason typed."""
    return {"networks": [{"network": n["network"], "mode": n["mode"], "words": n["words"]}
                         for n in plan["networks"]],
            "fingerprint": plan["fingerprint"], "why": plan["why"],
            "statement": confirm.get("statement", ""), "reason": reason}


def six_parts(pv: dict) -> dict:
    """The preview's six parts as `_preview_parts.html` draws them, one level down."""
    t = (pv.get("targets") or [{}])[0]
    prog = t.get("program") or {}
    return {"what": {"summary": (pv.get("what") or {}).get("summary", "")},
            "action": pv.get("action", ""), "titles": pv.get("titles") or {},
            "explain": pv.get("explain") or {},
            "what_not": {"items": [{"text": w.get("text", ""), "lines": w.get("lines") or []}
                                   for w in (pv.get("what_not") or {}).get("items") or []]},
            "targets": [{"name": t.get("name", ""),
                         "program": {"lines": prog.get("lines") or [],
                                     "unit": prog.get("unit", ""), "none": prog.get("none", ""),
                                     "notes": prog.get("notes") or []},
                         "operands": t.get("operands") or [], "gates": t.get("gates") or []}],
            "confirm": {"statement": (pv.get("confirm") or {}).get("statement", "")}}


def _analysis(network: str, now: float = None) -> dict:
    """The AI analysis of a can't-fix as the tab's Who is told says it (C2647), from the
    background feature's own state on *network* (`background.switches`, never the record of AI
    calls): ``{"state", "badge", "level", "words"}``, *state* ``off``, ``ended`` (its approval
    ran out), ``capped`` (its newest analysis stopped at a cap whose period lasts), ``ai_off``
    (on, but hosted AI is off) or ``on``, with who turned it on and when, its caps and when
    its approval ends; ``unreadable`` when the switch cannot be read."""
    from modules.ai import background, gateway
    from modules.ai import heal_analysis as HA
    from modules.nsot import listref

    try:
        slug = listref.network_id(network)
        entry = background.switches().get(slug, {}).get(HA.FEATURE)
    except Exception as exc:                          # said in place, never raised
        return {"state": "unreadable", "badge": "unknown", "level": "warn",
                "words": f"its switch cannot be read ({type(exc).__name__}: {exc})"}
    if not (isinstance(entry, dict) and entry.get("on") is True):
        return {"state": "off", "badge": f"off for {network}", "level": "muted",
                "words": ("an admin turns it on in Settings › Installation › AI, after its "
                          "estimate; until then a can't-fix is told without an analysis")}
    who = (f"turned on by {entry.get('by') or 'an unrecorded admin'} "
           f"{utc_words(entry.get('at') or '') or 'at an unrecorded time'}")
    if not background.in_force(entry):
        return {"state": "ended", "badge": "approval ended", "level": "warn",
                "words": (f"{who}; its {background.APPROVAL_DAYS}-day approval has ended, so "
                          "nothing is analysed until an admin turns it on again")}
    caps = background.caps_of(entry)
    cap_words = ", ".join(f"${v:.2f} a {k}" for k, v in (("day", caps["day"]),
                                                        ("month", caps["month"])) if v)
    ends = background.approval_ends(entry)
    tail = (f"{who}; caps {cap_words or 'not readable (it refuses)'}; approval ends "
            f"{utc_words(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(ends)))}; "
            f"{HA.beta()['label']}, {HA.beta()['words']}")
    if not gateway.hosted_allowed()["allowed"]:
        return {"state": "ai_off", "badge": "on, hosted AI off", "level": "warn",
                "words": f"{tail}. Hosted AI is off, so nothing is analysed until an admin "
                         "allows it"}
    try:
        stopped = HA.capped(network, now=now)
    except Exception as exc:                          # said in place
        stopped = {"words": f"its record cannot be read ({type(exc).__name__})"}
    if stopped:
        return {"state": "capped", "badge": "stopped at its cap", "level": "warn",
                "words": f"{stopped.get('words') or 'its cap is reached'}; {tail}"}
    return {"state": "on", "badge": f"on for {network}", "level": "ok", "words": tail}


def view(network: str, now: float = None) -> dict:
    """Everything the tab draws for *network* at rest."""
    from modules import heal_notify
    from modules.heal import policy as H
    from modules.notify import teams
    from modules.sdn import modes as sdn_modes

    cur = H.current(network, now)
    lab = cur["stage"].get("stage") == sdn_modes.AUTO_STAGE
    told = heal_notify.read(network)
    store = teams.read()
    team = store["teams"].get(told["team"]) if told["team"] else None
    team_words = ""
    if team is not None:
        dests = (team.get("destinations") or {}).values()
        mails = sum(1 for d in dests if d.get("channel") == "email")
        hooks = sum(1 for d in dests if d.get("channel") == "webhook")
        team_words = (f"{mails} address{'es' if mails != 1 else ''}, {hooks} webhook"
                      f"{'s' if hooks != 1 else ''}")
    return {
        "network": network, "cur": {k: cur[k] for k in CUR_DRAWN},
        "chip": _chip(cur), "means": MODE_MEANS.get(cur["mode"], ""),
        "until_words": utc_words(cur["until"]) if cur["until"] else "",
        "confirmed_words": utc_words(cur["confirmed"].get("at", "")),
        "kinds": _kinds(cur, lab), "fixed": FIXED_KINDS, "guards": _guards(cur, lab),
        "always": ALWAYS, "bar": PRODUCTION_BAR, "stopped": cur["stopped"],
        "told": told, "told_loaded": heal_notify.drawn(told), "choices": heal_notify.CHOICES,
        "teams": [{"id": k, "name": t.get("name", "")}
                  for k, t in sorted(store["teams"].items(),
                                     key=lambda kv: kv[1].get("name", "").lower())],
        "teams_state": store["state"], "teams_error": store["error"],
        "team": ({"id": told["team"], "name": team.get("name", ""), "words": team_words}
                 if team is not None else None),
        "team_missing": bool(told["team"]) and team is None,
        "history": _history(network),
        "analysis": _analysis(network, now),
    }


def change(network: str, part: str, form=None) -> dict:
    """The change card for *part* (``mode``, ``kinds`` or a hard stop's first key), with the
    values the form holds (the stored ones when it holds none)."""
    from modules.heal import policy as H

    form = form or {}
    v = view(network)
    cur = v["cur"]
    guard = next((g for g in v["guards"] if g["part"] == part), None)
    if part not in PARTS and guard is None:
        raise H.PolicyRefused(f"{part!r} is not a part of the heal policy a card changes: "
                              f"{', '.join(PARTS)}, or a hard stop "
                              f"({', '.join(g['part'] for g in v['guards'])})")
    mode = form.get(H.MODE_KEY) or cur["set"] or "off"
    until = form.get(H.UNTIL_KEY)
    if until is None:
        until = utc_words(cur["until"]) if cur["until"] else ""
    if guard is not None:
        guard = dict(guard, values={k: form.get(k, guard["values"][k]) for k in guard["keys"]})
    kinds = v["kinds"]
    if form.get(H.KINDS_AUTO_KEY) is not None or form.get(H.KINDS_PROPOSE_KEY) is not None:
        auto = _sent_list(form, H.KINDS_AUTO_KEY)
        propose = _sent_list(form, H.KINDS_PROPOSE_KEY)
        kinds = [dict(k, on=k["kind"] in (auto if k["tier"] == 1 else propose)) for k in kinds]
    return dict(v, part=part, guard=guard, mode=mode, until=until, kinds=kinds,
                guard_words=dict(H.GUARD_WORDS),
                auto_refused=_auto_refusal(network),
                reason=form.get("reason", ""))


def _sent_list(form, key) -> list:
    """A list field as the form sent it (one value per item, beside an empty one)."""
    items = form.getlist(key) if hasattr(form, "getlist") else (form.get(key) or [])
    return [i for i in items if i]


def _auto_refusal(network: str) -> str:
    from modules.sdn import modes as sdn_modes

    return sdn_modes.auto_refusal(network)


def _mode_words(mode: str, until: str) -> str:
    if mode == "auto":
        return f"Auto until {utc_words(until)}, then dry run" if until else "Auto"
    return {"off": "Off", "dry_run": "Dry run"}.get(mode, str(mode))


def _kinds_words(kinds) -> str:
    return "; ".join(KIND_LABELS.get(k, k).split(":")[0] for k in kinds) or "none"


def preview(network: str, p: dict, part: str) -> dict:
    """The plan *p* (`heal.policy.plan`) as the change card's What this changes table, its
    refusals and its confirm button's words."""
    from modules.heal import policy as H

    b, a = p["before"], p["after"]
    heal_b = b.get(H.KINDS_AUTO_KEY) if b.get(H.MODE_KEY) == "auto" else []
    heal_a = a.get(H.KINDS_AUTO_KEY) if a.get(H.MODE_KEY) == "auto" else []
    rows = [{"where": "Mode", "now": _mode_words(b.get(H.MODE_KEY), b.get(H.UNTIL_KEY)),
             "after": _mode_words(a.get(H.MODE_KEY), a.get(H.UNTIL_KEY))},
            {"where": "Kinds that heal without a person", "now": _kinds_words(heal_b),
             "after": _kinds_words(heal_a)},
            {"where": "Kinds proposed to a person",
             "now": _kinds_words(b.get(H.KINDS_PROPOSE_KEY)),
             "after": _kinds_words(a.get(H.KINDS_PROPOSE_KEY))}]
    for label, keys, fmt in GUARD_ROWS:
        if any(b.get(k) != a.get(k) for k in keys):
            rows.append({"where": label, "now": fmt.format(*[b.get(k) for k in keys]),
                         "after": fmt.format(*[a.get(k) for k in keys])})
    for r in rows:
        r["same"] = r["now"] == r["after"]
    refusals = [f"{g['name']}: {g['why']}" for g in p["gates"] if g["state"] == "fail"]
    mode = a.get(H.MODE_KEY)
    # The confirm's words name its work; the template words each kind (`button`).
    if part == "kinds":
        button = "kinds"
    elif part != "mode":
        button = "guard"
    else:
        button = mode if mode in H.MODES else "off"
    return {"rows": rows, "refusals": refusals, "button": button, "auto": mode == "auto",
            "guard_label": next((r[0] for r in GUARD_ROWS if r[1][0] == part), part),
            "until_words": utc_words(a.get(H.UNTIL_KEY)) if a.get(H.UNTIL_KEY) else "",
            "confirmable": p["confirmable"], "fingerprint": p["fingerprint"],
            "operands": p["operands"],
            "stopped": {"stopped": p["stopped"]["stopped"], "words": p["stopped"]["words"]}}
