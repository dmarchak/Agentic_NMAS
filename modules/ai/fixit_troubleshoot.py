"""AI troubleshooting on an incident's page (board recurring-fixes v2, steps 2 and 3; the fix-it
plan's S5; docs/HEAL_TO_INTENT.md section 12, "The AI call (S5)"; docs/MERCURY_CHARTER.md, "The
fix-it path"): one investigation a verified person's press asks for, its answer checked by code,
and at most ONE proposal, which opens its operation's own preview and runs only when a person
approves it there by that preview's hash.

**Started only by a person's press** (`troubleshoot`, `STEPS`): the incident page's Troubleshoot
with AI, or Retry with more information's Ask the AI to re-plan (routes/fixit_v2.py,
``troubleshoot``, a POST a verified person makes, gated ``configure``). Its trigger is
``triggers.person`` of the request's verified actor, which the gateway refuses outside a request
or for anyone else; no timer, job, page load or failure's handler calls it
(tests/test_ai_entry_points.py), but one: since the operator's R1 (2026-11-14) the background
feature ``fixit_auto`` (`background.FEATURES`, off by default per network) asks the same
investigation once per failure of Mercury's fix, as its job under its own trigger
(`background_trigger`; `heal_notice.fixit_investigation`). **One press, one investigation**: its
passes go on until one adds no new evidence (`read_loop.no_new_evidence`; the operator,
2026-11-16: no rounds or calls bound), its reads included, under the spending limits alone,
each judged by the gateway at every pass's start and live while it streams: the per-incident
cap (`incident_cap`, passed as the gateway's *spend_cap*), the feature's day and month caps
for a background investigation, and the installation's day cap. A start is refused before
anything is built only when the incident's cap cannot pay even the least one call costs
(`start_usd`). The estimate is drawn before the press (`estimate`). The mode is the installation's: this
build offers Manual (default) and Off (`fixit.policy.mode`); Off refuses the press with nothing
sent.

**What is sent** (`request`), built in code before any call:
- the incident's evidence pack (`evidence_pack.build_incident`: what started it, the device,
  History, Intent, neighbours, the network as observed, health, the monitoring side, its log
  lines, what self-healing tried as ``tried:<n>`` and Mercury's diagnosis by kind as
  ``diag:<n>``), its sections as Explain sends them (`explain.sent_sections`, the topology class
  asked); configuration only as the pack holds it (by kind, the intent diff masked);
- the incident's **attempts**, each catalog operation run in it (`fixit.payload.tried_parts`,
  every person a stable label), as the section ``attempts``, each piece ``attempt:<n>``
  (``tried:<n>`` is the pack's own self-healing steps);
- **Seen before**, Mercury's own record (`seen_before`, read from the alerts reader's stored
  value, never searched here), as the piece ``seen_before:1``;
- the person's **note**, the typed part ``note`` (`gateway.TYPED_PARTS`: masked as it leaves and
  said), cited ``note:1``;
- the **catalog** the fix may name (`fixit.payload.catalogue_part`), in the cached context.

**Since v7 and v8 (C3755, C3764, 2026-11-15) the answer is a PLAN** (`TroubleshootPlan`): its
steps in order, each a catalog operation, a built-in command plan (its typed parameters) or the
plan engine's intent change or deploy (`StepParams`), and an ``improvement`` note beside a
clumsy plan (the steps and time a shorter route saves, the shorter route's own steps kept as a
second line beside the first, and each raw-line shape it would need proposed provisional to
Mercury's rule for raw lines). It comes through the one door's `plan_for_incident`, each step
held there (`fix_proposal.step_held`: the plan engine's schema, the AI's never-list) and on the
page's preflight (`fixit.plan.preflight`). The catalogue it is sent is read from the code
(`fixit.payload.catalogue_part`). What follows is v1 to v6's, kept: ``fix`` is still taken as a
plan of one.

**The answer's schema** (`Troubleshoot`, shape B plus one fix): a rationale, at most three
hypotheses each citing what was sent, then ``fix`` (ONE catalog operation with its parameters,
or null), ``gap`` (what the fix would need that no catalog operation does, or null; never both)
and ``needs_human``. **The check** (`check`, each pass): Explain's (`explain.check`: every
reference resolves to what was sent, every confirming read on the read-only allowlist, every
device named cited); the fix held to the catalog's schema (`catalog.checked`: exactly the
operation's parameters, each of its shape, so a command string is no parameter and is refused);
and the read loop's actable rule (`acts_on`: the device and subscriptions a fix names must be
the incident's own, never one a read or the note returned). A refused answer is recorded
("refused by validation") and drawn "couldn't be checked", its spend counted.

**From an answer to a proposal, through the one door** (`fix_proposal.for_incident`): the fix,
exactly ``{operation, params}``, passes the same check as Mercury's own proposal
(`fixit.validate.check`: the catalog, the incident's scope, the heal guards, committed intent
through the operation's own preview), is flagged when it repeats a failed attempt, and is kept as
the incident's proposal line with ``source`` ``ai`` and its call ids, so its cost and "how fixed:
AI-assisted" are the incident's. A refused fix is recorded on its call and kept with no
operation. A gap, an answer that names no fix and the evidence that cannot say are each a
proposal line with no operation and their words. **Nothing here runs anything**: it opens no
session, holds no device, starts no job and sends to no device; the proposal's Approve is the
operation's own card and confirm (tests/test_ai_fix_rule.py). A failed attempt STOPs the section;
the AI is asked again only by a person's Retry with more information.

**The reads** go only through Mercury's read families, `fixit_reads.FAMILY` (v5 since C3661:
a show of one of the AI's command families (`router_reads.SHOW_FAMILIES`), or a bounded ping
or traceroute, named by its verb and words, held whole by Mercury's allowlist too, on a
device in scope, through the reads engine as Mercury's account by default and on History ›
Reads with whom it signed in as; Mercury's own reads of intent, golden, neighbours, history,
logs and metrics; a read Mercury lacks recorded as a missing capability, `record_missing`; what
follows is S6's, kept as v4): the router
read set's (each command whole on its allowlist, on the incident's device, as the read-only
account, through the reads engine and on History › Reads), the lost stream's three among them,
and Mercury's own (the collector's sessions on its host and the stream's series, held to the
incident's device and subscriptions), while the network's device state class is on (off by
default: then pass 1 is the plain pass, "reads not asked"). Each read is in the send log
(`read_log`) and on History (`history_sources.ai_reads`). The model composes no command.
"""

import json
import logging
import time
from enum import Enum
from typing import Optional

from modules.ai import calls, gateway
from modules.ai import read_loop as RL
from modules.ai import fixit_reads as FR
from modules.ai import router_reads as RR
from modules.ai.explain import Hypothesis
from modules.ai.schemas import FlatWire, StrictModel, register

from modules.identity import acts_as_ai  # noqa: E402 (the AI's own identity, its role)

log = logging.getLogger(__name__)

#: The task (`profiles.TASKS`'s pin) and its prompts: v1 the plain pass (no read class on), v4
#: the read loop's first pass over AI troubleshooting's own read family (S6), v3 its second.
#: v2 is S5's first pass over the router read set alone: no longer asked, kept with its schema
#: so a call recorded under it stays readable (expand, then contract).
FEATURE = "fixit_troubleshoot"
#: The background feature that asks the same investigation by itself when Mercury's fix fails
#: (the operator's R1, 2026-11-14; `background.FEATURES`, a STANDING one), and the finding kind
#: its trigger names: the failure's own record (`fixit.auto`'s key).
AUTO_FEATURE = "fixit_auto"
AUTO_FINDING = "fixit_failure"
PROMPT = (FEATURE, 1)
PROMPT_READS_V2 = (FEATURE, 2)
PROMPT_READS_V4 = (FEATURE, 4)
#: v5 (the operator, 2026-11-14, C3661): the reads pass over Mercury's own allowlist and its
#: own reads (`fixit_reads.FAMILY`), as Mercury's account by default. v4, the fixed shapes, is
#: no longer asked and is kept with its schema (expand, then contract).
PROMPT_READS = (FEATURE, 5)
#: v6 (2026-11-14): v3's second pass with no read set (pass 2 cannot ask again, and the read set
#: is left out of its request: the host's preview of a router's standing incident measured it
#: 7,632 characters of a request over its bound), a cut section said, and the reads as v5 names them. v3 stays
#: as it shipped; both answer by v3's schema (`TroubleshootSecond`).
PROMPT_SECOND_V3 = (FEATURE, 3)
PROMPT_SECOND_V6 = (FEATURE, 6)
#: v7 and v8 (C3755, C3764, 2026-11-15): the answer a plan of Mercury's steps (catalog
#: operations, built-in command plans, intent changes and deploys) with an improvement note; v7
#: the plain pass and the second, v8 the reads pass. v1, v5 and v6 stay as they shipped, with
#: their schemas, so a call recorded under them stays readable; none is asked now.
#: v9 and v10 (the operator, 2026-11-15): v7 and v8 as the provider can compile them, their
#: schemas flattened (`TroubleshootPlanFlat`); v7 and v8 stay readable, never asked.
#: v11, v12 and v13 (C3797, the same day): the investigation, iterative: v11 its first pass,
#: v12 a later pass with the reads so far (it may ask again), v13 its last pass (and the plain
#: one); each answer names the read it lacked. v9 and v10 stay readable, never asked.
#: v14, v15 and v16 (the operator, 2026-11-16, a router's wedged session): v11, v12 and v13 with a
#: lost stream's stalled session said: test the path first (DF pings at full size and a
#: traceroute), and, when it is clean, reset one end, least disruptive first, by the ladder
#: section's first untried rung (`modules/fixit/ladder.py`). v11 to v13 stay readable, never
#: asked; the answers' schemas are theirs, unchanged.
#: v17 (the operator, 2026-11-16: "The tighter answer shortens only the rationale fields; the
#: exact commands, citations and evidence stay whole. The prompt is a new numbered version"):
#: v14 to v16 as ONE prompt and ONE schema for every pass (the first, a later one, the last and
#: the plain one), so the system prefix and the schema are the same bytes call to call and the
#: provider's cache one call writes is read by the next (`read_loop.LoopFeature.one_shape`: the
#: pass is said in the data, `read_loop.PASS_PART`); its rationale fields bounded in length
#: (the rationale at most 300 characters, each hypothesis's claim, step's why, read's why and
#: hypothesis, gap's what, improvement's what and saves and why_not at most 160), every
#: command, citation and evidence field whole. The bounds are ASKED in the prompt, never
#: enforced: the schema has no maxLength (deliberate: an over-long answer must not fail the
#: schema and lose the investigation). v14 to v16 stay readable, never asked.
PROMPT_INVESTIGATE = (FEATURE, 18)
PROMPT_PLAN = PROMPT_INVESTIGATE
PROMPT_PLAN_READS = PROMPT_INVESTIGATE
PROMPT_AGAIN = PROMPT_INVESTIGATE
#: The investigation's bounds (C3797; the operator: "the incident's cost cap, plus a declared
#: maximum of reads and wall time (in the wait registry), not a fixed 2 passes"): `MAX_READS`
#: reads in all (three a pass, the family's limit), and `WALL_S` seconds from the first pass's
#: start before the last pass is asked (reasoned: a switch's press of 2026-11-15 19:10 UTC
#: took about 20 s a pass and under 2 s a read, so four passes and nine reads are about 100 s;
#: 2.5x that is 240 s). No rounds or calls bound (the operator, 2026-11-16: ``ROUNDS`` and
#: ``CALLS_WORST`` are gone): the loop stops when a pass adds no new evidence, and the spend
#: is the caps' to stop, at each pass's start and live.
MAX_READS = 9
WALL_S = 240.0
#: The calls the estimate expects of one investigation (reasoned: a read round and its
#: answer, then the last pass): an estimate input only.
CALLS_EXPECTED = 3
PROMPT_SECOND = PROMPT_PLAN
#: The pack's own sections, in the pack format's order (the heal analysis's, whose pack this is).
PACK_SECTIONS = ("incident", "device", "history", "intent", "neighbours", "observed", "health",
                 "observer", "logs", "tried", "diagnosis")
#: This incident's own sections, beside the pack's.
ATTEMPTS = "attempts"
#: Each failed attempt's own steps (`run_steps_section`), and the state read after the newest
#: failed run (`after_run_section`; the operator, 2026-11-16). The after-run parts are sent
#: whole: every collector session and every syslog line since the run (the operator,
#: 2026-11-16: ``AFTER_SESSIONS``, ``AFTER_SYSLOG_LINES`` and ``AFTER_LINE_CHARS`` are gone;
#: evidence is cut only to stay inside the context window).
RUN_STEPS = "run_steps"
AFTER_RUN = "after_run"
SEEN = "seen_before"
NOTE = "note"
READS_SECTION = "mercury_reads"
#: At most this many hypotheses (Explain's).
MAX_HYPOTHESES = 3
#: What a press runs, in order (the manual's How it works page names each).
STEPS = ("person", "mode", "cap", "pack", "ask", "check", "propose", "record")
#: The states an investigation ends in, each drawn by the section.
STATES = ("proposed", "refused_fix", "gap", "no_fix", "unanswerable", "unchecked", "failed")
#: The gateway's refusals before anything is sent, in a person's words.
NOT_SENT_WORDS = {"ai_off": "hosted AI is off", "no_key": "no Anthropic API key is set",
                  "over_cap": "a cap is reached", "feature_cap": "a cap is reached",
                  "trigger": "the press could not be tied to a verified person",
                  "classified": "the network's classification marking forces AI off"}
#: How long a shown text is kept, at most, in characters.
SHOWN_CHARS = 600


class Outcome(str, Enum):
    answer = "answer"
    refuse = "refuse"


class FixParams(StrictModel):
    """A fix's parameters: every parameter some catalog operation takes, the ones the named
    operation does not take null (`catalog.CATALOG`; `as_door` keeps only those given)."""
    device: str
    subscriptions: Optional[list[str]]
    subscription: Optional[str]


class Fix(StrictModel):
    """ONE catalog operation with its parameters, why and what it rests on."""
    operation: str
    params: FixParams
    why: str
    evidence_refs: list[str]


class Gap(StrictModel):
    """What the fix the evidence points to would have to do, which no catalog operation does."""
    what: str
    evidence_refs: list[str]


@register(FEATURE, 1)
class Troubleshoot(StrictModel):
    """Shape B, Explain's, with one fix or a gap: the rationale first, the hypotheses, then the
    fix (or null), the gap (or null), whether a person is needed, or why the evidence cannot
    say."""
    outcome: Outcome
    rationale: str
    hypotheses: list[Hypothesis]
    fix: Optional[Fix]
    gap: Optional[Gap]
    needs_human: bool
    why_not: str


#: One entry of S5's pass 1 ``reads`` field (`read_loop.request_model` over the router read
#: set): v2's, kept as it shipped so a call recorded under it is read by it.
ReadAsk = RL.request_model(RR.AI_READS)


#: S5's pass 1 (v2), no longer asked (v4 is): kept, its docstring and fields as it shipped
#: (they are its committed schema), so a call recorded under it stays readable.
@register(FEATURE, 2)
class TroubleshootReads(Troubleshoot):
    """Pass 1 of the read loop: `Troubleshoot`, plus at most 3 reads asked of Mercury."""
    reads: list[ReadAsk] = []


@register(FEATURE, 3)
class TroubleshootSecond(Troubleshoot):
    """Pass 2: `Troubleshoot`, the reads that ran attached; it cannot ask again."""


#: One entry of S6's pass 1 ``reads`` field, over AI troubleshooting's read family
#: (`fixit_reads.FAMILY`: the router read set, the stream's three shapes, Mercury's own reads).
FixitReadAsk = RL.request_model(FR.FAMILY_V4)


#: S6's pass 1 (v4), no longer asked (v5 is): kept, its docstring and fields as it shipped.
@register(FEATURE, 4)
class TroubleshootFixitReads(Troubleshoot):
    """Pass 1 of the read loop (S6): `Troubleshoot`, plus at most 3 reads of AI
    troubleshooting's read family."""
    reads: list[FixitReadAsk] = []


#: One entry of v5's pass 1 ``reads`` field, over AI troubleshooting's read family as C3661
#: made it (`fixit_reads.FAMILY`: Mercury's allowlist, Mercury's own reads, the stream reads).
EngineerReadAsk = RL.request_model(FR.FAMILY)


@register(FEATURE, 5)
class TroubleshootEngineerReads(Troubleshoot):
    """Pass 1 of the read loop: `Troubleshoot`, plus at most 3 reads Mercury runs: a device's
    read by Mercury's allowlist, or Mercury's own read of what it holds."""
    reads: list[EngineerReadAsk] = []


class StepParams(StrictModel):
    """A plan step's parameters (C3755, C3764): every parameter some step kind the plan may name
    takes, the ones the named kind does not take null (`plan_step_kinds`; `as_door` keeps only
    those given): a catalog operation's device and subscriptions, a built-in command plan's
    typed ones (an interface, a cause), an intent change's patch as its YAML text, a deploy's
    removals by their ids."""
    device: str
    subscriptions: Optional[list[str]]
    subscription: Optional[str]
    interface: Optional[str]
    cause: Optional[str]
    changes: Optional[str]
    remove: Optional[list[str]]


class PlanStepAnswer(StrictModel):
    """One step of the answer's plan: a step kind Mercury has, with its parameters, why and
    what it rests on."""
    operation: str
    params: StepParams
    why: str
    evidence_refs: list[str]


class ShapeAsk(StrictModel):
    """A raw configuration line a shorter command plan would need that Mercury has not measured,
    as Mercury writes a shape (`command_policy.shapes`): proposed to Mercury's rule for raw lines,
    held provisional until an admin approves it."""
    dialect: str
    shape: str
    why: str


