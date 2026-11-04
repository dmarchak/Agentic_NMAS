"""The AI analysis of a can't-fix (board H, part H8; docs/HEAL_TO_INTENT.md section 12): when
self-healing stops at can't fix, a hypothesis and a recommended next step, each cited from the
incident's evidence. **It advises only.**

- **Nothing in the heal loop reads it.** Detect, decide, act, verify and record never import
  this module or read an analysis (tests/test_heal_analysis_never_read.py parses
  `modules/heal/`). Only the notifier (`modules/heal_notice.py`) and the pages draw it. No fix
  is ever chosen or run from AI text.
- **A background call under CLAUDE.md's "AI cost safety" rules** (PHASE8_PLAN 18.3): its
  trigger is named, ``triggers.background("heal_analysis", <job>, <network>, "heal_incident",
  <incident id>)``; its finding is the deterministic one, the heal loop stopped at can't fix
  (`CANT_FIX`: the decision's can't fix, or an act whose symptom remained or that rolled back,
  which notify as a can't-fix, section 4); nothing else calls it (`analyse` refuses any other
  entry with no call). Its feature, ``heal_analysis`` in `background.FEATURES`, is off by
  default per network, turned on only in Settings › AI by an admin after its estimate, within
  its own day and month caps (`background.over_cap`); its frequency is measured from the heal's
  own record (`cant_fix_frequency`). The gateway refuses it, recorded, with no provider request,
  when it is off, past a cap, or hosted AI is off.

**Its input** (`prepare`): the incident's evidence pack (`evidence_pack.build_incident`: what
started it, the device, History, the Intent check with its masked intent-diff lines, at most 20
(N10), neighbours, the network as observed, health, the monitoring side, log lines) and its
``tried`` section, each step from the step log (`steplog.incident`, H6's seam) cited as
``tried:<n>``. **Egress, by kind:** the step log's configuration lines never leave as text:
each unit is said by its kind ("a security ACL added outside intent on Gi2, 2 lines, content
withheld", `evidence_pack.unit_by_kind`), the program by its size and hash, and any of the
incident's lines a step's words held is withheld (`evidence_pack.withhold`). The pack's own
sections go as Explain's do (`explain.sent_sections`, the topology class asked of
`egress_classes.topology_allowed`); the gateway's egress mask (`redact.egress_payload`) covers
every byte. That is the irreversible tier: its hand check is docs/TIER_HAND_CHECK.md's.

**The prompt and the check are Explain's** (`modules/ai/explain.py`): shape B, a rationale then
``{hypotheses: [{claim, evidence_refs, confirm_with}], needs_human}`` (`Analysis`); every
reference must resolve to what was sent, every ``confirm_with`` must be a read on the read-only
allowlist, and a device the answer names must be cited (C1897), all by `explain.check`. It runs
as its own task and prompt version (``heal_analysis`` v1), so its measurement is its own.

**Section 19's seam (H24 to H31, not built here).** Pass 1 of the read loop is this call with
one optional field more, ``reads`` (N21): `SCHEMA_OF` maps a prompt version to its schema, so
pass 1 registers ``("heal_analysis", 2)`` as `Analysis` plus ``reads`` and pass 2 keeps
`Analysis`, which has none; `check` is where ``read:<n>`` references are resolved then.

**What is kept** (`record`, the network's ``heal/analyses.jsonl``, owner-only, append-only):
one ``asked`` row per incident (the claim, so an incident is analysed once, `claim`), then its
``analysis`` row (the state, its words, what is drawn, the call's id, the pack as sent and
hashed), and the notifier's ``notice`` rows. The newest analysis of an incident is the one
drawn (`latest`).
"""

import json
import logging
import os
import time
from enum import Enum

from modules.ai import calls, gateway
from modules.ai.explain import Hypothesis
from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)

