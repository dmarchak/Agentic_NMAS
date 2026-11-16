"""What counts as tried in an incident, and the lost stream's ladder of repairs (the operator,
2026-11-16, incident hi-22cfdc299000: r7's streams 101 and 102 lost, its gRPC session wedged
with both ends holding it).

**Tried, by equivalence** (the operator: "The AI never proposes a step whose equivalent already
failed on the incident: three re-subscribes already removed and re-added r7's receivers, so
're-add the receiver' counts as tried. It proposes the first untried rung."). `TRIED_AS` is a
declared table: each step of Mercury's that resets the device's side of a stream, by the reset
it makes. Two steps of one class are the same attempt for "tried": a failed run of either makes
the other tried too, for the subscriptions they share (a step naming none, the whole device).
Read where the AI's proposal is checked (`fixit_troubleshoot`'s answer check refuses a plan
step whose equivalent failed, naming the attempt and the first untried rung) and in what the AI
is told (its ``ladder`` section, `section`). A person's and Mercury's proposals keep the
repeat flag alone (the operator's rule of 2026-11-11).

**The ladder** (`STREAM_LOST`), least disruptive first, never a reload (the operator: "Never a
reload anywhere in the ladder"). EVERY rung closes the collector's stale half first (the
operator, 2026-11-16), then resets the device's side, then verifies (each step's verify the
re-subscribe's own checks: the receiver Connected on a new connection, and the collector's
new session carrying data, `modules/heal/stream_checks.py`):
1. re-add the receiver: the re-subscribe with the collector step (`resubscribe.COLLECTOR_KEY`:
   the close, the device's connection read gone, each receiver removed and re-added);
2. recreate the subscriptions from committed intent: the collector step alone
   (`resubscribe.CLOSE_KEY`), then the built-in plan `telemetry-subscription-recreate` for each
   subscription (``no telemetry ietf subscription <id>`` and its lines as intent renders them,
   net zero); two subscriptions pause, nothing else;
3. restart the device's telemetry stack: the collector step alone, then the built-in plan
   `telemetry-stack-restart` (``no netconf-yang`` then ``netconf-yang``, net zero); all of the
   device's NETCONF and telemetry pause.
The lines of rungs 2 and 3 are PROVISIONAL shapes until an admin approves them, once
scripts/nmas-telemetry-reset-probe has measured each on r2 (the operator: "measure both on r2
first as Mercury probes ... I approve the shapes as admin when measured"): their plans preview
refused, naming each shape, and nothing runs before.

Reads only: the incident's attempts (`incident.attempts`), never a device or a store's write.
"""

import logging

log = logging.getLogger(__name__)

#: Each step's reset of the device's side of a stream, for "tried" (the operator, 2026-11-16).
TRIED_AS = {
    "telemetry-resubscribe": "receiver_readded",
    "telemetry-readd": "receiver_readded",
    "telemetry-collector-resubscribe": "receiver_readded",
    "telemetry-subscription-recreate": "subscription_recreated",
    "telemetry-stack-restart": "telemetry_stack_restarted",
}
#: The collector step alone: every later rung's first step, no reset of its own.
CLOSE_STEP = {"operation": "telemetry-collector-close", "params": {"subscriptions": "{subs}"}}
#: Each class in a person's words.
CLASS_WORDS = {
    "receiver_readded": "the subscription's receiver removed and re-added",
    "subscription_recreated": "the subscription removed and re-created from committed intent",
    "telemetry_stack_restarted": "the device's telemetry stack (its NETCONF-YANG processes) "
                                 "restarted",
}

