"""The bottom line up front (the operator's R2, 2026-11-14; docs/MERCURY_CHARTER.md, "Two standing
rules"), keyed by PROBLEM (R4, "Incidents are problems, not signals"): every screen, card and
notification about an incident leads with three plain lines, drawn from THIS table and never
written by the AI:

1. **what** happened, in the engineer's words, titled by the problem ("edge1: telemetry streams 101
   and 102 lost"), never by the alert that raised it nor Mercury's codes (CONFIG_I, g4,
   cant_fix, "departs (-2)"); when it began is the ISO instant ``since``, which the page
   localises (never "UTC" words here);
2. the **impact** on the network or on Mercury ("Mercury can't see edge1's interfaces or CPU;
   traffic is unaffected");
3. how to **fix** it: the one next action (``approve``: the AI's or Mercury's proposal with
   Approve, Modify and Deny; ``button``: one operation's own control; ``start``: Start AI
   troubleshooting; ``hand_over``: Hand over to an engineer; ``none``: nothing is left to do).

The incident's **title** is the problem and its impact ("edge1: telemetry streams 101 and 102 lost:
Mercury can't see edge1's interfaces or CPU; traffic is unaffected"); the signals it was classified
from are listed under it as **evidence** (`problem.evidence`).

**One table, keyed by problem condition** (`TABLE`, the conditions of `modules/problem.py`),
each entry's words using only the problem's own fields (`problem.FIELDS`, as ``{device}``,
``{object}`` and the rest; tests/test_bluf.py parses this module for any other). Every signal
kind Mercury raises has its condition (`problem.CONDITION_OF`, over `problem.declared_signals`),
and every condition its what, impact and fix (`missing`; a planted kind is found).

**Severity follows impact** (`severity`): ``critical`` only for a network outage a reach or
datapath check MEASURED (an `OUTAGE_CAPABLE` condition with ``outage_measured`` in the model;
no entry claims an outage it did not measure); ``warning`` for a network degraded or Mercury unable to see or act (``degraded``,
``mercury``); ``info`` for nothing affected (``none``). The AI never sets it.

**A guard or hold working as designed is one plain line, never a failure** (`hold_line`, from
`HOLD_LINES`, one per guard of `heal.policy.GUARDS`), e.g. guard 4: "Self-healing won't write
to edge1 until its saved config matches intent (2 lines differ). This doesn't block the fix
below."

Reads nothing but what it is handed: no store, no device, no model.
"""

import string

from modules import problem as P

#: The next action's kinds, as the section's ``bluf.fix.kind`` says them.
FIX_KINDS = ("approve", "button", "hand_over", "start", "none")
#: The effect an entry's impact has, and the severity each gives (`severity`).
EFFECTS = {"outage": "critical", "degraded": "warning", "mercury": "warning", "none": "info"}


def _e(what: str, impact: str, fix: str, effect: str) -> dict:
    return {"what": what, "impact": impact, "fix": fix, "effect": effect}


