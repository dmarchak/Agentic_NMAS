"""Mercury's own proposer: the fix its deterministic diagnosis names, as one catalog operation
with its parameters, made with no AI call (the fix-it plan's S2: the stand-in proposer's
production form).

The operator's order (overnight item 6, 2026-11-12), which this module implements in part:
"AI troubleshooting, as designed: a background job; the AI proposes one catalog operation with
parameters; code validates it against intent and the guards; a person approves it; on failure
STOP with Retry with more information (cost shown first), Cancel or Hand over; a per-incident
cap of $1.00; a repeated failed proposal is flagged; payloads use stable labels. Settings ›
Background processes, AI mode Manual by default. Section 12's rule stays in force."

**From a diagnosis to a proposal, by a fixed table** (`STREAM_PROPOSALS`), the way
`diagnose.action_for` chooses a heal's action: only the diagnosis's FIRST hypothesis decides,
only when its evidence is complete, and only when its rule is a row of the table. The rows are
the lost-stream runbook's rules whose next step is Re-subscribe (`diagnose_stream.RECOVERY`):
the stream stuck at its ends, as a half-open session, as no session on a collector that
listens, or as a stream that outlived its cause; and the one whose next step is the
re-subscribe with the collector step (`diagnose_stream.COLLECTOR_RECOVERY`, C3111): the
device's connection Disconnecting while the collector's session from it is established and
idle, both ends measured. Every other rule names a next step no catalog
operation is (put a neighbour back, start the collector, check drift, diagnose again later):
no proposal, its words naming the rule. Never a guess: no hypothesis, an incomplete first one,
or a diagnosis of another runbook proposes nothing.

**A receiver a run left removed comes first** (`resubscribe.removed_now`): while one stands the
proposal is its re-add, the danger state's own fix, whatever the diagnosis says.

What it returns is a proposal to check (`modules/fixit/validate.py`, `propose` with source
``mercury``), never a preview, a hash or a run: code validates it, and a person approves it.
Reads the operations' run records only; calls no model, sends nothing and starts nothing.
"""

import logging

log = logging.getLogger(__name__)

RUNBOOK = "stream_lost"
#: The lost-stream rules whose next step is Re-subscribe (`diagnose_stream.RECOVERY`), each
#: proposing it for the incident's lost subscriptions. tests/test_fixit_catalogue.py derives
#: the set from the rules' own source, independently of this table.
STREAM_PROPOSALS = {"half_open": "telemetry-resubscribe",
                    "no_session": "telemetry-resubscribe",
                    "outlived_cause": "telemetry-resubscribe",
                    # C3111: the device's connection Disconnecting while the collector's session
                    # from it is established and idle: the re-subscribe with the collector step
                    # (`diagnose_stream.COLLECTOR_RECOVERY`, `resubscribe.COLLECTOR_KEY`).
                    "stale_session": "telemetry-collector-resubscribe"}


def _none(words: str, rule: str = "") -> dict:
    return {"state": "none", "source": "mercury", "operation": "", "params": {}, "rule": rule,
            "words": words}


def _chosen(operation: str, params: dict, rule: str, words: str) -> dict:
    return {"state": "proposed", "source": "mercury", "operation": operation,
            "params": params, "rule": rule, "words": words}


def mercury(incident, diagnosis: dict = None) -> dict:
    """Mercury's own proposal for *incident* (an `incident.Incident`) from its newest
    *diagnosis* (`diagnose.run`'s answer, the lost-stream runbook's): ``{"state": "proposed",
    "source": "mercury", "operation", "params", "rule", "words"}`` with the catalog's
    parameters, or ``{"state": "none", ..., "words"}`` saying why there is none. Reads only."""
    from modules.fixit import incident as F
    from modules.heal import resubscribe as R
    from modules.heal.catalog import listed

    F._check(incident)
    if not incident.device:
        return _none(f"{incident.id} names no device, so no operation of the catalog acts in it")
    removed = [r["sub"] for r in R.removed_now(incident.network, incident.device)]
    if removed:
        sub = removed[0]
        return _chosen(R.READD_KEY, {"device": incident.device, "subscription": sub}, "",
                       f"a run left {incident.device}'s receiver for subscription {sub} "
                       "removed: add it back first")
    d = diagnosis or {}
    if not d:
        return _none("Mercury has not diagnosed this incident yet: Diagnose now reads it")
    if d.get("runbook") != RUNBOOK:
        return _none(f"the diagnosis ran \"{d.get('runbook_words') or d.get('runbook')}\", and "
                     "only the lost-stream runbook's findings name an operation of the catalog")
    if (d.get("target") or {}).get("device") != incident.device:
        return _none(f"the diagnosis is of {(d.get('target') or {}).get('device') or 'no device'}"
                     f", and {incident.id} is {incident.device}'s")
    hyps = d.get("hypotheses") or []
    if not hyps:
        return _none("the diagnosis found no cause, and a proposal is never a guess")
    first = hyps[0]
    rule = first.get("rule") or ""
    said = f"the first hypothesis ({rule}, {first.get('strength')})"
    if first.get("incomplete"):
        return _none(f"{said} lacks evidence ({(first.get('incomplete') or [''])[0]}), and a "
                     "proposal is made only on a complete one", rule)
    operation = STREAM_PROPOSALS.get(rule)
    if not operation:
        return _none(f"{said} names a next step no operation of the catalog is: "
                     f"{first.get('todo') or 'none named'}", rule)
    lost = [str(s) for s in (d.get("target") or {}).get("subscriptions") or []]
    subs = [s for s in lost if s in incident.subscriptions]
    if not subs:
        return _none(f"the diagnosis read subscription {listed(lost)}, none of which "
                     f"{incident.id} names", rule)
    return _chosen(operation, {"device": incident.device, "subscriptions": subs}, rule,
                   f"{said}: {first.get('claim') or ''}".rstrip(": "))
