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
  again);
- the heal's decision is held by a guard a PERSON resolves (`HELD_FOR_A_PERSON`: none since
  C3909, 2026-11-17; before it guards 4 and 6, held with no time to check again): no fix
  Mercury can run alone (the operator, 2026-11-15: "count held
  incidents (e.g. [a lab router]'s guard-4 hold) as 'no fix Mercury can run alone' ... The AI
  may only diagnose and propose within its catalog; where the fix needs a person's approval (a
  template
  bring-in), it says so as its finding and offers Hand over"): ``held:<incident>``, ONE per
  incident. A guard that WAITS (guard 3, planned work: held with a time to check again) is no
  failure (R2: "a guard or hold working as designed is not a
  failure"): it starts nothing, nor takes a key, so a later can't-fix or hold still does;
- the heal's act ended without a verified fix (`ACT_FAILURES`: its symptom remained, it could
  not be confirmed (partial), it rolled back, it failed after sending, it was refused before
  sending, it was interrupted): ``act:<decision>``, one per act. Its incident stays open,
  standing on the act (C3870, the operator, 2026-11-16: "Only 'healed' closes an incident";
  `heal.act.outcome_on_incident`), so this reader, which reads open incidents only, sees it;
- the heal's act healed and verified, and a step of its tail after Fixed failed (the save to
  startup, the golden commit, or the read against the new golden: `heal.act.tail_of`'s flag):
  ``tail:<decision>``, its incident reopened by the tail (`heal.act.reopen_on_tail`). Before
  any AI call on an act's or a tail's failure, Mercury reads the device itself and closes the
  incident on that read where it is at intent and its symptom gone
  (`heal.act.confirm_before_ai`, asked by `heal_notice._investigation`);
- a plan a person approved on the incident's page stopped at a step or failed (the R1 flow's
  step 7: "step 2 runs again with that failure in the evidence"): ``run:<plan run id>``;
- a retry of the incident's fixes that failed again (`heal.retry.failures_of`, the operator,
  2026-11-16: self-healing switched on, or a new script saved that matches it):
  ``retry:<retry id>``, one per retry; a daily retry's failure starts nothing (whether new
  evidence or a new capability should start it is a follow-up).

**In every mode of self-healing** (the operator, 2026-11-15, replacing 2026-11-14's "only while
self-healing is in Auto": "the AI only proposes, and nothing runs without a person's approval,
so it investigates in Dry run too"; `eligible`): the switch on and the failure recorded after
it went on are the whole condition. `heal_auto` still reads the policy, for the words a page
says, never as a gate.

**Once per failure, across processes**: the key is taken by ONE ``start`` line in the incident's
own record under its lock (`incident.claim_start`), whoever asks first; a second runner, a
second worker or a restart finds it taken and asks nothing.

**Nothing in the past starts by itself; turning it on catches up on the person's choice**
(`switch`, `manual_start`, `catch_up`; the operator, 2026-11-15: "when the switch is turned on,
it starts on every open incident whose fix failed or that has no fix, within the caps. Turning
it on shows the list first ... each tickable, and records what was chosen. After that, every
new failure starts by itself"): a failure recorded before the switch's ``at`` (when the person
turned it on, as `turn_on` recorded it) never starts anything by itself, nor does one recorded
while it was off. Turn on… lists what R1 would have started on had the switch been on when it
failed (`catch_up`, from the same reader as the automatic pass, `pending`); each one the person
ticks is started once at the turn-on, a person's start under its failure's own key
(`heal_notice.start_catch_up`), so the automatic pass never starts it again for that failure.
One left unticked, still open, offers ONE Start AI troubleshooting, a person's press (as for a
lab incident whose fix failed before this release). A switch whose ``at`` Mercury did not write
is never in force (`background.in_force`), so nothing starts on it.

