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
(tests/test_ai_entry_points.py), and no background feature is registered for it
(`background.FEATURES` holds none). **One press, one investigation**: at most two calls
(`read_loop.CALLS_PER_FINDING`: pass 1 and, when a read ran, pass 2), its reads included, under
the per-incident cap (`fixit.policy.cap_state`: spent plus the investigation's worst case,
`worst_usd`) and the gateway's own caps (the day cap and the per-call cap, asked before each
pass). The estimate is drawn before the press (`estimate`). The mode is the installation's: this
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
from enum import Enum
from typing import Optional

from modules.ai import calls, gateway
from modules.ai import read_loop as RL
from modules.ai import fixit_reads as FR
from modules.ai import router_reads as RR
from modules.ai.explain import Hypothesis
from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)

#: The task (`profiles.TASKS`'s pin) and its prompts: v1 the plain pass (no read class on), v4
#: the read loop's first pass over AI troubleshooting's own read family (S6), v3 its second.
#: v2 is S5's first pass over the router read set alone: no longer asked, kept with its schema
#: so a call recorded under it stays readable (expand, then contract).
FEATURE = "fixit_troubleshoot"
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
PROMPT_SECOND = (FEATURE, 6)
#: The pack's own sections, in the pack format's order (the heal analysis's, whose pack this is).
PACK_SECTIONS = ("incident", "device", "history", "intent", "neighbours", "observed", "health",
                 "observer", "logs", "tried", "diagnosis")
#: This incident's own sections, beside the pack's.
ATTEMPTS = "attempts"
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


SCHEMA_OF = {1: Troubleshoot, 2: TroubleshootReads, 3: TroubleshootSecond,
             4: TroubleshootFixitReads, 5: TroubleshootEngineerReads}


class Refused(ValueError):
    """Nothing was sent; the words say why. ``status`` is the HTTP status it answers."""

    def __init__(self, words: str, status: int = 409):
        super().__init__(words)
        self.status = status


# ── The figures, drawn before the press ─────────────────────────────────────────────────────

def worst_usd() -> float:
    """One investigation's worst case in US dollars: `read_loop.CALLS_PER_FINDING` calls at the
    pin's per-call cap (`profiles.cap_per_call`)."""
    from modules.ai import profiles

    return round(profiles.cap_per_call(FEATURE) * RL.CALLS_PER_FINDING, 6)


def estimate() -> dict:
    """``{"usd", "worst", "measured", "basis"}``: what one investigation is expected to cost,
    the task's measured mean cost per sent call (`background.measured_cost`, its last 30 days)
    times its two calls, or, with none measured, its worst case said as such; and the worst
    case. A read of the record of AI calls; no call is made."""
    from modules.ai import background

    got = background.measured_cost(FEATURE)
    worst = worst_usd()
    usd = round(float(got["usd_per_call"]) * RL.CALLS_PER_FINDING, 6)
    return {"usd": min(usd, worst), "worst": worst, "measured": bool(got["measured"]),
            "basis": got["basis"]}


# ── What is sent ────────────────────────────────────────────────────────────────────────────

def _section(name: str, state: str, why: str = "", pieces=(), source: str = "",
             **extra) -> dict:
    return {"ref": name, "name": name, "source": source, "state": state, "why": why,
            "pieces": list(pieces), **extra}


def attempts_section(incident, resolved: float = None, *, now: float = None) -> dict:
    """The incident's attempts as sent (`payload.tried_parts`, every person a stable label),
    each piece ``attempt:<n>``."""
    from modules.fixit import payload

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
        "catalogue is every operation a fix may name, with its parameters and their shapes."])


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
            resolved: float = None, seen: dict = None, loki=None, prometheus=None) -> dict:
    """`built_request`, or `Refused` with nothing sent when a person in it cannot be labelled
    because no label key is installed (C3458, `display_names.LabelKeyMissing`, the key named):
    a press and its preview alike, and no key is made by either."""
    from modules import display_names

    try:
        return built_request(network, found, incident, note=note, now=now, resolved=resolved,
                             seen=seen, loki=loki, prometheus=prometheus)
    except display_names.LabelKeyMissing as exc:
        raise Refused(f"Not asked: {exc}") from None


