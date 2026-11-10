"""A heal's change record: deterministic, no AI call (board H, part H6; docs/HEAL_TO_INTENT.md
section 8, "The change record"; board CR's format).

**Every section is Mercury's:** Summary, Scope, Risk, Implementation, Verification, Rollback
plan, Window and approver, and Status, in board CR's order. The facts are the deploy preview's
change record's own fact functions (`modules.ai.change_record.facts` and its `risk`, which make
no call): the device, the program (masked) and its hash, the stated reasons, Verify's scope,
the rollback the pipeline would run (`deploy.rollback_commands` over the program and the heal's
own read, then masked), and the risk's level by its stated rule. Mercury writes the Summary
from the step log's words; the Window and approver name the policy, who confirmed it, their
reason and its fingerprint, and AUTO's expiry when the policy read names it. The model is never
asked: this is a record of what Mercury did, never a draft of what it might.

**Kept in the step log** (the ``act`` row's ``records.change_record``: its markdown, masked),
so it is downloadable from the incident as .md: History's heal row, opened, draws **Download
the change record (.md)** when the record was made (`history_sources.heal`'s ``heal_record``),
and `routes/heal_proposal_v2.py`'s `change_record_md` serves it, masked, at
``/v2/network/<network>/heal/incident/<incident>/change-record.md`` (C2773); the same for an
action's record (`build_action`, H23). H8's analysis of a can't-fix never needs it. Made for every heal whose program was computed
at apply; a heal refused before that has no program, and says so.
"""

import logging

log = logging.getLogger(__name__)

SECTIONS = ("Summary", "Scope", "Risk", "Implementation", "Verification", "Rollback plan",
            "Window and approver", "Status")


def facts(network: str, host: str, *, platform: str, program_hash: str, commands: list,
          read: str, effects: dict, authorise: list, removals: int,
          golden_before: str = "") -> dict:
    """Mercury's facts for one heal (`modules.ai.change_record.facts`, which makes no call):
    *commands* the program and *read* the heal's own read, from which the rollback is
    computed and then masked."""
    from modules.ai import change_record as CR
    from modules.redact import redact_text

    return CR.facts(host=host, network=network, platform=platform, program_hash=program_hash,
                    lines=[redact_text(c) for c in commands], commands=list(commands),
                    captured=read or "", effects=effects or {}, derived=[], checks=[],
                    authorised=list(authorise or []), removals=int(removals or 0),
                    golden=golden_before)


def _step(steps: list, name: str) -> dict:
    found = [s for s in steps if s.get("step") == name]
    return found[-1] if found else {}


