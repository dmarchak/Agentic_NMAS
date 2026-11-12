"""The one door from an AI answer to anything runnable (docs/HEAL_TO_INTENT.md section 12, the
operator's rule of 2026-11-11, "by its preview's hash" the operator's of 2026-11-12;
docs/MERCURY_CHARTER.md, "The fix-it path", step 3): "No fix runs from AI text. The AI may
propose one operation from Mercury's catalog, with its parameters; code validates it against
intent and the guards, and a person approves it by its preview's hash before it runs. The AI
never composes commands, never runs anything itself, and never retries on its own."

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
    starts anything."""
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
    their *note* and the answer as *shown*. Never runs, holds, opens or starts anything."""
    from modules.fixit import incident as F
    from modules.fixit import validate

    ids = [c for c in calls or () if c] or ([call_id] if call_id else [])
    kept = {"by": actor, "verified": actor_verified, "note": note, "shown": shown or {}}
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
    got = validate.propose(incident, "ai", answer["operation"], answer["params"], calls=ids,
                           prompt=prompt, resolved=resolved, now=now, sources=sources,
                           planned=planned, **kept)
    if got["ok"]:
        return got
    return dict(got, recorded=_record(call_id, got["code"], got["refused"], incident.network,
                                      actor, actor_verified))


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
