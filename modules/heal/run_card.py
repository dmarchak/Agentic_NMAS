"""A run's outcome, drawn where the run was: the card a device's page reopens for a
self-healing run and for a telemetry re-subscribe, and the Finished entry of a run whose record
is all that is left of it (the operator, 2026-11-11, after a re-subscribe of that day: "the
run disappeared from 'running' with NO outcome shown, the row unchanged, and nothing under
'Finished, not opened yet'"; "Every operation and heal ends with a visible outcome on its card
and under 'Finished' (success / partial / failed, with the steps taken)").

**Why nothing was drawn.** The In progress chip lists a finished run only for a job that named
its device and its card (`capture_job.card_jobs`, C537), and a device's page reopens only such a
job's card (`device_actions.REOPENS`). A re-subscribe's job named neither, and a heal's named
no card, so each left the running list at its end with nothing in its place; and a job is kept
in memory, so after Mercury restarted no finished run was listed at all, whatever its record
said.

**What is built, for every run, never for one operation:**
- the job a run starts names its device and its card (``heal_run``, ``resubscribe``), so
  the one mechanism (C537) lists it under Finished for each person until they open it, and
  the device's page reopens its card: the outcome first (its level never green over a partial
  or a failure), then the steps taken, drawn by THE stepper from the run's own recorded steps
  (`run_stepper.from_record`);
- a run whose job this server no longer holds (a restart, or more than `capture_job.KEEP_S`
  ago) is listed from its RECORD (`finished_records`: the operations' record store,
  `privileged.runs`), for the person who started it, for `FINISHED_KEEP_S` after it started,
  until they open it or dismiss it; that is kept per person (`seen_runs`, C3081), so a
  restart lists it no more.

A heal that Mercury started (the policy's, no person) is listed for every person, as every
job's result is, until each opens it; its durable outcome is its incident's (History, and a
Needs attention row for every outcome that is not healed). A can't-fix is a DECISION, never a
run: nothing ran, so nothing is listed as finished; its outcome is its Needs attention row,
which stays until a person acknowledges it or a later heal ends healed, and its steps taken are
drawn there (`steps_card`) and sent in its notice (`heal_notice.facts`).

A READ throughout: it reads this process's jobs and the networks' records, and writes nothing.
"""

import logging
import os
import re
import threading
import time

log = logging.getLogger(__name__)

#: The cards (`device_actions.REOPENS`), as the In progress list names them.
HEAL_CARD, RESUB_CARD = "heal_run", "resubscribe"
#: How long a run's record keeps it under Finished for the person who started it, counted from
#: its start: a working day and the night after, so a run started in the evening is still
#: listed in the morning. Not a timeout: nothing waits on it.
FINISHED_KEEP_S = 86400
#: The outcomes drawn green: an ALLOWLIST. Every other outcome is amber or red.
HEALED = ("healed", "bounced", "cleared", "dampened")
#: The outcomes drawn amber: something landed, and not all of it is shown true.
PARTLY = ("symptom_remains", "partial", "unverified", "still_flapping", "not_formed",
          "reverted", "repaired", "not_back", "reset")
#: A decision's results that end it without a heal (drawn red on its step).
DECISION_BAD = ("cant_fix", "held", "halted", "off")
#: A decision's results that are its answer, not a failure.
DECISION_GOOD = ("heal", "would_heal", "propose", "nothing", "deferred")

_opened: dict = {}
_lock = threading.Lock()


def level_of(outcome: str) -> str:
    """A heal's outcome as a level: ``ok`` only for an outcome on `HEALED`."""
    return "ok" if outcome in HEALED else "warn" if outcome in PARTLY else "danger"


def _declared(steps: list, approved: bool = False) -> tuple:
    """The steps the run declared, chosen by the steps it recorded: the first of the heal
    operations' tables that names every recorded step; else the recorded keys themselves, in
    order, so nothing recorded is hidden and nothing unrecorded is drawn."""
    keys = [s.get("step") for s in steps if isinstance(s, dict)]
    for table, labels in heal_tables(approved):
        if set(keys) <= {k for k, _w in table}:
            return tuple(table), labels
    return tuple((k, str(k)) for k in dict.fromkeys(keys) if k), {}


def heal_tables(approved: bool = False) -> tuple:
    """The heal operations' declared steps, each with its short labels: ``((STEPS,
    STEP_LABELS), ...)``, an act's first (an approved proposal's first when *approved*)."""
    from modules.heal import act, bounce, propose, session_clear

    first = ((propose.STEPS, propose.STEP_LABELS), (act.STEPS, act.STEP_LABELS))
    return (first if approved else first[::-1]) + (
        (bounce.STEPS, bounce.STEP_LABELS), (session_clear.STEPS, session_clear.STEP_LABELS))


def _drawn(steps: list) -> list:
    """*steps* as a screen draws them (board E2a): each step's recorded words with every
    person named by display name (`display_names.people`: "as the policy set by <identity>"
    reads "as the policy set by <name>"). Copies; the recorded steps are never rewritten."""
    from modules import display_names

    return [dict(s, words=display_names.people(s.get("words") or ""))
            if isinstance(s, dict) and s.get("words") else s for s in steps]


# ── The heal's five stages (the operator, 2026-11-12) ───────────────────────────────────────

#: What was seen before the decision, from the incident's own record: it opened on a trigger,
#: then its grace period was waited out (the detect loop's, which is no job: C3124).
DETECT_STEPS = (("opened", "An incident opened: what was seen on the device"),
                ("grace", "Wait out the grace period, reading the device again"))
DETECT_LABELS = {"opened": "Open incident", "grace": "Wait out grace"}
#: The act's step keys under each of its stages: an act's, an approved proposal's, a bounce's
#: and a clear's own (`heal_tables`). A step none names joins the stage of the step before it.
FIXING = ("take", "stops", "read", "plan", "authorise", "hash", "hold", "pre-read", "route",
          "window", "send", "watch", "apply", "repair", "rollback")
