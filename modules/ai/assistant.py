"""The assistant's how-to answer, from the manual (card P7, stage 1; PHASE8_PLAN 16.10, its
build and its retrieval; board P7's 17 approved answers).

**What it is.** A person asks how to do something in Mercury, or what a screen means. Code
chooses the manual's passages (`manual_index.select`: BM25 with aliases and the screen's
boost, a floor, never padded); the model answers from those passages alone, in steps, citing
each passage it rests on. Its only jobs in stage 1 are how-to and explain-this-screen: it never
changes, deploys, approves or writes to any source of truth, and names no command to type.

**What leaves the host.** The question, a typed part (`gateway.TYPED_PARTS`): masked on its way
out, the person told what was removed. The passages chosen and the screen's name, Mercury's own
words (the manual is published with the product). Nothing of the network: no device, address
or configuration is sent in stage 1.

**The request** (`gateway.ask`): the instructions are the prompt, cached; the `context` is the
stable part every call shares, cached (the screens the manual names, `manual.SCREENS`); the
`parts` are the call's own (the question, the screen asked from, the passages), after.

**What Mercury checks before anything is drawn** (:func:`check`): every citation is a passage
it was sent; every screen it names is one the manual names; the answer is within its bounds.
An answer that says the passages do not cover the question, or that cites none, is drawn as
"the manual doesn't cover this". A refused answer is never drawn ("Couldn't answer: …", the
call kept in History).

**A manual gap** (no passage chosen, an answer that is not covered, or one the check refuses)
is what the ask route records (`record_gap`): a write of its own, never the read that ranks.

**One person's press, one recorded call** (PHASE8_PLAN 18.3: trigger person); never a
background feature.

**A plan (v2, 2026-11-14).** The answer may name one of the plan engine's plans with its
parameters (`plan_engine.PLANS`, told to the model in the cached `context`). Mercury holds it
to the plan's schema (`plan_of`) before it is drawn; the panel then offers Preview the plan…,
the engine's own preview, and a person approves it by its hash or not. The assistant runs
nothing.
"""
import json
import logging
import os
import re
import time

from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)

FEATURE = "assistant"
#: v2 (2026-11-14): the answer may name one of the plan engine's plans (`plan_engine.PLANS`).
PROMPT = ("assistant", 2)
#: The kind of subject a call is about (`history_sources.SUBJECT_WORDS`).
SUBJECT_KIND = "manual_question"
#: The longest answer drawn, characters; longer is refused at check.
MAX_ANSWER = 2400
#: The longest question asked, characters: a question, not a pasted file.
MAX_QUESTION = 600
#: The steps a press runs, each named on the manual's page (`modules/manual.py`).
STEPS = (
    ("choose", "the manual's passages chosen by code for the question (BM25 with the aliases "
               "and the screen's boost; none below the floor: a manual gap, no call)"),
    ("ask", "one recorded AI call: the instructions and the screens cached, then the question "
            "(masked on its way out) and the passages"),
    ("check", "Mercury's check: every citation a passage sent, every screen named one the "
              "manual names"),
    ("draw", "the answer drawn with its passages' links, or the manual's gap said and "
             "recorded"),
)
#: Said when the manual does not cover a question, whichever way that was found.
NOT_COVERED = "The manual doesn't cover this."


@register("assistant", 1)
class AssistantAnswer(StrictModel):
    """The model's answer: the steps, the passages they rest on (their links, as sent), whether
    the passages cover the question, and every screen the answer names."""
    answer: str
    cites: list[str]
    covered: bool
    screens: list[str]


class PlanParam(StrictModel):
    """One parameter of a plan the answer names: its name and its value, as the person gave it."""
    name: str
    value: str


class PlanAsk(StrictModel):
    """A plan the answer names (`plan_engine.PLANS`), with every parameter it takes."""
    plan: str
    params: list[PlanParam]


@register("assistant", 2)
class AssistantAnswerV2(StrictModel):
    """v2 (2026-11-14): v1's answer, and ``plan``: one of the plan engine's plans with its
    parameters, or null. Proposed only: Mercury previews it and a person approves it or not."""
    answer: str
    cites: list[str]
    covered: bool
    screens: list[str]
    plan: PlanAsk | None = None


def plans_offered(plan_engine) -> list:
    """What the model is told of each plan: its name, its words and each parameter's shape."""
    return [{"plan": p.key, "words": p.words,
             "params": [{"name": x.name, "takes": x.takes} for x in p.params]}
            for _k, p in sorted(plan_engine.PLANS.items())]