#: The task (`profiles.TASKS`'s pin) and the background feature (`background.FEATURES`).
FEATURE = "heal_analysis"
PROMPT = ("heal_analysis", 1)
#: The finding kind its trigger names (`triggers.background`'s *finding_kind*).
FINDING = "heal_incident"
#: The outcomes that stop at can't fix (section 12's trigger): the decision's, and an act's
#: that notifies as a can't-fix (section 4: configuration healed and the symptom remains;
#: verify failed and Mercury undid its own fix, the V1 case).
CANT_FIX = ("cant_fix", "symptom_remains", "rolled_back")
#: The pack's sections, in the order the pack format names them.
SECTIONS = ("incident", "device", "history", "intent", "neighbours", "observed", "health",
            "observer", "logs", "tried")
#: The can't-fix incidents a day are measured over this many days of the heal's own record.
FREQUENCY_DAYS = 14
#: At most this many hypotheses (Explain's).
MAX_HYPOTHESES = 3
#: The store's file, in the network's heal folder.
FILE = "analyses.jsonl"
ROWS = ("asked", "analysis", "notice")
#: Each state of an analysis, and the words the row and the message draw for it (section 12,
#: "A failure or refusal is stated in place": a failure is never a silent absence).
STATES = ("answered", "pending", "off", "capped", "couldnt_analyse", "no_answer",
          "unanswerable", "not_cant_fix")
LABEL = "Advisory (beta), a person should confirm"
PENDING_WORDS = "AI analysis: pending"
#: The gateway's refusals that are the feature or hosted AI being off, and what each says.
OFF_KINDS = {"feature_off": "off for this network", "ai_off": "hosted AI is off",
             "no_key": "no Anthropic API key is set", "classified": "the network's "
             "classification marking forces AI off"}
#: The cap refusals (the feature's own, and the installation's day cap or per-call cap).
CAP_KINDS = ("feature_cap", "over_cap")
#: The provider not answering (the adapter's kinds).
NO_ANSWER_KINDS = ("provider_down", "rate_limited", "overloaded")
#: The steps, for the manual's How it works page (H10).
STEPS = (("finding", "Self-healing stopped at can't fix: the only finding that asks"),
         ("pack", "Build the incident's pack and what Mercury tried, its configuration by kind"),
         ("ask", "One background call through the AI gateway, if the feature is on for the "
                 "network and within its caps"),
         ("check", "Check every citation and every next step, as Explain's answers are"),
         ("keep", "Keep it with the incident; the notice and Needs attention draw it"))

#: The analysis's measured reliability (15.12), the one record its label's figure is drawn from:
#: None until H13 measures its three recorded cases (C4, I5, V1), ten runs each. It never
#: borrows Explain's figure (`explain.MEASURED` is of Explain's prompt and alerts).
MEASURED = None


class Outcome(str, Enum):
    answer = "answer"
    refuse = "refuse"


@register("heal_analysis", 1)
class Analysis(StrictModel):
    """Shape B, Explain's: the rationale first, then the hypotheses (each a claim, what it
    cites, and the next step: one read-only read), or why the evidence cannot say."""
    outcome: Outcome
    rationale: str
    hypotheses: list[Hypothesis]
    needs_human: bool
    why_not: str


#: Each prompt version's answer schema (section 19's pass 1 adds ("heal_analysis", 2) here).
SCHEMA_OF = {1: Analysis}


class Refused(ValueError):
    """Nothing was asked; the words say why."""


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


# ── The label ─────────────────────────────────────────────────────────────────────────────────

def beta(measured: dict = None) -> dict:
    """The "Advisory (beta)" label every analysis is drawn with: ``{"label", "state", "words"}``,
    its measured score from *measured* (`MEASURED` by default) when it is of the prompt and the
    model pinned now, else said not measured; never a figure measured on another prompt."""
    from modules.ai import profiles

    m = MEASURED if measured is None else measured
    pin = profiles.task(FEATURE)["model"]
    if m and tuple(m.get("prompt") or ()) == tuple(PROMPT) and m.get("model") == pin:
        return {"label": LABEL, "state": "measured",
                "words": (f"{m['reliable']} of {m['cases']} recorded cases reliable, "
                          f"{m['runs']} runs each ({m['at']})")}
    return {"label": LABEL, "state": "not_measured",
            "words": (f"not measured yet: {PROMPT[0]} v{PROMPT[1]} on {pin} is measured on "
                      "three recorded cases, ten runs each, before it is shown with a score")}