CHECKING = ("intent", "reset", "symptom", "saved", "golden", "confirm", "verify", "stable")


def heal_stage_table(act_prefix: str = "") -> tuple:
    """The heal's stages (the operator, 2026-11-12: "The stepper shows FIVE stages: Detected →
    Decided → Fixing → Checking → Done"), each naming the card's steps under it: the
    detection's (``x-``), the decision's (``d-``, `decide.STEPS`: "They were done by the
    detection job: draw them done, with their times, as one continuous run") and the act's
    (*act_prefix* before each of its keys)."""
    from modules.heal import decide

    return (("detected", "Detected", ("x-opened", "x-grace")),
            ("decided", "Decided", tuple("d-" + k for k, _w in decide.STEPS)),
            ("fixing", "Fixing", tuple(act_prefix + k for k in FIXING)),
            ("checking", "Checking", tuple(act_prefix + k for k in CHECKING)),
            ("done", "Done", (act_prefix + "record",)))


#: What the first trigger was, as the Detected stage says it.
SEEN_WORDS = {"config_change": "{device}'s configuration changed outside Mercury",
              "drift": "{device} departed from its golden",
              "alert": "An alert fired on {device}",
              "adjacency": "An adjacency went down on {device}",
              "adjacency_log": "{device} logged an adjacency drop",
              "duplicate_router_id": "{device} logged a duplicate router-id"}
#: A decision's outcome, as the Decided stage leads with it.
DECIDED_WORDS = {"heal": "Heal", "would_heal": "Would heal (dry run: nothing sent)",
                 "propose": "Propose a fix to a person", "cant_fix": "Can't fix",
                 "nothing": "Nothing to heal"}
#: What the act's running step is doing, as its stage's sentence.
RUNNING_WORDS = {"take": "Checking {device} again before the fix…",
                 "stops": "Checking {device} again before the fix…",
                 "read": "Reading {device} again before the fix…",
                 "plan": "Recomputing the program from {device}'s read…",
                 "authorise": "Giving each removal the policy's reason…",
                 "apply": "Applying {lines} to {device}…",
                 "intent": "Checking {device} is at intent…",
                 "symptom": "Waiting for {device}'s symptom to clear",
                 "saved": "Saving {device}'s startup…",
                 "golden": "Reading {device} against its new golden…",
                 "record": "Recording the outcome…"}


def _lines_words(n) -> str:
    return f"{n} line{'s' if n != 1 else ''}" if isinstance(n, int) and n > 0 else "the fix"


def recorded_by(actor: str, kind: str = "policy") -> str:
    """Who a self-heal is by, as a RECORD names it: `by_words` with the person's identity as
    recorded, for History's rows (the operator, 2026-11-12: "3. One attribution for one heal:
    the receipt, self-healing and measured rows all read "Mercury's self-healing · policy set
    by <the operator's display name>". Not "heal to intent", and not "<the operator's display
    name> (by the policy they confirmed)"."). A
    screen draws it through the `people` filter, so it reads the display name, and the
    identity itself is kept under "The identity as recorded"; an export keeps the actor."""
    from modules.nsot.receipts import HEAL_DOER

    lead = "approved by" if kind == "approval" else "policy set by"
    return f"{HEAL_DOER} · {lead} {actor or 'nobody recorded'}"


def by_words(actor: str, kind: str = "policy") -> str:
    """Who a self-heal is by (the operator, 2026-11-12: "A self-heal is never "by <person>" or
    "started by you": the chip, the banner and the card read "by Mercury's self-healing ·
    policy set by <display name>""): Mercury's own, and the person whose decision it ran
    under, by display name (`identity.display_name`), never their identity. *kind*
    ``approval``: an approved proposal, which runs once a person approved it. The same words
    as History's (`recorded_by`), the name in place of the identity."""
    from modules import identity

    return recorded_by(identity.display_name(actor) if actor else "", kind)


def entry_by(entry: dict) -> tuple:
    """``(actor, kind)`` for a step-log entry (`steplog.incidents`'): the policy's setter as
    the act recorded them (``policy_by``), or the person an approved proposal ran as (its
    ``by``, a person's identity), else the policy's own setter (a decision that never acted,
    or a row written before ``policy_by`` was kept)."""
    if entry.get("policy_by"):
        return entry["policy_by"], "policy"
    by = str(entry.get("by") or "")
    # The act's own words when it ran as the policy (`steplog.policy_words`, or a withdrawal's
    # "heal to intent"); any other ``by`` is the person who approved it (`propose.approve`).
    if by and "(policy set by" not in by and not by.startswith("heal to intent"):
        return by, "approval"
    return (entry.get("policy") or {}).get("by") or "", "policy"


def job_by(job: dict) -> str:
    """`by_words` for a self-healing job (`capture_job`'s, its card ``heal_run``): its actor
    is the policy's setter, or the person who approved a proposal (``actor_kind``)."""
    return by_words(job.get("actor") or "", job.get("actor_kind") or "policy")


def _detected_phase(decision: dict, incident: dict = None, now: float = None) -> dict:
    """What was seen before the decision, as the first phase (``x-``), from the incident's own
    record: when it opened and on what, then the grace period from then until it settled.
    With no incident held (*incident* empty), the decision's own triggers, done, with no time:
    nothing is invented."""
    from modules import display_names, run_stepper

    inc = incident or {}
    triggers = [t for t in inc.get("triggers") or [] if isinstance(t, dict)]
    said = (triggers[0].get("words") if triggers else
            "; ".join(str(t) for t in (decision.get("triggers") or [])[:1])) or \
        "an incident opened"
    steps = [dict({"step": "opened", "result": "ok", "words": display_names.people(said)},
                  **({"at": inc["opened_at"]} if inc.get("opened_at") else {}))]
    settled = inc.get("settled") or {}
    if settled.get("at"):
        steps.append({"step": "grace", "result": "ok", "began": inc.get("opened_at") or "",
                      "at": settled["at"],
                      "words": display_names.people(settled.get("words") or "settled")})
    return run_stepper.from_record(DETECT_STEPS, steps, ended=True, now=now, prefix="x-",
                                   labels=DETECT_LABELS)


