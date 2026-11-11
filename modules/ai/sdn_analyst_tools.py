"""The SDN analyst with the trace tool (Lab 9 B4, the advanced technique; docs/HEAL_TO_INTENT.md
19.12 and 19.13; the TA's approval of 2026-11-10: "the tool-calling read loop invoking the trace
app, baseline = the same analyst without tools on a fixed snapshot, compared on findings, misses,
false positives and API cost"). SDN › Flows' **Analyse with the trace tool**, beside B1's
Analyse this network (`modules/sdn/analyst.py`), on the same kept snapshot.

**Here, in modules/ai/, and not beside B1 in modules/sdn/** (tests/test_read_loop_never_read.py):
nothing that changes a device imports the read loop. This module draws an advisory answer and
writes only its own analysis record; it acts on nothing.

**The technique is the read loop** (`modules/ai/read_loop.py`, item 3's loop, reused whole: its
two passes, its three reads a pass, its check of each request, its mask and 4 KiB cut of each
answer, its send log): pass 1 is B1's call with an optional ``reads`` field; Mercury checks
each read asked for and answers the allowed ones; pass 2 has the reads and cannot ask again.
Same model, same prompt otherwise (prompts/sdn_analyse_tools.v1.md and .v2.md are B1's text
with the reads' part added; .v3.md and .v4.md are the same on B1's v2, `PASSES_OF`), same
snapshot facts.

**The tools are a closed set of reads served from the SEALED snapshot** (`SEALED`, the
``seal`` transport, the topology class): nothing is read live, ever, during an analysis or an
evaluation. The executor (`_run`) is handed the snapshot and nothing else.
- ``trace(src, dst, proto, port)``: Mercury's flow-table trace (`modules/sdn/trace.py`, its one
  walk, `trace.over`) over the snapshot's own flow tables, links and hosts (`sealed_fabric`);
  IPv4 and IPv6 alike, ICMP echo or TCP or UDP to a port;
- ``switch_flows(dpid)``: a switch's flows and drop flows as the snapshot holds them;
- ``port_stats(dpid, port?)``: its ports' descriptions and rates;
- ``link_state(dpid, port)``: one port's state and the links that touch it.
Each request's arguments are parsed by their shape and compared with what the snapshot holds
(a switch it holds, a port that switch lists, a host its host table lists), else refused, naming
both operands.

**Capped:** at most two calls (the loop's passes) and three reads; each call by its pin
(pins/sdn_analyse_tools.json: its prompt and answer bounds, the per-call cap the gateway asks);
and the loop's whole spend by `TOTAL_TOKEN_CAP`, the gateway's over-estimate of both passes'
prompts plus each one's whole answer bound, asked before pass 2 is sent (`_total_capped`).

**Checked like B1:** the final answer is B1's findings schema, held by B1's own `check` to the
snapshot's evidence ids and the ids of the reads that ran (``read:<n>``, citable; a trace's
answer names snapshot ids, citable as they are). A planted issue is found only by the snapshot's
ids a kept finding cites (`analyst.marks`), never by a read id.

**Recorded:** each call in the record of AI calls (a person's trigger, the subject the
snapshot), each read in the send log (`read_log`, History › Reads), and the analysis with its
tool calls kept beside B1's in the network's folder (``latest.json`` ``analysis_tools``).

**Judged in code** (`judge`, the false-positive rule, shared with the evaluation): a kept
finding citing a planted issue's evidence is ``planted``; one citing a fact code measures as
abnormal (`abnormal_ids`: a port down, a link not up, a drop flow, a port dropping packets or at
`LOAD_HIGH` of its speed) is ``real``; an ``info`` one is a ``note``; any other is a
``false_positive``.
"""

import hashlib
import ipaddress
import json
import logging
import os
import time
import uuid
from typing import List

from modules.ai import read_loop as RL
from modules.ai.schemas import StrictModel, register
from modules.sdn import analyst as AN

log = logging.getLogger(__name__)

FEATURE = "sdn_analyse_tools"
#: The loop's two prompts (pass 1, pass 2) by the version of B1's prompt each pair is built on
#: (`analyst.SCHEMA_OF`; "same prompt otherwise": each is that version's text with the reads'
#: part added). B1's v2 (an evidence item is one id and nothing else) is the trace tool's v3
#: and v4; pass 2's says the same of a read cited as ``read:<n>``.
PASSES_OF = {1: (("sdn_analyse_tools", 1), ("sdn_analyse_tools", 2)),
             2: (("sdn_analyse_tools", 3), ("sdn_analyse_tools", 4))}
