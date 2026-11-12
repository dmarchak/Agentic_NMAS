"""A proposal in an incident, checked by code before any person sees an Approve: whoever made it
(Mercury's own diagnosis, a model's answer, a person's choice), held to Mercury's catalog, to
what the incident names, to the heal guards and to committed intent, and flagged when it
repeats a fix that already failed in the incident.

The operator's order (overnight item 6, 2026-11-12), which this module implements in part:
"AI troubleshooting, as designed: a background job; the AI proposes one catalog operation with
parameters; code validates it against intent and the guards; a person approves it; on failure
STOP with Retry with more information (cost shown first), Cancel or Hand over; a per-incident
cap of $1.00; a repeated failed proposal is flagged; payloads use stable labels. Settings ›
Background processes, AI mode Manual by default. Section 12's rule stays in force."

**Code decides; nothing here confirms or runs** (docs/HEAL_TO_INTENT.md section 12, "No fix
runs from AI text"). `check` answers the operation's own PREVIEW and the hash its confirm is
bound to, or a refusal naming what was compared and both operands, in this order, the first
that refuses ending the check:

1. **the catalog's schema** (`catalog.checked`): one operation the catalog holds, exactly the
   parameters its schema names, each of its shape. A command, a program, a flag the schema
   does not name, an unknown key: each refused by the schema, never matched as a pattern;
2. **the incident's own scope**: the device is the incident's, and every subscription named is
   one the incident's triggers name (`Incident.subscriptions`); a re-add's subscription is one
   a run left removed on the device (`resubscribe.removed_now`);
3. **the heal guards that hold any change to a device**: the device is one Mercury manages
   (`management.refusal_for`: never an observe-only device or a host), and no planned work
   holds it (guard 3, `heal.guards.g3_planned`: a planned restart window, the device held by
   another operation, a no-change window);
4. **committed intent and the operation's own guards** (`catalog.preview`: the operation's own
   plan, where the device's committed intent is read, the removal's measured shape asked and
   the program checked sendable).

**A repeat is flagged, never hidden and never refused** (the operator, 2026-11-11: "a
proposal that already failed in this incident is flagged, not silently re-proposed"): a checked
proposal carries ``repeat`` (`incident.repeat_of`: ``repeat``, ``variation`` naming each
changed parameter, or ``new``), whoever proposed it.

`propose` is `check` and then the proposal's line in the incident's record
(`incident.record_proposal`): the id its confirm will carry. A model's answer that is refused
is still recorded, with no operation, so the calls it cost stay the incident's; a refused
proposal of Mercury's or a person's records nothing.

Reads only, but for `propose`'s one line: the inventory, committed intent, the operations' run
records, the planned windows and holds, the incident's record. It opens no session, holds no
device, starts no job and calls no model (tests/test_fixit_incident.py's scan of
`modules/fixit/`).
"""

import logging
import time

log = logging.getLogger(__name__)

#: How a checked proposal's parameters read as an attempt's (`incident.PARAMETERS`), by
#: operation: the catalog's parameter name, and the attempt's. The device is the incident's,
#: never compared (`incident.NOT_PARAMETERS`).
AS_ATTEMPT = {"telemetry-resubscribe": {"subscriptions": "subs"},
              "telemetry-readd": {"subscription": "sub"}}
#: The checks, in the order they are made, each one's name as a refusal's code says it.
CHECKS = ("schema", "scope", "guards", "intent")
DONE = ". Nothing was previewed, and nothing runs"


def _listed(items) -> str:
    from modules.heal.catalog import listed

    return listed(items)


def as_attempt(operation: str, params: dict) -> dict:
    """*params*, a proposal's parameters as the catalog holds them (`catalog.checked`), in the
    form an attempt is compared by (`incident.canonical`)."""
    names = AS_ATTEMPT[operation]
    return {names[k]: v for k, v in params.items() if k in names}


def _subscriptions(params: dict) -> list:
    if "subscriptions" in params:
        return list(params["subscriptions"])
    return [params["subscription"]] if "subscription" in params else []


def _refused(code: str, check: str, words: str, passed: list) -> dict:
    return {"ok": False, "code": code, "check": check, "refused": words + DONE,
            "passed": list(passed)}