def markdown(network: str, decision: dict, result: dict, f: dict, *, policy: dict,
             golden_commit: str = "", until: str = "", at: str = "",
             approval: dict = None) -> str:
    """The record as text, every section Mercury's (the module's docstring). *approval* (H5,
    `modules/heal/propose.py`): a Tier 2 proposal a verified person approved, ``{"by",
    "verified", "reason", "hash", "at", "reset"}``; its Window and approver name the person,
    and a process reset sent is in its Implementation and its Rollback plan."""
    from modules.heal import act
    from modules.heal.kinds import KIND_WORDS

    host = f["host"]
    steps = result.get("steps") or []
    outcome = result.get("outcome") or ""
    kind = decision.get("kind") or ""
    units = [u.get("words") for u in decision.get("units") or [] if u.get("words")]
    person = (decision.get("person") or {}).get("words") or ""
    approval = approval or {}
    reset = approval.get("reset") or {}
    title = (f"returned to intent on {approval.get('by')}'s approval" if approval else
             "healed to intent by Mercury's self-healing")
    out = [f"# Change record: {host}, {title}", "",
           f"Mercury's record of decision {decision.get('id')}, incident "
           f"{decision.get('incident')}: deterministic, written by Mercury's code, no AI call. "
           f"Program {f['program_hash'][:12]}: the program is the change.", "",
           "## Summary", "",
           (f"Self-healing on {network} found {host} departed from its approved state "
            f"({KIND_WORDS.get(kind, kind) or 'no kind recorded'}"
            + (f": {'; '.join(units)}" if units else "") + ") and "
            + ("returned it to intent" if outcome in ("healed", "symptom_remains", "partial")
               else "did not change it" if outcome == "refused" else "undid its own change"
               if outcome == "rolled_back" else "could not say what landed")
            + f": {act.OUTCOME_WORDS.get(outcome, outcome)}."
            + (f" The change it healed was made outside Mercury ({person})." if person
               else "")), "",
           "## Scope", "",
           f"1 device: {host} ({f['platform']}), network {network}. "
           + (f"Interfaces {', '.join(f['interfaces'])}. " if f["interfaces"] else "")
           + (f"The approved state: golden {f['golden']}." if f["golden"] else ""), "",
           "## Risk", "", f"Level: {f['risk']['level']}. {f['risk']['rule']}", "",
           "## Implementation", "",
           f"Program {f['program_hash'][:12]}, {len(f['lines'])} line(s), recomputed from "
           f"Mercury's own read of {host} at apply and compared by its hash with the decision's, "
           f"sent merge-only as "
           + (f"{approval.get('by')}, who approved it," if approval else "the policy,")
           + f" holding {host}:", "", "```"] + list(f["lines"]) + ["```", ""]
    for r in f["reasons"]:
        out.append(f"The stated reason for `{r['line']}`: \"{r['reason']}\".")
    if reset:
        out.append(f"Then, still holding {host} and before its save to startup, the measured "
                   f"process reset `{reset.get('command')}`: {reset.get('words') or 'not sent'}"
                   ".")
    out += ["", "## Verification", "",
            f"{f['verify_scope']['scope'].upper()}: {f['verify_scope']['why']}."]
    for name, label in (("intent", "Each healed unit at intent"),
                        ("symptom", "The symptom read again"),
                        ("saved", "Saved to startup"),
                        ("golden", "The golden read again")):
        s = _step(steps, name)
        if s:
            out.append(f"- {label}: {s.get('result')}: {s.get('words')}")
    out += ["", "## Rollback plan", "",
            "On a failed Verify, or a healed unit not at intent after the change, Mercury "
            "undoes what landed, per device, re-adding a removed line from its own read, and "
            "says what it achieved:", "", "```"] + list(f["rollback"]) + ["```", ""]
    if f.get("rollback_error"):
        out.append(f"The rollback could not be computed: {f['rollback_error']}.")
    if reset:
        from modules.nsot.privileged import RESET_ROLLBACK

        out.append(f"The process reset is not in that rollback: {RESET_ROLLBACK}.")
    if f["golden"]:
        out.append(f"A manual back-out: restore {host}'s golden {f['golden']} from its History "
                   "tab.")
    window = (f"The standing policy {policy.get('fingerprint') or '(no fingerprint)'} for "
              f"{network}, confirmed by {policy.get('by') or 'nobody recorded'} ("
              f"{policy.get('reason') or 'no reason recorded'})"
              + (f", AUTO until {until}" if until else "")
              + ": a verified person previewed and confirmed it by its fingerprint, and this "
                "heal's program was decided under it.")
    if approval:
        window = (f"Approved by {approval.get('by')} (verified: {approval.get('verified')}) at "
                  f"{approval.get('at')}, confirming proposal {approval.get('hash')}, with the "
                  f"stated reason \"{approval.get('reason')}\": a Tier 2 fix waits for a person, "
                  "who decides its moment. The proposal was made under the policy "
                  f"{policy.get('fingerprint') or '(no fingerprint)'} confirmed by "
                  f"{policy.get('by') or 'nobody recorded'}.")
    out += ["", "## Window and approver", "", window, "",
            "## Status", "",
            (f"{act.OUTCOME_WORDS.get(outcome, outcome)}"
             + (f" at {at}" if at else "") + f": {result.get('words') or ''}"
             + (f" Golden {golden_commit[:10]} committed." if golden_commit else ""))]
    return "\n".join(out).rstrip() + "\n"