def _incident(network: str, incident_id: str) -> dict:
    """The incident *incident_id* as its store holds it (a closed one is kept), or {}."""
    from modules.heal import incidents

    if not incident_id:
        return {}
    try:
        got = incidents.read(network)
    except Exception as exc:                          # noqa: BLE001 (the decision's words stand)
        log.info("run_card: %s's incidents could not be read: %s", network, exc)
        return {}
    return next((i for i in got["incidents"] if i.get("id") == incident_id), {})


def heal_stages(card: dict, *, host: str, facts: dict, ended: bool, now: float = None,
                nested: dict = None, act_prefix: str = "") -> dict:
    """A heal's *card* (`run_stepper.record_card`'s) as its five stages (`heal_stage_table`),
    each its own sentence from *facts*: ``kind``, the first trigger's; ``decision``,
    ``units`` and ``lines``, the decision's outcome, units and program length; ``outcome``,
    the act's; ``since``, when it was first seen. *nested*: the deploy's stages, under Apply
    ("ONE stepper: the deploy's stages belong INSIDE "Apply" (expanding), not as a second
    stepper")."""
    from modules import run_stepper
    from modules.heal import act, said, steplog

    device = host or "the device"
    lines = _lines_words(facts.get("lines"))

    def sentence(g):
        lead = str((g["lead"] or {}).get("key") or "")[len(act_prefix):]
        if g["state"] == "running":
            return RUNNING_WORDS.get(lead, "").format(device=device, lines=lines)
        if g["key"] == "done" and g["state"] in ("done", "partial", "failed"):
            outcome = facts.get("outcome") or ""
            if not outcome:
                return ""
            words = act.OUTCOME_WORDS.get(outcome) or steplog.mark(outcome,
                                                                   facts.get("act_kind") or "")
            end = max((run_stepper._epoch(s.get("at")) or 0 for s in g["steps"]), default=0)
            took = end - facts["since"] if facts.get("since") and end else None
            return run_stepper._first_said(words) + (
                f" in {run_stepper.duration_words(took)}" if took and took >= 1 else "")
        if g["state"] != "done":
            return ""
        if g["key"] == "detected":
            return SEEN_WORDS.get(facts.get("kind") or "", "").format(device=device)
        if g["key"] == "decided":
            head = DECIDED_WORDS.get(facts.get("decision") or "", "")
            fixes = said.fixes_words(facts.get("units") or []) if facts.get("units") else ""
            return (f"{head}: {fixes}" if head and fixes and facts.get("decision") in (
                "heal", "would_heal", "propose") else head)
        if g["key"] == "fixing":
            sent = any(s["key"] == act_prefix + "apply" and s["state"] == "done"
                       for s in g["steps"])
            return f"Applied {lines} to {device}" if sent else ""
        if g["key"] == "checking":
            gone = any(s["key"] == act_prefix + "symptom" and s["state"] == "done"
                       for s in g["steps"])
            return f"{device} at intent" + ("; its symptom gone" if gone else "")
        return ""

    return run_stepper.stages(card, heal_stage_table(act_prefix), ended=ended, now=now,
                              sentence=sentence, nested=nested)


def _facts(decision: dict, incident: dict, outcome: str = "", act_kind: str = "") -> dict:
    """What a heal's stage sentences say, from its decision and its incident (`heal_stages`)."""
    from modules import run_stepper

    triggers = [t for t in (incident or {}).get("triggers") or [] if isinstance(t, dict)]
    program = decision.get("program")
    return {"kind": (triggers[0].get("kind") if triggers else "") or "",
            "decision": decision.get("outcome") or "",
            "units": [u for u in decision.get("units") or [] if isinstance(u, dict)],
            "lines": len(program) if isinstance(program, list) else None,
            "outcome": outcome, "act_kind": act_kind or decision.get("kind") or "",
            "since": (incident or {}).get("opened_epoch") or run_stepper._epoch(
                (incident or {}).get("opened_at")) or run_stepper._epoch(decision.get("at"))}


def act_phase(steps: list, *, ended: bool, approved: bool = False, now: float = None,
              prefix: str = "", host: str = "") -> dict:
    """An act's recorded *steps* on the stepper (`run_stepper.from_record`): a symptom read
    gone (or none named: `act.read_symptom`'s states) and a record's own good outcomes are
    done; a symptom still present, a rollback and a can't-fix are failed; anything else (a
    symptom unreadable, a save held) is amber. Each column says the operation's short label
    for *host*."""
    from modules import run_stepper

    table, labels = _declared(steps, approved)
    return run_stepper.from_record(
        table, _drawn(steps), ended=ended, now=now, prefix=prefix,
        good=HEALED + ("gone", "none"),
        bad=("present", "rolled_back", "interrupted", "rejected", "cant_fix"),
        conditional=("repair", "rollback", "reset"),
        labels=run_stepper.labels_for(labels, device=host or "the device"))


def decision_phase(steps: list, *, now: float = None, prefix: str = "d-",
                   host: str = "") -> dict:
    """A decision's recorded steps (`steplog.decision_steps`) against `decide.STEPS`."""
    from modules import run_stepper
    from modules.heal import decide

    return run_stepper.from_record(
        decide.STEPS, _drawn(steps), ended=True, now=now, prefix=prefix, good=DECISION_GOOD,
        bad=DECISION_BAD,
        labels=run_stepper.labels_for(decide.STEP_LABELS, device=host or "the device"))


