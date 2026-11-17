"""The retry pass: an open incident whose fixes failed is tried again ONCE per trigger (the
operator, 2026-11-16, replacing "never retry a failed fix"): when self-healing is switched on
again (``switched_on``), when a new script is saved or promoted that matches its problem
(``script_saved``, only the incidents that script matches), and every 24 hours while it stays
open (``daily``). One retry per trigger, never a loop. Deterministic; no AI.

**Who is retried** (the population, by the property): an incident ``standing`` (C2813: decided,
its cause still standing) whose newest decision is
- a can't-fix (``cant_fix``): Mercury's code has no fix for it, and a saved script's run that
  failed on it leaves it standing there too (scripts fire only on a can't-fix,
  `decide.SCRIPT_OUTCOMES`); or
- held by a guard that held for a person before C3909 (`WERE_HELD`, held with no time) whose
  guard no longer holds (`decide.guard_holds`: guard 4 and guard 6 as the decision judges them;
  the others hold nothing since 2026-11-16). One still holding is recorded as not tried, under
  the trigger's key, so it is not asked again for that trigger.
- C3844 (the operator, 2026-11-16: "a grace that ends with no answer puts the line back (in
  Auto) or shows 'Would put back: <line>' (in Dry run)"): a dry-run "would heal" (decided while
  self-healing was not in Auto: its decision's ``mode``) once self-healing is in Auto. Its fix
  did not fail; it was withheld by the mode, which no longer withholds it, so it is decided
  again in Auto. Besides the switch-on's own retry, the detect pass asks for it on every pass
  (``now_auto``, `now_auto`, keyed by the Auto confirmation's instant), so it heals with no
  press whichever path turned Auto on, once per confirmation. A would-heal decided in Auto (a
  kind Auto does not fix) is not in it: deciding it again changes nothing.
- C3870 (the operator, 2026-11-16: "Only 'healed' closes an incident ... Retry: the existing
  policy, once per trigger"): an act whose outcome was anything but healed, or a healed act
  whose tail then failed, leaves its incident standing on it (``act`` on its standing record,
  `act.outcome_on_incident`, `incidents.reopen`): decided again as a can't-fix is, once per
  trigger, never while the network is halted (recorded as not tried). The act's failure also
  starts the AI by its own key (`fixit.auto.failures`), once.
An incident a batch claimed (`heal.batch.claimed_by_batch`: its restore is the batch's, marked
under the incidents store's lock before the batch turned Auto on) is left to that batch. An
incident a saved script is firing on now (a ``firing`` track row, the batch's claim included)
is left alone. Nothing runs while self-healing is not in Auto: nothing is retried then.

**Each available fix, in order, through the paths that already run them**: the incident is sent
back for a fresh decision (``ready``, its settled grace kept, or ``watching`` when it holds none)
and the heal decision decides it (`decide.run`, the detect loop's own: every guard judged
again, a fresh read, the outcome recorded in the decisions and the step log); a can't-fix then
fires each matching saved script (`saved_plans.fire_matching`, under this retry's key, so a
run that failed before is tried once more and never twice). No person's operation runs here:
Re-subscribe and every catalog operation stay a person's (or an AI plan a person approves).

**Never twice** (cross-process): each retry is keyed by its trigger's instance (``switched_on:
<the confirmation's instant>``, ``script_saved:<key>:<saved or promoted instant>``,
``daily:<UTC day>``), recorded on the incident's own record (``retries``) under the incidents
store's lock before anything is sent back; a key already there is never retried again. The
daily retry runs only when the incident's last retry (or, never retried, its standing
decision) is 24 hours old or more, measured from the recorded instant, so it holds across
worker processes and restarts. Its check runs on the detect loop's pass (`detect._retry_step`),
no thread of its own.

**What is recorded**: the retry on the incident (when, the trigger in words, each fix tried and
its outcome), finished by the decision that takes it (`finish`, whichever process decides),
and the decision's own row in History, its claim step saying it was a retry and why. A
switch-on's or a script's retry whose fixes failed is a failure R1 sees (`failures_of`,
read by `fixit.auto.pending`); a daily retry's never starts the AI, nor does the act of a
heal its decision made (`fixit.auto.failures` leaves out an act whose decision a daily retry
made; a switch-on's or a script's re-decided heal that fails counts once, as its act).
"""

