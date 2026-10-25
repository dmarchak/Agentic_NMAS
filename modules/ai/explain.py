"""Explain an alert (PHASE8_PLAN 15.9, card P1's one AI step): its evidence pack in, one recorded
call through the gateway, and hypotheses out, each citing the pack and naming the read that
would confirm it. Nothing runs: the person reads the hypotheses beside the pack, and runs a read
through Show commands if they choose.

The model only reasons over the pack. Everything else is Mercury's, deterministic:

- **The pack as stored** (`evidence_pack.find`), its hash checked first (`intact`): a pack that
  changed since it was built is refused, never explained. Every string in it was masked when it
  was built, and the gateway masks the request again. It rides as data in the user turn; the
  pack's format and the read-only verbs are the cached prefix.
- **Shape B** (13.4): a short rationale, then `{hypotheses: [{claim, evidence_refs,
  confirm_with}], needs_human}`, in a strict schema.
- **The check** (`check`): every reference must resolve to the pack (`evidence_pack.resolve`)
  and every `confirm_with` must be a read on the read-only allowlist (`readonly_commands`); one
  that does not is "couldn't analyse", naming it, and nothing is shown (the card's kill
  criterion: one claim shown with a reference that does not resolve). No tool is offered.
"""
import json
import logging
from enum import Enum

from modules.ai import gateway
from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)

FEATURE = "explain"
PROMPT = ("explain", 1)
#: At most this many hypotheses (the card's "top hypothesis" and two behind it).
MAX_HYPOTHESES = 3
STEPS = (
    ("pack", "the alert's stored evidence pack, its hash checked: a pack changed since it was "
             "built is refused"),
    ("ask", "one recorded, capped call through the AI gateway, as the person who pressed "
            "Explain: the pack as data, no tool offered"),
    ("check", "every reference resolves to the pack and every confirming read is on the "
              "read-only allowlist; one that does not is couldn't analyse, and nothing is "
              "shown"),
    ("show", "the hypotheses drawn beside the pack, each reference linked to its piece; "
             "nothing runs"),
)


class Outcome(str, Enum):
    answer = "answer"
    refuse = "refuse"


class Hypothesis(StrictModel):
    claim: str
    evidence_refs: list[str]
    confirm_with: str


@register("explain", 1)
class Explanation(StrictModel):
    """Shape B: the rationale first, then the hypotheses, or why the pack cannot say."""
    outcome: Outcome
    rationale: str
    hypotheses: list[Hypothesis]
    needs_human: bool
    why_not: str


def vocabulary() -> str:
    """The pack's format and the reads a hypothesis may name, the same bytes on every call."""
    from modules import evidence_pack as EP
    from modules import readonly_commands as R

    return "\n".join([
        "An evidence pack has sections, each with a reference (its name), a state, its source "
        "and when it was read, and pieces, each with its own reference (section:n).",
        "Sections: " + "; ".join(f"{k} = {EP.SECTION_WORDS[k]}" for k in EP.SECTIONS),
        "States: " + ", ".join(EP.STATES) + " (only ok and empty were read; absent, "
        "not_configured and unreadable are not evidence)",
        "A confirming read is one command a person may run on the device, read-only: it begins "
        "with one of " + ", ".join(R.READ_ONLY_VERBS) + "; a pipe may follow with "
        + ", ".join(R.SAFE_MODIFIERS),
        f"At most {MAX_HYPOTHESES} hypotheses, the most likely first.",
    ])


def parts(pack: dict) -> dict:
    """The call's own data: the pack's sections as stored, and the alert's own words."""
    return {"alert": f"{pack.get('rule', '')} on {pack.get('device') or 'no one device'}",
            "pack": json.dumps(pack.get("sections") or [], sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"))}


def check(answer: "Explanation", pack: dict) -> str:
    """"" when every hypothesis cites the pack and names an allowed read, else why not (the
    first one that does not, named)."""
    from modules import evidence_pack as EP
    from modules import readonly_commands as R

    if answer.outcome is Outcome.refuse:
        return ""
    if not answer.hypotheses and not answer.needs_human:
        return "the answer holds no hypothesis and does not ask for a person"
    if len(answer.hypotheses) > MAX_HYPOTHESES:
        return f"{len(answer.hypotheses)} hypotheses; at most {MAX_HYPOTHESES} are taken"
    for i, h in enumerate(answer.hypotheses, 1):
        if not h.evidence_refs:
            return f"hypothesis {i} cites nothing in the pack"
        for ref in h.evidence_refs:
            if EP.resolve(pack, ref) is None:
                return f"hypothesis {i} cites {ref[:40]!r}, which is not in the pack"
        refused = R.refusal(h.confirm_with)
        if refused:
            return f"hypothesis {i}'s confirming read is not a read Mercury allows: {refused}"
    return ""


def explain(pack_id: str, *, actor: str, send=None, today: str = None) -> dict:
    """``{"ok", "error", "detail", "answer", "pack_id", "call_id", "cost_usd"}``: the pack's
    hypotheses, checked; or a refusal naming why, with nothing shown."""
    from modules import evidence_pack as EP

    pack, state, error = EP.find(pack_id)
    if pack is None:
        return {"ok": False, "error": "no_pack", "pack_id": pack_id,
                "detail": (f"the evidence packs cannot be read ({error})"
                           if state == "unreadable" else f"no evidence pack {pack_id} is kept")}
    if not EP.intact(pack):
        return {"ok": False, "error": "changed", "pack_id": pack_id,
                "detail": "the pack's hash does not match: it changed since it was built, so "
                          "it is not explained"}
    got = gateway.ask(FEATURE, PROMPT, Explanation, parts(pack), actor=actor,
                      context={"pack_format": vocabulary()}, send=send, today=today)
    if not got["ok"]:
        return dict(got, pack_id=pack_id)
    answer, base = got["output"], {"pack_id": pack_id, "call_id": got["call_id"],
                                   "cost_usd": got["cost_usd"]}
    why = check(answer, pack)
    if why:
        return dict(base, ok=False, error="couldnt_analyse",
                    detail=f"couldn't analyse: {why}; nothing is shown")
    if answer.outcome is Outcome.refuse:
        return dict(base, ok=False, error="unanswerable",
                    detail=f"the pack cannot say: {answer.why_not[:200]}")
    # What is drawn (an answer's outcome is "answer" and its why_not empty by now); the whole
    # answer is in the call's record.
    return dict(base, ok=True, error="", answer=answer.model_dump(
        mode="json", include={"rationale", "hypotheses", "needs_human"}))
