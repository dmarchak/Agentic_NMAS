"""R1's trigger, its records (the operator, 2026-11-14; docs/MERCURY_CHARTER.md, "Two standing
rules"): which failures of Mercury's fix start an AI investigation by themselves, each once.

**Off by default on every network** (the operator, 2026-11-14: CLAUDE.md's AI cost safety rules
stand): it is the background feature ``fixit_auto`` (`background.FEATURES`), turned on per
network by a verified person in Settings › AI after its estimate (`background.estimate`,
`background.turn_on`, which records who, when and the estimate shown), off in one press
(`background.turn_off`), and the gateway refuses its call while it is off or past its caps.
`switch` reads it.

**A failure** (`failures`) is a fix of Mercury's that failed, did not verify, or does not exist
for the incident's kind, read from its own record, each with its own key (`key_of`):
- the heal's decision found no code fix for this kind (`DECISION_FAILURES`: ``cant_fix``):
  ``decision:<incident>``, ONE per incident however often a standing incident is judged again
  (C2813: a re-judged standing incident is the same failure, never a new one that spends
  again). A hold is NEVER a failure (R2: "a guard or hold working as designed is not a
  failure"): a guard that waits (the grace, planned work, a recent change, a person working)
  holds the heal for now, and one that stops it (guard 4's departure) is a person's to resolve;
  neither starts anything, nor takes the incident's key, so a later can't-fix still does;
- the heal's act ended without a verified fix (`ACT_FAILURES`: its symptom remained, it rolled
  back, it failed after sending, it was refused before sending, it was interrupted):
  ``act:<decision>``, one per act;
- a plan a person approved on the incident's page stopped at a step or failed (the R1 flow's
  step 7: "step 2 runs again with that failure in the evidence"): ``run:<plan run id>``.

**Only while self-healing is in Auto for that problem kind** (the operator, 2026-11-14: "with
self-healing off or in Dry run, nobody asked Mercury to fix anything"; `heal_auto`, `eligible`):
the network's heal policy in Auto NOW (`heal.policy.current`: in force, not expired, after the
kill switch and the stage guard), and, for a failure of a code fix, its kind among the kinds
Auto allows; a problem with no code fix (a can't-fix, a lost stream) needs only Auto. A failure
recorded before Auto went on (the policy's confirmation time) never starts by itself either.

**Once per failure, across processes**: the key is taken by ONE ``start`` line in the incident's
own record under its lock (`incident.claim_start`), whoever asks first; a second runner, a
second worker or a restart finds it taken and asks nothing.

**No catch-up** (`switch`, `manual_start`): a failure recorded before the switch's ``at`` (when
the person turned it on, as `turn_on` recorded it) never starts anything by itself, nor does one
recorded while it was off: turning it on, or on again after its approval ended, starts nothing
for the past. Such an incident, still open, offers ONE Start AI troubleshooting, a person's
press (as for a lab incident whose fix failed before this release). A switch whose ``at``
Mercury did not write is never in force (`background.in_force`), so nothing starts on it.

Reads, and the start lines; nothing here asks the AI, holds a device, starts a job or sends
(tests/test_fixit_incident.py's scan of `modules/fixit/`). The pass that asks is the
notifier's (`heal_notice.run_fixit`).
"""

import calendar
import logging
import time

log = logging.getLogger(__name__)

#: The background feature (`background.FEATURES`) and its finding kind.
FEATURE = "fixit_auto"
#: The decision outcomes after which no code fix of Mercury's exists for the problem (can't
#: fix, `heal.decisions.OUTCOMES`). Never ``held``: a hold works as designed (R2).
DECISION_FAILURES = ("cant_fix",)
#: The act outcomes that are no verified fix (`heal.act.OUTCOMES`; ``healed`` and ``partial``
#: are not failures: partial healed and says what it could not show).
ACT_FAILURES = ("symptom_remains", "rolled_back", "failed", "refused", "interrupted")
#: A plan run's outcomes that are a failure of an approved plan (`plan_engine.RECORD_STATE`).
PLAN_FAILURES = ("stopped", "failed")
#: The incident states in which a failure may still start an investigation.
OPEN = ("watching", "ready", "claimed", "standing")
#: How far back a failure's frequency is measured, for the feature's estimate.
FREQUENCY_DAYS = 7


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def switch(network: str) -> dict:
    """The network's switch for ``fixit_auto``: ``{"on", "epoch", "at", "by", "entry"}``,
    *epoch* when it was turned on (its entry's ``at``), None while it is off or its approval
    has ended (`background.entry_of`). A read of the settings."""
    from modules.ai import background
    from modules.nsot import listref

    entry = background.entry_of(listref.network_id(network), FEATURE)
    if not entry:
        return {"on": False, "epoch": None, "at": "", "by": "", "entry": None}
    try:
        epoch = float(calendar.timegm(time.strptime(str(entry.get("at") or ""),
                                                    "%Y-%m-%dT%H:%M:%SZ")))
    except ValueError:
        return {"on": False, "epoch": None, "at": "", "by": "", "entry": None}
    return {"on": True, "epoch": epoch, "at": entry["at"], "by": entry.get("by") or "",
            "entry": entry}