class Improvement(StrictModel):
    """Beside a plan that works but is clumsy: what a shorter route would do, what it saves
    (steps and time), the shorter route's own steps when Mercury has them, and the shapes it
    would need that Mercury has not measured."""
    what: str
    saves: str
    steps: list[PlanStepAnswer]
    shapes: list[ShapeAsk]


#: v7 (C3755, C3764, 2026-11-15): the answer is a PLAN of steps, in order, each a catalog
#: operation, a built-in command plan or an intent change or deploy, with an improvement note
#: beside a clumsy one. `fix` stays, a plan of one in the older shape (expand, then contract).
@register(FEATURE, 7)
class TroubleshootPlan(Troubleshoot):
    """`Troubleshoot`, its fix a plan of Mercury's steps in order (or a gap), and an improvement
    note beside a plan a shorter route would beat. Its JSON schema, committed and sent, holds no
    title or description (nl_query's `_LeanSchema`, C1830's rule: each field is the prompt's to
    describe; the gate's measurement, 2026-11-15: v8's 7,019 characters to 4,418), the same
    properties, required fields, enums and references."""
    plan: list[PlanStepAnswer] = []
    improvement: Optional[Improvement] = None

    @classmethod
    def model_json_schema(cls, by_alias=True, ref_template=None, schema_generator=None,
                          mode="validation", **kw):
        from pydantic.json_schema import DEFAULT_REF_TEMPLATE

        from modules.ai.nl_query import _LeanSchema
        return super().model_json_schema(by_alias=by_alias,
                                         ref_template=ref_template or DEFAULT_REF_TEMPLATE,
                                         schema_generator=schema_generator or _LeanSchema,
                                         mode=mode, **kw)


@register(FEATURE, 8)
class TroubleshootPlanReads(TroubleshootPlan):
    """Pass 1 of the read loop: `TroubleshootPlan`, plus at most 3 reads Mercury runs."""
    reads: list[EngineerReadAsk] = []


@register(FEATURE, 9)
class TroubleshootPlanFlat(FlatWire, TroubleshootPlan):
    """`TroubleshootPlan` as the provider can compile it (the operator, 2026-11-15: v7's 17 and
    v8's 20 union parameters were over the provider's 16, and v8's every call was refused,
    "The compiled grammar is too large"): sent flattened, every field required and none
    nullable ("" or [] for none; `schemas.flatten`), read back in v7's shape (`unflatten`). Its
    legacy ``fix`` is not asked (the plan is the fix) and reads as None."""

    @classmethod
    def model_json_schema(cls, *args, **kw):
        schema = super().model_json_schema(*args, **kw)
        return _without_fix(schema)


@register(FEATURE, 10)
class TroubleshootPlanReadsFlat(FlatWire, TroubleshootPlanReads):
    """`TroubleshootPlanReads` flattened as `TroubleshootPlanFlat` is: its reads' arguments each
    a string ("" for one the operation does not take), never a union of every scalar."""

    @classmethod
    def model_json_schema(cls, *args, **kw):
        schema = super().model_json_schema(*args, **kw)
        return _without_fix(schema)


@register(FEATURE, 11)
class TroubleshootInvestigate(TroubleshootPlanReadsFlat):
    """The investigation's first pass (C3797; the operator, 2026-11-15: "the AI settles
    uncertainty itself, like a Mercury user"): `TroubleshootPlanReadsFlat`, with the read it
    lacked (*lacked_read*: the one read-only command that would settle what its plan depends on
    when its read set offers none, "" otherwise), flattened as v10 is."""
    lacked_read: str = ""


@register(FEATURE, 12)
class TroubleshootInvestigateAgain(TroubleshootInvestigate):
    """A later pass of the investigation, its reads so far attached: `TroubleshootInvestigate`,
    which may ask for more."""


@register(FEATURE, 13)
class TroubleshootInvestigated(TroubleshootPlanFlat):
    """The investigation's last pass (its bounds reached): `TroubleshootPlanFlat` with
    *lacked_read*; it cannot ask again."""
    lacked_read: str = ""


# v14 to v16 (2026-11-16): the same answers as v11 to v13, asked by the prompts that say a
# stalled stream's session and the ladder; registered apart so a call names its version.
@register(FEATURE, 14)
class TroubleshootInvestigateV14(TroubleshootInvestigate):
    """v11's first pass, asked by v14's prompt."""


@register(FEATURE, 15)
class TroubleshootInvestigateAgainV15(TroubleshootInvestigateAgain):
    """v12's later pass, asked by v15's prompt."""


@register(FEATURE, 16)
class TroubleshootInvestigatedV16(TroubleshootInvestigated):
    """v13's last pass, asked by v16's prompt."""


#: v17 (2026-11-16): every pass's one schema, v14's answer (with reads: a last or plain pass's
#: reads are never run), asked by v17's prompt.
@register(FEATURE, 17)
class TroubleshootInvestigateV17(TroubleshootInvestigate):
    """The investigation's one answer for every pass, asked by v17's prompt."""


#: v18 (the operator, 2026-11-17: "when a fix exists, the AI always proposes it; any doubt
#: (recurrence, re-trip risk) is stated as a risk on the plan, never a reason to withhold"):
#: v17's prompt with that rule, and a gap only when no fix exists; v17's answer, unchanged.
@register(FEATURE, 18)
class TroubleshootInvestigateV18(TroubleshootInvestigate):
    """The investigation's one answer for every pass, asked by v18's prompt."""


#: How a call that was sent and got no answer begins its line (the operator, 2026-11-15: a
#: refused request was drawn as "the AI named no fix"): `fixit.section` reads it as a failure,
#: never as an answer.
NOT_ANSWERED = "The AI didn't answer"
#: The same line as it was kept until then ("The AI did not answer (<kind>: <detail>)").
NOT_ANSWERED_BEFORE = "The AI did not answer ("


def not_answered_words(kind: str, detail: str) -> str:
    """What a sent call that got no answer says: what happened, in words, then that nothing
    reached a device (a failed call changes nothing). "The AI named no fix" is said only of an
    answer that named none."""
    import re

    d = str(detail or "")
    m = re.match(r"HTTP (\d{3})", d)
    status = int(m.group(1)) if m else 0
    low = d.lower()
    if status == 429:
        reason = "the provider is limiting requests; ask again in a minute"
    elif 400 <= status < 500:
        why = ("its schema too large" if "grammar" in low or ("schema" in low and (
            "complex" in low or "large" in low)) else d.split(": ", 2)[-1][:120])
        reason = f"the request was rejected ({why})"
    elif status >= 500:
        reason = f"the provider failed (HTTP {status})"
    else:
        reason = f"{kind or 'the call failed'}: {d[:160]}" if d else (kind or "the call failed")
    return f"{NOT_ANSWERED}: {reason}. Nothing was sent to any device."


def _without_fix(schema: dict) -> dict:
    """*schema* without the legacy one-step ``fix`` (and its definitions, unreferenced once it
    is gone): v9 and v10 ask for the plan alone."""
    schema["properties"].pop("fix", None)
    schema["required"] = [k for k in schema["required"] if k != "fix"]
    text = json.dumps({k: v for k, v in schema.items() if k != "$defs"})
    defs = schema.get("$defs") or {}
    used, todo = set(), [text]
    while todo:
        chunk = todo.pop()
        for name, body in defs.items():
            if name not in used and f'"#/$defs/{name}"' in chunk:
                used.add(name)
                todo.append(json.dumps(body))
    schema["$defs"] = {k: v for k, v in defs.items() if k in used}
    return schema


SCHEMA_OF = {1: Troubleshoot, 2: TroubleshootReads, 3: TroubleshootSecond,
             4: TroubleshootFixitReads, 5: TroubleshootEngineerReads, 7: TroubleshootPlan,
             8: TroubleshootPlanReads, 9: TroubleshootPlanFlat, 10: TroubleshootPlanReadsFlat,
             11: TroubleshootInvestigate, 12: TroubleshootInvestigateAgain,
             13: TroubleshootInvestigated, 14: TroubleshootInvestigateV14,
             15: TroubleshootInvestigateAgainV15, 16: TroubleshootInvestigatedV16,
             17: TroubleshootInvestigateV17, 18: TroubleshootInvestigateV18}


class Refused(ValueError):
    """Nothing was sent; the words say why. ``status`` is the HTTP status it answers."""

    def __init__(self, words: str, status: int = 409):
        super().__init__(words)
        self.status = status


# ── The figures, drawn before the press ─────────────────────────────────────────────────────

def start_usd() -> float:
    """The least any call of an investigation can cost, in US dollars: the task's typical
    output (`background.typical_output`, the measured median, or the pin's stand-in) at its
    model's output rate, before any prompt. What a start, a retry or a catch-up is held to
    before its request is built (`fixit.policy.cap_state`): a remaining under it cannot pay
    the counted prompt plus the typical output of any call, so refusing there is never
    stricter than the gateway's own rule (the operator, 2026-11-16: "A start is refused only
    if the remaining budget can't cover the counted prompt plus the task's measured typical
    output"); the gateway judges the real figure at each call. Replaces ``worst_usd``."""
    from modules.ai import background, profiles

    pin = profiles.task(FEATURE)
    rate = profiles.prices_for(pin["model"], 0)["output"]
    return round(int(background.typical_output(FEATURE)["tokens"]) * rate / 1_000_000, 6)


def worst_usd() -> float:
    """Kept ONLY for the tests that still call it (tests/test_fixit_catch_up.py,
    test_fixit_start_spend.py, test_fixit_troubleshoot.py, test_fixit_unverified.py) until the
    full pass updates them (skip mode, 2026-11-16): `start_usd`'s value. Nothing in the product
    calls it; there is no worst case any more."""
    return start_usd()


def estimate() -> dict:
    """``{"usd", "least", "measured", "basis"}``: what one investigation is expected to cost,
    the task's measured mean cost per sent call (`background.measured_cost`, its last 30 days)
    times the calls one is expected to make (`CALLS_EXPECTED`), or, with none measured, its
    stand-in said as such; and the least one call costs (`start_usd`). No worst case: there is
    no bound on calls, only the spending limits. A read of the record of AI calls; no call is
    made."""
    from modules.ai import background

    got = background.measured_cost(FEATURE)
    usd = round(float(got["usd_per_call"]) * CALLS_EXPECTED, 6)
    return {"usd": usd, "least": start_usd(), "measured": bool(got["measured"]),
            "basis": got["basis"]}


def incident_cap(incident, spent_here) -> dict:
    """The incident's own spending limit as the gateway's *spend_cap* (`gateway.ask`): its cap
    (`fixit.policy.cap_usd`, the network's or the installation's, said with where it is
    changed), and what it has spent read inside the reservations' lock each time: the calls
    its proposals name (`fixit.incident.cost_so_far`) plus *spent_here()*, this
    investigation's calls so far (recorded, not yet on a proposal); its calls in flight are
    held under ``incident:<id>``. None when the cap cannot be read (the start's check refuses
    that first)."""
    from modules.fixit import incident as F
    from modules.fixit import policy as P

    network = getattr(incident, "network", None)
    cap = P.cap_usd(network)
    if cap["state"] != "ok":
        return None

    def spent():
        got = F.cost_so_far(incident)
        if got["state"] == "unreadable":
            return {"state": "unreadable", "error": got["error"]}
        return {"state": "ok", "usd": float(got["usd"] or 0.0) + float(spent_here() or 0.0)}

    return {"name": "this incident's AI cap", "kind": "incident",
            "said": f"this incident's AI cap ({P.cap_said(network or 'the network', cap)})",
            "usd": float(cap["usd"]), "spent": spent, "scope": f"incident:{incident.id}"}


# ── What is sent ────────────────────────────────────────────────────────────────────────────

def _section(name: str, state: str, why: str = "", pieces=(), source: str = "",
             **extra) -> dict:
    return {"ref": name, "name": name, "source": source, "state": state, "why": why,
            "pieces": list(pieces), **extra}


def attempts_section(incident, resolved: float = None, *, now: float = None,
                     got: dict = None) -> dict:
    """The incident's attempts as sent (`payload.tried_parts`, every person a stable label,
    or *got*, its answer already read), each piece ``attempt:<n>``."""
    from modules.fixit import payload

    if got is None:
        got = payload.tried_parts(incident, resolved, now=now)
    pieces = []
    for key, part in sorted(got["parts"].items(), key=lambda kv: int(kv[0].split(":")[1])):
        pieces.append(dict(part, ref="attempt:" + key.split(":", 1)[1],
                           device=incident.device))
    source = "the operations' own run records, this incident's attempts (modules/fixit)"
    if got["state"] != "ok":
        return _section(ATTEMPTS, "ok" if pieces else "unreadable", got["error"], pieces,
                        source, incomplete=got["error"])
    return _section(ATTEMPTS, "ok" if pieces else "empty",
                    "" if pieces else "no catalog operation has run in this incident", pieces,
                    source)


def failed_of(got: dict) -> list:
    """The failed attempts of *got* (`payload.tried_parts`'s, as sent), as the ladder reads
    them (`ladder.tried`): ``[{"n", "operation", "params", "outcome"}]``."""
    out = []
    for key, part in sorted(((got or {}).get("parts") or {}).items(),
                            key=lambda kv: int(kv[0].split(":")[1])):
        if not part.get("passed"):
            out.append({"n": int(key.split(":")[1]), "operation": part.get("operation") or "",
                        "params": dict(part.get("params") or {}),
                        "outcome": part.get("outcome") or ""})
    return out


def run_steps_section(incident, got: dict) -> dict:
    """Each failed attempt's own steps (*got*, `payload.tried_parts`'s ``run_steps``; the
    operator, 2026-11-16), each piece ``run_steps:<n>`` by the attempt's number: its steps in
    order, each its name, result, words and reads' line, masked and capped
    (`payload.RUN_STEPS_CHARS` a piece, the newest `payload.RUN_STEPS_ATTEMPTS` failed
    attempts)."""
    from modules.fixit import payload

    steps = (got or {}).get("run_steps") or {}
    pieces = [dict(part, ref=key, device=incident.device)
              for key, part in sorted((steps.get("parts") or {}).items(),
                                      key=lambda kv: int(kv[0].split(":")[1]))]
    source = "each failed attempt's own run record, its steps in order (modules/fixit/payload.py)"
    said = list(steps.get("unread") or [])
    if steps.get("left_out"):
        said.append(f"{steps['left_out']} older failed attempt(s) left out: the newest "
                    f"{payload.RUN_STEPS_ATTEMPTS} are sent")
    if not pieces:
        return _section(RUN_STEPS, "unreadable" if steps.get("unread") else "empty",
                        "; ".join(said) or "no attempt in this incident failed", (), source)
    return _section(RUN_STEPS, "ok", "; ".join(said), pieces, source)


def after_run_section(network: str, incident, newest: dict, *, now: float = None,
                      loki=None, stream_reads: dict = None) -> dict:
    """The state read AFTER a failed run, for a re-investigation the run's failure started or a
    person's after it (*newest*, `payload.tried_parts`'s ``newest_failed``; the operator,
    2026-11-16): from Mercury's own sources, read now, each piece citable:

    - ``after_run:collector``: for each subscription, the collector's sessions from the
      device's addresses with their counters (bytes received and sent, the last receive and
      send, `diagnose_stream.read_collector` through `fixit_reads._collector`), every session;
    - ``after_run:series``: each subscription's series now (`diagnose_stream.series_of`);
    - ``after_run:collector_log``: the collector's own journal since the run started, its unit
      measured from the listener's owner (`diagnose_stream.collector_unit`, never typed), at
      most `diagnose_stream.JOURNAL_LINES` lines of `diagnose_stream.JOURNAL_LINE_CHARS`;
    - ``after_run:syslog``: the device's syslog lines since the run started, through the
      pack's own Loki read (`evidence_pack.logs_section`, its window from the run's start),
      every line whole.

    ``None`` when the newest attempt passed or none ran. A telemetry part is read only for an
    incident naming subscriptions. Everything is masked (`redact_payload`). *loki* and
    *stream_reads* (``{"collector", "series", "journal", "unit"}``) replace the reads (tests)."""
    import time as _time

    from modules import evidence_pack as EP
    from modules.heal import diagnose_stream as DS
    from modules.nsot import listref
    from modules.redact import redact_payload

    if not newest or not newest.get("started_at"):
        return None
    fx_reads = dict(stream_reads or {})
    since = float(newest["started_at"])
    now = float(now if now is not None else _time.time())
    at = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(since))
    pieces = []
    if incident.subscriptions:
        fx = dict(FR.stream_scope(network, incident), collector=fx_reads.get("collector"),
                  series=fx_reads.get("series"))
        coll, series, units = [], [], {}
        for sub in incident.subscriptions:
            try:
                got = FR._collector(fx, sub)
                coll.append(dict(got, subscription=sub, state="read"))
            except (RuntimeError, KeyError, ValueError, OSError) as exc:
                coll.append({"subscription": sub, "state": "unread", "why": str(exc)[:200]})
            try:
                series.append(dict(FR._series(fx, incident.device, sub), subscription=sub))
            except Exception as exc:                  # noqa: BLE001 (said, never raised)
                series.append({"subscription": sub, "state": "unread",
                               "why": f"not read ({type(exc).__name__})"})
            stream = (fx.get("streams") or {}).get(sub) or {}
            if stream.get("address"):
                units[(stream["address"], int(stream["port"]))] = sub
        pieces.append({"ref": f"{AFTER_RUN}:collector", "device": incident.device,
                       "what": "the collector's sessions from the device's addresses, read "
                               "now, after the run", "subscriptions": coll,
                       "note": "bytes_sent null: not printed (the kernel's tool prints it only "
                               "when it is not zero)"})
        pieces.append({"ref": f"{AFTER_RUN}:series", "device": incident.device,
                       "what": "each subscription's series in Prometheus now",
                       "subscriptions": series})
        pieces.append(_collector_log_piece(units, since, at, fx_reads, DS))
    try:
        ref = listref.resolve(network)
        logs = EP.logs_section(ref, incident.device, since, now, client=loki)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        logs = {"state": "unreadable", "why": f"not read ({type(exc).__name__})", "pieces": []}
    lines = [p for p in logs.get("pieces") or [] if p.get("after_onset")]
    kept = lines
    pieces.append({"ref": f"{AFTER_RUN}:syslog", "device": incident.device,
                   "what": f"{incident.device}'s syslog lines since the run started ({at}), "
                           "from the network's Loki",
                   "state": ("read" if lines else "empty" if logs.get("state") in ("ok", "empty")
                             else "unread"),
                   "why": "" if lines else (logs.get("why") or "no line since the run started"),
                   "lines": [{"at": p.get("at") or "", "severity": p.get("severity_word") or "",
                              "text": _line_cut(p.get("text"))} for p in kept],
                   "total": len(lines), "left_out": len(lines) - len(kept)})
    source = (f"Mercury's own reads after attempt:{newest.get('n')} ({newest.get('operation')}) "
              f"failed, read now, since the run started at {at}")
    return _section(AFTER_RUN, "ok", "", redact_payload(pieces), source,
                    run=f"attempt:{newest.get('n')}", since=at)


