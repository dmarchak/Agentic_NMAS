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

from modules.ai import gateway
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


#: Each prompt version's answer schema: v1 to v3 were written for `Explanation`, v4 for
#: `ExplanationV2`, so a replay asking v1 asks it as it was.
SCHEMA_OF = {1: Explanation, 2: Explanation, 3: Explanation, 4: ExplanationV2}
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
            "says why, and is not a zero.")
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
           "version": "", "subject": device, "network": network, "observed": ""}
    gate = egress_classes.topology_allowed(network)
    if not gate["allowed"]:
        return dict(out, why=gate["why"])
    if not device:
        return dict(out, why="the alert is not one device's, so no part of the network is "
                             "picked out")
    overlay = EP.overlay_of(pack)
    got = NM.context_for(network, device, hops=HOPS, overlay=overlay)
    if not got["ok"]:
        return dict(out, why=f"the network model could not be read ({got['error']})",
                    yaml=f"could not read: the network model ({got['error']})")
    observed = (f"as of {overlay['as_of']}" if overlay["state"] == "read" else
                f"could not read ({overlay['why']})")
    return dict(out, sent=True, summary=got["summary"], yaml=got["yaml"], ids=got["ids"],
                reached=got["reached"], version=got["version"], observed=observed)


def sent_sections(pack: dict, topo: dict = None) -> list:
    """The pack's sections as they are sent: never the observed overlay (it rides in the
    subgraph); the health figures of the alert's device alone when no topology is sent (who
    is near it is topology), the rest said withheld."""
    out = []
    for s in pack.get("sections") or []:
        if s.get("name") in NOT_SENT:
            continue
        if s.get("name") == "health" and not (topo or {}).get("sent"):
            kept = [p for p in s.get("pieces") or [] if p.get("hop") == 0]
            if len(kept) < len(s.get("pieces") or []):
                s = dict(s, pieces=kept, withheld=(
                    "the figures of the devices around it are not sent: who is near the "
                    "device is the topology class, and no topology was sent"))
        out.append(s)
    return out


def parts(pack: dict, topo: dict = None) -> dict:
    """The call's own data: the topology around the device (when sent, or why it could not be
    read), the pack's sections as sent, and the alert's own words, which sort last."""
    out = {"pack": json.dumps(sent_sections(pack, topo), sort_keys=True, ensure_ascii=False,
                              separators=(",", ":")),
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
        state = (piece or {}).get("state") or "ok"
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


def explain_pack(pack: dict, *, actor: str, send=None, today: str = None,
                 prompt: tuple = PROMPT) -> dict:
    """`explain` of a pack in hand (a stored one, or a replay's, scripts/nmas-pack-replay):
    its hash checked, the class gates asked, one call through the gateway, the answer checked
    against what was sent. *prompt* ``("explain", 1)`` asks as v1 did (the pack's six
    sections, no topology, no health), for a replay's before-and-after."""
    from modules import evidence_pack as EP

    pack_id = pack.get("id") or ""
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
            "devices": sorted(topo["reached"]), "observed": topo["observed"]}
    schema = SCHEMA_OF.get(int(prompt[1]), ExplanationV2)
    got = gateway.ask(FEATURE, tuple(prompt), schema, data, actor=actor, context=ctx,
                      send=send, today=today)
    if not got["ok"]:
        return dict(got, pack_id=pack_id, topology=said)
    answer, base = got["output"], {"pack_id": pack_id, "call_id": got["call_id"],
                                   "cost_usd": got["cost_usd"], "topology": said}
    why = check(answer, pack, topo["ids"] if topo["sent"] else (), sections=sections)
    if why:
        return dict(base, ok=False, error="couldnt_analyse",
                    detail=f"couldn't analyse: {why}; nothing is shown")
    if answer.outcome.value == "refuse":
        return dict(base, ok=False, error="unanswerable",
                    detail=f"the pack cannot say: {answer.why_not[:200]}")
    # What is drawn (an answer or no fault found by now, its why_not empty); the whole answer
    # is in the call's record. Each citation says where it resolves: a pack piece is a link to
    # it on the card, a topology id is drawn as text.
    shown = answer.model_dump(mode="json", include={"rationale", "hypotheses", "needs_human"})
    shown["outcome"] = answer.outcome.value
    for h in shown["hypotheses"]:
        h["cites"] = [{"ref": r, "in_pack": EP.resolve(pack, r) is not None}
                      for r in h.pop("evidence_refs")]
    shown["checked"] = [{"ref": r, "in_pack": EP.resolve(pack, r) is not None}
                        for r in getattr(answer, "checked", None) or []]
    return dict(base, ok=True, error="", answer=shown)