def built_request(network: str, found: dict, incident, *, note: str = "", now: float = None,
                  resolved: float = None, seen: dict = None, loki=None,
                  prometheus=None) -> dict:
    """The investigation's request for the incident `incident_page.resolve` *found* (its
    `fixit.incident.Incident`, *incident*), before any call: ``{"pack", "topo", "sections",
    "checked_sections", "data", "ctx", "subject", "actable", "said"}``. *sections* are what is
    sent of the pack, *checked_sections* those plus this incident's own (what an answer's
    references resolve against). Raises `Refused` for a network whose marking forces AI off.
    Reads Mercury's stores and the monitoring the pack reads; calls no model."""
    from modules import evidence_pack as EP
    from modules.ai import egress_classes, explain
    from modules.fixit import payload

    marked = egress_classes.classification_marking(network)
    if marked:
        raise Refused(f"{network} carries the classification marking {marked!r}, which forces "
                      "AI off: nothing was sent")
    entry = found.get("entry") or {}
    units = [u for d in found.get("decisions") or [] for u in d.get("units") or []]
    pack = EP.build_incident(network, found.get("incident") or {}, entry, units,
                             now=float(entry.get("epoch") or 0) or now, loki=loki,
                             prometheus=prometheus)
    topo = explain.topology(pack)
    sections = explain.sent_sections(pack, topo)
    own = [attempts_section(incident, resolved, now=now),
           seen_section(network, incident.device, seen)]
    checked = list(sections) + own + [note_section(note)]
    data = {"pack": json.dumps([explain.as_sent(s) for s in sections] + own, sort_keys=True,
                               ensure_ascii=False, separators=(",", ":")),
            "note": " ".join(str(note or "").split()),
            "the_incident": (f"{incident.id} on {incident.device}: "
                             + (f"telemetry subscription(s) {', '.join(incident.subscriptions)}"
                                " lost" if incident.subscriptions else "no subscription named")
                             + "; it stands open, and a person asked you to troubleshoot it")}
    if topo.get("yaml"):
        data["network_topology"] = topo["yaml"]
    ctx = {"pack_format": explain.vocabulary(PACK_SECTIONS), "fixit_format": fixit_format(),
           "catalogue": json.dumps(payload.catalogue_part(), sort_keys=True,
                                   ensure_ascii=False, separators=(",", ":"))}
    if topo.get("sent"):
        from modules import network_model as NM
        ctx["network"] = topo["summary"]
        ctx["topology_format"] = NM.FORMAT
    said = {"sent": topo.get("sent"), "why": topo.get("why"), "devices": sorted(
        topo.get("reached") or ())}
    prep = {"pack": pack, "topo": topo, "sections": sections, "checked_sections": checked,
            "data": data, "ctx": ctx, "said": said,
            "subject": {"kind": "heal_incident", "id": incident.id,
                        "devices": [incident.device] if incident.device else []},
            "actable": [incident.device, *incident.subscriptions],
            "own": own, "note_part": note_section(note)}
    return fit(prep)


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

