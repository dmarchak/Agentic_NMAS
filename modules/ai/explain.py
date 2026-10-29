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
  read-only allowlist (`readonly_commands`); and every device the answer names (its rationale
  and each claim, a name matched as a whole token against the devices the pack and the topology
  name) must be cited somewhere in it (C1897, `uncited_devices`: Walk 2's answer named a device
  whose alert the pack held and cited nothing of it). One that does not is "couldn't analyse", naming it, and nothing is
  shown (the card's kill criterion: one claim shown with a reference that does not resolve).
  No tool is offered. **The operator's decision 7 (2026-10-28):** a device the answer names
  and the pack as sent holds, cited nothing of, is cited by Mercury (`mercury_cites`: its other
  alert, else its first figure, or the alert for its own device), kept and drawn as
  Mercury's, never among the model's citations; a device only the topology sent knows still
  refuses; a device of the network the call never sent is not demanded (`sent_names`); and an
  adjacency cited with its ends in the other order, or a topology id with ``topology:`` before
  it, is read as the id sent (`as_topology_id`, `normalised`), the model's words drawn beside
  it.
- **The monitoring side** (C1896): the pack's `observer` section, the scrape jobs polling the
  devices across all their targets, the SNMP exporter and the collector's host, one line per
  piece, each cited ``observer:<what>``.
- **The fact sheet** (the operator's order of 2026-10-29, C2117; `fact_sheet`, `facts`): lines
  computed by Mercury from the pack as sent, each labelled so, the first data block
  (uncached, so the cached prefix is unchanged): heartbeat cadence against the neighbours,
  reloads in the window and what accounts for them, the changes and actions in the window
  and who made each (the operator's order of 2026-10-29, "WHO, guaranteed in code"), the
  scrape jobs at the alert's time, and what the pack lacks. Every prompt but v1 receives it:
  it is input, not prompt text.
- **Who, guaranteed** (the same order, `modules/ai/who.py`): a hypothesis citing a change or
  an action (a History receipt or record, a configuration-change log line, the Intent check's
  difference) carries who made it (``who``), from the pack's records; one whose claim does not
  name that actor, or say "no record of who" where none is recorded, has it added by Mercury
  (`who.mercury_who`, recorded with the use; on each hypothesis kept, the ``who`` entry whose
  *by* is "mercury"), drawn as Mercury's after the model's words; the model's answer stays as
  received in the call's record.
- **Mercury's needs_human** (the operator's order of 2026-10-29, C2141; `needs_human_guard`):
  no fault found with needs_human false while the alert's own source shows it firing
  (`fault_shown`) is kept needing a person, recorded apart (``mercury_needs_human``, its
  reason, on the kept answer and the use's record) and drawn under "set by Mercury"; the
  model's answer stays as received in the call's record.

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
            "Explain: a fact sheet computed by Mercury from the pack (heartbeat cadence "
            "against the neighbours, reloads in the window and what accounts for them, the "
            "changes and actions in the window and who made each, the scrape jobs at the "
            "alert's time, what the pack lacks), the pack, its health "
            "figures for the devices within two hops, and the topology as data, no tool "
            "offered"),
    ("check", "every reference resolves to the pack or to the topology as sent (an adjacency "
              "written with its ends in the other order, or a topology id written with "
              "topology: before it, is read as the id sent), and every confirming read is on "
              "the read-only allowlist; no fault found cites the evidence it checked, each "
              "piece read; every device the answer names that the pack or the topology sent "
              "holds is cited somewhere in it: one the pack holds and the answer cited "
              "nothing of is cited by Mercury, by its alert or its figure, and drawn as "
              "Mercury's; one the pack does not hold, or anything else that does not hold, "
              "is couldn't analyse, and nothing is shown; no fault found that does not ask "
              "for a person while the alert's own source shows it firing is kept needing a "
              "person, set by Mercury and drawn as Mercury's; a hypothesis citing a change or "
              "an action carries who made it, from the pack's records, and one whose words "
              "do not name them (or say no record of who) has it added by Mercury, drawn as "
              "Mercury's"),
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


class Band(str, Enum):
    """How likely a hypothesis is on its evidence (prompt v9, the operator's item 2 of
    2026-10-29): the evidence points to it, is consistent with it, or it is kept to rule out."""
    likely = "likely"
    possible = "possible"
    unlikely = "unlikely"


class RankedHypothesis(StrictModel):
    """A v9 hypothesis: v4's, with its band; `confirm_with` is the one confirming step."""
    claim: str
    evidence_refs: list[str]
    confirm_with: str
    band: Band


@register("explain", 4)
class ExplanationV4(StrictModel):
    """Prompt v9's answer (the operator's item 2, "MOST LIKELY", 2026-10-29): v2's, each
    hypothesis banded, and `why_first`, why the first ranks above the others."""
    outcome: Assessment
    rationale: str
    hypotheses: list[RankedHypothesis]
    why_first: str
    checked: list[str]
    needs_human: bool
    why_not: str


#: Each prompt version's answer schema: v1 to v3 were written for `Explanation`, v4 for
#: `ExplanationV2`, so a replay asking v1 asks it as it was.
SCHEMA_OF = {1: Explanation, 2: Explanation, 3: Explanation, 4: ExplanationV2,
             5: ExplanationV2, 6: ExplanationV3, 7: ExplanationV2, 8: ExplanationV2,
             9: ExplanationV4}
#: The versions built on the network context (the context budget rule, the needs round): v6.
#: A set, never "6 and later": v7 is v4's request with one rule more (C2038).
NETWORK_CONTEXT_VERSIONS = frozenset({6})
#: Candidate prompts, asked only by a replay (`nmas-pack-replay --prompt N`) until proved.
#: v5 adds general Analyst guidance ("when symptoms appear on several devices in the same
#: window, consider a common cause beneath them early"; the operator, 2026-10-26); it stays
#: rejected. v6, the network-context version, is built from v4 (the operator, 2026-10-26):
#: the coverage header's line (say when an answer rests on a layer not collected), the pack's
#: endpoints (C1778), the needs round (C1780), and a pack section rebuilt afterwards never
#: read as observed at the time (alert history, C1808); adopted only by the operator's bar.
#: v7 is v4 with one rule (C2038, the operator's choice of 2026-10-28): every device an answer
#: names is cited, as the check (C1897) requires; the check stays as strict.
#: v8 is v4 with one rule (the operator's decision 3, 2026-10-28): an unexplained reload or
#: out-of-band action (a device restarted, a configuration changed, with no recorded operation
#: explaining it) sets needs_human true, so a person confirms it was intended.
#: v9 is v4 with the operator's item 2 (2026-10-29, "MOST LIKELY"): a band per hypothesis, why
#: the first ranks first, one confirming step, who named in a change's claim (WHO's check
#: reads the words, `who.mercury_who`), and the fact sheet's block described; asked for its
#: own schema (`ExplanationV4`), adopted only by 15.12's rule.
CANDIDATES = (("explain", 5), ("explain", 6), ("explain", 7), ("explain", 8), ("explain", 9))
#: A checked piece's states that were read (pack_format: only ok and empty are evidence).
READ_STATES = ("ok", "empty")

#: Explain's measured reliability, the ONE dated record every "Advisory (beta)" label draws its
#: figure from (PHASE8_PLAN 15.12, Explain's ship ruling of 2026-10-29, condition (b)): never a
#: figure typed into a template. The 10-run adoption round of 2026-10-29 (C2117, C2141): the
#: pinned prompt and model, with the fact sheet and Mercury's needs-a-person guard, over the 21
#: recorded cases; a case reliable when it passed every run (15.12's reliability). Confidently
#: wrong (criterion 3) as shown (guarded, the ruling's count) and as the model answered (raw).
#: ``blind`` is the blind held-out set's measurement (C2121), None until it is made: Explain
#: leaves beta only after it (condition (c)). A new adoption writes a new record here.
MEASURED = {"at": "2026-10-29", "prompt": ("explain", 4), "model": "claude-sonnet-5-5",
            "fact_sheet": True, "guard": True, "round": "msgbatch_01D8vrAjVh3NpSifBhdFcV26", "commit": "4a468990",
            "cases": 21, "reliable": 17, "runs": 10, "passed_runs": 194,
            "wrong_shown": 0, "wrong_raw": 10, "blind": None}


def beta(measured: dict = None) -> dict:
    """The "Advisory (beta)" label as every Explain answer and control draws it
    (templates/v2/_explain_beta.html): ``words``, the measured figure from *measured*
    (`MEASURED` by default) when it is of the prompt and model pinned now, else what was
    measured and what is asked now (``state`` "measured" or "not_measured"); ``hover``, the
    whole record in words. A pin the record is not of never borrows its figure."""
    from modules.ai import profiles

    m = MEASURED if measured is None else measured
    pin_model = profiles.task(FEATURE)["model"]

    def said(prompt, model):
        return f"{prompt[0]} v{prompt[1]} on {profiles.profile(model)['words']}"

    total = m["cases"] * m["runs"]
    pct = round(100 * m["reliable"] / m["cases"]) if m["cases"] else 0
    with_ = " and ".join(w for w, on in (("Mercury's fact sheet", m["fact_sheet"]),
                                         ("its needs-a-person guard", m["guard"])) if on)
    hover = (f"Explain is advisory while in beta. Measured {m['at']}: "
             f"{said(m['prompt'], m['model'])} ({m['model']})"
             f"{', with ' + with_ if with_ else ''}; {m['cases']} recorded alerts, {m['runs']} "
             f"runs each (round {m['round']}, on {m['commit']}): {m['reliable']} of "
             f"{m['cases']} cases reliable, {m['passed_runs']} of {total} runs passed; "
             f"confidently wrong {m['wrong_shown']} of {total} runs as shown, "
             f"{m['wrong_raw']} as the model answered. "
             + ("The blind held-out set is not yet measured, so Explain stays in beta."
                if m["blind"] is None else f"The blind held-out set: {m['blind']}."))
    if tuple(m["prompt"]) == tuple(PROMPT) and m["model"] == pin_model:
        return {"state": "measured", "percent": pct, "hover": hover,
                "words": (f"{pct}% of recorded cases reliable in measurement ({m['at']}, "
                          f"{m['cases']} cases, {m['runs']} runs)")}
    return {"state": "not_measured", "percent": None, "hover": hover,
            "words": (f"Not measured: Explain now asks {said(PROMPT, pin_model)}; the "
                      f"measurement of {m['at']} was of {said(m['prompt'], m['model'])}")}


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
    if "observer" in names:
        from modules import evidence_observer as O
        lines.append(
            "observer is the monitoring side over the health section's window: each scrape job "
            "polling the alert's device or a device within two hops, across ALL its targets "
            "(not only those devices); the SNMP exporter; and the host Prometheus runs on (the "
            "collector's host). A failed scrape that ran to its timeout is a target that did not "
            "answer in "
            f"time; one over in under {O.REFUSED_UNDER_S} s was refused. A piece's reference is "
            "its own, observer:<what>, as written; the section's lines hold the pieces, "
            + O.LINE_FORMAT + ". When several devices fail at once from one collector, the "
            "collector and what is beneath the devices are candidate causes beside each "
            "device's own: this section (the collector's side) and the health section (the "
            "devices' side) are what rank them.")
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
    from modules import evidence_observer as O

    if section.get("name") == "observer":
        # One line per piece, its reference first (C1896); the pieces' words are the pack
        # format's.
        out = {k: v for k, v in section.items() if k != "pieces"}
        out["lines"] = O.lines(section.get("pieces") or [])
        return out
    if section.get("name") != "health":
        return section
    # The figures' words are the pack format's (the cached prefix), not repeated per call.
    out = {k: v for k, v in section.items() if k not in ("pieces", "figures")}
    out["lines"] = H.lines(section.get("pieces") or [])
    return out


def roles_of(topo: dict = None) -> dict:
    """``{device name: role}`` of the devices the topology SENT holds (its yaml, already built
    for the call: no read), for the fact sheet's heartbeat line; ``{}`` when none was sent."""
    import yaml

    if not (topo or {}).get("sent") or not topo.get("yaml"):
        return {}
    try:
        devices = (yaml.safe_load(topo["yaml"]) or {}).get("devices") or {}
    except yaml.YAMLError:
        return {}
    return {d["name"]: str(d["role"]) for d in devices.values()
            if isinstance(d, dict) and d.get("name") and d.get("role")}


def facts(pack: dict, sections: list, topo: dict = None) -> str:
    """The fact sheet sent with the pack (`fact_sheet.sheet`, the operator's order of
    2026-10-29): computed by Mercury from the pack AS SENT (*sections*, `sent_sections`), so a
    class gate's withholding holds in it too, and masked on the way out."""
    from modules.ai import fact_sheet
    return fact_sheet.sheet(pack, sections, roles_of(topo))


def parts(pack: dict, topo: dict = None) -> dict:
    """The call's own data: the fact sheet first (`facts`: its block's name sorts first), the
    topology around the device (when sent, or why it could not be read), the pack's sections
    as sent, and the alert's own words, which sort last."""
    from modules.ai import fact_sheet

    sections = sent_sections(pack, topo)
    out = {"pack": json.dumps([as_sent(s) for s in sections], sort_keys=True,
                              ensure_ascii=False, separators=(",", ":")),
           "the_alert": f"{pack.get('rule', '')} on {pack.get('device') or 'no one device'}",
           fact_sheet.PART: facts(pack, sections, topo)}
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


#: The sections every piece of which is the alert's own device's: citing one cites that device.
OWN_DEVICE_SECTIONS = ("alert", "device", "history", "intent", "neighbours", "logs")


def device_ids(sections: list, names: dict = None, own: str = "") -> dict:
    """``{device name: its id, or ""}``: every device the pack as sent or the topology sent
    names (C1897): the health figures' and the other alerts' ``device`` with its ``dev``, the
    topology's *names* (its ids by name), and the alert's own device *own*."""
    out = {}
    for s in sections or []:
        if s.get("name") not in DEVICE_ID_SECTIONS:
            continue
        for p in s.get("pieces") or []:
            if p.get("device"):
                out[p["device"]] = out.get(p["device"]) or p.get("dev") or ""
    for name, dev in (names or {}).items():
        if name:
            out[name] = dev or out.get(name, "")
    if own:
        out.setdefault(own, "")
    return out


def named_devices(text: str, known) -> list:
    """The names of *known* that *text* names as whole tokens, sorted: a name inside a longer
    name or word is not it ("edge1" in "edge10", "core-edge1" or "edge1.lab" is not edge1), and
    a name is
    matched as written (case kept). Longer names are matched first, so a name that is part of
    another known name is not counted inside it."""
    import re

    found, rest = set(), text or ""
    for name in sorted({n for n in known if n}, key=lambda n: (-len(n), n)):
        pat = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-]|\.\w)")
        if pat.search(rest):
            found.add(name)
            rest = pat.sub(" ", rest)
    return sorted(found)