def plan_of(words) -> tuple:
    """``(plan, why)``: the plan *words* names, held to the plan engine's schema
    (`plan_engine.checked`: a plan Mercury has, exactly its parameters, each of its shape), as
    ``{"plan", "params", "title"}``; ``(None, "")`` for none; ``(None, why)`` refused. Reads
    nothing and runs nothing."""
    from modules import plan_engine

    ask = getattr(words, "plan", None)
    if ask is None:
        return None, ""
    given = {}
    for p in ask.params:
        if p.name in given:
            return None, f"its plan names the parameter {p.name!r} twice"
        given[p.name] = p.value
    try:
        plan, held, _steps = plan_engine.checked(ask.plan, given)
    except plan_engine.Refused as exc:
        return None, f"its plan is refused: {exc}"
    return {"plan": plan.key, "params": held, "title": plan.title(held)}, ""


def passages_sent(chosen: list) -> list:
    """What the model is sent of each chosen passage: its link, its page, its heading, its
    text."""
    return [{"link": p["link"], "page": p["page"], "heading": p["heading"], "text": p["text"]}
            for p in chosen]


def context() -> dict:
    """The stable prefix every call shares, cached: the screens the manual names."""
    from modules import manual
    from modules import plan_engine
    return {"screens": sorted(manual.SCREENS), "plans": plans_offered(plan_engine)}


def parts(question: str, screen: str, chosen: list) -> dict:
    """The call's own data, after the cached prefix."""
    return {"question": question, "screen": screen or "", "passages": passages_sent(chosen)}


def check(words, chosen: list) -> str:
    """Why *words* (an `AssistantAnswer`) is refused, or ``""``: a citation that is no passage
    sent, a screen the manual does not name, an answer past `MAX_ANSWER`."""
    from modules import manual

    sent = {p["link"] for p in chosen}
    stray = [c for c in words.cites if c not in sent]
    if stray:
        return f"it cites {', '.join(stray)}, which it was not sent"
    unknown = [s for s in words.screens if s not in manual.SCREENS]
    if unknown:
        return f"it names {', '.join(unknown)}, which is no screen the manual names"
    if len(words.answer) > MAX_ANSWER:
        return f"its answer is {len(words.answer)} characters, past {MAX_ANSWER}"
    return ""


def subject(screen: str) -> dict:
    return {"kind": SUBJECT_KIND, "id": screen or "", "devices": []}


def prepare(question: str, *, screen: str = "") -> dict:
    """`answer`'s steps before its call, the one code path a person's press and an evaluation's
    batched request share (scripts/nmas-assistant-cases): the question's checks, the passages
    chosen from it as it leaves (masked, the mask's placeholders out), and the request.
    ``{"done": <answer's result, no call>}`` when it is refused (empty, too long) or no passage
    is chosen (a manual gap); else ``{"chosen", "drawn", "request"}``, *request* what
    `gateway.ask` takes for it: ``{"feature", "prompt", "schema", "parts", "context",
    "subject"}``."""
    from modules.ai import manual_index

    question = (question or "").strip()
    if not question:
        return {"done": {"ok": False, "state": "refused", "error": "empty",
                         "detail": "Ask a question first.", "passages": [], "gap": False}}
    if len(question) > MAX_QUESTION:
        return {"done": {"ok": False, "state": "refused", "error": "too_long",
                         "detail": (f"The question is {len(question)} characters; ask it in at "
                                    f"most {MAX_QUESTION}."), "passages": [], "gap": False}}
    # Chosen from the question as it leaves (`redact.redact_egress`), its placeholders taken
    # out: neither a pasted secret's value nor the mask's own words rank the manual.
    from modules import redact
    ranked_by = re.sub(r"<redacted[^>]*>", " ", redact.redact_typed(question))
    chosen = manual_index.select(ranked_by, screen=screen)
    drawn = [{"link": p["link"], "page": p["page"], "heading": p["heading"]} for p in chosen]
    if not chosen:
        return {"done": {"ok": True, "state": "not_covered", "error": "", "detail": NOT_COVERED,
                         "passages": [], "gap": True}}
    return {"chosen": chosen, "drawn": drawn,
            "request": {"feature": FEATURE, "prompt": PROMPT, "schema": AssistantAnswerV2,
                        "parts": parts(question, screen, chosen), "context": context(),
                        "subject": subject(screen)}}