import logging
import time
import uuid

log = logging.getLogger(__name__)

#: The triggers, and how each is said.
TRIGGERS = ("switched_on", "script_saved", "daily", "now_auto")
#: A daily retry waits this long after the incident's last retry (or its standing decision).
DAY_S = 86400.0
#: C3909 (the operator, 2026-11-17): the guards that held an incident for a person before
#: guards 4 and 6 stopped holding (`fixit.auto.HELD_FOR_A_PERSON` is empty now). An incident
#: still standing on one is decided again once `decide.guard_holds` finds it no longer holds
#: (guard 6 never; guard 4 only for a device Mercury changes nothing on).
WERE_HELD = (4, 6)
#: How many retries an incident keeps, newest last.
KEPT = 20
#: The decision's states after which Mercury's fix failed: no code fix, or a person's hold (a
#: hold with a time to check again waits as designed, ``deferred``; a decision that raised is
#: decided again by its own deferral, and is no failure of a fix).
FAILED_STATES = ("no_fix", "held")


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(epoch)))


def _hhmm(epoch: float) -> str:
    return time.strftime("%H:%M", time.gmtime(float(epoch)))


def times(n: int) -> str:
    return {1: "once", 2: "twice"}.get(int(n), f"{int(n)} times")


def trigger_words(trigger: str, script_name: str = "", how: str = "saved") -> str:
    """The trigger in words: "self-healing switched on", "a new script <name> saved" (or
    "script <name> promoted to Auto"), "the daily retry"."""
    if trigger == "switched_on":
        return "self-healing switched on"
    if trigger == "script_saved":
        return (f"script {script_name} promoted to Auto" if how == "promoted"
                else f"a new script {script_name} saved")
    if trigger == "now_auto":
        return "self-healing is in Auto now, and this was decided in dry run"
    return "the daily retry"


def trigger_words_of(record: dict, retry_id: str) -> str:
    """The words of the retry *retry_id* the incident *record* carries, or "a retry"."""
    r = next((r for r in (record or {}).get("retries") or [] if r.get("id") == retry_id), {})
    return r.get("trigger_words") or "a retry"


def _guard_of(standing: dict):
    g = (standing or {}).get("guard")
    return g.get("guard") if isinstance(g, dict) else g


def _firing(network: str, incident_id: str) -> bool:
    """Whether a saved script's run is claimed in flight on *incident_id* (a ``firing`` track
    row, in any process: the batch's claim included)."""
    from modules.nsot import saved_plans

    return any(r.get("incident") == incident_id and r.get("state") == "firing"
               for e in saved_plans.scripts(network).values() for r in e.get("track") or [])


def _last_epoch(inc: dict) -> float:
    """When the incident was last tried: its newest recorded retry, else its standing
    decision (its ``standing.epoch``)."""
    rs = [float(r.get("epoch") or 0) for r in inc.get("retries") or []]
    return max(rs + [float((inc.get("standing") or {}).get("epoch") or 0)])


def due_daily(inc: dict, now: float) -> bool:
    """Whether the daily retry is due on *inc*: its last try is `DAY_S` old or more."""
    return now - _last_epoch(inc) >= DAY_S


def _dry_run_decisions(network: str, incs: list) -> set:
    """The ids of the decisions a standing would-heal of *incs* stands on that were decided
    while self-healing was not in Auto (the decision's own ``mode``): one read of the
    decisions, only when such an incident stands. Unreadable: none (logged), so nothing is
    sent back on a guess."""
    want = {(i.get("standing") or {}).get("decision") for i in incs
            if i.get("state") == "standing"
            and (i.get("standing") or {}).get("outcome") == "would_heal"}
    want.discard(None)
    if not want:
        return set()
    from modules.heal import decisions

    try:
        rows = decisions.decisions(network)
    except Exception as exc:                          # noqa: BLE001 (none; logged)
        log.error("heal: %s's decisions could not be read for the would-heals: %s", network,
                  exc)
        return set()
    return {d["id"] for d in rows if d.get("id") in want and d.get("mode") != "auto"}