# ── An action's change record (H23; docs/HEAL_TO_INTENT.md 19.4, "Record") ──────────────────

#: Each action family's risk, by its stated rule (board CR's Risk section): the level and why.
ACTION_RISK = {
    "bounce": ("medium", "a port shut and brought straight back up in one write, inside the "
                         "device's own revert timer: the link's traffic stops for seconds; no "
                         "configuration line changes and nothing is saved"),
    "clear": ("low", "one named BGP neighbour cleared: a hard clear only of a session not "
                     "Established in two reads (it carried no routes to lose), a soft clear a "
                     "route refresh that resets nothing; no configuration line changes"),
    "dampening": ("medium", "a change to intent, one line (`dampening` under the port, the "
                            "platform's defaults), deployed as the person who approved it: it "
                            "holds the port down while it keeps flapping"),
}
#: The steps each family's Verification section names, in its act's order.
ACTION_VERIFY_STEPS = {"bounce": ("confirm", "verify", "stable", "repair"),
                       "clear": ("send", "verify"),
                       "dampening": ("apply", "verify")}
#: Each family's title, as the record's first line names what was done.
ACTION_TITLE = {"bounce": "a port bounced by Mercury's self-healing (an action)",
                "clear": "a BGP neighbour cleared by Mercury's self-healing (an action)",
                "dampening": "dampening proposed by self-healing, approved and deployed"}


def _family_words(family: str) -> dict:
    from modules.heal import bounce, dampening, session_clear

    return {"bounce": bounce.OUTCOME_WORDS, "clear": session_clear.OUTCOME_WORDS,
            "dampening": dampening.OUTCOME_WORDS}[family]


def _window_words(window: dict) -> str:
    if not window:
        return "no planned window was recorded: the act ended before it declared one"
    if window.get("error"):
        return f"no planned window: it could not be recorded ({window['error']}), so nothing " \
               "was sent"
    far = [f"{f.get('device')} {f.get('interface') or ''}".strip()
           for f in window.get("far_ends") or [] if isinstance(f, dict) and f.get("device")]
    return (f"planned window {window.get('from')} to {window.get('until')}, declared by "
            f"{window.get('via') or 'self-healing'} before anything was sent, naming "
            f"{', '.join(window.get('interfaces') or []) or 'no interface'}"
            + (f"; its far end: {', '.join(far)}" if far else "; no far end named"))


def _action_rollback(family: str, decision: dict, result: dict) -> list:
    """The Rollback plan's lines: what undoes the action, then what the act did of it."""
    rec = result.get("records") or {}
    a = decision.get("action") or {}
    if family == "bounce":
        timer = (decision.get("bounce") or {}).get("timer") or "its"
        out = [f"The device's own revert timer ({timer} minute(s), `configure terminal revert "
               "timer`): `configure confirm` is sent only once Mercury is back in and the "
               "post-check passes, so a session Mercury loses reverts the device by itself. When "
               "the end is not as before, Mercury sends `no shutdown` (and `configure confirm` "
               "only while a revert is pending) and reads it back."]
        rep = rec.get("repair") or {}
        if rep:
            out.append(("Repaired: " if rep.get("restored") else "NOT RESTORED: ")
                       + "; ".join(f"{s.get('step')}: {s.get('achieved')}"
                                   for s in rep.get("steps") or []))
        elif result.get("outcome") == "reverted":
            out.append("No confirm was sent, and the device's revert timer reverted it.")
        return out
    if family == "clear":
        return [f"A clear is not put back: {rec.get('rollback') or 'does not apply'}."]
    from modules.heal import dampening

    undo = dampening.rollback_program(a.get("interface") or "",
                                      (decision.get("dampening") or {}).get("dialect") or "")
    head = (f"Mode B's `{dampening.SHAPE}` removal, the pipeline's own rollback on a failed "
            "verify, then the intent edit put back as the person (one forward commit)")
    body = ([head + ":", "", "```"] + list(undo.get("commands") or []) + ["```"]
            if undo.get("commands") else [f"{head}: not available ({undo.get('refused')})."])
    return body + ["", f"Intent put back: {rec.get('put_back') or 'not needed'}."]