def _line_cut(text) -> str:
    """A syslog line's whitespace collapsed; never cut (the operator, 2026-11-16)."""
    return " ".join(str(text or "").split())


def _collector_log_piece(units: dict, since: float, at: str, fx_reads: dict, DS) -> dict:
    """``after_run:collector_log``: the collector's own journal since *since*, its unit
    measured once per receiver (`diagnose_stream.collector_unit`), one unit read once."""
    base = {"ref": f"{AFTER_RUN}:collector_log",
            "what": f"the collector's own log lines since the run started ({at}), from the "
                    "journal of its systemd service (the service measured from the listener's "
                    "owner on the receiver's port)"}
    if not units:
        return dict(base, state="unread", why="no subscription's receiver is known from intent")
    unit_of = fx_reads.get("unit") or DS.collector_unit
    journal = fx_reads.get("journal") or DS.collector_journal
    found, whys = {}, []
    for (address, port), sub in units.items():
        got = unit_of(address, port)
        if got.get("unit"):
            found.setdefault(got["unit"], sub)
        else:
            whys.append(f"subscription {sub}: {got.get('why')}")
    if not found:
        return dict(base, state="unread", why="; ".join(whys)[:400])
    reads = []
    for unit in sorted(found):
        got = journal(unit, since)
        reads.append({"unit": unit, "state": got.get("state"), "why": got.get("why") or "",
                      "lines": got.get("lines") or [], "total": got.get("total") or 0,
                      "total_is_least": bool(got.get("total_is_least"))})
    state = "read" if any(r["state"] == "read" for r in reads) else (
        "empty" if all(r["state"] == "empty" for r in reads) else "unread")
    return dict(base, state=state, why="; ".join(whys)[:400], units=reads)


def seen_section(network: str, device: str, value: dict = None) -> dict:
    """Seen before, as Mercury's alerts reader stored it for *device* (`seen_before.context`,
    kept in the reader's value as ``streams``): one piece ``seen_before:1``, or the section
    saying why it is not known. *value* is the reader's stored document (tests); by default it
    is read from the store, never searched."""
    source = "Mercury's own records, Seen before (modules/heal/seen_before.py)"
    if value is None:
        from modules import reader_job

        got = reader_job.read_cached_for("grafana-alerts", network)
        if got.get("state") != "ok":
            return _section(SEEN, "unreadable" if got.get("state") == "unreadable" else
                            "absent", got.get("why") or "the alerts reader holds no value yet",
                            source=source)
        value = (got.get("doc") or {}).get("value") or got.get("doc") or {}
    streams = (value or {}).get("streams")
    if not isinstance(streams, dict) or streams.get("state") != "read":
        return _section(SEEN, "absent", "Mercury's records were not searched for this reading "
                        "of the alerts", source=source)
    entry = ((streams.get("devices") or {}).get(device) or {}).get("seen") or {}
    if not entry:
        return _section(SEEN, "absent", f"no lost-stream alert of {device} was searched",
                        source=source)
    state = entry.get("state") or ""
    piece = {"ref": f"{SEEN}:1", "device": device, "state": state,
             "words": entry.get("record") or entry.get("why") or "",
             "from": entry.get("from") or "", "to": entry.get("to") or "",
             "what": entry.get("what") or "", "cause": entry.get("cause") or "",
             "ended": (entry.get("ended") or {}).get("words") or "",
             "held": (entry.get("held") or {}).get("words") or ""}
    return _section(SEEN, "unreadable" if state == "unreadable" else "ok",
                    entry.get("why") or "", [piece], source)


def note_section(note: str) -> dict:
    """The note's own section, for the check alone: ``note:1`` resolves when a note was sent.
    Its words go as the typed part ``note``, never inside the pack."""
    if not " ".join(str(note or "").split()):
        return _section(NOTE, "empty", "the person wrote no note")
    return _section(NOTE, "ok", "", [{"ref": f"{NOTE}:1", "what": "the person's note"}],
                    "the person who pressed, masked")


def fixit_format() -> str:
    """What this incident's own sections are and how each is cited: the same bytes every call."""
    return "\n".join([
        "attempts is each run of a catalog operation on the incident's device during the "
        "incident, read from the operation's own record, in order: its operation and "
        "parameters, its outcome and the run's words, who proposed it and who approved it (each "
        "person a stable label), and when. A piece's reference is attempt:<n>, its place. "
        "passed true means its verify read the fix hold.",
        "seen_before is Mercury's own record of whether this device lost its stream before: the "
        "past incident it matched, how that ended and how long it held, or that none is found. "
        "Its one piece is seen_before:1. Never state a past incident it does not hold.",
        "note is what the person who pressed wrote, masked: cite it as note:1. It is a person's "
        "belief, not a measurement.",
        "run_steps is each failed attempt's own steps, in order, from its run record: each "
        "step's name, its result, its words and the reads it made in one line. A piece's "
        "reference is run_steps:<n>, the attempt's place (attempt:<n>); omitted counts the "
        "steps left out to fit, its earliest passing ones first.",
        "after_run, when the newest attempt failed, is what Mercury read after that run, now: "
        "after_run:collector (the collector's sessions from the device's addresses with bytes "
        "received and sent and the milliseconds since the last receive and send), "
        "after_run:series (whether each subscription has data now), after_run:collector_log "
        "(the collector's own log lines since the run started) and after_run:syslog (the "
        "device's syslog lines since the run started). Each says when it could not be read; "
        "an unread part is not evidence of anything.",
        "ladder, for a lost stream, is Mercury's ladder of repairs, least disruptive first, "
        "never a reload: each rung ladder:<n> names its reset (tried_words), the plan of "
        "Mercury's steps that makes it (steps, empty with why when no step does yet), what its "
        "verify reads and its impact, tried (the failed attempt that already made the same "
        "reset, by equivalence: a re-subscribe, a re-add and a re-subscribe with the collector "
        "step are one reset) and first_untried. Never propose a step whose rung is tried; "
        "propose the first_untried rung's steps as they stand, or, when none is left, say so "
        "as a gap.",
        "mercury_reads may begin with Mercury's standard reads for the incident's problem kind, "
        "run before your first pass (their why says so): then this pass is your first, there is "
        "no previous answer to replace, and they are cited as any read is. They are what this "
        "problem kind needs read (for an err-disabled port: its state and cause, the device's "
        "own recovery, the port's configuration when the configuration class is on, and the "
        "cause's own state), and the plan's preconditions are read again by Mercury: never "
        "ask one of them again, and when they and the pack settle the cause, propose the plan "
        "in this pass with reads empty."])
    # The catalogue is the prompt's to describe (v7 and v8 say it once; the gate's measurement,
    # 2026-11-15: every request's fixed size inside its bound).


def read_set() -> str:
    """The reads pass's context block ``read_set``: what the model may ask Mercury to read (the
    read family's operations and their arguments, `fixit_reads.FAMILY`), the same bytes on
    every call."""
    lines = [
        "read_set is the read-only reads Mercury may run for this investigation, as an engineer "
        "would ask them through Mercury: the device's own (show, show_config, ping, "
        "traceroute: give the command's words after its verb in words, for example "
        "\"interfaces GigabitEthernet1\" for show; Mercury runs a show of one of its command "
        "families, listed below, on a device in scope, through its own reads engine), and "
        "Mercury's own of what it holds about a device in scope (intent, golden, neighbours, "
        "history, logs, metrics; collector_sessions: the collector's side of a subscription's "
        "stream on Mercury's host; stream_series: whether the stream has data now). To ask for "
        "one, add it to reads: op is one of the operations below, args its arguments by name "
        "(device always, and null for an argument the operation does not take), why one line "
        "on what it would show, and hypothesis the hypothesis it tests. Ask for at most 3; ask "
        "for none when the evidence says enough. Mercury checks each request (the allowlist, "
        "each address and interface against the device's golden and intent, the egress "
        "classes) and runs only those it allows; the next message carries the answers, or why "
        "a request was refused. A read Mercury refuses, or one it lacks, is recorded as a "
        "missing capability for people to review: never try to word around a refusal.",
        "The operations:"]
    for op in FR.FAMILY.operations:
        args = ", ".join(f"{a} ({spec.shape.words})" for a, spec in op.args.items())
        lines.append(f"- {op.name}: {op.words}; args: {args}")
    lines.append("show's command families: `show <family> <form>`, each family's forms after "
                 "the colon, - for the family alone ({if} an interface the device's golden "
                 "holds, as one word; {a4} {a6} an address of the network; {p4} {p6} a prefix "
                 "of it; {mask} a netmask after an address; {vlan} {n} numbers; {sub} a "
                 "subscription the incident names; {mac} a MAC; {name} a VRF):")
    for family, tails in RR.SHOW_FAMILIES:
        lines.append(f"- {family}: " + " | ".join(t or "-" for t in tails))
    return "\n".join(lines)


def request(network: str, found: dict, incident, *, note: str = "", now: float = None,
            resolved: float = None, seen: dict = None, loki=None, prometheus=None,
            timings: dict = None) -> dict:
    """`built_request`, or `Refused` with nothing sent when a person in it cannot be labelled
    because no label key is installed (C3458, `display_names.LabelKeyMissing`, the key named):
    a press and its preview alike, and no key is made by either."""
    from modules import display_names

    try:
        return built_request(network, found, incident, note=note, now=now, resolved=resolved,
                             seen=seen, loki=loki, prometheus=prometheus, timings=timings)
    except display_names.LabelKeyMissing as exc:
        raise Refused(f"Not asked: {exc}") from None


def held_words(network: str, incident) -> str:
    """``"; self-healing holds it by guard <n> (<name>): <words>; a person resolves that hold,
    so Mercury cannot fix it alone"`` when R1's failure reader holds a hold a person resolves
    for *incident* (`fixit.auto.failures`, ``held``: C3732, the operator, 2026-11-15: "where
    the fix needs a person's approval (a template bring-in), it says so as its finding and
    offers Hand over"), the newest; else ``""``. The AI is told the hold and its guard, so its
    finding can say the fix needs a person; its catalogue and its NEVERs are unchanged."""
    from modules.fixit import auto as A

    try:
        got = A.failures(network, open_ids={incident.id})
    except Exception as exc:                                    # noqa: BLE001 (said in the log)
        log.warning("fixit troubleshoot: %s's hold could not be read: %s", incident.id, exc)
        return ""
    held = [f for f in got["failures"] if f["kind"] == "held"]
    if not held:
        return ""
    g = held[-1].get("guard") or {}
    return (f"; self-healing holds it by guard {g.get('guard')} ({g.get('name') or 'a guard'})"
            f": {' '.join(str(g.get('words') or '').split())}; a person resolves that hold, so "
            "Mercury cannot fix it alone")


def built_request(network: str, found: dict, incident, *, note: str = "", now: float = None,
                  resolved: float = None, seen: dict = None, loki=None,
                  prometheus=None, timings: dict = None) -> dict:
    """The investigation's request for the incident `incident_page.resolve` *found* (its
    `fixit.incident.Incident`, *incident*), before any call: ``{"pack", "topo", "sections",
    "checked_sections", "data", "ctx", "subject", "actable", "said"}``. *sections* are what is
    sent of the pack, *checked_sections* those plus this incident's own (what an answer's
    references resolve against). Raises `Refused` for a network whose marking forces AI off.
    Reads Mercury's stores and the monitoring the pack reads; calls no model. *timings*, when
    given, gets each part's seconds (``pack:<source>`` each of the pack's own sources, read at
    once, `evidence_pack.build_incident`), for the investigation's record."""
    import time

    from modules import evidence_pack as EP
    from modules.ai import egress_classes, explain
    from modules.fixit import payload

    timings = timings if timings is not None else {}
    t0 = [time.monotonic()]

    def part(name):
        now_ = time.monotonic()
        timings[name] = round(now_ - t0[0], 2)
        t0[0] = now_

    marked = egress_classes.classification_marking(network)
    if marked:
        raise Refused(f"{network} carries the classification marking {marked!r}, which forces "
                      "AI off: nothing was sent")
    entry = found.get("entry") or {}
    units = [u for d in found.get("decisions") or [] for u in d.get("units") or []]
    # What this problem kind's pack leaves unread, and whether its topology is sent (`KIND_PACK`).
    trim = KIND_PACK.get(problem_condition(found)) or {}
    sources = {}
    pack = EP.build_incident(network, found.get("incident") or {}, entry, units,
                             now=float(entry.get("epoch") or 0) or now, loki=loki,
                             prometheus=prometheus, skip=trim.get("skip"), timings=sources)
    part("pack")
    timings.update({f"pack:{k}": v for k, v in sources.items()})
    topo = (explain.topology(pack) if not trim.get("topology") else {
        "sent": False, "why": trim["topology"], "summary": "", "yaml": "", "ids": [],
        "reached": {}, "version": "", "subject": incident.device, "network": network,
        "observed": "", "names": {}, "as_now": ""})
    sections = explain.sent_sections(pack, topo)
    part("topology")
    tried = payload.tried_parts(incident, resolved, now=now)
    own = [attempts_section(incident, resolved, now=now, got=tried)]
    part("attempts")
    own.append(seen_section(network, incident.device, seen))
    part("seen_before")
    own.append(run_steps_section(incident, tried))
    # The state after a failed run, when the newest attempt failed (the operator, 2026-11-16:
    # R1's re-investigation a failed run starts, and a person's after it).
    after = after_run_section(network, incident, tried.get("newest_failed"), now=now, loki=loki)
    if after is not None:
        own.append(after)
    # The ladder (the operator, 2026-11-16): what counts as tried by equivalence, and the first
    # untried rung, from the same attempts as sent.
    from modules.fixit import ladder
    tried_as = ladder.tried(failed_of(tried))
    rungs = ladder.rungs(incident, tried_as)
    lad = ladder.section(incident, tried_as)
    if lad is not None:
        own.append(lad)
    part("run_steps, after_run and the ladder")
    checked = list(sections) + own + [note_section(note)]
    data = {"pack": json.dumps([explain.as_sent(s) for s in sections] + own, sort_keys=True,
                               ensure_ascii=False, separators=(",", ":")),
            "note": " ".join(str(note or "").split()),
            "the_incident": (f"{incident.id} on {incident.device}: "
                             + (f"telemetry subscription(s) {', '.join(incident.subscriptions)}"
                                " lost" if incident.subscriptions else "no subscription named")
                             + held_words(network, incident)
                             + "; it stands open, and a person asked you to troubleshoot it")}
    if topo.get("yaml"):
        data["network_topology"] = topo["yaml"]
    elif trim.get("topology"):
        data["network_topology"] = trim["topology"]
    ctx = {"pack_format": explain.vocabulary(PACK_SECTIONS), "fixit_format": fixit_format(),
           # Only the steps this incident's device can take (`payload.catalogue_part`).
           "catalogue": json.dumps(payload.catalogue_part(incident, problem_condition(found)),
                                   sort_keys=True, ensure_ascii=False, separators=(",", ":"))}
    # The topology's format in every request (v17): fixed text, so the cached prefix is the same
    # bytes whether this incident's topology is sent or not; the network's summary is the
    # incident's own (`gateway.PER_REQUEST_CONTEXT`), after it.
    from modules import network_model as NM
    ctx["topology_format"] = NM.FORMAT
    if topo.get("sent"):
        ctx["network"] = topo["summary"]
    said = {"sent": topo.get("sent"), "why": topo.get("why"), "devices": sorted(
        topo.get("reached") or ())}
    prep = {"pack": pack, "topo": topo, "sections": sections, "checked_sections": checked,
            "data": data, "ctx": ctx, "said": said,
            "subject": {"kind": "heal_incident", "id": incident.id,
                        "devices": [incident.device] if incident.device else []},
            "actable": [incident.device, *incident.subscriptions],
            "own": own, "note_part": note_section(note),
            # Plain data the answer check reads (`loop_feature`): the failed attempts by their
            # equivalence class, and the ladder's rungs.
            "tried_as": tried_as, "ladder": rungs}
    part("held, the catalogue and the contexts")
    got = fit(prep)
    part("the fit")
    return got