def _in_population(network: str, inc: dict, now: float, dry=frozenset()) -> tuple:
    """``(kind, hold)``: *kind* ``decide`` (sent back for a fresh decision) or ``skip`` (held,
    its guard still holding: *hold* the guard's hit), or ``("", None)`` when *inc* is not an
    incident whose fixes failed or a dry-run would-heal (*dry*, `_dry_run_decisions`; the
    module's docstring)."""
    from modules.heal import decide

    if inc.get("state") != "standing":
        return "", None
    s = inc.get("standing") or {}
    if s.get("act"):
        # C3870: an act's outcome but healed, or a healed act's tail that failed
        # (`incidents.stand`'s ``act``, `incidents.reopen`), decided again as a can't-fix is,
        # once per trigger by this retry's keys. No halt holds it (the operator, 2026-11-17,
        # round 2: nothing halts a network).
        return "decide", None
    if s.get("outcome") in ("cant_fix", "propose", "halted"):
        # Round 2 (the operator, 2026-11-17): a Tier 2 proposal and a halt hold nothing now,
        # so an incident standing on one is decided again and healed in Auto.
        return "decide", None
    if s.get("outcome") == "held" and _guard_of(s) not in WERE_HELD:
        # Held by a guard that holds nothing now (11, 12, 14, the batch's): decided again.
        return "decide", None
    if s.get("outcome") == "would_heal":
        # Round 2 (2026-11-17): a would-heal decided in Auto (a kind not allowed Auto then)
        # heals now too, since no kind list holds it.
        del dry
        return "decide", None
    if s.get("outcome") == "held" and _guard_of(s) in WERE_HELD:
        try:
            g = decide.guard_holds(network, inc, _guard_of(s), now=now)
        except Exception as exc:                      # noqa: BLE001 (an unread guard holds)
            log.error("heal: whether guard %s still holds %s could not be read: %s",
                      _guard_of(s), inc.get("id"), exc)
            return "skip", {"guard": _guard_of(s), "name": "",
                            "words": f"whether it still holds could not be read ({exc})"}
        return ("skip", g) if g else ("decide", None)
    return "", None