#: What pass 2 may add to pass 1 at most (`reads_reserve_chars`, measured at import); pass 2
#: sends no read set (`loop_feature`'s ``first_only``).
def reads_reserve_chars() -> int:
    """What pass 2 may add to pass 1 at most, in the request's characters, MEASURED by building
    it (the review of the fit, 2026-11-14: a fixed 600 a read undercounted): `read_loop.
    MAX_READS` records as `read_loop.as_sent` sends them, each at its largest (its why and its
    hypothesis at `read_loop.TEXT_MAX`, its words at the command shape's most, an answer of
    `read_loop.AI_READ_CAP` characters written as show output escapes worst in practice: a
    line break every 40 characters and a quoted word on each line), the part encoded as pass 2
    sends it and then once more as the request's body escapes it, and the reads' format
    context, likewise, beside its wrapper. A text of quotes alone would escape further; show
    output does not."""
    line = 'state "up" ' + "x" * 24 + "\n"                     # 40 characters a line
    answer = (line * (RL.AI_READ_CAP // len(line) + 1))[:RL.AI_READ_CAP]
    words = "w" * RR.COMMAND_WORDS.most
    records = [{"id": f"read:{n}", "op": "show", "args": {"device": "d" * 63, "words": words},
                "why": "y" * RL.TEXT_MAX, "hypothesis": "h" * RL.TEXT_MAX, "verdict": "run",
                "answer": answer, "bytes": 10 ** 6, "cut": True, "withheld": 999}
               for n in range(1, RL.MAX_READS + 1)]
    part = json.dumps(RL.as_sent(records), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))
    wrapper = '\n<data name="mercury_reads">\n\n</data>\n<context name="reads_format">\n\n</context>'
    return (len(json.dumps(part, ensure_ascii=False)) + len(json.dumps(RL.READS_FORMAT))
            + len(json.dumps(wrapper)))


READS_RESERVE_CHARS = reads_reserve_chars()
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


def request_chars(prep: dict) -> int:
    """Pass 1's masked request body in characters, as the gateway builds it (`request_body`:
    the press's own builder, no provider request), or 0 when it is refused before it is built
    (a stored secret, no label key: the press is refused for that, never for its size)."""
    from modules.ai import triggers

    prompt, schema, parts, ctx = RL.first_request(
        loop_feature(prep), prep["data"], prep["ctx"], reads_context(), plain=False)
    got = gateway.request_body(FEATURE, prompt, schema, parts, context=ctx or None,
                               kind=triggers.PERSON)
    if "refused" in got:
        return 0
    return len(json.dumps(got["body"], ensure_ascii=False))


def _over(prep: dict, bound: int) -> bool:
    """Whether pass 1, or pass 2 at its worst (pass 1 less the read set it does not carry, plus
    `READS_RESERVE_CHARS`), is over *bound* by the fallback over-estimate."""
    chars = request_chars(prep)
    worst = chars + max(0, READS_RESERVE_CHARS - len(read_set()))
    return bool(chars) and gateway.tokens_of_chars(max(chars, worst)) > bound


def _repack(prep: dict) -> None:
    from modules.ai import explain

    prep["data"]["pack"] = json.dumps([explain.as_sent(s) for s in prep["sections"]]
                                      + prep["own"], sort_keys=True, ensure_ascii=False,
                                      separators=(",", ":"))
    prep["checked_sections"] = list(prep["sections"]) + prep["own"] + [prep["note_part"]]


def fit(prep: dict, bound: int = None) -> dict:
    """*prep* fitted to the task's bound (`profiles.TASKS`' ``max_prompt_tokens``) by the
    fallback over-estimate, both passes (pass 2 at its worst, `_over`): unchanged when
    it fits; else the topology left out (said in its part, and nothing of it citable), then the
    largest trimmable section halved, again, each cut said in the section (``cut``), until it
    fits or nothing is left to cut. What was done is ``said["fit"]``, in order; the request is
    asked either way (the provider's count decides, `gateway.ask`)."""
    from modules.ai import explain, profiles

    bound = int(bound or (profiles.TASKS.get(FEATURE) or {}).get("max_prompt_tokens") or 0)
    steps = []
    prep["said"]["fit"] = steps
    if not bound or not _over(prep, bound):
        return prep
    if prep["topo"].get("sent"):
        prep["topo"] = dict(prep["topo"], sent=False, why=TOPOLOGY_LEFT_OUT, ids=[],
                            reached={}, yaml="", names={})
        prep["data"]["network_topology"] = TOPOLOGY_LEFT_OUT
        for key in ("network", "topology_format"):
            prep["ctx"].pop(key, None)
        prep["sections"] = explain.sent_sections(prep["pack"], prep["topo"])
        prep["said"].update(sent=False, why=TOPOLOGY_LEFT_OUT, devices=[])
        _repack(prep)
        steps.append("the topology left out")
    halved = {}
    while _over(prep, bound):
        cuttable = [(len(json.dumps(s)), i) for i, s in enumerate(prep["sections"])
                    if s.get("name") in TRIMMABLE and len(s.get("pieces") or []) > 1
                    and halved.get(s.get("name"), 0) < MOST_HALVINGS]
        if not cuttable:
            steps.append("still over the bound by the fallback estimate: the provider's count "
                         "decides")
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
    fix = getattr(answer, "fix", None)
    if fix is None:
        return []
    p = fix.params
    return [p.device, *(p.subscriptions or []), *([p.subscription] if p.subscription else [])]


def cites(answer) -> list:
    """Every reference an answer makes: each hypothesis's, the fix's and the gap's."""
    out = [r for h in getattr(answer, "hypotheses", None) or [] for r in h.evidence_refs]
    for part in (getattr(answer, "fix", None), getattr(answer, "gap", None)):
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


def check(answer, pack: dict, sections: list, topo: dict) -> str:
    """"" when *answer* stands against what was sent (*sections*, this incident's own among
    them), else why not, the first that does not (the module's docstring): Explain's check of
    the hypotheses; a fix and a gap not both; the fix's and the gap's references resolved; the
    fix held to the catalog's schema. The actable rule is the read loop's (`acts_on`)."""
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
                               added=[a["ref"] for a in added])
    if why:
        return why
    if len(answer.hypotheses) > MAX_HYPOTHESES:
        return f"{len(answer.hypotheses)} hypotheses; at most {MAX_HYPOTHESES} are taken"
    if answer.outcome.value == "refuse":
        if answer.fix is not None or answer.gap is not None:
            return "the answer says the evidence cannot say, and still names a fix or a gap"
        return ""
    if answer.fix is not None and answer.gap is not None:
        return ("the answer names both a fix and a gap: a fix is one catalog operation, and a "
                "gap is what no catalog operation does, never both")
    for name, part in (("fix", answer.fix), ("gap", answer.gap)):
        if part is None:
            continue
        if not part.evidence_refs:
            return f"the {name} cites nothing that was sent"
        ref = _unresolved(part.evidence_refs, sections)
        if ref and ref not in set(ids or ()):
            return f"the {name} cites {ref[:40]!r}, which is not in what was sent"
    if answer.fix is not None:
        from modules.ai import fix_proposal

        why = fix_proposal.held(as_door(answer.fix))
        if why:
            return f"the fix is not one catalog operation with its parameters: {why}"
    return ""