def check(incident, operation, params, *, resolved: float = None, now: float = None,
          sources=None, planned=None) -> dict:
    """*operation* with *params*, proposed in *incident* (an `incident.Incident`), checked in
    the module docstring's order: ``{"ok": True, "operation", "params", "preview", "hash",
    "repeat", "passed"}`` (the operation's preview as its card draws it, masked, and the hash
    its confirm is bound to), or ``{"ok": False, "code", "check", "refused", "passed"}``, the
    words naming what was compared and both operands. *passed* names each check made and
    passed. *resolved* is when the incident resolved (None while it stands); *sources* the
    operation's plan's own seam and *planned* guard 3's (``{"explained", "holder",
    "window"}``), each for tests. Never raises on a proposal's content."""
    from modules.fixit import incident as F
    from modules.heal import catalog, guards
    from modules.heal import resubscribe as R
    from modules.inventory.management import refusal_for

    F._check(incident)
    at = time.time() if now is None else float(now)
    network, passed = incident.network, []
    try:
        op, held = catalog.checked(operation, params)
    except catalog.Refused as exc:
        return _refused(exc.code, "schema", str(exc), passed)
    passed.append("schema")

    device, subs = held["device"], _subscriptions(held)
    if not incident.device:
        return _refused("no_device", "scope", (
            f"{incident.id} names no device, and {op.key} acts on one ({device} was proposed)"),
            passed)
    if device != incident.device:
        return _refused("another_device", "scope", (
            f"the proposal names the device {device}, and {incident.id} is "
            f"{incident.device}'s: a proposal acts on its incident's own device"), passed)
    outside = [s for s in subs if s not in incident.subscriptions]
    if outside:
        return _refused("not_named", "scope", (
            f"the proposal names subscription {_listed(outside)} on {device}, and "
            f"{incident.id} names "
            + (f"subscription {_listed(incident.subscriptions)}" if incident.subscriptions
               else "no subscription")
            + ": a proposal acts only on what its incident names"), passed)
    if op.key == R.READD_KEY:
        removed = [r["sub"] for r in R.removed_now(network, device)]
        if subs[0] not in removed:
            return _refused("not_removed", "scope", (
                f"a re-add adds back a receiver a run left removed, and the proposal names "
                f"subscription {subs[0]} on {device}, while the receivers left removed there "
                f"are {('those of subscription ' + _listed(removed)) if removed else 'none'}"),
                passed)
    passed.append("scope")

    why = refusal_for(network, device, what=f"a proposed {op.key}")
    if why:
        return _refused("management", "guards", why.removesuffix(" Nothing was sent."), passed)
    seams = dict(planned or {})
    g = guards.g3_planned(network, device, at, explained=seams.get("explained"),
                          holder=seams.get("holder"), window=seams.get("window"))
    if g:
        return _refused("planned_work", "guards", (
            f"guard {g['guard']} ({g['name']}) holds {device}: {g['words']}"), passed)
    passed.append("guards")

    got = catalog.preview(op.key, held, network=network, sources=sources)
    if not got["ok"]:
        return _refused(got["code"], "intent", got["refused"], passed)
    passed.append("intent")
    flag = F.repeat_of(incident, op.key, as_attempt(op.key, got["params"]), resolved, now=at)
    return {"ok": True, "operation": got["operation"], "params": got["params"],
            "preview": got["preview"], "hash": got["hash"], "repeat": flag, "passed": passed}


def propose(incident, source: str, operation, params, *, calls=(), prompt: str = "",
            resolved: float = None, now: float = None, sources=None, planned=None) -> dict:
    """`check`, and the proposal's line in *incident*'s record (`incident.record_proposal`):
    the check's answer with ``proposal``, the line's id, which the operation's confirm carries
    into its run (`incident.run_link`); ``""`` when nothing was recorded. A refused answer of a
    model (*source* ``ai``) is recorded with no operation, so the calls it cost (*calls*) stay
    the incident's; a refused proposal of Mercury's or a person's records nothing. Starts
    nothing."""
    from modules.fixit import incident as F

    if source not in F.SOURCES:
        raise F.Refused(f"a proposal comes from one of {', '.join(F.SOURCES)}, and {source!r} "
                        "was given")
    got = check(incident, operation, params, resolved=resolved, now=now, sources=sources,
                planned=planned)
    if got["ok"]:
        line = F.record_proposal(incident, source, got["operation"],
                                 as_attempt(got["operation"], got["params"]), calls=calls,
                                 prompt=prompt, now=now)
    elif source == "ai":
        line = F.record_proposal(incident, source, calls=calls, prompt=prompt, now=now)
    else:
        line = {}
    log.info("fixit: %s: a %s proposal %s", incident.id, source,
             "checked" if got["ok"] else f"refused ({got['code']})")
    return dict(got, proposal=line.get("proposal", ""))