def run(network: str, trigger: str, *, instance: str, script: str = "", how: str = "saved",
        by: str = "", now: float = None, decide_now: bool = True, skip=()) -> dict:
    """The retry pass for *network* and one *trigger* instance (the module's docstring):
    ``{"ran", "network", "trigger", "key", "words", "retried", "skipped", "decided"}``,
    *retried* and *skipped* the incidents' ids. *script*: the saved script's key (for
    ``script_saved``, only the incidents it matches). *decide_now*: the heal decision is run
    at once (`decide.run`); a network busy with another pass decides them at its next one.
    *skip* (C3823): incidents a batch turning self-healing on fixes itself (the switch-on's
    restores and saved scripts, `heal.batch.run`), never retried by this pass: no retry row,
    nothing sent back."""
    from modules import incident_page
    from modules import problem as P
    from modules.heal import incidents, policy
    from modules.nsot import saved_plans

    now = time.time() if now is None else float(now)
    if trigger not in TRIGGERS:
        raise ValueError(f"a retry's trigger is one of {', '.join(TRIGGERS)}, not {trigger!r}")
    key = f"{trigger}:{instance}"
    out = {"ran": False, "network": network, "trigger": trigger, "key": key, "words": "",
           "retried": [], "skipped": [], "decided": {}}
    mode = policy.current(network, now)
    if mode.get("mode") != "auto":
        return dict(out, words=f"nothing retried: self-healing is not in Auto on {network} "
                               f"({mode.get('words') or mode.get('mode')})")
    entry = {}
    if trigger == "script_saved":
        entry = saved_plans.scripts(network).get(script) or {}
        if entry.get("mode") != "auto":
            return dict(out, words=f"nothing retried: {script} is no Automatic script of "
                                   f"{network}")
    words = trigger_words(trigger, entry.get("name") or script, how)
    if trigger in ("switched_on", "now_auto"):
        # Round 2 (the operator, 2026-11-17: "Every incident with an approved fix must run the
        # moment self-healing is On, watching or not"): a watching incident waiting out an
        # older deferral is read and decided on the detect loop's next pass, never left to
        # its timer. A person's planned window still holds it there (guard 3, decided again).
        woken = []

        def wake(doc):
            for inc in doc["incidents"]:
                if (inc.get("state") == "watching" and inc.get("id") not in set(skip or ())
                        and float(inc.get("defer_until") or 0) > now):
                    inc["defer_until"] = None
                    inc["updated_at"] = _iso(now)
                    woken.append(inc["id"])
            return woken
        try:
            incidents._mutate(network, wake)
        except Exception as exc:                      # noqa: BLE001 (said; the pass reads them)
            log.error("heal: %s's watching incidents were not woken: %s", network, exc)
        out["woken"] = woken
    got = incidents.read(network)
    if got["state"] == "unreadable":
        return dict(out, words=got["error"])
    plans, skip = {}, set(skip or ())
    from modules.heal import batch as B
    dry = _dry_run_decisions(network, got["incidents"])
    for inc in got["incidents"]:
        if inc.get("id") in skip or B.claimed_by_batch(inc, now):
            continue
        if trigger == "daily" and not due_daily(inc, now):
            continue
        if any(r.get("key") == key for r in inc.get("retries") or []):
            continue
        kind, hold = _in_population(network, inc, now, dry)
        if trigger == "now_auto" and (inc.get("standing") or {}).get("outcome") != "would_heal":
            continue                                  # the catch-up is the would-heals' alone
        if not kind or _firing(network, inc["id"]):
            continue
        if trigger == "script_saved":
            try:
                prob = P.classify(incident_page.resolve(network, inc["id"]))
            except Exception as exc:                  # noqa: BLE001 (said; not retried)
                log.error("heal: %s's problem could not be classified: %s", inc["id"], exc)
                continue
            if not prob.condition or not saved_plans.matches(entry.get("match") or {}, prob):
                continue
        plans[inc["id"]] = {"kind": kind, "hold": hold,
                            "decision": (inc.get("standing") or {}).get("decision") or ""}
    if not plans:
        return dict(out, ran=True, words="nothing to retry")

    def change(doc):
        for inc in doc["incidents"]:
            plan = plans.get(inc.get("id"))
            s = inc.get("standing") or {}
            if (not plan or inc.get("state") != "standing"
                    or (s.get("decision") or "") != plan["decision"]
                    or B.claimed_by_batch(inc, now)
                    or any(r.get("key") == key for r in inc.get("retries") or [])
                    or (trigger == "daily" and not due_daily(inc, now))):
                continue                              # moved since it was read, or taken
            g = _guard_of(s)
            rec = {"id": "rt-" + uuid.uuid4().hex[:12], "key": key, "trigger": trigger,
                   "trigger_words": words, "script": script, "at": _iso(now), "epoch": now,
                   "by": by or "Mercury",
                   "from": {"decision": s.get("decision") or "", "outcome": s.get("outcome"),
                            "guard": g, "words": (s.get("words") or "")[:300]},
                   "fixes": []}
            if plan["kind"] == "skip":
                h = plan["hold"] or {}
                rec.update(state="skipped", failed=False, done_epoch=now,
                           words=(f"Retried at {_hhmm(now)} UTC: {words}; not tried: guard "
                                  f"{h.get('guard') or g} still holds"
                                  + (f" ({h['words']})" if h.get("words") else "")))
                out["skipped"].append(inc["id"])
            else:
                rec.update(state="deciding", failed=False,
                           words=f"Retried at {_hhmm(now)} UTC: {words}; deciding again")
                # Back for a fresh decision, as a settled incident is (`incidents.settle`):
                # its grace's settlement kept, never a second decision path.
                # An act's standing is kept as ``stood`` (the review, finding 5): a re-decision
                # that would close it puts it back on that act (`decide._act`).
                inc.update(state="ready" if inc.get("settled") else "watching",
                           standing=None, stood=s if s.get("act") else None, claimed=None,
                           retry_pending=rec["id"],
                           updated_at=_iso(now),
                           unsettled={"at": _iso(now), "why": f"tried again: {words}",
                                      "from": f"standing on {s.get('decision') or '?'}"})
                if not inc.get("settled"):
                    inc["defer_until"] = None
                out["retried"].append(inc["id"])
            inc["retries"] = (list(inc.get("retries") or []) + [rec])[-KEPT:]
        return out

    incidents._mutate(network, change)
    out.update(ran=True, words=(f"{words}: {len(out['retried'])} incident(s) sent back for a "
                                f"fresh decision, {len(out['skipped'])} still held"))
    log.info("heal: %s's retry (%s): %s", network, key, out["words"])
    if out["retried"] and decide_now:
        from modules.heal import decide
        got = decide.run(network, now=now, by=f"the retry ({words})")
        out["decided"] = {d["incident"]: d["outcome"] for d in got.get("decided") or []}
        if got.get("busy"):
            log.info("heal: %s's retry waits for the next decision: %s", network, got["busy"])
    try:
        from modules import invalidation
        invalidation.announce(invalidation.ANNOUNCERS["heal-decide"], by="heal-decide")
    except Exception as exc:                          # noqa: BLE001 (said; recorded)
        log.info("heal: %s's retry recorded, not announced: %s", network, exc)
    return out


