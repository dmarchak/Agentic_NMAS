"""Diagnose… on the device page (board H's amendment, artboards I and J; part H16 of
docs/HEAL_TO_INTENT.md 19.7): the dialog that picks a runbook and its target, lists every read
the run will make on which devices with the worst case, runs it as a job, and draws the
diagnosis in place.

**The target is picked, never typed as a command** (19.3): for "adjacency down", one of the
device's intended neighbours (a link intent holds, or a BGP neighbour intent names), each
offered only when its plan can be made, the rest named with why; for "can't reach", a device
of the network by its intended loopback address, or an address checked as one IPv4 or IPv6
address (an IPv6 address is refused by name: "A can't reach B" reads IPv4 forwarding only until
`show ipv6 cef` is captured, C2415).

**The plan drawn is the plan run.** The card shows `diagnose.plan`'s reads, never its private
intent (`_intent`, the lines the reach runbook walks with, dropped by `shown`); the run is bound
to the plan's fingerprint, and a plan that moved between the card and the press is refused,
naming both, with nothing read.

**The run** is `diagnose.run` as a job (`capture_job`), as the verified person: the request
answers at once, the job announces ``diagnosis`` when it ends, and the card re-reads its result
by id. Nothing here sends a command: every read is the runbook's, through the reads engine.
"""

import hashlib
import ipaddress
import json
import logging

log = logging.getLogger(__name__)

ANNOUNCE_KEYS = ("diagnosis",)
ANNOUNCER = "diagnosis"
#: The two runbooks as the dialog offers them: (key, label, its rest).
CHOICES = (("adjacency_down", "An adjacency is down", "with both ends at intent"),
           ("cant_reach", "Can't reach", "a device or an address from"))
IPV4_ONLY = ("Can't reach reads IPv4 forwarding only: an IPv6 address is refused by name, with "
             "nothing read, until show ipv6 cef is captured and parsed (C2415)")


def _protocols(end: dict) -> str:
    parts = []
    if end.get("ospf"):
        parts.append(f"OSPF, area {end.get('ospf_area')}")
    if end.get("ospfv3"):
        parts.append(f"OSPFv3, area {end.get('ospfv3_area')}")
    if end.get("bgp"):
        parts.append(f"BGP to {end['bgp']['address']}")
    return ", ".join(parts)


def adjacencies(network: str, host: str, model: dict, intents: dict) -> tuple:
    """``(offered, not_offered)``: every adjacency intent expects on *host*, ``{"value",
    "words"}`` each, offered when its plan can be made; the rest ``{"words", "why"}``."""
    from modules.heal import diagnose as D
    from modules.neighbours import _all_lines
    ids = model.get("names") or {}
    me = ids.get(host)
    by_id = {v: k for k, v in ids.items()}
    offered, refused, seen = [], [], set()
    for link in sorted((model.get("links") or {}).values(), key=lambda l: l.get("id") or ""):
        members = link.get("members") or []
        mine = [m for m in members if m["dev"] == me]
        for m in mine:
            for far in members:
                b = by_id.get(far["dev"])
                if not b or far["dev"] == me or (b, m["interface"]) in seen:
                    continue
                seen.add((b, m["interface"]))
                value = f"link|{b}|{m['interface']}"
                words = f"{b} over {m['interface']}"
                try:
                    p = D.plan(network, "adjacency_down", {"device": host, "neighbour": b,
                                                           "interface": m["interface"]},
                               model=model, intents=intents)
                except D.Refused as exc:
                    refused.append({"words": words, "why": str(exc)})
                    continue
                offered.append({"value": value, "words": (
                    f"{words}: {_protocols(p['ends'][0]) or 'no protocol'} (intent)")})
    for peer in D._bgp(_all_lines(intents or {}).get(host) or {}):
        words = f"{peer['address']}: BGP, AS {peer['remote_as']}"
        try:
            D.plan(network, "adjacency_down", {"device": host, "peer": peer["address"]},
                   model=model, intents=intents)
        except D.Refused as exc:
            refused.append({"words": words, "why": str(exc)})
            continue
        offered.append({"value": f"bgp|{peer['address']}", "words": f"{words} (intent)"})
    return offered, refused