def cites_device(ref: str, name: str, dev: str, sent: dict, own: str) -> bool:
    """Whether the citation *ref* is of the device *name* (its id *dev*): a piece of the pack
    as sent naming it (``device``, ``dev``, or a neighbour's ``peer``), any piece of the alert's
    own device's sections when it is *own*, or a topology id that is the device's id or holds
    it as a whole part (an adjacency's or a cable's end)."""
    import re

    from modules import evidence_pack as EP

    piece = EP.resolve(sent, ref)
    if piece is not None:
        if name in (piece.get("device"), piece.get("peer")) or (dev and piece.get("dev") == dev):
            return True
        return name == own and ref.split(":", 1)[0] in OWN_DEVICE_SECTIONS
    return bool(dev) and re.search(r"(?:^|[:~])" + re.escape(dev) + r"(?=$|[:~/])",
                                   ref) is not None


def uncited_devices(answer, sent: dict, names: dict = None, own: str = "",
                    added=()) -> list:
    """The devices the answer names (its rationale and each hypothesis's claim, matched as
    whole tokens against the devices the pack and the topology name, `device_ids`) with no
    citation of their own anywhere in it (a hypothesis's references or the checked list, and
    *added*, the citations Mercury added, `mercury_cites`), sorted (C1897: an answer naming a
    device whose alert the pack held, without citing it)."""
    ids = device_ids(sent.get("sections") or [], names, own)
    text = " ".join([answer.rationale or ""] + [h.claim or "" for h in answer.hypotheses])
    refs = [r for h in answer.hypotheses for r in h.evidence_refs] + list(
        getattr(answer, "checked", None) or []) + list(added or ())
    return [n for n in named_devices(text, ids)
            if not any(cites_device(r, n, ids[n], sent, own) for r in refs)]