# ── The request's size (the host's preview of a standing incident, 2026-11-14) ────────────────
#
# Measured on the host, 2026-11-14 10:3x UTC (`nmas-fixit-cases --preview` of a router's standing
# incident, no provider request): pass 1's masked body was 64,847 characters and pass 2's 64,191,
# 36,051 and 35,688 tokens by the fallback estimate (`gateway.CHARS_PER_TOKEN`, 1.8, an
# over-estimate), against the task's bound of 27,000. The system text was 23.7K (the prompt
# 6.2K; the contexts 17.5K, the read set 7.6K of it), the pack 19.9K (its logs 4.4K, neighbours
# 3.8K, history 3.2K, observer 2.7K, health 2.6K), the topology 13.9K, the schema 4.0K; pass 2's
# reads only 1.1K. A press asks the provider's count first (`gateway.Counter`) and is refused
# (`prompt_too_long`, nothing sent) when it is over the bound, or when the count is not had and
# the fallback is. So the request is fitted before it is asked (`fit`), never by raising the
# bound on a guess: the read set is sent compactly and only to pass 1 (pass 2 cannot ask), and,
# while pass 1 with room for pass 2's reads is over the bound by the fallback estimate, the
# topology is left out (the investigation reads only the incident's device, C3685), then the
# pack's largest trimmable sections are cut to half their pieces, each cut said in the section.

#: Since the operator's 2026-11-16 decision (no size bound of Mercury's own; a read's answer is
#: sent whole) there is no reserve for later passes' reads (``reads_reserve_chars``,
#: ``READS_ADDED_CHARS`` and ``READS_ROOM_CHARS`` are gone): pass 1 is fitted to the room the
#: context window leaves (`fit`, `profiles.prompt_room`), and later passes' reads share what it
#: leaves after pass 1 (`read_room`; once counted, `read_loop.counted_room`).
#: How much longer one pass's words (`read_loop.PASS_WORDS`) may be than another's, in the
#: request's characters: a later pass may carry the longest where pass 1 carried the shortest.
PASS_SLACK_CHARS = (max(len(json.dumps(w)) for w in RL.PASS_WORDS.values())
                    - min(len(json.dumps(w)) for w in RL.PASS_WORDS.values()))
#: What a pass carrying reads holds once beside their part, whatever their number, in the
#: request's characters: the part's wrapper and the pass's words' slack. With v17's one shape
#: the reads' format is in every pass's context already (`shared_context`), pass 1's too.
READS_OVERHEAD_CHARS = len(json.dumps('\n<data name="mercury_reads">\n\n</data>')) \
    + PASS_SLACK_CHARS
def _room_of(prep: dict):
    """*prep*'s room for reads (`read_room`), measured once, when the press or the preview builds
    its feature after the fit, and kept on it: measuring builds pass 1's request
    (`request_chars`), which builds this feature again, so while a request is being sized (and
    for a request with no pack built) no room is declared (None: nothing cut; the gateway's
    count against the context window decides), never measured (a press of 2026-11-15 20:41 UTC
    recursed here for minutes before its first call)."""
    if "read_room" in prep:
        return prep["read_room"]
    if "sections" not in prep or prep.get("_measuring_room"):
        return None
    prep["_measuring_room"] = True
    try:
        prep["read_room"] = read_room(prep)
    finally:
        prep.pop("_measuring_room", None)
    return prep["read_room"]


def read_room(prep: dict):
    """The room every pass of this investigation may fill with reads (C3797), in the request's
    characters as `read_loop._sent_chars` counts them: what the context window leaves for a
    prompt (`profiles.prompt_room`, less the count's margin, `read_loop.margin_tokens`) after
    pass 1 as built, by the fallback estimate (`gateway.CHARS_PER_TOKEN`: fewer characters a
    token than any recorded call, so the room is never over the real one; the provider's count
    replaces it once pass 1 is counted, `read_loop.counted_room`), less the reads' wrapper.
    None when pass 1 cannot be built (no room declared). 0 or less is no room: a later read is
    then cut to nothing and the loop stops without paying for a pass (A's fix: no sentinel
    room of 1). Its reads share it: past it the newest answers are cut, said
    (`read_loop._within_room`)."""
    from modules.ai import profiles

    try:
        chars = request_chars(prep)
    except Exception:                               # noqa: BLE001 (no room declared instead)
        chars = 0
    if not chars:
        return None
    bound = int(profiles.prompt_room(FEATURE))
    allowed = int((bound - RL.margin_tokens(bound) - 1) * gateway.CHARS_PER_TOKEN)
    return allowed - chars - READS_OVERHEAD_CHARS
#: The pack's sections a fit may cut, in no order (the largest is cut first): never the
#: incident, the device, what Mercury tried, the diagnosis, the attempts or Seen before.
TRIMMABLE = ("logs", "neighbours", "history", "observer", "health")
#: Each trimmable section is halved at most this many times (to an eighth of its pieces: with
#: the measured reserve, the host's measured incident's sizes need a third halving of their
#: largest section).
MOST_HALVINGS = 3
#: The topology's words when a fit leaves it out (the prompt: "Its absence is not evidence").
TOPOLOGY_LEFT_OUT = ("not sent: with it the request would be over its bound; this "
                     "investigation reads only the incident's device")


def _first_parts(prep: dict) -> tuple:
    """Pass 1's ``(prompt, schema, parts, context)`` for *prep*, as the press asks it."""
    # Pass 1's body never depends on the room for reads, so it is built without measuring it
    # (`_room_of`): measuring is `request_chars`, and a fit asks it while the pack still moves.
    measuring = prep.get("_measuring_room")
    prep["_measuring_room"] = True
    try:
        feature = loop_feature(prep)
    finally:
        if measuring:
            prep["_measuring_room"] = measuring
        else:
            prep.pop("_measuring_room", None)
    return RL.first_request(feature, prep["data"], prep["ctx"], reads_context(), plain=False)


def _raw_chars(prep: dict) -> int:
    """What of pass 1's body moves while a request is fitted, unmasked, in the body's
    characters: its data turn and its context blocks as `gateway.build_request` delimits them,
    each encoded as the body encodes it. The prompt, the schema and the pin do not move."""
    _prompt, _schema, parts, ctx = _first_parts(prep)
    return (len(json.dumps(gateway._delimited("data", parts), ensure_ascii=False))
            + len(json.dumps(gateway._delimited("context", ctx), ensure_ascii=False)))


def request_chars(prep: dict) -> int:
    """Pass 1's masked request body in characters, or 0 when it is refused before it is built
    (a stored secret, no label key: the press is refused for that, never for its size).

    **Measured once, then local** (the operator, 2026-11-16: "the fit (5.8 s) ... make it local
    and fast ... never a round trip per request"): the first ask builds the body as the gateway
    does (`gateway.request_body`, the press's own builder, the mask and all; no provider
    request) and keeps its size beside the unmasked size of what moves (`_raw_chars`); every
    later ask, while the fit cuts and when the room for reads is measured, is that size moved
    by the unmasked difference, plus a margin: what the mask shortened the whole request by
    (it can shorten what a cut removes at most that much), so the estimate is never under the
    masked body it stands for. Building and masking the body again for each cut is what it
    replaces."""
    from modules.ai import triggers

    sized = prep.get("_sized")
    if sized is not None:
        masked, raw, margin = sized
        return max(0, masked + (_raw_chars(prep) - raw) + margin)
    prompt, schema, parts, ctx = _first_parts(prep)
    got = gateway.request_body(FEATURE, prompt, schema, parts, context=ctx or None,
                               kind=triggers.PERSON)
    if "refused" in got:
        return 0
    masked = len(json.dumps(got["body"], ensure_ascii=False))
    try:
        # The same body unmasked (the prompt's text as sent: it holds nothing masked).
        body_raw = gateway.build_request(
            {"text": got["body"]["system"][0]["text"]}, schema, parts, got["pin"],
            context=ctx or None, profile=got["profile"], cache=True,
            volatile=gateway.PER_REQUEST_CONTEXT.get(FEATURE, ()))
    except Exception:                       # noqa: BLE001 (then built and masked every time)
        return masked
    prep["_sized"] = (masked, _raw_chars(prep),
                      max(0, len(json.dumps(body_raw, ensure_ascii=False)) - masked))
    return masked


def refit_first(prep: dict, cut_chars: int):
    """The loop's pass-1 refit hook (`read_loop.LoopFeature.refit_first`, A's fix, C3890): for
    a pass 1 the gateway refused over the context window, *cut_chars* more of its characters
    cut by the fit's own steps (`fit`), and ``(data, context, words)`` for the loop to ask it
    again with; None when nothing more could be cut. Nothing was sent, so nothing was spent."""
    start = request_chars(prep)
    fit(prep, cut_chars=cut_chars)
    if request_chars(prep) >= start:
        return None
    prep.pop("read_room", None)                    # pass 1 moved: its room is measured again
    return prep["data"], prep["ctx"], f"evidence trimmed by {start - request_chars(prep):,} " \
                                      "characters to fit the context window"


def _over(prep: dict, bound: int) -> bool:
    """Whether pass 1 is over *bound* (the room the context window leaves for a prompt,
    `profiles.prompt_room`) by the fallback over-estimate. A later pass's reads are held to
    the room pass 1 leaves inside it (`read_room`, C3797); no reserve for them is kept (a read
    is sent whole)."""
    chars = request_chars(prep)
    return bool(chars) and gateway.tokens_of_chars(chars) > bound


def _repack(prep: dict) -> None:
    from modules.ai import explain

    prep["data"]["pack"] = json.dumps([explain.as_sent(s) for s in prep["sections"]]
                                      + prep["own"], sort_keys=True, ensure_ascii=False,
                                      separators=(",", ":"))
    prep["checked_sections"] = list(prep["sections"]) + prep["own"] + [prep["note_part"]]


def fit(prep: dict, bound: int = None, *, cut_chars: int = 0) -> dict:
    """*prep* fitted to the only size bound, the room the model's context window leaves for a
    prompt (`profiles.prompt_room`; the operator, 2026-11-16: per-task prompt limits are gone),
    less the fit's safety margin (`read_loop.margin_tokens`, C3890), by the fallback
    over-estimate (`_over`): unchanged when it fits; else the topology left out
    (said in its part, and nothing of it citable), then the largest trimmable section halved,
    again, each cut said in the section (``cut``), until it fits or nothing is left to cut.
    What was done is ``said["fit"]``, in order; the request is asked either way (the provider's
    count decides, `gateway.ask`).

    *cut_chars* (a pass 1 refused over the context window, `refit_first`): cut that many more
    of pass 1's characters (`request_chars`) by the same steps, in the same order, after the
    fit's own, its steps added to ``said["fit"]``; a section is halved at most `MOST_HALVINGS`
    times in all."""
    from modules.ai import explain, profiles

    bound = int(bound or profiles.prompt_room(FEATURE))
    bound -= RL.margin_tokens(bound)
    halved = prep.setdefault("_halved", {})
    if cut_chars:
        steps = prep["said"].setdefault("fit", [])
        target = request_chars(prep) - int(cut_chars)

        def over():
            return request_chars(prep) > target
    else:
        steps = []
        prep["said"]["fit"] = steps

        def over():
            return _over(prep, bound)
    if not bound or not over():
        return prep
    if prep["topo"].get("sent"):
        prep["topo"] = dict(prep["topo"], sent=False, why=TOPOLOGY_LEFT_OUT, ids=[],
                            reached={}, yaml="", names={})
        prep["data"]["network_topology"] = TOPOLOGY_LEFT_OUT
        # The network's summary goes; the topology's format stays, fixed text in the cached
        # prefix (v17).
        prep["ctx"].pop("network", None)
        prep["sections"] = explain.sent_sections(prep["pack"], prep["topo"])
        prep["said"].update(sent=False, why=TOPOLOGY_LEFT_OUT, devices=[])
        _repack(prep)
        steps.append("the topology left out")
    while over():
        cuttable = [(len(json.dumps(s)), i) for i, s in enumerate(prep["sections"])
                    if s.get("name") in TRIMMABLE and len(s.get("pieces") or []) > 1
                    and halved.get(s.get("name"), 0) < MOST_HALVINGS]
        if not cuttable:
            steps.append("still over the bound by the fallback estimate: the provider's count "
                         "decides" if not cut_chars else
                         "nothing more of pass 1's evidence to cut")
            break
        _size, i = max(cuttable)
        s = prep["sections"][i]
        pieces = list(s.get("pieces") or [])
        total = s.get("cut_of") or len(pieces)
        kept, which = halve(pieces, prep["pack"].get("onset") or "")
        prep["sections"][i] = dict(s, pieces=kept, cut_of=total,
                                   cut=f"{len(kept)} of its {total} pieces sent, {which}, to "
                                       "fit the request's bound")
        halved[s.get("name")] = halved.get(s.get("name"), 0) + 1
        _repack(prep)
        steps.append(f"{s.get('name')} cut to {len(kept)} of {total} pieces, {which}")
    return prep