Reads, and the start lines; nothing here asks the AI, holds a device, starts a job or sends
(tests/test_fixit_incident.py's scan of `modules/fixit/`). The pass that asks is the
notifier's (`heal_notice.run_fixit`).
"""

import calendar
import logging
import time

# The one name of a healed act whose tail then failed: its own failure, keyed
# ``tail:<decision>`` (`failures`), from the act row whose tail record flagged.
from modules.heal.act import TAIL_FAILED

log = logging.getLogger(__name__)

#: The background feature (`background.FEATURES`) and its finding kind.
FEATURE = "fixit_auto"
#: The decision outcomes after which no code fix of Mercury's exists for the problem (can't
#: fix, `heal.decisions.OUTCOMES`). A ``held`` decision is one only by `HELD_FOR_A_PERSON`.
DECISION_FAILURES = ("cant_fix",)
#: The guards whose hold R1 counts as no fix Mercury can run alone. Since C3909 (the operator,
#: 2026-11-17: "Self-healing On + an approved fix ... -> it runs. No person holds") guard 4
#: holds only a device Mercury must never change (observe-only, or Mercury's own host,
#: `refusal_for`), which the AI may still investigate; a golden departing from intent is a
#: can't-fix R1 starts on (C3910); guard 6 holds nothing. Guard 3, planned work, holds WITH a
#: time to check again: it waits as designed and is never a failure.
HELD_FOR_A_PERSON = (4,)
#: The act outcomes that are no verified fix (`heal.act.OUTCOMES`; only ``healed`` is one).
#: ``partial`` is one since C3870 (the operator, 2026-11-16: "Only 'healed' closes an
#: incident"): Mercury's fix ran and could not be confirmed, and its incident stays open. A
#: ``refused`` act refused by a guard that waits is not one (`heal.act.refusal_waits`, R2).
ACT_FAILURES = ("symptom_remains", "partial", "rolled_back", "failed", "refused",
                "interrupted")
#: Each tail step in the words a failure's reason names it by (`heal.act.TAIL_STEPS`).
TAIL_STEP_WORDS = {"saved": "the save to startup", "commit": "the golden commit",
                   "golden": "the read against its new golden"}
#: A plan run's outcomes that are a failure of an approved plan (`plan_engine.RECORD_STATE`).
PLAN_FAILURES = ("stopped", "failed")
#: The incident states in which a failure may still start an investigation.
OPEN = ("watching", "ready", "claimed", "standing")
#: A catch-up's start line's words (`heal_notice.start_catch_up`); its card adds who ticked it,
#: by display name (`section._status`: "started at turn-on by <name>").
CATCH_UP_WORDS = "started at turn-on"
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


#: The failures where no code fix exists for the problem (a can't-fix, a lost stream).
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


def eligible(failure: dict, sw: dict, heal: dict = None) -> str:
    """``""`` when *failure* starts an investigation by itself, else why not: the switch on
    (*sw*, `switch`) and the failure recorded after it went on.

    **In every mode of self-healing** (the operator, 2026-11-15, replacing 2026-11-14's "R1
    fires only while self-healing is in Auto"): "Drop 'R1 only while self-healing is in Auto':
    the AI only proposes, and nothing runs without a person's approval, so it investigates in
    Dry run too". *heal* (`heal_auto`) is no longer asked, and is kept only for its callers."""
    del heal
    if not sw.get("on"):
        return "automatic troubleshooting is off for this network"
    if failure["epoch"] < sw["epoch"]:
        return "it was recorded before automatic troubleshooting was turned on for this network"
    return ""


def key_of(kind: str, ident: str) -> str:
    """A failure's key: ``decision:<incident>``, ``held:<incident>``, ``act:<decision>``,
    ``tail:<decision>`` or ``run:<run id>`` (the
    shape a background trigger's finding id takes: no underscore, no space)."""
    return f"{kind}:{ident}"


def failures(network: str, *, open_ids=None) -> dict:
    """*network*'s failures of Mercury's fix, oldest first (the module's docstring):
    ``{"state", "failures", "error"}``, each ``{"key", "kind", "id", "incident", "device",
    "outcome", "epoch", "at"}``; *open_ids*, when given, keeps only those incidents'. A step log
    that cannot be read gives none, said.

    Not failures (the review, finding 4): an act whose decision a DAILY retry made (its
    incident's ``retries``, `heal.retry.finish`'s fix ``decision``: "a daily retry's never starts
    the AI"); and a ``refused`` act refused by a guard that waits (`heal.act.refusal_waits`,
    R2). An ``interrupted`` row (`interrupted.reap`'s, `steplog.record_interrupted`) is the act
    failure it is (finding 6)."""
    from modules.heal import act, incidents, steplog

    got = steplog.read(network)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "failures": [], "error": got["error"]}
    daily = {x.get("decision") for i in incidents.read(network).get("incidents") or []
             for rt in i.get("retries") or [] if rt.get("trigger") == "daily"
             for x in rt.get("fixes") or [] if x.get("fix") == "decision" and x.get("decision")}
    seen, out = set(), []
    for r in got["rows"]:
        inc = r.get("incident") or ""
        if not inc or (open_ids is not None and inc not in open_ids):
            continue
        row, outcome = r.get("row"), r.get("outcome") or ""
        if row == "interrupted":
            outcome = "interrupted"
        guard = r.get("guard") if isinstance(r.get("guard"), dict) else {}
        if row in ("act", "interrupted") and r.get("decision") in daily:
            continue
        if row == "decision" and outcome in DECISION_FAILURES:
            kind, ident = "decision", inc
        elif (row == "decision" and outcome == "held"
              and guard.get("guard") in HELD_FOR_A_PERSON):
            kind, ident = "held", inc
        elif (row in ("act", "interrupted") and outcome in ACT_FAILURES and r.get("decision")
              and not act.refusal_waits(r)):
            kind, ident = "act", r["decision"]
        elif (row == "act" and outcome == "healed" and r.get("decision")
              and ((r.get("records") or {}).get("tail") or {}).get("state") == "flagged"):
            # C3870: verified, and a step after it failed (its tail's second ``act`` row).
            kind, ident, outcome = "tail", r["decision"], TAIL_FAILED
        else:
            continue
        key = key_of(kind, ident)
        if key in seen:
            continue
        seen.add(key)
        epoch = float(r.get("epoch") or 0)
        tail = ((r.get("records") or {}).get("tail") or {}) if kind == "tail" else {}
        failed = act.tail_failed_step(tail)
        out.append({"key": key, "kind": kind, "id": ident, "incident": inc,
                    "device": r.get("device") or "", "outcome": outcome, "epoch": epoch,
                    "at": r.get("at") or (_iso(epoch) if epoch else ""),
                    "fix_kind": r.get("kind") or "",
                    **({"guard": {k: guard.get(k) for k in ("guard", "name", "words")}}
                       if kind == "held" else {}),
                    **({"step": TAIL_STEP_WORDS.get(failed, failed or "a step after it"),
                        "flag": tail.get("flag") or ""} if kind == "tail" else {})})
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


def capability_failures(network: str, incident, now: float = None) -> list:
    """C3733 (the operator, 2026-11-15): *incident*'s investigations that ended in a missing
    capability (`ai.missing`'s gap rows keyed to it) whose wanted step now exists, registered
    and deployed (`missing.available`): each a failure keyed by its row's id
    (``capability:<row id>``), so the incident restarts ONCE for it, whoever asks, within its
    caps (`incident.claim_start` takes the key; `heal_notice.run_fixit` asks). Its time is now:
    the capability became available to this pass. A read."""
    from modules.ai import missing

    at = time.time() if now is None else float(now)
    out, seen = [], set()
    for row in missing.for_incident(incident.id):
        rid = str(row.get("id") or "")
        if not rid or rid in seen or row.get("network") not in (network, None, ""):
            continue
        seen.add(rid)
        now_has = missing.available(row)
        if not now_has:
            continue
        out.append({"key": key_of("capability", rid), "kind": "capability", "id": rid,
                    "incident": incident.id, "device": incident.device,
                    "outcome": "available", "epoch": at, "at": _iso(at), "now": now_has,
                    "wanted": str(row.get("what") or "")})
    return out


def open_incidents(network: str) -> dict:
    """``{incident id: its record}`` for the network's incidents still open (`OPEN`)."""
    from modules.heal import incidents

    got = incidents.read(network)
    return {i["id"]: i for i in got["incidents"]
            if isinstance(i, dict) and i.get("id") and i.get("state") in OPEN}


def pending(network: str) -> dict:
    """R1's ONE reader of what may start an investigation on *network*: the automatic pass
    (`heal_notice.run_fixit`) and the catch-up at turn-on (`catch_up`) both read it, so the two
    never hold two definitions of a failure. ``{"state", "error", "incidents", "failed"}``,
    *incidents* ``[{"id", "found", "incident", "failures"}]``, each open incident with a page
    and its failures: its step log's (`failures`), its record's no code fix (`no_code_fix`),
    oldest first, then its approved plans that stopped (`plan_failures`). An open incident with
    a troubleshooting record and none of these is listed with none (its plans were read).
    *failed* names an incident whose plans could not be read. A read."""
    import os

    from modules import incident_page
    from modules.config import list_data_path
    from modules.fixit import incident as F
    from modules.fixit import section

    opened = open_incidents(network)
    got = failures(network, open_ids=set(opened))
    if got["state"] != "ok":
        return {"state": got["state"], "error": got["error"], "incidents": [], "failed": []}
    by = {}
    for f in got["failures"]:
        by.setdefault(f["incident"], []).append(f)
    from modules.heal import retry
    for iid, record in opened.items():
        lost = no_code_fix(record)
        if lost and lost["key"] not in {f["key"] for f in by.get(iid, [])}:
            by.setdefault(iid, []).append(lost)
            by[iid].sort(key=lambda f: f["epoch"])
        # A retry whose fixes all failed (the operator, 2026-11-16: switched on, or a new
        # script saved), each its own failure (``retry:<id>``); a daily retry's is none.
        again = retry.failures_of(record)
        if again:
            by.setdefault(iid, []).extend(again)
            by[iid].sort(key=lambda f: f["epoch"])
    folder = os.path.join(list_data_path(network), F.STORE_DIR)
    for iid in opened:
        if iid not in by and os.path.exists(os.path.join(folder, f"{iid}.json")):
            by[iid] = []
    out, failed = [], []
    for iid, fs in by.items():
        found = incident_page.resolve(network, iid)
        if found["found"] != "page":
            continue
        inc = section.incident_of(network, found)["incident"]
        if inc is None:
            continue
        try:
            fs = fs + plan_failures(network, inc) + capability_failures(network, inc)
        except Exception as exc:                      # said; the next read asks again
            failed.append(f"{iid}: {type(exc).__name__}: {exc}")
            continue
        out.append({"id": iid, "found": found, "incident": inc, "failures": fs})
    return {"state": "ok", "error": "", "incidents": out, "failed": failed}


#: Why an incident is listed at turn-on, in plain words: ``{(failure kind, outcome): words}``
#: (`failures`, `no_code_fix`, `plan_failures`), and the kind of reason each is (*failed*:
#: Mercury's fix ran and did not fix it; *no_fix*: no code fix of Mercury's exists for it).
#: A hold (``held``) is said from its guard: "held by guard <n>: <its words>" (`catch_up`).
WHY = {("decision", "cant_fix"): ("no_fix", "Mercury has no fix of its own for it"),
       ("decision", "no_code_fix"): ("no_fix", "no code fix exists for a lost telemetry stream"),
       ("act", "symptom_remains"): ("failed", "Mercury's fix ran and the problem remained"),
       # C3870 (the operator, 2026-11-16): its incident stays open on these too.
       ("act", "partial"): ("failed", "Mercury's fix ran and could not be confirmed"),
       ("tail", TAIL_FAILED): ("failed", "Mercury's fix verified, and a step after it failed "
                                         "({step})"),
       ("act", "rolled_back"): ("failed", "Mercury's fix was rolled back"),
       ("act", "failed"): ("failed", "Mercury's fix failed"),
       ("act", "refused"): ("failed", "Mercury's fix was refused before it sent anything"),
       ("act", "interrupted"): ("failed", "Mercury's fix was interrupted"),
       ("run", "stopped"): ("failed", "an approved plan stopped at a step"),
       ("run", "failed"): ("failed", "an approved plan failed"),
       # C3733: an investigation that lacked a step, which now exists.
       ("capability", "available"): ("no_fix", "a step its last investigation lacked now "
                                               "exists"),
       # The retry policy (the operator, 2026-11-16, `heal.retry`): tried again, failed again.
       ("retry", "switched_on"): ("failed", "Mercury's fixes were tried again when "
                                            "self-healing was switched on, and failed"),
       ("retry", "script_saved"): ("failed", "Mercury's fixes were tried again when a new "
                                             "script was saved, and failed")}


def catch_up(network: str, now: float = None, bound_s: float = None) -> dict:
    """What turning ``fixit_auto`` on starts on, for the person to tick (the operator,
    2026-11-15): every open incident R1 would have started an investigation on had the switch
    been on when its fix failed, from R1's one reader (`pending`), whatever the switch says
    now. ``{"state", "error", "items", "failed"}``, *items* ``[{"id", "device", "title",
    "why", "why_kind", "failure", "incident", "found"}]``, *failure* the one R1 starts on (the
    oldest of its failures no start has taken, as `heal_notice.run_fixit` picks it).

    An incident is left out when no failure of it is new: each was taken by a start already
    (the automatic pass's, or an earlier turn-on's), or the AI was asked about it since (a
    person's start or an AI answer newer than every untaken failure), or an investigation is in
    flight (`in_flight`, *bound_s*). A hold by a guard a person resolves is in it
    (`HELD_FOR_A_PERSON`); a guard that waits, or a working decision (a dry run's would-heal),
    never is. A read."""
    from modules import bluf
    from modules.fixit import incident as F

    at = time.time() if now is None else float(now)
    got = pending(network)
    if got["state"] != "ok":
        return {"state": got["state"], "error": got["error"], "items": [], "failed": []}
    items, failed = [], list(got["failed"])
    for p in got["incidents"]:
        inc = p["incident"]
        rec = F.read(inc)
        if rec["state"] == "unreadable":
            failed.append(f"{p['id']}: its troubleshooting record cannot be read "
                          f"({rec['error']})")
            continue
        asked = max((float(ln.get("epoch") or 0) for ln in rec["lines"]
                     if ("start" in ln and ln.get("state") == "started")
                     or ("proposal" in ln and ln.get("source") == "ai")), default=None)
        # C3872: only a start that started takes its key; a refused one is listed again.
        have = {ln.get("start") for ln in rec["lines"] if "start" in ln
                and ln.get("state") == "started"}
        new = [f for f in p["failures"] if f["key"] not in have
               and (asked is None or f["epoch"] > asked)]
        if not new or (bound_s and in_flight(inc, at, bound_s)):
            continue
        f = new[0]
        kind, words = WHY.get((f["kind"], f["outcome"]), ("failed", "Mercury's fix failed"))
        # A tail's failure names its step (`failures`' ``step``).
        words = words.replace("{step}", f.get("step") or "a step after it")
        if f["kind"] == "held":
            g = f.get("guard") or {}
            kind, words = "held", (f"held by guard {g.get('guard')}: "
                                   f"{g.get('words') or g.get('name') or 'a person resolves it'}")
        items.append({"id": p["id"], "device": inc.device, "title": bluf.what_of(p["found"]),
                      "why": words, "why_kind": kind, "failure": f, "incident": inc,
                      "found": p["found"]})
    return {"state": "ok", "error": "", "items": items, "failed": failed}


def taken(incident) -> set:
    """The failure keys *incident*'s record has taken: its ``started`` start lines alone
    (C3872: a refused start, capped or off, records its refusal and spends no key)."""
    from modules.fixit import incident as F

    return {ln.get("start") for ln in F.starts(incident)["starts"]
            if ln.get("state") == "started"}


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