def sent_names(names: dict, topology_ids=()) -> dict:
    """The topology's ids by name (*names*, the network model's: every device of the network)
    held to the devices the topology SENT holds (*topology_ids*): a device of the network the
    call never sent is not one the answer could cite, so it is never demanded (the operator's
    decision 7c, 2026-10-28)."""
    known = set(topology_ids or ())
    return {n: d for n, d in (names or {}).items() if d and d in known}


#: Where Mercury looks for a device's own piece to cite for it (decision 7a): its other alerts
#: first, then its health figures, each in the pack's order.
MERCURY_CITE_ORDER = ("concurrent", "health")


def _named_in(answer, name: str) -> str:
    """Where the answer names *name*: the first hypothesis whose claim names it, else the
    rationale."""
    for i, h in enumerate(answer.hypotheses, 1):
        if named_devices(h.claim, [name]):
            return f"hypothesis {i}"
    return "the rationale"


def mercury_cites(answer, sent: dict, names: dict = None, own: str = "") -> list:
    """The citations Mercury adds to an answer (the operator's decision 7a, 2026-10-28):
    ``[{"device", "ref", "named_in"}]``, one for each device the answer names without citing
    it (`uncited_devices`) whose own evidence the pack as sent holds: its other alert, else its
    first health figure (`MERCURY_CITE_ORDER`), or the alert itself for the alert's own device.
    A device the pack holds nothing of (one known only by the topology sent) gets none, and the
    check still refuses the answer for it. The model's own citations are never changed: these
    are kept and drawn as Mercury's, beside them."""
    if answer.outcome.value == "refuse":
        return []
    sections = sent.get("sections") or []
    out = []
    for name in uncited_devices(answer, sent, names, own):
        ref = "alert" if name == own and any(s.get("ref") == "alert" for s in sections) else ""
        for want in () if ref else MERCURY_CITE_ORDER:
            ref = next((p.get("ref") or "" for s in sections if s.get("name") == want
                        for p in s.get("pieces") or [] if p.get("device") == name
                        and p.get("ref")), "")
            if ref:
                break
        if ref:
            out.append({"device": name, "ref": ref, "named_in": _named_in(answer, name)})
    return out


