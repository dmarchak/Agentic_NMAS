"""What a later AI troubleshoot call would be sent of an incident's own record: the attempts
(``tried:<n>``) and the catalog it may propose from (``catalogue``), built here with no call
made, every person a stable label.

The operator's order (overnight item 6, 2026-11-12), which this module implements in part:
"AI troubleshooting, as designed: a background job; the AI proposes one catalog operation with
parameters; code validates it against intent and the guards; a person approves it; on failure
STOP with Retry with more information (cost shown first), Cancel or Hand over; a per-incident
cap of $1.00; a repeated failed proposal is flagged; payloads use stable labels. Settings ›
Background processes, AI mode Manual by default. Section 12's rule stays in force."

**Stable labels** (the operator, 2026-11-12: no email and no name in an AI payload): every
person in a part is `display_names.label` of their identity ("person-3f9a1c", the same for one
identity in every request), never the identity, never the name they set and never their
default name (the part before the "@"). Words recorded with a person in them are unnamed
(`unnamed`): each email-shaped identity labelled (`display_names.labelled`), and the display
name of each person the record names replaced by that person's label, word by word.

**Masked, then by kind.** Every text is masked (`redact.redact_payload`, by value and by
position). No configuration line is a part: an attempt says its operation, its parameters (a
device's name and subscription ids, which the catalog holds to their shapes), its outcome and
its run's own words. What leaves the host is the gateway's, which masks every byte again
(`redact.egress_payload`); this module sends nothing, calls no model and starts nothing.

A part names each attempt as the incident's record derives it (`incident.attempts`), so what
the model reads of what was tried is what the page draws, from the operations' own records.
"""

import logging

log = logging.getLogger(__name__)

#: Who a proposal came from, as a part says it.
SOURCE_WORDS = {"mercury": "Mercury's diagnosis", "ai": "an AI answer",
                "person": "a person's choice", "": "no proposal recorded"}


def unnamed(text, actors=()) -> str:
    """*text* with no person named in it (`display_names.unnamed`, the one home): each
    email-shaped identity labelled, and each of *actors*' display names (set or default)
    replaced by that actor's label where it stands as a word of its own."""
    from modules import display_names

    return display_names.unnamed(text, actors)


#: The intent steps in a few words each, for an incident's own catalogue (`catalogue_part` with
#: an incident): their parameters' shapes say the rest.
INTENT_WORDS = {"intent-edit": "Change the device's committed intent",
                "intent-deploy": "Deploy the device's committed intent (merge-only; a removal "
                                 "by its id from the deploy's preview)"}
#: The intent steps' parameters in short words, for an incident's own catalogue (the step
#: kinds' own words, `plan_engine.STEP_KINDS`, hold them whole; the plan engine holds each).
INTENT_TAKES = {
    "changes": ("1 to 32 changes as YAML text, each {path, before, after}: a dotted path of a "
                "field intent models (a list item by its name), the value now and the value it "
                "becomes ({__absent__: true} for none)"),
    "remove": "optional: at most 64 line ids from the deploy's preview to remove (Mode B)"}
#: A step's device parameter in an incident's own catalogue: always the incident's.
DEVICE_TAKES = "the incident's device"
#: The parameters an incident must name for a step taking them: its subscriptions.
NEEDS_SUBSCRIPTIONS = ("subscriptions", "subscription")


def _fits(key: str, op, incident, condition: str, fixes: dict) -> bool:
    """Whether the step *key* (*op*'s) can take its parameters from *incident*: one naming
    subscriptions only where the incident names some; a built-in command plan only where it
    fixes the incident's problem *condition* (the err-disable plan for an err-disabled port,
    whose interface and cause the problem gives). A reusable action people saved is offered
    as before (its own match is the problem's, `saved_plans`)."""
    from modules.heal import catalog

    names = {p.name for p in op.params}
    if names & set(NEEDS_SUBSCRIPTIONS) and not getattr(incident, "subscriptions", ()):
        return False
    if key in catalog.COMMAND_PLANS:
        return bool(condition) and condition in (fixes.get(key) or ())
    return True