# ── The investigation ───────────────────────────────────────────────────────────────────────

def _scope(network: str, incident, actor: str, collector=None, series=None) -> dict:
    """What the read family's comparisons read (`fixit_reads.scope_for`): the incident's device
    and subscriptions alone, the reads recorded as the press's."""
    return FR.scope_for(network, incident, actor=actor, collector=collector, series=series)


def record_missing(got: dict, incident, network: str) -> dict:
    """What the investigation wanted that Mercury lacks, recorded for review (C3663,
    `modules/ai/missing.py`): each read it asked for that Mercury lacks, and its gap. Never
    acted on; a store that cannot be written is logged and the answer stands."""
    from modules.ai import missing

    try:
        rows = missing.wanted(got.get("answer"), got.get("reads") or [], feature=FEATURE,
                              network=network, about=("incident", incident.id))
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


def shown(answer, said: dict = None, pass_: int = 1, fit=()) -> dict:
    """What the section draws of a checked answer: the rationale, each hypothesis's claim and
    what it cites, the fix's why or the gap's what, and what the reads did. Kept with the
    proposal line (masked at rest)."""
    out = {"rationale": _cut(answer.rationale), "needs_human": bool(answer.needs_human),
           "hypotheses": [{"claim": _cut(h.claim), "cites": list(h.evidence_refs)[:8]}
                          for h in answer.hypotheses[:MAX_HYPOTHESES]],
           "passes": pass_}
    if answer.fix is not None:
        out["why"] = _cut(answer.fix.why)
        out["cites"] = list(answer.fix.evidence_refs)[:8]
    if answer.gap is not None:
        out["gap"] = _cut(answer.gap.what)
        out["cites"] = list(answer.gap.evidence_refs)[:8]
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
    def check_(answer, *, read_ids):
        sections = list(prep["checked_sections"])
        if read_ids:
            sections.append({"ref": READS_SECTION, "name": READS_SECTION, "state": "ok",
                             "pieces": [{"ref": r} for r in read_ids]})
        return check(answer, prep["pack"], sections, prep["topo"])

    return RL.LoopFeature(task=FEATURE, first=(PROMPT_READS, TroubleshootEngineerReads),
                          second=(PROMPT_SECOND, TroubleshootSecond),
                          plain=(PROMPT, Troubleshoot), check=check_, cites=cites,
                          acts_on=acts_on, first_only=("read_set",))


def reads_context() -> dict:
    """The context only the reads pass carries: the read set (`read_set`)."""
    return {"read_set": read_set()}


def _person(actor: str, actor_verified: str, person: bool) -> str:
    if person and actor and actor_verified not in ("", "none", None):
        return ""
    return ("Not asked: Troubleshoot with AI is a verified person's press, and this request is "
            f"not one (its actor is {actor or 'none'}, verified by {actor_verified or 'nothing'})"
            ". Nothing was sent")