def _adjacency_parts(ref: str):
    """``(prefix, a, b, where)`` of an adjacency id ``adj:<protocol>:<a>~<b>:<where>``
    (`network_model._adj_id`; a device id is ``dev:<one part>``), or None."""
    import re

    m = re.fullmatch(r"(adj:[^:~]+:)([^~]+)~(dev:[^:~]+|[^:~]+):(.+)", ref or "")
    return m.groups() if m else None


#: The prefix a model has written before a topology id (decision 7b): never part of an id.
TOPOLOGY_PREFIX = "topology:"


def as_topology_id(ref: str, topology_ids=()) -> str:
    """The id of the topology sent that *ref* names, written as the topology writes it, or ""
    (the operator's decision 7b, 2026-10-28): *ref* itself; or with a ``topology:`` prefix
    taken off; or an adjacency with its two ends in the other order. Only an exact id of the
    topology sent is returned, never a near one."""
    known = set(topology_ids or ())
    if not ref or not known:
        return ""
    bare = ref[len(TOPOLOGY_PREFIX):] if ref.startswith(TOPOLOGY_PREFIX) else ref
    if bare in known:
        return bare
    parts = _adjacency_parts(bare)
    if parts:
        prefix, a, b, where = parts
        swapped = f"{prefix}{b}~{a}:{where}"
        if swapped in known:
            return swapped
    return ""


def normalised(answer, sent: dict, topology_ids=()):
    """``(answer, written)``: *answer* with each reference that resolves to nothing as written
    but names an id of the topology sent (`as_topology_id`) written as the topology writes it,
    and *written* each such id's reference as the model wrote it, so it is drawn beside it.
    A copy; the model's own answer is kept as received in the call's record."""
    from modules import evidence_pack as EP

    written = {}

    def one(ref):
        if EP.resolve(sent, ref) is not None or ref in set(topology_ids or ()):
            return ref
        canon = as_topology_id(ref, topology_ids)
        if canon:
            written[canon] = ref
            return canon
        return ref
    hyps = [h.model_copy(update={"evidence_refs": [one(r) for r in h.evidence_refs]})
            for h in answer.hypotheses]
    update = {"hypotheses": hyps}
    if hasattr(answer, "checked"):
        update["checked"] = [one(r) for r in answer.checked or []]
    return answer.model_copy(update=update), written


def _uncited_words(names: list) -> str:
    said = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return (f"the answer names {said} but cites nothing of {'it' if len(names) == 1 else 'them'}"
            ": every device it names needs a citation of its own (its figures, its alerts or "
            "its id in the topology)")