def action_markdown(network: str, decision: dict, result: dict, *, approval: dict = None,
                    at: str = "") -> str:
    """An action's record as text, every section Mercury's (board CR's order, `SECTIONS`): what
    was acted on and why, the program (masked) and its hash, the verify it read, its rollback
    and what the act did of it, its planned window with its far end, who approved it (the
    policy, or the person), and its status. Deterministic: no AI call."""
    from modules.heal import steplog
    from modules.heal.actions import KIND_WORDS
    from modules.redact import redact_text

    kind = decision.get("kind") or (decision.get("action") or {}).get("kind") or ""
    family = steplog.ACTION_FAMILY[kind]
    host = decision.get("device") or ""
    a = decision.get("action") or {}
    rec = result.get("records") or {}
    steps = result.get("steps") or []
    outcome = result.get("outcome") or ""
    words = _family_words(family)
    what = steplog.subject({"device": host, "action": a, "kind": kind})
    prog = [redact_text(x) for x in decision.get("program") or []]
    level, rule = ACTION_RISK[family]
    pol = decision.get("policy") or {}
    approval = approval or {}
    sent = bool(result.get("sent"))
    out = [f"# Change record: {what}, {ACTION_TITLE[family]}", "",
           f"Mercury's record of decision {decision.get('id')}, incident "
           f"{decision.get('incident') or '(none)'}: deterministic, written by Mercury's code, "
           f"no AI call. Program {(decision.get('program_hash') or '')[:12]}: the program is the "
           "action.", "",
           "## Summary", "",
           (f"Self-healing on {network} chose {KIND_WORDS.get(kind, kind)} on {what}"
            + (f", from {'; '.join(t for t in decision.get('triggers') or [] if t)}"
               if decision.get("triggers") else "")
            + f". It ended: {words.get(outcome, outcome)}. "
            + ("An action, not a heal to intent: no configuration line changes, and no golden "
               "is committed." if family != "dampening" else
               "A change to intent, a person's: the intent edit is committed and deployed under "
               "one hash.")), "",
           "## Scope", "",
           (f"1 device: {host}, network {network}; {what}. "
            + "; ".join(f"Its far end: {f['device']} {f.get('interface') or ''}".strip()
                        for f in steplog.far_ends({"device": host, "records": rec,
                                                   "action": a}))).rstrip(), "",
           "## Risk", "", f"Level: {level}. {rule}.", "",
           "## Implementation", "",
           (f"Program {(decision.get('program_hash') or '')[:12]}, {len(prog)} line(s), "
            + ("sent as " + (f"{approval.get('by')}, who approved it," if approval else
                             "the policy,") + f" holding {host}:" if sent else
               f"NOT sent: {result.get('words') or 'the act refused it'}. The program it "
               "held:")), "", "```"] + prog + ["```", ""]
    if rec.get("privileged"):
        out.append(f"The privileged command's record: {rec['privileged']} (History, privileged "
                   "commands, with the session as it was before).")
    if rec.get("intent"):
        out.append(f"The intent commit: {rec['intent']}.")
    out += ["", "## Verification", ""]
    shown = [s for s in steps if s.get("step") in ACTION_VERIFY_STEPS[family]]
    out += ([f"- {s.get('step')}: {s.get('result')}: {redact_text(str(s.get('words') or ''))}"
             for s in shown] or ["Nothing was verified: nothing was sent."])
    if rec.get("verify"):
        out.append(f"- the verify read: {rec['verify']}")
    out += ["", "## Rollback plan", ""] + _action_rollback(family, decision, result)
    window = (f"Approved by {approval.get('by')} (verified: {approval.get('verified')}) at "
              f"{approval.get('at')}, confirming proposal {approval.get('hash')}, with the stated "
              f"reason \"{approval.get('reason')}\"." if approval else
              f"The standing policy {pol.get('fingerprint') or '(no fingerprint)'} for {network}, "
              f"confirmed by {pol.get('by') or 'nobody recorded'} "
              f"({pol.get('reason') or 'no reason recorded'}): this action was allowed AUTO "
              "under it.")
    planned = ("No planned window: a deploy of one intent line takes no link down on purpose, "
               "so it declares none" if family == "dampening" else
               _window_words(rec.get("window") or {}))
    out += ["", "## Window and approver", "", f"{planned}.", "",
            window, "",
            "## Status", "",
            f"{words.get(outcome, outcome)}" + (f" at {at}" if at else "")
            + f": {result.get('words') or ''}"]
    return redact_text("\n".join(out).rstrip() + "\n")