# ── The store ─────────────────────────────────────────────────────────────────────────────────

def path(network: str) -> str:
    from modules.heal.incidents import _dir

    return os.path.join(_dir(network), FILE)


def _append(network: str, row: dict, now: float = None) -> dict:
    from modules import filestore
    from modules.config import open_secure
    from modules.nsot import listref

    if not network or not listref.exists(network):
        raise Refused(f"{network or 'no network'} is no network, so nothing is kept")
    if row.get("row") not in ROWS:
        raise Refused(f"an analysis row is one of {', '.join(ROWS)}, not {row.get('row')!r}")
    from modules import redact

    now = time.time() if now is None else float(now)
    # Every string masked before it is kept (a secret's position and value never reach the
    # store), as the step log's are.
    kept = redact.redact_payload(dict(row, network=network, at=_iso(now), epoch=now))
    p = path(network)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with filestore.PathLock(p):
        with open_secure(p, "a") as fh:
            fh.write(json.dumps(kept, sort_keys=True) + "\n")
    return kept


def read(network: str) -> dict:
    """``{"state": "ok"|"absent"|"unreadable", "rows", "error"}``, oldest first; a line that
    will not parse makes the read unreadable, never a row quietly missing."""
    p = path(network)
    if not os.path.exists(p):
        return {"state": "absent", "rows": [], "error": ""}
    try:
        with open(p, encoding="utf-8") as fh:
            rows = [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "rows": [],
                "error": f"{network}'s AI analyses cannot be read ({type(exc).__name__})"}
    return {"state": "ok", "rows": rows, "error": ""}


def claim(network: str, incident_id: str, *, job: str, device: str = "",
          now: float = None) -> bool:
    """Take *incident_id* for its one analysis: True when this call took it (its ``asked``
    row written), False when it was taken before. Under the store's lock across processes, so
    two runners never both ask. Raises when the store cannot be read: an incident is never
    asked about twice because its record could not be read."""
    from modules import filestore
    from modules.config import open_secure
    from modules.nsot import listref

    if not network or not listref.exists(network):
        raise Refused(f"{network or 'no network'} is no network, so nothing is kept")
    now = time.time() if now is None else float(now)
    p = path(network)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with filestore.PathLock(p):
        got = read(network)
        if got["state"] == "unreadable":
            raise RuntimeError(got["error"])
        if any(r.get("row") == "asked" and r.get("incident") == incident_id
               for r in got["rows"]):
            return False
        with open_secure(p, "a") as fh:
            fh.write(json.dumps({"row": "asked", "incident": incident_id, "device": device,
                                 "job": job, "network": network, "at": _iso(now),
                                 "epoch": now}, sort_keys=True) + "\n")
    return True


def latest(network: str, incident_id: str, rows=None) -> dict:
    """The newest ``analysis`` row of *incident_id*, or ``{}``; *rows* the store's, read once by
    a caller drawing many. Raises when the store cannot be read."""
    if rows is None:
        got = read(network)
        if got["state"] == "unreadable":
            raise RuntimeError(got["error"])
        rows = got["rows"]
    found = [r for r in rows if r.get("row") == "analysis" and r.get("incident") == incident_id]
    return found[-1] if found else {}


def record(network: str, result: dict, now: float = None) -> dict:
    """Keep one analysis (`analyse`'s result) as its incident's ``analysis`` row."""
    keep = {k: result.get(k) for k in ("incident", "device", "state", "words", "label",
                                       "answer", "call_id", "cost_usd", "pack_id", "pack",
                                       "error", "detail", "cap", "topology", "job")
            if k in result}
    return _append(network, dict(keep, row="analysis"), now)


