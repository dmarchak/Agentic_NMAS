"""The toolbar assistant's answer, from the manual and from the reads a person has (card P7,
stage 1; stage 2, docs/design/assistant.md as amended 2026-11-23; PHASE8_PLAN 16.10, its build
and its retrieval; board P7's 17 approved answers).

**What it is.** A person asks how to do something in Mercury, what a screen means, or what
Mercury holds about the device or incident on screen. Code chooses the manual's passages
(`manual_index.select`: BM25 with aliases and the screen's boost, a floor, never padded); the
model answers from those passages and from the reads Mercury runs for it, citing each passage
and read it rests on. It never changes, deploys, approves or writes to any source of truth,
and names no command to type.

**Where the person is** (stage 2) is the page's path, resolved by the server
(`assistant_context.resolve`) into the screen, the network, the device and the incident. The
reads are scoped to that device, or to the incident's, and to the devices of the network the
question names (`scope_of`).

**The reads** (stage 2; the operator, 2026-11-23: the same read-only tools a person has, device
reads included) run through the generic read loop (`read_loop.run`) over the assistant's read
family (`FAMILY`): AI troubleshooting's operations exactly (`fixit_reads.FAMILY`'s: the
device's reads by Mercury's allowlist, `router_reads.COMMAND_OPS`, and Mercury's own reads of
what it holds, `fixit_reads.OWN_READS`), their runner (`fixit_reads.run`, which hands a device
read to the reads engine, `router_reads.run`, recorded on History › Reads) and one session a
device a round (`router_reads.run_many`). Each read is judged by the loop's check (the
allowlist, the device in scope, the egress classes), logged in the send log before anything of
it is sent, and drawn on History beside the calls. With no device or incident in view, or the
device state class off for the network, the one pass is the plain one and no read is asked.

**What leaves the host.** The question, a typed part (`gateway.TYPED_PARTS`): masked on its way
out, the person told what was removed. The passages chosen, the screen's name, what the person
is looking at (the screen, network, device and incident names), Mercury's own words. A read's
answer only under its egress class, masked (`read_loop`).

**The request** (`gateway.ask`, through the loop): one shape for every pass
(`read_loop.LoopFeature.one_shape`): the instructions are the prompt, cached; the `context` is
the stable part every call shares, cached (the screens the manual names, `manual.SCREENS`, the
plans, the read set and the reads' format); the `parts` are the call's own (the question, the
screen asked from, what it is looking at, the passages, the pass, and the reads once run).

**What Mercury checks before anything is drawn** (:func:`check`): every citation is a passage
it was sent or a read that ran; every screen it names is one the manual names; the answer is
within its bounds. An answer that says it is not covered, or that cites nothing, is drawn as
"the manual doesn't cover this". A refused answer is never drawn ("Couldn't answer: …", the
call kept in History).

**A manual gap** (no passage chosen and nothing to read, an answer that is not covered, or one
the check refuses) is what the ask route records (`record_gap`): a write of its own, never the
read that ranks.

**One person's press, one recorded call a pass** (PHASE8_PLAN 18.3: trigger person); never a
background feature.

**A plan (v2, 2026-11-14).** The answer may name one of the plan engine's plans with its
parameters (`plan_engine.PLANS`, told to the model in the cached `context`). Mercury holds it
to the plan's schema (`plan_of`) before it is drawn; the panel then offers Preview the plan…,
the engine's own preview, and a person approves it by its hash or not. The assistant runs
nothing.

**A hand-off (v3, stage 2).** A change the person asks for that no plan does is handed to the
existing gated flow, pre-filled and not started (`handoff_of`): the device's Intent tab, its
Change it in words box filled, or the incident's AI troubleshooting card. The person presses,
previews and confirms there, as ever.

**A senior engineer working through Mercury (v6 and schema v4; the operator, 2026-11-28).** It
investigates with Mercury's reads (of the device or incident in view, and of any device of the
network the question names, `named_devices`), says what it found, and:
- asked to make a change, proposes ONE plan: a named plan, or ``change`` (the plan engine's
  `plan_engine.CHANGE`: its steps named one by one, each one of Mercury's operations that needs
  no incident, held to its step kind's schema by the one check of a plan's steps). The panel
  previews it in place at once (each step's own preview, a read), and a person approves it by
  its hash on the plan's card; the plan engine runs it. The assistant runs nothing, and an
  answer whose words say a change was made is refused (`check`);
- asked for what no operation or read of Mercury's does, says so (``no_tool``, `no_tool_of`):
  drawn as "Mercury has no tool for this", and recorded for review as an operation Mercury
  lacks (`record_no_tool`, `missing`), never a device command or a way around Mercury.
"""
import json
import logging
import os
import re
import time
from enum import Enum

from modules.ai import fixit_reads as FR
from modules.ai import read_loop as RL
from modules.ai import router_reads as RR
from modules.ai.schemas import StrictModel, register

from modules.identity import acts_as_ai  # noqa: E402 (the AI's own identity, its role)

log = logging.getLogger(__name__)