def build_action(network: str, decision: dict, result: dict, *, approval: dict = None,
                 at: str = "") -> dict:
    """``{"state": "made"|"none"|"failed", "words", "markdown", "risk"}``: an action's record
    (`action_markdown`), or why there is none (no program: the decision held none). Never
    raised: a record that could not be made is said."""
    from modules.heal import steplog

    kind = decision.get("kind") or (decision.get("action") or {}).get("kind") or ""
    if not decision.get("program") or kind not in steplog.ACTION_FAMILY:
        return {"state": "none", "markdown": "", "risk": "",
                "words": "no change record: the action held no program, so there is no change "
                         "to record"}
    try:
        text = action_markdown(network, decision, result, approval=approval, at=at)
    except Exception as exc:
        log.error("heal: %s's change record for %s's action could not be made: %s", network,
                  decision.get("device"), exc)
        return {"state": "failed", "markdown": "", "risk": "",
                "words": f"the change record could not be made: {type(exc).__name__}: {exc}"}
    level = ACTION_RISK[steplog.ACTION_FAMILY[kind]][0]
    return {"state": "made", "markdown": text, "risk": level,
            "words": (f"made: {len(text.splitlines())} line(s), risk {level}, deterministic "
                      "(no AI call)")}


def build(network: str, decision: dict, result: dict, *, host: str, platform: str,
          prog: dict, read: str, entry: dict, authorise: list, policy: dict,
          golden_before: str = "", golden_commit: str = "", until: str = "",
          at: str = "", approval: dict = None) -> dict:
    """``{"state": "made"|"none"|"failed", "words", "markdown", "risk"}``: the record of one
    heal, or why there is none. Never raised: a record that could not be made is said.
    *approval*: a person's approval of a Tier 2 proposal (`markdown`'s)."""
    from modules.redact import redact_text

    if not prog or not prog.get("commands"):
        return {"state": "none", "markdown": "", "risk": "",
                "words": "no change record: the heal was refused before its program was "
                         "computed, so there is no change to record"}
    try:
        f = facts(network, host, platform=platform, program_hash=prog["hash"],
                  commands=prog["commands"], read=read,
                  effects=(entry or {}).get("expected_effects") or {}, authorise=authorise,
                  removals=len(prog.get("ids") or []), golden_before=golden_before)
        text = redact_text(markdown(network, decision, result, f, policy=policy,
                                    golden_commit=golden_commit, until=until, at=at,
                                    approval=approval))
    except Exception as exc:
        log.error("heal: %s's change record for %s could not be made: %s", network, host, exc)
        return {"state": "failed", "markdown": "", "risk": "",
                "words": f"the change record could not be made: {type(exc).__name__}: {exc}"}
    return {"state": "made", "markdown": text, "risk": f["risk"]["level"],
            "words": (f"made: {len(text.splitlines())} line(s), risk {f['risk']['level']}, "
                      "deterministic (no AI call)")}
