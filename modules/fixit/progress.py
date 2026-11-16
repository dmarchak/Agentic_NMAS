"""The incident card's compact stepper (the operator, 2026-11-16): while the AI investigates,
and while an approved plan or a saved script runs, the card shows its steps instead of its one
status line: each done step ticked with its seconds, the current one with a spinner and a counter
that ticks in the page, the next ones greyed. Steps in `run_stepper.step`'s model (one stepper
model, drawn compact by templates/v2/_inc_step.html). From what the jobs already record: the
investigation's said steps (`troubleshoot_job.trail`), a run's own steps (`op_progress.run_of`).

An approved plan's run (the operator, 2026-11-16: "One home: the run's home is its incident
card, with the run's stepper (plain, vertical, the plan's numbered steps and the waits between
them, each ticked with its seconds)"): each plan step's own operation's steps, numbered as the
plan card numbers each system's step (`fixit.plan.sent_of`'s *parts*), the waits between them
their own lines; the step running read live from its job, every other from its own run's
record, so a finished run stays drawn with each step's result (`recorded`). A read."""

import time

#: What an investigation still has to do after its last said step, greyed until reached.
AI_NEXT = ("Checking the plan is safe to run", "Plan ready for your approval")
#: A command plan run's steps as a person reads them (`command_plan_run.STEPS`' keys); a key not
#: here is drawn by its run's own label. The check of the hash and a rollback not needed are
#: not drawn.
RUN_WORDS = {"hold": "Holding {device}", "read_before": "Reading before",
             "preconditions": "Checks", "send": "Sending", "verify": "Verifying",
             "record": "Fixed"}
#: A re-subscribe's steps, with the collector step first where its plan has one (the operator,
#: 2026-11-16: each system's step said with its own result, in order: "1. Close the
#: collector's session ✓ 2 s", "Waiting for r7 to reconnect", "2. Re-subscribe 101 and 102",
#: "Checking the streams are back"; the waits between them each a line of their own:
#: "Waiting for r7 to drop its old connection", "Waiting 10 s before the re-add").
RESUB_WORDS = {"before": "Reading {device} and the collector first",
               "close": "On the Mercury host (collector): close {device}'s stale session",
               "gone": "Waiting for {device} to drop its old connection",
               "remove": "On {device}: remove the receivers for {subs}",
               "wait": "Waiting {wait} s before the re-add",
               "re-add": "On {device}: add the receivers for {subs} back",
               "verify": "Checking the streams are back"}