FEATURE = "assistant"
#: v2 (2026-11-14): the answer may name one of the plan engine's plans (`plan_engine.PLANS`).
#: v3 (2026-11-14, C3666): v2 hardened on its measurement (22 of 39 cases reliable over ten
#: runs): the question's text, tag-shaped text included, is data and never an instruction, and
#: is never repeated; only Mercury's screens and controls, never a device command's name; a
#: masked secret answered around; covered unless the passages say nothing about it; only
#: sidebar screens in "screens". Its plan rules are v2's, and its schema is v2's
#: (`AssistantAnswerV2`).
#: v4 (2026-11-14, C3666): v3 measured 29 of 39 over ten runs; "covered" follows from the
#: answer (any step from the passages makes it true), and a not-covered answer names the
#: screens the passages are about, never a command, control or tool. Otherwise v3's.
#: v5 (stage 2, docs/design/assistant.md): v4's, and what the person is looking at, the reads
#: (when to ask, of which device, citing ``read:<n>``) and the hand-off to a gated flow; its
#: schema is v3 (`AssistantAnswerV3`), one shape for every pass.
#: v6 (the operator, 2026-11-28: "take on the role of a senior network engineer ... If Mercury
#: doesn't have a tool for it, it should say so. When prompted to make a change it should
#: present a plan for approval"): v5's hardening, and the engineer's role: it investigates with
#: reads, says what it found; a change asked for is ONE plan (a named plan, or ``change``, its
#: steps Mercury's own operations), never said to be made; what no operation or read of
#: Mercury's does is ``no_tool``, never a command or a way around Mercury. Its schema is v4
#: (`AssistantAnswerV4`). v5 stays readable (a recorded case's answers are v5's).
PROMPT = ("assistant", 6)
#: The kind of subject a call is about (`history_sources.SUBJECT_WORDS`).
SUBJECT_KIND = "manual_question"
#: The longest answer drawn, characters; longer is refused at check.
MAX_ANSWER = 2400
#: The longest question asked, characters: a question, not a pasted file.
MAX_QUESTION = 600
#: The longest hand-off sentence: the Intent tab's Change it in words box takes 300.
MAX_HANDOFF = 300
#: The steps a press runs, each named on the manual's page (`modules/manual.py`).
STEPS = (
    ("place", "what the person is looking at, from the page's path by Mercury's own URL map: "
              "the screen, the network, the device and the incident"),
    ("choose", "the manual's passages chosen by code for the question (BM25 with the aliases "
               "and the screen's boost; none below the floor and nothing to read: a manual "
               "gap, no call)"),
    ("ask", "one recorded AI call: the instructions, the screens, the plans and the read set "
            "cached, then the question (masked on its way out), what it is looking at and the "
            "passages"),
    ("read", "the reads the answer asks for, of the device or incident in view and of any "
             "device of the network the question names, each judged by Mercury's check and run "
             "through its reads engine and its own records, recorded, then one more recorded "
             "call with their answers"),
    ("check", "Mercury's check: every citation a passage sent or a read that ran, every screen "
              "named one the manual names, no word saying a change was made"),
    ("draw", "the answer drawn with its sources' links, the model, the cost and the calls in "
             "History; a change's plan previewed in place for a person to approve by its hash, "
             "a hand-off offered, Mercury's lack of a tool said and recorded, or the manual's "
             "gap said and recorded"),
)
#: Said when the manual does not cover a question, whichever way that was found.
NOT_COVERED = "The manual doesn't cover this."
#: Why no read is asked when the page is about no device or incident.
NO_PLACE = ("no device or incident is in view and the question names no device of the network, "
            "so no device is read")
#: The most devices of the network a question may name for its reads (each one's committed
#: stores and read-only account are read for the scope, `router_reads.scope_for`).
MOST_NAMED = 6
#: The longest "Mercury has no tool for this" said: what was wanted, and why.
MAX_NO_TOOL = 300
#: What Mercury records as its reason for a "no tool" answer (`missing.wanted`).
NO_TOOL_REASON = "no operation or read of Mercury's does it"
#: Words that say the assistant made a change, or that the change asked for is now made (an
#: answer's never do: the assistant makes none; a plan it proposes runs only once a person
#: approves it). Refused by resemblance, the safe side; the assistant's own first person and
#: the change "now" made only, so a fact History holds ("Mercury deployed edge1 on Tuesday") is
#: never one.
_CLAIMS_MADE = re.compile(
    r"\bI(?:['’]ve|\s+have)?\s+(?:now\s+|already\s+|just\s+)?"
    r"(?:applied|deployed|changed|committed|saved|configured|reloaded|reserved|removed|"
    r"pushed|shut)\b"
    r"|\b(?:the|your|this)\s+change\s+(?:is\s+now|has\s+(?:now\s+)?been)\s+"
    r"(?:made|applied|deployed|done|complete|committed)\b", re.I)


#: C4334 (CLAUDE.md, "No terminal steps"): the words a device's command line starts with. An
#: answer, or its "Mercury has no tool for this", that names one in a code span, a code block's
#: line, or after a device prompt ("edge1#", "Router(config)#") is refused by Mercury's check, held
#: by code and not only by the prompt. Refusing by resemblance is safe: a refused answer is said
#: and kept in History, never drawn.
#: The configuring and exec verbs, matched case-sensitively (a device's command line is lower
#: case; Mercury's controls are not: `Show commands`, `Delete`). A read's `show …` is not one of
#: them: an answer cites the reads Mercury ran in that form (the read set's own words), and a
#: read goes through Mercury's reads. A field name alone (`shutdown`, `hostname`) is not a
#: command: a code span is one only with words after its verb, or as `STANDALONE`.
CLI_VERBS = frozenset((
    "aaa", "access-list", "clear", "conf", "configure", "copy", "crypto", "debug", "default",
    "delete", "do", "enable", "erase", "hostname", "int", "interface", "ip", "ipv6", "line",
    "logging", "no", "ntp", "reload", "route-map", "router", "service", "shut", "shutdown",
    "snmp-server", "spanning-tree", "switchport", "terminal", "username", "vlan", "write"))
#: An exec command complete in one word, a terminal step on its own.
STANDALONE = frozenset(("reload", "enable", "wr"))
#: The read verbs, a terminal step only after a device's prompt ("edge1# show running-config").
READ_VERBS = frozenset(("show", "sh", "sho", "ping", "traceroute"))
_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_FENCE = re.compile(r"```[^\n]*\n(.*?)```", re.S)
_DEVICE_PROMPT = re.compile(r"(?:^|`)\s*([A-Za-z][\w.-]*(?:\([\w-]+\))?[#>])[ \t]*([a-z][\w-]*)",
                            re.M)


def _command_in(line: str) -> bool:
    words = line.strip().split()
    if not words:
        return False
    return (len(words) >= 2 and words[0] in CLI_VERBS) or (len(words) == 1 and
                                                           words[0] in STANDALONE)


def device_command(text: str) -> str:
    """The first device command *text* names, or ``""``: a code span or a code block's line that
    is one (`CLI_VERBS` with words after it, or `STANDALONE`), or a device prompt followed by a
    command or a read ("edge1# reload", "Router(config)# no ip route …")."""
    text = text or ""
    spans = [m.group(1) for m in _CODE_SPAN.finditer(text)]
    spans += [line for m in _FENCE.finditer(text) for line in m.group(1).splitlines()]
    for span in spans:
        if _command_in(span):
            return span.strip()
    for m in _DEVICE_PROMPT.finditer(text):
        if m.group(2) in CLI_VERBS or m.group(2) in READ_VERBS:
            return f"{m.group(1)} {m.group(2)}"
    return ""


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