#: The lost stream's ladder, least disruptive first. ``steps`` is the plan as the AI proposes
#: it: ``{subs}`` the incident's subscriptions, ``{each}`` one step per subscription.
STREAM_LOST = (
    {"rung": 1, "what": "Re-add the receiver, the collector's stale half closed first",
     "tried_as": "receiver_readded",
     "steps": ({"operation": "telemetry-collector-resubscribe",
                "params": {"subscriptions": "{subs}"}},),
     "verify": "the device's receiver reads Connected on a new connection, and the collector's "
               "new session from the device carries data (its bytes received grow on two "
               "reads)",
     "impact": "only the chosen subscriptions' streams pause, for seconds; traffic unaffected",
     "why": ""},
    {"rung": 2, "what": "Recreate the subscriptions from committed intent, the collector's "
                        "stale half closed first",
     "tried_as": "subscription_recreated",
     # ONE recreate step: it recreates every subscription on the named one's receiver in one
     # batch (the review of 2026-11-16: they share one connection).
     "steps": (CLOSE_STEP, {"operation": "telemetry-subscription-recreate",
                            "params": {"subscription": "{first}"}}),
     "verify": "each subscription's receiver reads Connected on a new connection, and the "
               "collector's new session carries data (alone on its receiver: its bytes grow on "
               "two reads; sharing it: its own series is back and a new session receives)",
     "impact": "only the recreated subscriptions' streams pause (for a time not yet "
               "measured); routing, forwarding and other subscriptions untouched",
     "why": "its lines are provisional shapes until an admin approves them, once the probe "
            "has measured them on r2: the plan's preview names them, and nothing runs before"},
    {"rung": 3, "what": "Restart the device's telemetry stack (its NETCONF-YANG processes, "
                        "never the device), the collector's stale half closed first",
     "tried_as": "telemetry_stack_restarted",
     "steps": (CLOSE_STEP, {"operation": "telemetry-stack-restart", "params": {}}),
     "verify": "every subscription the device's intent declares is back, by the same checks",
     "impact": "the device's NETCONF, RESTCONF and every telemetry subscription pause while "
               "its NETCONF-YANG processes restart (for a time not yet measured); routing and "
               "forwarding are unaffected; never a reload",
     "why": "its two lines are provisional shapes until an admin approves them, once the "
            "probe has measured them on r2: the plan's preview names them, and nothing runs "
            "before"},
)


def _subs_of(params: dict) -> set:
    p = params or {}
    if p.get("subs"):
        return {str(s) for s in p["subs"]}
    if p.get("subscriptions"):
        return {str(s) for s in p["subscriptions"]}
    for k in ("sub", "subscription"):
        if p.get(k):
            return {str(p[k])}
    return set()


def _overlaps(a: set, b: set) -> bool:
    """Two resets touch one stream: they share a subscription, or either names none (the
    whole device)."""
    return not a or not b or bool(a & b)


def tried(failed) -> list:
    """Each failed attempt (*failed*, `fixit_troubleshoot.failed_of`'s) whose step `TRIED_AS`
    holds, as
    plain data a request carries: ``[{"attempt", "operation", "tried_as", "subs",
    "outcome"}]``."""
    out = []
    for a in failed or ():
        cls = TRIED_AS.get(a.get("operation"))
        if cls:
            out.append({"attempt": a.get("n"), "operation": a.get("operation"),
                        "tried_as": cls, "subs": sorted(_subs_of(a.get("params"))),
                        "outcome": a.get("outcome") or ""})
    return out


def equivalent_of(operation: str, params: dict, tried_rows) -> dict:
    """The newest of *tried_rows* (`tried`) that makes *operation* with *params* tried: the
    same class, an overlapping stream; ``{}`` when none does."""
    cls = TRIED_AS.get(operation)
    if not cls:
        return {}
    mine = _subs_of(params)
    hits = [t for t in tried_rows or () if t["tried_as"] == cls
            and _overlaps(mine, set(t["subs"]))]
    return dict(hits[-1]) if hits else {}


def rungs(incident, tried_rows) -> list:
    """The lost stream's ladder for *incident* (`STREAM_LOST`), each rung with ``tried``
    (the attempt that made it tried, ``{}`` when none), ``built`` and ``first_untried`` (the
    one rung to propose: the first neither tried nor without a step), its steps filled with the
    incident's device and subscriptions. ``[]`` for an incident that names no subscription."""
    subs = [str(s) for s in getattr(incident, "subscriptions", ()) or ()]
    if not subs:
        return []
    out, chosen = [], False
    for r in STREAM_LOST:
        steps = []
        for s in r["steps"]:
            each = "{each}" in s["params"].values()
            for one in (subs if each else [None]):
                steps.append({"operation": s["operation"], "params": dict(
                    {k: (subs if v == "{subs}" else one if v == "{each}" else
                         subs[0] if v == "{first}" else v)
                     for k, v in s["params"].items()}, device=incident.device)})
        hit = {}
        for t in tried_rows or ():
            if t["tried_as"] == r["tried_as"] and _overlaps(set(subs), set(t["subs"])):
                hit = dict(t)
        row = {"rung": r["rung"], "what": r["what"], "tried_as": r["tried_as"],
               "tried_words": CLASS_WORDS[r["tried_as"]], "steps": steps,
               "verify": r["verify"], "impact": r["impact"], "built": bool(steps),
               "why": r["why"], "tried": hit, "first_untried": False}
        if not chosen and steps and not hit:
            row["first_untried"] = chosen = True
        out.append(row)
    return out


def first_untried(rows) -> dict:
    return next((r for r in rows or () if r.get("first_untried")), {})