def run_soon(network: str, trigger: str, **kw) -> None:
    """`run` on its own thread: a switch, a save or a promote answers at once; the decision
    and each script's run hold their device and are announced as they record."""
    import threading

    def go():
        try:
            run(network, trigger, **kw)
        except Exception as exc:                      # noqa: BLE001 (said; the daily retry runs)
            log.error("heal: %s's retry (%s) failed: %s: %s", network, trigger,
                      type(exc).__name__, exc)
    threading.Thread(target=go, name=f"heal-retry-{network}", daemon=True).start()


def daily(network: str, now: float = None) -> dict:
    """The daily retry of *network*, asked on every detect pass (`detect._retry_step`): `run`
    with ``daily`` only when an incident standing on a can't-fix, an act (C3870) or a person's
    hold has not
    been tried for `DAY_S` (from its recorded retry or decision); otherwise one read of the
    incidents store and nothing else."""
    from modules.heal import incidents

    now = time.time() if now is None else float(now)
    got = incidents.read(network)
    if got["state"] != "ok" or not any(
            i.get("state") == "standing" and due_daily(i, now)
            and ((i.get("standing") or {}).get("outcome") == "cant_fix"
                 or (i.get("standing") or {}).get("act")
                 or ((i.get("standing") or {}).get("outcome") == "held"
                     and _guard_of(i.get("standing")) in WERE_HELD))
            for i in got["incidents"]):
        return {"ran": False, "network": network, "trigger": "daily", "words": "none due"}
    return run(network, "daily", instance=time.strftime("%Y-%m-%d", time.gmtime(now)),
               by="Mercury", now=now)