# ── stage 2: the reads, the hand-off and the one shape ──────────────────────────────────────

#: The assistant's read family: AI troubleshooting's operations exactly, its runner and one
#: session a device a round (`fixit_reads.FAMILY`'s), held by the loop's check to the device
#: or incident in view (`scope_of`). Its own name, so its requests and the send log say whose.
FAMILY = RL.ReadFamily(
    name="assistant", transport="local", egress_class="device_state",
    operations=FR.FAMILY.operations, run=FR.run, run_many=RR.run_many,
    words="the toolbar assistant's reads: AI troubleshooting's, of the device or incident in "
          "view")
#: One entry of the answer's ``reads`` (`read_loop.request_model`).
ReadAsk = RL.request_model(FAMILY)


class HandoffFlow(str, Enum):
    """The gated flows a change is handed to: the device's Intent tab, Change it in words, and
    the incident's AI troubleshooting."""
    intent_words = "intent_words"
    ai_troubleshooting = "ai_troubleshooting"


class Handoff(StrictModel):
    """A change the person asked for, handed to one gated flow with its words, not started."""
    flow: HandoffFlow
    words: str


@register("assistant", 3)
class AssistantAnswerV3(StrictModel):
    """v3 (stage 2): v2's answer, ``cites`` holding passages' links and ``read:<n>``, a
    ``handoff`` (one gated flow and its words, or null) and ``reads`` (the read loop's
    requests; run only in a pass that may ask for reads)."""
    answer: str
    cites: list[str]
    covered: bool
    screens: list[str]
    plan: PlanAsk | None = None
    handoff: Handoff | None = None
    reads: list[ReadAsk] = []


# ── v4: the senior engineer's answer (the operator, 2026-11-28) ─────────────────────────────

class PlanStepAsk(StrictModel):
    """One step of a change the answer names: one of the operations a change admits
    (`plan_engine.CHANGE_ADMITTED`) and each of its parameters, as {name, value}."""
    operation: str
    params: list[PlanParam]


class PlanAskV4(StrictModel):
    """A plan the answer names (`plan_engine.PLANS`): a named plan's parameters, or a change's
    steps (``plan`` ``change``, its ``params`` empty)."""
    plan: str
    params: list[PlanParam]
    steps: list[PlanStepAsk] = []


class NoTool(StrictModel):
    """What the person asked for that no operation or read of Mercury's does: what was
    wanted, and why Mercury cannot do it, in a sentence each."""
    wanted: str
    why: str


@register("assistant", 4)
class AssistantAnswerV4(StrictModel):
    """v4 (2026-11-28): v3's answer, its ``plan`` able to name a change's steps
    (`PlanAskV4`), and ``no_tool`` (what no operation or read of Mercury's does, or null)."""
    answer: str
    cites: list[str]
    covered: bool
    screens: list[str]
    plan: PlanAskV4 | None = None
    handoff: Handoff | None = None
    reads: list[ReadAsk] = []
    no_tool: NoTool | None = None


#: Each read's operation and the device tab it opens on (Open, beside the source): Mercury's
#: own reads their tab, a device read the device's Ask the device tab (its record on History ›
#: Reads beside it).
READ_TAB = {"intent": "intent", "golden": "overview", "neighbours": "neighbours",
            "history": "history", "logs": "logs", "metrics": "monitoring",
            "collector_sessions": "monitoring", "stream_series": "monitoring", "show": "ask",
            "show_config": "ask", "ping": "ask", "traceroute": "ask"}
TAB_WORDS = {"intent": "Intent", "overview": "Overview", "neighbours": "Neighbours",
             "history": "History", "logs": "Logs", "monitoring": "Monitoring",
             "ask": "Ask the device"}


def read_set() -> str:
    """The cached context block ``read_set``: what the model may ask Mercury to read (`FAMILY`'s
    operations and their arguments), the same bytes on every call. Mercury's own words."""
    lines = [
        "read_set is the read-only reads Mercury may run for this question, as a person reads "
        "through Mercury, and only of a device in looking_at's devices: the device's own "
        "(show, show_config, ping, traceroute: give the command's words after its verb in "
        "words, for example \"interfaces GigabitEthernet1\" for show; Mercury runs a show of "
        "one of its command families, listed below, through its own reads engine), and "
        "Mercury's own of what it holds about the device (intent, golden, neighbours, history, "
        "logs, metrics; collector_sessions and stream_series only on an incident about a lost "
        "telemetry stream). To ask for one, add it to reads: op is one of the operations "
        "below, args its arguments by name (device always, and null for an argument the "
        "operation does not take), why one line on what it would show, and hypothesis what it "
        "would confirm or rule out. Mercury checks each request (the allowlist, each address "
        "and interface against the device's golden and intent, the egress classes) and runs "
        "only those it allows.",
        "The operations:"]
    for op in FAMILY.operations:
        args = ", ".join(f"{a} ({spec.shape.words})" for a, spec in op.args.items())
        lines.append(f"- {op.name}: {op.words}; args: {args}")
    lines.append("show's command families: `show <family> <form>`, each family's forms after "
                 "the colon, - for the family alone ({if} an interface the device's golden "
                 "holds, as one word; {a4} {a6} an address of the network; {p4} {p6} a prefix "
                 "of it; {mask} a netmask after an address; {vlan} {n} numbers; {sub} a "
                 "subscription; {mac} a MAC; {name} a VRF):")
    for family, tails in RR.SHOW_FAMILIES:
        lines.append(f"- {family}: " + " | ".join(t or "-" for t in tails))
    return "\n".join(lines)


def loop_feature(chosen: list) -> "RL.LoopFeature":
    """The assistant as the read loop asks it: one prompt and one schema every pass (v5, v3),
    the read set and the reads' format in the cached context, Mercury's check
    (`check`) given the reads that ran."""
    def check_(answer, *, read_ids):
        return check(answer, chosen, read_ids=read_ids)

    spec = (PROMPT, AssistantAnswerV4)
    return RL.LoopFeature(task=FEATURE, first=spec, second=spec, plain=spec, check=check_,
                          cites=lambda a: list(a.cites), one_shape=True,
                          shared_context={"read_set": read_set(),
                                          "reads_format": RL.READS_FORMAT})