#: The pair in use: the one built on B1's prompt in use (`analyst.PROMPT`), so the two
#: techniques are adopted together and the comparison stays the reads' alone.
PROMPT_FIRST, PROMPT_SECOND = PASSES_OF[AN.PROMPT[1]]
#: The loop's whole spend at most, in tokens: both passes' prompts by the gateway's fallback
#: over-estimate and each pass's whole answer bound (its pin's max_tokens). Provisional, not
#: measured: the lab's five switches are about 25,000 tokens a pass (pins/sdn_analyse.json);
#: two passes of them with three 4 KiB reads are about 64,000. Two calls at the pin's bounds
#: (2 x 52,096) are over it, so this binds first on a large snapshot.
TOTAL_TOKEN_CAP = 80000
#: A trace's branches sent at most (a flood is one branch per port it leaves by); the rest
#: counted.
TRACE_BRANCHES_SENT = 6
#: A port at or above this share of its speed is abnormal by code (`abnormal_ids`).
LOAD_HIGH = 80.0
#: The answers' allowance for the page's "about $X" (`estimate`): B1's.
OUTPUT_TOKENS_ESTIMATE = AN.OUTPUT_TOKENS_ESTIMATE
STEPS = (
    ("snapshot", "the kept snapshot the region names, its seal checked: the same one B1's "
                 "Analyse this network reads; refused, and nothing sent, if it changed"),
    ("first", "one recorded, capped AI call as the person who pressed it, B1's prompt and the "
              "snapshot's facts with the tools it may ask for and the hosts a trace can take; "
              "it answers, or asks for at most 3 reads"),
    ("check_reads", "each read asked for held to the closed set (trace, a switch's flows, its "
                    "ports, a link's state), its arguments parsed by shape and compared with "
                    "what the snapshot holds; anything else refused, naming why"),
    ("reads", "the allowed reads answered from the sealed snapshot alone, never a live read: "
              "the trace walks its flow tables; each answer masked and cut to 4 KiB, and "
              "logged before anything of it is sent"),
    ("second", "a second recorded call with the reads, which cannot ask again, only within the "
               "loop's total token cap and the gateway's caps; otherwise the first answer "
               "stands, said so"),
    ("check", "the final answer checked as B1's: every evidence id held to the snapshot's and "
              "to the reads that ran; a finding citing nothing it holds dropped and counted"),
    ("compare", "each planted issue found or missed by the snapshot's ids its findings cite; "
                "beside B1's answer on the same snapshot: findings, found, missed, false "
                "positives by Mercury's rule, calls and cost"),
)


# ───────────────────────────────────────────────────────────────────────────── the seal

def _dpid_int(dpid_hex) -> int:
    return int(str(dpid_hex), 16)


def _port_value(port):
    """A port as the trace takes it: a number, or a reserved name (``LOCAL``)."""
    text = str(port)
    return int(text) if text.isdigit() else text


def _switch(snap: dict, dpid_hex: str) -> dict:
    return next((s for s in snap.get("switches") or [] if s.get("dpid_hex") == dpid_hex), {})


def partial_words(s: dict) -> str:
    """Why the snapshot holds only part of a switch's table, or "" when it holds it whole."""
    if s.get("partial"):
        return s["partial"]
    if (s.get("flows_sent") or 0) < (s.get("flows_total") or 0):
        return (f"its {s['flows_sent']} busiest of {s['flows_total']} forwarding flows, every "
                "drop flow beside them")
    return ""


def sealed_fabric(snap: dict) -> dict:
    """The kept snapshot *snap* in `trace.fabric`'s shape, from the snapshot alone (no store,
    no controller, no reader): each switch's flows and drop flows, its ports, the links up, and
    the hosts the collection learned (on an edge port). ``state`` ``no_hosts`` when the snapshot
    holds no host table, so no trace can start."""
    if "hosts" not in snap:
        return {"state": "no_hosts", "controllers": [],
                "why": ("this snapshot holds no host table (it was kept before the collection "
                        "read the controller's hosts): Collect now keeps one that does")}
    by_conn = {}

    def conn_of(name):
        return by_conn.setdefault(name, {
            "name": name, "label": "", "state": "read", "why": "",
            "read_at": snap.get("collected_at") or "", "hosts_note": "", "switches": {},
            "links": {}, "hosts": []})

    for s in snap.get("switches") or []:
        c = conn_of(s.get("connection") or "")
        ports = {_port_value(p["port_no"]): p.get("name") or "" for p in s.get("ports") or []}
        if not ports:
            ports = {_port_value(r["port_no"]): "" for r in s.get("rates") or []
                     if r.get("port_no") is not None}
        flows = [dict(f) for f in list(s.get("flows") or []) + list(s.get("drops") or [])]
        unread = s.get("state") == "unreadable"
        c["switches"][_dpid_int(s["dpid_hex"])] = {
            "name": s.get("name") or "", "ports": ports or None,
            "flows": None if unread else flows,
            "why": (f"its flow table could not be read: {s.get('error') or 'no answer'}"
                    if unread else "")}
    for ln in snap.get("links") or []:
        if ln.get("state") != "up" or len(ln.get("ends") or []) != 2:
            continue
        (a, ap), (b, bp) = ln["ends"]
        c = conn_of(ln.get("connection") or "")
        one, two = (_dpid_int(a), _port_value(ap)), (_dpid_int(b), _port_value(bp))
        c["links"][one], c["links"][two] = two, one
    for h in snap.get("hosts") or []:
        c = conn_of(h.get("connection") or "")
        at = (_dpid_int(h["dpid_hex"]), _port_value(h["port_no"]))
        if at in c["links"]:
            continue
        c["hosts"].append({"mac": h.get("mac") or "", "ipv4": list(h.get("ipv4") or []),
                           "ipv6": list(h.get("ipv6") or []), "dpid": at[0],
                           "dpid_hex": h["dpid_hex"], "port_no": at[1],
                           "port_name": h.get("port_name") or ""})
    return {"state": "read", "why": "", "controllers": list(by_conn.values()),
            "netbox": sealed_netbox(snap)}