def now_auto(network: str, now: float = None) -> dict:
    """C3844's catch-up, asked on every detect pass (`detect._retry_step`): while *network* is
    in Auto, each standing would-heal decided in dry run is decided again once (`run` with
    ``now_auto``), keyed by the Auto confirmation's instant (``now_auto:<at>``, recorded on the
    incident under the incidents store's lock, so another worker's pass or a restart never
    takes it twice for that confirmation); otherwise one read of the policy and the incidents
    store and nothing else."""
    from modules.heal import incidents, policy

    now = time.time() if now is None else float(now)
    mode = policy.current(network, now)
    if mode.get("mode") != "auto":
        return {"ran": False, "network": network, "trigger": "now_auto", "words": "not in Auto"}
    at = str((mode.get("confirmed") or {}).get("at") or mode.get("fingerprint") or "")
    key = f"now_auto:{at}"
    got = incidents.read(network)
    if got["state"] != "ok" or not any(
            i.get("state") == "standing"
            and (i.get("standing") or {}).get("outcome") == "would_heal"
            # Its mode where the standing record carries it (since C3844); else the
            # decisions are read in `run`.
            and (i.get("standing") or {}).get("mode") != "auto"
            and not any(r.get("key") == key for r in i.get("retries") or [])
            for i in got["incidents"]):
        return {"ran": False, "network": network, "trigger": "now_auto", "words": "none"}
    return run(network, "now_auto", instance=at, by="Mercury", now=now)


def _fix_state(outcome: str) -> str:
    return {"nothing": "fixed", "heal": "running", "propose": "proposed", "cant_fix": "no_fix",
            "held": "held", "failed": "failed", "deferred": "deferred"}.get(outcome, outcome)


def finish(network: str, incident_id: str, retry_id: str, d: dict, fires: list, *,
           now: float = None) -> dict:
    """The retry *retry_id* on *incident_id* finished by the decision *d* that took it and the
    saved scripts it fired (*fires*, `saved_plans.fire_matching`'s answers): each fix and its
    outcome recorded on the retry, its words, and whether every fix failed (``failed``, the
    failure R1 sees, `failures_of`). Called by `decide.run`, whichever process decides it."""
    from modules.heal import incidents
    from modules.nsot import saved_plans

    now = time.time() if now is None else float(now)
    g = d.get("guard") if isinstance(d.get("guard"), dict) else {}
    state = ("deferred" if d.get("outcome") in ("held", "deferred") and d.get("until")
             else _fix_state(d.get("outcome") or ""))
    fixes = [{"fix": "decision", "name": "Mercury's own fix", "decision": d.get("id") or "",
              "outcome": d.get("outcome") or "", "state": state, "guard": g.get("guard"),
              # What Mercury did or would do (C2817), its cause the decision's own.
              "words": (d.get("outcome_words") or d.get("words") or "")[:300]}]
    every = saved_plans.scripts(network)
    for f in fires or []:
        e = every.get(f.get("key") or "") or {}
        before = [r for r in e.get("track") or [] if r.get("incident") == incident_id
                  and r.get("mode") == "auto" and r.get("sent") and not r.get("ok")
                  and r.get("retry") != retry_id]
        ok = bool(f.get("ok")) and f.get("mode") == "auto" and bool(f.get("sent"))
        fixes.append({"fix": "script", "key": f.get("key") or "", "name": e.get("name") or
                      f.get("key") or "", "mode": f.get("mode") or "", "sent": bool(f.get("sent")),
                      "state": "fixed" if ok else "failed" if f.get("sent") else "not_run",
                      "again": bool(before), "words": str(f.get("words") or "")[:300]})
    failed = state in FAILED_STATES and not any(x["state"] == "fixed" for x in fixes[1:])

    def said(x):
        if x["fix"] == "decision":
            return f"Mercury's own fix: {x['words'] or x['outcome']}"
        if x["state"] == "fixed":
            return f"saved script {x['name']} fixed it"
        if x["state"] == "failed":
            return (f"saved script {x['name']} failed{' again' if x['again'] else ''}"
                    + (f" ({x['words']})" if x["words"] else ""))
        return f"saved script {x['name']}: {x['words'] or 'not run'}"

    def change(doc):
        inc = incidents._find(doc, incident_id)
        for r in inc.get("retries") or []:
            if r.get("id") == retry_id:
                r.update(state="done", fixes=fixes, failed=failed, done_epoch=now,
                         done_at=_iso(now),
                         words=(f"Retried at {_hhmm(float(r.get('epoch') or now))} UTC: "
                                f"{r.get('trigger_words') or 'a retry'}; "
                                + "; ".join(said(x) for x in fixes)))
                break
        if inc.get("retry_pending") == retry_id:
            inc.pop("retry_pending", None)
        return inc
    return incidents._mutate(network, change)