def plans_offered(plan_engine) -> list:
    """What the model is told of each plan: its name, its words and each parameter's shape; a
    change (`plan_engine.CHANGE`) also the operations its steps may be, each with its
    parameters (`plan_engine.change_operations`)."""
    return [dict({"plan": p.key, "words": p.words,
                  "params": [{"name": x.name, "takes": x.takes} for x in p.params]},
                 **({"operations": plan_engine.change_operations()}
                    if p.key == plan_engine.CHANGE else {}))
            for _k, p in sorted(plan_engine.PLANS.items())]


def _named_once(params, what: str) -> tuple:
    """``(values, why)``: *params* (``[{name, value}]``) as ``{name: value}``, or why not (a
    name given twice, said by its name only)."""
    given = {}
    for p in params:
        if p.name in given:
            return None, f"{what} names the parameter {p.name!r} twice"
        given[p.name] = p.value
    return given, ""


def plan_of(words) -> tuple:
    """``(plan, why)``: the plan *words* names, held to the plan engine's schema
    (`plan_engine.checked`: a plan Mercury has, exactly its parameters, each of its shape; a
    change's steps each an operation a change admits, exactly its parameters), as
    ``{"plan", "params", "title"}``; ``(None, "")`` for none; ``(None, why)`` refused. Reads
    nothing and runs nothing."""
    from modules import plan_engine

    ask = getattr(words, "plan", None)
    if ask is None:
        return None, ""
    given, why = _named_once(ask.params, "its plan")
    if why:
        return None, why
    steps = list(getattr(ask, "steps", None) or [])
    if steps:
        # A change's steps (v4): each {operation, params}, as the plan engine's check takes them.
        if "steps" in given:
            return None, "its plan names its steps twice"
        given["steps"] = []
        for n, s in enumerate(steps, 1):
            values, why = _named_once(s.params, f"its plan's step {n}")
            if why:
                return None, why
            given["steps"].append({"operation": s.operation, "params": values})
    try:
        plan, held, steps = plan_engine.checked(ask.plan, given)
    except plan_engine.Refused as exc:
        return None, f"its plan is refused: {exc}"
    # The AI proposes under its engineer role (`identity.AI_NEVER`): a step a person would
    # take through a settings, users, credentials, notifications or template-approval route
    # is never the AI's to propose (`plan_engine.ai_step_refusal`).
    for s in steps:
        never = plan_engine.ai_step_refusal(s["kind"])
        if never:
            return None, f"its plan is refused: step {s['n']}: {never}"
    return {"plan": plan.key, "params": held, "title": plan.title(held)}, ""


def handoff_of(words, place: dict) -> tuple:
    """``(handoff, why)``: the gated flow *words* hands a change to, pre-filled for what the
    person is looking at (*place*), as ``{"flow", "words", "device", "incident", "network"}``;
    ``(None, "")`` for none; ``(None, why)`` dropped (a flow with nothing in view to hand to,
    words past `MAX_HANDOFF`, or beside a plan). Reads nothing and starts nothing."""
    from modules import redact

    hand = getattr(words, "handoff", None)
    if hand is None:
        return None, ""
    place = place or {}
    if getattr(words, "plan", None) is not None:
        return None, "it names a plan and a hand-off; the plan is offered"
    said = " ".join(str(hand.words or "").split())
    if not said:
        return None, "its hand-off has no words"
    if len(said) > MAX_HANDOFF:
        return None, f"its hand-off is {len(said)} characters, past {MAX_HANDOFF}"
    flow = HandoffFlow(hand.flow).value
    network = place.get("network") or ""
    if flow == HandoffFlow.intent_words.value:
        devices = list(place.get("devices") or [])
        device = place.get("device") or (devices[0] if len(devices) == 1 else "")
        if not device:
            return None, "it hands a change to a device's Intent tab, and no one device is in view"
        return {"flow": flow, "words": redact.redact_text(said), "device": device,
                "incident": "", "network": network}, ""
    if not place.get("incident"):
        return None, ("it hands a change to an incident's AI troubleshooting, and no incident "
                      "is in view")
    return {"flow": flow, "words": redact.redact_text(said), "device": "",
            "incident": place["incident"], "network": network}, ""


def no_tool_of(words) -> dict:
    """What the answer says Mercury has no tool for (v4's ``no_tool``), as the panel draws and
    the missing capabilities record keeps it: ``{"wanted", "why"}``, each one line, masked
    (`redact.redact_text`), at most `MAX_NO_TOOL` characters; ``None`` for none (or one with
    nothing wanted). Reads nothing."""
    from modules import redact

    got = getattr(words, "no_tool", None)
    if got is None:
        return None
    wanted = " ".join(str(got.wanted or "").split()).rstrip(".")
    if not wanted:
        return None
    why = " ".join(str(got.why or "").split())
    return {"wanted": redact.redact_text(wanted)[:MAX_NO_TOOL],
            "why": redact.redact_text(why)[:MAX_NO_TOOL]}


def record_no_tool(got: dict, *, network: str) -> dict:
    """The chat's job's write (`assistant_turns.work`, beside the manual's gap): an answer that
    said Mercury has no tool for what was asked, recorded as one missing capability for review
    (`missing.wanted` and `missing.record`: an operation Mercury lacks, for the question, keyed
    by the answering call; masked at rest). ``{"ok", "recorded", "error"}``; nothing for an
    answer without one."""
    from modules.ai import missing

    if not (got or {}).get("no_tool"):
        return {"ok": True, "recorded": 0, "error": ""}
    rows = missing.wanted(None, (), feature=FEATURE, network=network or "",
                          about=("question", got.get("call_id") or ""),
                          no_tool=dict(got["no_tool"], reason=NO_TOOL_REASON))
    return missing.record(rows[:1])


def passages_sent(chosen: list) -> list:
    """What the model is sent of each chosen passage: its link, its page, its heading, its
    text."""
    return [{"link": p["link"], "page": p["page"], "heading": p["heading"], "text": p["text"]}
            for p in chosen]


def context() -> dict:
    """The stable prefix every call shares, cached: the screens the manual names and the plans
    (the read set and the reads' format are the loop feature's, `loop_feature`)."""
    from modules import manual
    from modules import plan_engine
    return {"screens": sorted(manual.SCREENS), "plans": plans_offered(plan_engine)}