def _epoch(text) -> float:
    from datetime import datetime

    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def halve(pieces: list, onset: str) -> tuple:
    """``(kept, which)``: half of *pieces* (at least one), in their own order, and which half
    in words. When every piece has a time (``at``) and the pack an onset, the half nearest the
    onset (a log section holds the lines nearest it, sorted by time: the review of the fit,
    2026-11-14); else the first half, said."""
    k = max(1, len(pieces) // 2)
    at = _epoch(onset)
    times = [_epoch(p.get("at")) if isinstance(p, dict) else None for p in pieces]
    if at is not None and pieces and all(t is not None for t in times):
        nearest = sorted(range(len(pieces)), key=lambda i: (abs(times[i] - at), i))[:k]
        return [pieces[i] for i in sorted(nearest)], "those nearest the onset"
    return pieces[:k], "the first in its order"


# ── The check ───────────────────────────────────────────────────────────────────────────────

def as_door(fix) -> dict:
    """A checked answer's fix as the one door takes it: exactly ``{"operation", "params"}``,
    the parameters the answer gave (a null is a parameter not given)."""
    params = {k: v for k, v in fix.params.model_dump(mode="json").items() if v is not None}
    return {"operation": fix.operation, "params": params}


def acts_on(answer) -> list:
    """Every value a fix acts on: its device and each subscription it names (`read_loop`'s
    actable rule holds them to the incident's own)."""
    out = []
    for step in _steps_of(answer, improvement=True):
        p = step.params
        out += [p.device, *(p.subscriptions or []),
                *([p.subscription] if p.subscription else [])]
    return out


def _steps_of(answer, *, improvement: bool = False) -> list:
    """The answer's fix as its steps: its plan's (v7), or its one fix as a plan of one; with
    *improvement*, the improvement's shorter route's steps too."""
    fix = getattr(answer, "fix", None)
    steps = list(getattr(answer, "plan", None) or []) or ([fix] if fix is not None else [])
    imp = getattr(answer, "improvement", None)
    if improvement and imp is not None:
        steps += list(imp.steps)
    return steps


def cites(answer) -> list:
    """Every reference an answer makes: each hypothesis's, the fix's (each plan step's) and the
    gap's."""
    out = [r for h in getattr(answer, "hypotheses", None) or [] for r in h.evidence_refs]
    for part in _steps_of(answer, improvement=True) + [getattr(answer, "gap", None)]:
        if part is not None:
            out += list(part.evidence_refs)
    return out


def _unresolved(refs, sections) -> str:
    from modules import evidence_pack as EP

    sent = {"sections": list(sections)}
    for ref in refs:
        if EP.resolve(sent, ref) is None:
            return ref
    return ""


# ── Unverified citations (the operator, 2026-11-15) ─────────────────────────────────────────
#
# "Never discard a whole answer for a bad citation: mark that claim 'unverified (cites X, not
# in the evidence)' and still show the rest. Then retry once automatically, telling the AI which
# citation failed, within the incident cap." A citation that resolves to nothing sent is no
# reason to refuse the answer (`check`'s *unverified*): each hypothesis, the fix, the gap and
# each step resting on one is kept, marked in words naming it (`unverified_words`), and the
# investigation asks once more, naming them (`RETRY_PART`), when the incident's cap leaves room
# for one more call; a step resting ONLY on unverified citations is never approvable (the
# page's preflight, `fixit.plan.preflight`, refuses it by the kept marks).

#: The part a retry adds, naming the citations Mercury's check could not find (Mercury's own
#: words, a fact about the answer, never an instruction: the prompt says what data is).
RETRY_PART = "citation_check"


def _listed(refs) -> str:
    refs = list(refs)
    return refs[0] if len(refs) == 1 else ", ".join(refs[:-1]) + " and " + refs[-1]


def _cites_said(refs) -> str:
    """What a part's marks say it cites, in words (`unverified_words`, `retry_words`): each
    citation not in what was sent, "nothing" for a part citing nothing (`explain.UNCITED`), and
    each device it names without citing it (`explain.uncited_mark`)."""
    from modules.ai import explain

    refs = list(dict.fromkeys(refs or ()))
    real = [r for r in refs if not explain.is_mark(r)]
    devices = [explain.marked_device(r) for r in refs if explain.marked_device(r)]
    said = []
    if real:
        said.append(f"cites {_listed(real)}, not in the evidence")
    if explain.UNCITED in refs:
        said.append("cites nothing in the evidence")
    if devices:
        said.append(f"names {_listed(devices)} without citing "
                    f"{'it' if len(devices) == 1 else 'them'}")
    return "; ".join(said)


def unverified_words(refs) -> str:
    """How a claim, a hypothesis or a step resting on *refs* (citations not in what was sent,
    and the marks of a missing citation, `explain.UNCITED` and `explain.uncited_mark`) is
    marked: ``unverified (cites history:3, not in the evidence)``, ``unverified (cites nothing
    in the evidence)``."""
    return f"unverified ({_cites_said(refs)})"


def _parts(answer) -> list:
    """``[(name, part)]``: the answer's fix, gap, plan steps and improvement steps by the names
    `check` gives them (a part None left out)."""
    plan = list(getattr(answer, "plan", None) or [])
    imp = getattr(answer, "improvement", None)
    out = [("fix", getattr(answer, "fix", None)), ("gap", getattr(answer, "gap", None))]
    out += [(f"plan's step {n}", s) for n, s in enumerate(plan, 1)]
    out += [(f"improvement's step {n}", s) for n, s in enumerate((imp.steps if imp else []), 1)]
    return [(name, p) for name, p in out if p is not None]


def unverified(answer, sections: list, topo: dict, pack: dict = None) -> dict:
    """``{part: [citation, ...]}``: each citation of *answer* that resolves to nothing sent
    (*sections*, this incident's own and the reads that ran among them) nor to the topology
    sent, by the part citing it (``hypothesis <i>``, ``fix``, ``gap``, ``plan's step <n>``,
    ``improvement's step <n>``); ``{}`` when every one resolves. A hypothesis's citations are
    read as Explain's check reads them (`explain.normalised`).

    A MISSING citation is marked too (the operator, 2026-11-16: a router's pass 2 was discarded
    whole for "hypothesis 2 cites nothing in the pack"): a part citing nothing is marked
    `explain.UNCITED`, and, with *pack*, each device the answer names and cites nowhere (as
    Explain's check finds them, Mercury's own citations of it added first, `mercury_cites`)
    is marked `explain.uncited_mark` on the part naming it (``hypothesis <i>`` or ``the
    rationale``, `explain._named_in`)."""
    from modules import evidence_pack as EP
    from modules.ai import explain

    ids = set(topo["ids"] if topo.get("sent") else ())
    sent = {"sections": list(sections)}
    normal, _written = explain.normalised(answer, sent, tuple(ids))

    def bad(refs):
        if not refs:
            return [explain.UNCITED]
        return [r for r in dict.fromkeys(refs) if EP.resolve(sent, r) is None and r not in ids]

    out = {}
    for i, h in enumerate(normal.hypotheses, 1):
        if bad(h.evidence_refs):
            out[f"hypothesis {i}"] = bad(h.evidence_refs)
    for name, part in _parts(answer):
        if bad(part.evidence_refs):
            out[name] = bad(part.evidence_refs)
    if pack is not None and normal.outcome.value != "refuse":
        names = explain.sent_names(topo.get("names") if topo.get("sent") else None,
                                   tuple(ids))
        own = pack.get("device") or ""
        added = [a["ref"] for a in explain.mercury_cites(normal, sent, names, own)]
        for name in explain.uncited_devices(normal, sent, names, own, added):
            out.setdefault(explain._named_in(normal, name), []).append(
                explain.uncited_mark(name))
    return out


def _flat(marks: dict) -> list:
    return sorted({r for refs in (marks or {}).values() for r in refs})


def retry_words(marks: dict) -> str:
    """What a retry tells the model (`RETRY_PART`): Mercury's check of its previous answer,
    each citation it could not find, each part citing nothing and each device named without a
    citation, by the part that made it."""
    return ("Mercury's check of the previous answer to this request marked these parts "
            "unverified, because a reference they cite is not in what was sent, they cite "
            f"nothing, or they name a device without citing it: {_marks_said(marks)}. Every "
            "hypothesis, fix, gap and step cites what was sent. The references sent are the "
            "pack's, this incident's own sections', the note's and the reads' that ran, exactly "
            "as written in them.")


def _marks_said(marks: dict) -> str:
    """*marks* (`unverified`'s) in words, part by part: ``hypothesis 2 cites nothing in the
    evidence; plan's step 1 cites history:9, not in the evidence``."""
    return "; ".join(f"{part} {_cites_said(refs)}" for part, refs in (marks or {}).items())


def check(answer, pack: dict, sections: list, topo: dict, unverified=()) -> str:
    """"" when *answer* stands against what was sent (*sections*, this incident's own among
    them), else why not, the first that does not (the module's docstring): Explain's check of
    the hypotheses; a fix and a gap not both; the fix's and the gap's references resolved; the
    fix held to the catalog's schema. The actable rule is the read loop's (`acts_on`). A
    citation in *unverified* (`unverified`'s, marked by the caller) is no reason to refuse."""
    unv = set(unverified or ())
    # Explain's validation of an answer against what was sent (no call to the model), named
    # apart from the gateway's own entries, which tests/test_ai_triggers.py reads by name.
    from modules.ai.explain import check as explain_answer_check

    from modules.ai import explain

    ids = topo["ids"] if topo.get("sent") else ()
    names = topo.get("names") if topo.get("sent") else None
    sent = {"sections": list(sections)}
    # Explain's normalising and Mercury's own citations of a device the answer names (the
    # heal analysis's check, `explain.normalised`, `explain.mercury_cites`).
    normal, _written = explain.normalised(answer, sent, ids)
    added = explain.mercury_cites(normal, sent, explain.sent_names(names, ids),
                                  pack.get("device") or "")
    why = explain_answer_check(normal, pack, ids, sections=sections, names=names,
                               added=[a["ref"] for a in added], unverified=unv)
    if why:
        return why
    if len(answer.hypotheses) > MAX_HYPOTHESES:
        return f"{len(answer.hypotheses)} hypotheses; at most {MAX_HYPOTHESES} are taken"
    plan = list(getattr(answer, "plan", None) or [])
    imp = getattr(answer, "improvement", None)
    if answer.outcome.value == "refuse":
        if answer.fix is not None or answer.gap is not None or plan or imp is not None:
            return "the answer says the evidence cannot say, and still names a fix or a gap"
        return ""
    if answer.fix is not None and answer.gap is not None:
        return ("the answer names both a fix and a gap: a fix is one catalog operation, and a "
                "gap is what no catalog operation does, never both")
    if plan and (answer.fix is not None or answer.gap is not None):
        return ("the answer names a plan and also a " + ("fix" if answer.fix is not None
                                                         else "gap")
                + ": a plan is the fix, and a gap is what nothing within Mercury's policy can "
                  "do, never both")
    if imp is not None and not plan:
        return ("the answer gives an improvement note and no plan: an improvement is beside a "
                "plan that works")
    parts = [("fix", answer.fix), ("gap", answer.gap)] + [
        (f"plan's step {n}", s) for n, s in enumerate(plan, 1)] + [
        (f"improvement's step {n}", s) for n, s in enumerate((imp.steps if imp else []), 1)]
    for name, part in parts:
        if part is None:
            continue
        if not part.evidence_refs:
            if explain.UNCITED in unv:
                continue                # kept, marked unverified (`unverified`, 2026-11-16)
            return f"the {name} cites nothing that was sent"
        ref = _unresolved([r for r in part.evidence_refs if r not in unv], sections)
        if ref and ref not in set(ids or ()):
            return f"the {name} cites {ref[:40]!r}, which is not in what was sent"
    from modules.ai import fix_proposal

    if answer.fix is not None:
        why = fix_proposal.held(as_door(answer.fix))
        if why:
            return f"the fix is not one catalog operation with its parameters: {why}"
    for name, part in parts[2:]:
        why = fix_proposal.step_held(as_door(part))
        if why:
            return f"the {name} is not one of Mercury's steps with its parameters: {why}"
    if len(plan) > fix_proposal.most_steps():
        return f"the plan has {len(plan)} steps; at most {fix_proposal.most_steps()} are taken"
    return ""


# ── The investigation ───────────────────────────────────────────────────────────────────────

def _scope(network: str, incident, actor: str, collector=None, series=None) -> dict:
    """What the read family's comparisons read (`fixit_reads.scope_for`): the incident's device
    and subscriptions alone, the reads recorded as the press's."""
    return FR.scope_for(network, incident, actor=actor, collector=collector, series=series)


def problem_condition(found) -> str:
    """The incident's problem condition (`problem.classify`), or ``""`` when it cannot be
    told: what a gap wanted, so it restarts once a step that fixes it exists (C3733)."""
    from modules import problem

    try:
        return str(problem.classify(found).condition or "") if found else ""
    except Exception as exc:                          # noqa: BLE001 (no condition, said)
        log.info("fixit troubleshoot: the problem could not be classified: %s", exc)
        return ""


def record_missing(got: dict, incident, network: str, found=None, overlooked=()) -> dict:
    """What the investigation wanted that Mercury lacks, recorded for review (C3663,
    `modules/ai/missing.py`): each read it asked for that Mercury lacks, and its gap, with its
    incident's problem condition (*found*'s) so the gap restarts once a step that fixes it
    exists (C3733), and, when Mercury has steps for that problem not yet tried in it
    (*overlooked*, `overlooked_steps`), those steps on the gap's row (``overlooked``), so a
    reviewer reads it as a plan the AI did not compose, not a capability Mercury lacks. A store
    that cannot be written is logged and the answer stands."""
    from modules.ai import missing

    try:
        rows = missing.wanted(got.get("answer"), got.get("reads") or [], feature=FEATURE,
                              network=network, about=("incident", incident.id),
                              condition=problem_condition(found))
        if overlooked:
            rows = [dict(r, overlooked=list(overlooked)) if r.get("kind") ==
                    missing.KIND_OPERATION else r for r in rows]
        return missing.record(rows)
    except Exception as exc:                          # noqa: BLE001 (the answer stands)
        log.error("fixit troubleshoot: %s's missing capabilities were not recorded: %s",
                  getattr(incident, "id", "?"), exc)
        return {"ok": False, "recorded": 0, "error": f"not recorded ({type(exc).__name__})"}


def reads_said(got: dict) -> dict:
    """What the loop did with reads, in Mercury's words: how many were asked for, run,
    refused and failed, each refused or failed one's reason, and the send log's id."""
    recs = got.get("reads") or []
    return {"words": got.get("words") or "", "asked": len(recs),
            **{v: sum(1 for r in recs if r.get("verdict") == v)
               for v in ("run", "refused", "failed")},
            "reasons": [f"{r.get('id')} {r.get('op') or '?'}: {r.get('reason') or ''}"
                        for r in recs if r.get("verdict") in ("refused", "failed")][:6],
            "loop": got.get("loop") or ""}


def _cut(text) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= SHOWN_CHARS else text[:SHOWN_CHARS - 1] + "…"


def _marked(refs, marks_of_part) -> dict:
    """A part's citations and its unverified mark (`unverified_words`): ``{"cites",
    "unverified_words", "only_unverified"}``, the last True when every citation it makes is
    unverified."""
    from modules.ai import explain

    cited = list(dict.fromkeys(refs))
    marks = list(marks_of_part or ())
    bad = [r for r in cited if r in set(marks)]
    # A missing citation's marks (`explain.UNCITED`, `explain.uncited_mark`) are said too; a
    # part citing nothing rests on nothing sent, so it is unverified only (never approvable).
    said = bad + [m for m in marks if explain.is_mark(m)]
    return {"cites": cited[:8], "unverified_words": unverified_words(said) if said else "",
            "only_unverified": (bool(cited) and len(bad) == len(cited))
            or (not cited and explain.UNCITED in marks)}


def shown(answer, said: dict = None, pass_: int = 1, fit=(), marks: dict = None,
          retry: dict = None) -> dict:
    """What the section draws of a checked answer: the rationale, each hypothesis's claim, what
    it cites and its next step (its confirming read), each step of the fix with its why and
    what it cites, the gap's what, and what the reads did; each part resting on a citation not
    in what was sent marked in words naming it (*marks*, `unverified`), and what the retry did
    (*retry*, ``{"asked", "words"}``). Kept with the proposal line (masked at rest)."""
    marks = dict(marks or {})
    hyps = []
    for i, h in enumerate(answer.hypotheses[:MAX_HYPOTHESES], 1):
        m = _marked(h.evidence_refs, marks.get(f"hypothesis {i}"))
        hyps.append({"claim": _cut(h.claim), "cites": list(h.evidence_refs)[:8],
                     "unverified_words": m["unverified_words"],
                     "confirm": _cut(h.confirm_with)})
    out = {"rationale": _cut(answer.rationale), "needs_human": bool(answer.needs_human),
           "hypotheses": hyps, "passes": pass_}
    if marks.get("the rationale"):
        # A device the rationale names and nothing cites (`unverified`, 2026-11-16).
        out["rationale_unverified_words"] = unverified_words(marks["the rationale"])
    # The read the AI lacked (C3797): what "How to fix it" offers a person to run.
    lacked = " ".join(str(getattr(answer, "lacked_read", "") or "").split())
    if lacked:
        out["lacked_read"] = _cut(lacked)
    plan = list(getattr(answer, "plan", None) or [])
    # The fix's steps, each with its why, its citations and its mark: the page's preflight
    # refuses a step resting only on unverified citations by these (`fixit.plan.preflight`).
    named = ([(f"plan's step {n}", s) for n, s in enumerate(plan, 1)] if plan else
             [("fix", answer.fix)] if answer.fix is not None else [])
    if named:
        out["steps"] = [dict(_marked(s.evidence_refs, marks.get(name)), n=n,
                             operation=s.operation, why=_cut(s.why))
                        for n, (name, s) in enumerate(named, 1)]
    if retry:
        out["retry"] = {"asked": bool(retry.get("asked")), "words": _cut(retry.get("words"))}
    if answer.fix is not None:
        out["why"] = _cut(answer.fix.why)
        out["cites"] = list(answer.fix.evidence_refs)[:8]
    if plan:
        out["why"] = _cut("; ".join(s.why for s in plan))
        out["cites"] = list(dict.fromkeys(r for s in plan for r in s.evidence_refs))[:8]
    imp = getattr(answer, "improvement", None)
    if imp is not None:
        out["improvement"] = {"what": _cut(imp.what), "saves": _cut(imp.saves)}
    if answer.gap is not None:
        out["gap"] = _cut(answer.gap.what)
        out["cites"] = list(answer.gap.evidence_refs)[:8]
        out["gap_unverified_words"] = (unverified_words(marks["gap"]) if marks.get("gap")
                                       else "")
    if said and said.get("asked"):
        out["reads"] = _cut(said.get("words"))
    if fit:
        # What `fit` left out or cut to bring the request inside its bound, said where the
        # section draws the call's line (beside what the reads did), and kept with the line.
        out["fit"] = list(fit)
        out["reads"] = _cut("; ".join(x for x in (out.get("reads"), fit_words(fit)) if x))
    return out


def fit_words(fit) -> str:
    """The fit's steps as a person reads them, or ``""``: "to fit the prompt's bound: the
    topology left out; logs cut to ..."."""
    return ("to fit the prompt's bound: " + "; ".join(fit)) if fit else ""


def loop_feature(prep: dict) -> RL.LoopFeature:
    """The investigation as the read loop's feature, for the request *prep* (`request`): its
    three passes' prompts and schemas, the press's own check (with the reads that ran as
    ``mercury_reads``), what an answer cites and acts on. `troubleshoot` and `preview` share
    it."""
    kept = prep.setdefault("marks", [])

    def check_(answer, *, read_ids):
        sections = list(prep["checked_sections"])
        if read_ids:
            sections.append({"ref": READS_SECTION, "name": READS_SECTION, "state": "ok",
                             "pieces": [{"ref": r} for r in read_ids]})
        # A citation not in what was sent is marked, never a reason to refuse the answer
        # (the operator, 2026-11-15); the marks are kept beside the answer they belong to.
        marks = unverified(answer, sections, prep["topo"], prep["pack"])
        why = check(answer, prep["pack"], sections, prep["topo"], unverified=_flat(marks))
        actable = {str(a) for a in prep.get("actable") or ()}
        if not why and any(str(v) not in actable for v in acts_on(answer)):
            # A step on a device or subscription the finding does not name is the read loop's
            # refusal to name (`read_loop._acts_check`, every pass's), never the ladder's: its
            # "tried" compares a step's class and subscriptions, not its device, so edge3's
            # re-subscribe read as edge2's attempt 1 tried again (17215a95).
            return ""
        if not why:
            why = tried_refusal(answer, prep)
        if not why:
            kept.append((answer, marks))
        return why

    def cites_(answer):
        # A read's citation is judged by `check_` too (a read that did not run is a citation
        # not in what was sent, marked), so the loop's own read-id check does not refuse the
        # whole answer for it.
        return [r for r in cites(answer) if not str(r).startswith("read:")]

    # The investigation (C3797): iterative until a pass adds no new evidence, each pass's spend
    # judged by the gateway (the incident's cap its *spend_cap*, `incident_cap`).
    # One shape (v17, the operator, 2026-11-16): every pass is v17's prompt and schema, with the
    # read set and the reads' format in every pass's context, so the cached prefix is the same
    # bytes call to call; the pass is said in the data.
    one = (PROMPT_INVESTIGATE, SCHEMA_OF[PROMPT_INVESTIGATE[1]])
    return RL.LoopFeature(task=FEATURE, first=one, second=one, plain=one, again=one,
                          check=check_, cites=cites_, acts_on=acts_on, one_shape=True,
                          shared_context=shared_context(), iterative=True,
                          max_reads=MAX_READS, wall_s=WALL_S, read_room=_room_of(prep),
                          refit_first=lambda chars: refit_first(prep, chars))


def tried_refusal(answer, prep: dict) -> str:
    """Why *answer*'s fix or plan names a step whose equivalent already failed in the incident
    (the operator, 2026-11-16: "The AI never proposes a step whose equivalent already failed on
    the incident"; `ladder.step_refusal`, by the request's own ``tried_as`` and ``ladder``),
    or ``""``. An improvement's steps are held the same way."""
    from modules.fixit import ladder

    rows = (prep or {}).get("tried_as") or []
    if answer is None:
        return ""
    # Asked of every answer (the third review): close-first holds also where the incident
    # names no subscription and no ladder was built.
    steps = [as_door(answer.fix)] if getattr(answer, "fix", None) is not None else []
    steps += [as_door(s) for s in getattr(answer, "plan", None) or []]
    imp = getattr(answer, "improvement", None)
    steps += [as_door(s) for s in (imp.steps if imp else [])]
    return ladder.step_refusal(steps, rows, (prep or {}).get("ladder") or [])


def marks_of(prep: dict, answer) -> dict:
    """The unverified citations `loop_feature`'s check kept for *answer* (this very answer,
    by identity), or ``{}``."""
    return next((m for a, m in reversed(prep.get("marks") or []) if a is answer), {})


def retry_once(prep: dict, feature, got: dict, incident, *, ask, network: str, actor: str,
               trigger: dict, send=None, today: str = None) -> dict:
    """When the loop's answer (*got*'s, `read_loop.run`'s) cites what was not sent: ask once
    more, the final pass's request with `RETRY_PART` naming each such citation, while the
    spending limits can pay its counted prompt plus its typical output (the gateway judges it,
    the incident's cap among them, through *ask*'s *spend_cap*; the operator, 2026-11-16: no
    worst case drawn before the press any more); the second answer, checked as
    the loop checks pass 2, replaces the first, marked again if it still cites what was not
    sent; a second answer not had or refused leaves the first, marked. *got*'s ``answer``,
    ``call_ids`` and ``cost_usd`` are updated in place. ``{}`` when nothing was marked, else
    ``{"asked", "accepted", "marks", "words", "call_id"}``, *marks* those of the answer kept."""
    answer = got.get("answer")
    marks = marks_of(prep, answer) if answer is not None else {}
    if got.get("state") not in ("answered", "first_pass") or not marks:
        return {}
    if (got.get("second") or {}).get("error") in ("budget_ran_out", "max_tokens"):
        # The investigation stopped because the budget ran out mid-answer: never asked again.
        return {"asked": False, "accepted": False, "marks": marks, "call_id": "",
                "words": "not asked again: the budget ran out mid-answer"}
    out = {"asked": False, "accepted": False, "marks": marks, "words": "", "call_id": ""}
    records = got.get("reads") or []
    ran = [r for r in records if r.get("verdict") == "run"]
    if ran or feature.one_shape:
        # v17's one shape: the last pass, its reads (none, perhaps) attached, the same cached
        # prefix as every call of the investigation.
        prompt, schema, parts, ctx = RL.second_request(feature, prep["data"], prep["ctx"],
                                                       records)
    else:
        prompt, schema, parts, ctx = RL.first_request(feature, prep["data"], prep["ctx"],
                                                      None, plain=True)
    parts[RETRY_PART] = retry_words(marks)
    r = ask(FEATURE, prompt, schema, parts, trigger=trigger, context=ctx or None,
            actor=actor, subject=prep["subject"], network=network, send=send, today=today)
    out.update(asked=RL.left_host(r), call_id=r.get("call_id") or "")
    got["call_ids"] = (list(got.get("call_ids") or []) + list(r.get("also_calls") or [])
                       + [out["call_id"]])
    got["cost_usd"] = float(got.get("cost_usd") or 0.0) + float(r.get("cost_usd") or 0.0)
    if not r.get("ok") and not RL.left_host(r):
        # Refused before anything was sent (a spending limit could not pay it): said as such.
        out["words"] = (f"not asked again: {r.get('error')}: "
                        f"{(r.get('detail') or '')[:240]}")
        return out
    if not r.get("ok"):
        out["words"] = (f"asked once more, naming what it marked ({_marks_said(marks)}), and "
                        f"not answered ({r.get('error')}: {(r.get('detail') or '')[:160]}); "
                        "the first answer is shown, marked")
        return out
    why = RL.second_check(feature, r["output"], records, prep["actable"])
    if why:
        out["words"] = (f"asked once more, naming what it marked ({_marks_said(marks)}); "
                        f"Mercury's check refused the second answer ({why}), so the first is "
                        "shown, marked")
        return out
    again = marks_of(prep, r["output"])
    got["answer"] = r["output"]
    out.update(accepted=True, marks=again, words=(
        f"asked once more, naming what it marked ({_marks_said(marks)}): "
        + ("every citation of the second answer is in what was sent" if not again else
           "the second answer still has a citation that is bad or missing, and is shown "
           "marked")))
    return out


def overlooked_steps(answer, found, incident=None) -> list:
    """The steps Mercury has for the incident's problem when *answer* reports a gap: each step
    a proposal may name that fixes its condition (`fix_proposal.capabilities`, by
    `problem_condition`) and that no attempt in *incident* already ran and failed. A plan of
    them may exist, so the gap is flagged (C3755: the AI composes a plan before it reports a
    gap), its missing-capability row marked so; ``[]`` otherwise."""
    if answer is None or getattr(answer, "gap", None) is None:
        return []
    condition = problem_condition(found)
    if not condition:
        return []
    from modules.ai import fix_proposal

    failed = set()
    if incident is not None:
        from modules.fixit import incident as F
        try:
            failed = {a["operation"] for a in F.attempts(incident)["attempts"]
                      if not a.get("passed")}
        except Exception as exc:                      # noqa: BLE001 (none excluded, said)
            log.info("fixit troubleshoot: %s's attempts could not be read: %s",
                     getattr(incident, "id", "?"), exc)
    # A step whose equivalent failed counts as tried too (`ladder.TRIED_AS`, 2026-11-16).
    from modules.fixit.ladder import TRIED_AS
    classes = {TRIED_AS[k] for k in failed if k in TRIED_AS}
    return sorted(k for k, fixes in fix_proposal.capabilities().items()
                  if condition in fixes and k not in failed
                  and TRIED_AS.get(k, object()) not in classes)


def overlooked_words(keys) -> str:
    """Why a gap is flagged: the steps Mercury has for its problem, not yet tried in it."""
    return (f"Mercury's catalogue has {_listed(keys)} for this incident's problem, not yet "
            "tried here, so a plan of Mercury's own steps may do it; Ask the AI again for it")


def reads_context() -> dict:
    """The read set's context (`read_set`). With v17's one shape every pass carries it
    (`shared_context`), the plain and the last pass too."""
    return {"read_set": read_set()}


def shared_context() -> dict:
    """What every pass's context carries beside the request's own (v17, `loop_feature`'s
    *shared_context*): the read set and the reads' format, the same bytes every call, so the
    provider's cache written by one call is read by the next, of this investigation or of the
    next one within the cache's five minutes."""
    return dict(reads_context(), reads_format=RL.READS_FORMAT)


# ── Per problem kind: the standard reads and the pack (the operator, 2026-11-16: "Target:
# investigation start to plan ready in 45 s or less") ──────────────────────────────────────────

#: Each problem kind's standard reads (`problem.classify`'s condition), run at once before the
#: first call (`read_loop.run`'s *pregather*), as the model would ask them: ``(op, words,
#: hypothesis, causes)``, *op* a read family operation (``show``, or ``show_config``, which the
#: configuration class decides: refused and left out while it is off), *words* after its verb,
#: *causes* the classification's causes it is read for (``()`` for every one); ``{if}`` the
#: incident's port (its classification's), the read left out when none is known. For an
#: err-disabled port (the operator, 2026-11-16: "the pre-gathered reads must answer it in ONE
#: call"): its state and cause, the device's own recovery, the port's own configuration, and
#: the cause's own state: port security's settings, violation count and last violator, and
#: whether a MAC is still learned on the port; BPDU guard's state and the BPDUs the port took.
#: The plan's own preconditions are read ahead too (`read_ahead_for`).
PSEC, BPDU = "psecure-violation", "bpduguard"
PREGATHER = {"err_disabled": (
    ("show", "interfaces status err-disabled", "the port is err-disabled now, and by which "
                                               "cause", ()),
    ("show", "errdisable recovery", "whether the device recovers the cause by itself, and "
                                    "after how long", ()),
    ("show_config", "running-config interface {if}", "the port's own configuration: its "
                                                     "port-security and BPDU guard settings", ()),
    ("show", "port-security interface {if}", "the port's port-security settings, violation "
                                             "count and last violating MAC", (PSEC,)),
    ("show", "mac address-table interface {if}", "whether a MAC, the violator's or another, is "
                                                 "still learned on the port", (PSEC,)),
    ("show", "spanning-tree interface {if} detail", "BPDU guard on the port, and the BPDUs it "
                                                    "sent and received", (BPDU,)))}
PREGATHER_WHY = "Mercury's standard read for this problem kind, run before the first pass"
#: A classification's own read of the same command on the same device is reused while it is at
#: most this old (reasoned, not measured: IOS's default errdisable recovery interval is 300 s, so
#: a read 60 s old misses at most a fifth of one interval; the classification re-reads every
#: `heal.errdisable.RECHECK_S`, 600 s, so most presses read afresh).
REUSE_S = 60.0
_NOT_FOR_PORT = ("not read for an err-disabled port: its problem is the port's own, read from "
                 "the device (mercury_reads); ask the {read} read if it matters")
#: What each problem kind's pack leaves unread (`evidence_pack.build_incident`'s *skip*), and
#: the topology's words when it is not sent. An err-disabled port is one switch port's problem:
#: its routing neighbours, the network as observed, the two-hop health figures, the monitoring
#: side and the topology say nothing of it (its device's lines, intent, History, what Mercury
#: tried and its diagnosis stay); the model may still ask Mercury's own neighbours or metrics.
KIND_PACK = {"err_disabled": {
    "skip": {"neighbours": _NOT_FOR_PORT.format(read="neighbours"),
             "observed": _NOT_FOR_PORT.format(read="neighbours"),
             "health": _NOT_FOR_PORT.format(read="metrics"),
             "observer": _NOT_FOR_PORT.format(read="metrics")},
    "topology": "not sent: an err-disabled port is its own switch port's problem; this "
                "investigation reads only the incident's device"}}


def pregather_for(network: str, found: dict, incident) -> tuple:
    """``(requests, reuse)`` for `read_loop.run`: the incident's problem kind's standard reads
    (`PREGATHER`) and, from its classification's own device read (`heal.errdisable.confirm`, its
    reads-engine run) at most `REUSE_S` old, each answered command as ``{(device, command):
    read_loop.Answered}``. ``([], {})`` for a kind with none."""
    import time

    from modules.heal import errdisable as ED
    from modules.nsot import reads

    c = ED.of_record((found or {}).get("incident") or {})
    port, conf = str(c.get("port") or ""), c.get("confirmed") or {}
    cause = str(c.get("cause") or "")
    asked = [(op, words, hypothesis) for op, words, hypothesis, causes
             in PREGATHER.get(problem_condition(found)) or () if not causes or cause in causes]
    age = time.time() - float(conf.get("epoch") or 0)
    reuse = {}
    if asked and conf.get("run") and 0 <= age <= REUSE_S:
        try:
            rec = reads.get(network, conf["run"]) or {}
        except (OSError, ValueError) as exc:
            log.info("fixit troubleshoot: %s's classification read is not reused: %s",
                     incident.id, exc)
            rec = {}
        got = (rec.get("results") or {}).get(incident.device) or {}
        reuse = {(incident.device, a["command"]): RL.Answered(
                     a.get("answer") or "", run=conf["run"],
                     signed_in_as=dict(got.get("signed_in_as") or {}))
                 for a in got.get("answers") or [] if a.get("state") == "answered"}
    out = []
    for op, words, hypothesis in asked:
        if "{if}" in words and not port:
            continue
        words = words.replace("{if}", port)
        why = PREGATHER_WHY + (f"; Mercury's classification read it {int(age)} s before, reused"
                               if (incident.device, f"show {words}") in reuse else "")
        out.append({"op": op, "args": {"device": incident.device, "words": words},
                    "why": why, "hypothesis": hypothesis})
    return out, reuse


#: Who a read ahead of the plan's preflight reads as, and why: the preflight's own reader
#: (`command_plan_run.Sources.read`), so its answer is the one the preflight would take.
AHEAD_ACTOR = "Mercury (reviewed commands)"
AHEAD_PURPOSE = ("a command plan's precondition read, read ahead while the AI looks, for its "
                 "plan's preflight")


def read_ahead_for(found: dict, incident, requests) -> list:
    """The precondition reads of each built-in command plan that fixes the incident's problem
    kind (its template's ``fixes`` and ``preconditions``), ``{interface}`` the classification's
    port, less those *requests* (`pregather_for`'s) read already: read through the reads
    engine while the first call is asked (`troubleshoot`), so the plan's preflight on the card
    takes them young (`fix_proposal.job_reads`) instead of reading the device after the answer.
    Never sent to the model: Mercury's own reads, recorded on History › Reads. A read naming any
    other placeholder is left out (its value is the plan's, not known yet). ``[]`` for a kind
    with no plan."""
    from modules.heal import errdisable as ED
    from modules.nsot import command_plan
    from modules.nsot.command_plan_run import Reused

    cond = problem_condition(found)
    port = str(ED.of_record((found or {}).get("incident") or {}).get("port") or "")
    have = {Reused.key(incident.device, f"show {r['args']['words']}") for r in requests or ()}
    out = []
    try:
        plans = list(command_plan.builtin().values())
    except Exception as exc:                                  # noqa: BLE001 (then none ahead)
        log.info("fixit troubleshoot: the built-in plans could not be read: %s", exc)
        return []
    for t in plans:
        if cond not in tuple(getattr(t, "fixes", ()) or ()):
            continue
        for p in t.preconditions:
            read = str(p.get("read") or "")
            if not read:
                continue
            try:
                read = command_plan.substitute(read, {"interface": port} if port else {})
            except command_plan.Refused:
                continue
            if Reused.key(incident.device, read) not in have and read not in out:
                out.append(read)
    return out


def read_ahead(network: str, incident, commands: list, *, pool: str = "") -> str:
    """*commands* on the incident's device through THE reads engine, as the preflight reads
    them (`AHEAD_ACTOR`): the run's id, or ``""`` when nothing was read (refused, said in the
    log: the preflight then reads live, as before). Bounded by the engine's own session
    bounds. *pool* is the investigation's key for the engine's one session per device and
    account (`reads.SessionPool`, C3974), when it has one."""
    from modules.nsot import reads

    if not commands or not incident.device:
        return ""
    try:
        rec = reads.run(network, [incident.device], list(commands), AHEAD_ACTOR,
                        purpose=AHEAD_PURPOSE, **({"pool": pool} if pool else {}))
    except Exception as exc:                                  # noqa: BLE001 (read live later)
        log.info("fixit troubleshoot: %s's plan reads were not read ahead: %s", incident.id, exc)
        return ""
    return str(rec.get("id") or "")


def _laps(what: str):
    """``lap(step, seconds=None)``: logs how long *step* took since the last lap (the
    operator's measurement of a press, 2026-11-16: 25 s before the first call and 29 s after
    the last, unattributed), or, with *seconds*, a part measured on its own (one of several
    read at once), which moves no lap. ``lap.took`` holds every step's seconds, numbered in
    order (``"01 the request ..."``), for the investigation's record (`fixit.incident.
    record_proposal`'s *took*): the host logs below info, so the log alone never shows them."""
    import time

    last = [time.monotonic()]
    took = {}

    def lap(step, seconds=None):
        now = time.monotonic()
        s = (now - last[0]) if seconds is None else float(seconds)
        if seconds is None:
            last[0] = now
        log.info("fixit troubleshoot: %s: %s took %.1f s", what, step, s)
        took[f"{len(took) + 1:02d} {step}"] = round(s, 1)
    lap.took = took
    return lap


def _as_this_job(fn):
    """*fn* to run in another thread as this job's work (`op_progress.running_as`), so a step
    it says (`troubleshoot_job.say`) is this investigation's; the AI's identity is carried by
    the thread starter (`fanout.read_each`, `identity.ai_carried`)."""
    from modules import op_progress

    job = op_progress.current()

    def run():
        with op_progress.running_as(job):
            return fn()
    return run


def _at_once(named: list) -> dict:
    """Each ``(name, fn)`` of *named* run at once (`fanout.read_each`), as this job:
    ``{name: (its result or a fanout.Failed, its seconds)}``. Each is bounded by its own
    sources' bounds, as it was when they ran one after another."""
    import time

    from modules import fanout

    def one(item):
        name, fn = item
        t0 = time.monotonic()
        try:
            return _as_this_job(fn)()
        finally:
            took[name] = round(time.monotonic() - t0, 1)

    took = {}
    got = fanout.read_each(one, named, name="fixit_troubleshoot.at_once",
                           max_workers=max(1, len(named)))
    return {name: (g, took.get(name, 0.0)) for (name, _fn), g in zip(named, got)}


def _behind(fn):
    """*fn* started now in its own thread as this job and as the AI acting now
    (`identity.ai_carried`); ``join()`` waits for it: ``(its result, or None when it raised,
    said in the log; its seconds)``. Bounded by *fn*'s own bounds (the reads engine's)."""
    import threading
    import time

    from modules import identity

    out = {}

    def run():
        t0 = time.monotonic()
        try:
            out["got"] = _as_this_job(fn)()
        except Exception as exc:                                  # noqa: BLE001 (said)
            log.warning("fixit troubleshoot: a read ahead failed: %s", exc)
        finally:
            out["s"] = round(time.monotonic() - t0, 1)

    t = threading.Thread(target=identity.ai_carried(run), name="fixit-read-ahead",
                         daemon=True)
    t.start()

    def join():
        t.join()
        return out.get("got"), out.get("s", 0.0)
    return join


def background_trigger(network: str, job: str, failure_key: str) -> dict:
    """The background trigger of an investigation R1 starts by itself (CLAUDE.md, "Every AI
    call names its trigger"): ``fixit_auto``'s, as *job*, on *network*'s one id
    (`listref.network_id`, what `background.admit` compares), caused by the failure's own
    record *failure_key* (`fixit.auto`)."""
    from modules.ai import triggers
    from modules.nsot import listref

    return triggers.background(AUTO_FEATURE, job, listref.network_id(network), AUTO_FINDING,
                               failure_key)


def _person(actor: str, actor_verified: str, person: bool) -> str:
    if person and actor and actor_verified not in ("", "none", None):
        return ""
    return ("Not asked: Troubleshoot with AI is a verified person's press, and this request is "
            f"not one (its actor is {actor or 'none'}, verified by {actor_verified or 'nothing'})"
            ". Nothing was sent")


@acts_as_ai("fixit-troubleshoot")
def troubleshoot(network: str, found: dict, incident, *, actor: str, actor_verified: str,
                 person: bool, note: str = "", resolved: float = None, send=None,
                 today: str = None, now: float = None, sources=None, planned=None,
                 seen: dict = None, loki=None, prometheus=None, collector=None,
                 series=None, trigger: dict = None, counts_for: dict = None) -> dict:
    """One investigation of *incident* (a `fixit.incident.Incident`, the one *found* resolves),
    a person's press counting toward a background feature's spend too when *counts_for* names
    it (``{"feature", "network"}``, C3751: a turn-on catch-up's, `triggers.person`),
    asked by *actor*, a person verified as *actor_verified* (`STEPS`), or, with *trigger*, by
    the background feature ``fixit_auto`` on a failure (`background_trigger`, R1): *actor* is
    then the trigger's job (``job:<id>``), no person is named on its line, and the gateway
    refuses the call unless the feature is on and inside its caps.

    ``{"state", "words", "proposal", "checked", "call_ids", "cost_usd", "reads", "typed_masked",
    "shown"}``, *state* one of `STATES`, *proposal* the line kept in the incident's record
    (``{}`` when nothing was kept: a call refused before it was sent), *checked* the one door's
    answer for a fix (its preview and hash, or its refusal). Raises `Refused` with nothing sent
    for a press that is not a verified person's, the mode off or unreadable, the per-incident
    cap, or a marking that forces AI off. *send* replaces the provider (tests); *sources* and
    *planned* are the proposal check's seams; *seen*, *loki* and *prometheus* the pack's;
    *collector* and *series* the two local reads' (`fixit_reads.scope_for`)."""
    from modules.ai import fix_proposal, triggers
    from modules.fixit import incident as F
    from modules.fixit import policy as P

    background = isinstance(trigger, dict) and trigger.get("kind") == triggers.BACKGROUND
    if background:
        if trigger.get("feature") != AUTO_FEATURE or actor != triggers.actor_of(trigger):
            raise Refused(f"Not asked: a background investigation is {AUTO_FEATURE}'s, as its "
                          f"job ({triggers.actor_of(trigger)!r}), and {trigger.get('feature')!r}"
                          f" as {actor!r} was given. Nothing was sent", 403)
        actor_verified = ""
    else:
        why = _person(actor, actor_verified, person)                             # person
        if why:
            raise Refused(why, 403)
    off = P.ai_refusal(network)                                                  # mode
    if off:
        raise Refused(f"Not asked: {off}. Nothing was sent")
    # The start is refused here only when the incident's cap cannot pay even the least one call
    # costs (`start_usd`); each call's own counted prompt plus typical output is the gateway's
    # to judge, the incident's cap among the limits (`incident_cap`).
    cs = P.cap_state(incident, start_usd())                                      # cap
    if cs["state"] != "allowed":
        raise Refused(cs["words"].replace("Retry isn't available", "Not asked", 1)
                      + ". Nothing was sent")
    from modules import troubleshoot_job as TJ
    lap = _laps(incident.id)
    # The loop names the network by its one id (`listref.network_id`), as the heal analysis's
    # does: the send log's rows and the calls are keyed by it, and History draws a network's
    # reads by it (C3344: by the list's name, none was drawn).
    from modules.nsot import listref
    net_id = listref.network_id(network)
    plain = bool(RL.reads_off(FR.FAMILY, net_id))
    trig = trigger if background else triggers.person(actor, counts_for=counts_for)
    kind_reads = not plain and bool(PREGATHER.get(problem_condition(found)))
    TJ.step("building the request (the evidence pack, the attempts, the catalogue)"
            + ("" if plain else " and, at once, the reads' scope (the device's committed intent "
               "and golden)" + (" and the standard reads" if kind_reads else "")))
    # The step a person reads on the status line (board R5's screen 3): plain words only.
    if kind_reads:
        TJ.say(f"Gathering what Mercury knows and reading what this problem needs from "
               f"{incident.device}…", done="Gathered what Mercury knows and read what this "
                                           f"problem needs from {incident.device}")
    else:
        TJ.say("Gathering what Mercury already knows about this incident…",
               done="Gathered what Mercury already knows about this incident")
    request_parts = {}
    # The investigation's one device session per account (the operator, 2026-11-16: "sign in
    # once"): its standard reads, the plan's reads read ahead and each later round's ride it;
    # closed once the last of them has run (`finally` below). The pool, its sessions and its
    # credentials are the reads engine's (C3974): this function holds only its key.
    pool = f"ai-investigation-{incident.id}-{time.time_ns()}"   # the engine's pool, by key
    side = {}
    behinds = []                                # the read-ahead threads not joined yet

    def build():                                                                 # pack
        return request(network, found, incident, note=note, now=now, resolved=resolved,
                       seen=seen, loki=loki, prometheus=prometheus, timings=request_parts)

    def reads_side():
        # The reads' scope, then the problem kind's standard reads on it (the operator,
        # 2026-11-16: the scope ran 12.8 s serially before anything else; now beside the
        # request): a classification's read of seconds ago is reused, never read again; and the
        # plan's own precondition reads, named here, read ahead while the first call is asked.
        t0 = time.monotonic()
        scope_ = _scope(network, incident, actor, collector, series)
        scope_["session_pool"] = pool
        side["scope"] = scope_
        pre_, reuse_ = pregather_for(network, found, incident)
        side.update(pre=pre_, reuse=reuse_,
                    ahead=read_ahead_for(found, incident, pre_) if pre_ else [],
                    scope_s=round(time.monotonic() - t0, 1))
        return (RL.pregather_run(FR.FAMILY, pre_, reuse_, network=net_id, scope=scope_)
                if pre_ else None)

    try:
        # The request, and the reads' scope with the standard reads after it, at once (the
        # operator, 2026-11-16: "whatever runs one after the other runs concurrently"): the
        # reads reach the device, the request reads Mercury's stores and its monitoring, so
        # neither waits on the other.
        got_at_once = _at_once([("request", build)] + ([] if plain else [("reads", reads_side)]))
        lap("the request and, at once, the reads' scope" + (" and the standard reads"
                                                              if kind_reads else ""))
        prep, secs = got_at_once["request"]
        lap("the request (the pack, the attempts, Seen before, the fit)", seconds=secs)
        for name, s in request_parts.items():
            lap(f"the request: {name}", seconds=s)
        from modules import fanout
        if isinstance(prep, fanout.Failed):
            raise prep.error
        scope, pre, reuse, ahead, pregathered = None, [], {}, [], None
        if not plain:
            pregathered, secs = got_at_once["reads"]
            if "scope" not in side:
                raise pregathered.error                # as when the scope was read first
            scope, pre, reuse = side["scope"], side.get("pre") or [], side.get("reuse") or {}
            ahead = side.get("ahead") or []
            lap("the reads' scope (beside the request)", seconds=side.get("scope_s") or 0.0)
            if pre:
                lap(f"the standard reads ({len(pre)}, one device session)",
                    seconds=max(0.0, round(secs - (side.get("scope_s") or 0.0), 1)))
            if isinstance(pregathered, fanout.Failed):
                log.warning("fixit troubleshoot: %s's standard reads failed: %s", incident.id,
                            pregathered)
                pregathered = []
            if not pre:
                pregathered = None
            # The pack's own History and Intent check of the device, read seconds ago, answer
            # the model's own reads of them (`fixit_reads._own_read`): read once.
            scope["held"] = {incident.device: {
                s["name"]: s for s in (prep["pack"].get("sections") or [])
                if s.get("name") in ("history", "intent") and s.get("state") in ("ok", "empty")}}
        memo = {"spent": 0.0}
        # The incident's own cap, judged by the gateway at every call's start and live while it
        # streams, with this investigation's calls so far counted (they are on no proposal yet).
        own_cap = incident_cap(incident, lambda: memo["spent"])
        feature = loop_feature(prep)

        def ask(feature_, prompt, schema, parts, *, trigger, **kw):
            # The gateway's own ask, the press's trigger passed on; what it masked of the note
            # is said back to the person.
            memo["calls"] = memo.get("calls", 0) + 1
            TJ.step(f"asking the model (call {memo['calls']}, prompt {prompt[0]}.v{prompt[1]})")
            # Plain steps (the operator, 2026-11-16): the first call is the AI's first look,
            # every later one works out a fix from what it found; the calls' numbers are
            # Details' alone (`TJ.step`). A round of reads after it says how many it asked for
            # (`say_round`).
            if memo["calls"] == 1 or memo.pop("first_again", False):
                TJ.say("The AI's first look…", done="The AI's first look")
            else:
                TJ.say("The AI is working out a fix from what it found…",
                       done="The AI worked out a fix from what it found")
            lap(f"before call {memo['calls']}")
            # The plan's precondition reads, read ahead while the first call is asked (the
            # device is idle then) on the investigation's one session; joined before any round
            # of reads, so they never hold the device against the loop's own (one operation
            # per device, refused by name).
            behind = (_behind(lambda: read_ahead(network, incident, ahead,
                                                 pool=pool))
                      if memo["calls"] == 1 and ahead else None)
            # Kept until joined, so the `finally` below joins it when the call or the loop
            # raises, before the sessions are closed.
            behinds.append(behind)
            # A stream outliving its job (`troubleshoot_job.bound_s`) is closed as soon as the
            # job is stopped (the review, 2026-11-16), read on the job's own thread.
            from modules import op_progress
            job = op_progress.current()
            got = gateway.ask(feature_, prompt, schema, parts, trigger=trigger,
                              spend_cap=own_cap, stop_if=lambda: TJ.was_stopped(job), **kw)
            memo["spent"] += float(got.get("cost_usd") or 0.0)
            lap(f"call {memo['calls']} ({prompt[0]}.v{prompt[1]}, its send)")
            # Its parts, as the gateway timed them (the speed pass, 2026-11-17): the gates and
            # request build, the provider's count among them, and the model call itself.
            gl = got.get("laps") or {}
            if gl:
                lap(f"call {memo['calls']}: of which the provider count", seconds=gl.get(
                    "count_s") or 0.0)
                lap(f"call {memo['calls']}: of which the gates and request build less the count",
                    seconds=max(0.0, (gl.get("prepare_s") or 0.0) - (gl.get("count_s") or 0.0)))
                lap(f"call {memo['calls']}: of which the model call (stream, parse)",
                    seconds=gl.get("send_s") or 0.0)
            if behind is not None:
                behinds.remove(behind)
                run_id, secs_ = behind()
                memo["ahead"] = run_id
                lap(f"the plan's {len(ahead)} precondition read(s) read ahead, beside call 1",
                    seconds=secs_)
                lap("waiting for them past call 1")
            TJ.step(f"after call {memo['calls']}: running the reads it asked for, or answering")
            if got.get("typed_masked") and "typed_masked" not in memo:
                memo["typed_masked"] = got["typed_masked"]
            return got

        # Pass 1 over the context window is refitted inside the loop by the one retry rule
        # (`read_loop.retry_too_long`, the feature's `refit_first`), never here (A's fix).
        got = RL.run(FR.FAMILY, feature, ask=ask, network=net_id,                # ask, check
                     data=prep["data"], actor=actor, trigger=trig,
                     context=prep["ctx"], subject=prep["subject"], scope=scope,
                     actable=prep["actable"], send=send, today=today,
                     reads_context=reads_context(), pregather=pre, reuse=reuse,
                     pregathered=pregathered, lap=lap)
        # What the loop did to fit a pass (`read_loop.counted_room`, `retry_too_long`), said
        # with the fit's own steps.
        prep["said"]["fit"].extend(got.get("fitted") or [])
        lap("after the last call")
        # A citation not in what was sent: asked once more, naming it, within the
        # investigation's worst case and the incident's cap (the operator, 2026-11-15).
        retry = retry_once(prep, feature, got, incident, ask=ask, network=net_id, actor=actor,
                           trigger=trig, send=send, today=today)
    finally:
        # A read ahead still running (the call or the loop raised before it was joined) is
        # joined first, bounded by the engine's own session bounds; then the investigation's
        # sessions are closed, and the pool opens none after (the plan's preflight below reads
        # on its own, reusing these reads' answers).
        for join in [b for b in behinds if b is not None]:
            join()
        from modules.nsot import reads as _reads
        _reads.close_pool(pool)
    marks = retry.get("marks", {}) if retry else marks_of(prep, got.get("answer"))
    said = reads_said(got)
    # A gap for a problem a step Mercury has, not yet tried here, fixes is flagged on the card
    # and on its missing-capability row (C3755: the AI composes a plan before it reports one).
    overlooked = overlooked_steps(got.get("answer"), found, incident)
    record_missing(got, incident, network, found=found, overlooked=overlooked)
    ids = [c for c in got.get("call_ids") or [] if c]
    first = got.get("first") or {}
    out = {"state": "failed", "words": "", "proposal": {}, "checked": None, "call_ids": ids,
           "cost_usd": float(got.get("cost_usd") or 0.0), "reads": said, "shown": {},
           "typed_masked": memo.get("typed_masked"),
           # What was left out or cut to fit the prompt's bound (`fit`), in order.
           "fit": list(prep["said"].get("fit") or ())}
    links = {"page": f"/v2/incident/{incident.id}?list={network}", "anchor": "inc-ai"}
    # The prompt the kept answer came from: the investigation's own pass when it says
    # (`read_loop._investigate`: v12 or v13), else as the two passes chose it.
    asked_prompt = str(got.get("prompt") or "")
    version = (int(asked_prompt.rsplit(".v", 1)[1])
               if asked_prompt.startswith(f"{FEATURE}.v") and not (retry or {}).get("accepted")
               else (PROMPT_PLAN if got["pass"] >= 2 or plain or (retry or {}).get("accepted")
                     else PROMPT_PLAN_READS)[1])
    # A background investigation names no person on its line (both or neither are kept): its
    # trigger, the job, is on its calls' rows.
    common = {"calls": ids, "prompt": f"{FEATURE}.v{version}",
              "by": "" if background else actor, "verified": actor_verified, "note": note}

    def keep(words, **more):                                                     # record
        from modules import op_progress
        if TJ.was_stopped(op_progress.current()):
            # Its watchdog ended this job past its bound (`troubleshoot_job._watch`): the
            # incident already says so, and a late answer is never kept over it.
            log.warning("fixit troubleshoot: %s's answer came after its job was stopped; "
                        "not kept", incident.id)
            return {}
        try:
            return F.record_proposal(incident, "ai", words=words, now=now, **common, **more,
                                     took=dict(lap.took))
        except (F.Refused, OSError, ValueError) as exc:
            log.error("fixit troubleshoot: %s's answer was not kept: %s", incident.id, exc)
            return {}

    if got["state"] == "failed":
        kind, detail = got.get("error") or "", got.get("detail") or ""
        words = (f"The AI was not asked: {NOT_SENT_WORDS.get(kind, kind)}: {detail}"
                 if not RL.left_host(first) else not_answered_words(kind, detail))
        out.update(words=words)
        if ids and RL.left_host(first):
            out["proposal"] = keep(words)
        return out
    # The call whose answer is kept: the retry's when it stands, else the loop's own record of
    # it (`answer_call`: a later pass refused leaves the earlier call's answer kept).
    final_call = ((retry or {}).get("call_id") if (retry or {}).get("accepted") else
                  got.get("answer_call") or (
                      (got.get("second") or {}).get("call_id") if got["pass"] >= 2
                      else first.get("call_id"))) or (ids[-1] if ids else "")
    # The loop stopped while the answer it keeps asked for reads (`read_loop._stopped`): said
    # plainly in place of that answer's "reading first" words (the operator, 2026-11-16).
    stopped = None if (retry or {}).get("accepted") else got.get("stopped")
    if got["state"] == "refused_by_check":
        why = got.get("why") or ""
        calls.record_use(first.get("call_id") or "", fix_proposal.REFUSED_USE, actor=actor,
                         detail=why[:800], links=links)
        words = f"The AI's answer couldn't be checked, so it isn't shown: {why}"
        out.update(state="unchecked", words=words, proposal=keep(words))
        return out
    answer = got["answer"]
    from modules import op_progress
    if TJ.was_stopped(op_progress.current()):
        # Ended by its watchdog past its bound: nothing of a late answer is kept or proposed.
        out.update(state="failed", words="stopped past its bound before it answered")
        return out
    out["shown"] = shown(answer, said, got["pass"], fit=prep["said"].get("fit") or (),
                         marks=marks, retry=retry)
    if overlooked:
        out["shown"]["gap_overlooked"] = overlooked_words(overlooked)
    stopped_said = stopped_words(stopped, answer) if stopped else ""
    if stopped_said:
        # What the section draws as the answer's rationale is Mercury's words, never the
        # kept answer's own "I am reading first"; the model's are kept beside them.
        out["shown"].update(stopped=stopped_said, rationale=stopped_said,
                            model_rationale=_cut(answer.rationale))
    marked = (f" Marked unverified: {len(marks)} part{'s' if len(marks) != 1 else ''} of the "
              "answer cite what was not sent or cite nothing; a step resting only on those is "
              "not approvable." if marks else "")
    if answer.outcome.value == "refuse":
        calls.record_use(final_call, "shown: the evidence cannot say", actor=actor,
                         detail=answer.why_not[:200], links=links)
        words = f"The AI says the evidence cannot say: {_cut(answer.why_not)}"
        out.update(state="unanswerable", words=words, proposal=keep(words, shown=out["shown"]))
        return out
    if answer.fix is not None:                                                   # propose
        door = fix_proposal.for_incident(
            as_door(answer.fix), incident, call_id=final_call, calls=ids, actor=actor,
            actor_verified=actor_verified, note=note, shown=out["shown"],
            prompt=common["prompt"], now=now, sources=sources, planned=planned,
            resolved=resolved)
        out["checked"] = door
        out["proposal"] = door.get("line") or {}
        if door["ok"]:
            calls.record_use(final_call, "shown: a proposal, opened in its operation's preview",
                             actor=actor, detail=door["operation"], links=links)
            out.update(state="proposed", words=(
                "The AI proposes one fix, checked against this incident, the heal guards and "
                "committed intent: it is below with its operation's card. Nothing runs until "
                "you approve it there." + marked))
        else:
            out.update(state="refused_fix", words=(
                f"The AI proposed a fix Mercury's check refused: {door['refused']}"))
        return out
    if getattr(answer, "plan", None):                                            # propose
        # v7 (C3755, C3764): a plan of Mercury's steps, through the same door, and the
        # improvement's shorter route beside it, the person choosing.
        TJ.step("checking the plan: each step held, its preconditions read on the device")
        door = fix_proposal.plan_for_incident(
            [as_door(s) for s in answer.plan], incident, improvement=answer.improvement,
            call_id=final_call, calls=ids, actor=actor, actor_verified=actor_verified,
            note=note, shown=out["shown"], prompt=common["prompt"], now=now,
            # The investigation's own device reads, reused by the plan's preflight (its card
            # alone) when the same command on the same device is young enough (2026-11-16).
            investigated=list(got.get("reads") or ()) + (
                [{"verdict": "run", "run": memo["ahead"]}] if memo.get("ahead") else []),
            # Each part's seconds so far, kept on the plan's line (its preflight's own are
            # its ``preconditions_read``'s ``reuse``).
            took=dict(lap.took))
        lap("the plan's door (its preconditions read, the alternative's too, the record)")
        # Every lap in one line, once, at the end (the speed pass, 2026-11-17).
        log.warning("fixit troubleshoot: %s: laps: %s", incident.id,
                    "; ".join(f"{k} {v} s" for k, v in lap.took.items()))
        out["checked"] = door
        out["proposal"] = door.get("line") or {}
        if door["ok"]:
            calls.record_use(final_call, "shown: a plan, preflighted on the incident's page",
                             actor=actor, detail=", ".join(s["operation"] for s in door["steps"]),
                             links=links)
            out.update(state="proposed", words=(
                f"The AI proposes a plan of {len(door['steps'])} step"
                f"{'s' if len(door['steps']) != 1 else ''}, each preflighted against this "
                "incident, the heal guards and committed intent: it is below. Nothing runs "
                "until you approve it by its hash."
                + (" A shorter route is proposed beside it; you choose."
                   if door.get("alternative") else "") + marked))
        else:
            out.update(state="refused_fix", words=(
                f"The AI proposed a plan Mercury's check refused: {door['refused']}"))
        return out
    if answer.gap is not None:
        calls.record_use(final_call, "shown: a gap, no operation proposed", actor=actor,
                         detail=answer.gap.what[:200], links=links)
        words = (f"No Mercury operation does what the fix needs yet (a gap): "
                 f"{_cut(answer.gap.what)}" + marked)
        if overlooked:
            # C3755: a plan within policy exists for this problem, so the gap is flagged and
            # never recorded as a missing capability; Ask the AI again asks for the plan.
            words = (f"The AI reported a gap, and Mercury's check flags it: "
                     f"{overlooked_words(overlooked)}. Its gap is not recorded as a missing "
                     f"capability. What it said: {_cut(answer.gap.what)}" + marked)
        out.update(state="gap", words=words, proposal=keep(
            words, shown=out["shown"], **({"overlooked": list(overlooked)} if overlooked
                                          else {})))
        if overlooked:
            out["overlooked"] = list(overlooked)
        return out
    if stopped_said:
        calls.record_use(final_call, "shown: the investigation stopped before an answer",
                         actor=actor, detail=stopped_said[:200], links=links)
        words = stopped_said + marked
        out.update(state="no_fix", words=words, proposal=keep(words, shown=out["shown"]),
                   stopped=dict(stopped))
        return out
    calls.record_use(final_call, "shown: no fix named", actor=actor, links=links)
    words = "The AI named no fix: " + (_cut(answer.rationale) or "it gave no reason") + marked
    out.update(state="no_fix", words=words, proposal=keep(words, shown=out["shown"]))
    return out


def stopped_words(stopped: dict, answer) -> str:
    """What an investigation that stopped while its kept answer asked for reads says
    (`read_loop._stopped`; the operator, 2026-11-16): "The AI stopped after N rounds of reads:
    <why>; what it found so far: <its hypotheses' claims>", never that answer's own rationale
    (which says it is reading first). ``""`` for no *stopped*."""
    if not stopped:
        return ""
    n = int(stopped.get("rounds") or 0)
    found = "; ".join(" ".join(str(h.claim or "").split())
                      for h in (answer.hypotheses or [])[:MAX_HYPOTHESES] if h.claim)
    return _cut(f"The AI stopped after {n} round{'s' if n != 1 else ''} of reads: "
                f"{stopped.get('why') or 'no reason recorded'}; what it found so far: "
                + (found or "no hypothesis yet") + ".")


# ── The preview (C3406: scripts/nmas-fixit-cases --preview) ─────────────────────────────────

#: The class a preview builds the press's request with, on, whatever its switch says (the
#: operator, 2026-11-13: "it runs the reads as if the device-state class were on (read-only,
#: nothing sent, no record), so I review before I enable it").
PREVIEW_CLASS = "device_state"
#: The device's reads a preview runs (the lost stream's three reads, by Mercury's allowlist,
#: through the reads engine; C3661).
PREVIEW_DEVICE_READS = ("show",)
#: What each read a preview asks for says as its why and its hypothesis (sent in pass 2, as a
#: model's own words would be).
PREVIEW_WHY = "the preview runs every read of the lost stream the incident's scope allows"
PREVIEW_HYPOTHESIS = "none: a preview's request, not the model's"


def preview_requests(incident, *, device_reads: bool = True) -> list:
    """Every read of the lost stream the incident's scope allows, as pass 1 would ask for it:
    the device's subscriptions brief, then for each subscription the incident names its
    receiver on the device, the collector's side and the stream's series. *device_reads* False
    leaves the device's two out (only Mercury's own reads run, so the reads engine records
    nothing)."""
    def ask(op, **args):
        return {"op": op, "args": dict({"device": incident.device}, **args),
                "why": PREVIEW_WHY, "hypothesis": PREVIEW_HYPOTHESIS}

    # The device's connections (C3640) follow its brief: one read for every subscription. Each
    # is a read by Mercury's allowlist (C3661), the command's words after its verb.
    out = [ask("show", words="telemetry ietf subscription all"),
           ask("show", words="telemetry internal connection")]
    for sub in incident.subscriptions:
        out += [ask("show", words=f"telemetry ietf subscription {sub} receiver"),
                ask("collector_sessions", subscription=sub),
                ask("stream_series", subscription=sub)]
    return [r for r in out if device_reads or r["op"] not in PREVIEW_DEVICE_READS]


def _preview_body(prompt: tuple, schema, parts: dict, ctx: dict) -> dict:
    """One pass's body as the press's call builds it (`gateway.request_body`, a person's
    trigger: the one home of what is sent), with what was masked and withheld; or the
    gateway's refusal, with no body (a request still holding a stored secret is never
    printed)."""
    from modules.ai import profiles, triggers

    got = gateway.request_body(FEATURE, prompt, schema, parts, context=ctx or None,
                               kind=triggers.PERSON)
    out = {"prompt": f"{prompt[0]}.v{prompt[1]}",
           "typed_masked": got["told"].get("typed_masked") or {},
           "withheld": got["told"].get("withheld") or []}
    if "refused" in got:
        kind, detail = got["refused"]
        return dict(out, refused={"kind": kind, "detail": detail}, body=None)
    est = gateway.prompt_tokens(got["body"])
    # The only bound: the room the model's context window leaves for a prompt (the operator,
    # 2026-11-16); the key keeps its name for the preview's readers.
    bound = int(profiles.prompt_room(FEATURE))
    return dict(out, schema=got["row"]["schema"], body=got["body"],
                prompt_tokens_estimated=est, max_prompt_tokens=bound,
                over_the_bound_by_the_estimate=bool(bound and est > bound))


def _read_shown(r: dict) -> dict:
    return {k: r.get(k) for k in ("id", "op", "args", "requests", "verdict", "reason", "bytes",
                                  "sent_bytes", "cut", "withheld", "run") if k in r}


def preview(network: str, found: dict, incident, *, actor: str = "", note: str = "",
            device_reads: bool = True, now: float = None, resolved: float = None,
            seen: dict = None, loki=None, prometheus=None, collector=None,
            series=None) -> dict:
    """What a Troubleshoot with AI press on *incident* would send with the device state class
    on, built by the press's own code and the gateway's (`request`, `loop_feature`,
    `read_loop.first_request` and `second_request`, `gateway.request_body`), with no provider
    request of any kind (no send, no token count), no API key read, and nothing recorded (no
    call row, no send log, no proposal, no spend); the class's switch is read to say what it
    is now, never written, and never decides what is built.

    ``{"network", "incident", "class", "first", "reads", "second", "said"}``: *first* pass 1's
    body (the reads pass's), *reads* every read the incident's scope allows
    (`preview_requests`), each judged by the loop's check with the class assumed on and run
    by the loop's own runner, masked as the loop masks it (the device's through Mercury's
    reads engine, which records each device read on History › Reads as it records every one;
    *device_reads* False runs Mercury's own reads alone), *second* pass 2's body from those
    answers (``None`` when no read ran). Raises `Refused` for a network whose marking forces
    AI off. *collector* and *series* replace the two local reads (tests)."""
    from modules.nsot import listref

    prep = request(network, found, incident, note=note, now=now, resolved=resolved,
                   seen=seen, loki=loki, prometheus=prometheus)
    feature = loop_feature(prep)
    net_id = listref.network_id(network)
    now_off = RL.class_state(FR.FAMILY, PREVIEW_CLASS, net_id)
    prompt, schema, parts, ctx = RL.first_request(feature, prep["data"], prep["ctx"],
                                                  reads_context(), plain=False)
    first = _preview_body(prompt, schema, parts, ctx)
    scope = _scope(network, incident, actor, collector, series)
    scope["actor"] = (f"the preview of AI troubleshooting of incident {incident.id} "
                      f"(scripts/nmas-fixit-cases --preview, run by {actor or 'nobody named'}"
                      "): nothing was sent to the AI")
    scope["purpose"] = "a preview of the AI's read: nothing of it was sent to the AI"
    asked = preview_requests(incident, device_reads=device_reads)
    verdicts = []
    for n, raw in enumerate(asked, 1):
        # Each judged alone, as the loop judges a request (a pass asks for at most 3: the
        # preview runs every one the scope allows, so its pass 2 holds all a press could send).
        (v,) = RL.check(FR.FAMILY, [raw], network=net_id, scope=scope,
                        assume_on=(PREVIEW_CLASS,))
        verdicts.append(dict(v, id=f"read:{n}"))
    # A pass 1 the gateway refuses is never sent, so no read would run: none is run here.
    records = RL.run_reads(FR.FAMILY, verdicts, scope) if first["body"] is not None \
        else verdicts
    ran = [r for r in records if r.get("verdict") == "run"]
    second = None
    if ran:
        # The press's next pass after its reads: the investigation's again pass (C3797), which
        # may ask for more, as `read_loop._investigate` builds it.
        build = RL.again_request if feature.iterative else RL.second_request
        prompt2, schema2, parts2, ctx2 = build(feature, prep["data"], ctx, records)
        second = _preview_body(prompt2, schema2, parts2, ctx2)
    state = "on" if not now_off else "off"
    said = [
        f"The device state class is {state} for {network} now"
        + (f" ({now_off})" if now_off else "") + "; this preview built what a press would "
        "send with it on, and did not change it.",
        f"Pass 1 is the reads pass ({first['prompt']}): the pack, the incident's own sections, "
        "the note and the read set"
        + (", the topology left out to fit the prompt's bound" if TOPOLOGY_LEFT_OUT in
           (prep["data"].get("network_topology") or "") else
           (", and the topology" if prep["topo"].get("sent") else "")) + ".",
        f"The preview ran {len(ran)} of {len(asked)} read(s), every one the incident's scope "
        "allows (" + ", ".join(f"{r['id']} {r.get('op')} {r.get('verdict')}"
                                for r in records) + "). A press's real first answer asks "
        "for at most 3 and may ask for fewer, or none; pass 2 here holds every read that ran, "
        "so it holds all a press's pass 2 could.",
        "Nothing was sent to the AI: no provider request, no token count (the prompt's size "
        "is the fallback estimate), no API key read, and no call, send log, proposal or "
        "spend recorded."
        + (" Each device read ran through Mercury's reads engine, which records it on "
           "History › Reads, as it records every read of a device." if device_reads else
           " The device's reads were left out (--local-reads-only).")]
    fitted = prep["said"].get("fit") or []
    said.append(("The request was fitted " + fit_words(fitted) + ", as a press's would be.")
                if fitted else "The request fits the prompt's bound whole: nothing was left "
                               "out or cut.")
    if second is None:
        said.append("Pass 2 is not built: " + ("pass 1 was refused" if first["body"] is None
                                               else "no read ran, so a press asks no pass 2"))
    return {"network": network, "incident": {"id": incident.id, "device": incident.device,
                                             "subscriptions": list(incident.subscriptions)},
            "class": {"name": PREVIEW_CLASS, "now": state, "why_off": now_off,
                      "assumed": "on, for this preview only: the setting was not written"},
            "first": first, "reads": [_read_shown(r) for r in records], "second": second,
            "said": said}


# ── A recorded case (the fix-it plan's S7: scripts/nmas-fixit-cases) ──────────────────────────

#: What a case keeps of a request: everything the call and its check read, the note apart.
CASE_KEYS = ("pack", "checked_sections", "data", "ctx", "subject", "actable", "topo")
#: The topology's fields the check reads (`check`), kept with a case.
TOPO_KEYS = ("sent", "why", "ids", "names", "summary", "yaml")


def snapshot(prep: dict, incident) -> dict:
    """A case's ``pack``: the request *prep* (`request`) as the call is sent it and its check
    reads it, the note taken out (a case states its own), and the incident it was built for.
    JSON-able; a read of nothing."""
    out = {k: prep[k] for k in CASE_KEYS if k != "topo"}
    out["topo"] = {k: (prep.get("topo") or {}).get(k) for k in TOPO_KEYS}
    out["data"] = {k: v for k, v in prep["data"].items() if k != "note"}
    out["checked_sections"] = [s for s in prep["checked_sections"] if s.get("name") != NOTE]
    out["incident"] = {"network": incident.network, "id": incident.id,
                       "device": incident.device, "subscriptions": list(incident.subscriptions)}
    return json.loads(json.dumps(out, sort_keys=True, default=str))


def request_of_case(pack: dict, note: str = "") -> dict:
    """The request a recorded case's *pack* (`snapshot`) is asked with, its *note* the case's:
    the request `request` built, read from the record, with no store, device or service read."""
    note = " ".join(str(note or "").split())
    return {"pack": pack["pack"], "topo": dict(pack.get("topo") or {}),
            "checked_sections": list(pack["checked_sections"]) + [note_section(note)],
            "data": dict(pack["data"], note=note), "ctx": dict(pack["ctx"]),
            "subject": dict(pack["subject"]), "actable": list(pack["actable"])}


def case_result(prep: dict, got: dict) -> dict:
    """A recorded case's answer (*got*, the gateway's result of its plain pass, asked by
    scripts/nmas-fixit-cases under an evaluation's trigger) held to the press's own check and
    the read loop's actable rule: ``{"state": "answered"|"unchecked"|"failed", "answer", "why",
    "call_id", "cost_usd", "error"}``, *answer* the checked answer as a dict (its fix and gap
    included). Calls nothing; nothing is kept, proposed or run."""
    out = {"state": "failed", "answer": None, "why": "", "call_id": got.get("call_id") or "",
           "cost_usd": float(got.get("cost_usd") or 0.0),
           "error": f"{got.get('error') or ''}: {got.get('detail') or ''}".strip(": ")}
    if not got.get("ok"):
        return out
    answer = got["output"]
    why = check(answer, prep["pack"], prep["checked_sections"], prep["topo"])
    if not why:
        outside = [str(v) for v in acts_on(answer) if str(v) not in set(prep["actable"])]
        if outside:
            why = (f"the answer acts on {outside[0]}, which is not one the finding names "
                   f"({', '.join(prep['actable'])})")
    out["answer"] = answer.model_dump(mode="json")
    out.update(state="unchecked" if why else "answered", why=why, error="")
    return out