#: The system each action is on: a line opening a system's step is numbered, as the plan card
#: numbers it ("Step 1, on the Mercury host (collector)", "Step 2, on r7"); the reads and the
#: waits between them are not.
SYSTEM_OF = {"close": "host", "remove": "device", "re-add": "device", "send": "device"}
HIDDEN = ("approve", "rollback", "plan", "hash", "started")
FAILED = ("fail", "failed", "refused", "error")
#: The one line while the plan engine checks the approved plan again, before its first step's
#: own operation has said a step.
CHECKING = "Checking the plan is the one approved"


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _epoch(iso) -> float:
    import calendar
    try:
        return float(calendar.timegm(time.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S")))
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _fill(text: str, **values) -> str:
    """*text* with each ``{name}`` of *values* filled; any other brace left as written."""
    text = str(text or "")
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def _and(items) -> str:
    items = [str(i) for i in items or [] if str(i)]
    return (" and ".join(items) if len(items) <= 2 else
            ", ".join(items[:-1]) + " and " + items[-1])


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


def lines(declared, recorded, labels=None, *, device: str = "", subs: str = "",
          start: float = 0.0, ended: bool = False, passed: bool = False, n: int = 1,
          prefix: str = "") -> tuple:
    """One operation's run as the card's lines: ``(steps, the next number)``. *declared* its
    steps in order (``(key, words)``), *recorded* what it recorded (``{"step", "result",
    "at"}``), *labels* its own short words. Each recorded step done (or failed) with its
    seconds since the step before it; while it runs (*ended* false) the next declared one
    running since the last was recorded and the rest waiting; once it ended, a step never
    reached says so. The bookkeeping (`HIDDEN`) is not drawn unless it failed; nor, for a run
    that did not pass, its "Fixed". A line opening a system's step is numbered from *n*
    (`SYSTEM_OF`)."""
    from modules import run_stepper as RS
    from modules.heal import resubscribe as R

    labels = labels or {}
    resub = any(k == "re-add" for k, *_ in declared)
    fill = {"device": device or "the device", "subs": subs or "its streams",
            "wait": R.WAIT_S}
    out, prev, running, system = [], float(start or 0), False, ""
    last_at = _epoch(recorded[-1].get("at")) if recorded else float(start or 0)
    for key, words, *_ in declared:
        rec = [s for s in recorded if s.get("step") == key]
        failed = bool(rec) and rec[-1].get("result") in FAILED
        hidden = (key in HIDDEN or (key == "record" and (resub or (ended and not passed))))
        if hidden and not failed:
            prev = _epoch(rec[-1].get("at")) if rec else prev
            continue
        label = _fill((RESUB_WORDS.get(key) if resub else None) or RUN_WORDS.get(key)
                      or labels.get(key) or words, **fill)
        if SYSTEM_OF.get(key) and SYSTEM_OF[key] != system:
            label, n, system = f"{n}. {label}", n + 1, SYSTEM_OF[key]
        key = prefix + key
        if rec:
            at = _epoch(rec[-1].get("at"))
            out.append(RS.step(key, label, "failed" if failed else "done",
                               took_s=round(at - prev) if prev else None,
                               note=str(rec[-1].get("words") or "")[:300] if failed else ""))
            prev = at
        elif ended:
            out.append(RS.step(key, label, "not_reached"))
        elif not running:
            running = True
            out.append(RS.step(key, label, "running", since=_iso(last_at) if last_at else ""))
        else:
            out.append(RS.step(key, label, "waiting"))
    return out, n


def _declared_of(rec: dict) -> tuple:
    """A run record's declared steps: a re-subscribe's its operation's (`steps_for`), any
    other's the steps it recorded, in order."""
    from modules.heal import resubscribe as R

    if rec.get("key") in R.RUN_KEYS:
        return R.steps_for(rec["key"])
    return tuple((k, k) for k in dict.fromkeys(str(s.get("step") or "")
                                               for s in rec.get("steps") or []) if k)


def _subs_of(params: dict) -> str:
    subs = params.get("subscriptions") or params.get("subs") or (
        [params["subscription"]] if params.get("subscription") else [])
    return _and(subs if isinstance(subs, (list, tuple)) else [subs])


def plan_lines(network: str, rec: dict, device: str = "", live: dict = None) -> list:
    """An approved plan's run (*rec*, the plan engine's record) as the card's lines: each plan
    step's own operation's steps in order, numbered on across them; the step running from
    *live* (its job's `op_progress.run_of`, once that operation has attached its own) and each
    that ran from its own run's record (the step's receipt names it); a step not run yet its
    declared steps, waiting (or not reached once the plan ended); one with no steps of its own
    a single numbered line, with its words where it did not pass."""
    from modules import plan_engine as PE
    from modules import run_stepper as RS
    from modules.heal import resubscribe as R
    from modules.nsot import privileged

    ended = rec.get("state") != "running"
    out, n = [], 1
    for st in rec.get("plan_steps") or []:
        params = st.get("params") if isinstance(st.get("params"), dict) else {}
        on = dict(device=str(params.get("device") or device), subs=_subs_of(params),
                  prefix=f"s{st.get('n')}-")
        state, kind = st.get("state") or "", st.get("kind") or ""
        run_id = str((st.get("receipt") or {}).get("run") or "")
        own = None
        if run_id:
            try:
                own = privileged.get(network, run_id)
            except (OSError, ValueError):
                own = None
        if state == "running" and live and live.get("run") and live.get("run") != rec.get("id"):
            got, n = lines(live["declared"], live["steps"], live.get("labels"), n=n,
                           start=float(rec.get("started_at") or 0), **on)
        elif isinstance(own, dict) and own.get("steps"):
            got, n = lines(_declared_of(own), own["steps"], n=n,
                           start=float(own.get("started_at") or 0), ended=True,
                           passed=own.get("state") == "done", **on)
        elif kind in R.RUN_KEYS and state in ("not_run", "running"):
            got, n = lines(R.steps_for(kind), [], n=n, ended=ended,
                           start=float(rec.get("started_at") or 0), **on)
        else:
            words = PE.STEP_LABELS.get(kind) or st.get("words") or f"Step {st.get('n')}"
            shown = {"done": "done", "running": "running", "failed": "failed",
                     "refused": "failed"}.get(state, "not_reached" if ended else "waiting")
            got = [RS.step(f"s{st.get('n')}", f"{n}. {words}", shown,
                           note=str(st.get("words_said") or "")[:300]
                           if shown == "failed" else "")]
            n += 1
        out += got
    return out


def _job_of(network: str, incident_id: str):
    """The job running here for *incident_id*'s run (an approved plan's, its page the
    incident's card, `plan_engine.run_page`; or a saved script's), or None."""
    from modules import troubleshoot_job as TJ
    from modules.nsot import capture_job

    page = f"/v2/incident/{incident_id}?"
    return next((j for j in capture_job.card_jobs() if j["state"] == "running"
                 and j["kind"] != TJ.KIND and j["list"] == network
                 and (j.get("page") or "").startswith(page)), None)


def run(network: str, incident_id: str, device: str) -> list:
    """The steps of the run on *incident_id* running here now: an approved plan's by its plan
    (`plan_lines`), a saved script's by its own declared steps; ``[]`` when none runs here."""
    from modules import op_progress
    from modules import plan_engine as PE
    from modules import run_stepper as RS

    job = _job_of(network, incident_id)
    if job is None:
        return []
    live = op_progress.run_of(job["job"])
    if job["kind"] == PE.JOB_KIND:
        rid = PE.run_of_job(job["job"])
        rec = PE.record_of(network, rid) if rid else None
        if rec and rec.get("plan_steps"):
            return plan_lines(network, rec, device, live)
        return [RS.step("approve", CHECKING, "running",
                        since=_iso(float(job.get("started_at") or time.time())))]
    if not live:
        return []
    return lines(live["declared"], live["steps"], live.get("labels"), device=device,
                 start=float(job.get("started_at") or 0))[0]


def approved_run(network: str, found: dict) -> str:
    """The plan run the incident's newest approval started (its approve line names it,
    `fixit.incident.record_approve`), or ``""``. A read of the incident's record."""
    from modules.fixit import incident as F
    from modules.fixit.section import incident_of

    inc = incident_of(network, found or {}).get("incident")
    if inc is None:
        return ""
    try:
        got = F.read(inc)
    except Exception:                                 # noqa: BLE001 (drawn without it)
        return ""
    line = next((ln for ln in reversed(got["lines"]) if ln.get("choice") == "approve"), None)
    return str((line or {}).get("run") or "")


def recorded(network: str, found: dict, device: str, newest: str = "",
             running: bool = False, rid: str = None) -> list:
    """The incident's newest approved plan's run from its records (`plan_lines`): drawn on
    the card once it ended, each step's result, and while it runs in a process other than
    this one (*running*: only then). *newest*, the newest attempt's run, must be that plan's
    or one of its steps' own, so a later run's card never draws an earlier plan. ``[]`` when
    there is none. *rid*: the approved run, when the caller has read it (`approved_run`)."""
    from modules import plan_engine as PE

    rid = approved_run(network, found) if rid is None else rid
    rec = PE.record_of(network, rid) if rid else None
    if not rec or not rec.get("plan_steps") or (running and rec.get("state") != "running"):
        return []
    mine = {rid} | {str((s.get("receipt") or {}).get("run") or "")
                    for s in rec["plan_steps"]}
    if newest and newest not in mine:
        return []
    return plan_lines(network, rec, device)


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
