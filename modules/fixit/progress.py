"""The incident card's compact live stepper (the operator, 2026-11-16): while the AI investigates,
and while an approved plan or a saved script runs, the card shows its steps instead of its one
status line: each done step ticked with its seconds, the current one with a spinner and a counter
that ticks in the page, the next ones greyed. Steps in `run_stepper.step`'s model (one stepper
model, drawn compact by templates/v2/_inc_step.html). From what the jobs already record: the
investigation's said steps (`troubleshoot_job.trail`), a run's own steps (`op_progress.run_of`).
In this process's memory, as the jobs are: a page drawn elsewhere shows none. A read."""

import time

#: What an investigation still has to do after its last said step, greyed until reached.
AI_NEXT = ("Checking the plan against the switch", "Plan ready")
#: A command plan run's steps as a person reads them (`command_plan_run.STEPS`' keys); a key not
#: here is drawn by its run's own label. The check of the hash and a rollback not needed are
#: not drawn.
RUN_WORDS = {"hold": "Holding {device}", "read_before": "Reading before",
             "preconditions": "Checks", "send": "Sending", "verify": "Verifying",
             "record": "Fixed"}
HIDDEN = ("approve", "rollback")
FAILED = ("fail", "failed", "refused", "error")


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _epoch(iso) -> float:
    import calendar
    try:
        return float(calendar.timegm(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S")))
    except (TypeError, ValueError, OverflowError):
        return 0.0


def investigation(network: str, incident_id: str) -> list:
    """The running investigation's steps: each said step done but the last, which runs, then
    `AI_NEXT` not yet reached, waiting; ``[]`` when none runs here."""
    from modules import run_stepper as RS
    from modules import troubleshoot_job as TJ

    said = TJ.trail(network, incident_id)
    if not said:
        return []
    out = [RS.step(str(n), s["done"] or s["doing"].rstrip("…"), "done",
                   took_s=round(said[n + 1]["at"] - s["at"]))
           for n, s in enumerate(said[:-1])]
    last = said[-1]
    out.append(RS.step(str(len(said) - 1), last["doing"].rstrip("…"), "running",
                       since=_iso(last["at"])))
    reached = {s["doing"].rstrip("…") for s in said}
    out += [RS.step(f"next-{n}", w, "waiting") for n, w in enumerate(AI_NEXT)
            if w not in reached]
    return out


def run(network: str, incident_id: str, device: str) -> list:
    """The steps of the run on *incident_id* running now (an approved plan's or a saved
    script's job, its page the incident's): recorded ones done (or failed), the next declared
    one running since the last was recorded, the rest waiting; ``[]`` when none runs here."""
    from modules import op_progress
    from modules import run_stepper as RS
    from modules import troubleshoot_job as TJ
    from modules.nsot import capture_job

    page = f"/v2/incident/{incident_id}?"
    job = next((j for j in capture_job.card_jobs() if j["state"] == "running"
                and j["kind"] != TJ.KIND and j["list"] == network
                and page in (j.get("page") or "")), None)
    own = op_progress.run_of(job["job"]) if job else None
    if not own:
        return []
    recorded, labels = own["steps"], own.get("labels") or {}
    last_at = _epoch(recorded[-1]["at"]) if recorded else float(job.get("started_at") or 0)
    out, prev, running = [], float(job.get("started_at") or 0), False
    for key, words in own["declared"]:
        rec = [s for s in recorded if s.get("step") == key]
        label = RUN_WORDS.get(key, labels.get(key) or words).format(device=device)
        if key in HIDDEN and not (rec and rec[-1].get("result") in FAILED):
            prev = _epoch(rec[-1]["at"]) if rec else prev
            continue
        if rec:
            at = _epoch(rec[-1]["at"])
            out.append(RS.step(key, label, "failed" if rec[-1].get("result") in FAILED
                               else "done", took_s=round(at - prev) if prev else None))
            prev = at
        elif not running:
            running = True
            out.append(RS.step(key, label, "running", since=_iso(last_at) if last_at else ""))
        else:
            out.append(RS.step(key, label, "waiting"))
    return out


def of(network: str, incident_id: str, device: str, state: str) -> list:
    """The card's live steps for *state* (the section's): an investigation's while it
    investigates, else the run's while one runs; ``[]`` otherwise."""
    if state == "investigating":
        return investigation(network, incident_id)
    return run(network, incident_id, device) if state != "resolved" else []


def took_words(seconds) -> str:
    """A duration as the collapsed line says it ("1 min 27 s")."""
    s = max(0, int(round(float(seconds or 0))))
    return f"{s // 60} min {s % 60} s" if s >= 60 else f"{s} s"