def record_notice(network: str, incident_id: str, *, event: str, analysis_state: str,
                  delivery: dict, now: float = None) -> dict:
    """The notifier's ``notice`` row: which event was sent for the incident, the analysis's
    state it carried (``pending`` for the first message of a slow one), and what was
    delivered (counts only, never a message's text)."""
    said = {k: (delivery or {}).get(k) for k in ("ok", "sent", "failed", "error")}
    return _append(network, {"row": "notice", "incident": incident_id, "event": event,
                             "analysis_state": analysis_state, "delivery": said}, now)


# ── Its frequency, for the estimate (background.FEATURES' "frequency") ───────────────────────

def cant_fix_frequency(network: str, now: float = None) -> dict:
    """``{"per_day", "basis"}``: the network's can't-fix incidents a day over the last
    `FREQUENCY_DAYS` days of the heal's own step log (the record's age when it is younger, a
    day at least); unknown (None), never guessed, when the heal has recorded nothing on the
    network or its step log cannot be read."""
    from modules.heal import steplog

    now = time.time() if now is None else float(now)
    got = steplog.incidents(network)
    if got["state"] == "unreadable":
        return {"per_day": None, "basis": f"the heal step log cannot be read ({got['error']})"}
    if got["state"] == "absent" or not got["entries"]:
        return {"per_day": None, "basis": (f"self-healing has recorded nothing on {network} "
                                           "yet, so how often it stops at can't fix is not "
                                           "measured")}
    since = now - FREQUENCY_DAYS * 86400
    first = min(float(e.get("epoch") or now) for e in got["entries"])
    days = max(1.0, (now - max(since, first)) / 86400)
    n = sum(1 for e in got["entries"] if e.get("outcome") in CANT_FIX
            and float(e.get("epoch") or 0) >= since)
    return {"per_day": n / days, "basis": (f"{n} can't-fix incident(s) in the heal's step log "
                                           f"over {days:.1f} day(s) on {network}")}


# ── The request ───────────────────────────────────────────────────────────────────────────────

def tried_format() -> str:
    """What the tried section is and how its configuration is said: the same bytes on every
    call (the cached prefix)."""
    from modules import evidence_pack as EP

    return "\n".join([
        "tried is each step Mercury's self-healing took for the incident, in order: the "
        "decision's steps (" + ", ".join(n for n, _w in _decide_steps()) + ") and, when it "
        "applied a fix, the act's (" + ", ".join(n for n, _w in _act_steps()) + "), each with "
        "its result (ok, refused, failed, running, or the outcome it ended on) and Mercury's "
        "words. A piece's reference is tried:<n>, its place.",
        "After the steps come the units the decision found, each by its kind, what departed "
        "and how many lines, and then the program by its size and its hash.",
        "Configuration is never sent as text from the step log: a line it held is "
        f"{EP.WITHHELD!r} in a step's words, and a unit says 'content withheld'. The intent "
        "section's lines are the committed golden's difference from intent, masked.",
        "The section's outcome is where self-healing stopped: can't fix (it will not or cannot "
        "fix this kind), symptom remains (the configuration healed, the symptom did not "
        "clear), or rolled back (verify failed and Mercury undid its own fix)."])


def _decide_steps():
    from modules.heal import decide
    return decide.STEPS


def _act_steps():
    from modules.heal import act
    return act.STEPS


def vocabulary() -> str:
    """The pack's format for an incident's pack: Explain's (`explain.vocabulary`) over this
    pack's sections."""
    from modules.ai import explain

    return explain.vocabulary(SECTIONS)


def context(topo: dict = None) -> dict:
    """The cached prefix: the pack's format and the tried section's, and the network's summary
    and the topology's format when the topology is sent."""
    from modules import network_model as NM

    out = {"pack_format": vocabulary(), "tried_format": tried_format()}
    if topo and topo.get("sent"):
        out["network"] = topo["summary"]
        out["topology_format"] = NM.FORMAT
    return out