def sealed_netbox(snap: dict):
    """NetBox's view as the snapshot keeps it (`analyst.build_snapshot`'s ``netbox``), in
    `sdn.known.read`'s shape, or None for a snapshot kept without one: the trace tool's ends by
    NetBox name or address come from the seal, never from a live read (C2950, C3013)."""
    kept = snap.get("netbox")
    if not kept:
        return None
    return {"state": "read", "why": "", "sha": kept.get("sha") or "",
            "rows": list(kept.get("rows") or []),
            "names": {int(d, 16): n for d, n in (kept.get("names") or {}).items()},
            "hosts": kept.get("hosts"), "devices": kept.get("devices") or 0}


def trace_answer(snap: dict, src: str, dst: str, proto: str = "icmp", port=None) -> dict:
    """The trace tool: `trace.over` on `sealed_fabric(snap)`, answered short for the model:
    ``{"state", "ending", "words", "source", "destination", "family", "branches": [{"outcome",
    "words", "hops": [{"switch", "in", "out", "flows"}]}], "more", "evidence", "partial"}``, or
    ``{"refused": why}``. *evidence* is every snapshot id the walk passed (each hop's deciding
    flows, its ports' and rates' ids, the links crossed); *partial* each switch walked whose
    table the snapshot holds only part of, which a flow it does not hold could decide
    otherwise. The ends are the walk's own (`sdn.known.resolve`): a host the snapshot lists,
    one named as NetBox names it where the snapshot keeps NetBox's view, and, for *dst*, an
    address nothing lists, followed to how it ends (*ending*), with what that assumes
    (``assumed``) and how a name was resolved (``notes``) said."""
    from modules.sdn import trace as TR

    fab = sealed_fabric(snap)
    if fab["state"] != "read":
        return {"refused": fab["why"]}
    got = TR.over(fab, snap.get("network") or "", src, dst, protocol=proto, port=port)
    if not got.get("ok"):
        return {"refused": got.get("error") or "the trace could not start"}
    ids = AN.evidence_ids(snap)
    down = {(s.get("connection"), s["dpid_hex"], str(p["port_no"]))
            for s in snap.get("switches") or [] for p in s.get("ports") or []
            if not p.get("link_up")}
    conn = got.get("controller") or ""
    evidence, partial, branches = [], [], []

    def cite(i):
        if i in ids and i not in evidence:
            evidence.append(i)

    for b in got.get("branches") or []:
        hops = []
        for n, h in enumerate(b["hops"]):
            flows = [f.get("id") or "" for f in h.get("flows") or []]
            for i in flows:
                cite(i)
            for p in (h.get("in_port"), h.get("out_port")):
                if p is not None:
                    cite(f"port:{conn}:{h['dpid_hex']}:{p}")
                    cite(AN.rate_ref(conn, h["dpid_hex"], p))
            if h.get("out_port") is not None and n + 1 < len(b["hops"]):
                nxt = b["hops"][n + 1]
                cite(AN.link_ref(conn, (h["dpid_hex"], h["out_port"]),
                                 (nxt["dpid_hex"], nxt["in_port"])))
            why = partial_words(_switch(snap, h["dpid_hex"]))
            if why and h["dpid_hex"] not in partial:
                partial.append(h["dpid_hex"])
            hops.append({"switch": h["dpid_hex"], "in": h.get("in_port"),
                         "out": h.get("out_port"), "flows": flows})
        words = b["words"]
        last = b["hops"][-1] if b["hops"] else {}
        if (conn, last.get("dpid_hex"), str(last.get("out_port"))) in down:
            words += (f" (the snapshot reports {last['dpid_hex']} port {last['out_port']}'s link "
                      "DOWN)")
        branches.append({"outcome": b["outcome"], "words": words, "hops": hops})
    words = got["words"]
    if partial:
        words += ("; walked over part of the table of " + ", ".join(partial)
                  + " (the flows the snapshot holds): a flow it does not hold may decide "
                  "otherwise")
    pkt = got.get("packet") or {}
    out = {"state": got["state"], "ending": got.get("ending") or "", "words": words,
           "source": got["source"]["words"], "destination": got["destination"]["words"],
           "family": 6 if "ipv6_src" in pkt else 4, "proto": proto, "port": port,
           "branches": branches[:TRACE_BRANCHES_SENT],
           "more": max(0, len(branches) - TRACE_BRANCHES_SENT) + (got.get("more") or 0),
           "evidence": evidence, "partial": partial}
    if got.get("assumed"):
        out["assumed"] = got["assumed"]
    if got.get("notes"):
        out["notes"] = list(got["notes"])
    return out


def _flow_short(f: dict) -> dict:
    return {"id": f["id"], "table": f.get("table_id", 0), "priority": f.get("priority", 0),
            "match": AN._match_words(f.get("match")),                 # noqa: SLF001 (B1's words)
            "actions": AN._action_words(f.get("actions")),            # noqa: SLF001
            "packets": f.get("packet_count") or 0, "bytes": f.get("byte_count") or 0}


def _flows_answer(snap: dict, dpid: str) -> dict:
    s = _switch(snap, dpid)
    return {"switch": dpid, "forwarding_flows": s.get("flows_total", 0),
            "listed": s.get("flows_sent", 0), "partial": partial_words(s),
            "flows": [_flow_short(f) for f in s.get("flows") or []],
            "drops": [_flow_short(f) for f in s.get("drops") or []]}


def _same_port(row: dict, port) -> bool:
    return port is None or str(row.get("port_no")) == str(port)