def steps_card(host: str, entry: dict) -> dict:
    """An incident's steps taken (a step-log entry's, `steplog.incidents`), for its Needs
    attention row: the decision's steps, then the act's when it had one, on THE stepper, the
    step it stopped at leading. None for an entry with no steps."""
    from modules import run_stepper

    steps = [s for s in entry.get("steps") or [] if isinstance(s, dict)]
    if not steps:
        return None
    decided = [s for s in steps if s.get("row") in ("decision", None)]
    acted = [s for s in steps if s.get("row") not in ("decision", None)]
    phases = [decision_phase(decided, host=host)] if decided else []
    if acted:
        phases.append(act_phase(acted, ended=entry.get("state") != "applying", prefix="a-",
                                host=host))
    outcome = entry.get("outcome") or ""
    # Its stages, as the heal's card draws them (C3163): the decision's, then the act's when it
    # had one; what was seen is the row's own cause, said above it (so no Detected here), and
    # the failed stage names its step.
    ended = entry.get("state") != "applying"
    card = run_stepper.record_card(
        host, f"The steps self-healing took on {host}", phases, ended=ended,
        level="ok" if outcome in HEALED + DECISION_GOOD else level_of(outcome),
        key=f"heal-steps-{entry.get('incident') or host}",
        summarised=True)                              # the row's cause says why, above it
    acted_outcome = outcome if acted else ""
    return heal_stages(card, host=host, ended=ended, act_prefix="a-", facts={
        "kind": "", "decision": next((s.get("result") for s in reversed(decided)
                                      if s.get("step") not in ("record",)), "") or "",
        "units": [], "lines": None, "outcome": acted_outcome,
        "act_kind": entry.get("kind") or "", "since": None})


def heal_card(network: str, host: str, job_id: str, got="unread") -> dict:
    """The self-healing card for its job (`capture_job.get`, or None): running, its outcome
    with the steps taken, the reason its job raised, or unknown here."""
    from modules import run_stepper
    from modules.heal import steplog
    from modules.nsot import capture_job

    got = capture_job.get(job_id) if got == "unread" else got
    card = {"op": HEAL_CARD, "host": host, "list": network, "job": job_id}
    if got is None:
        return dict(card, state="unknown")
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(got.get("started_at") or 0))
    # Who it is by, in words that name no person by identity (C3161): Mercury's own, under
    # the policy its setter confirmed (or the proposal a person approved).
    card.update(started=started, by=job_by(got))
    if got["state"] == "running":
        # The run's REAL steps as they stand now (`op_progress.run_of`: the act's own list),
        # after what was seen and its decision's; while it applies, the deploy's stages from
        # the device's hold, under Apply (C3160).
        from modules import op_progress
        card["state"] = "running"
        live = op_progress.run_of(job_id)
        if live is not None:
            phases, facts = _decided(network, live["run"], host)
            phases.append(act_phase(live["steps"], ended=False, host=host))
            stages = _stages(network, host)
            card["steps"] = heal_stages(
                run_stepper.record_card(host, f"Self-healing on {host}", phases,
                                        ended=False, key=f"heal-run-{job_id[:12]}"),
                host=host, facts=facts, ended=False,
                nested={"apply": stages} if stages else None)
        return card
    if got["state"] == "failed":
        return dict(card, state="failed", error=got.get("error") or "no reason was recorded")
    result = (got.get("payload") or {}).get("result") or {}
    outcome = result.get("outcome") or "failed"
    steps = [s for s in result.get("steps") or [] if isinstance(s, dict)]
    phases, facts = _decided(network, result.get("decision") or "", host)
    phases.append(act_phase(steps, ended=True, host=host))
    level = level_of(outcome)
    facts.update(outcome=outcome, act_kind=result.get("kind") or facts.get("act_kind") or "")
    return dict(card, state="result", level=level, outcome=outcome,
                words=steplog.mark(outcome, result.get("kind") or ""),
                steps=heal_stages(
                    run_stepper.record_card(host, f"Self-healing on {host}", phases,
                                            ended=True, level=level,
                                            key=f"heal-run-{job_id[:12]}"),
                    host=host, facts=facts, ended=True),
                finished=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime(got.get("finished_at") or 0)))


#: A heal run's id, as History's row and the device page's ``?result=`` name it: its
#: incident's (``hi-``) or one of its decisions' (``hd-``), `incidents.new_id`'s and
#: `decisions.record`'s shape.
HEAL_RUN_ID = re.compile(r"h[id]-[0-9a-f]{12}")
#: An entry's states in which an act ran (`steplog.incidents`): only these are a RUN. A
#: decision alone (a dry run, a can't-fix, a proposal) ran nothing, so it has no run card.
ACTED = ("done", "applying", "interrupted")


def acted_entry(entry: dict) -> bool:
    """Whether step-log *entry* is a run (its act started), so its card can be reopened."""
    return entry.get("state") in ACTED