#: THE table, by problem condition (`problem.CONDITIONS`): what (a template of the problem's
#: fields), impact, the next action's kind, and its effect. Plain words only.
TABLE = {
    "telemetry_lost": _e("{device}: {object} lost",
                         "Mercury can't see {device}'s interfaces or CPU; traffic is unaffected",
                         "approve", "mercury"),
    "neighbour_down": _e("{device}: {object} down",
                         "Routes through that neighbour are withdrawn: traffic between them stops "
                         "unless another path carries it", "approve", "degraded"),
    "neighbour_dropped": _e("{device}: {object} went down",
                            "Routes through that neighbour were withdrawn while it was down; "
                            "traffic reroutes where another path exists", "approve", "degraded"),
    "router_id_duplicate": _e("{device}: {object} is used by another router",
                              "OSPF may choose wrong routes or drop neighbours between the two "
                              "routers sharing the ID", "approve", "degraded"),
    "changed_outside_mercury": _e("{device}: {object} was changed outside Mercury",
                                  "{device} no longer matches its intent; traffic is affected "
                                  "only where the change touches it", "approve", "none"),
    "departs_from_golden": _e("{device}: {object} no longer matches its approved copy",
                              "{device} no longer matches its intent; traffic is affected only "
                              "where the difference touches it", "approve", "none"),
    "alert_unclassified": _e("{device}: {object} Mercury has not classified yet",
                             "Mercury cannot say yet what it affects; the AI names the problem",
                             "start", "degraded"),
    "line_missing": _e("{device}: {object} is missing",
                       "What that line sets up is off on {device} until it is put back",
                       "button", "degraded"),
    "line_changed": _e("{device}: {object} differs from its intent",
                       "{device} runs that line's new value, not the one intended", "button",
                       "degraded"),
    "line_added": _e("{device}: {object} was added",
                     "{device} runs a line nobody approved; traffic is affected only where it "
                     "touches it", "button", "degraded"),
    "interface_shut": _e("{device}: {object} is shut down, and its intent says up",
                         "Traffic over that interface stops; it reroutes only where another path "
                         "exists", "button", "degraded"),
    "security_broke_neighbour": _e("{device}: {object} on one side broke a neighbour",
                                   "The neighbour is down until the change is put back",
                                   "button", "degraded"),
    "needs_process_reset": _e("{device}: {object} takes effect only once its process resets",
                              "{device} runs the old behaviour until the process is reset",
                              "approve", "degraded"),
    "qos_changed": _e("{device}: {object} differs from its intent",
                      "Traffic on {device} is prioritised differently from what was intended",
                      "approve", "degraded"),
    "secret_changed": _e("{device}: {object} was changed",
                         "Whoever signs in with it may be refused or let in differently",
                         "approve", "degraded"),
    "acl_changed": _e("{device}: {object} was added or changed",
                      "Traffic the ACL matches is filtered differently from what was intended",
                      "approve", "degraded"),
    "security_changed": _e("{device}: {object} was changed outside intent",
                           "{device}'s protection differs from what was intended", "approve",
                           "degraded"),
    "link_down": _e("{device}: {object} is down while it is meant to be up",
                    "Traffic over that link stops; it reroutes only where another path exists",
                    "hand_over", "degraded"),
    "cause_unknown": _e("{device}: {object} is wrong, and its configuration matches intent",
                        "The cause is outside the configuration, so Mercury cannot say yet what "
                        "it affects", "approve", "degraded"),
    "account_changed": _e("{device}: {object} was changed",
                          "People or Mercury may be refused when they sign in to {device}",
                          "hand_over", "mercury"),
    "management_path_changed": _e("{device}: {object} was changed",
                                  "Mercury may lose its way to {device}; traffic through it is "
                                  "not affected by that alone", "hand_over", "mercury"),
    "multi_device_change": _e("{device}: {object}, {device} among them",
                              "Traffic between those devices may be affected; no single "
                              "device's fix can be checked alone", "hand_over", "degraded"),
    "port_stuck": _e("{device}: {object} stopped passing traffic",
                     "Traffic over that port stops until it is bounced", "button", "degraded"),
    "bgp_session_stuck": _e("{device}: {object} is stuck",
                            "Routes from that neighbour are stale or missing", "button",
                            "degraded"),
    "ospf_neighbour_stuck": _e("{device}: {object} is stuck",
                               "Routes through that neighbour are missing until it is reset",
                               "button", "degraded"),
    "port_flapping": _e("{device}: {object} keeps going up and down",
                        "Traffic over it drops each time it flaps", "approve", "degraded"),
}