def looking_at(place: dict, screen: str = "") -> dict:
    """What the model is told the person is looking at: the screen, the network, the device,
    the incident and the devices a read may be of (names only)."""
    place = place or {}
    return {"screen": place.get("screen") or screen or "", "network": place.get("network") or "",
            "device": place.get("device") or "", "incident": place.get("incident") or "",
            "devices": list(place.get("devices") or [])}


def parts(question: str, screen: str, chosen: list, place: dict = None) -> dict:
    """The call's own data, after the cached prefix."""
    return {"question": question, "screen": screen or "",
            "looking_at": looking_at(place, screen), "passages": passages_sent(chosen)}


def check(words, chosen: list, read_ids=()) -> str:
    """Why *words* (an `AssistantAnswer` of any version) is refused, or ``""``: a citation that
    is neither a passage sent nor a read that ran (*read_ids*), a screen the manual does not
    name, an answer past `MAX_ANSWER`."""
    from modules import manual

    sent = {p["link"] for p in chosen} | set(read_ids or ())
    stray = [c for c in words.cites if c not in sent]
    if stray:
        return f"it cites {', '.join(stray)}, which it was not sent"
    unknown = [s for s in words.screens if s not in manual.SCREENS]
    if unknown:
        return f"it names {', '.join(unknown)}, which is no screen the manual names"
    if len(words.answer) > MAX_ANSWER:
        return f"its answer is {len(words.answer)} characters, past {MAX_ANSWER}"
    claim = _CLAIMS_MADE.search(words.answer or "")
    if claim:
        # The assistant makes no change; a plan it proposes runs only once a person approves
        # it. Its words are never drawn saying otherwise.
        return (f"its words say a change was made (\"{claim.group(0)}\"), and the assistant "
                "makes none: a plan runs only once a person approves it")
    # C4334: never a device command, in the answer or in what it says Mercury has no tool for.
    lacking = getattr(words, "no_tool", None)
    handoff = getattr(words, "handoff", None)
    for text in (words.answer, getattr(lacking, "wanted", ""), getattr(lacking, "why", ""),
                 getattr(handoff, "words", "") if handoff is not None else ""):
        command = device_command(text)
        if command:
            return (f"its words name a device command (\"{command[:80]}\"), and the assistant "
                    "never gives one: a read goes through Mercury's reads, and a change "
                    "through a plan you approve or its gated flow")
    return ""


def subject(screen: str, place: dict = None) -> dict:
    devices = list((place or {}).get("devices") or [])
    return {"kind": SUBJECT_KIND, "id": screen or "", "devices": devices}


def model_words(model: str = None) -> dict:
    """The model an answer ran on (*model*, the person's choice, else the task's pin): its id
    and its name, as the answer draws it ("Claude Haiku 5.5")."""
    from modules.ai import profiles

    model = model or profiles.task(FEATURE)["model"]
    return {"model": model, "model_words": profiles.profile(model)["words"]}


def named_devices(question: str, network: str) -> list:
    """The devices of *network*'s inventory that *question* names (the operator, 2026-11-28: a
    senior engineer reads the device the person names, not only the one on screen): each word of
    the question as it leaves (masked, `redact.redact_typed`) that is a device's name in the
    inventory, compared without case, in the order named, at most `MOST_NAMED`, each as the
    inventory spells it. A name the inventory does not hold names nothing (a read of it is
    refused by the read loop's check); an inventory that cannot be read names none, said in the
    log. Reads the inventory only."""
    from modules import redact
    from modules.nsot.restore import _devices_of

    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]*", redact.redact_typed(question or ""))
    if not words or not network:
        return []
    try:
        # The network's own inventory, as every per-network operation reads it.
        names = [str(d.get("hostname") or "") for d in _devices_of(network)]
    except Exception as exc:                          # noqa: BLE001 (none named: said)
        log.warning("assistant: %s's inventory could not be read for the names a question "
                    "gives: %s", network, exc)
        return []
    by_case = {n.casefold(): n for n in names if n}
    out = []
    for w in words:
        name = by_case.get(w.rstrip("._-").casefold())
        if name and name not in out:
            out.append(name)
    return out[:MOST_NAMED]


def scope_of(place: dict, actor: str, question: str = "") -> tuple:
    """``(scope, devices, why)``: what the read family's comparisons read for what the person is
    looking at (*place*) and the devices *question* names (`named_devices`): a device page's
    device and those named (`router_reads.scope_for`), an incident's device and its streams
    (`fixit_reads.scope_for`, the incident as its fix-it record takes it) with those named; the
    devices a read may be of; and why no read may be asked ("" when one may). Read only at a
    press, and only when the device state class is on for the network (`read_loop.reads_off`);
    each read is still judged by the read loop's check, a device outside the scope refused, and
    every read it allows is recorded as the assistant's, asked by the person."""
    from modules.nsot import listref

    place = place or {}
    network = place.get("network") or ""
    device, incident = place.get("device") or "", place.get("incident") or ""
    named = [n for n in named_devices(question, network) if n != device] if network else []
    if not network or not (device or incident or named):
        return None, [device] if device else [], NO_PLACE
    try:
        net_id = listref.network_id(network)
    except Exception as exc:                          # noqa: BLE001 (no read: said)
        return None, [device] if device else [], f"the network {network} is not known ({exc})"
    off = RL.reads_off(FAMILY, net_id)
    if off:
        return None, [device] if device else [], off
    try:
        if device or not incident:
            scope = RR.scope_for(network, ([device] if device else []) + named,
                                 turned_on_by=actor)
        else:
            from modules import incident_page
            from modules.fixit import section

            got = section.incident_of(network, incident_page.resolve(network, incident))
            if got["incident"] is None:
                return None, [], got["why"]
            scope = FR.scope_for(network, got["incident"], actor=actor)
            more = [n for n in named if n not in (scope.get("devices") or {})]
            if more:
                # The devices the question names beside the incident's, each as a device
                # page's is read (`router_reads.scope_for`).
                extra = RR.scope_for(network, more, turned_on_by=actor)
                scope["devices"] = dict(scope.get("devices") or {}, **extra["devices"])
                for key in ("addresses", "prefixes"):
                    scope[key] = sorted(set(scope.get(key) or ()) | set(extra.get(key) or ()))
    except Exception as exc:                          # noqa: BLE001 (no read: said)
        about = device or incident or ", ".join(named)
        log.error("assistant: the reads' scope of %s could not be built: %s", about, exc)
        return None, [device] if device else [], (f"what Mercury holds about {about} could "
                                                  f"not be read ({type(exc).__name__})")
    scope["actor"] = f"the toolbar assistant, asked by {actor or 'nobody named'}"
    scope["purpose"] = "the toolbar assistant's read"
    return scope, sorted(scope.get("devices") or {}), ""