def record_heal_card(network: str, host: str, entry: dict) -> dict:
    """A heal's card drawn from its RECORD, the step log's entry (`steplog.incidents`), as its
    job's card draws a finished heal (`heal_card`): the same five stages, from what was seen
    and the decision through the act's every step to its outcome, with who it is by
    (`by_words`). The operator, 2026-11-12: "1. Every operation row in History (device and
    fleet) has "Open the card", which opens that run's card with the five-stage stepper. Same
    pattern for every operation." A job is kept in memory (C3080), so the card a History row
    opens is drawn from what is kept on disk: it reopens after any restart, at any age.

    The act's steps are its acting decision's (an incident checked again later holds more than
    one); an entry whose act started and recorded no end (``applying``, no heal job holding
    the device: its job ended with the process) is drawn as ended inside its last step, never
    as still running."""
    from modules import run_stepper
    from modules.heal import steplog

    steps = [s for s in entry.get("steps") or [] if isinstance(s, dict)]
    acted = [s for s in steps if s.get("row") in ("started", "act", "interrupted")]
    did = (acted[-1].get("decision") if acted else "") or (
        (entry.get("decisions") or [""])[-1])
    acted = [s for s in acted if not did or s.get("decision") in (did, "")]
    outcome = entry.get("outcome") or ""
    stopped = entry.get("state") == "applying"
    phases, facts = _decided(network, did, host)
    phases.append(act_phase(acted, ended=True, host=host))
    level = "danger" if stopped else level_of(outcome)
    words = ("ended before it recorded its outcome" if stopped else
             steplog.mark(outcome, entry.get("kind") or ""))
    facts.update(outcome="" if stopped else outcome,
                 act_kind=entry.get("kind") or facts.get("act_kind") or "")
    actor, kind = entry_by(entry)
    times = [t for t in (run_stepper._epoch(s.get("began") or s.get("at")) for s in acted)
             if t is not None]
    started = (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(min(times))) if times
               else entry.get("first_at") or entry.get("at") or "")
    run = entry.get("incident") or did
    return {"op": HEAL_CARD, "host": host, "list": network, "job": "", "run": run,
            "state": "result", "level": level, "outcome": outcome, "words": words,
            "by": by_words(actor, kind), "started": started,
            "finished": entry.get("at") or "",
            "steps": heal_stages(
                run_stepper.record_card(host, f"Self-healing on {host}", phases, ended=True,
                                        level=level, key=f"heal-run-{run[-12:]}"),
                host=host, facts=facts, ended=True)}


def named_heal(network: str, host: str, run_id: str):
    """``(card, job)`` as `named_record` gives them, for the heal run *run_id* names on *host*
    (its incident's id or one of its decisions'): its card from its record
    (`record_heal_card`), and what a job row would say of it; a heal job still running on
    *host* for that decision draws its live card instead (`heal_card`). None when *run_id* is
    no heal's id, the step log holds no run of it on *host*, or the log cannot be read."""
    from modules.heal import steplog
    from modules.nsot import capture_job

    if not HEAL_RUN_ID.fullmatch(run_id or ""):
        return None
    got = steplog.incidents(network, device=host)
    if got["state"] == "unreadable":
        log.info("run_card: %s's step log could not be read: %s", network, got["error"])
        return None
    entry = next((e for e in got["entries"] if acted_entry(e) and (
        e.get("incident") == run_id or run_id in (e.get("decisions") or []))), None)
    if entry is None:
        return None
    if entry.get("state") == "applying":
        job = capture_job.for_device(network, host, HEAL_CARD)
        if job and job["state"] == "running":
            return heal_card(network, host, job["job"]), dict(job, card=HEAL_CARD)
    card = record_heal_card(network, host, entry)
    return card, {"card": HEAL_CARD, "actor": entry_by(entry)[0], "state": "done"}


def _decision_steps(network: str, decision: dict) -> list:
    """The decision's steps as the detection job recorded them (the operator, 2026-11-12:
    "They were done by the detection job: draw them done, with their times, as one continuous
    run"). The decision's own store keeps no steps (`decide.run` writes them to the step log,
    `steplog.record_decision`), so a card that read them there drew every step before the
    outcome as not needed; they are read from the step log's decision row, each stamped with
    that row's time where it keeps none of its own. A decision the step log does not hold is
    drawn from its own record, as before."""
    from modules.heal import steplog

    try:
        got = steplog.of_decision(network, decision.get("id") or "")
    except Exception as exc:                          # noqa: BLE001 (its own record stands)
        log.info("run_card: %s's step log could not be read: %s", network, exc)
        got = {"rows": []}
    row = next((r for r in got.get("rows") or [] if r.get("row") == "decision"), None)
    if row is None or not row.get("steps"):
        return [dict(s, at=s.get("at") or decision.get("at") or "")
                for s in steplog.decision_steps(decision)]
    return [dict(s, at=s.get("at") or row.get("at") or "") for s in row["steps"]
            if isinstance(s, dict)]


def _decided(network: str, decision_id: str, host: str = "") -> tuple:
    """``(phases, facts)``: what was seen, then the decision that started a heal, as the first
    phases of its stepper (the incident's record, `_detected_phase`; the decision's recorded
    steps, `_decision_steps`), and what their stages say (`_facts`); no phase when the
    decision cannot be read: the act's own steps are still drawn."""
    from modules.heal import decisions

    if not decision_id:
        return [], _facts({}, {})
    try:
        decision = decisions.find(network, decision_id)
    except Exception as exc:                          # noqa: BLE001 (the act's steps stand)
        log.info("run_card: %s's decision %s could not be read: %s", network, decision_id, exc)
        return [], _facts({}, {})
    incident = _incident(network, decision.get("incident") or "")
    return ([_detected_phase(decision, incident),
             decision_phase(_decision_steps(network, decision), host=host)],
            _facts(decision, incident))


def _stages(network: str, host: str) -> list:
    """The deploy's stages while a heal applies, from the device's hold (the deploy's own
    stepper rows, `device_actions.job_steps`), or [] when the heal is not holding the device
    as a deploy now."""
    from modules import device_actions
    from modules.nsot import device_ops

    try:
        holder = device_ops.holder(network, host)
    except OSError:
        return []
    if not holder or holder.get("operation") != "deploy":
        return []
    return device_actions.job_steps("deploy", network, host, holder=holder)


# ── A re-subscribe's run, from its record ───────────────────────────────────────────────────

#: A record's state (`resubscribe.RECORD_STATE`) -> its level: only ``done`` is green.
RECORD_LEVELS = {"done": "ok", "unverified": "warn"}


def record_level(rec: dict) -> str:
    return RECORD_LEVELS.get(rec.get("state") or "", "danger")