#: The failures that need only self-healing in Auto, whatever their kind: no code fix exists for
#: the problem (a can't-fix, a lost stream). Any other failure needs its fix kind among the
#: kinds Auto allows (`heal.policy.current`'s ``kinds_auto``).
NO_CODE_FIX = ("cant_fix", "no_code_fix")


def heal_auto(network: str, now: float = None) -> dict:
    """Whether self-healing is in Auto on *network* NOW (the operator, 2026-11-14: "R1 fires
    only while self-healing is in Auto for that problem kind; with self-healing off or in Dry
    run, nobody asked Mercury to fix anything"): ``{"auto", "since", "kinds_auto", "words"}``,
    *auto* the policy's mode after the kill switch, its confirmation, its expiry and the stage
    guard (`heal.policy.current`), *since* when the policy in force was confirmed (epoch), the
    time a failure must not precede (no catch-up)."""
    from modules.heal import policy

    got = policy.current(network, now)
    if got.get("mode") != "auto":
        return {"auto": False, "since": None, "kinds_auto": [], "words": got.get("words") or ""}
    try:
        since = float(calendar.timegm(time.strptime(
            str((got.get("confirmed") or {}).get("at") or ""), "%Y-%m-%dT%H:%M:%SZ")))
    except ValueError:
        return {"auto": False, "since": None, "kinds_auto": [],
                "words": "AUTO's confirmation holds no time, so when it went on is not known"}
    return {"auto": True, "since": since, "kinds_auto": list(got.get("kinds_auto") or []),
            "words": got.get("words") or ""}


def eligible(failure: dict, sw: dict, heal: dict) -> str:
    """``""`` when *failure* starts an investigation by itself, else why not: the switch on
    (*sw*, `switch`) and the failure recorded after it went on; self-healing in Auto (*heal*,
    `heal_auto`) and the failure recorded after Auto went on; and, for a failure of a code
    fix, its kind among the kinds Auto allows."""
    if not sw.get("on"):
        return "automatic troubleshooting is off for this network"
    if failure["epoch"] < sw["epoch"]:
        return "it was recorded before automatic troubleshooting was turned on for this network"
    if not heal.get("auto"):
        return "self-healing is not in Auto on this network, so nobody asked Mercury to fix it"
    if failure["epoch"] < heal["since"]:
        return "it was recorded before self-healing's Auto went on"
    kind = failure.get("fix_kind") or ""
    if failure.get("outcome") not in NO_CODE_FIX and kind and kind not in heal["kinds_auto"]:
        return f"self-healing's Auto does not allow its kind of fix ({kind})"
    return ""


def key_of(kind: str, ident: str) -> str:
    """A failure's key: ``decision:<incident>``, ``act:<decision>`` or ``run:<run id>`` (the
    shape a background trigger's finding id takes: no underscore, no space)."""
    return f"{kind}:{ident}"


def failures(network: str, *, open_ids=None) -> dict:
    """*network*'s failures of Mercury's fix, oldest first (the module's docstring):
    ``{"state", "failures", "error"}``, each ``{"key", "kind", "id", "incident", "device",
    "outcome", "epoch", "at"}``; *open_ids*, when given, keeps only those incidents'. A step log
    that cannot be read gives none, said."""
    from modules.heal import steplog

    got = steplog.read(network)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "failures": [], "error": got["error"]}
    seen, out = set(), []
    for r in got["rows"]:
        inc = r.get("incident") or ""
        if not inc or (open_ids is not None and inc not in open_ids):
            continue
        row, outcome = r.get("row"), r.get("outcome") or ""
        if row == "decision" and outcome in DECISION_FAILURES:
            kind, ident = "decision", inc
        elif row == "act" and outcome in ACT_FAILURES and r.get("decision"):
            kind, ident = "act", r["decision"]
        else:
            continue
        key = key_of(kind, ident)
        if key in seen:
            continue
        seen.add(key)
        epoch = float(r.get("epoch") or 0)
        out.append({"key": key, "kind": kind, "id": ident, "incident": inc,
                    "device": r.get("device") or "", "outcome": outcome, "epoch": epoch,
                    "at": r.get("at") or (_iso(epoch) if epoch else ""),
                    "fix_kind": r.get("kind") or ""})
    return {"state": "ok", "failures": out, "error": ""}


def no_code_fix(record: dict) -> dict:
    """The failure an incident *record* (its own store's) is when no code fix exists for its
    kind: a lost telemetry stream (`diagnose_stream.target_from`), whose fix changes the
    device's configuration and is never the heal's own. Keyed as the decision's would be
    (``decision:<incident>``, `key_of`), so a decision on it later is the same failure. ``{}``
    for any other incident."""
    from modules.heal import diagnose_stream

    target = diagnose_stream.target_from(record or {})
    if not target or not record.get("id"):
        return {}
    epoch = float(target.get("lost_at") or 0)
    return {"key": key_of("decision", record["id"]), "kind": "decision", "id": record["id"],
            "incident": record["id"], "device": record.get("device") or "",
            "outcome": "no_code_fix", "epoch": epoch, "at": _iso(epoch) if epoch else ""}


