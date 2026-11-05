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
         "without": [], "plan": None, "error": "", "ipv4_only": IPV4_ONLY, "hint": "",
         "busy": []}
    try:
        model, intents = D._sources(network)
    except D.Refused as exc:
        c["error"] = str(exc)
        return c
    if runbook == "adjacency_down":
        c["options"], c["not_offered"] = adjacencies(network, host, model, intents)
        if not c["adjacency"] and c["options"]:
            c["adjacency"], c["hint"] = _hinted(c["options"], args.get("interface") or "",
                                                args.get("neighbour") or "")
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
    # A device the plan reads already in a diagnosis (artboard I's amendment note): named in
    # place of Run, read from the lock's record WITHOUT taking the lock; the press's lock
    # stays the authority. The card re-reads when a diagnosis ends.
    c["busy"] = [{"host": h, "diagnosis": b.get("diagnosis") or "",
                  "actor": b.get("actor") or "an unrecorded caller",
                  "started": (b.get("started_at") or "")[11:16] or "an unrecorded time"}
                 for h, b in D.in_diagnosis(network, [r["device"] for r in c["plan"]["rows"]])
                 .items()]
    return c


def _hinted(options: list, interface: str, neighbour: str) -> tuple:
    """``(adjacency, hint)``: the offered adjacency an alert or incident named (over
    *interface*, matched in the short form intent's links use, or toward *neighbour*), else the
    first offered and the hint saying the named one is not among them (never silently
    swapped)."""
    from modules.nsot.ifnames import abbreviate
    if not interface and not neighbour:
        return options[0]["value"], ""
    short = (abbreviate(interface) or interface) if interface else ""
    for o in options:
        kind, _, rest = o["value"].partition("|")
        b, _, port = rest.partition("|")
        if kind == "link" and ((short and port == short) or (not short and b == neighbour)):
            return o["value"], ""
    named = f"{interface}" if interface else f"the link toward {neighbour}"
    return options[0]["value"], (f"What raised this names {named}: no adjacency intent holds "
                                 "over it is offered, so the first is chosen")


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
                            kind="diagnosis", announce_keys=ANNOUNCE_KEYS, announcer=ANNOUNCER,
                            # C537: the device's page reopens this card while it runs and its
                            # result until each person has opened it (`job_card`).
                            device=host, card="diagnose")
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
    # Can't reach's path, hop by hop (artboard J's right): the chip names the first hop that
    # diverges, as the board draws it ("diverges at <device>").
    hops = [{"n": h.get("n", 0), "device": h.get("device") or "", "read": h.get("read") or "",
             "against": h.get("against") or "", "verdict": h.get("verdict") or "unread"}
            for h in d.get("hops") or []]
    where = next((h["device"] for h in hops if h["verdict"] == "diverges"), "")
    if where and state not in ("refused", "busy"):
        chip, level = f"diverges at {where}", "danger"
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
            "runs": runs, "recorded": d.get("recorded"), "hops": hops}


# ── Diagnose… from an alert and from a can't-fix row (board H's amendment, artboard I) ─────

#: An alert rule whose fault is the device not answering Mercury: its Diagnose… is "can't
#: reach" toward the device, from the device nearest it by intent (`unreachable`).
UNREACHABLE = "unreachable"
OPENS = "Opens the dialog in place of the device's tab: nothing is read until you run it"


def entry(network: str, device: str, *, rule: str = "", interface: str = "",
          neighbour: str = "") -> dict:
    """Diagnose… for something that names *device* (an alert, a can't-fix incident):
    ``{"device", "list", "args", "unreachable", "words", "title"}``, the template's link built
    by `url_for` from them: an alert whose rule is the device unreachable (`UNREACHABLE`),
    "can't reach" toward it from its nearest device (``unreachable``, the redirect route);
    one naming an interface, "an adjacency is down" over it (the card's ``interface`` hint);
    one naming the other end, toward it (``neighbour``); anything else, the dialog on its
    first choice. ``device`` "" and ``words`` the reason when it names no device of a network.
    Reads nothing: the dialog reads intent when it opens, and only a press reads a device."""
    if not device or not network:
        return {"device": "", "list": "", "args": {}, "unreachable": False, "title": "",
                "words": ("it names no device" if not device else
                          f"{device} is in no network Mercury holds")}
    out = {"device": device, "list": network, "args": {}, "unreachable": False,
           "title": OPENS}
    if UNREACHABLE in (rule or "").lower():
        out.update(unreachable=True, words=(f"\"Can't reach\" {device}, from the device "
                                            f"nearest it by intent ({rule})"))
    elif interface:
        out.update(args={"runbook": "adjacency_down", "interface": interface},
                   words=f"\"An adjacency is down\" on {device} {interface}")
    elif neighbour:
        out.update(args={"runbook": "adjacency_down", "neighbour": neighbour},
                   words=f"\"An adjacency is down\" between {device} and {neighbour}")
    else:
        out["words"] = f"on {device}: the runbook and its target chosen on the dialog"
    return out