def troubleshoot(network: str, found: dict, incident, *, actor: str, actor_verified: str,
                 person: bool, note: str = "", resolved: float = None, send=None,
                 today: str = None, now: float = None, sources=None, planned=None,
                 seen: dict = None, loki=None, prometheus=None, collector=None,
                 series=None) -> dict:
    """One investigation of *incident* (a `fixit.incident.Incident`, the one *found* resolves),
    asked by *actor*, a person verified as *actor_verified* (`STEPS`):

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

    why = _person(actor, actor_verified, person)                                 # person
    if why:
        raise Refused(why, 403)
    off = P.ai_refusal()                                                         # mode
    if off:
        raise Refused(f"Not asked: {off}. Nothing was sent")
    cs = P.cap_state(incident, worst_usd())                                      # cap
    if cs["state"] != "allowed":
        raise Refused(cs["words"].replace("Retry isn't available", "Not asked", 1)
                      + ". Nothing was sent")
    prep = request(network, found, incident, note=note, now=now, resolved=resolved,  # pack
                   seen=seen, loki=loki, prometheus=prometheus)
    memo = {}
    feature = loop_feature(prep)

    def ask(feature_, prompt, schema, parts, *, trigger, **kw):
        # The gateway's own ask, the press's trigger passed on; what it masked of the note is
        # said back to the person.
        got = gateway.ask(feature_, prompt, schema, parts, trigger=trigger, **kw)
        if got.get("typed_masked") and "typed_masked" not in memo:
            memo["typed_masked"] = got["typed_masked"]
        return got

    # The loop names the network by its one id (`listref.network_id`), as the heal analysis's
    # does: the send log's rows and the calls are keyed by it, and History draws a network's
    # reads by it (C3344: by the list's name, none was drawn).
    from modules.nsot import listref
    net_id = listref.network_id(network)
    plain = bool(RL.reads_off(FR.FAMILY, net_id))
    scope = None if plain else _scope(network, incident, actor, collector, series)
    got = RL.run(FR.FAMILY, feature, ask=ask, network=net_id,                  # ask, check
                 data=prep["data"], actor=actor, trigger=triggers.person(actor),
                 context=prep["ctx"], subject=prep["subject"], scope=scope,
                 actable=prep["actable"], send=send, today=today,
                 reads_context=reads_context())
    said = reads_said(got)
    record_missing(got, incident, network)
    ids = [c for c in got.get("call_ids") or [] if c]
    first = got.get("first") or {}
    out = {"state": "failed", "words": "", "proposal": {}, "checked": None, "call_ids": ids,
           "cost_usd": float(got.get("cost_usd") or 0.0), "reads": said, "shown": {},
           "typed_masked": memo.get("typed_masked"),
           # What was left out or cut to fit the prompt's bound (`fit`), in order.
           "fit": list(prep["said"].get("fit") or ())}
    links = {"page": f"/v2/incident/{incident.id}?list={network}", "anchor": "inc-ai"}
    version = (PROMPT_SECOND if got["pass"] == 2 else PROMPT if plain else PROMPT_READS)[1]
    common = {"calls": ids, "prompt": f"{FEATURE}.v{version}", "by": actor,
              "verified": actor_verified, "note": note}

    def keep(words, **more):                                                     # record
        try:
            return F.record_proposal(incident, "ai", words=words, now=now, **common, **more)
        except (F.Refused, OSError, ValueError) as exc:
            log.error("fixit troubleshoot: %s's answer was not kept: %s", incident.id, exc)
            return {}

    if got["state"] == "failed":
        kind, detail = got.get("error") or "", got.get("detail") or ""
        words = (f"The AI was not asked: {NOT_SENT_WORDS.get(kind, kind)}: {detail}"
                 if not RL.left_host(first) else
                 f"The AI did not answer ({kind}: {detail[:200]})")
        out.update(words=words)
        if ids and RL.left_host(first):
            out["proposal"] = keep(words)
        return out
    final_call = ((got.get("second") or {}).get("call_id") if got["pass"] == 2
                  else first.get("call_id")) or (ids[-1] if ids else "")
    if got["state"] == "refused_by_check":
        why = got.get("why") or ""
        calls.record_use(first.get("call_id") or "", fix_proposal.REFUSED_USE, actor=actor,
                         detail=why[:800], links=links)
        words = f"The AI's answer couldn't be checked, so it isn't shown: {why}"
        out.update(state="unchecked", words=words, proposal=keep(words))
        return out
    answer = got["answer"]
    out["shown"] = shown(answer, said, got["pass"], fit=prep["said"].get("fit") or ())
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
                "you approve it there."))
        else:
            out.update(state="refused_fix", words=(
                f"The AI proposed a fix Mercury's check refused: {door['refused']}"))
        return out
    if answer.gap is not None:
        calls.record_use(final_call, "shown: a gap, no operation proposed", actor=actor,
                         detail=answer.gap.what[:200], links=links)
        words = (f"No Mercury operation does what the fix needs yet (a gap): "
                 f"{_cut(answer.gap.what)}")
        out.update(state="gap", words=words, proposal=keep(words, shown=out["shown"]))
        return out
    calls.record_use(final_call, "shown: no fix named", actor=actor, links=links)
    words = "The AI named no fix: " + (_cut(answer.rationale) or "it gave no reason")
    out.update(state="no_fix", words=words, proposal=keep(words, shown=out["shown"]))
    return out


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
    bound = int((profiles.TASKS.get(FEATURE) or {}).get("max_prompt_tokens") or 0)
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
        prompt2, schema2, parts2, ctx2 = RL.second_request(feature, prep["data"], ctx, records)
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