def plan_failures(network: str, incident) -> list:
    """*incident*'s approved plans that stopped or failed (the R1 flow's step 7), each a
    failure keyed by its run (`key_of`): read from its record's approve lines and each plan
    run's own record (`plan_engine.record_of`)."""
    from modules import plan_engine
    from modules.fixit import incident as F

    rec = F.read(incident)
    out = []
    for ln in rec["lines"]:
        if ln.get("choice") != "approve" or not ln.get("run"):
            continue
        run = plan_engine.record_of(network, ln["run"])
        if not run or run.get("outcome") not in PLAN_FAILURES:
            continue
        epoch = float(run.get("finished_at") or run.get("started_at") or 0)
        out.append({"key": key_of("run", ln["run"]), "kind": "run", "id": ln["run"],
                    "incident": incident.id, "device": incident.device,
                    "outcome": run.get("outcome"), "epoch": epoch,
                    "at": _iso(epoch) if epoch else ""})
    return out


def open_incidents(network: str) -> dict:
    """``{incident id: its record}`` for the network's incidents still open (`OPEN`)."""
    from modules.heal import incidents

    got = incidents.read(network)
    return {i["id"]: i for i in got["incidents"]
            if isinstance(i, dict) and i.get("id") and i.get("state") in OPEN}


def taken(incident) -> set:
    """The failure keys *incident*'s record has taken (its start lines)."""
    from modules.fixit import incident as F

    return {ln.get("start") for ln in F.starts(incident)["starts"]}


def in_flight(incident, now: float, bound_s: float) -> bool:
    """Whether an investigation of *incident* was started and nothing has come of it yet: its
    newest start is ``started``, no proposal line follows it, and it is younger than *bound_s*
    (the investigation's own bound; past it, it is no longer waited for)."""
    from modules.fixit import incident as F

    lines = F.read(incident)["lines"]
    last = max((n for n, ln in enumerate(lines) if "start" in ln), default=None)
    if last is None or lines[last].get("state") != "started":
        return False
    if any("proposal" in ln for ln in lines[last + 1:]):
        return False
    return now - float(lines[last].get("epoch") or 0) < bound_s


def manual_start(network: str, incident_id: str, extra=(), record: dict = None) -> dict:
    """Whether *incident_id* offers the one Start AI troubleshooting (a person's press, the R1
    flow from step 3) because its failure will not start one by itself: ``{"offered",
    "failure", "words"}``. Offered when it has a failure (`failures`, its *record*'s
    `no_code_fix`, or *extra*, its failed attempts) and the switch is off, or its first
    failure was recorded before the switch went on (no catch-up). The caller adds what the
    record says (no AI asked yet)."""
    got = failures(network, open_ids={incident_id})
    found = list(got["failures"])
    lost = no_code_fix(record or {})
    if lost and lost["key"] not in {f["key"] for f in found}:
        found.append(lost)
    found.sort(key=lambda f: f["epoch"])
    first = found[0] if found else None
    if first is None and not extra:
        return {"offered": False, "failure": None, "words": ""}
    sw = switch(network)
    why = (eligible(first, sw, heal_auto(network)) if first is not None else
           "" if sw["on"] else "automatic troubleshooting is off for this network")
    if why:
        return {"offered": True, "failure": first,
                "words": f"The AI did not start by itself: {why}"}
    return {"offered": False, "failure": first, "words": ""}


def offers_start(network: str, record: dict) -> bool:
    """Whether the incident *record* (its own store's) offers Start AI troubleshooting as its one
    next action now, as its page does (`section._contract`): its failure will not start an
    investigation by itself (`manual_start`), and no investigation was started or answered in
    it. Needs attention's row about it asks this, so the row and the page offer the same first
    action (`attention.first_action`, R1 and R2). A read."""
    from modules.fixit import incident as F
    from modules.fixit import section

    if not isinstance(record, dict) or not record.get("id"):
        return False
    found = {"id": record["id"], "incident": record, "entry": {}, "decisions": []}
    inc = section.incident_of(network, found)["incident"]
    if inc is None:
        return False
    rec = F.read(inc)
    if rec["state"] == "unreadable" or any(
            "start" in ln or ("proposal" in ln and ln.get("source") == "ai")
            for ln in rec["lines"]):
        return False
    return bool(manual_start(network, record["id"], record=record)["offered"])


def failure_frequency(network: str, now: float = None) -> dict:
    """``{"per_day", "basis"}``: the network's failures of Mercury's fix a day over the last
    `FREQUENCY_DAYS` days, from its step log (the feature's estimate, `background.estimate`)."""
    now = time.time() if now is None else float(now)
    got = failures(network)
    if got["state"] != "ok":
        return {"per_day": None, "basis": f"its step log cannot be read ({got['error']})"}
    since = now - FREQUENCY_DAYS * 86400
    n = sum(1 for f in got["failures"] if f["epoch"] >= since)
    return {"per_day": n / FREQUENCY_DAYS,
            "basis": (f"{n} failure(s) of Mercury's fix in the last {FREQUENCY_DAYS} days of "
                      f"{network}'s step log")}