def parts(pack: dict, sections: list, topo: dict = None) -> dict:
    """The call's own data: the topology (when sent, or why it could not be read), the pack's
    sections as sent, and the incident's own words, which sort last."""
    from modules.ai import explain

    tried = next((s for s in sections if s.get("name") == "tried"), {})
    out = {"pack": json.dumps([explain.as_sent(s) for s in sections], sort_keys=True,
                              ensure_ascii=False, separators=(",", ":")),
           "the_incident": (f"self-healing stopped at "
                            f"{(tried.get('outcome') or 'cant_fix').replace('_', ' ')} on "
                            f"{pack.get('device') or 'no one device'}")}
    if topo and topo.get("yaml"):
        out["network_topology"] = topo["yaml"]
    return out


def gather(network: str, incident_id: str, now: float = None) -> dict:
    """What the analysis reads, deterministic and before any call: ``{"entry", "incident",
    "units"}``: the incident's step log entry (raises when the step log cannot be read: an
    analysis of what is unread is never made), the incident's record, and its decisions' masked
    units. Raises Refused when the incident did not stop at can't fix (the only finding)."""
    from modules.heal import decisions, incidents, steplog

    entry = steplog.incident(network, incident_id)
    if not entry:
        raise Refused(f"the step log holds no incident {incident_id} on {network}, so there is "
                      "nothing to analyse")
    if entry.get("outcome") not in CANT_FIX:
        raise Refused(f"incident {incident_id} ended {entry.get('outcome') or 'undecided'!r}, "
                      f"not at can't fix ({', '.join(CANT_FIX)}): only a can't-fix asks for an "
                      "analysis, and nothing was sent")
    got = incidents.read(network)
    incident = next((i for i in got.get("incidents") or [] if i.get("id") == incident_id), {})
    units = []
    for did in entry.get("decisions") or []:
        units += list((decisions.find(network, did) or {}).get("units") or [])
    return {"entry": entry, "incident": incident, "units": units}


def prepare(network: str, incident_id: str, *, now: float = None, loki=None,
            prometheus=None) -> dict:
    """The request for *incident_id*, before any call: ``{"pack", "topo", "sections", "data",
    "ctx", "subject", "said"}`` (`gather`, `evidence_pack.build_incident`, Explain's class
    gates). Raises Refused for an incident that is not a can't-fix, or a network whose marking
    forces AI off."""
    from modules import evidence_pack as EP
    from modules.ai import egress_classes, explain

    got = gather(network, incident_id, now)
    entry = got["entry"]
    marked = egress_classes.classification_marking(network)
    if marked:
        raise Refused(f"{network} carries the classification marking {marked!r}, which forces "
                      "AI off: nothing was sent")
    pack = EP.build_incident(network, got["incident"], entry, got["units"],
                             now=float(entry.get("epoch") or 0) or now, loki=loki,
                             prometheus=prometheus)
    return dict(request_of(pack), entry=entry, units=got["units"])


def request_of(pack: dict) -> dict:
    """The request for an incident's *pack* as built (`evidence_pack.build_incident`), or as
    recorded (H13's cases: a pack captured in a lab run, replayed with no store read):
    ``{"pack", "topo", "sections", "said", "data", "ctx", "subject"}``, Explain's class gates
    asked (`explain.topology`, `explain.sent_sections`)."""
    from modules.ai import explain

    topo = explain.topology(pack)
    sections = explain.sent_sections(pack, topo)
    said = {"sent": topo["sent"], "why": topo["why"], "network": topo["network"],
            "subject": topo["subject"], "hops": explain.HOPS, "version": topo["version"],
            "devices": sorted(topo["reached"]), "observed": topo["observed"]}
    return {"pack": pack, "topo": topo, "sections": sections, "said": said,
            "data": parts(pack, sections, topo), "ctx": context(topo),
            "subject": {"kind": FINDING, "id": pack.get("incident") or "",
                        "devices": [pack["device"]] if pack.get("device") else []}}


def trigger_for(network: str, incident_id: str, job: str) -> dict:
    """The background trigger of an analysis (section 12: its trigger named), its network the
    network's one id (`listref.network_id`, what `background.admit` compares)."""
    from modules.ai import triggers
    from modules.nsot import listref

    return triggers.background(FEATURE, job, listref.network_id(network), FINDING, incident_id)


# ── The check ─────────────────────────────────────────────────────────────────────────────────

