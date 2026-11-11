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
  until they open it; opening is remembered in memory, as a job's is, so a restart lists it
  once more.

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
    from modules.heal import act, bounce, propose, session_clear

    keys = [s.get("step") for s in steps if isinstance(s, dict)]
    tables = ((propose.STEPS, act.STEPS) if approved else (act.STEPS, propose.STEPS)) + (
        bounce.STEPS, session_clear.STEPS)
    for table in tables:
        if set(keys) <= {k for k, _w in table}:
            return tuple(table)
    return tuple((k, str(k)) for k in dict.fromkeys(keys) if k)


def act_phase(steps: list, *, ended: bool, approved: bool = False, now: float = None,
              prefix: str = "") -> dict:
    """An act's recorded *steps* on the stepper (`run_stepper.from_record`): a symptom read
    gone (or none named: `act.read_symptom`'s states) and a record's own good outcomes are
    done; a symptom still present, a rollback and a can't-fix are failed; anything else (a
    symptom unreadable, a save held) is amber."""
    from modules import run_stepper

    return run_stepper.from_record(
        _declared(steps, approved), steps, ended=ended, now=now, prefix=prefix,
        good=HEALED + ("gone", "none"),
        bad=("present", "rolled_back", "interrupted", "rejected", "cant_fix"),
        conditional=("repair", "rollback", "reset"))


def decision_phase(steps: list, *, now: float = None, prefix: str = "d-") -> dict:
    """A decision's recorded steps (`steplog.decision_steps`) against `decide.STEPS`."""
    from modules import run_stepper
    from modules.heal import decide

    return run_stepper.from_record(decide.STEPS, steps, ended=True, now=now, prefix=prefix,
                                   good=DECISION_GOOD, bad=DECISION_BAD)


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
    phases = [decision_phase(decided)] if decided else []
    if acted:
        phases.append(act_phase(acted, ended=entry.get("state") != "applying", prefix="a-"))
    outcome = entry.get("outcome") or ""
    return run_stepper.record_card(
        host, f"The steps self-healing took on {host}", phases,
        ended=entry.get("state") != "applying",
        level="ok" if outcome in HEALED + DECISION_GOOD else level_of(outcome),
        key=f"heal-steps-{entry.get('incident') or host}")


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
    card.update(started=started, actor=got.get("actor") or "the policy")
    if got["state"] == "running":
        return dict(card, state="running")
    if got["state"] == "failed":
        return dict(card, state="failed", error=got.get("error") or "no reason was recorded")
    result = (got.get("payload") or {}).get("result") or {}
    outcome = result.get("outcome") or "failed"
    steps = [s for s in result.get("steps") or [] if isinstance(s, dict)]
    phase = act_phase(steps, ended=True)
    level = level_of(outcome)
    return dict(card, state="result", level=level, outcome=outcome,
                words=steplog.mark(outcome, result.get("kind") or ""),
                summary=result.get("words") or "",
                steps=run_stepper.record_card(host, f"The steps self-healing took on {host}",
                                              [phase], ended=True, level=level,
                                              key=f"heal-run-{job_id[:12]}"),
                finished=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime(got.get("finished_at") or 0)))


# ── A re-subscribe's run, from its record ───────────────────────────────────────────────────

#: A record's state (`resubscribe.RECORD_STATE`) -> its level: only ``done`` is green.
RECORD_LEVELS = {"done": "ok", "unverified": "warn"}


def record_level(rec: dict) -> str:
    return RECORD_LEVELS.get(rec.get("state") or "", "danger")


def record_steps(host: str, rec: dict, *, now: float = None) -> dict:
    """A re-subscribe's (or a Re-add the receiver's) recorded steps on THE stepper, the step
    to act on leading: `run_stepper.record_card` over the record's own ``steps``, against the
    steps the operation declares."""
    from modules import run_stepper
    from modules.heal import resubscribe as R

    ended = rec.get("state") != "running"
    declared = R.READD_STEPS if rec.get("key") == R.READD_KEY else R.STEPS
    phase = run_stepper.from_record(declared, rec.get("steps") or [], ended=ended, now=now,
                                    conditional=("rollback",))
    return run_stepper.record_card(
        host, f"The steps the re-subscribe took on {host}", [phase], ended=ended,
        level=record_level(rec) if ended else "", key=f"resub-run-{str(rec.get('id'))[-12:]}")


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
    with _lock:
        return viewer in _opened.get(run_id, ())


def mark_opened(run_id: str, viewer: str) -> bool:
    """*viewer* has seen run *run_id*'s result: Finished stops listing it for them. In memory,
    beside the jobs' own marks; True when it was news."""
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
                    "at": in_flight._clock(at), "who": "you", "run": run,
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
    if rec is None or (rec.get("state") == "running" and (j is None or
                                                         j["state"] == "running")):
        return {"state": "running"}
    o = record_outcome(rec)
    return {"state": "result", "level": o["level"], "left_removed": o["removed"],
            "record": dict({k: rec.get(k) for k in ("state", "outcome", "why", "actor", "at",
                                                    "reason", "hash")},
                           subscriptions=[{k: s.get(k) for k in ("sub", "outcome", "verify",
                                                                 "stale")}
                                          for s in rec.get("subscriptions") or []]),
            "steps": record_steps(host, rec)}


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
    rec = unopened_record(network, host, viewer, now)
    if rec is None:
        return None
    from modules import run_stepper

    started = run_stepper._epoch(rec.get("at")) or 0
    return (record_card_for(network, host, rec["id"]),
            {"actor": rec.get("actor"), "state": "done", "started_at": started,
             "finished_at": rec.get("finished_at") or started})