def destinations(host: str, lines: dict) -> tuple:
    """``(offered, without)``: every other device of the network with an intended loopback,
    ``{"value": its address, "words"}``, and the names of those without one."""
    from modules.heal import diagnose_reach as R
    offered, without = [], []
    for other in sorted(lines or {}):
        if other == host:
            continue
        name, address = R._loopback(lines[other])
        if address:
            offered.append({"value": address, "words": f"{other} ({name} {address})"})
        else:
            without.append(other)
    return offered, without


def target_of(host: str, runbook: str, adjacency: str, to: str, address: str) -> tuple:
    """``(target, refusal)`` from the form's fields: a choice the card offered, or an address
    checked as one address, never a command."""
    if runbook == "adjacency_down":
        kind, _, rest = (adjacency or "").partition("|")
        if kind == "link" and "|" in rest:
            b, _, port = rest.partition("|")
            return {"device": host, "neighbour": b, "interface": port}, ""
        if kind == "bgp" and rest:
            return {"device": host, "peer": rest}, ""
        return None, "choose which adjacency"
    if runbook == "cant_reach":
        raw = (address or "").strip() or (to or "").strip()
        if not raw:
            return None, "choose a device, or give an address"
        try:
            ip = None if "%" in raw else ipaddress.ip_address(raw)
        except ValueError:
            ip = None
        if ip is None:
            return None, f"{raw!r} is not one IPv4 or IPv6 address"
        return {"device": host, "address": str(ip)}, ""
    return None, f"{runbook!r} is not a runbook"


def fingerprint(p: dict) -> str:
    """The plan's reads and target, hashed: what the card showed, bound to the press."""
    body = json.dumps({"runbook": p["runbook"], "target": p["target"], "reads": p["reads"]},
                      sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:16]


def shown(p: dict) -> dict:
    """The plan as the card draws it: each device's reads in order (a command read in both
    rounds once, "twice"), the per-hop reads for "can't reach", the count, the cap and the worst
    case. The plan's private intent (`_intent`) is not carried."""
    from modules.heal import diagnose as D
    rows = []
    for host, cmds in p["reads"].items():
        firsts = [c for c in cmds if c.get("round", 1) == 1]
        again = {c["command"] for c in cmds if c.get("round", 1) == 2}
        reads = [c["command"] + (f" (twice, {int(D.DELTA_SECONDS)} s apart)"
                                 if c["command"] in again else "") for c in firsts]
        reads += [c["command"] for c in cmds if c.get("round", 1) == 2
                  and c["command"] not in {f["command"] for f in firsts}]
        rows.append({"device": host, "reads": reads, "count": len(cmds)})
    worst = int(p["worst_s"])
    return {"runbook": p["runbook"], "words": p["words"], "rows": rows,
            "per_hop": list(p.get("per_hop") or []), "hops_at_cap": p.get("hops_at_cap") or 0,
            "count": p["count"], "cap": p["cap"],
            "worst": (f"{worst} s" if worst < 120 else f"{worst} s (about {round(worst / 60)} "
                      "min)"),
            "outside": p.get("outside") or "", "fingerprint": fingerprint(p)}


def card(network: str, host: str, back: str, args) -> dict:
    """The dialog for *host*, from intent and the network model alone (nothing asks a device):
    the choices, and the plan of the one chosen (the first offered when none is), or why there
    is none."""
    from modules.heal import diagnose as D
    from modules.neighbours import _all_lines
    runbook = args.get("runbook") or "adjacency_down"
    if runbook not in dict((k, l) for k, l, _r in CHOICES):
        runbook = "adjacency_down"
    c = {"op": "diagnose", "state": "pick", "host": host, "list": network, "back": back,
         "runbook": runbook,
         "choices": [{"value": k, "label": l, "rest": f"{r} {host}" if k == "cant_reach" else r}
                     for k, l, r in CHOICES],
         "adjacency": args.get("adjacency") or "", "to": args.get("to") or "",
         "address": (args.get("address") or "").strip(), "options": [], "not_offered": [],
         "without": [], "plan": None, "error": "", "ipv4_only": IPV4_ONLY}
    try:
        model, intents = D._sources(network)
    except D.Refused as exc:
        c["error"] = str(exc)
        return c
    if runbook == "adjacency_down":
        c["options"], c["not_offered"] = adjacencies(network, host, model, intents)
        if not c["adjacency"] and c["options"]:
            c["adjacency"] = c["options"][0]["value"]
    else:
        c["options"], c["without"] = destinations(host, _all_lines(intents or {}))
        if not c["to"] and not c["address"] and c["options"]:
            c["to"] = c["options"][0]["value"]
    target, why = target_of(host, runbook, c["adjacency"], c["to"], c["address"])
    if target is None:
        c["error"] = why
        return c
    try:
        c["plan"] = shown(D.plan(network, runbook, target, model=model, intents=intents))
    except D.Refused as exc:
        c["error"] = str(exc)
    return c


