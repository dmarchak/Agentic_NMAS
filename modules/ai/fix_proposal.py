"""The one door from an AI answer to anything runnable (docs/HEAL_TO_INTENT.md section 12, the
operator's rule of 2026-11-14, replacing 2026-11-11's; docs/MERCURY_CHARTER.md, "The fix-it
path", step 3): "No fix runs from AI text. The AI may propose a plan of catalog operations,
approved once by a person by hash, executed in order, stopping on the first failure; it never
composes commands, runs anything itself, or retries on its own; a saved fix is the operation a
person saved from a verified run." Until the plan engine lands this door takes a plan of one:
ONE operation of the catalog, refusing any other shape.

`proposal` takes what a recorded AI call answered and returns one of two things:
- the proposed operation's PREVIEW and its hash (`modules/heal/catalog.py`, `preview`: the
  operation's own plan, where committed intent and the operation's guards are asked), for a
  person to read and confirm at the operation's own confirm route; or
- a refusal, its words naming what was compared and both operands, RECORDED on the call's own
  use record (`calls.record_use`, "refused by validation", the reason whole and masked).

**What it accepts, and nothing else:** an object holding exactly ``operation`` (ONE key of the
catalog, as text) and ``params`` (an object giving that operation's parameters, each of its
schema's shape). Any other field, at either level, is refused because the schema does not
name it: a ``commands`` list, a ``program``, a ``retry`` or ``run`` flag are all only "a field
the schema does not name", and no text is matched as a pattern. A list of operations, two
operations or none are refused. The answer comes from a call the record of AI calls holds
(*call_id*): one that names no recorded call is refused too, since the gateway records every
call and a refusal's record is that call's.

**It never runs anything.** It opens no session, holds no device, starts no job and commits
nothing; an accepted proposal writes nothing at all, and a refused one writes its one use row.
It imports no function that sends (tests/test_ai_fix_rule.py scans every module of
`modules/ai/` for a reference to one, this module among them). From a proposal to a run is a
verified person's confirm, with the previewed hash, at the catalog entry's confirm route; a
failed run comes back as its record, and nothing here asks again.

**An incident's proposal** (`for_incident`, AI troubleshooting on the incident's page,
`modules/ai/fixit_troubleshoot.py`; docs/HEAL_TO_INTENT.md section 12, "The AI call (S5)"):
the same door, the same shape and the same recorded call, and then the same check as
Mercury's own proposal (`modules/fixit/validate.py`, `propose` with source ``ai``: the
catalog's schema, the incident's scope, the heal guards, committed intent through the
operation's own preview), which keeps the proposal's line in the incident's record with its
call ids, an accepted one opening its operation's preview and a refused one kept with no
operation. A refusal is recorded on the call's use record as `proposal` records it. No route
calls `proposal` itself yet (Explain's proposal, step 3, is a later slice).
"""

import logging

from modules.identity import acts_as_ai  # noqa: E402 (the AI's own identity, its role)

log = logging.getLogger(__name__)

#: The fields a proposal holds, exactly.
FIELDS = ("operation", "params")
#: The use a refused proposal is recorded as: the word the other drafted answers are refused
#: under (`intent_words.change`, `policy_intent.draft`).
REFUSED_USE = "refused by validation"
#: How many unknown field names a refusal says back.
NAMES_SAID = 8


def _shape(answer) -> tuple:
    """``(code, words)`` when *answer* is not one proposal's shape, else ``("", "")``."""
    from modules.heal.catalog import kind_of, listed, said

    if isinstance(answer, (list, tuple)):
        return "not_one_operation", (
            "a proposal is one operation with its parameters, and the answer is a list of "
            f"{len(answer)}")
    if not isinstance(answer, dict):
        return "not_an_object", (
            f"a proposal is an object holding {listed(FIELDS)}, and the answer is "
            f"{kind_of(answer)}")
    unknown = [k for k in answer if k not in FIELDS]
    if unknown:
        return "unknown_field", (
            f"a proposal holds exactly the fields {listed(FIELDS)}, and this one also holds "
            f"{listed(said(k) for k in unknown[:NAMES_SAID])}"
            + (f" and {len(unknown) - NAMES_SAID} more" if len(unknown) > NAMES_SAID else "")
            + ": a field the schema does not name is refused, whatever it holds")
    named = answer.get("operation")
    if isinstance(named, (list, tuple)) or named is None or named == "":
        count = len(named) if isinstance(named, (list, tuple)) else 0
        return "not_one_operation", (
            "a proposal names exactly one operation, and this one names "
            f"{count if count else 'none'}")
    if not isinstance(named, str):
        return "wrong_type", (
            "a proposal names its operation by the catalog's key, as text, and this one gave "
            f"{kind_of(named)}")
    if "params" not in answer:
        return "missing_field", (
            f"a proposal holds {listed(FIELDS)}, and this one holds no params")
    return "", ""