def check(answer: "Explanation", pack: dict, topology_ids=(), sections=None,
          names: dict = None, added=()) -> str:
    """"" when every hypothesis cites the pack as sent (*sections*, by default the pack's
    every section) or the topology sent (*topology_ids*) and names an allowed read, every
    piece of evidence the answer says it checked (schema v2) is one of them and was read, and
    every device the answer names (in its rationale or a claim) is cited somewhere in it, by
    the model or by Mercury (*added*, `mercury_cites`'s references) (C1897; *names* the
    network's ids by name, held to the devices the topology sent holds, `sent_names`); else
    why not (the first one that does not, named; every uncited device, named). No fault found
    holds no hypothesis and cites at least one piece it checked."""
    from modules import evidence_pack as EP
    from modules import readonly_commands as R

    outcome = answer.outcome.value
    if outcome == "refuse":
        return ""
    sent = {"sections": (pack.get("sections") or []) if sections is None else list(sections)}
    known = set(topology_ids or ())
    names = sent_names(names, known)
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
    own = pack.get("device") or ""
    if outcome == "no_fault_found":
        uncited = uncited_devices(answer, sent, names, own, added)
        return _uncited_words(uncited) if uncited else ""
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
    uncited = uncited_devices(answer, sent, names, own, added)
    return _uncited_words(uncited) if uncited else ""


#: The alert piece's kind while its condition holds (`grafana_alerts._kind`: Grafana's
#: Alerting or firing, and "Alerting (NoData)" of a rule whose no data is its fault, C2174; an
#: SDN detection's own, `sdn.detect`): never no data, error, pending or normal, each its own
#: kind.
FIRING_KIND = "condition"
#: An alert state that is not firing, however its kind reads (a state Mercury did not write).
NOT_FIRING = ("normal", "resolved", "inactive", "pending")


def fault_shown(pack: dict) -> str:
    """Why the alert's own source shows the fault, in words, or "" (the operator's order of
    2026-10-29, C2141): the pack's alert section was read (state ok) and its piece's kind is
    `FIRING_KIND`, its condition holding (a state no word of `NOT_FIRING` begins), as of the
    pack's time (its ``built_at``, the alert's time); and the pack records no resolve at or
    before that time (``resolved_at``, a pack built from the alert history). A resolved alert,
    one with no data or an error, and a pack whose alert section was not read show no fault;
    a heartbeat or telemetry alert firing on its data's absence ("Alerting (NoData)" of a rule
    whose no data is its fault, the condition kind, C2174) shows one."""
    sec = next((s for s in pack.get("sections") or [] if s.get("name") == "alert"), {})
    piece = (sec.get("pieces") or [{}])[0] if sec.get("state") == "ok" else {}
    state = str(piece.get("state") or "")
    if piece.get("kind") != FIRING_KIND or state.lower().startswith(NOT_FIRING):
        return ""
    at, resolved = _epoch(pack.get("built_at")), _epoch(pack.get("resolved_at"))
    if resolved and (not at or resolved <= at):
        return ""
    return (f"the alert's own source ({sec.get('source') or 'the alert section'}) holds it "
            f"firing ({state or 'its condition holding'}) at the alert's time "
            f"{pack.get('built_at') or '(not recorded)'}")


def needs_human_guard(outcome: str, needs_human: bool, pack: dict) -> dict:
    """Mercury's own needs_human (the operator's order of 2026-10-29, C2141): ``{"reason"}``
    when the answer is no fault found with needs_human false while the alert's own
    source shows the fault (`fault_shown`), else ``{}``. Mercury then sets needs_human true on
    the answer it keeps and draws, recorded apart as its own change (``mercury_needs_human``,
    as `mercury_cites` is), the model's answer kept as received in the call's record."""
    if outcome != "no_fault_found" or needs_human:
        return {}
    why = fault_shown(pack)
    if not why:
        return {}
    return {"reason": (f"The model found no fault and did not ask for a person, but {why}: a "
                       "firing alert whose evidence shows nothing wrong needs a person to look "
                       "(the cause may be outside the pack, or the rule may be wrong)")}


def explain(pack_id: str, *, actor: str, trigger: dict, send=None, today: str = None) -> dict:
    """``{"ok", "error", "detail", "answer", "pack_id", "call_id", "cost_usd"}``: the pack's
    hypotheses, checked; or a refusal naming why, with nothing shown."""
    from modules import evidence_pack as EP

    pack, state, error = EP.find(pack_id)
    if pack is None:
        return {"ok": False, "error": "no_pack", "pack_id": pack_id,
                "detail": (f"the evidence packs cannot be read ({error})"
                           if state == "unreadable" else f"no evidence pack {pack_id} is kept")}
    return explain_pack(pack, actor=actor, trigger=trigger, send=send, today=today)


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


def budgeted(pack: dict, topo: dict, prompt: tuple, schema, counter=None) -> dict:
    """v6 under the context budget rule (PHASE8_PLAN 10.6; the operator, 2026-10-26), the
    task's `max_prompt_tokens` its budget: the network context's parts dropped in
    `nl_query.CONTEXT_DROPS`' order (the device index, the summary's links and counts, each
    layer's why, the whole summary), then the pack's in `PACK_DROPS`' order, one piece at a
    time, then each layer's source last; each layer's status and age always kept. ``{"data",
    "ctx", "sections", "said"}``: what is sent, and what was dropped to fit. Each request's
    tokens are *counter*'s (`gateway.counter`: the provider's count where the call could be
    sent, C1898), else the gateway's fallback over-estimate."""
    from modules import network_model as NM
    from modules.ai import fact_sheet, nl_query, prompts, profiles

    loaded, pin = prompts.load(*prompt), profiles.TASKS[FEATURE]
    budget = pin["max_prompt_tokens"]
    base_sections = sent_sections(pack, topo)
    # The fact sheet is computed from the pack as sent before anything is dropped for size, so
    # it is the same at every level.
    sheet = facts(pack, base_sections, topo)
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
                "the_alert": f"{pack.get('rule', '')} on {pack.get('device') or 'no one device'}",
                fact_sheet.PART: sheet}
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
                "pack_dropped": counts,
                "estimate": (counter.measure(body, budget)["tokens"] if counter is not None
                             else gateway.prompt_tokens(body)),
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


