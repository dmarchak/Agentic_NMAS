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
        table, steps, ended=ended, now=now, prefix=prefix,
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
        decide.STEPS, steps, ended=True, now=now, prefix=prefix, good=DECISION_GOOD,
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
    return run_stepper.record_card(
        host, f"The steps self-healing took on {host}", phases,
        ended=entry.get("state") != "applying",
        level="ok" if outcome in HEALED + DECISION_GOOD else level_of(outcome),
        key=f"heal-steps-{entry.get('incident') or host}",
        summarised=True)                              # the row's cause says why, above it


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
        # The run's REAL steps as they stand now (`op_progress.run_of`: the act's own list),
        # after its decision's; while it applies, the deploy's stages from the device's hold.
        from modules import op_progress
        card["state"] = "running"
        live = op_progress.run_of(job_id)
        if live is not None:
            phases = _decided(network, live["run"], host) + [
                act_phase(live["steps"], ended=False, host=host)]
            card["steps"] = run_stepper.record_card(
                host, f"Self-healing's steps on {host}", phases, ended=False,
                key=f"heal-run-{job_id[:12]}")
            stages = _stages(network, host)
            if stages:
                card["stages"] = stages
        return card
    if got["state"] == "failed":
        return dict(card, state="failed", error=got.get("error") or "no reason was recorded")
    result = (got.get("payload") or {}).get("result") or {}
    outcome = result.get("outcome") or "failed"
    steps = [s for s in result.get("steps") or [] if isinstance(s, dict)]
    phases = _decided(network, result.get("decision") or "", host) + [
        act_phase(steps, ended=True, host=host)]
    level = level_of(outcome)
    return dict(card, state="result", level=level, outcome=outcome,
                words=steplog.mark(outcome, result.get("kind") or ""),
                summary=result.get("words") or "",
                # The card's own "What happened" says why: the lead names the step alone.
                steps=run_stepper.record_card(host, f"The steps self-healing took on {host}",
                                              phases, ended=True, level=level,
                                              key=f"heal-run-{job_id[:12]}", summarised=True),
                finished=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime(got.get("finished_at") or 0)))


def _decided(network: str, decision_id: str, host: str = "") -> list:
    """The decision that started a heal, as the first phase of its stepper (its recorded
    steps, `steplog.decision_steps`), or no phase when the decision cannot be read: the act's
    own steps are still drawn."""
    from modules.heal import decisions, steplog

    if not decision_id:
        return []
    try:
        decision = decisions.find(network, decision_id)
    except Exception as exc:                          # noqa: BLE001 (the act's steps stand)
        log.info("run_card: %s's decision %s could not be read: %s", network, decision_id, exc)
        return []
    return [decision_phase(steplog.decision_steps(decision), host=host)]


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
    return run_stepper.record_card(
        host, f"The steps the re-subscribe took on {host}", [phase], ended=ended,
        level=record_level(rec) if ended else "", key=f"resub-run-{str(rec.get('id'))[-12:]}",
        summarised=summarised)


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
    on (`routes/v2.seen_run`), never the device's newest. None when there is none."""
    now = time.time() if now is None else now
    rec = next((r for r in _records(network, now - FINISHED_KEEP_S)
                if r.get("id") == run_id and r.get("device") == host
                and r.get("state") != "running"), None) if run_id else None
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