def catalogue_part(incident=None, condition: str = "") -> list:
    """The operations a proposal may name, each with its parameters' shapes in words, as the
    catalog declares them (`catalog.entries`: its operations and the built-in command plans,
    C3757), and the plan engine's intent change and deploy (`plan_engine.FIX_ADMITTED`, each its
    step kind's own parameters, the incident and proposal the plan gives it left out): what the
    model is told it may propose, read from the code each time, never typed into a prompt.
    Each says its ``kind``: ``operation``, ``command_plan`` or ``intent_step``.

    With *incident* (and its problem's *condition*, `problem.classify`), only the steps that
    incident's device can take (`_fits`), the device parameter said once as the incident's,
    and the intent steps and their parameters in a few words (`INTENT_WORDS`, `INTENT_TAKES`):
    the request's fixed size kept
    inside its bound (the gate's measurement, 2026-11-15: the whole catalogue was 3,648
    characters of every request). Without one, everything, as before."""
    from modules import plan_engine as PE
    from modules.heal import catalog

    own = incident is not None
    fixes = catalog.capabilities() if own else {}

    def takes(p):
        return DEVICE_TAKES if own and p.name == "device" else p.takes

    out = [{"operation": op.key, "words": op.words,
            "kind": "command_plan" if catalog.is_command_plan(key) else "operation",
            "params": [{"name": p.name, "takes": takes(p)} for p in op.params]}
           for key, op in sorted(catalog.entries().items())
           if not own or _fits(key, op, incident, condition, fixes)]
    out += [{"operation": key, "words": (INTENT_WORDS.get(key) if own else None)
             or PE.STEP_KINDS[key].words, "kind": "intent_step",
             "params": [{"name": p.name, "takes": (INTENT_TAKES.get(p.name) if own else None)
                         or takes(p)} for p in PE.STEP_KINDS[key].params
                        if p.name not in ("incident", "proposal")]}
            for key in sorted(PE.FIX_ADMITTED)]
    return out


def tried_parts(incident, resolved: float = None, *, now: float = None) -> dict:
    """``{"state": "ok"|"incomplete", "parts", "error"}``: *incident*'s attempts as a call
    would be sent them, ``parts`` keyed ``tried:<n>``, each ``{"operation", "operation_words",
    "params", "outcome", "passed", "words", "approved_by", "verified", "proposed_by", "at"}``,
    every person a stable label. *incomplete* says what could not be read (`incident.attempts`)."""
    from modules import display_names
    from modules.fixit import incident as F
    from modules.heal import catalog
    from modules.redact import redact_payload

    got = F.attempts(incident, resolved, now=now)
    actors = sorted({a["actor"] for a in got["attempts"] if a["actor"]})
    parts = {}
    for a in got["attempts"]:
        op = catalog.entries().get(a["operation"])
        parts[f"tried:{a['n']}"] = {
            "operation": a["operation"], "operation_words": op.words if op else "",
            "params": dict(a["params"]), "outcome": a["outcome"], "passed": a["passed"],
            "words": unnamed(a["words"], actors),
            "approved_by": display_names.label(a["actor"]) if a["actor"] else "",
            "verified": a["actor_verified"],
            "proposed_by": SOURCE_WORDS.get(a["source"], a["source"]), "at": a["at"]}
    return {"state": got["state"], "parts": redact_payload(parts),
            "error": unnamed(got["error"], actors)}


def pack(incident, resolved: float = None, *, now: float = None) -> dict:
    """Every part this module builds for *incident*: ``{"state", "parts", "error"}``,
    ``parts`` holding each ``tried:<n>`` and the ``catalogue``."""
    got = tried_parts(incident, resolved, now=now)
    return {"state": got["state"], "parts": dict(got["parts"], catalogue=catalogue_part()),
            "error": got["error"]}