def check(answer: Analysis, pack: dict, sections: list, topo: dict) -> dict:
    """Explain's check on what was sent (`explain.check`, with its normalising and Mercury's
    citations, `explain.normalised` and `mercury_cites`): ``{"why", "answer", "added",
    "written"}``, *why* "" when every reference resolves, every next step is an allowed read
    and every device named is cited. The model's own answer stays as received in the call's
    record."""
    from modules.ai import explain
    # Explain's validation of an answer against what was sent (no call to the model), named
    # apart from the gateway's own entries, which tests/test_ai_triggers.py reads by name.
    from modules.ai.explain import check as explain_answer_check

    ids = topo["ids"] if topo.get("sent") else ()
    names = topo.get("names") if topo.get("sent") else None
    sent = {"sections": list(sections)}
    normal, written = explain.normalised(answer, sent, ids)
    added = explain.mercury_cites(normal, sent, explain.sent_names(names, ids),
                                  pack.get("device") or "")
    why = explain_answer_check(normal, pack, ids, sections=sections, names=names,
                               added=[a["ref"] for a in added])
    if not why and len(normal.hypotheses) > MAX_HYPOTHESES:
        why = f"{len(normal.hypotheses)} hypotheses; at most {MAX_HYPOTHESES} are taken"
    return {"why": why, "answer": normal, "added": added, "written": written}


# ── The call ──────────────────────────────────────────────────────────────────────────────────

def words_of(state: str, detail: str = "", cap: str = "") -> str:
    """What the row and the message say for an analysis in *state* (section 12's words)."""
    if state == "answered":
        return f"AI analysis: {LABEL}"
    if state == "pending":
        return PENDING_WORDS
    if state == "off":
        return f"AI analysis: not run, {detail or 'off for this network'}"
    if state == "capped":
        return (f"AI analysis: not run, its cap for "
                f"{'this month' if cap == 'month' else 'today'} is reached")
    if state == "no_answer":
        return f"AI analysis: the provider did not answer within {detail}"
    if state == "unanswerable":
        return f"AI analysis: the evidence cannot say: {detail}"
    if state == "not_cant_fix":
        return f"AI analysis: not asked: {detail}"
    return f"AI analysis: couldn't analyse: {detail}"


def _bound_words(seconds: float) -> str:
    return f"{int(round(seconds))} s"


def _failed(got: dict) -> dict:
    """A gateway refusal or failure as the analysis's state, its words in place."""
    kind, detail = got.get("error") or "", got.get("detail") or ""
    if kind in OFF_KINDS:
        return {"state": "off", "words": words_of("off", OFF_KINDS[kind])}
    if kind in CAP_KINDS:
        cap = got.get("cap_kind") or ("month" if "month cap" in detail else "day")
        return {"state": "capped", "cap": cap, "words": words_of("capped", cap=cap)}
    if kind in NO_ANSWER_KINDS:
        return {"state": "no_answer",
                "words": words_of("no_answer", _bound_words(gateway.send_bound_s()))
                + f" ({kind}: {detail[:160]})"}
    return {"state": "couldnt_analyse",
            "words": words_of("couldnt_analyse", f"{kind}: {detail[:200]}" if kind else detail)}


def shown(answer: Analysis, added: list) -> dict:
    """What is drawn of a checked answer: the rationale, each hypothesis's claim, what it cites
    and its next step, and Mercury's citations apart from the model's."""
    return {"rationale": answer.rationale, "needs_human": bool(answer.needs_human),
            "hypotheses": [{"claim": h.claim, "cites": list(h.evidence_refs),
                            "next": h.confirm_with} for h in answer.hypotheses],
            "mercury_cites": [{"device": a["device"], "ref": a["ref"]} for a in added]}