def _ports_answer(snap: dict, dpid: str, port=None) -> dict:
    s = _switch(snap, dpid)
    return {"switch": dpid, "port": port,
            "ports": [p for p in s.get("ports") or [] if _same_port(p, port)],
            "rates": [r for r in s.get("rates") or [] if _same_port(r, port)],
            "described": bool(s.get("ports"))}


def _link_answer(snap: dict, dpid: str, port) -> dict:
    s = _switch(snap, dpid)
    desc = next((p for p in s.get("ports") or [] if _same_port(p, port)), None)
    links = [{"id": ln["id"], "state": ln.get("state"), "words": ln.get("words")}
             for ln in snap.get("links") or []
             if [dpid, str(port)] in [list(map(str, e)) for e in ln.get("ends") or []]]
    return {"switch": dpid, "port": port,
            "port_state": desc if desc is not None else "no port description read",
            "links": links}


def _summary(op: str, answer: dict) -> str:
    """A read's answer in one short line, for the screen's list of tool calls."""
    if "refused" in answer:
        return f"could not run: {answer['refused']}"[:200]
    if op == "trace":
        return answer["words"][:200]
    if op == "switch_flows":
        return (f"{answer['listed']} of {answer['forwarding_flows']} forwarding flows, "
                f"{len(answer['drops'])} drop flows")
    if op == "port_stats":
        downs = sum(1 for p in answer["ports"] if not p.get("link_up"))
        return (f"{len(answer['ports'])} port descriptions ({downs} down), "
                f"{len(answer['rates'])} rates")
    state = answer["port_state"]
    said = state if isinstance(state, str) else (
        f"link {'up' if state.get('link_up') else 'DOWN'}, admin "
        f"{'up' if state.get('admin_up') else 'down'}")
    return f"{said}; {len(answer['links'])} link(s): " + ", ".join(
        f"{ln['id']} {ln['state']}" for ln in answer["links"])[:160]


def _run(op: str, args: dict, requests: list, scope: dict):
    """The sealed family's executor: *scope*'s snapshot answers, nothing else (no store, no
    controller, no reader). Each answer's one-line summary is kept in *scope*'s ``said``."""
    del requests
    snap = scope["snapshot"]
    if op == "trace":
        answer = trace_answer(snap, args["src"], args["dst"], args["proto"], args.get("port"))
    elif op == "switch_flows":
        answer = _flows_answer(snap, args["dpid"])
    elif op == "port_stats":
        answer = _ports_answer(snap, args["dpid"], args.get("port"))
    else:
        answer = _link_answer(snap, args["dpid"], args["port"])
    scope.setdefault("said", {})[_said_key(op, args)] = _summary(op, answer)
    return answer


def _said_key(op: str, args: dict) -> str:
    return op + json.dumps(args, sort_keys=True, default=str)


# ── the comparisons each request's arguments are held to ──────────────────────────────────────

def _switch_listed(value, scope) -> str:
    held = [s["dpid_hex"] for s in scope["snapshot"].get("switches") or []]
    if value in held:
        return ""
    return f"{value} is not a switch the snapshot holds: it holds {RL._listed(held)}"  # noqa: SLF001


def _port_listed(args: dict, scope) -> str:
    if "port" not in args:
        return ""
    s = _switch(scope["snapshot"], args["dpid"])
    listed = sorted({str(p["port_no"]) for p in s.get("ports") or []}
                    | {str(r["port_no"]) for r in s.get("rates") or []})
    if str(args["port"]) in listed:
        return ""
    return (f"port {args['port']} is not a port the snapshot lists for {args['dpid']}: it "
            f"lists {RL._listed(listed)}")                                   # noqa: SLF001


def _host_listed(value, scope) -> str:
    """Whether *value* (an address, a MAC or a NetBox name) is a host the snapshot knows: one
    its host table lists, or, where the snapshot keeps NetBox's view, one of its interfaces by
    name, address or MAC. The trace's own resolution (`sdn.known.resolve`) then says where it
    is, or refuses naming why."""
    snap = scope["snapshot"]
    if "hosts" not in snap:
        return ("the snapshot holds no host table (kept before the collection read hosts), so "
                "no trace can start")
    hosts = snap.get("hosts") or []
    for h in hosts:
        if h.get("mac") == value:
            return ""
        for a in list(h.get("ipv4") or []) + list(h.get("ipv6") or []):
            try:
                if str(ipaddress.ip_address(a)) == value:
                    return ""
            except ValueError:
                continue
    kept = snap.get("netbox") or {}
    for r in kept.get("rows") or []:
        if value in (r.get("mac"), *(r.get("ipv4") or []), *(r.get("ipv6") or [])) \
                or str(r.get("name") or "").lower() == str(value).lower():
            return ""
    said = f"{value} is no host the snapshot lists ({len(hosts)} hosts listed)"
    if kept:
        said += (f", and none NetBox names in the NSOT export it keeps ({kept.get('sha')}: "
                 f"{len(kept.get('rows') or [])} interfaces)")
    return said


def _destination_known(value, scope) -> str:
    """A trace's *dst*: a host the snapshot knows (`_host_listed`), or any IPv4 or IPv6
    address, which the walk follows to how it ends (a drop, the table-miss, a port)."""
    why = _host_listed(value, scope)
    if not why or "holds no host table" in why:
        return why
    try:
        ipaddress.ip_address(str(value))
    except ValueError:
        return why
    return ""