def _ask_round(prompt, schema, data, ctx, network, *, actor, trigger, send, today,
               subject) -> dict:
    """v6's call and its needs round (at most one follow-up, `needs.run`), as Ask in words'
    (`nl_query._ask_round`): the follow-up's answer in place of the first's when there was one,
    the cost the round's, ``parent_call_id`` the first call's."""
    from modules.ai import needs as N
    from modules.ai import nl_query

    kw = {"actor": actor, "trigger": trigger, "context": ctx, "send": send, "today": today,
          "network": network}
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


def explain_pack(pack: dict, *, actor: str, trigger: dict, send=None, today: str = None,
                 prompt: tuple = PROMPT) -> dict:
    """`explain` of a pack in hand (a stored one, or a replay's, scripts/nmas-pack-replay):
    its hash checked, the class gates asked, one call through the gateway, the answer checked
    against what was sent. *prompt* ``("explain", 1)`` asks as v1 did (the pack's six
    sections, no topology, no health), for a replay's before-and-after."""
    prep = _prepare_pack(pack, actor=actor, trigger=trigger, prompt=prompt)
    if "done" in prep:
        return prep["done"]
    if prep["round"]:
        got = _ask_round(tuple(prompt), prep["schema"], prep["data"], prep["ctx"],
                         pack.get("network") or "", actor=actor, trigger=trigger, send=send,
                         today=today, subject=prep["subject"])
    else:
        got = gateway.ask(FEATURE, tuple(prompt), prep["schema"], prep["data"], actor=actor,
                          trigger=trigger, context=prep["ctx"], send=send, today=today,
                          subject=prep["subject"], network=pack.get("network") or "")
    return _checked(pack, prep, got, actor=actor)


def _prepare_pack(pack: dict, *, actor: str, trigger: dict, prompt: tuple) -> dict:
    """What `explain_pack` sends for *pack* with *prompt*, before any call: ``{"done": <its
    refusal>}`` (a pack changed since it was built, or a network AI is forced off for), or
    ``{"schema", "data", "ctx", "subject", "round", ...}``, the request's parts and what the
    check reads (`_checked`). ``round``: v6's needs round follows the first call."""
    from modules import evidence_pack as EP

    pack_id = pack.get("id") or ""
    # Which pack an answer read (C1862): two packs of one alert are told apart by id, schema
    # and when each was built, drawn with the answer.
    read = {"id": pack_id, "schema": EP.schema_of(pack), "built_at": EP.built_when(pack),
            "as_of": pack.get("built_at") or ""}
    if not EP.intact(pack):
        return {"done": {"ok": False, "error": "changed", "pack_id": pack_id,
                         "detail": "the pack's hash does not match: it changed since it was "
                                   "built, so it is not explained"}}
    from modules.ai import egress_classes
    marked = egress_classes.classification_marking(pack.get("network") or "")
    if marked:
        return {"done": {"ok": False, "error": "classified", "pack_id": pack_id,
                         "detail": f"{pack.get('network')} carries the classification marking "
                                   f"{marked!r}, which forces AI off: nothing was sent"}}
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
    rounds = int(prompt[1]) in NETWORK_CONTEXT_VERSIONS
    if rounds:
        # The context budget rule: what is sent fits the task's bound, what was dropped said
        # in the prompt ("omitted for size") and kept with the answer.
        sel = budgeted(pack, topo, tuple(prompt), schema,
                       counter=gateway.counter(FEATURE, actor=actor, trigger=trigger))
        data, ctx, sections, kept = sel["data"], sel["ctx"], sel["sections"], {
            "context": sel["said"]}
    return {"pack_id": pack_id, "read": read, "topo": topo, "said": said, "schema": schema,
            "subject": subject, "data": data, "ctx": ctx, "sections": sections, "kept": kept,
            "round": rounds}


