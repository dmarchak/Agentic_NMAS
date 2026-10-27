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
- **The topology** (PHASE8_PLAN 15.15, the topology class of 15.11): the network model's
  subgraph within `HOPS` of the alert's device (`network_model.context_for`), overlaid with
  the observed adjacencies and cables THE PACK CAPTURED when the alert was found firing
  (`evidence_pack.overlay_of`, C1712): Explain reads no observed state itself, so a past
  alert is never explained against the network now, and a pack built before overlays were
  captured says so on every item. The network's summary and the subgraph's format in the
  cached prefix. Sent unless the network turns the class off
  (`egress_classes.topology_allowed`), and the result says whether it was and why not. The
  pack's `observed` section is never sent as pack data: it is the topology class, sent only
  inside the subgraph.
- **The health figures** (C1714): the pack's `health` section, the allowed class (metric
  series), each figure a piece cited by its id (``health:<device id>:<figure>``). With the
  topology class off, only the alert's device's own figures are sent: who sits within two hops
  of it is topology.
- **The other alerts** (C1850): the pack's `concurrent` section, every other alert of the
  network around the onset from the alert history, each cited ``concurrent:<episode id>``.
- **One device, one id** (C1849, `one_id`): the pack as sent names each device the topology
  names by the topology's id; a stored pack naming it otherwise (built before its ids were the
  model's) is translated as it is sent, never rewritten, and the check takes what was sent.
- **A rebuilt pack's topology is of now** (C1851, `as_now_of`): the subgraph sent with a pack
  built after its alert says it is the network model as it is now, which may differ from then.
- **The check** (`check`): every reference must resolve to what was SENT, a piece of the pack
  as sent or an id of the topology sent, and every `confirm_with` must be a read on the
  read-only allowlist (`readonly_commands`); one that does not is "couldn't analyse", naming
  it, and nothing is shown (the card's kill criterion: one claim shown with a reference that
  does not resolve). No tool is offered.