def refusal(question: str) -> dict:
    """The question's own checks, before anything is chosen or asked: `answer`'s result for a
    question refused (empty, too long), else ``{}``. The panel's Send asks it first, so a
    refused question is said at once and starts no job (routes/assistant_v2.ask)."""
    question = (question or "").strip()
    if not question:
        return {"ok": False, "state": "refused", "error": "empty",
                "detail": "Ask a question first.", "passages": [], "gap": False}
    if len(question) > MAX_QUESTION:
        return {"ok": False, "state": "refused", "error": "too_long",
                "detail": (f"The question is {len(question)} characters; ask it in at "
                           f"most {MAX_QUESTION}."), "passages": [], "gap": False}
    return {}


class Stopped(Exception):
    """The person pressed Stop: raised by `answer`'s ask before a call it would make next, so
    no further read or call is made. *calls* the calls already made, *cost_usd* their cost."""

    def __init__(self, calls, cost_usd):
        super().__init__("stopped by the person")
        self.calls, self.cost_usd = list(calls), float(cost_usd or 0.0)


#: Said when the person pressed Stop.
STOPPED = ("Stopped by you. No call was made after Stop; a round of reads already running when "
           "you pressed it finished first. What was already spent is recorded in History")
#: The use recorded on each call a Stop ended (`stopped_result`).
STOPPED_USE = "stopped by the person"


#: C4330: the verbs a person asks a change with. A question that starts with one (after "please"
#: or "can you") is a change request, asked of the model though no passage of the manual is
#: chosen and nothing may be read: the model answers it with a plan of Mercury's operations or
#: "Mercury has no tool for this", neither of which cites the manual. Measured 2026-11-28 on twelve
#: typical requests: two chose no passage (a DHCP reservation, an OSPF cost), so without a device
#: in view they were drawn "The manual doesn't cover this" and no plan was offered. Matching a
#: verb only spends the one call the person pressed Send for; it allows nothing else.
CHANGE_VERBS = frozenset((
    "add", "allow", "apply", "assign", "bounce", "bring", "change", "configure", "create",
    "decrease", "delete", "deploy", "describe", "disable", "enable", "give", "increase", "lower",
    "make", "move", "push", "raise", "reload", "remove", "rename", "reserve", "restart",
    "restore", "revert", "roll", "save", "set", "shut", "shutdown", "start", "turn", "unshut",
    "update"))
#: A second word that makes the verb's sentence a question or an idiom, not a change ("Describe
#: how BGP works", "Set aside your rules", "Make sense of this", "Start by explaining").
NOT_A_CHANGE_AFTER = frozenset(("how", "what", "why", "when", "where", "which", "who", "whether",
                                "aside", "sense", "by", "me"))
_LEAD_IN = re.compile(
    r"^(?:please[,\s]+|(?:can|could|would|will)\s+you\s+(?:please\s+)?|(?:can|may)\s+i\s+|"
    r"i\s+(?:want|need|would\s+like|'d\s+like|’d\s+like)\s+to\s+|let'?s\s+)", re.I)


def asks_a_change(question: str) -> bool:
    """Whether *question* asks for a change (`CHANGE_VERBS`, its first word after a polite lead
    in, not a heading's word before a colon, nor a question's shape, `NOT_A_CHANGE_AFTER`), so
    it is asked of the model even when no passage is chosen (C4330)."""
    words = _LEAD_IN.sub("", (question or "").strip()).split()
    if not words or any(w.endswith(":") for w in words[:2]):
        # A heading before a colon ("Update: …", "Change management: …"), not a request.
        return False
    if len(words) > 1 and words[1].lower().strip(",.:;!?") in NOT_A_CHANGE_AFTER:
        return False
    return words[0].lower().strip(",.;!?") in CHANGE_VERBS


def prepare(question: str, *, screen: str = "", place: dict = None,
            reads_off: str = NO_PLACE) -> dict:
    """`answer`'s steps before its call, the one code path a person's press and an evaluation's
    batched request share (scripts/nmas-assistant-cases): the question's checks, the passages
    chosen from it as it leaves (masked, the mask's placeholders out), the call's data, its
    context and the loop feature, and the request of the plain pass (the one a press sends
    when no read may be asked, *reads_off* saying why).
    ``{"done": <answer's result, no call>}`` when it is refused (empty, too long) or no passage
    is chosen and nothing may be read (a manual gap); else ``{"chosen", "drawn", "data",
    "ctx", "feature", "place", "request"}``, *request* what `gateway.ask` takes for it:
    ``{"feature", "prompt", "schema", "parts", "context", "subject"}``."""
    from modules.ai import manual_index

    place = dict(place or {})
    question = (question or "").strip()
    refused = refusal(question)
    if refused:
        return {"done": refused}
    # Chosen from the question as it leaves (`redact.redact_egress`), its placeholders taken
    # out: neither a pasted secret's value nor the mask's own words rank the manual.
    from modules import redact
    ranked_by = re.sub(r"<redacted[^>]*>", " ", redact.redact_typed(question))
    chosen = manual_index.select(ranked_by, screen=screen)
    drawn = [{"link": p["link"], "page": p["page"], "heading": p["heading"]} for p in chosen]
    if not chosen and (reads_off or not place.get("devices")) and not asks_a_change(question):
        return {"done": {"ok": True, "state": "not_covered", "error": "", "detail": NOT_COVERED,
                         "passages": [], "gap": True}}
    data = parts(question, screen, chosen, place)
    ctx = context()
    feature = loop_feature(chosen)
    prompt, schema, sent, ctx_ = RL.first_request(feature, data, ctx, plain=True)
    return {"chosen": chosen, "drawn": drawn, "data": data, "ctx": ctx, "feature": feature,
            "place": place,
            "request": {"feature": FEATURE, "prompt": prompt, "schema": schema, "parts": sent,
                        "context": ctx_, "subject": subject(screen, place)}}