def record_steps(host: str, rec: dict, *, now: float = None, labels: dict = None,
                 summarised: bool = False) -> dict:
    """A re-subscribe's (or a Re-add the receiver's) recorded steps on THE stepper, the step
    to act on leading: `run_stepper.record_card` over the record's own ``steps``, against the
    steps the operation declares."""
    from modules import run_stepper
    from modules.heal import resubscribe as R

    ended = rec.get("state") != "running"
    declared = R.READD_STEPS if rec.get("key") == R.READD_KEY else R.STEPS
    subs = [s.get("sub") for s in rec.get("subscriptions") or [] if isinstance(s, dict)]
    phase = run_stepper.from_record(declared, rec.get("steps") or [], ended=ended, now=now,
                                    conditional=("rollback",),
                                    cut_short=rec.get("state") == "stopped",
                                    labels=labels or R.step_labels(host, subs))
    card = run_stepper.record_card(
        host, f"The re-subscribe on {host}", [phase], ended=ended,
        level=record_level(rec) if ended else "", key=f"resub-run-{str(rec.get('id'))[-12:]}",
        summarised=summarised)
    return resub_stages(card, host=host, subs=subs, outcome=rec.get("outcome") or "",
                        ended=ended, now=now)


#: A re-subscribe's stages (the operator, 2026-11-12: "Apply the same five-stage pattern to
#: every operation's stepper (re-subscribe, deploys…), with stage names that fit each"):
#: planned and read before anything is sent, the receivers removed and the wait after, added
#: back, the stream checked, done. A Re-add the receiver removes nothing, so it has four.
RESUB_STAGES = (("planned", "Planned", ("plan", "hash", "hold", "started", "before")),
                ("removing", "Removing", ("remove", "wait", "rollback")),
                ("re-adding", "Re-adding", ("re-add",)),
                ("checking", "Checking", ("verify",)),
                ("done", "Done", ("record",)))
#: What a re-subscribe's running step is doing, as its stage's sentence.
RESUB_RUNNING = {"plan": "Reading each receiver from {device}'s committed intent…",
                 "hash": "Comparing each program with the one previewed…",
                 "hold": "Holding {device}…", "started": "Recording the run before it sends…",
                 "before": "Reading {device} before anything is sent…",
                 "remove": "Removing {subs}'s receiver…",
                 "wait": "Waiting after the removal",
                 "re-add": "Adding {subs}'s receiver back…",
                 "verify": "Checking {subs}'s stream is back",
                 "rollback": "Adding back what was removed…",
                 "record": "Recording the outcome…"}
RESUB_DONE = {"planned": "Each receiver from {device}'s committed intent; {device} held",
              "removing": "{subs}'s receiver removed", "re-adding": "{subs}'s receiver back"}


def resub_stages(card: dict, *, host: str, subs: list, outcome: str, ended: bool,
                 now: float = None) -> dict:
    """A re-subscribe's (or a Re-add's) *card* as its stages (`RESUB_STAGES`), each its own
    sentence; Done says the outcome and how long the run took."""
    from modules import run_stepper
    from modules.heal import resubscribe as R

    subs = [str(s) for s in subs or [] if str(s)]
    named = (", ".join(subs) if 0 < len(subs) <= 2 else
             f"{len(subs)} streams" if subs else "each stream")
    fields = {"device": host or "the device", "subs": named}

    def sentence(g):
        lead = str((g["lead"] or {}).get("key") or "")
        if g["state"] == "running":
            return RESUB_RUNNING.get(lead, "").format(**fields)
        if g["key"] == "done" and g["state"] in ("done", "partial", "failed") and outcome:
            words = R.OUTCOME_WORDS.get(outcome, outcome.replace("_", " "))
            took = _run_took(card)
            return run_stepper._first_said(words) + (
                f" in {run_stepper.duration_words(took)}" if took and took >= 1 else "")
        if g["state"] == "done" and g["key"] in RESUB_DONE:
            return RESUB_DONE[g["key"]].format(**fields)
        return ""

    return run_stepper.stages(card, RESUB_STAGES, ended=ended, now=now, sentence=sentence)


def _run_took(card: dict):
    """How long a run drawn on *card* took: from its first step's start to its last step's
    time, or None when its steps keep no times."""
    from modules import run_stepper

    steps = (card.get("rows") or [{}])[0].get("steps") or []
    starts = [e for e in (run_stepper._epoch(s.get("began") or s.get("at")) for s in steps)
              if e is not None]
    ends = [e for e in (run_stepper._epoch(s.get("at")) for s in steps) if e is not None]
    return max(ends) - min(starts) if starts and ends else None


def record_outcome(rec: dict) -> dict:
    """What a finished re-subscribe's record says, short: ``{"level", "outcome", "words",
    "why", "removed"}``; *removed* names each subscription whose receiver it left removed (the
    next action is Re-add the receiver)."""
    from modules.heal import resubscribe as R

    outcome = rec.get("outcome") or "failed"
    return {"level": record_level(rec), "outcome": outcome,
            "words": R.OUTCOME_WORDS.get(outcome, outcome.replace("_", " ")),
            "why": rec.get("why") or "",
            "removed": [str(s.get("sub")) for s in rec.get("subscriptions") or []
                        if s.get("outcome") == "removed"]}


def _records(network: str, since: float) -> list:
    """*network*'s re-subscribe runs that started at or after *since*, newest first, read
    without creating anything: the run's id leads with its start (`reads.new_id`), so only
    the files inside the window are opened."""
    import json

    from modules.config import list_data_path
    from modules.heal import resubscribe as R

    folder = os.path.join(list_data_path(network), "privileged")
    floor = time.strftime("%Y%m%dT%H%M%S", time.gmtime(since))
    try:
        names = sorted((n for n in os.listdir(folder) if n.endswith(".json")
                        and n[:15] >= floor), reverse=True)
    except (FileNotFoundError, NotADirectoryError):
        return []
    out = []
    for name in names:
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue                                  # History names an unreadable record
        if isinstance(rec, dict) and rec.get("key") in (R.KEY, R.READD_KEY):
            out.append(rec)
    return out