**The request's order** (the operator, 2026-10-25): the stable context first, cached (the
prompt, then the network summary, the pack's format and the topology's format: the same bytes
on every call for the network while its model holds); the call's own data last, uncached (the
subgraph, the pack, and the alert itself). Network notes, when they exist, go in the context
beside the summary; none exist yet.
"""
import json
import logging
from enum import Enum

from modules.ai import calls, gateway
from modules.ai.needs import Need
from modules.ai.schemas import StrictModel, register

log = logging.getLogger(__name__)

FEATURE = "explain"
PROMPT = ("explain", 4)
#: Prompt v1's request (before the topology, 15.15, and the health figures, C1714): its
#: sections and its data blocks, kept so a replay can ask both ways (scripts/nmas-pack-replay).
V1_SECTIONS = ("alert", "device", "history", "intent", "neighbours", "logs")
#: At most this many hypotheses (the card's "top hypothesis" and two behind it).
MAX_HYPOTHESES = 3
#: The topology sent: the alert's device and everything one link, adjacency or cable from it
#: (the operator's ruling: context_for(subject, hops=1)).
HOPS = 1
#: Pack sections never sent as pack data: the observed overlay rides inside the subgraph (the
#: topology class), never beside it.
NOT_SENT = ("observed",)
STEPS = (
    ("pack", "the alert's stored evidence pack, its hash checked: a pack changed since it was "
             "built is refused"),
    ("topology", "the network model's part around the alert's device, one hop: devices, "
                 "links, subnets, expected adjacencies, and the observed ones the pack "
                 "captured when the alert fired (never read again later); no configuration "
                 "line; sent unless the network turns the topology class off"),
    ("ask", "one recorded, capped call through the AI gateway, as the person who pressed "
            "Explain: the pack, its health figures for the devices within two hops, and the "
            "topology as data, no tool offered"),
    ("check", "every reference resolves to the pack or to the topology as sent, and every "
              "confirming read is on the read-only allowlist; no fault found cites the "
              "evidence it checked, each piece read; one that does not is couldn't analyse, "
              "and nothing is shown"),
    ("show", "the hypotheses drawn beside the pack, or no fault found with what it checked, "
             "each reference linked to its piece; nothing runs"),
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


class Assessment(str, Enum):
    """Schema v2's outcome: a cause hypothesised, no fault found in the evidence checked
    (C1742), or the pack cannot say."""
    answer = "answer"
    no_fault_found = "no_fault_found"
    refuse = "refuse"


@register("explain", 2)
class ExplanationV2(StrictModel):
    """Shape B with a "no fault found" assessment (the operator's ruling, 2026-10-25, C1742:
    a tool that cannot say nothing is wrong will always invent something): no hypothesis, and
    `checked` cites the healthy evidence the model checked, never a free-text guess."""
    outcome: Assessment
    rationale: str
    hypotheses: list[Hypothesis]
    checked: list[str]
    needs_human: bool
    why_not: str


@register("explain", 3)
class ExplanationV3(StrictModel):
    """Prompt v6's answer (the network-context version, the operator, 2026-10-26): v2's, and
    `needs`, what the answer lacked that Mercury looks up once (`modules/ai/needs.py`, C1780)."""
    outcome: Assessment
    rationale: str
    hypotheses: list[Hypothesis]
    checked: list[str]
    needs_human: bool
    why_not: str
    needs: list[Need]


#: Each prompt version's answer schema: v1 to v3 were written for `Explanation`, v4 for
#: `ExplanationV2`, so a replay asking v1 asks it as it was.
SCHEMA_OF = {1: Explanation, 2: Explanation, 3: Explanation, 4: ExplanationV2,
             5: ExplanationV2, 6: ExplanationV3}
#: Candidate prompts, asked only by a replay (`nmas-pack-replay --prompt N`) until proved.
#: v5 adds general Analyst guidance ("when symptoms appear on several devices in the same
#: window, consider a common cause beneath them early"; the operator, 2026-10-26); it stays
#: rejected. v6, the network-context version, is built from v4 (the operator, 2026-10-26):
#: the coverage header's line (say when an answer rests on a layer not collected), the pack's
#: endpoints (C1778), the needs round (C1780), and a pack section rebuilt afterwards never
#: read as observed at the time (alert history, C1808); adopted only by the operator's bar.
CANDIDATES = (("explain", 5), ("explain", 6))
#: A checked piece's states that were read (pack_format: only ok and empty are evidence).
READ_STATES = ("ok", "empty")


def vocabulary(sections=None) -> str:
    """The pack's format and the reads a hypothesis may name, the same bytes on every call.
    *sections* the sections it names (v1's six for a v1 request); by default every section
    sent as pack data, and the health figures' ids."""
    from modules import evidence_health as H
    from modules import evidence_pack as EP
    from modules import readonly_commands as R

    names = list(sections) if sections is not None else [
        s for s in EP.SECTIONS if s not in NOT_SENT]
    lines = [
        "An evidence pack has sections, each with a reference (its name), a state, its source "
        "and when it was read, and pieces, each with its own reference (section:n).",
        "Sections: " + "; ".join(f"{k} = {EP.SECTION_WORDS[k]}" for k in names),
        "States: " + ", ".join(EP.STATES) + " (only ok and empty were read; absent, "
        "not_configured and unreadable are not evidence)",
    ]
    if "health" in names:
        lines.append(
            "health holds a few figures for each device within two hops of the alert's device "
            "(hop 0 is that device; a shared segment's members are one hop), each one line "
            "summarising the incident's window (the section's window: from 15 minutes before "
            "the onset to the alert's time, as_of), its times in UTC: "
            + "; ".join(f"{k} = {H.FIGURE_WORDS[k]}" for k in H.FIGURES)
            + ". A figure's reference is health:<device id>:<figure>, the device id the "
            "topology gives the device. A figure whose state is not ok was not measured: it "
            "says why, and is not a zero. The section's lines hold the figures, "
            + H.LINE_FORMAT)
    if "concurrent" in names:
        lines.append(
            "concurrent lists every other alert in the same network active in the section's "
            "window (from 15 minutes before the onset to the alert's time), as it stood at the "
            "alert's time: its rule, its device (with the device's id where the topology knows "
            "it) or address, its state then, when it started, fired and resolved (blank when "
            "not by then), and same_alert when it is an earlier episode of this alert; "
            "Grafana's times, UTC. A piece's reference is concurrent:<episode id>, as written.")
    if "health" in names or "concurrent" in names:
        lines.append(
            "One device has one id in everything sent (the pack and the topology): cite a "
            "device's figures and items by the id given for it, exactly as written.")
    lines += [
        "A confirming read is one command a person may run on the device, read-only: it begins "
        "with one of " + ", ".join(R.READ_ONLY_VERBS) + "; a pipe may follow with "
        + ", ".join(R.SAFE_MODIFIERS),
        f"At most {MAX_HYPOTHESES} hypotheses, the most likely first.",
    ]
    return "\n".join(lines)


def topology(pack: dict) -> dict:
    """What of the network goes with the pack: ``{"sent", "why", "summary", "yaml", "ids",
    "reached", "version", "subject", "observed"}``. Not sent when the pack names no one device
    of one network or the network turns the class off; when the model cannot be built, the
    call carries that it could not be read (``yaml``), and nothing of it is cited. The
    observed overlay is the pack's own capture (`evidence_pack.overlay_of`), never a read."""
    from modules import evidence_pack as EP
    from modules import network_model as NM
    from modules.ai import egress_classes

    network, device = pack.get("network") or "", pack.get("device") or ""
    out = {"sent": False, "why": "", "summary": "", "yaml": "", "ids": [], "reached": {},
           "version": "", "subject": device, "network": network, "observed": "",
           "names": {}, "as_now": ""}
    gate = egress_classes.topology_allowed(network)
    if not gate["allowed"]:
        return dict(out, why=gate["why"])
    if not device:
        return dict(out, why="the alert is not one device's, so no part of the network is "
                             "picked out")
    overlay = EP.overlay_of(pack)
    as_now = as_now_of(pack)
    got = NM.context_for(network, device, hops=HOPS, overlay=overlay, carried=carried_layers(pack),
                         as_now=as_now)
    if not got["ok"]:
        return dict(out, why=f"the network model could not be read ({got['error']})",
                    yaml=f"could not read: the network model ({got['error']})")
    observed = (f"as of {overlay['as_of']}" if overlay["state"] == "read" else
                f"could not read ({overlay['why']})")
    return dict(out, sent=True, summary=got["summary"], yaml=got["yaml"], ids=got["ids"],
                reached=got["reached"], version=got["version"], observed=observed,
                names=got.get("names") or {}, as_now=as_now)


def as_now_of(pack: dict) -> str:
    """What the topology sent with a pack built AFTER its alert says of itself (C1851): the
    devices, links and expected adjacencies are the network model as it is when Explain is
    pressed, never as they were then; "" for a pack captured as its alert fired."""
    if pack.get("provenance") != "rebuilt":
        return ""
    from modules import network_model as NM
    model, _err = NM.model_for(pack.get("network") or "")
    if model is None:
        return ""
    words = NM.as_now_words(model, pack.get("built_at") or "")
    obs = next((s for s in pack.get("sections") or [] if s.get("name") == "observed"), {})
    if obs.get("provenance") == "missing" or obs.get("state") not in ("ok", "empty"):
        words += "; nothing observed then was captured, so observed says could not read"
    return words


#: The pack's sections that are a layer of the network context's coverage header.
CARRIED_LAYERS = {"health": "performance", "logs": "events", "endpoints": "endpoints"}


def carried_layers(pack: dict) -> dict:
    """The coverage header's layers this pack carries beside its topology: health is
    performance, the log lines are events, and the endpoints are endpoints (C1778), each
    present when its section was read (empty is read, with nothing in its window), else
    not_collected with the section's why (a pack before schema 3 holds no endpoints section,
    so that layer stays as the coverage header says it without one)."""
    out = {}
    for s in pack.get("sections") or []:
        layer = CARRIED_LAYERS.get(s.get("name"))
        if not layer:
            continue
        read = s.get("state") in ("ok", "empty")
        out[layer] = {"state": "present" if read else "not_collected",
                      "source": f"the evidence pack's {s['name']} section: {s.get('source', '')}",
                      "age": s.get("read_at") or "",
                      "why": "" if read else f"{s.get('state')}: {s.get('why', '')}"}
    return out


def sent_sections(pack: dict, topo: dict = None) -> list:
    """The pack's sections as they are sent: never the observed overlay (it rides in the
    subgraph); the health figures of the alert's device alone when no topology is sent (who
    is near it is topology), the rest said withheld. An SDN detection's ``sdn`` section (its
    flows and port rates, PHASE8_PLAN 17.1 S6) is the topology class: its pieces are sent only
    while the class is allowed for the pack's network (`egress_classes.topology_allowed`, asked
    of the class itself, since a controller's switch is no device the subgraph is drawn around),
    else withheld, saying why. With a topology sent, every device it knows is named by its id
    (`one_id`, C1849)."""
    from modules import evidence_pack as EP
    from modules.ai import egress_classes

    out = []
    for s in pack.get("sections") or []:
        if s.get("name") in NOT_SENT:
            continue
        if s.get("name") == EP.SDN_SECTION:
            gate = egress_classes.topology_allowed(pack.get("network") or "")
            if not gate["allowed"]:
                s = dict(s, pieces=[], withheld=(
                    "the flows and port rates are not sent: they are the topology class, and "
                    + gate["why"]))
        if s.get("name") == "endpoints" and not (topo or {}).get("sent"):
            # Endpoints (MAC, address, hostname) are the topology class (15.15, the
            # operator's ruling): with no topology sent, none of them is.
            s = dict(s, pieces=[], withheld=(
                "the endpoints are not sent: they are the topology class, and no topology "
                "was sent"))
        if s.get("name") == "health" and not (topo or {}).get("sent"):
            kept = [p for p in s.get("pieces") or [] if p.get("hop") == 0]
            if len(kept) < len(s.get("pieces") or []):
                s = dict(s, pieces=kept, withheld=(
                    "the figures of the devices around it are not sent: who is near the "
                    "device is the topology class, and no topology was sent"))
        out.append(s)
    # One device, one id, in the pack as sent and the topology sent (C1849).
    if (topo or {}).get("sent"):
        out, _back = one_id(out, topo.get("names") or {})
    return out


#: The sections whose pieces name a device by id (``dev``, beside its name ``device``), and so
#: carry it in their references (C1849).
DEVICE_ID_SECTIONS = ("health", "concurrent")


def one_id(sections: list, names: dict) -> tuple:
    """*sections* with every device the network model knows named by the model's id (*names*,
    the model's ids by name: the topology sent's), so one device has one id in all a call sends
    (C1849): a pack built before its ids were the model's (schema 4 and earlier, or built while
    the model could not be read) names a device ``dev:@<name>`` while the topology names it
    ``dev:<NetBox id>``; a model's id may also move (a device given a NetBox id later). Copies,
    never the stored pack (it is frozen and hashed): ``(sections, back)``, *back* each moved
    reference's pack reference, so a citation of what was sent is linked to its piece."""
    if not names:
        return list(sections), {}
    out, back = [], {}
    for s in sections:
        if s.get("name") not in DEVICE_ID_SECTIONS:
            out.append(s)
            continue
        pieces = []
        for p in s.get("pieces") or []:
            want = names.get(p.get("device") or "")
            have = p.get("dev") or ""
            if want and want != have and (have or s.get("name") == "concurrent"):
                ref = p.get("ref") or ""
                moved = ref.replace(f":{have}:", f":{want}:", 1) if f":{have}:" in ref else ref
                if moved != ref:
                    back[moved] = ref
                p = dict(p, dev=want, ref=moved)
            pieces.append(p)
        out.append(dict(s, pieces=pieces))
    return out, back


def as_sent(section: dict) -> dict:
    """A section as the model reads it: the health figures one line per device (the operator,
    2026-10-26, the approved trim; `evidence_health.lines`), every other section as stored.
    The check resolves against the pieces, which the pack keeps."""
    from modules import evidence_health as H

    if section.get("name") != "health":
        return section
    # The figures' words are the pack format's (the cached prefix), not repeated per call.
    out = {k: v for k, v in section.items() if k not in ("pieces", "figures")}
    out["lines"] = H.lines(section.get("pieces") or [])
    return out


def parts(pack: dict, topo: dict = None) -> dict:
    """The call's own data: the topology around the device (when sent, or why it could not be
    read), the pack's sections as sent, and the alert's own words, which sort last."""
    out = {"pack": json.dumps([as_sent(s) for s in sent_sections(pack, topo)], sort_keys=True,
                              ensure_ascii=False, separators=(",", ":")),
           "the_alert": f"{pack.get('rule', '')} on {pack.get('device') or 'no one device'}"}
    if topo and topo.get("yaml"):
        out["network_topology"] = topo["yaml"]
    return out


def v1_parts(pack: dict) -> dict:
    """Prompt v1's request data: the six sections v1 knew, the alert as ``alert``."""
    sections = [s for s in pack.get("sections") or [] if s.get("name") in V1_SECTIONS]
    return {"alert": f"{pack.get('rule', '')} on {pack.get('device') or 'no one device'}",
            "pack": json.dumps(sections, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"))}


def context(topo: dict = None) -> dict:
    """The call's cached prefix: the pack's format always; the network's summary and the
    topology's format when the topology is sent. The same bytes on every call while the
    network's model holds."""
    from modules import network_model as NM

    out = {"pack_format": vocabulary()}
    if topo and topo.get("sent"):
        out["network"] = topo["summary"]
        out["topology_format"] = NM.FORMAT
    return out


def check(answer: "Explanation", pack: dict, topology_ids=(), sections=None) -> str:
    """"" when every hypothesis cites the pack as sent (*sections*, by default the pack's
    every section) or the topology sent (*topology_ids*) and names an allowed read, and every
    piece of evidence the answer says it checked (schema v2) is one of them and was read; else
    why not (the first one that does not, named). No fault found holds no hypothesis and cites
    at least one piece it checked."""
    from modules import evidence_pack as EP
    from modules import readonly_commands as R

    outcome = answer.outcome.value
    if outcome == "refuse":
        return ""
    sent = {"sections": (pack.get("sections") or []) if sections is None else list(sections)}
    known = set(topology_ids or ())
    checked = list(getattr(answer, "checked", None) or [])
    if outcome == "no_fault_found":
        if answer.hypotheses:
            return (f"the answer finds no fault yet holds {len(answer.hypotheses)} "
                    "hypotheses")
        if not checked:
            return "the answer finds no fault but cites no evidence it checked"
    for ref in checked:
        piece = EP.resolve(sent, ref)
        if piece is None and ref not in known:
            return (f"the evidence checked cites {ref[:40]!r}, which is not in the pack"
                    + (" or the topology sent" if known else "")
                    + (" as sent" if EP.resolve(pack, ref) is not None else ""))
        # Whether it was read is its section's state (a health figure's own); a piece's own
        # `state` is what it describes, an adjacency "up", an alert "alerting" (C1761). A
        # topology id was read with the network's model.
        state = EP.read_state(sent, ref) if piece is not None else "ok"
        if state not in READ_STATES:
            return f"the evidence checked cites {ref[:40]!r}, which was not read ({state})"
    if outcome == "no_fault_found":
        return ""
    if not answer.hypotheses and not answer.needs_human:
        return "the answer holds no hypothesis and does not ask for a person"
    if len(answer.hypotheses) > MAX_HYPOTHESES:
        return f"{len(answer.hypotheses)} hypotheses; at most {MAX_HYPOTHESES} are taken"
    for i, h in enumerate(answer.hypotheses, 1):
        if not h.evidence_refs:
            return f"hypothesis {i} cites nothing in the pack"
        for ref in h.evidence_refs:
            if EP.resolve(sent, ref) is None and ref not in known:
                return (f"hypothesis {i} cites {ref[:40]!r}, which is not in the pack"
                        + (" or the topology sent" if known else "")
                        + (" as sent" if EP.resolve(pack, ref) is not None else ""))
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
    return explain_pack(pack, actor=actor, send=send, today=today)


#: The pack's parts in the order v6's budget DROPS them (the operator, 2026-10-26): the oldest
#: and least relevant first; never a log line inside the onset window (`ONSET_WINDOW_S` before
#: the onset to the alert's time), never the alert's own device's figures, and never the
#: alert, device or Intent sections.
PACK_DROPS = (
    "History older than the onset window, oldest first",
    "log lines outside the onset window, farthest from the onset first",
    "the health figures of devices two hops away, then one hop away",
)
#: The onset window's start before the onset: the health figures' own window (15 minutes).
ONSET_WINDOW_S = 900


def _epoch(text) -> float:
    import calendar
    import time as _t

    try:
        return float(calendar.timegm(_t.strptime(str(text)[:19], "%Y-%m-%dT%H:%M:%S")))
    except (TypeError, ValueError):
        return 0.0


def _pack_drop_order(pack: dict, sections: list) -> list:
    """``[(class, section name, ref)]``: the pieces of the sections as sent v6's budget may
    drop, in `PACK_DROPS`' order, each class's least relevant first."""
    onset = _epoch(pack.get("onset")) or _epoch(pack.get("built_at"))
    start = onset - ONSET_WINDOW_S
    end = max(onset, _epoch(next((p.get("starts_at") for s in sections
                                  if s.get("name") == "alert" for p in s.get("pieces") or []),
                                 "")))
    by = {s.get("name"): s.get("pieces") or [] for s in sections}
    out = []
    old = [p for p in by.get("history", ()) if _epoch(p.get("at")) < start]
    out += [(0, "history", p["ref"]) for p in sorted(old, key=lambda p: _epoch(p.get("at")))]
    outside = [p for p in by.get("logs", ())
               if not start <= _epoch(p.get("at")) <= end]
    out += [(1, "logs", p["ref"]) for p in sorted(
        outside, key=lambda p: -abs(_epoch(p.get("at")) - onset))]
    far = [p for p in by.get("health", ()) if (p.get("hop") or 0) > 0]
    out += [(2, "health", p["ref"]) for p in sorted(far, key=lambda p: -(p.get("hop") or 0))]
    return out


def _without(sections: list, gone: set, counts: dict) -> list:
    """*sections* with the pieces *gone* (refs) left out, each section that lost some saying
    how many, "omitted for size"."""
    out = []
    for s in sections:
        pieces = s.get("pieces") or []
        kept = [p for p in pieces if p.get("ref") not in gone]
        if len(kept) < len(pieces):
            s = dict(s, pieces=kept, omitted_for_size=(
                f"{len(pieces) - len(kept)} of its {len(pieces)} pieces left out to fit the "
                "prompt's size (not the same as not read)"))
            counts[s.get("name")] = len(pieces) - len(kept)
        out.append(s)
    return out


def _topology_yaml(topo: dict, why: bool, source: bool, omitted: list) -> str:
    """The topology as sent, its coverage header kept whole but for each layer's why or source
    where dropped, and what the budget left out said on it, "omitted for size"."""
    import yaml

    from modules import network_model as NM

    doc = yaml.safe_load(topo["yaml"]) or {}
    cov = doc.get("coverage") or {}
    for layer, c in list(cov.items()):
        if isinstance(c, dict):
            cov[layer] = {k: v for k, v in c.items()
                          if (why or k != "why") and (source or k != "source")}
    if omitted:
        cov["omitted for size (not the same as not_collected)"] = "; ".join(omitted)
    doc["coverage"] = cov
    return NM._yaml(doc)


def budgeted(pack: dict, topo: dict, prompt: tuple, schema) -> dict:
    """v6 under the context budget rule (PHASE8_PLAN 10.6; the operator, 2026-10-26), the
    task's `max_prompt_tokens` its budget: the network context's parts dropped in
    `nl_query.CONTEXT_DROPS`' order (the device index, the summary's links and counts, each
    layer's why, the whole summary), then the pack's in `PACK_DROPS`' order, one piece at a
    time, then each layer's source last; each layer's status and age always kept. ``{"data",
    "ctx", "sections", "said"}``: what is sent, and what was dropped to fit."""
    from modules import network_model as NM
    from modules.ai import nl_query, prompts, profiles

    loaded, pin = prompts.load(*prompt), profiles.TASKS[FEATURE]
    budget = pin["max_prompt_tokens"]
    base_sections = sent_sections(pack, topo)
    model = NM.model_for(topo["network"])[0] if topo.get("sent") else None
    order = _pack_drop_order(pack, base_sections)

    def build(net_level: int, n_pieces: int, source: bool):
        dropped = list(nl_query.CONTEXT_DROPS[:min(net_level, 4)])
        counts = {}
        gone = {ref for _c, _n, ref in order[:n_pieces]}
        sections = _without(base_sections, gone, counts)
        classes = sorted({c for c, _n, _r in order[:n_pieces]})
        omitted = dropped + [PACK_DROPS[c] for c in classes] + \
            ([] if source else [nl_query.CONTEXT_DROPS[4]])
        ctx = context(topo)
        data = {"pack": json.dumps([as_sent(s) for s in sections], sort_keys=True,
                                   ensure_ascii=False, separators=(",", ":")),
                "the_alert": f"{pack.get('rule', '')} on {pack.get('device') or 'no one device'}"}
        if topo.get("sent") and model is not None and (net_level or n_pieces or not source):
            if net_level == 1:
                ctx["network"] = nl_query._summary_text(model, False, True)
            elif net_level in (2, 3):
                ctx["network"] = nl_query._summary_text(model, False, False)
            elif net_level >= 4:
                ctx["network"] = "omitted for size: the network's summary"
            data["network_topology"] = _topology_yaml(topo, net_level < 3, source, omitted)
        elif topo.get("yaml"):
            data["network_topology"] = topo["yaml"]          # level 0: as v4 sends it
        body = gateway.build_request(loaded, schema, dict(data, looked_up="(nothing looked up)"),
                                     pin, ctx)
        said = {"level": net_level + (0 if source else 1), "dropped": omitted,
                "pack_dropped": counts, "estimate": gateway.prompt_tokens(body),
                "budget": budget}
        return {"data": data, "ctx": ctx, "sections": sections, "said": said}

    steps = [(lv, 0, True) for lv in range(0, 5)] + \
        [(4, n, True) for n in range(1, len(order) + 1)] + [(4, len(order), False)]
    if not topo.get("sent"):
        steps = [(0, n, True) for n in range(0, len(order) + 1)]
    chosen = None
    for net_level, n, source in steps:
        chosen = build(net_level, n, source)
        if chosen["said"]["estimate"] <= budget:
            break
    return chosen


def _ask_round(prompt, schema, data, ctx, network, *, actor, send, today, subject) -> dict:
    """v6's call and its needs round (at most one follow-up, `needs.run`), as Ask in words'
    (`nl_query._ask_round`): the follow-up's answer in place of the first's when there was one,
    the cost the round's, ``parent_call_id`` the first call's."""
    from modules.ai import needs as N
    from modules.ai import nl_query

    kw = {"actor": actor, "context": ctx, "send": send, "today": today}
    got = gateway.ask(FEATURE, prompt, schema, dict(data, looked_up=nl_query.looked_up([])),
                      subject=subject, **kw)
    wanted = list(getattr(got.get("output"), "needs", None) or []) if got.get("ok") else []
    if not wanted:
        return got
    held = {}

    def follow(results, link):
        held["got"] = gateway.ask(FEATURE, prompt, schema,
                                  dict(data, looked_up=nl_query.looked_up(results)),
                                  subject=dict(subject, **link), **kw)
        return held["got"]

    rnd = N.run(got["call_id"], network, [n.model_dump(mode="json") for n in wanted],
                actor=actor, follow=follow)
    second = held.get("got")
    if not rnd["ok"] or second is None:
        return dict(got, needs_said=rnd["error"] or "nothing could be looked up")
    total = round((got.get("cost_usd") or 0) + (second.get("cost_usd") or 0), 6)
    return dict(second, cost_usd=total, parent_call_id=got["call_id"],
                needs_said="; ".join(f"{r['kind']} {r['subject']}: {r['state']}"
                                     for r in rnd["results"]))


def explain_pack(pack: dict, *, actor: str, send=None, today: str = None,
                 prompt: tuple = PROMPT) -> dict:
    """`explain` of a pack in hand (a stored one, or a replay's, scripts/nmas-pack-replay):
    its hash checked, the class gates asked, one call through the gateway, the answer checked
    against what was sent. *prompt* ``("explain", 1)`` asks as v1 did (the pack's six
    sections, no topology, no health), for a replay's before-and-after."""
    from modules import evidence_pack as EP

    pack_id = pack.get("id") or ""
    # Which pack an answer read (C1862): two packs of one alert are told apart by id, schema
    # and when each was built, drawn with the answer.
    read = {"id": pack_id, "schema": EP.schema_of(pack), "built_at": EP.built_when(pack),
            "as_of": pack.get("built_at") or ""}
    if not EP.intact(pack):
        return {"ok": False, "error": "changed", "pack_id": pack_id,
                "detail": "the pack's hash does not match: it changed since it was built, so "
                          "it is not explained"}
    from modules.ai import egress_classes
    marked = egress_classes.classification_marking(pack.get("network") or "")
    if marked:
        return {"ok": False, "error": "classified", "pack_id": pack_id,
                "detail": f"{pack.get('network')} carries the classification marking "
                          f"{marked!r}, which forces AI off: nothing was sent"}
    if tuple(prompt) == ("explain", 1):
        topo = {"sent": False, "why": "prompt v1 sends no topology", "ids": [], "reached": {},
                "network": pack.get("network") or "", "subject": pack.get("device") or "",
                "version": "", "observed": ""}
        data, ctx = v1_parts(pack), {"pack_format": vocabulary(V1_SECTIONS)}
        sections = [s for s in pack.get("sections") or [] if s.get("name") in V1_SECTIONS]
    else:
        topo = topology(pack)
        data, ctx, sections = parts(pack, topo), context(topo), sent_sections(pack, topo)
    said = {"sent": topo["sent"], "why": topo["why"], "network": topo["network"],
            "subject": topo["subject"], "hops": HOPS, "version": topo["version"],
            "devices": sorted(topo["reached"]), "observed": topo["observed"],
            "as_now": topo.get("as_now") or ""}
    schema = SCHEMA_OF.get(int(prompt[1]), ExplanationV2)
    # What the call is about, written with it (15.14): the alert's pack and its device.
    subject = {"kind": "alert", "id": pack_id, "rule": pack.get("rule") or "",
               "devices": [pack["device"]] if pack.get("device") else []}
    kept = {}
    if int(prompt[1]) >= 6:
        # The context budget rule: what is sent fits the task's bound, what was dropped said
        # in the prompt ("omitted for size") and kept with the answer.
        sel = budgeted(pack, topo, tuple(prompt), schema)
        data, ctx, sections, kept = sel["data"], sel["ctx"], sel["sections"], {
            "context": sel["said"]}
        got = _ask_round(tuple(prompt), schema, data, ctx, pack.get("network") or "",
                         actor=actor, send=send, today=today, subject=subject)
    else:
        got = gateway.ask(FEATURE, tuple(prompt), schema, data, actor=actor, context=ctx,
                          send=send, today=today, subject=subject)
    if not got["ok"]:
        return dict(got, pack_id=pack_id, pack_read=read, topology=said, **kept)
    answer, base = got["output"], {"pack_id": pack_id, "pack_read": read,
                                   "call_id": got["call_id"],
                                   "cost_usd": got["cost_usd"], "topology": said,
                                   **{k: got[k] for k in ("parent_call_id", "needs_said")
                                      if got.get(k)}, **kept}
    links = {"page": f"/v2/monitoring/alerts/pack/{pack_id}", "anchor": f"explain-{pack_id}"}
    why = check(answer, pack, topo["ids"] if topo["sent"] else (), sections=sections)
    if why:
        calls.record_use(got["call_id"], "refused by validation", actor=actor, detail=why,
                         links=links)
        return dict(base, ok=False, error="couldnt_analyse",
                    detail=f"couldn't analyse: {why}; nothing is shown")
    if answer.outcome.value == "refuse":
        calls.record_use(got["call_id"], "shown: the pack cannot say", actor=actor,
                         detail=answer.why_not[:200], links=links)
        return dict(base, ok=False, error="unanswerable",
                    detail=f"the pack cannot say: {answer.why_not[:200]}")
    calls.record_use(got["call_id"], "shown: " + answer.outcome.value.replace("_", " "),
                     actor=actor, links=links)
    # What is drawn (an answer or no fault found by now, its why_not empty); the whole answer
    # is in the call's record. Each citation says where it resolves: a pack piece is a link to
    # it on the card, a topology id is drawn as text.
    shown = answer.model_dump(mode="json", include={"rationale", "hypotheses", "needs_human"})
    shown["outcome"] = answer.outcome.value
    # A reference sent under the model's id for a device the pack names otherwise (C1849,
    # `one_id`) is linked to the pack's own piece, the reference sent kept beside it.
    back = one_id(pack.get("sections") or [], topo.get("names") or {})[1] \
        if topo.get("sent") else {}

    def cite(r):
        mine = back.get(r, r)
        return dict({"ref": mine, "in_pack": EP.resolve(pack, mine) is not None},
                    **({"as_sent": r} if mine != r else {}))
    for h in shown["hypotheses"]:
        h["cites"] = [cite(r) for r in h.pop("evidence_refs")]
    shown["checked"] = [cite(r) for r in getattr(answer, "checked", None) or []]
    return dict(base, ok=True, error="", answer=shown)