@acts_as_ai("assistant")
def answer(question: str, *, screen: str = "", place: dict = None, actor: str, trigger: dict,
           send=None, today: str = None, progress=None, stop_if=None,
           model: str = None) -> dict:
    """A person's question answered from the manual and the reads, or why not: ``{"ok",
    "state", "error", "detail", "answer"?, "cites"?, "sources"?, "reads"?, "calls"?,
    "passages", "call_id"?, "gap", ...}``. *state* ``answered``, ``not_covered`` (no passage
    chosen and nothing to read, or the answer is not covered: no answer drawn), ``refused`` (a
    gate, or Mercury's check) or ``failed``; *gap* True when the manual's gap is the route's
    to record; *passages* each chosen one's link, page and heading. *place* is what the person
    is looking at (`assistant_context.resolve`). Its steps: `scope_of`, `prepare`, the read loop
    through the gateway (`read_loop.run`), `settle`.

    The chat's job (`assistant_turns`) passes *progress* (``progress(words)``, each step as a
    person reads it: the model asked, the reads it asked for running, the model asked again) and
    *stop_if* (``stop_if() -> bool``, the person's Stop): the gateway closes a stream as soon as
    it reads a stop (its own *stop_if*), and no call is made after one, so no further read runs
    either; the result is then ``stopped`` with the calls made and their cost. *model* is the
    person's choice of model (`profiles.CHOOSABLE`), every call of the answer made on it; None,
    or the pin's own, is the pin's (no choice sent)."""
    from modules.ai import gateway
    from modules.nsot import listref

    say = progress or (lambda words: None)
    # The person's choice, checked and applied by the gateway (`gateway.request_body`, where the
    # pin's own model is no choice); None for the pin's.
    chosen = model or None
    place = dict(place or {})
    scope, devices, reads_off = scope_of(place, actor, question)
    place["devices"] = devices
    say("Choosing the manual's passages")
    prep = prepare(question, screen=screen, place=place, reads_off=reads_off)
    if "done" in prep:
        return prep["done"]
    seen = {"calls": [], "cost": 0.0}

    def ask(*a, trigger, **k):
        # Stop pressed: no call after it (so no read after it either).
        if stop_if is not None and stop_if():
            raise Stopped(seen["calls"], seen["cost"])
        n = len(seen["calls"]) + 1
        say("Asking the model" if n == 1 else f"Answering from the reads (call {n})")
        # The gateway's own result, its typed part's mask kept to say what was removed.
        got = gateway.ask(*a, trigger=trigger, stop_if=stop_if, model=chosen, **k)
        seen["calls"].append(got.get("call_id") or "")
        seen["cost"] += float(got.get("cost_usd") or 0.0)
        if got.get("typed_masked") and "typed_masked" not in seen:
            seen["typed_masked"] = got["typed_masked"]
        if stop_if is not None and stop_if():
            raise Stopped(seen["calls"], seen["cost"])
        wanted = getattr(got.get("output"), "reads", None) or []
        if got.get("ok") and wanted:
            say(f"Running the {len(wanted)} read{'s' if len(wanted) != 1 else ''} it asked for")
        return got

    network = place.get("network") or ""
    try:
        net_id = listref.network_id(network) if network else ""
    except Exception:                                  # noqa: BLE001 (the installation's)
        net_id = ""
    try:
        got = RL.run(FAMILY, prep["feature"], ask=ask, network=net_id, data=prep["data"],
                     actor=actor, trigger=trigger, context=prep["ctx"],
                     subject=prep["request"]["subject"], scope=scope, send=send, today=today,
                     reads_off=reads_off)
    except Stopped as stopped:
        return stopped_result(stopped.calls, stopped.cost_usd, prep["drawn"], actor,
                              model=chosen)
    if stop_if is not None and stop_if():
        # Stopped during the last call: its stream was closed, so its answer is not drawn.
        return stopped_result(seen["calls"], seen["cost"], prep["drawn"], actor, model=chosen)
    return settle(got, dict(prep, model=chosen), actor=actor,
                  typed_masked=seen.get("typed_masked") or "")


def stopped_result(calls_, cost_usd, passages, actor: str = "", model: str = None) -> dict:
    """`answer`'s result when the person pressed Stop: the calls made and what they cost. Each
    call's use is recorded as the person's Stop (`calls.record_use`, beside the call in History):
    the gateway records a closed stream in its own words, which name its watchdog's bound for
    every stop (C4324), so the assistant's own record says who stopped it."""
    from modules.ai import calls

    calls_ = [c for c in calls_ if c]
    for c in calls_:
        calls.record_use(c, STOPPED_USE, actor=actor,
                         detail=("Stopped by the person who asked: Stop in the assistant's "
                                 "panel; no call was made after it"))
    return {"ok": False, "state": "stopped", "error": "stopped", "detail": STOPPED,
            "calls": calls_, "call_id": calls_[-1] if calls_ else "", "cost_usd": cost_usd,
            "passages": passages, "gap": False, **model_words(model)}


def _reads_drawn(records: list, place: dict) -> list:
    """Each read the answer asked for, as the panel draws it: its id, what it read in a person's
    words, its verdict and reason, the device and the tab it opens on, and its run on History ›
    Reads."""
    out = []
    for r in records or []:
        op = r.get("op") or ""
        dev = str((r.get("args") or {}).get("device") or "")
        out.append({"id": r.get("id") or "", "words": FR.checked_words([r]),
                    "verdict": r.get("verdict") or "", "reason": r.get("reason") or "",
                    "device": dev, "tab": READ_TAB.get(op, "ask"),
                    "tab_words": TAB_WORDS.get(READ_TAB.get(op, "ask"), "Ask the device"),
                    "run": r.get("run") or "", "network": (place or {}).get("network") or ""})
    return out