def _call_refusal(call_id) -> tuple:
    """``(code, words)`` when *call_id* names no call the record of AI calls holds."""
    from modules.ai import calls
    from modules.heal.catalog import kind_of, said

    if not isinstance(call_id, str) or not call_id:
        return "no_call", (
            "a proposal is the answer of a recorded AI call, and it came with "
            f"{'no call id' if not call_id else kind_of(call_id) + ' for its call id'}")
    found = calls.find(call_id)
    if found["state"] != "ok":
        return "no_call", (
            f"a proposal is the answer of a recorded AI call, and the record of AI calls "
            f"holds no call {said(call_id)}"
            + (f" (it could not be read: {found['error']})" if found.get("error") else ""))
    return "", ""


@acts_as_ai("fix-proposal")
def proposal(answer, *, network: str, call_id: str, actor: str, actor_verified: str,
             sources=None) -> dict:
    """What an AI call's *answer* proposes for *network*, held to the catalog (the module's
    docstring): ``{"ok": True, "operation", "params", "preview", "hash"}``, the operation's
    preview and the hash its confirm is bound to; or ``{"ok": False, "code", "refused",
    "recorded"}``, the refusal's words and whether its record was written.

    *call_id* is the recorded call that answered; *actor* who asked and *actor_verified* how
    they were verified, kept with a refusal's record. Neither approves anything: the approval
    is the confirm route's, a verified person's, with the hash. *sources* is the operation's
    plan's own seam (tests). Never raises on an answer's content; never runs, holds, opens or
    starts anything, and causes nothing on Mercury's host: the collector step's proposal names
    the operation and its device and never runs the close helper, not even its dry run, which
    runs only on the person's own card preview, the hash its confirm is bound to (the
    operator, 2026-11-14; `catalog._collector_plan`)."""
    from modules.heal import catalog

    code, words = _call_refusal(call_id)
    if not code:
        code, words = _shape(answer)
    if not code:
        got = catalog.preview(answer["operation"], answer["params"], network=network,
                              sources=sources)
        if got["ok"]:
            return got
        code, words = got["code"], got["refused"]
    words += ". Nothing was previewed, and nothing runs"
    return {"ok": False, "code": code, "refused": words,
            "recorded": _record(call_id, code, words, network, actor, actor_verified)}


def held(answer) -> str:
    """Why *answer* is not one proposal's shape held to the catalog's schema (`_shape`, then
    `catalog.checked`: one operation the catalog holds, exactly its parameters, each of its
    shape), or ``""``. Reads nothing and records nothing: an answer's own check asks it before
    its call is judged (`fixit_troubleshoot.check`); the proposal itself still comes through
    `for_incident`, which asks again."""
    from modules.heal import catalog

    code, words = _shape(answer)
    if code:
        return words
    try:
        catalog.checked(answer["operation"], answer["params"])
    except catalog.Refused as exc:
        return str(exc)
    return ""