def opened(run_id: str, viewer: str) -> bool:
    """Whether *viewer* has seen run *run_id*'s result: drawn on a card this process served
    (`mark_opened`, a cache lost at a restart), or opened or dismissed under Finished, which is
    kept (`seen_runs`, C3081)."""
    from modules import seen_runs

    with _lock:
        if viewer in _opened.get(run_id, ()):
            return True
    return seen_runs.is_seen(viewer, run_id)


def mark_opened(run_id: str, viewer: str) -> bool:
    """*viewer* has been drawn run *run_id*'s result on a card: Finished stops listing it for
    them while this process runs. In memory, beside the jobs' own marks, a cache: what is kept
    across a restart is a person's own press (`seen_runs.mark`, through a declared route, since
    a read writes nothing). True when it was news."""
    if not run_id:
        return False
    with _lock:
        seen = _opened.setdefault(run_id, set())
        if viewer in seen:
            return False
        seen.add(viewer)
        while len(_opened) > 256:
            _opened.pop(next(iter(_opened)))
    return True


def last_record(network: str, host: str, now: float = None):
    """*host*'s newest re-subscribe run that ended and started inside `FINISHED_KEEP_S`, or
    None: what the card on the lost stream's row leads with, so a run's outcome is read where
    it was started, whoever looks and however the page was reached."""
    now = time.time() if now is None else now
    return next((r for r in _records(network, now - FINISHED_KEEP_S)
                 if r.get("device") == host and r.get("state") != "running"), None)


def unopened_record(network: str, host: str, viewer: str, now: float = None):
    """*host*'s newest ended re-subscribe run that *viewer* started and has not opened."""
    now = time.time() if now is None else now
    return next((r for r in _records(network, now - FINISHED_KEEP_S)
                 if r.get("device") == host and r.get("state") != "running"
                 and r.get("actor") and r.get("actor") == viewer
                 and not opened(r.get("id") or "", viewer)), None)


def finished_records(network: str, viewer: str, now: float = None, have=()) -> list:
    """*network*'s ended re-subscribe runs that *viewer* started and has not opened, as the
    In progress list's Finished rows (`in_flight.finished_row`'s shape, with ``steps``, how
    many the record holds, and ``run``); *have* are the runs a kept job already lists."""
    from modules import in_flight

    now = time.time() if now is None else now
    if not viewer:
        return []
    out = []
    for rec in _records(network, now - FINISHED_KEEP_S):
        run = rec.get("id") or ""
        if (rec.get("state") == "running" or rec.get("actor") != viewer or run in have
                or opened(run, viewer)):
            continue
        o = record_outcome(rec)
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(
            rec.get("finished_at") or rec.get("started_at") or 0)))
        out.append({"device": rec.get("device") or "", "list": network, "card": RESUB_CARD,
                    "name": in_flight.OPERATION_NAMES[RESUB_CARD], "level": o["level"],
                    "outcome": in_flight.OUTCOMES[o["level"]], "words": o["words"],
                    "at": in_flight._clock(at), "who": "you", "run": run, "job": "",
                    "steps": len(rec.get("steps") or [])})
    return out


def resubscribe_view(network: str, host: str, run_id: str, job_id: str = "") -> dict:
    """The re-subscribe card's fields for run *run_id* (`routes/resubscribe_v2.card` draws
    them in `_resubscribe.html`): ``running`` while its record says so and its job (when this
    server still holds it) runs; else ``result``: what the result draws of the record History
    keeps whole, its level, the steps taken on THE stepper (`record_steps`), and each receiver
    it left removed (the next action: Re-add the receiver)."""
    from modules.nsot import capture_job, privileged

    j = capture_job.get(job_id) if job_id else None
    rec = privileged.get(network, run_id)
    if rec is not None and rec.get("state") == "running" and j is None:
        from modules.heal import resubscribe as R
        if not R._in_flight(network, host):
            # Its record says running, this server holds no job for it and no re-subscribe
            # holds the device (the kernel frees a hold when its process ends): the run
            # stopped before it recorded an outcome. Said, never drawn as still running; by
            # identity, not by a timer.
            last = next((s for s in reversed(rec.get("steps") or []) if isinstance(s, dict)),
                        {})
            return {"state": "stopped", "level": "danger",
                    "stopped_since": last.get("at") or rec.get("at") or "",
                    "steps": record_steps(host, dict(rec, state="stopped"))}
    if rec is None or (rec.get("state") == "running" and (j is None or
                                                         j["state"] == "running")):
        # Running: its REAL steps as they stand now. The job's own list where this server
        # runs it (`op_progress.run_of`: the list its record keeps, read live); else what its
        # record held when it was last written.
        from modules import op_progress
        from modules.heal import resubscribe as R

        live = op_progress.run_of(job_id) if job_id else None
        if live is not None and live["run"] == run_id:
            # Its declared steps are the ones its run attached (a Re-add's are fewer).
            readd = len(live["declared"]) == len(R.READD_STEPS)
            now = {"id": run_id, "state": "running", "steps": live["steps"],
                   "key": R.READD_KEY if readd else R.KEY}
        else:
            now = rec
        return dict({"state": "running"}, **(
            {"steps": record_steps(host, now, labels=(live or {}).get("labels") or None)}
            if now and now.get("steps") else {}))
    o = record_outcome(rec)
    return {"state": "result", "level": o["level"], "left_removed": o["removed"],
            "record": dict({k: rec.get(k) for k in ("state", "outcome", "why", "actor", "at",
                                                    "reason", "hash")},
                           subscriptions=[{k: s.get(k) for k in ("sub", "outcome", "verify",
                                                                 "stale")}
                                          for s in rec.get("subscriptions") or []]),
            # The result's red box says why (the record's own summary): the lead names the
            # step that failed and does not say it again.
            "steps": record_steps(host, rec, summarised=True)}