def _trace_args(args: dict, scope) -> str:
    del scope
    if args["proto"] == "icmp" and "port" in args:
        return f"an ICMP echo has no port, and {args['port']} was given"
    if args["proto"] != "icmp" and "port" not in args:
        return f"a {args['proto'].upper()} trace needs its destination port"
    if args["src"] == args["dst"]:
        return f"the source and the destination are both {args['src']}"
    return ""


DPID = RL.Text(r"[0-9a-f]{16}", "a switch's datapath id, 16 lower-case hex digits", 16)
SWITCH_PORT = RL.AnyOf((RL.Integer(0, 0xFFFFFF00, "a port number"),
                        RL.Text(r"LOCAL", "LOCAL", 5)), "a port number, or LOCAL")
#: A host as a trace takes it: an address, a MAC, or the name NetBox gives it (one token, no
#: colon, so a MAC in another form is never read as a name).
HOST = RL.AnyOf((RL.Address(), RL.Mac(),
                 RL.Text(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", "a NetBox name", 64)),
                "a host's IPv4 or IPv6 address, or its MAC in lower-case colon form, or its "
                "NetBox name")

#: The closed set: each read answered from the sealed snapshot (``seal``), the topology class.
SEALED = RL.ReadFamily(
    name="sdn_sealed", transport="seal", egress_class="topology", run=_run,
    words="the SDN analyst's reads, each answered from the kept snapshot it analyses",
    operations=(
        RL.Operation("trace", {"src": RL.Arg(HOST, against=_host_listed),
                               "dst": RL.Arg(HOST, against=_destination_known),
                               "proto": RL.Arg(RL.Text(r"icmp|tcp|udp", "icmp, tcp or udp", 4)),
                               "port": RL.Arg(RL.Integer(1, 65535, "a port from 1 to 65535"),
                                              required=False)},
                     sends=("snapshot trace {src} {dst} {proto}",), against=_trace_args,
                     words="a packet walked through the snapshot's flow tables"),
        RL.Operation("switch_flows", {"dpid": RL.Arg(DPID, against=_switch_listed)},
                     sends=("snapshot flows {dpid}",),
                     words="a switch's flows and drop flows as the snapshot holds them"),
        RL.Operation("port_stats", {"dpid": RL.Arg(DPID, against=_switch_listed),
                                    "port": RL.Arg(SWITCH_PORT, required=False)},
                     sends=("snapshot ports {dpid}",), against=_port_listed,
                     words="a switch's port descriptions and rates"),
        RL.Operation("link_state", {"dpid": RL.Arg(DPID, against=_switch_listed),
                                    "port": RL.Arg(SWITCH_PORT)},
                     sends=("snapshot link {dpid} {port}",), against=_port_listed,
                     words="one port's state and the links that touch it"),
    ))

#: One entry of pass 1's ``reads`` (`read_loop.request_model`).
SealedRead = RL.request_model(SEALED)


@register("sdn_analyse_tools", 1)
class NetworkAnalysisReads(StrictModel):
    """Pass 1: B1's findings, and at most 3 reads asked of Mercury (a fourth is refused)."""
    findings: List[AN.Finding]
    reads: List[SealedRead] = []


def _cites(answer) -> list:
    """Every id the answer cites, each entry as its id (`analyst.evidence_id`: a whole line
    cites its leading id), so the loop holds a read cited as a whole line, ``read:<n> <its
    words>``, to the same rule as one cited by its id: it ran and was sent, or the answer
    does not stand."""
    return [AN.evidence_id(e) for f in getattr(answer, "findings", None) or []
            for e in f.evidence]


def _no_whole_refusal(answer, *, read_ids) -> str:
    """The loop's own check of a whole answer: none. B1's check (`analyst.check`) drops what
    cites nothing the snapshot holds, finding by finding, after the loop."""
    del answer, read_ids
    return ""


@register("sdn_analyse_tools", 2)
class NetworkAnalysisReadsV2(StrictModel):
    """Pass 1: B1's findings, and at most 3 reads asked of Mercury (a fourth is refused)."""
    # On B1's prompt v2: each evidence item described as an id alone (`analyst.FindingV2`).
    findings: List[AN.FindingV2]
    reads: List[SealedRead] = []


#: Pass 1's schema by B1's prompt version (pass 2's is B1's own, `analyst.SCHEMA_OF`).
READS_SCHEMA_OF = {1: NetworkAnalysisReads, 2: NetworkAnalysisReadsV2}
#: The loop by B1's prompt version (`PASSES_OF`): the one in use, and each candidate, asked
#: only by the evaluation (`ask_snapshot`'s *prompt*) until its measurement adopts it.
LOOPS = {v: RL.LoopFeature(task=FEATURE, first=(PASSES_OF[v][0], READS_SCHEMA_OF[v]),
                           second=(PASSES_OF[v][1], AN.SCHEMA_OF[v]),
                           check=_no_whole_refusal, cites=_cites)
         for v in sorted(PASSES_OF)}
LOOP = LOOPS[AN.PROMPT[1]]


def loop_for(version: int = None):
    """The loop built on *version* of B1's prompt (None: the one in use); ValueError names a
    version no loop is built on."""
    version = AN.PROMPT[1] if version is None else version
    if version not in LOOPS:
        raise ValueError(f"no trace-tool prompts are built on sdn_analyse v{version}; they "
                         f"are built on {', '.join(f'v{v}' for v in sorted(LOOPS))}")
    return LOOPS[version]


# ───────────────────────────────────────────────────────────────────────────── the call

def hosts_text(snap: dict) -> str:
    """The hosts a trace can take, one a line (the trace's own domain; never an evidence id)."""
    from modules.sdn import known

    hosts = snap.get("hosts")
    if hosts is None:
        return "none: this snapshot holds no host table, so the trace cannot be asked for\n"
    kept = snap.get("netbox") or {}
    owner = known.host_names(kept.get("rows"))
    lines = [f"host {h.get('mac')} on switch {h.get('dpid_hex')} port {h.get('port_no')}"
             + (f" ({h['port_name']})" if h.get("port_name") else "")
             + (f", IPv4 {' '.join(h['ipv4'])}" if h.get("ipv4") else "")
             + (f", IPv6 {' '.join(h['ipv6'])}" if h.get("ipv6") else "")
             + (f", NetBox name {owner[h['mac']][0]}" if h.get("mac") in owner else "")
             for h in hosts]
    # Where the snapshot keeps NetBox's view (C2950): each interface NetBox cables to a switch
    # port that the controller has not learnt is a host a trace can take too, by its name.
    learnt = {h.get("mac") for h in hosts}
    for r in kept.get("rows") or []:
        if r.get("mac") and r["mac"] not in learnt and r.get("dpid") is not None \
                and r.get("port_no") is not None:
            lines.append(f"host {r['mac']} on switch {r['dpid']:016x} port {r['port_no']}, "
                         f"NetBox name {r['name']}"
                         + (f", IPv4 {' '.join(r['ipv4'])}" if r.get("ipv4") else "")
                         + (f", IPv6 {' '.join(r['ipv6'])}" if r.get("ipv6") else "")
                         + ", placed by NetBox's cable (the controller has not learnt it)")
    return "\n".join(lines or ["none listed"]) + "\n"


def _chars(prompt: tuple, parts: dict, context: dict) -> int:
    from modules.ai import prompts

    return (len(prompts.load(*prompt)["text"]) + len(json.dumps(parts or {}))
            + len(json.dumps(context or {})) + 1500)


def _total_capped(cap: int = None):
    """The gateway's ask, held to `TOTAL_TOKEN_CAP` (or *cap*) across the loop's passes: each
    pass counted by the gateway's over-estimate of its prompt and its whole answer bound; pass
    2 is refused before it is sent when it would take the loop past the cap (a cap kind, so the
    loop says "second pass not run" and keeps pass 1's answer)."""
    from modules.ai import gateway, profiles

    limit = TOTAL_TOKEN_CAP if cap is None else int(cap)
    spent = {"tokens": 0, "calls": 0}

    def ask(feature, prompt, schema, parts, *, trigger=None, **kw):
        pass_tokens = (gateway.tokens_of_chars(_chars(prompt, parts, kw.get("context")))
                       + int(profiles.task(feature)["max_tokens"]))
        if spent["calls"] and spent["tokens"] + pass_tokens > limit:
            return {"ok": False, "error": "over_cap", "call_id": "", "cost_usd": 0.0,
                    "detail": (f"the loop's first pass took up to {spent['tokens']} tokens and "
                               f"this one up to {pass_tokens}, over its total cap of {limit} "
                               "(TOTAL_TOKEN_CAP); nothing of it was sent")}
        spent["calls"] += 1
        spent["tokens"] += pass_tokens
        return gateway.ask(feature, prompt, schema, parts, trigger=trigger, **kw)
    return ask


def _reads_shown(records: list, said: dict) -> list:
    out = []
    for r in records or []:
        row = {k: r.get(k) for k in ("id", "op", "args", "verdict", "reason", "why")}
        row["short"] = (said.get(_said_key(r.get("op") or "", r.get("args") or {}), "")
                        if r.get("verdict") == "run" else "")
        row["cut"] = bool(r.get("cut"))
        out.append(row)
    return out


def ask_snapshot(network: str, snap: dict, *, actor: str, trigger: dict, send=None,
                 today: str = None, now: float = None, cap: int = None,
                 prompt: int = None) -> dict:
    """The tool-calling analysis of *snap* (sealed, in hand), reading and writing no analyst
    store: the loop's two passes at most (`read_loop.run` over `SEALED`), then B1's check of the
    final answer. B4's technique arm (scripts/nmas-sdn-b4-eval) and the press's core. Refused
    before any call on the classification marking or the topology class off
    (``refused_before``). ``{"ok", "error", "detail", "network", "snapshot_id", "actor", "at",
    "call_id", "calls", "cost_usd", "model", "technique", "passes", "state", "words", "loop",
    "reads", "findings", "dropped", "dropped_words", "removed_ids", "capped"}``. *prompt* is a
    version of B1's prompt whose loop is asked in place of the one in use (`loop_for`: a
    candidate measured before it is adopted; the evaluation's ``--prompt``), never a press's."""
    from modules.ai import egress_classes, profiles

    loop = loop_for(prompt)
    now = time.time() if now is None else now
    snap_id = snap.get("id", "")
    base = {"ok": False, "error": "", "detail": "", "network": network, "snapshot_id": snap_id,
            "collected_at": snap.get("collected_at"), "actor": actor, "at": AN._iso(now),  # noqa: SLF001
            "call_id": "", "calls": [], "cost_usd": 0.0, "technique": "trace_tool",
            "model": profiles.task(FEATURE)["model"], "passes": 0, "state": "", "words": "",
            "loop": "", "reads": [], "findings": [], "dropped": 0, "dropped_words": "",
            "removed_ids": 0, "capped": 0}
    marked = egress_classes.classification_marking(network)
    if marked:
        return dict(base, error="classified", refused_before=True,
                    detail=f"{network} carries the classification marking {marked!r}, which "
                           "forces AI off; nothing was sent")
    gate = egress_classes.topology_allowed(network)
    if not gate["allowed"]:
        return dict(base, error="withheld", refused_before=True,
                    detail=("the snapshot's flows and port rates, and every read of it, are "
                            f"the topology class, and {gate['why']}; nothing was sent"))
    scope = {"snapshot": snap, "said": {}}
    got = RL.run(SEALED, loop, ask=_total_capped(cap), network=network,
                 data={"snapshot": AN.facts(snap), "hosts": hosts_text(snap)}, actor=actor,
                 trigger=trigger, subject={"kind": "sdn_snapshot", "id": snap_id, "devices": []},
                 scope=scope, send=send, today=today)
    calls_made = [c for c in got.get("call_ids") or [] if c]
    shown = (got.get("second") or {}).get("call_id") if got.get("pass") == 2 else \
        (got.get("first") or {}).get("call_id")
    out = dict(base, call_id=shown or "", calls=calls_made,
               cost_usd=round(float(got.get("cost_usd") or 0.0), 6), passes=got.get("pass", 0),
               state=got.get("state", ""), words=got.get("words", ""),
               loop=got.get("loop", ""), reads=_reads_shown(got.get("reads"), scope["said"]))
    if got.get("state") == "failed":
        first = got.get("first") or {}
        return dict(out, error=first.get("error") or got.get("error") or "failed",
                    detail=first.get("detail") or got.get("detail") or "")
    if got.get("state") == "refused_by_check":
        return dict(out, error="check", detail=got.get("why") or "")
    ran = {r["id"] for r in got.get("reads") or [] if r.get("verdict") == "run"}
    checked = AN.check(got["answer"], AN.evidence_ids(snap) | ran)
    return dict(out, ok=True, **checked)


def analyse(network: str, snap_id: str, *, actor: str, trigger: dict, send=None,
            today: str = None, now: float = None) -> dict:
    """Analyse with the trace tool, on the kept snapshot *snap_id* of *network* (`STEPS`): the
    snapshot read and its seal checked, `ask_snapshot`, and the analysis kept under its own id
    beside B1's, the network's ``analysis_tools``."""
    from modules.ai import calls

    now = time.time() if now is None else now
    got = AN.snapshot(network, snap_id)
    if not got["ok"]:
        return dict(AN._refused(network, snap_id, actor, "snapshot",           # noqa: SLF001
                                f"{got['error']}; nothing was sent"),
                    technique="trace_tool", reads=[], calls=[])
    out = ask_snapshot(network, got["snapshot"], actor=actor, trigger=trigger, send=send,
                       today=today, now=now)
    if out.pop("refused_before", False):
        return out
    if out["ok"] and out["call_id"]:
        calls.record_use(out["call_id"], f"shown: {len(out['findings'])} findings after "
                         f"{out['passes']} pass(es) and {len(out['reads'])} read(s), "
                         f"{out['dropped']} dropped by the check", actor=actor,
                         detail=out["words"][:800],
                         links={"page": "/v2/sdn/flows", "anchor": "sdn-analyse"})
    out["id"] = "an-" + hashlib.sha256(f"tools|{snap_id}|{out['call_id']}|{now}|{uuid.uuid4()}"
                                       .encode()).hexdigest()[:16]
    with AN._lock(network):                                                 # noqa: SLF001
        AN._write_json(os.path.join(AN._dir(network), "analyses", f"{out['id']}.json"), out)  # noqa: SLF001
        latest = AN._latest(network)                                        # noqa: SLF001
        latest["analysis_tools"] = out["id"]
        AN._write_json(os.path.join(AN._dir(network), "latest.json"), latest)  # noqa: SLF001
    return out


def estimate(snap: dict) -> dict:
    """``{"tokens", "usd", "calls"}``: the loop's two calls at most, by the gateway's fallback
    over-estimate: pass 1 B1's facts, the hosts and the prompt; pass 2 the same and three
    reads at their 4 KiB cut; each with `OUTPUT_TOKENS_ESTIMATE` of answer."""
    from modules.ai import gateway, profiles, prompts

    model = profiles.task(FEATURE)["model"]
    first = gateway.tokens_of_chars(len(AN.facts(snap)) + len(hosts_text(snap))
                                    + len(prompts.load(*PROMPT_FIRST)["text"]) + 1500)
    second = first + gateway.tokens_of_chars(SEALED.limit * RL.AI_READ_CAP
                                             + len(RL.READS_FORMAT))
    usd = (profiles.cost_usd(model, first, OUTPUT_TOKENS_ESTIMATE)
           + profiles.cost_usd(model, second, OUTPUT_TOKENS_ESTIMATE))
    return {"tokens": first + second, "usd": round(usd, 4), "calls": RL.CALLS_PER_FINDING}


# ───────────────────────────────────────────────────────────────────────────── judged in code

def abnormal_ids(snap: dict) -> set:
    """The snapshot's ids whose facts code measures as abnormal: a port (not the switch's own
    LOCAL) link or admin down, a link not up, every drop flow, a port's rate with drops in the
    interval or at `LOAD_HIGH` or more of its speed."""
    out = {ln["id"] for ln in snap.get("links") or [] if ln.get("state") != "up"}
    for s in snap.get("switches") or []:
        out.update(p["id"] for p in s.get("ports") or []
                   if p.get("port_no") != AN.LOCAL
                   and not (p.get("link_up") and p.get("admin_up")))
        out.update(d["id"] for d in s.get("drops") or [])
        out.update(r["id"] for r in s.get("rates") or []
                   if (r.get("rx_dropped_delta") or 0) > 0 or (r.get("tx_dropped_delta") or 0) > 0
                   or (r.get("load_pct") or 0) >= LOAD_HIGH)
    return out


def judge(finding: dict, issues: list, abnormal: set) -> str:
    """A kept finding, judged in code: ``planted`` (it cites a planted issue's evidence),
    ``real`` (it cites a fact `abnormal_ids` measures), ``note`` (severity info), else
    ``false_positive``."""
    cited = finding.get("evidence") or []
    if any(AN._matches(p, e) for i in issues or [] for p in i.get("evidence") or []  # noqa: SLF001
           for e in cited):
        return "planted"
    if any(e in abnormal for e in cited):
        return "real"
    if finding.get("severity") == "info":
        return "note"
    return "false_positive"


def scored(result: dict, issues: list, snap: dict) -> dict:
    """One analysis against the planted *issues* on its snapshot: ``{"findings", "found",
    "missed", "false_positives", "real", "notes", "judged"}``."""
    rows = AN.marks(issues, result, AN.evidence_ids(snap) if snap else None)
    abnormal = abnormal_ids(snap or {})
    judged = [judge(f, issues, abnormal) for f in (result or {}).get("findings") or []]
    return {"findings": len(judged), "found": sum(r["found"] == "found" for r in rows),
            "missed": sum(r["found"] == "missed" for r in rows),
            "false_positives": judged.count("false_positive"), "real": judged.count("real"),
            "notes": judged.count("note"), "judged": judged}


def summary_of(snap: dict) -> dict:
    """What the network's ``latest.json`` keeps of a snapshot for the trace tool
    (`analyst.save_snapshot`), so a page view reads no snapshot: its estimate, how many hosts
    it holds (None: no host table), and the ids `abnormal_ids` measures."""
    return {"id": snap["id"], "estimate": estimate(snap),
            "hosts": len(snap["hosts"]) if "hosts" in snap else None,
            "abnormal": sorted(abnormal_ids(snap))}


def compare(network: str, b1: dict, tools: dict, kept: dict = None) -> dict:
    """The two analyses of one snapshot side by side, or {} when they are not both answered
    on the same snapshot: per technique its findings, planted found and missed, false
    positives by `judge`, calls and cost. The abnormal ids are the latest snapshot's kept
    summary (*kept*, `summary_of`'s) when it is that snapshot (no snapshot read), else that
    snapshot's own. An analysis checked again (`analyst.recheck`) is counted from that check
    (`analyst.as_checked`), as the sheet is marked, its row saying so (``rechecked``)."""
    if not (b1 and tools and b1.get("ok") and tools.get("ok")
            and b1.get("snapshot_id") == tools.get("snapshot_id")):
        return {}
    sid = b1["snapshot_id"]
    if kept and kept.get("id") == sid and "abnormal" in kept:
        abnormal = set(kept["abnormal"])
    else:
        snap = AN.snapshot(network, sid).get("snapshot")
        if not snap:
            return {}
        abnormal = abnormal_ids(snap)
    issues = AN.planted(network)["issues"]
    rows = []
    for name, first, calls_n in (("Without tools (B1)", b1, 1),
                                 ("With the trace tool", tools, len(tools.get("calls") or []))):
        r = AN.as_checked(first)
        marked = AN.marks(issues, r)
        judged = [judge(f, issues, abnormal) for f in r.get("findings") or []]
        rows.append({"name": name, "findings": len(judged), "rechecked": r is not first,
                     "found": sum(m["found"] == "found" for m in marked),
                     "missed": sum(m["found"] == "missed" for m in marked),
                     "false_positives": judged.count("false_positive"),
                     "real": judged.count("real"), "notes": judged.count("note"),
                     "calls": calls_n, "reads": len(r.get("reads") or []),
                     "cost_usd": float(r.get("cost_usd") or 0.0)})
    return {"snapshot_id": sid, "planted": len(issues), "rows": rows}


def view_part(network: str, latest: dict, snap_sum: dict, b1: dict) -> dict:
    """What the region draws of the trace tool, from the network's small files: its latest
    analysis, whether it is about an older snapshot, its estimate on the latest snapshot and
    that snapshot's hosts (both kept with it), and the comparison with B1's when both answered
    the same snapshot."""
    from modules.ai import profiles

    result = AN.analysis(network, latest.get("analysis_tools") or "")
    kept = latest.get("snapshot_tools") or {}
    if kept.get("id") != snap_sum.get("id"):
        kept = {}
    return {"result": result,
            "stale": bool(result and snap_sum and result.get("snapshot_id") != snap_sum.get("id")),
            "estimate": kept.get("estimate") or {},
            "hosts": kept.get("hosts"),
            "model_words": profiles.profile(profiles.task(FEATURE)["model"])["words"],
            "comparison": compare(network, b1, result, kept)}