@acts_as_ai("fix-proposal")
def for_incident(answer, incident, *, call_id: str, calls=(), actor: str,
                 actor_verified: str, note: str = "", shown: dict = None, prompt: str = "",
                 now: float = None, sources=None, planned=None, resolved: float = None) -> dict:
    """What an AI call's *answer* proposes in *incident* (a `fixit.incident.Incident`), held
    to this door and then to Mercury's own check (the module's docstring): ``{"ok": True,
    "operation", "params", "preview", "hash", "repeat", "passed", "proposal", "line"}`` (the
    operation's preview, the hash its confirm is bound to, the repeat flag, and the incident's
    proposal line kept), or ``{"ok": False, "code", "refused", "recorded", "line"}``. *calls*
    are every call of the investigation (its cost is the incident's), *call_id* the one whose
    answer this is; *actor* who pressed and *actor_verified* how, kept with the line beside
    their *note* and the answer as *shown*. Never runs, holds, opens or starts anything; for
    the collector step it reads the session it would close once, by the close helper's DRY
    RUN, which closes nothing (`plan_engine.read_sessions`, C3725), inside the job making the
    proposal, so the record keeps it and the page draws it without waiting."""
    from modules.fixit import incident as F
    from modules.fixit import validate

    ids = [c for c in calls or () if c] or ([call_id] if call_id else [])
    # A background investigation's (R1: its *actor* the job, *actor_verified* none) names no
    # person on its line: both or neither are kept.
    verified_person = bool(actor_verified) and actor_verified != "none"
    kept = {"by": actor if verified_person else "",
            "verified": actor_verified if verified_person else "", "note": note,
            "shown": shown or {}}
    code, words = _call_refusal(call_id)
    if not code:
        code, words = _shape(answer)
    if code:
        words += ". Nothing was previewed, and nothing runs"
        try:
            line = F.record_proposal(incident, "ai", calls=ids, prompt=prompt, now=now,
                                     words=f"Mercury's check refused the AI's fix: {words}",
                                     **kept)
        except (F.Refused, OSError, ValueError) as exc:
            log.error("fix_proposal: %s's refused answer was not kept: %s", incident.id, exc)
            line = {}
        return {"ok": False, "code": code, "refused": words, "line": line,
                "recorded": _record(call_id, code, words, incident.network, actor,
                                    actor_verified)}
    # A collector step's session, read now, inside the job making the proposal, and kept with
    # it, so the page draws it from the record and never waits (C3725).
    from modules import plan_engine as PE
    from modules.heal import resubscribe as R

    sessions = (PE.read_sessions(incident.network, [{
        "operation": R.COLLECTOR_KEY,
        "params": dict(answer.get("params") or {}, device=incident.device)}], now=now)
        if answer.get("operation") == R.COLLECTOR_KEY else None)
    got = validate.propose(incident, "ai", answer["operation"], answer["params"], calls=ids,
                           prompt=prompt, resolved=resolved, now=now, sources=sources,
                           planned=planned, sessions=sessions, **kept)
    if got["ok"]:
        return got
    return dict(got, recorded=_record(call_id, got["code"], got["refused"], incident.network,
                                      actor, actor_verified))


# ── A plan of steps (C3755, C3764; fixit_troubleshoot v7) ───────────────────────────────────

def capabilities() -> dict:
    """Every step a proposal may name, with the problem conditions it fixes
    (`catalog.capabilities`): what a missing capability's restart compares (C3733,
    `ai.missing.available`). A read of the code."""
    from modules.heal import catalog

    return catalog.capabilities()


def most_steps() -> int:
    """The most steps a plan holds: the plan engine's (`plan_engine.MOST_STEPS`)."""
    from modules import plan_engine as PE

    return PE.MOST_STEPS


def step_held(step) -> str:
    """Why *step* is not one of Mercury's plan steps held to its schema, or ``""``: one
    proposal's shape (`_shape`), then the plan engine's own check of an incident's plan's steps
    (`plan_engine._fix_steps_refusal`: a catalog operation or a built-in command plan held to
    the catalog's schema, or an intent change or a deploy held to its step kind's), then the
    AI's never-list (`plan_engine.ai_step_refusal`: a settings, users, credentials,
    notifications or template-approval step, whatever its kind). Reads nothing."""
    from modules import plan_engine as PE

    code, words = _shape(step)
    if code:
        return words
    why = PE._fix_steps_refusal([step])                    # noqa: SLF001 (the engine's own check)
    if why:
        return why
    return PE.ai_step_refusal(step["operation"])