def resubscribe_job_card(network: str, host: str, job_id: str) -> dict:
    """The card a device's page reopens for a re-subscribe's job: the re-subscribe card itself
    (`_resubscribe.html`, in the state its run is in), ``framed`` as the page's cards are (a
    heading with its outcome, Close), with what the In progress list reads of it (``state``,
    ``level``, ``words``). ``unknown`` when this server holds neither the job nor a record
    it started."""
    from modules.nsot import capture_job

    got = capture_job.get(job_id)
    if got is None:
        return {"op": RESUB_CARD, "host": host, "list": network, "job": job_id,
                "state": "unknown"}
    run_id = ((got.get("payload") or {}).get("run") if isinstance(got.get("payload"), dict)
              else "") or ""
    if not run_id:
        # Still running (its job answers with its run's id only at its end): the record this
        # job's run wrote, the device's newest one started since the job did.
        rec = next((r for r in _records(network, (got.get("started_at") or 0) - 1)
                    if r.get("device") == host), None)
        run_id = (rec or {}).get("id") or ""
    if got["state"] == "failed":
        # Its job raised (the run itself never raises: `resubscribe.apply`): said by the In
        # progress list, which reads ``state`` and ``error``; the page draws its tab.
        return dict(record_card_for(network, host, run_id, job_id), state="failed",
                    level="danger", raised=got.get("error") or "no reason was recorded",
                    error=got.get("error") or "no reason was recorded")
    return record_card_for(network, host, run_id, job_id)


def record_card_for(network: str, host: str, run_id: str, job_id: str = "") -> dict:
    """The reopened re-subscribe card for run *run_id* (its job's id when this server holds
    it): `resubscribe_view` drawn in the page's frame."""
    from modules.heal import resubscribe as R
    from modules.nsot import privileged

    rec = privileged.get(network, run_id) if run_id else None
    subs = [str(s.get("sub")) for s in (rec or {}).get("subscriptions") or [] if s.get("sub")]
    view = resubscribe_view(network, host, run_id, job_id) if run_id else {"state": "running"}
    out = dict({"op": RESUB_CARD, "framed": True, "host": host, "list": network, "subs": subs,
                "job": job_id, "run": run_id, "error": "", "reason": "",
                "bound_s": R.VERIFY_BOUND_S, "wait_s": R.WAIT_S,
                "outcome_words": dict(R.OUTCOME_WORDS)}, **view)
    if view["state"] == "result":
        out["words"] = record_outcome(rec)["words"]
    return out


def last_view(network: str, host: str, now: float = None):
    """What the re-subscribe card leads with of *host*'s last run (`last_record`): its level,
    its outcome in words, why, who ran it and when, its id, and the steps it took on THE
    stepper; None when no run of the day ended."""
    rec = last_record(network, host, now)
    if rec is None:
        return None
    return dict(record_outcome(rec), actor=rec.get("actor") or "", at=rec.get("at") or "",
                run=rec.get("id") or "", steps=record_steps(host, rec))


def reopened_record(network: str, host: str, viewer: str, now: float = None):
    """``(card, job)`` for the run *viewer* started on *host* and has not opened, known only
    by its record (`unopened_record`): its reopened card (`record_card_for`), and what a job
    row would say of it (who started it, when it started and ended), for the page's "Finished
    at …, while you were elsewhere". None when there is none."""
    return _as_reopened(network, host, unopened_record(network, host, viewer, now))


def named_record(network: str, host: str, run_id: str, now: float = None):
    """``(card, job)`` as `reopened_record` gives them, for the ended run *run_id* on *host*
    started inside `FINISHED_KEEP_S`, opened or not: the run a person pressed Open the result
    on (`routes/v2.seen_run`), never the device's newest; or a History row's Open the card,
    at any age (the operator, 2026-11-12: "Every operation row in History (device and fleet)
    has "Open the card""), read by its id from the record store. None when there is none."""
    from modules.heal import resubscribe as R
    from modules.nsot import privileged

    now = time.time() if now is None else now
    rec = next((r for r in _records(network, now - FINISHED_KEEP_S)
                if r.get("id") == run_id and r.get("device") == host
                and r.get("state") != "running"), None) if run_id else None
    if rec is None and run_id:
        try:
            got = privileged.get(network, run_id)
        except (ValueError, OSError):                 # no run's id, or an unreadable record
            got = None
        if (isinstance(got, dict) and got.get("key") in (R.KEY, R.READD_KEY)
                and got.get("device") == host and got.get("state") != "running"):
            rec = got
    return _as_reopened(network, host, rec)


def _as_reopened(network: str, host: str, rec):
    if rec is None:
        return None
    from modules import run_stepper

    started = run_stepper._epoch(rec.get("at")) or 0
    return (record_card_for(network, host, rec["id"]),
            {"actor": rec.get("actor"), "state": "done", "started_at": started,
             "finished_at": rec.get("finished_at") or started})


def running_resubscribe(network: str, host: str):
    """The re-subscribe running on *host* now, ``{"job", "run"}`` (its run's id once its
    record is written, else ``""``), or None: the card opened without a run names this one,
    so a page refreshed mid-run draws the run, never a fresh offer (the operator,
    2026-11-11)."""
    from modules.nsot import capture_job

    job = capture_job.for_device(network, host, RESUB_CARD)
    if not job or job["state"] != "running":
        return None
    rec = next((r for r in _records(network, (job.get("started_at") or 0) - 1)
                if r.get("device") == host), None)
    return {"job": job["job"], "run": (rec or {}).get("id") or ""}
