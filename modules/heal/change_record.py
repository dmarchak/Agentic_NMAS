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
so it is downloadable from the incident as .md (H9's History step log draws the link) and
H8's analysis of a can't-fix never needs it. Made for every heal whose program was computed
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
             golden_commit: str = "", until: str = "", at: str = "") -> str:
    """The record as text, every section Mercury's (the module's docstring)."""
    from modules.heal import act
    from modules.heal.kinds import KIND_WORDS

    host = f["host"]
    steps = result.get("steps") or []
    outcome = result.get("outcome") or ""
    kind = decision.get("kind") or ""
    units = [u.get("words") for u in decision.get("units") or [] if u.get("words")]
    person = (decision.get("person") or {}).get("words") or ""
    out = [f"# Change record: {host}, healed to intent by Mercury's self-healing", "",
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
           f"sent merge-only as the policy, holding {host}:", "", "```"] + list(f["lines"]) \
        + ["```", ""]
    for r in f["reasons"]:
        out.append(f"The stated reason for `{r['line']}`: \"{r['reason']}\".")
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
    if f["golden"]:
        out.append(f"A manual back-out: restore {host}'s golden {f['golden']} from its History "
                   "tab.")
    out += ["", "## Window and approver", "",
            (f"The standing policy {policy.get('fingerprint') or '(no fingerprint)'} for "
             f"{network}, confirmed by {policy.get('by') or 'nobody recorded'} ("
             f"{policy.get('reason') or 'no reason recorded'})"
             + (f", AUTO until {until}" if until else "")
             + ": a verified person previewed and confirmed it by its fingerprint, and this "
               "heal's program was decided under it."), "",
            "## Status", "",
            (f"{act.OUTCOME_WORDS.get(outcome, outcome)}"
             + (f" at {at}" if at else "") + f": {result.get('words') or ''}"
             + (f" Golden {golden_commit[:10]} committed." if golden_commit else ""))]
    return "\n".join(out).rstrip() + "\n"


def build(network: str, decision: dict, result: dict, *, host: str, platform: str,
          prog: dict, read: str, entry: dict, authorise: list, policy: dict,
          golden_before: str = "", golden_commit: str = "", until: str = "",
          at: str = "") -> dict:
    """``{"state": "made"|"none"|"failed", "words", "markdown", "risk"}``: the record of one
    heal, or why there is none. Never raised: a record that could not be made is said."""
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
                                    golden_commit=golden_commit, until=until, at=at))
    except Exception as exc:
        log.error("heal: %s's change record for %s could not be made: %s", network, host, exc)
        return {"state": "failed", "markdown": "", "risk": "",
                "words": f"the change record could not be made: {type(exc).__name__}: {exc}"}
    return {"state": "made", "markdown": text, "risk": f["risk"]["level"],
            "words": (f"made: {len(text.splitlines())} line(s), risk {f['risk']['level']}, "
                      "deterministic (no AI call)")}