def analyse(network: str, incident_id: str, *, job: str, send=None, today: str = None,
            now: float = None, keep: bool = True, loki=None, prometheus=None) -> dict:
    """One analysis of a can't-fix incident: ``{"ok", "state", "words", "label", "answer",
    "call_id", "cost_usd", "pack_id", "incident", "device", ...}``, kept with the incident
    (*keep*) whatever its state. Asked only of an incident that stopped at can't fix; one
    background call through the gateway (its trigger named, `trigger_for`), its answer checked
    (`check`) before anything of it is drawn. Never raises: a step log that cannot be read is
    said, and nothing is sent."""
    label = beta()
    base = {"incident": incident_id, "label": label, "job": job, "ok": False, "answer": None,
            "call_id": "", "cost_usd": 0.0, "pack_id": "", "device": ""}
    try:
        prep = prepare(network, incident_id, now=now, loki=loki, prometheus=prometheus)
    except Refused as exc:
        out = dict(base, state="not_cant_fix", detail=str(exc),
                   words=words_of("not_cant_fix", str(exc)))
        return _kept(network, out, keep)
    except Exception as exc:                          # said, and nothing is sent
        log.error("heal analysis: %s's incident %s could not be read: %s", network,
                  incident_id, exc)
        out = dict(base, state="couldnt_analyse", detail=str(exc), words=words_of(
            "couldnt_analyse", f"what it reads could not be read ({type(exc).__name__}: "
                               f"{exc}); nothing was sent"))
        return _kept(network, out, keep)
    out = ask_prepared(prep, trigger=trigger_for(network, incident_id, job), send=send,
                       today=today, base=base)
    return _kept(network, out, keep)


def ask_prepared(prep: dict, *, trigger: dict, send=None, today: str = None,
                 base: dict = None) -> dict:
    """One call for a prepared request (`prepare`, or `request_of` of a recorded pack), its
    answer checked: the result `analyse` keeps. **H13's seam:** a recorded incident pack is
    asked as the feature asks it, ``ask_prepared(request_of(pack), trigger=<an evaluation
    run's, triggers.evaluation>)``, the same request and the same check, kept nowhere; its three
    recorded cases (C4, I5, V1) ten runs each are that, or `gateway.ask_batch` over
    `request_of`'s parts."""
    from modules.ai import triggers

    pack = prep["pack"]
    incident_id = pack.get("incident") or ""
    base = dict(base or {"incident": incident_id, "label": beta(), "job": "", "ok": False,
                         "answer": None, "call_id": "", "cost_usd": 0.0},
                pack_id=pack["id"], device=pack.get("device") or "", pack=pack,
                topology=prep["said"])
    actor = triggers.actor_of(trigger)
    got = gateway.ask(FEATURE, PROMPT, SCHEMA_OF[PROMPT[1]], prep["data"], actor=actor,
                      trigger=trigger, context=prep["ctx"], send=send, today=today,
                      subject=prep["subject"], network=trigger.get("network") or
                      pack.get("network") or "")
    base.update(call_id=got.get("call_id") or "", cost_usd=float(got.get("cost_usd") or 0.0))
    links = {"page": f"/v2/device/{base['device']}?tab=history", "anchor": f"heal-{incident_id}"}
    if not got.get("ok"):
        return dict(base, error=got.get("error") or "", detail=got.get("detail") or "",
                    **_failed(got))
    checked = check(got["output"], pack, prep["sections"], prep["topo"])
    if checked["why"]:
        calls.record_use(got["call_id"], "refused by validation", actor=actor,
                         detail=checked["why"], links=links)
        return dict(base, state="couldnt_analyse", detail=checked["why"],
                    words=words_of("couldnt_analyse", f"{checked['why']}; nothing is shown"))
    answer = checked["answer"]
    if answer.outcome.value == "refuse":
        calls.record_use(got["call_id"], "shown: the evidence cannot say", actor=actor,
                         detail=answer.why_not[:200], links=links)
        return dict(base, state="unanswerable", detail=answer.why_not[:200],
                    words=words_of("unanswerable", answer.why_not[:200]))
    note = "; ".join(f"cited by Mercury: {a['device']} by the pack's {a['ref']}"
                     for a in checked["added"])
    calls.record_use(got["call_id"], "shown: advisory analysis", actor=actor, links=links,
                     **({"detail": note[:800]} if note else {}))
    return dict(base, ok=True, state="answered", words=words_of("answered"),
                answer=shown(answer, checked["added"]))


