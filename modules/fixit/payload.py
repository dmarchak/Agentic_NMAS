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


def catalogue_part() -> list:
    """The operations a proposal may name, each with its parameters' shapes in words, as the
    catalog declares them (`catalog.CATALOG`): what the model is told it may propose."""
    from modules.heal import catalog

    return [{"operation": op.key, "words": op.words,
             "params": [{"name": p.name, "takes": p.takes} for p in op.params]}
            for _key, op in sorted(catalog.CATALOG.items())]


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
        op = catalog.CATALOG.get(a["operation"])
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