#: A guard or hold working as designed, as one plain line (`hold_line`), by guard number
#: (`heal.policy.GUARDS`): what self-healing will not do, and whether the fix shown is blocked.
HOLD_LINES = {
    1: "Self-healing is switched off for the whole installation, so it writes to no device.",
    2: "Self-healing on {device}'s network is set to watch only, so it writes nothing by "
       "itself.",
    3: "Self-healing won't write to {device} during the planned work holding it.",
    4: "Self-healing won't write to {device} until its saved config matches intent ({lines} "
       "differ).",
    5: "Self-healing waits after a recent change near {device} before it writes.",
    6: "Self-healing won't write while many devices drift at once.",
    7: "Self-healing won't write to {device} while a person is working on it.",
    8: "Self-healing waits out its grace period before it writes to {device}.",
    9: "Self-healing has fixed {device} as often as it may this hour.",
    10: "Self-healing has fixed its network as often as it may this hour.",
    11: "Self-healing fixed this same difference on {device} twice, so it waits for a person.",
    12: "This fix is larger than self-healing may send by itself.",
    13: "This kind of fix is one a person approves; self-healing proposes it and sends nothing.",
    14: "Self-healing is halted on {device}'s network after a fix that didn't verify.",
}
#: Said after a hold's line when the fix shown is not one the hold stops.
NOT_BLOCKING = "This doesn't block the fix below."
#: Said when the hold is what refused a step of the fix shown at its preflight.
BLOCKING = "This blocks the fix below until it ends."


def declared_kinds() -> dict:
    """What the table must hold: ``{"signals", "conditions"}``, every signal kind Mercury raises
    (`problem.declared_signals`) and every problem condition they classify to."""
    signals = P.declared_signals()
    return {"signals": signals,
            "conditions": tuple(dict.fromkeys(P.CONDITION_OF.get(s, "") for s in signals))}


def placeholders(text: str) -> set:
    """The field names a template of the table names (``{device}`` and the like)."""
    return {name for _lit, name, _spec, _conv in string.Formatter().parse(text) if name}


def missing(table: dict = None) -> list:
    """``[(kind, why)]``: each declared signal with no condition, each condition *table* (THE
    `TABLE` by default) lacks or holds without its what, impact or fix, a fix or effect that is
    not a known one, and a template naming a field outside the problem's (`problem.FIELDS`)."""
    table = TABLE if table is None else table
    got = declared_kinds()
    out = [(s, "no problem condition") for s in got["signals"] if s not in P.CONDITION_OF]
    for cond in got["conditions"]:
        e = table.get(cond)
        if not cond:
            continue
        if not isinstance(e, dict):
            out.append((cond, "no entry"))
            continue
        for part in ("what", "impact", "fix"):
            if not str(e.get(part) or "").strip():
                out.append((cond, f"no {part}"))
        if e.get("fix") not in FIX_KINDS:
            out.append((cond, f"its fix {e.get('fix')!r} is not one of {FIX_KINDS}"))
        if e.get("effect") not in EFFECTS:
            out.append((cond, f"its effect {e.get('effect')!r} is not one of "
                              f"{tuple(EFFECTS)}"))
        for part in ("what", "impact"):
            extra = placeholders(str(e.get(part) or "")) - set(P.FIELDS)
            if extra:
                out.append((cond, f"its {part} names {sorted(extra)}, outside the problem's "
                                  "fields"))
    return out


def entry(condition: str) -> dict:
    """*condition*'s entry, or ``{}``."""
    return dict(TABLE.get(condition) or {})


#: The conditions that CAN be a network outage (traffic stopping somewhere), each critical
#: only once a reach or datapath check MEASURED the outage (*outage_measured*): until then
#: degraded, warning (the operator's R2: "critical only for a network outage"; the review of
#: 2026-11-14: severity is a claim about the world, measured).
OUTAGE_CAPABLE = ("neighbour_down", "interface_shut", "link_down", "port_stuck",
                  "ospf_neighbour_stuck", "security_broke_neighbour")