def _checked(pack: dict, prep: dict, got: dict, *, actor: str) -> dict:
    """The answer *got* (the gateway's result for *prep*, `_prepare_pack`'s) checked against
    what was sent, and what is drawn of it, as `explain_pack` returns it."""
    from modules import evidence_pack as EP

    pack_id, read, topo, said = prep["pack_id"], prep["read"], prep["topo"], prep["said"]
    sections, kept = prep["sections"], prep["kept"]
    if not got["ok"]:
        return dict(got, pack_id=pack_id, pack_read=read, topology=said, **kept)
    answer, base = got["output"], {"pack_id": pack_id, "pack_read": read,
                                   "call_id": got["call_id"],
                                   "cost_usd": got["cost_usd"], "topology": said,
                                   **{k: got[k] for k in ("parent_call_id", "needs_said")
                                      if got.get(k)}, **kept}
    links = {"page": f"/v2/monitoring/alerts/pack/{pack_id}", "anchor": f"explain-{pack_id}"}
    ids = topo["ids"] if topo["sent"] else ()
    names = topo.get("names") if topo["sent"] else None
    sent = {"sections": list(sections)}
    # Decision 7b: a topology id written with an adjacency's ends in the other order, or with
    # a `topology:` prefix, is read as the id the topology sent (the model's own words kept in
    # the call's record and drawn beside it). Decision 7a: a device the answer names and the
    # pack holds, cited nothing of, is cited by Mercury, and drawn as Mercury's.
    answer, written = normalised(answer, sent, ids)
    added = mercury_cites(answer, sent, sent_names(names, ids), pack.get("device") or "")
    why = check(answer, pack, ids, sections=sections, names=names,
                added=[a["ref"] for a in added])
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
    # The operator's order of 2026-10-29 (C2141): no fault found with needs_human false while
    # the alert's own source shows the fault is not kept as it came: Mercury sets needs_human,
    # recorded and drawn as its own change.
    guard = needs_human_guard(answer.outcome.value, answer.needs_human, pack)
    # The operator's order of 2026-10-29, "WHO, guaranteed in code" (b): a hypothesis citing a
    # change or an action carries who made it; one whose claim does not name them has it added
    # by Mercury, kept apart from the model's words (`who.mercury_who`).
    from modules.ai import who
    added_who = who.mercury_who(answer.hypotheses, sections)
    # What Mercury added or read differently is recorded with the use: the call's record keeps
    # the model's answer as received, so both stand.
    note = "; ".join(
        [f"cited by Mercury: {a['device']} by the pack's {a['ref']}" for a in added]
        + [f"read {w} as the topology's {c}" for c, w in sorted(written.items())]
        + ([f"needs a person, set by Mercury: {guard['reason']}"] if guard else [])
        + [f"who, added by Mercury to hypothesis {w['hypothesis']}: {w['words']} "
           f"({', '.join(w['refs'])})" for w in added_who])
    calls.record_use(got["call_id"], "shown: " + answer.outcome.value.replace("_", " "),
                     actor=actor, links=links, **({"detail": note[:800]} if note else {}))
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
                    **({"as_sent": r} if mine != r else {}),
                    **({"as_written": written[r]} if r in written else {}))
    for h in shown["hypotheses"]:
        # Who made each change it cites, one representation (`who.who_of`): each actor with
        # *by* "model" when the claim names them, else "mercury" (what Mercury added, the same
        # entries `added_who` recorded with the use), and the pieces recording it as citations,
        # drawn after the model's claim, Mercury's as Mercury's.
        h["who"] = [dict(w, cites=[cite(r) for r in w["refs"]])
                    for w in who.who_of(h["claim"], h["evidence_refs"], sections)]
        h["cites"] = [cite(r) for r in h.pop("evidence_refs")]
    shown["checked"] = [cite(r) for r in getattr(answer, "checked", None) or []]
    # Mercury's citations, never among the model's: each the device named, where, and the piece.
    shown["mercury_cites"] = [dict(cite(a["ref"]), device=a["device"], named_in=a["named_in"])
                              for a in added]
    # Mercury's needs_human, never the model's: set on what is kept and drawn, with its reason
    # drawn under its own chip; what the model said stays in the call's record.
    shown["mercury_needs_human"] = dict(guard)
    if guard:
        shown["needs_human"] = True
    return dict(base, ok=True, error="", answer=shown)


def batch_custom_id(pack_index: int, prompt: tuple, run: int) -> str:
    """A batched request's custom_id: the pack's place in the round's list, the prompt's
    version and the run (``p0-explain-v4-r2``), in the provider's shape (letters, digits, _
    and -, at most 64)."""
    return f"p{int(pack_index)}-{prompt[0]}-v{int(prompt[1])}-r{int(run)}"


