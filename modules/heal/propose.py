"""Tier 2: a heal that needs a person, proposed, then approved or declined (board H, part H5;
docs/HEAL_TO_INTENT.md sections 4 step 3, 5, 9 (artboard E), 11 and 19.8; N17; C2374).

**The proposal** is the decision H3 recorded (`decisions.proposals`): outcome ``propose``, its
units by kind and tier (masked), the program (masked) and its hash, the departure, the policy
it was made under and the person whose change it would fix. `view` adds what a person reads
before deciding: the program; the process reset a fix that takes effect only through one needs
(`privileged.PROCESS_RESETS`: R8's router-id), what it affects, what it will not do and why a
rollback cannot undo it; whether that reset is measured on the device's platform; the stops
that would refuse it now; and the **proposal's hash** (`proposal_hash`: the network, the
device, the decision, the program's hash and the reset's command), which the approval confirms.

**Approve** (`approve`): a verified person, a reason of three words or more, and the hash as
previewed. Refused with nothing taken or sent when any of those fails, when the proposal was
taken already, when its reset is not measured on the device's platform (`privileged.reset_plan`:
the shipped record holds no measurement, so R8's proposal is refused, saying so, until H11's lab
measurements), or when a stop applies (the kill switch, self-healing off on the network, a halt,
planned work, a kind the policy no longer proposes). Otherwise its mark is held
(`interrupted.hold`) and the decision taken once (`decisions.take`), and the act runs as a job
(`start`) AS THE PERSON (`identity.carried`, so its golden commit reads ``Actor-Verified:
access``), through H4's parts (`apply_approved`, `STEPS`):
1. **take**, once; a second take is refused by name;
2. **stops**, judged again in the job;
3. **read** the device again (the capture path's one checked read);
4. **plan against that read**: the units classified again and the program recomputed
   (`decide.program`), refused unless its hash is the decision's, its tier still 2, nothing
   blocked, and its reset the one planned; then THE plan (`plan_devices`) with that read as its
   capture source, refused unless its program is the proposal's, byte for byte, it is
   deployable, and it cuts nothing of Mercury's reach;
5. **authorise**: every line the CI gate flags (`authorisation.flagged`: a dangerous line, a
   removal) carries the person's reason, in the hash and the receipt;
6. **apply** as the person (``actor_kind="person"``) through `apply_batch`, holding the device;
7. **after the pipeline verified, the device still held and its save held** (``after_verify``):
   each unit at intent, or what landed is undone; then the measured **reset**
   (`privileged.send_reset` on the apply's own session): its before-state kept, the measured
   prompt alone answered, the neighbour table read until the adjacencies formed before are
   formed again within about 2.5 times the measured settle time, and its Tier 2 record written
   as the person with their reason (`privileged.reset_record`; History's privileged commands).
   A reset not made (a question it does not record, or the device refusing it) puts the change
   back: nothing is left half applied. A reset made cannot be undone, so it is kept whatever
   its verify says, and the symptom decides the outcome;
8. **saved, golden, symptom** and **record** as a heal's (`act._judge`): the golden re-check,
   the symptom read once the device is released, `decisions.applied`, `incidents.close`, the
   change record and the NetBox journal entry naming the person (H6), and the step log's
   ``started`` row before anything is sent and its ``act`` row at the end, ``by`` the person.

**Decline** (`decline`): a verified person with a reason. The decision is taken and recorded
``declined``, its incident closed (a later read may propose again), and its step log's ``act``
row written as the person; nothing is sent.

**Withdrawn** (`withdraw`, C2470; board H artboard E: "If <device> changes, the proposal is
withdrawn and made again"): the detect pass reads a waiting proposal's device again
(`detect._proposals`); read back at its golden, which matched its intent, the proposal is
withdrawn and its incident closed; read with another departure than the one it was bound to,
it is withdrawn and its incident watched again, so the decision makes it again by its normal
path. One row in the decisions store (`decisions.withdraw`, so a person's approval and a
withdrawal never both take it) and an ``act`` row in the step log, each naming the read and the
bound state; nothing is sent. Its card says so (`view`'s ``withdrawn``), and its approval is
refused naming the hash confirmed and both states.

**Where it is drawn** is H9's (board H artboard E: the Needs attention row ``heal``/``proposal``
with **Approve…** and **Decline…**); the routes are `routes/heal_proposal_v2.py`'s, registered
with that screen.
"""

import hashlib
import json
import logging
import time

from modules.heal import act

log = logging.getLogger(__name__)

#: The approved act's steps, in order, for the step log and the manual's How it works page.
STEPS = (("take", "Take the approved proposal, once"),
         ("stops", "Check the kill switch, the mode, a halt, planned work and the kind proposed"),
         ("read", "Read the device again"),
         ("plan", "Recompute the program from that read, and compare its hash"),
         ("authorise", "Give each line that needs one the approving person's reason"),
         ("apply", "Apply as the person who approved it, holding the device: the deploy's "
                   "nine stages"),
         ("intent", "Check each fixed unit is at intent"),
         ("reset", "Send the measured process reset the fix needs, still holding the device"),
         ("saved", "Saved to startup once verified, the device released"),
         ("golden", "Read the device again against its new golden"),
         ("symptom", "Read the symptom again"),
         ("record", "Record the outcome and close the incident"))