def answer(question: str, *, screen: str = "", actor: str, trigger: dict, send=None,
           today: str = None) -> dict:
    """A person's question answered from the manual, or why not: ``{"ok", "state", "error",
    "detail", "answer"?, "cites"?, "passages", "call_id"?, "gap"}``. *state* ``answered``,
    ``not_covered`` (no passage chosen, or the passages do not cover it: no answer drawn),
    ``refused`` (a gate, or Mercury's check) or ``failed``; *gap* True when the manual's gap
    is the route's to record; *passages* each chosen one's link, page and heading. Its steps:
    `prepare`, one call through the gateway, `judge`."""
    from modules.ai import gateway

    prep = prepare(question, screen=screen)
    if "done" in prep:
        return prep["done"]
    req = prep["request"]
    got = gateway.ask(req["feature"], req["prompt"], req["schema"], req["parts"],
                      actor=actor, trigger=trigger, context=req["context"],
                      subject=req["subject"], send=send, today=today)
    return judge(got, prep, actor=actor)


def judge(got: dict, prep: dict, *, actor: str) -> dict:
    """`answer`'s steps after its call, the one code path a call and an evaluation's batched
    answer share: *got* is `gateway.ask`'s result (or a batch's for one request, the same
    shape), *prep* `prepare`'s. Mercury's check (`check`), then covered or not, the use
    recorded on the call; the result is `answer`'s."""
    from modules.ai import calls

    chosen, drawn = prep["chosen"], prep["drawn"]
    if not got.get("ok"):
        return {"ok": False, "state": "refused", "error": got.get("error") or "failed",
                "detail": got.get("detail") or "", "call_id": got.get("call_id") or "",
                "passages": drawn, "gap": False}
    words = got["output"]
    why = check(words, chosen)
    if why:
        calls.record_use(got["call_id"], "refused by validation", actor=actor, detail=why)
        return {"ok": False, "state": "refused", "error": "couldnt_answer",
                "detail": f"Couldn't answer: {why}. The call is in History.",
                "call_id": got["call_id"], "passages": drawn, "gap": True,
                "typed_masked": got.get("typed_masked") or ""}
    if not words.covered or not words.cites:
        calls.record_use(got["call_id"], "shown: not covered", actor=actor)
        return {"ok": True, "state": "not_covered", "error": "", "detail": NOT_COVERED,
                "call_id": got["call_id"], "passages": drawn, "gap": True,
                "typed_masked": got.get("typed_masked") or ""}
    calls.record_use(got["call_id"], "shown: answered", actor=actor)
    cited = [d for d in drawn if d["link"] in set(words.cites)]
    # A plan named (v2): proposed only, held to the plan engine's schema by `check`; the panel
    # offers its preview, and a person approves it or not.
    plan, dropped = plan_of(words)
    return {"ok": True, "state": "answered", "error": "", "detail": "", "plan": plan,
            "plan_dropped": (f"Mercury dropped the plan the answer named: {dropped}" if dropped
                             else ""),
            "answer": words.answer, "cites": cited, "passages": drawn,
            "call_id": got["call_id"], "cost_usd": got.get("cost_usd") or 0.0, "gap": False,
            "typed_masked": got.get("typed_masked") or ""}


# ── the manual's gaps (board P7's answer 11: counted and listed, never Needs attention) ────────

GAPS_FILE = "manual_gaps.jsonl"


def _gaps_path() -> str:
    from modules.config import DATA_DIR
    return os.path.join(DATA_DIR, GAPS_FILE)


def record_gap(question: str, *, screen: str, state: str, actor: str, best: float = None,
               call_id: str = "", now: float = None) -> dict:
    """Record a question the manual did not answer (*state*: no passage chosen, not covered,
    or refused by the check), the question masked as it leaves (`redact.redact_typed`), so the
    record holds no secret a person pasted or wrote. The ask route's write; the read that ranks writes
    nothing."""
    from modules import redact
    from modules.config import open_secure
    from modules.filestore import PathLock

    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if now is None
                                                                  else now)),
           "question": redact.redact_typed(" ".join((question or "").split()))[:MAX_QUESTION],
           "screen": screen or "", "state": state, "actor": actor, "call_id": call_id or "",
           **({"best": round(float(best), 3)} if best is not None else {})}
    path = _gaps_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with PathLock(path):
        with open_secure(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def gaps(limit: int = 50) -> dict:
    """``{"state", "error", "count", "rows"}``: the manual's gaps recorded, the newest *limit*
    first (counted whole). An unreadable record is said, never read as none."""
    path = _gaps_path()
    if not os.path.exists(path):
        return {"state": "ok", "error": "", "count": 0, "rows": []}
    try:
        with open(path, encoding="utf-8") as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "error": type(exc).__name__, "count": 0, "rows": []}
    return {"state": "ok", "error": "", "count": len(rows), "rows": rows[::-1][:limit]}