def explain_packs_batch(packs: list, prompts_: list, runs: int, *, actor: str, trigger: dict,
                        today: str = None, stop_usd: float = None, provider=None,
                        sleep=None, clock=None) -> dict:
    """An evaluation round of Explain as one batch (the operator's decision of 2026-10-29,
    PHASE8_PLAN 15.12; `gateway.ask_batch`, which refuses any trigger but an evaluation's):
    each pack of *packs* (stored packs, as `explain_pack` takes them) asked with each prompt
    of *prompts_* (``("explain", 4)``, or a version's number) *runs* times. Each request is
    what `explain_pack` would send for the same pack and prompt (the same parts, the same
    budget for v6), and each answer is checked as `explain_pack` checks it. v6's needs round
    cannot ride in the first batch (its follow-up depends on the first answer): each v6
    answer naming a need is looked up (`needs.run`, as `explain_pack`'s round) and its one
    follow-up sent in a second batch (custom_id ``<first>-n``), at the batch rate, said as
    ``needs_followed: "batched"``; the answer checked is the follow-up's, the cost the
    round's.

    ``{"ok", "error", "detail", "batch_id", "cost_usd", "worst_usd", "results": {custom_id:
    explain_pack's result with "pack_id", "prompt", "run"}, "requests": {custom_id: {"pack_id",
    "prompt", "run"}}}``; results are keyed by custom_id (`batch_custom_id`), whatever order
    the provider returned them in. A pack refused before any call (changed since it was
    built, or its network marked) is its result with nothing sent."""
    asked = [tuple(p) if isinstance(p, (list, tuple)) else (FEATURE, int(p)) for p in prompts_]
    batch_requests, meta, preps, results = [], {}, {}, {}
    for i, pack in enumerate(packs):
        for prompt in asked:
            prep = _prepare_pack(pack, actor=actor, trigger=trigger, prompt=prompt)
            for run in range(int(runs)):
                cid = batch_custom_id(i, prompt, run)
                meta[cid] = {"pack_id": pack.get("id") or "", "prompt": list(prompt),
                             "run": run}
                if "done" in prep:
                    results[cid] = dict(prep["done"], **meta[cid])
                    continue
                preps[cid] = (pack, prompt, prep)
                data = prep["data"]
                if prep["round"]:
                    from modules.ai import nl_query
                    data = dict(data, looked_up=nl_query.looked_up([]))
                batch_requests.append({"custom_id": cid, "feature": FEATURE,
                                       "prompt": prompt, "schema": prep["schema"],
                                       "parts": data, "context": prep["ctx"],
                                       "subject": prep["subject"]})
    if not batch_requests:
        return {"ok": False, "error": "nothing_sent", "batch_id": "", "cost_usd": 0.0,
                "worst_usd": 0.0, "results": results, "requests": meta,
                "detail": "every pack was refused before a batch was built (each result "
                          "names why); nothing was sent"}
    kw = {"actor": actor, "trigger": trigger, "today": today, "provider": provider,
          "sleep": sleep, "clock": clock}
    got = gateway.ask_batch(batch_requests, stop_usd=stop_usd, **kw)
    firsts = {cid: got["results"].get(cid) for cid in preps}
    looked = _needs_rounds(preps, firsts, actor=actor)
    rounds = {cid: r for cid, r in looked.items() if "request" in r}
    second = None
    if rounds:
        # The follow-ups, one batch: the evaluation's stop is what the first batch left of it.
        left = None if stop_usd is None else max(0.0, float(stop_usd) - got["worst_usd"])
        second = gateway.ask_batch([r["request"] for r in rounds.values()], stop_usd=left,
                                   **kw)
    for cid, (pack, prompt, prep) in preps.items():
        one = firsts[cid]
        if one is None:
            results[cid] = dict(ok=False, error=got["error"] or "no_result",
                                detail=got["detail"] or "the batch returned no result for it",
                                **meta[cid])
            continue
        extra = {}
        if cid in rounds:
            one, extra = _round_result(one, rounds[cid], second), {"needs_followed": "batched"}
        elif cid in looked:
            one = dict(one, needs_said=looked[cid]["needs_said"])
        results[cid] = dict(_checked(pack, prep, one, actor=actor), **extra, **meta[cid])
    cost = round(sum(float(r.get("cost_usd") or 0) for r in results.values()), 6)
    batch_ids = [b["batch_id"] for b in (got, second) if b and b["batch_id"]]
    return {"ok": got["ok"] and (second is None or second["ok"]),
            "error": got["error"] or (second or {}).get("error", ""),
            "detail": got["detail"] or (second or {}).get("detail", ""),
            "batch_id": got["batch_id"], "batch_ids": batch_ids, "cost_usd": cost,
            "worst_usd": got["worst_usd"] + ((second or {}).get("worst_usd") or 0.0),
            "results": results, "requests": meta}


def _needs_rounds(preps: dict, firsts: dict, *, actor: str) -> dict:
    """``{custom_id: {"request", "first", "needs_said"}}``: each v6 first answer naming a need,
    looked up and recorded as `explain_pack`'s round does (`needs.run`), and the follow-up's
    batched request (custom_id ``<first>-n``, the subject naming its parent); a round refused
    or with nothing looked up holds only its ``needs_said``, as `_ask_round` says it."""
    from modules.ai import needs as N
    from modules.ai import nl_query

    out = {}
    for cid, (pack, prompt, prep) in preps.items():
        one = firsts.get(cid)
        if not prep["round"] or not one or not one.get("ok"):
            continue
        wanted = list(getattr(one.get("output"), "needs", None) or [])
        if not wanted:
            continue
        held = {}

        def follow(results, link, held=held):
            held["looked"], held["link"] = results, link
            return None
        rnd = N.run(one["call_id"], pack.get("network") or "",
                    [n.model_dump(mode="json") for n in wanted], actor=actor, follow=follow)
        if not rnd["ok"] or "looked" not in held:
            out[cid] = {"needs_said": rnd["error"] or "nothing could be looked up"}
            continue
        out[cid] = {"first": one, "needs_said": "; ".join(
            f"{r['kind']} {r['subject']}: {r['state']}" for r in rnd["results"]),
            "request": {"custom_id": f"{cid}-n", "feature": FEATURE, "prompt": prompt,
                        "schema": prep["schema"], "context": prep["ctx"],
                        "parts": dict(prep["data"], looked_up=nl_query.looked_up(
                            held["looked"])),
                        "subject": dict(prep["subject"], **held["link"])}}
    return out


def _round_result(first: dict, rnd: dict, second: dict) -> dict:
    """The follow-up's result in place of the first's, as `_ask_round` gives it: the round's
    cost, ``parent_call_id`` the first call's; the second batch's refusal when it had none."""
    got = (second or {}).get("results", {}).get(rnd["request"]["custom_id"]) or {
        "ok": False, "error": (second or {}).get("error") or "no_result",
        "detail": (second or {}).get("detail") or "the follow-up's batch returned no result",
        "call_id": "", "cost_usd": 0.0}
    total = round((first.get("cost_usd") or 0) + (got.get("cost_usd") or 0), 6)
    return dict(got, cost_usd=total, parent_call_id=first["call_id"],
                needs_said=rnd["needs_said"])