DECLINED = "declined"
#: A reason's shape (`authorisation.MIN_WORDS`, `MIN_CHARS`): never its quality.
REASON_WORDS = 3
REASON_CHARS = 8
#: The reset's own states, as the step log's result for its step.
RESET_RESULT = {"done": "ok", "not_back": "failed", "unverified": "unknown",
                "refused": "refused", "rejected": "failed"}


class Refused(ValueError):
    """Nothing was taken or sent; the message names why."""


class NotAPerson(Refused):
    """Refused because the request is not a verified person's."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _person(actor: str, actor_verified: str, person: bool, what: str) -> None:
    if not actor or actor_verified in ("", "none") or not person:
        raise NotAPerson(f"{what} is a verified person's, and this request is not one (actor "
                         f"{actor or 'none'}, verified {actor_verified or 'none'}). Nothing "
                         "was taken or sent")


def _reason(reason: str, what: str) -> str:
    text = (reason or "").strip()
    if len(text.split()) < REASON_WORDS or len(text) < REASON_CHARS:
        raise Refused(f"{what} needs a reason of {REASON_WORDS} words or more, recorded as the "
                      f"person's statement ({len(text.split())} given). Nothing was taken or "
                      "sent")
    return text


class Sources(act.Sources):
    """H4's sources, and the reset sent on the apply's own session."""

    def reset(self, device: str, dev: dict, ctx, plan: dict) -> dict:
        """Send *plan* on the session the pipeline holds for *device* (``ctx``'s pool), masked
        by the one redactor. A question left unanswered closes that session, which abandons the
        command; a rollback opens a new one."""
        from modules.commands import run_device_command
        from modules.connection import close_persistent_connection, get_persistent_connection
        from modules.nsot import privileged
        from modules.redact import known_secret_values, redact_text

        values = known_secret_values()
        conn = get_persistent_connection(dev, ctx.connections_pool, ctx.pool_lock)

        def read(cmd):
            return redact_text(run_device_command(conn, cmd) or "", values)

        def send(text):
            return redact_text(conn.send_command_timing(text, strip_prompt=False,
                                                        strip_command=False, read_timeout=30,
                                                        last_read=2.0) or "", values)

        got = privileged.send_reset(plan, read=read, send=send, clock=self.clock,
                                    sleep=self.sleep)
        if got.get("state") == "refused":
            close_persistent_connection(dev.get("ip", ""), ctx.connections_pool, ctx.pool_lock)
        return got


# ── The proposal ────────────────────────────────────────────────────────────────────────────

def _section(u: dict) -> str:
    return u.get("section") or ((u.get("chain") or [""])[0] if u.get("chain") else "")


def resets_of(units: list, *, dialect: str, device: str) -> dict:
    """The process reset the units need (``process_reset``'s, R8): ``{"needed", "plan",
    "refused"}``. One reset a proposal; a routing process Mercury does not reset, or a reset
    not measured on *dialect*, refuses, naming why (`privileged.reset_plan`)."""
    from modules.nsot import privileged

    sections = sorted({_section(u) for u in units or [] if u.get("kind") == "process_reset"})
    if not sections:
        return {"needed": False, "plan": None, "refused": ""}
    if len(sections) > 1:
        return {"needed": True, "plan": None, "refused": (
            f"the fix needs {len(sections)} process resets ({'; '.join(sections)}), and a "
            "proposal sends one: a person makes this fix. Nothing was sent")}
    which = privileged.reset_for(sections[0])
    if which["refused"]:
        return {"needed": True, "plan": None, "refused": which["refused"] + ". Nothing was sent"}
    plan = privileged.reset_plan(which["key"], which["process"], dialect=dialect, device=device,
                                 purpose="router_id")
    return {"needed": True, "plan": plan, "refused": plan["refused"]}


def proposal_hash(network: str, decision: dict, reset_command: str) -> str:
    """What an approval confirms: the network, the device, the decision, the program's hash and
    the reset's command."""
    body = {"network": network, "device": decision.get("device") or "",
            "decision": decision.get("id") or "",
            "program_hash": decision.get("program_hash") or "", "reset": reset_command or ""}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


def _stops(network: str, decision: dict, now: float, src) -> str:
    """Why the proposal may not be applied now, or ``""``: the kill switch, self-healing off,
    a kind the policy no longer proposes, a halt, planned work."""
    from modules.heal import decisions

    mode = src.mode(now)
    if (mode.get("stopped") or {}).get("stopped"):
        return f"self-healing is stopped everywhere: {mode['stopped'].get('words')}"
    if mode.get("mode") not in ("dry_run", "auto"):
        return (f"self-healing is off for {network} now ({mode.get('words')}), and a proposal "
                "is applied only while it is on")
    proposed = set(mode.get("kinds_propose") or [])
    kinds = sorted({u.get("kind") for u in decision.get("units") or [] if u.get("tier") == 2})
    off = [k for k in kinds if k not in proposed]
    if off:
        return (f"{', '.join(off)} {'is' if len(off) == 1 else 'are'} no longer proposed by "
                f"{network}'s policy (proposed now: {', '.join(sorted(proposed)) or 'none'})")
    try:
        halt = decisions.halted(network)
    except Exception as exc:
        return f"whether {network} is halted cannot be read ({exc}), and a halt unread holds"
    if halt.get("id"):
        return f"{network}'s self-healing is halted by guard {halt.get('guard')}: {halt.get('words')}"
    g = src.planned(decision["device"], now)
    if g:
        return f"guard 3, planned work: {g['words']}"
    return ""


def _steps_of(decision: dict) -> tuple:
    """The approved act's steps: a session clear's (H21), the dampening proposal's (H22) or a
    heal's."""
    from modules.heal import dampening, session_clear

    kind = (decision.get("action") or {}).get("kind")
    if kind in session_clear.KINDS:
        return session_clear.STEPS
    if kind == dampening.KIND:
        return dampening.STEPS
    return STEPS


def _is_dampening(decision: dict) -> bool:
    from modules.heal import dampening

    return (decision.get("action") or {}).get("kind") == dampening.KIND


def _find(network: str, decision_id: str) -> dict:
    from modules.heal import decisions

    try:
        d = decisions.find(network, decision_id)
    except decisions.Refused as exc:
        raise Refused(str(exc)) from None
    except RuntimeError as exc:
        raise Refused(f"{network}'s heal decisions cannot be read ({exc}). Nothing was taken or "
                      "sent") from None
    if d.get("outcome") != "propose":
        raise Refused(f"{decision_id} is {decisions.OUTCOME_WORDS.get(d.get('outcome'), d.get('outcome'))}"
                      ", not a proposal: only a fix that waits for a person is approved or "
                      "declined")
    return d


def view(network: str, decision_id: str, *, now: float = None, sources=None) -> dict:
    """The proposal as a person reads it before deciding (the module's docstring); reads only
    Mercury's records, never the device. ``{"network", "decision", "incident", "device",
    "platform", "kind", "kind_words", "tier", "units", "program", "program_hash", "reset",
    "lines", "hash", "refusals", "confirmable", "person", "policy", "triggers", "words", "at",
    "steps", "withdrawn", "diagnosis"}``; *withdrawn* is the withdrawal's record (C2470) or
    None; *diagnosis* is Mercury's diagnosis of its incident (`auto_diagnose.drawn`, H17)."""
    from modules.heal.kinds import KIND_WORDS

    now = time.time() if now is None else float(now)
    src = sources or Sources(network)
    d = _find(network, decision_id)
    device = d["device"]
    dev = src.device(device)
    platform = src.platform(device, dev)
    r = resets_of(d.get("units") or [], dialect=platform, device=device)
    plan = r["plan"] or {}
    refusals = []
    if d.get("withdrawn"):
        # C2470: withdrawn by the heal's own pass, its words naming the read and the state the
        # proposal was bound to.
        w = d["withdrawn"]
        refusals.append(f"{decision_id} was {w.get('words')} (recorded at {w.get('at')})")
    elif d.get("taken"):
        done = (d.get("applied") or {}).get("outcome")
        refusals.append(f"{decision_id} was taken by {d['taken']['by']} at {d['taken']['at']}"
                        + (f" and is {done}" if done else ", and its act is running"))
    if r["refused"]:
        refusals.append(r["refused"])
    units = [u.get("words") for u in d.get("units") or []]
    if _is_dampening(d):
        # H22 (19.4): a change to intent, its rollback Mode B's measured removal (refused by
        # name until measured), lapsed once its port is stable for 24 h.
        from modules.heal import dampening, decisions
        units = dampening.units_words(d)
        if not d.get("taken") and not d.get("withdrawn"):
            try:
                rows = decisions.decisions(network)
            except Exception as exc:
                rows = []
                refusals.append(f"{network}'s heal decisions cannot be read ({exc}), so whether "
                                "the proposal lapsed cannot be told")
            refusals += dampening.refusals(d, rows, now)
    why = _stops(network, d, now, src)
    if why:
        refusals.append(why + ". Nothing was sent")
    reset = ({k: plan.get(k) for k in ("key", "label", "command", "read", "affects", "not_doing",
                                       "rollback", "measured", "bound_s", "refused")}
             if plan else None)
    program = list(d.get("program") or [])
    # H17 (19.3, N14; artboard E's insert): Mercury's diagnosis, run once the proposal was
    # made, drawn beside Approve…; running while its device is held for it. Never withdraws.
    from modules.heal import auto_diagnose
    diagnosis = auto_diagnose.drawn(network, d.get("incident") or "", device)
    return {"network": network, "decision": d["id"], "incident": d.get("incident"),
            "diagnosis": diagnosis,
            "device": device, "platform": platform, "kind": d.get("kind"),
            "kind_words": KIND_WORDS.get(d.get("kind"), d.get("kind")), "tier": d.get("tier"),
            "units": units, "program": program,
            "program_hash": d.get("program_hash") or "", "reset": reset,
            "lines": program + ([plan["command"]] if plan.get("command") else []),
            "hash": proposal_hash(network, d, plan.get("command") or ""),
            "refusals": refusals, "confirmable": not refusals,
            "person": (d.get("person") or {}).get("words") or "", "policy": d.get("policy") or {},
            "triggers": [t for t in d.get("triggers") or [] if t], "words": d.get("words") or "",
            "at": d.get("at"), "steps": [w for _n, w in _steps_of(d)],
            "withdrawn": dict(d["withdrawn"]) if d.get("withdrawn") else None}


# ── Approve ─────────────────────────────────────────────────────────────────────────────────

def approve(network: str, decision_id: str, *, confirmed_hash: str, reason: str, actor: str,
            actor_verified: str, person: bool, ident=None, now: float = None, sources=None,
            starter=None) -> dict:
    """Approve one proposal as previewed and start its act as a job: ``{"ok", "network",
    "decision", "device", "job", "hash"}``. Raises `NotAPerson` or `Refused` with nothing taken
    or sent (the module's docstring); *starter* is `start` unless given."""
    from modules.heal import decisions, incidents, interrupted

    now = time.time() if now is None else float(now)
    _person(actor, actor_verified, person, "approving a self-healing proposal")
    reason = _reason(reason, "approving a proposal")
    v = view(network, decision_id, now=now, sources=sources)
    if v["withdrawn"]:
        raise Refused(f"not approved: the proposal you confirmed ({confirmed_hash or 'no hash'}"
                      f"; the proposal's {v['hash']}) is no longer waiting: "
                      + "; ".join(v["refusals"]) + ". Nothing was taken or sent")
    if v["refusals"]:
        raise Refused("not approved: " + "; ".join(v["refusals"]))
    if (confirmed_hash or "") != v["hash"]:
        raise Refused(f"not approved: the proposal is not the one you confirmed (confirmed "
                      f"{confirmed_hash or 'no hash'}, now {v['hash']}); nothing was taken or "
                      "sent: read it again")
    try:
        interrupted.hold(network, decision_id, v["device"], by=actor)
    except (interrupted.Busy, OSError) as exc:
        raise Refused(f"not approved: {exc}") from None
    try:
        taken = decisions.take(network, decision_id, by=f"{actor}: approved", now=now)
    except decisions.Refused as exc:
        interrupted.release(network, decision_id)
        raise Refused(f"not approved: {exc}") from None
    full = (resets_of(taken.get("units") or [], dialect=v["platform"],
                      device=v["device"])["plan"] or None)
    approval = {"by": actor, "verified": actor_verified, "reason": reason, "hash": v["hash"],
                "at": _iso(now), "reset": full}
    try:
        job = (starter or start)(network, taken, approval, sources=sources, ident=ident)
    except Exception as exc:
        words = f"its job could not start ({type(exc).__name__}: {exc}). Nothing was sent"
        log.error("heal: %s's approved proposal %s could not start: %s", network, decision_id,
                  exc)
        try:
            decisions.applied(network, decision_id, "refused", by=actor, words=words, now=now)
            incidents.close(network, taken.get("incident"),
                            f"refused: {words} (decision {decision_id})", now)
        finally:
            interrupted.release(network, decision_id)
        raise Refused(f"not approved: {words}") from None
    return {"ok": True, "network": network, "decision": decision_id, "device": v["device"],
            "job": job, "hash": v["hash"]}


def start(network: str, decision: dict, approval: dict, *, sources=None, ident=None) -> str:
    """Run the approved act as a job (`capture_job.start`, a heal's kind and announcements),
    as the person (`identity.carried`); the mark `approve` took is released once its outcome is
    recorded, or it raised."""
    from modules import identity
    from modules.heal import interrupted
    from modules.nsot import capture_job

    def work(_job):
        try:
            with identity.carried(ident):
                return {"ok": True, "result": act._guarded(
                    network, decision, lambda: _approved_for(network, decision, approval,
                                                             sources=sources))}
        finally:
            interrupted.release(network, decision["id"])

    # The dampening proposal's act commits intent too, so its job announces intent (H22).
    from modules.heal import dampening
    keys, announcer = ((dampening.DONE_KEYS, dampening.ANNOUNCER) if _is_dampening(decision)
                       else (act.DONE_KEYS, act.ANNOUNCER))
    return capture_job.start(network, f"healing {decision['device']} (approved by "
                                      f"{approval['by']})", approval["by"], work, kind=act.KIND,
                             announce_keys=keys, announcer=announcer,
                             device=decision["device"])


def _approved_for(network: str, decision: dict, approval: dict, *, sources=None) -> dict:
    """An approved proposal's act: a BGP session clear's (19.4, H21: Tier 2 on a network not
    marked lab, `session_clear.apply_approved`, as the person), the dampening proposal's (H22,
    `dampening.apply_approved`: the intent commit and its deploy under one hash, as the
    person), or a heal's (`apply_approved`). One approval, one take, one record, whichever it
    is."""
    from modules.heal import dampening, session_clear

    if (decision.get("action") or {}).get("kind") in session_clear.KINDS:
        return session_clear.apply_approved(network, decision, approval)
    if _is_dampening(decision):
        return dampening.apply_approved(
            network, decision, approval,
            sources=sources if isinstance(sources, dampening.Sources) else None)
    return apply_approved(network, decision, approval, sources=sources)


def _said(got: dict) -> str:
    """A reset's result in words."""
    state = got.get("state")
    v = (got.get("verify") or {}).get("words") or ""
    waited = got.get("waited_s")
    if state == "done":
        return f"sent; {v}, within {waited} s"
    if state == "not_back":
        return f"sent; {v} after {waited} s: not every adjacency formed again"
    if state == "unverified":
        return f"sent; {v}"
    if state == "rejected":
        return f"not made: the device refused it ({got.get('why')})"
    return f"not sent: {got.get('why') or 'refused'}"


def apply_approved(network: str, decision: dict, approval: dict, *, now: float = None,
                   sources=None) -> dict:
    """Apply one taken, approved proposal as the person, verify it and record it (the
    module's steps 2 to 8): ``{"decision", "device", "outcome", "words", "steps", "sent",
    "report", "records"}``."""
    from modules import pipeline
    from modules.drift_check import departure, drift_diff
    from modules.heal import decide, decisions, incidents, kinds, steplog
    from modules.nsot import authorisation, privileged
    from modules.redact import redact_text

    now = time.time() if now is None else float(now)
    src = sources or Sources(network)
    device = decision["device"]
    by = approval["by"]
    via = f"heal proposal approved by {by}"
    pol = decision.get("policy") or {}
    steps = [{"step": "take", "result": "ok",
              "words": f"taken on {by}'s approval of proposal {approval['hash']}"}]
    held = {"dev": {}, "prog": None, "read": "", "entry": {}, "authorise": [], "platform": "",
            "golden_before": ""}
    reset = {"plan": None, "got": None}

    def step(name, result, words):
        steps.append({"step": name, "result": result, "words": redact_text(words),
                      "at": _iso(time.time())})

    def finish(outcome, words, *, sent=False, report=None):
        step("record", outcome, f"{act.OUTCOME_WORDS[outcome]}: {words}")
        try:
            decisions.applied(network, decision["id"], outcome, by=by, words=words, now=now)
            if outcome == "failed":
                decisions.halt(network, guard=14, name="a heal sent and not verified",
                               words=f"the approved heal of {device} ({decision['id']}) failed "
                                     f"after sending and was not rolled back: {words}",
                               operands={"decision": decision["id"], "device": device},
                               now=now)
        except Exception as exc:
            log.error("heal: %s's outcome on %s was not recorded: %s", network, device, exc)
        try:
            incidents.close(network, decision["incident"],
                            f"{outcome}: {words} (decision {decision['id']})", now)
        except Exception as exc:
            log.error("heal: %s's incident %s was not closed: %s", network,
                      decision.get("incident"), exc)
        log.info("heal: %s on %s, approved by %s: %s: %s", network, device, by, outcome, words)
        result = {"decision": decision["id"], "device": device, "outcome": outcome,
                  "words": redact_text(words), "steps": steps, "sent": sent, "report": report}
        plan = reset["plan"]
        said = dict(approval, reset=({"command": plan["command"],
                                      "words": _said(reset["got"]) if reset["got"] else
                                      "not sent: the act ended before it"} if plan else None))
        result["records"] = act._records(network, decision, result, src, held, now,
                                         approval=said)
        result["records"]["approval"] = (
            f"approved by {by} ({approval.get('verified')}) at {approval.get('at')}, confirming "
            f"proposal {approval.get('hash')}, with the reason \"{approval.get('reason')}\"")
        try:
            steplog.record_act(network, decision, result, by=by, now=now)
            result["records"]["step_log"] = "written"
        except Exception as exc:
            log.error("heal: %s's act on %s is not in the step log: %s", network, device, exc)
            result["records"]["step_log"] = f"not written: {type(exc).__name__}: {exc}"
        return result

    def refuse(name, words):
        step(name, "refused", words)
        return finish("refused", f"{words}. Nothing was sent")

    why = _stops(network, decision, now, src)
    if why:
        return refuse("stops", why)
    step("stops", "ok", "self-healing on, no halt, no planned work, the kind still proposed")

    dev = src.device(device)
    text, error = src.read(dev)
    if not text:
        return refuse("read", f"the read of {device} at apply could not be made ({error})")
    step("read", "ok", f"{device} read again")
    held.update(dev=dev, read=text)

    golden = src.golden(device, dev)
    held["golden_before"] = golden.get("commit") or ""
    if golden.get("state") != "at_intent" or not golden.get("text"):
        return refuse("plan", f"{device}'s golden is not at its intent now ("
                              f"{golden.get('words') or golden.get('state')})")
    platform = src.platform(device, dev)
    intended = src.intended(device, platform)
    if not intended.get("text"):
        return refuse("plan", f"committed intent cannot be rendered: {intended.get('why')}")
    inc = act._incident(network, decision["incident"])
    c = kinds.classify(golden["text"], text, intended["text"], platform=platform,
                       mgmt_ip=dev.get("ip", ""), related=bool(inc.get("related")))
    prog = decide.program(golden["text"], text, c["units"], c["removal_ids"],
                          mgmt_ip=dev.get("ip", ""), platform=platform)
    dep = departure(drift_diff(golden["text"], text, device))
    if prog["hash"] != decision.get("program_hash"):
        return refuse("plan", (f"the program recomputed from the read at apply is not the one "
                               f"proposed (proposed {decision.get('program_hash')}, now "
                               f"{prog['hash']}): {act._moved(decision, c['units'], prog, dep)}; "
                               "this proposal is closed, and a later read starts over"))
    if prog["refused"] or c.get("blocked") or c["tier"] != 2:
        return refuse("plan", "the program is not the proposal's now: "
                              + ((prog["refused"] or [{}])[0].get("reason")
                                 or (c.get("blocked") or {}).get("why")
                                 or f"its tier is {c['tier']}, not 2"))
    r = resets_of(c["units"], dialect=platform, device=device)
    if r["refused"]:
        return refuse("plan", r["refused"].removesuffix(". Nothing was sent"))
    planned_reset = ((approval.get("reset") or {}).get("command") or "")
    if ((r["plan"] or {}).get("command") or "") != planned_reset:
        return refuse("plan", (f"the reset is not the one approved (approved "
                               f"{planned_reset or 'none'}, now "
                               f"{(r['plan'] or {}).get('command') or 'none'})"))
    reset["plan"] = r["plan"]
    step("plan", "ok", (f"the program recomputed from the read: {len(prog['commands'])} line(s), "
                        f"hash {prog['hash']}, the proposal's"
                        + (f"; then {r['plan']['command']} (measured on {platform})"
                           if r["plan"] else "")))
    held.update(prog=prog, platform=platform)

    flagged = authorisation.flagged(prog["commands"], prog["keys"])
    authorise = [{"line": k, "reason": approval["reason"]} for k in flagged]
    held["authorise"] = authorise
    step("authorise", "ok", (f"{len(authorise)} line(s) that need a reason carry {by}'s"
                             if authorise else "nothing that needs a reason"))
    dangerous = pipeline.dangerous_commands(prog["commands"])
    capture = {device: {"text": kinds._stored(text), "intended": prog["fragment"]}}
    plan_kw = {"authorise": {device: authorise}, "remove": {device: list(c["removal_ids"])},
               "capture": capture}
    entry = src.plan(device, **plan_kw)
    held["entry"] = entry
    if entry.get("refused") or entry.get("error"):
        return refuse("plan", f"the deploy's plan refused it: "
                              f"{entry.get('refused') or entry.get('error')}")
    if not entry.get("deployable", True) or entry.get("blocking_reasons"):
        return refuse("plan", "the deploy's plan refused it: "
                              + "; ".join(entry.get("blocking_reasons") or ["not deployable"]))
    if list(entry.get("commands") or []) != prog["commands"]:
        return refuse("plan", (f"the deploy's plan ({len(entry.get('commands') or [])} line(s)) "
                               f"is not the proposal's program ({len(prog['commands'])} line(s)):"
                               " what is approved is what is sent, byte for byte"))
    if entry.get("authorisation_ok") is False:
        return refuse("authorise", f"the plan's authorisation check refused it: "
                                   f"{entry.get('authorisation_error')}")
    lost = (entry.get("expected_effects") or {}).get("reach_lost") or {}
    if lost and (lost.get("state") != "known" or lost.get("cut")):
        return refuse("plan", ("the fix would cut Mercury's path ("
                               f"{', '.join(lost.get('cut') or []) or lost.get('why')}), and a "
                               "change to that path needs a repair route independent of it"))

    def after_verify(host, result, ctx):
        post = ((result.get("golden_pending") or [{}])[0] or {}).get("config_text") or ""
        left = act.units_left(c["units"], post) if post else ["no read after the change"]
        state = src.intent_state(device, post, platform) if post else {
            "state": "unknown", "words": "no read after the change"}
        record = {"intent": {"left": left, **state}}
        if left:
            step("intent", "failed", f"{len(left)} unit(s) not at intent: {left[0]}")
            return {"rollback": (f"{len(left)} unit(s) not at intent after the change "
                                 f"({left[0]}), so what landed was undone"), "record": record}
        step("intent", "ok", f"each unit at intent; intent: {state['words']}")
        plan = reset["plan"]
        if not plan:
            return {"rollback": "", "record": record}
        started = time.time()
        got = src.reset(device, held["dev"], ctx, plan)
        reset["got"] = got
        said = _said(got)
        record["reset"] = {"command": plan["command"], "state": got.get("state"), "words": said}
        try:
            run = privileged.reset_record(network, plan, got, actor=by,
                                          reason=approval["reason"], hash_=approval["hash"],
                                          decision=decision["id"], started=started)
            record["reset"]["run"] = run["id"]
        except Exception as exc:
            log.error("heal: %s's reset record for %s was not written: %s", network, device, exc)
            record["reset"]["run"] = f"not written: {type(exc).__name__}: {exc}"
        step("reset", RESET_RESULT.get(got.get("state"), "failed"), f"{plan['command']}: {said}")
        if got.get("state") in ("refused", "rejected"):
            return {"rollback": (f"the process reset was not made ({said}), so the change that "
                                 "takes effect only through it was put back: nothing is left "
                                 "half applied"), "record": record}
        return {"rollback": "", "record": record}

    facts = {"decision": decision["id"], "incident": decision.get("incident"),
             "kind": decision.get("kind"), "mode": decision.get("mode"),
             "policy": {"fingerprint": pol.get("fingerprint"), "by": pol.get("by"),
                        "reason": pol.get("reason") or ""},
             "person": dict(decision.get("person") or {}), "program_hash": prog["hash"],
             "approved": {"by": by, "verified": approval.get("verified"),
                          "reason": approval["reason"], "hash": approval["hash"]},
             "reset": (r["plan"] or {}).get("command") or ""}
    lines = [redact_text(x) for x in prog["commands"]] + (
        [r["plan"]["command"]] if r["plan"] else [])
    try:
        steplog.record_started(network, decision, steps + [{
            "step": "apply", "result": "running",
            "words": f"as {by}, who approved it, holding {device}"}], lines, prog["hash"],
            by=by, now=now)
    except Exception as exc:
        return refuse("apply", (f"the program could not be written to the step log before it "
                                f"is sent ({type(exc).__name__}: {exc}), and a heal sends "
                                "nothing it has not recorded"))
    step("apply", "running", f"as {by}, who approved it, holding {device}"
                             + (f"; {len(dangerous)} dangerous line(s) carry the reason"
                                if dangerous else ""))
    report = src.apply(
        device, confirmations={device: entry.get("capture_hash")},
        command_hashes={device: entry.get("command_hash")}, actor=by, actor_kind="person",
        stop_at_first=True, after_verify=after_verify, heal={device: facts}, hold_detail=via,
        **plan_kw)
    got = next((x for x in report.get("results") or [] if x.get("device") == device), {})

    def symptom():
        s = src.symptom(device, inc.get("triggers") or [], now)
        step("symptom", s["state"], s["words"])
        return s

    return act._judge(device, got, report, src, via, step, finish, symptom)


# ── Withdrawn (C2470) ───────────────────────────────────────────────────────────────────────

def withdrawn_how(decision: dict, read: dict) -> str:
    """Whether *read* (the detect pass's read of a waiting proposal's device: its state and
    departure, `detect.read_device`'s) withdraws the proposal: ``at_intent`` (read back at its
    golden, which matched its intent when it was proposed: guard 4), ``changed`` (a departure
    other than the one the proposal was bound to), or ``""`` (still the departure it was made
    for, or a read that says nothing of the device: an error, a skip, a busy run). A dampening
    proposal (H22) is bound to no departure: its device is at intent by its own rule, so a read
    never withdraws it; it lapses by time instead (`dampening.lapsed`)."""
    if _is_dampening(decision):
        return ""
    state = (read or {}).get("state")
    if state == "clean":
        return "at_intent"
    if state == "drifted" and (read.get("departure") or "") != (decision.get("departure") or ""):
        return "changed"
    return ""


def withdraw(network: str, decision: dict, read: dict, *, how: str, now: float = None,
             by: str = "heal to intent") -> dict:
    """Withdraw one waiting proposal the heal's own pass read its device against (board H
    artboard E: "If <device> changes, the proposal is withdrawn and made again. Clears when
    ... <device> is back at intent"): recorded in the decisions store (`decisions.withdraw`, one row, so its
    Needs attention row leaves) and the step log (an ``act`` row, ``withdrawn``, nothing sent),
    with the read and the state it was bound to. ``at_intent`` closes its incident; ``changed``
    sends it back to watching (`incidents.defer`), its grace period restarting at once, so the
    decision makes it again from the device as it is now, by its normal path. ``{"decision",
    "device", "how", "words", "records"}``; raises `decisions.Refused` when a person took it
    first (their approval or decline stands)."""
    from modules.heal import decisions, incidents, steplog

    now = time.time() if now is None else float(now)
    device = decision.get("device") or ""
    bound = (f"it was bound to {device} as read at {decision.get('at') or 'an unrecorded time'}"
             f" (departure {decision.get('departure') or 'none'})")
    if how == "at_intent":
        words = (f"withdrawn: {device} read back at its golden, which matches its intent, at "
                 f"{read.get('at')}, so nothing is left to fix; {bound}")
    else:
        words = (f"withdrawn: {device} changed since it was proposed (read at {read.get('at')}, "
                 f"departure {read.get('departure') or 'none'}); {bound}. Its grace period "
                 "starts again, and the decision makes it again from the device as it is now")
    d = decisions.withdraw(network, decision["id"], how=how, by=by, words=words, read=read,
                           now=now)
    records = {"decision": f"withdrawn in {network}'s heal decisions ({decision['id']})"}
    try:
        if how == "at_intent":
            incidents.close(network, decision.get("incident"),
                            f"{decisions.WITHDRAWN}: {words} (decision {decision['id']})", now)
            records["incident"] = "closed"
        else:
            incidents.defer(network, decision.get("incident"), now,
                            f"{decisions.WITHDRAWN}: {words} (decision {decision['id']})", now)
            records["incident"] = "watching again"
    except Exception as exc:
        log.error("heal: %s's incident %s after withdrawing %s: %s", network,
                  decision.get("incident"), decision["id"], exc)
        records["incident"] = f"not moved: {type(exc).__name__}: {exc}"
    result = {"decision": decision["id"], "device": device, "outcome": decisions.WITHDRAWN,
              "how": how, "words": words, "sent": False,
              "steps": [{"step": "read", "result": read.get("state") or "",
                         "words": (f"{device} read at {read.get('at')}: departure "
                                   f"{read.get('departure') or 'none'}")},
                        {"step": "record", "result": decisions.WITHDRAWN,
                         "words": f"{words}. Nothing was sent"}],
              "records": records}
    try:
        steplog.record_act(network, d, result, by=by, now=now)
        records["step_log"] = "written"
    except Exception as exc:
        log.error("heal: %s's withdrawn proposal %s is not in the step log: %s", network,
                  decision["id"], exc)
        records["step_log"] = f"not written: {type(exc).__name__}: {exc}"
    log.info("heal: %s's proposal %s for %s %s", network, decision["id"], device, words)
    return result


# ── Decline ─────────────────────────────────────────────────────────────────────────────────

def decline(network: str, decision_id: str, *, reason: str, actor: str, actor_verified: str,
            person: bool, now: float = None) -> dict:
    """Decline one proposal as a verified person with a reason: taken, recorded ``declined``,
    its incident closed, its step log's ``act`` row written; nothing is sent. ``{"ok",
    "network", "decision", "device", "outcome", "words", "records"}``."""
    from modules.heal import decisions, incidents, interrupted, steplog

    now = time.time() if now is None else float(now)
    _person(actor, actor_verified, person, "declining a self-healing proposal")
    reason = _reason(reason, "declining a proposal")
    d = _find(network, decision_id)
    try:
        mark = interrupted.Mark(network, decision_id, d["device"], by=actor).acquire()
    except (interrupted.Busy, OSError) as exc:
        raise Refused(f"not declined: {exc}") from None
    try:
        try:
            taken = decisions.take(network, decision_id, by=f"{actor}: declined", now=now)
        except decisions.Refused as exc:
            raise Refused(f"not declined: {exc}") from None
        words = f"declined by {actor}: {reason}"
        decisions.applied(network, decision_id, DECLINED, by=actor, words=words, now=now)
        try:
            incidents.close(network, d.get("incident"),
                            f"{DECLINED}: {words} (decision {decision_id})", now)
        except Exception as exc:
            log.error("heal: %s's incident %s was not closed: %s", network, d.get("incident"),
                      exc)
        result = {"decision": decision_id, "device": d["device"], "outcome": DECLINED,
                  "words": words, "sent": False,
                  "steps": [{"step": "take", "result": "ok",
                             "words": f"taken by {actor} to decline it"},
                            {"step": "record", "result": DECLINED,
                             "words": f"{words}. Nothing was sent"}],
                  "records": {"approval": (f"declined by {actor} ({actor_verified}) at "
                                           f"{_iso(now)}, with the reason \"{reason}\"")}}
        try:
            steplog.record_act(network, taken, result, by=actor, now=now)
            result["records"]["step_log"] = "written"
        except Exception as exc:
            log.error("heal: %s's declined proposal %s is not in the step log: %s", network,
                      decision_id, exc)
            result["records"]["step_log"] = f"not written: {type(exc).__name__}: {exc}"
    finally:
        mark.release()
    log.info("heal: %s's proposal %s for %s declined by %s", network, decision_id,
             d["device"], actor)
    return dict(result, ok=True, network=network)