def failures_of(record: dict) -> list:
    """The failures of Mercury's fix the incident *record*'s retries are, for R1's one reader
    (`fixit.auto.pending`): each finished retry whose fixes all failed, keyed by the retry
    (``retry:<id>``), its time the retry's end, EXCEPT a daily retry's (the operator,
    2026-11-16: a daily retry never starts the AI; whether new evidence or a new capability
    should is a follow-up). Its outcome is the trigger."""
    from modules.fixit.auto import key_of

    out = []
    for r in (record or {}).get("retries") or []:
        if r.get("state") != "done" or not r.get("failed") or r.get("trigger") == "daily":
            continue
        epoch = float(r.get("done_epoch") or r.get("epoch") or 0)
        out.append({"key": key_of("retry", r["id"]), "kind": "retry", "id": r["id"],
                    "incident": record.get("id") or "", "device": record.get("device") or "",
                    "outcome": r.get("trigger") or "", "epoch": epoch,
                    "at": _iso(epoch) if epoch else "", "words": r.get("words") or ""})
    return out


def reason(network: str, record: dict) -> str:
    """Why a person is needed on an incident whose fixes failed, from its own record (the
    operator, 2026-11-16), or ``""``: what Mercury tried on THIS incident (its saved scripts'
    failed runs on it, from their track records; its own decisions' can't-fixes, from its
    retries), or, for a lost stream, that Mercury has no fix it runs by itself; then its last
    retry, and that the AI can investigate. Nothing before this incident counts: a person's
    Re-subscribe runs are never Mercury's fixes, nor are any on its device before it opened."""
    from modules.heal import diagnose_stream
    from modules.nsot import saved_plans

    rec = record or {}
    iid = rec.get("id") or ""
    if not iid:
        return ""
    rs = [r for r in rec.get("retries") or [] if r.get("state") in ("done", "skipped")]
    try:
        lost = bool(diagnose_stream.target_from(rec))
    except Exception:                                 # noqa: BLE001 (said without it)
        lost = False
    failed = {}
    try:
        for e in saved_plans.scripts(network).values():
            n = sum(1 for r in e.get("track") or [] if r.get("incident") == iid
                    and r.get("mode") == "auto" and r.get("state") == "done"
                    and r.get("sent") and not r.get("ok"))
            if n:
                failed[e.get("name") or e.get("key")] = n
    except Exception as exc:                          # noqa: BLE001 (said without them)
        log.error("heal: %s's saved scripts could not be read: %s", iid, exc)
    if not (rs or failed or lost):
        return ""
    parts = []
    if failed:
        parts.append("Mercury's fixes failed: " + ", ".join(
            f"saved script {name} {times(n)}" for name, n in sorted(failed.items())))
    if lost:
        parts.append("Mercury has no fix it runs by itself for a lost stream; Re-subscribe is a "
                     "person's operation")
    else:
        no_fix = sum(1 for r in rs for x in r.get("fixes") or []
                     if x.get("fix") == "decision" and x.get("state") == "no_fix")
        first = (rs[0].get("from") or {}).get("outcome") if rs else ""
        no_fix += 1 if first == "cant_fix" else 0
        if no_fix:
            parts.append(f"Mercury has no fix of its own for this (decided {times(no_fix)})")
    if rs:
        last = rs[-1]
        at = _hhmm(float(last.get("epoch") or 0))
        parts.append(f"Not retried at {at} UTC ({last.get('trigger_words')}): a guard still "
                     "holds" if last.get("state") == "skipped" else
                     f"Retried at {at} UTC: {last.get('trigger_words')}")
    return ". ".join(parts) + ". The AI can investigate"
