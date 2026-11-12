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

**The reads** go only through Mercury's read families, `fixit_reads.FAMILY` (S6): the router
read set's (each command whole on its allowlist, on the incident's device, as the read-only
account, through the reads engine and on History › Reads), the lost stream's two among them,
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
PROMPT_READS = (FEATURE, 4)
PROMPT_SECOND = (FEATURE, 3)
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
#: (`fixit_reads.FAMILY`: the router read set, the stream's two shapes, Mercury's own reads).
FixitReadAsk = RL.request_model(FR.FAMILY)


@register(FEATURE, 4)
class TroubleshootFixitReads(Troubleshoot):
    """Pass 1 of the read loop (S6): `Troubleshoot`, plus at most 3 reads of AI
    troubleshooting's read family."""
    reads: list[FixitReadAsk] = []


SCHEMA_OF = {1: Troubleshoot, 2: TroubleshootReads, 3: TroubleshootSecond,
             4: TroubleshootFixitReads}


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
        "read_set is the read-only reads Mercury may run for this investigation: the device's "
        "own (each on the incident's device, as its read-only account), and Mercury's own of "
        "what it holds (collector_sessions: the collector's side of a subscription's stream on "
        "Mercury's host; stream_series: whether the stream has data now). To ask for one, add it to "
        "reads: op is one of the operations below, args its arguments by name (device always, "
        "and null for an argument the operation does not take), why one line on what it would "
        "show, and hypothesis the hypothesis it tests. Ask for at most 3; ask for none when the "
        "evidence says enough. Mercury checks each request against what it holds and runs only "
        "those it allows; the next message carries the answers, or why a request was refused.",
        "The operations:"]
    for op in FR.FAMILY.operations:
        args = ", ".join(f"{a} ({spec.shape.words})" for a, spec in op.args.items())
        lines.append(f"- {op.name}: {op.words}; args: {args}")
    return "\n".join(lines)


def request(network: str, found: dict, incident, *, note: str = "", now: float = None,
            resolved: float = None, seen: dict = None, loki=None, prometheus=None) -> dict:
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
    return {"pack": pack, "topo": topo, "sections": sections, "checked_sections": checked,
            "data": data, "ctx": ctx, "said": said,
            "subject": {"kind": "heal_incident", "id": incident.id,
                        "devices": [incident.device] if incident.device else []},
            "actable": [incident.device, *incident.subscriptions]}


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


def shown(answer, said: dict = None, pass_: int = 1) -> dict:
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
    return out


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

    def check_(answer, *, read_ids):
        sections = list(prep["checked_sections"])
        if read_ids:
            sections.append({"ref": READS_SECTION, "name": READS_SECTION, "state": "ok",
                             "pieces": [{"ref": r} for r in read_ids]})
        return check(answer, prep["pack"], sections, prep["topo"])

    feature = RL.LoopFeature(task=FEATURE, first=(PROMPT_READS, TroubleshootFixitReads),
                             second=(PROMPT_SECOND, TroubleshootSecond),
                             plain=(PROMPT, Troubleshoot), check=check_, cites=cites,
                             acts_on=acts_on)

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
                 reads_context={"read_set": read_set()})
    said = reads_said(got)
    ids = [c for c in got.get("call_ids") or [] if c]
    first = got.get("first") or {}
    out = {"state": "failed", "words": "", "proposal": {}, "checked": None, "call_ids": ids,
           "cost_usd": float(got.get("cost_usd") or 0.0), "reads": said, "shown": {},
           "typed_masked": memo.get("typed_masked")}
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
    out["shown"] = shown(answer, said, got["pass"])
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