def _attempt_form(step: dict) -> dict:
    """*step* as an incident's plan line keeps it (`fixit.incident.record_proposal`): a
    catalog operation's or command plan's parameters as an attempt's (`validate.as_attempt`),
    an intent change's or deploy's its own, the device (the incident's) left out."""
    from modules import plan_engine as PE
    from modules.fixit import validate
    from modules.heal import catalog

    if step["operation"] in PE.FIX_ADMITTED:
        return {"operation": step["operation"],
                "params": {k: v for k, v in step["params"].items() if k != "device"}}
    _op, held_ = catalog.checked(step["operation"], step["params"])
    return {"operation": step["operation"],
            "params": validate.as_attempt(step["operation"], held_)}


def _command_plan_reads(network: str, steps: list, incident: str = "") -> dict:
    """Each built-in command plan step's preconditions read NOW, through the read engine,
    inside the job making the proposal (`catalog.PlanStep.preflight` with *reads*), so the page
    draws them from the record and never waits: ``{"<n>": {"ok", "refused", "hash"}}``."""
    from modules.heal import catalog

    out = {}
    for n, s in enumerate(steps, 1):
        if not catalog.is_command_plan(s["operation"]):
            continue
        try:
            got = catalog.COMMAND_PLANS[s["operation"]].preflight(network, s["params"],
                                                                  reads=True,
                                                                  incident=incident)
        except Exception as exc:                          # noqa: BLE001 (kept, never raised)
            got = {"ok": False, "refused": f"its preconditions could not be read "
                                           f"({type(exc).__name__})", "hash": ""}
        out[str(n)] = {"ok": bool(got.get("ok")), "refused": str(got.get("refused") or ""),
                       "hash": str(got.get("hash") or "")}
    return out


def _propose_shapes(network: str, shapes, call_id: str) -> list:
    """Each shape a shorter command plan would need, proposed to Mercury's rule for raw lines
    (`command_policy.propose`: held PROVISIONAL until an admin approves it; the AI approves
    none): ``[{"dialect", "shape", "state", "words"}]``."""
    from modules.nsot import command_policy

    out = []
    for s in shapes or ():
        got = command_policy.propose(network, s.get("dialect") or "", s.get("shape") or "",
                                     by=f"the AI (call {call_id or 'not recorded'})",
                                     why=s.get("why") or "")
        out.append({"dialect": s.get("dialect") or "", "shape": s.get("shape") or "",
                    "state": got.get("state") or "", "words": got.get("words") or ""})
    return out