def from_pack(pack: dict) -> dict:
    """Diagnose… on an alert's evidence pack (Monitoring › Alerts, beside Explain): its device,
    network and rule, and the interface its alert piece's labels name (`triggers`'
    ``INTERFACE_LABELS``). An SDN detection's pack names a switch, never a device: none."""
    from modules.heal import triggers
    if not pack:
        return {}
    if not pack.get("device"):
        return entry("", "", rule="") | {"words": (
            "an SDN detection names a switch, which no runbook reads"
            if (pack.get("store") or "").startswith("sdn") else "the alert names no device")}
    labels = {}
    for s in pack.get("sections") or []:
        if s.get("name") == "alert":
            labels = ((s.get("pieces") or [{}])[0] or {}).get("labels") or {}
            break
    interface = next((str(labels[k]) for k in triggers.INTERFACE_LABELS if labels.get(k)), "")
    return entry(pack.get("network") or "", pack["device"], rule=pack.get("rule") or "",
                 interface=interface)


def from_incident(network: str, e: dict, triggers=None) -> dict:
    """Diagnose… on a can't-fix row (Needs attention, of any tier, Never's included), on its
    step log entry's device (*e*), from its incident's first trigger that names a target
    (*triggers*: the incident's own, `incidents.read`'s, each with its kind; the step log keeps
    only their words): an alert's rule and interface, or an adjacency's other end. No
    trigger read: the dialog on its first choice."""
    rule, interface, neighbour = "", "", ""
    for t in triggers or []:
        if not isinstance(t, dict):
            continue
        if t.get("kind") == "alert":
            rule, interface = t.get("rule") or "", t.get("interface") or ""
            break
        if t.get("kind") == "adjacency" and t.get("related"):
            neighbour = sorted(t["related"])[0]
            break
    return entry(network, e.get("device") or "", rule=rule, interface=interface,
                 neighbour=neighbour)


def nearest(model: dict, host: str) -> list:
    """*host*'s neighbours by the network model's links, by name: the devices a "can't reach"
    toward *host* can be run from, one hop from it, each once."""
    ids = model.get("names") or {}
    me = ids.get(host)
    by_id = {v: k for k, v in ids.items()}
    out = set()
    for link in (model.get("links") or {}).values():
        members = [m.get("dev") for m in link.get("members") or []]
        if me is not None and me in members:
            out |= {by_id[d] for d in members if d != me and d in by_id}
    return sorted(out)


def unreachable(network: str, host: str) -> dict:
    """Where Diagnose… for *host* unreachable opens: ``{"host", "args", "words"}``, the first
    of its neighbours by intent with "can't reach" chosen and *host*'s intended loopback its
    target (none chosen when intent gives it none), or *host*'s own dialog and why when no
    neighbour or no intent is known. Reads intent and the model only."""
    from modules.heal import diagnose as D
    from modules.heal import diagnose_reach as R
    from modules.neighbours import _all_lines
    try:
        model, intents = D._sources(network)
    except D.Refused as exc:
        return {"host": host, "args": {}, "words": str(exc)}
    near = nearest(model, host)
    if not near:
        return {"host": host, "args": {},
                "words": f"intent cables {host} to no other device to diagnose from"}
    _name, address = R._loopback(_all_lines(intents or {}).get(host) or {})
    return {"host": near[0], "args": {"runbook": "cant_reach", "to": address or ""},
            "words": f"from {near[0]}, the first of {host}'s {len(near)} neighbour(s) by intent"}


def job_card(network: str, host: str, job_id: str, back: str = "overview") -> dict:
    """The diagnosis's card by its job, as its job route and the device page's reopened card
    draw it (C537): running, the diagnosis drawn (artboard J), the job's failure, or that this
    server holds no such job (or one of another kind). ``level`` and ``words`` are the In
    progress chip's: a diagnosis that ran is done whatever it found (its chip says what), one
    refused or busy is partial."""
    from modules.nsot import capture_job
    c = {"op": "diagnose", "host": host, "list": network, "back": back, "job": job_id,
         "level": "", "words": ""}
    j = capture_job.get(job_id)
    if j is None or j.get("list") != network or j.get("kind") != "diagnosis":
        c.update(state="unknown")
    elif j["state"] == "running":
        c.update(state="running")
    elif j["state"] == "failed" or not isinstance(j.get("payload"), dict):
        c.update(state="failed", error=j.get("error") or "the job answered nothing")
    else:
        d = result(j["payload"])
        c.update(state="done", d=d, words=d["chip"],
                 level="warn" if d["chip"] == "not diagnosed" else "ok")
    return c