def severity(condition: str, *, outage_measured: bool = False) -> str:
    """``critical`` only for a network outage a reach or datapath check measured (an
    `OUTAGE_CAPABLE` condition with *outage_measured*), ``warning`` for a network degraded or
    Mercury unable to see or act, ``info`` for nothing affected; ``warning`` for a condition
    the table does not hold (never critical on a guess)."""
    if outage_measured is True and condition in OUTAGE_CAPABLE:
        return "critical"
    return EFFECTS.get(entry(condition).get("effect"), "warning")


def _fmt(text: str, problem: P.Problem) -> str:
    fields = problem.as_dict()
    fields["device"] = fields["device"] or "the device"
    return text.format(**fields)


def model_of(found: dict, nxt: dict = None) -> dict:
    """The BLUF's model of the incident `incident_page.resolve` *found*: its problem
    (`problem.classify`), when it began (``since``, an ISO instant: its first trigger's, else
    when it opened, else its step log's first row), the evidence (`problem.evidence`) and the
    next action *nxt*."""
    inc, e = found.get("incident") or {}, found.get("entry") or {}
    trig = [t for t in inc.get("triggers") or [] if isinstance(t, dict)]
    since = (trig[0].get("at") if trig else "") or ""
    if not since and trig and isinstance(trig[0].get("epoch"), (int, float)) \
            and trig[0]["epoch"] > 0:
        import time
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(trig[0]["epoch"])))
    since = since or inc.get("opened_at") or e.get("first_at") or ""
    return {"problem": P.classify(found), "since": str(since or ""),
            "evidence": P.evidence(found), "next": nxt}


def bluf(model: dict) -> dict:
    """The three lines for an incident *model* (`model_of`): ``{"what", "impact", "fix",
    "severity", "title", "since", "problem", "evidence"}``. Without a next action the fix is the
    table's own kind with no label. A problem the table does not hold says so plainly."""
    p = (model or {}).get("problem")
    if not isinstance(p, P.Problem):
        p = P.Problem(device=str((model or {}).get("device") or ""), object="something",
                      condition=str((model or {}).get("condition") or ""))
    e = entry(p.condition)
    nxt = (model or {}).get("next")
    if not isinstance(nxt, dict) or nxt.get("kind") not in FIX_KINDS:
        nxt = {"kind": e.get("fix") or "hand_over", "label": ""}
    base = {"fix": nxt, "since": str((model or {}).get("since") or ""), "problem": p.as_dict(),
            "evidence": list((model or {}).get("evidence") or [])}
    if not e:
        what = f"{p.device or 'A device'}: something happened"
        impact = ("Mercury has no plain description of this problem yet, so its impact is not "
                  "known")
        return dict(base, what=what, impact=impact, severity="warning", title=what)
    what, impact = _fmt(e["what"], p), _fmt(e["impact"], p)
    return dict(base, what=what, impact=impact, severity=severity(
        p.condition, outage_measured=(model or {}).get("outage_measured") is True),
                title=f"{what}: {impact}")


def hold_line(hit: dict, device: str, *, blocks: bool = False) -> str:
    """A guard or hold that applied, working as designed, as one plain line (`HOLD_LINES`):
    *hit* is the guard's own record (``{"guard", "operands"}``, `heal.guards.hit`). Guard 4
    counts the lines that differ from its operands (the departing lines and how many more).
    Unless the hold *blocks* the fix shown, the line ends `NOT_BLOCKING`. ``""`` for no hit."""
    if not isinstance(hit, dict) or not hit.get("guard"):
        return ""
    try:
        n = int(hit["guard"])
    except (TypeError, ValueError):
        return ""
    ops = hit.get("operands") or {}
    count = len(ops.get("lines") or []) + int(ops.get("lines_more") or 0)
    lines = f"{count} line{'s' if count != 1 else ''}" if count else "some lines"
    text = HOLD_LINES.get(n) or "Self-healing is holding {device}."
    text = text.format(device=device or "the device", lines=lines)
    return f"{text} {BLOCKING if blocks else NOT_BLOCKING}"