def settle(got: dict, prep: dict, *, actor: str, typed_masked="") -> dict:
    """`answer`'s steps after the read loop (*got*, `read_loop.run`'s result): its state read as
    the panel's, the answering call's use recorded, then `drawn`."""
    from modules.ai import calls

    records = got.get("reads") or []
    first = got.get("first") or {}
    base = {"calls": [c for c in got.get("call_ids") or [] if c],
            "reads": _reads_drawn(records, prep.get("place")), "passages": prep["drawn"],
            "typed_masked": typed_masked, **model_words(prep.get("model"))}
    if got["state"] == "failed":
        return dict(base, ok=False, state="refused", error=first.get("error") or "failed",
                    detail=first.get("detail") or "", call_id=first.get("call_id") or "",
                    gap=False)
    if got["state"] == "refused_by_check":
        why = got.get("why") or ""
        calls.record_use(first.get("call_id") or "", "refused by validation", actor=actor,
                         detail=why)
        return dict(base, ok=False, state="refused", error="couldnt_answer",
                    detail=f"Couldn't answer: {why}. The call is in History.",
                    call_id=first.get("call_id") or "", gap=True)
    second = got.get("second") or {}
    if second.get("ok") and second.get("why"):
        calls.record_use(second.get("call_id") or "", "refused by validation", actor=actor,
                         detail=second["why"])
    call_id = got.get("answer_call") or first.get("call_id") or ""
    out = drawn(got["answer"], prep, actor=actor, call_id=call_id,
                cost_usd=float(got.get("cost_usd") or 0.0), records=records,
                typed_masked=typed_masked)
    if got["state"] == "first_pass":
        out["note"] = ("Mercury's reads were not answered on: " + (got.get("words") or "")
                       .replace("AI analysis: ", ""))[:400]
    return dict(base, **out)


def judge(got: dict, prep: dict, *, actor: str) -> dict:
    """`answer`'s steps after one call, the code path an evaluation's batched answer takes: *got*
    is `gateway.ask`'s result (or a batch's for one request, the same shape), *prep*
    `prepare`'s. Mercury's check (`check`), then `drawn`; the result is `answer`'s."""
    from modules.ai import calls

    chosen, drawn_ = prep["chosen"], prep["drawn"]
    if not got.get("ok"):
        return {"ok": False, "state": "refused", "error": got.get("error") or "failed",
                "detail": got.get("detail") or "", "call_id": got.get("call_id") or "",
                "passages": drawn_, "gap": False}
    words = got["output"]
    why = check(words, chosen)
    if why:
        calls.record_use(got["call_id"], "refused by validation", actor=actor, detail=why)
        return {"ok": False, "state": "refused", "error": "couldnt_answer",
                "detail": f"Couldn't answer: {why}. The call is in History.",
                "call_id": got["call_id"], "passages": drawn_, "gap": True,
                "typed_masked": got.get("typed_masked") or ""}
    return drawn(words, prep, actor=actor, call_id=got["call_id"],
                 cost_usd=got.get("cost_usd") or 0.0, records=(),
                 typed_masked=got.get("typed_masked") or "")


def drawn(words, prep: dict, *, actor: str, call_id: str, cost_usd: float, records,
          typed_masked="") -> dict:
    """An answer Mercury's check passed, as the panel draws it: not covered (no citation, or
    the answer says so), or answered with its sources (each passage and read it cites), a
    plan held to the plan engine's schema and a hand-off to a gated flow; the use recorded on
    *call_id*."""
    from modules.ai import calls

    place = prep.get("place") or {}
    passages = prep["drawn"]
    # A plan named (v2; a change's steps, v4): proposed only, held to the plan engine's schema;
    # the panel previews it in place at once, and a person approves it by its hash or not.
    plan, dropped = plan_of(words)
    # What Mercury has no tool for (v4): said and recorded (`record_no_tool`), never padded.
    no_tool = no_tool_of(words)
    plan_dropped = f"Mercury dropped the plan the answer named: {dropped}" if dropped else ""
    # C4330's review: a change request asked with no passage chosen and no read run is grounded
    # in nothing Mercury sent, so its free words are never drawn: only its plan (each step
    # previewed by Mercury's own operation) or what it has no tool for.
    grounded = bool(passages) or bool(records)
    if plan is None and no_tool is None and (not words.covered or not words.cites
                                             or not grounded):
        calls.record_use(call_id, "shown: not covered", actor=actor)
        return {"ok": True, "state": "not_covered", "error": "", "detail": NOT_COVERED,
                "call_id": call_id, "passages": passages, "gap": True,
                "plan_dropped": plan_dropped,
                "cost_usd": cost_usd, "typed_masked": typed_masked}
    calls.record_use(call_id, "shown: no tool" if no_tool and plan is None
                     else "shown: answered", actor=actor)
    cited = [d for d in passages if d["link"] in set(words.cites)]
    by_id = {r["id"]: r for r in _reads_drawn(list(records or ()), place)}
    sources = ([dict(c, kind="manual") for c in cited]
               + [dict(by_id[c], kind="read") for c in words.cites if c in by_id])
    handoff, handoff_dropped = handoff_of(words, place)
    return {"ok": True, "state": "answered", "error": "", "detail": "", "plan": plan,
            "no_tool": no_tool,
            "plan_dropped": plan_dropped,
            "handoff": handoff,
            "handoff_dropped": (f"Mercury dropped the hand-off the answer named: "
                                f"{handoff_dropped}" if handoff_dropped else ""),
            "answer": words.answer if grounded else "", "cites": cited, "sources": sources,
            "passages": passages,
            "call_id": call_id, "cost_usd": cost_usd, "gap": False,
            "typed_masked": typed_masked}


def button_state() -> dict:
    """The top bar's AI Assistant as every page draws it, from settings alone (no spend read,
    no call): ``{"switched_on", "ready", "why"}``. *switched_on*: the Assistant's switch
    (`installation_settings.assistant_on`); off, the button is disabled, its title saying where
    it is turned on. *ready*: hosted AI is allowed (`controls._hosted`, the AI controls' own
    seam); not ready, the button is greyed and still opens the panel, whose Ask says why in
    full (`ai_control('assistant')`)."""
    from modules import installation_settings
    from modules.ai import controls

    if not installation_settings.assistant_on():
        return {"switched_on": False, "ready": False,
                "why": installation_settings.ASSISTANT_OFF_WORDS}
    try:
        hosted = controls._hosted()
    except Exception as exc:                          # noqa: BLE001 (read as not ready)
        hosted = {"allowed": False, "why": f"hosted AI's setting cannot be read ({exc})"}
    if not hosted.get("allowed"):
        return {"switched_on": True, "ready": False,
                "why": ("The Assistant cannot answer now: hosted AI is off. A person who may "
                        "configure allows it on Settings › Installation › AI, the AI (hosted) "
                        "card. The panel still opens, and its manual links work.")}
    return {"switched_on": True, "ready": True, "why": ""}


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