def _kept(network: str, out: dict, keep: bool) -> dict:
    if not keep:
        return out
    try:
        record(network, out)
        out["kept"] = True
    except Exception as exc:                          # said on the result, never raised
        log.error("heal analysis: %s's analysis of %s was not kept: %s", network,
                  out.get("incident"), exc)
        out["kept"] = False
    return out


# ── What is drawn: the Needs attention row's block and the message's ─────────────────────────

def block(result: dict) -> dict:
    """The analysis as the row and the message draw it, after Mercury's facts: ``{"state",
    "words", "label", "score", "rationale", "hypotheses": [{"claim", "next", "cites"}]}``. A
    state with no answer draws its words alone (pending, off, capped, couldn't analyse, the
    provider not answering): never a silent absence."""
    if not result:
        return {"state": "pending", "words": PENDING_WORDS, "label": "", "score": "",
                "rationale": "", "hypotheses": []}
    label = result.get("label") or beta()
    out = {"state": result.get("state") or "couldnt_analyse",
           "words": result.get("words") or words_of("couldnt_analyse", "no words recorded"),
           "label": "", "score": "", "rationale": "", "hypotheses": []}
    if out["state"] == "answered" and result.get("answer"):
        a = result["answer"]
        out.update(label=label.get("label") or LABEL, score=label.get("words") or "",
                   rationale=a.get("rationale") or "",
                   hypotheses=[{"claim": h.get("claim") or "", "next": h.get("next") or "",
                                "cites": list(h.get("cites") or [])}
                               for h in a.get("hypotheses") or []][:MAX_HYPOTHESES])
    return out


def drawn(network: str, incident_id: str) -> dict:
    """The Needs attention row's block for *incident_id* (`block` of its newest analysis):
    ``{"state": "ok"|"unreadable", "error", "block"}``; an incident not yet analysed draws
    pending."""
    from modules.ai import profiles

    pin = profiles.task(FEATURE)
    words = f"{pin['words']}: {pin['model']}, a background call"
    got = read(network)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "error": got["error"], "block": {},
                "provenance": {"task_words": words}}
    kept = latest(network, incident_id, got["rows"])
    return {"state": "ok", "error": "", "block": block(kept),
            "provenance": {"incident": incident_id, "call_id": kept.get("call_id") or "",
                           "cost_usd": float(kept.get("cost_usd") or 0.0),
                           "at": kept.get("at") or "", "task_words": words}}


def capped(network: str, rows=None, now: float = None) -> dict:
    """The newest analysis on *network* stopped at a cap, while that cap's period lasts:
    ``{"incident", "cap", "at", "ends", "words"}``, or ``{}`` (Needs attention's
    ``heal``/``analysis_capped``). A later analysis that ran, or the period's end, clears it.
    The period is the cap's own: its day turns over at the stated day boundary
    (`calls.resets_at`), its month at the first midnight of the next month there."""
    import datetime

    now = time.time() if now is None else float(now)
    if rows is None:
        got = read(network)
        if got["state"] == "unreadable":
            raise RuntimeError(got["error"])
        rows = got["rows"]
    done = [r for r in rows if r.get("row") == "analysis" and r.get("state") not in (
        "not_cant_fix",)]
    if not done or done[-1].get("state") != "capped":
        return {}
    last = done[-1]
    at = float(last.get("epoch") or 0)
    when = datetime.datetime.fromtimestamp(at, datetime.timezone.utc)
    nxt = calls.resets_at(when)
    if last.get("cap") == "month":
        # Each next day's midnight until the month turns, at most 31 of them.
        month = calls.day_of(when)[:7]
        for _ in range(31):
            if calls.day_of(nxt)[:7] != month:
                break
            nxt = calls.resets_at(nxt)
    ends = nxt.timestamp()
    if now >= ends:
        return {}
    return {"incident": last.get("incident") or "", "cap": last.get("cap") or "day",
            "at": at, "ends": ends, "words": last.get("words") or ""}