def step_refusal(steps, tried_rows, rows=None) -> str:
    """Why a plan of *steps* (``[{"operation", "params"}]``, an AI's) names a step whose
    equivalent already failed in the incident (`equivalent_of`), naming the attempt and the
    first untried rung of *rows* (`rungs`); ``""`` when none does."""
    for n, s in enumerate(steps or (), 1):
        op = (s or {}).get("operation") or ""
        hit = equivalent_of(op, (s or {}).get("params") or {}, tried_rows)
        if not hit:
            continue
        nxt = first_untried(rows)
        then = (f"propose the first untried rung, rung {nxt['rung']} ({nxt['what']}): "
                + ", then ".join(x["operation"] for x in nxt["steps"]) if nxt else
                "no rung of the ladder is left untried: report the gap and hand it over")
        return (f"the plan's step {n} ({op}) counts as tried: attempt:{hit['attempt']} "
                f"({hit['operation']}, {hit['outcome'] or 'failed'}) already made the same "
                f"reset in this incident ({CLASS_WORDS[hit['tried_as']]}), and an equivalent "
                f"of a failed step is never proposed again; {then}")
    return rung_refusal(steps, rows)


#: The steps that reset a later rung's device side: each must follow the collector step.
CLOSE_FIRST = ("telemetry-subscription-recreate", "telemetry-stack-restart")


def rung_refusal(steps, rows) -> str:
    """Why an AI's plan of *steps* is not the ladder's first untried rung as the ladder makes it
    (the review of 2026-11-16), or ``""``: a reset of a later rung than the first untried one,
    or a later rung's reset with no collector step (`CLOSE_STEP`'s) before it."""
    nxt = first_untried(rows)
    steps = [s or {} for s in steps or ()]
    ops = [s.get("operation") or "" for s in steps]
    for n, op in enumerate(ops, 1):
        cls = TRIED_AS.get(op)
        rung = next((r for r in rows or () if r["tried_as"] == cls), None)
        if rung and nxt and rung["rung"] > nxt["rung"]:
            return (f"the plan's step {n} ({op}) is rung {rung['rung']}, and the first untried "
                    f"rung is rung {nxt['rung']} ({nxt['what']}): propose it first, least "
                    "disruptive first: " + ", then ".join(x["operation"] for x in nxt["steps"]))
        if op in CLOSE_FIRST:
            why = _close_before(steps, n, rows)
            if why:
                return why
    return ""


def _close_before(steps: list, n: int, rows) -> str:
    """Why step *n*'s reset has no collector step before it closing for the same device and
    the reset's subscriptions (the ladder's own, all of them, for a reset naming none), or
    ``""`` (the third review)."""
    reset = steps[n - 1]
    rp = reset.get("params") or {}
    want = _subs_of(rp) or next((set(map(str, s["params"].get("subscriptions") or []))
                                 for r in rows or () for s in r["steps"]
                                 if s["operation"] == CLOSE_STEP["operation"]), set())
    for s in steps[:n - 1]:
        if s.get("operation") != CLOSE_STEP["operation"]:
            continue
        p = s.get("params") or {}
        if p.get("device") != rp.get("device"):
            continue
        if not want or want <= {str(x) for x in p.get("subscriptions") or []}:
            return ""
    return (f"the plan's step {n} ({reset.get('operation')}) resets "
            f"{rp.get('device') or 'the device'}'s side with no {CLOSE_STEP['operation']} step "
            "before it for the same device and "
            + (f"subscription {', '.join(sorted(want))}" if want else "its subscriptions")
            + ": every rung closes the collector's stale half first")


def close_first_note(steps) -> str:
    """For a person's plan (kept as approved): a later rung's reset with no collector step
    before it, said in its preview; ``""`` otherwise."""
    ops = [(s or {}).get("operation") or "" for s in steps or ()]
    for n, op in enumerate(ops, 1):
        if op in CLOSE_FIRST and CLOSE_STEP["operation"] not in ops[:n - 1]:
            return (f"Step {n} ({op}) resets the device's side without closing the "
                    "collector's stale session first (telemetry-collector-close), as every "
                    "rung of the lost stream's ladder does: a stale session may keep the "
                    "stream from coming back.")
    return ""


def section(incident, tried_rows) -> dict:
    """The ``ladder`` section a request carries (`fixit_troubleshoot.built_request`): each rung
    a piece ``ladder:<n>``, None for an incident with no stream named."""
    rows = rungs(incident, tried_rows)
    if not rows:
        return None
    pieces = [dict(r, ref=f"ladder:{r['rung']}", device=incident.device) for r in rows]
    return {"ref": "ladder", "name": "ladder", "state": "ok", "why": "",
            "source": "Mercury's ladder for a lost stream and the incident's failed attempts "
                      "(modules/fixit/ladder.py)", "pieces": pieces}