def plan_for_incident(steps, incident, *, improvement=None, call_id: str, calls=(),
                      actor: str, actor_verified: str, note: str = "", shown: dict = None,
                      prompt: str = "", now: float = None, alternative_of: str = "") -> dict:
    """What an AI call's plan proposes in *incident*: *steps* ``[{"operation", "params"}]`` in
    order, each held to this door (`step_held`), then kept as the incident's proposal line with
    its steps (`fixit.incident.record_proposal`), whose preflight on the page (`fixit.plan.
    preflight`) holds each step to the incident's scope, the heal guards, committed intent and
    the AI's never-list, a refused step drawn refused and the plan then not approvable. Inside
    this job: each collector step's session and each command plan step's preconditions read
    once (`plan_engine.read_sessions`, `_command_plan_reads`), kept with the line; each shape
    the *improvement* names proposed provisional (`_propose_shapes`); and the improvement's
    shorter route, when it names steps, kept as a second line beside the first
    (``alternative``), the person choosing. ``{"ok", "steps", "line", "alternative",
    "shapes", "refused", "code"}``. Never runs, holds, opens or starts anything."""
    from modules import plan_engine as PE
    from modules.fixit import incident as F

    ids = [c for c in calls or () if c] or ([call_id] if call_id else [])
    verified_person = bool(actor_verified) and actor_verified != "none"
    kept = {"by": actor if verified_person else "",
            "verified": actor_verified if verified_person else "", "note": note}
    code, words = _call_refusal(call_id)
    steps = list(steps or [])
    if not code and not 1 <= len(steps) <= most_steps():
        code, words = "steps", f"a plan is 1 to {most_steps()} steps, and {len(steps)} were given"
    for n, s in enumerate(steps, 1):
        if code:
            break
        why = step_held(s)
        if why:
            code, words = "step_refused", f"step {n} ({s.get('operation')}): {why}"
        elif (s.get("params") or {}).get("device") != incident.device:
            code, words = "another_device", (
                f"step {n} names the device {(s.get('params') or {}).get('device')}, and "
                f"{incident.id} is {incident.device}'s: a plan acts on its incident's device")
    if code:
        words += ". Nothing was previewed, and nothing runs"
        try:
            line = F.record_proposal(incident, "ai", calls=ids, prompt=prompt, now=now,
                                     words=f"Mercury's check refused the AI's plan: {words}",
                                     shown=shown or {}, **kept)
        except (F.Refused, OSError, ValueError) as exc:
            log.error("fix_proposal: %s's refused plan was not kept: %s", incident.id, exc)
            line = {}
        return {"ok": False, "code": code, "refused": words, "line": line, "steps": [],
                "alternative": {}, "shapes": [],
                "recorded": _record(call_id, code, words, incident.network, actor,
                                    actor_verified)}
    imp = improvement.model_dump(mode="json") if hasattr(improvement, "model_dump") else (
        dict(improvement) if isinstance(improvement, dict) else {})
    shapes = _propose_shapes(incident.network, imp.get("shapes") or [], call_id)
    sessions = PE.read_sessions(incident.network, steps, now=now) or None
    shown_ = dict(shown or {})
    from modules import troubleshoot_job
    # The card's live stepper (the operator, 2026-11-16): the plan's own reads of the switch.
    troubleshoot_job.say("Checking the plan against the switch…",
                         done="Checked the plan against the switch")
    reads = _command_plan_reads(incident.network, steps, incident.id)
    if reads:
        shown_["preconditions_read"] = reads
    if shapes:
        shown_["shapes"] = shapes
    if alternative_of:
        shown_["alternative_of"] = alternative_of
    line = F.record_proposal(incident, "ai", steps=[_attempt_form(s) for s in steps],
                             calls=ids, prompt=prompt, now=now, sessions=sessions,
                             shown=shown_, **kept)
    alt = {}
    if imp.get("steps") and not alternative_of:
        alt_steps = [{"operation": s["operation"],
                      "params": {k: v for k, v in (s.get("params") or {}).items()
                                 if v is not None}} for s in imp["steps"]]
        got = plan_for_incident(alt_steps, incident, call_id=call_id, calls=calls, actor=actor,
                                actor_verified=actor_verified, note=note,
                                shown={"why": imp.get("what") or "",
                                       "improvement": {"what": imp.get("what") or "",
                                                       "saves": imp.get("saves") or ""}},
                                prompt=prompt, now=now,
                                alternative_of=str(line.get("proposal") or ""))
        alt = got.get("line") or {}
    log.info("fixit: %s: an AI plan of %d step(s) kept as %s", incident.id, len(steps),
             line.get("proposal"))
    return {"ok": True, "code": "", "refused": "", "steps": steps, "line": line,
            "alternative": alt, "shapes": shapes, "proposal": line.get("proposal", "")}


def _record(call_id, code: str, words: str, network: str, actor: str,
            actor_verified: str) -> bool:
    """Keep a refusal on the call's use record, the reason whole and masked; whether it was
    written. An answer that named no recorded call is kept all the same, as a use of the id
    it gave (or of none), and said in the log: History draws a use with its call, so that row
    is read in the record and its export only."""
    from modules import redact
    from modules.ai import calls

    kept = calls.record_use(
        call_id if isinstance(call_id, str) else "", REFUSED_USE, actor=actor or "",
        detail=redact.redact_text(
            f"{words} ({code}; proposed for {network or 'no network'}; asked by "
            f"{actor or 'nobody'}, verified {actor_verified or 'none'})"))
    recorded = bool(kept.get("recorded"))
    log.log(logging.INFO if recorded and code != "no_call" else logging.ERROR,
            "fix_proposal: refused (%s) for %s, call %s, recorded %s", code, network,
            call_id if isinstance(call_id, str) else "", recorded)
    return recorded