def start(network: str, host: str, runbook: str, target: dict, shown_fp: str,
          actor: str) -> dict:
    """The press: the plan made again and compared with the one the card showed, then the run
    as a job. ``{"job"}`` or ``{"error"}``, nothing read on a refusal."""
    from modules.heal import diagnose as D
    from modules.nsot import capture_job
    from modules.outbound import mask_payload
    try:
        p = D.plan(network, runbook, target)
    except D.Refused as exc:
        return {"error": f"Not diagnosed: {exc}. Nothing was read."}
    now = fingerprint(p)
    if (shown_fp or "") != now:
        return {"error": (f"Not diagnosed: the reads this diagnosis would make changed since the "
                          f"card was drawn (fingerprint {shown_fp or 'none'} then, {now} now), "
                          "so nothing was read. Read the list again and run it.")}
    job = capture_job.start(network, f"diagnosing {host}: {p['runbook_words']}", actor,
                            lambda _j: mask_payload(D.run(network, runbook, target, actor)),
                            kind="diagnosis", announce_keys=ANNOUNCE_KEYS, announcer=ANNOUNCER)
    return {"job": job}


def _read_link(reference: str) -> dict:
    """A read's reference (``read:<run>:<device>:<command>``) as the link to its run on
    History › Reads, where its masked answer is."""
    parts = (reference or "").split(":", 3)
    if len(parts) != 4 or parts[0] != "read" or not parts[1]:
        return {"run": "", "label": reference or ""}
    return {"run": parts[1], "label": f"{parts[2]} {parts[3]}"}


def result(d: dict) -> dict:
    """The diagnosis as artboard J draws it: its headline and chip, the ranked hypotheses with
    their evidence (each read a link to its run), what was ruled out, what was not checked,
    and each step in order."""
    hyps = [{"n": n, "claim": h.get("claim") or "", "layer": h.get("layer") or "",
             "strength": h.get("strength") or "", "incomplete": list(h.get("incomplete") or []),
             "rule_out": h.get("rule_out") or "", "todo": h.get("todo") or "",
             "evidence": [dict(_read_link(e.get("read") or ""),
                               line=e.get("line") or "", intent=e.get("intent") or "")
                          for e in h.get("evidence") or []]}
            for n, h in enumerate(d.get("hypotheses") or [], 1)]
    state = d.get("state") or ""
    if state in ("refused", "busy"):
        chip, level = ("not diagnosed", "warn")
    elif hyps:
        first = hyps[0]
        chip = (f"{len(hyps) + (d.get('more') or 0)} hypothes"
                f"{'i' if len(hyps) == 1 and not d.get('more') else 'e'}s · the first "
                f"{first['strength']}" + (" (evidence incomplete)" if first["incomplete"] else ""))
        level = "danger" if first["strength"] == "decisive" else "warn"
    else:
        chip, level = "no cause found", "info"
    runs = sorted(set(d.get("runs") or []))
    return {"id": d.get("id") or "", "words": d.get("words") or "",
            "runbook_words": d.get("runbook_words") or "", "actor": d.get("actor") or "",
            "incident": d.get("incident") or "", "started_at": d.get("started_at") or "",
            "finished_at": d.get("finished_at") or "", "chip": chip, "level": level,
            "hypotheses": hyps, "more": d.get("more") or 0,
            "ruled_out": [r.get("check") or "" for r in d.get("ruled_out") or []],
            "not_checked": [{"check": r.get("check") or "", "why": r.get("why") or ""}
                            for r in d.get("not_checked") or []],
            "steps": [{"step": s.get("step") or "", "device": s.get("device") or "",
                       "result": s.get("result") or "", "words": s.get("words") or ""}
                      for s in d.get("steps") or []],
            "commands": d.get("commands") or 0, "cap": d.get("cap") or 0,
            "devices": list(d.get("devices") or []), "stopped": d.get("stopped") or "",
            "runs": runs, "recorded": d.get("recorded")}
