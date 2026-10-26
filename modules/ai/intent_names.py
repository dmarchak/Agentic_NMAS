"""How people name a device's interfaces, resolved before any model is asked (feature 7's
part 1, PHASE8_PLAN 15.16; the operator, 2026-10-26). Deterministic and read-only: the model
receives the resolved names only, and the resolved interfaces are the request's scope.

**Shorthand.** A token is first canonicalised by the shared table (`ifnames.canonical`:
Gi0/1, GigabitEthernet 0/1, Te, Fa, Po, Lo, Vl, Tu), and otherwise matched as the device's own
CLI matches it: an unambiguous prefix of one of the device's interface names with the same
numbers ("G1/0", "Gig1/0", "gi1/0" to GigabitEthernet1/0). Only a name the device holds is
resolved; the shared table is not widened (a bare "G" there would touch every user of it).

**References**, from committed intent and the network model's neighbours (`neighbours_of`:
the model's shared subnets, and the Topology read's physical links, the management path among
them; NetBox's cables are made from those same LLDP links, so they are not read again):
- "host port(s)": an access port, enabled in intent, with no managed neighbour. Structural,
  never from a description; a shut access port is not one unless named directly (the
  operator's ruling of 2026-10-26: Mercury holds no host, C1772).
- "the port to X", "toward X": X a device of the network, the ports whose neighbour is X;
  otherwise the ports whose committed description names X as a word ("desk7" never matches
  "desk70"), said as the description.
- "uplink(s)", "the uplink to edge1": ports toward a router or the management path.
- "trunk(s)": trunk ports in intent. "the VLAN 10 ports": access ports in VLAN 10.
- A plural ("host ports", "all trunks", "both uplinks") is every match. One match is used.
  Several, with a singular reference, is a question before any call: each candidate with its
  neighbour or description, and "Both" or "All N". No match, or a name the device lacks (and
  nothing else named that it holds), is said with the device's real interfaces.
"""
import logging
import re

log = logging.getLogger(__name__)

#: Phrases, in the order they are read; each span is read once. A reference's noun decides
#: its kind; "all", "both" and "every" before it, or a plural noun, mean every match.
_ALL = r"(?:(?P<all>all|both|every)\s+(?:of\s+)?)?(?:the\s+)?"
REFERENCES = (
    ("port_to", re.compile(r"\b" + _ALL + r"(?P<noun>ports?|interfaces?|links?)\s+(?:to|toward|towards"
                           r"|facing)\s+(?P<x>[\w][\w.-]*)", re.I)),
    ("toward", re.compile(r"\b(?P<noun>toward|towards)\s+(?P<x>[\w][\w.-]*)", re.I)),
    ("uplink", re.compile(r"\b" + _ALL + r"(?P<noun>uplinks?)(?:\s+(?:to|toward)\s+"
                          r"(?P<x>[\w][\w.-]*))?", re.I)),
    ("host", re.compile(r"\b" + _ALL + r"(?P<noun>host[- ]?(?:ports?|interfaces?))", re.I)),
    ("trunk", re.compile(r"\b" + _ALL + r"(?P<noun>trunk(?:s|\s+ports?)?)\b", re.I)),
    ("vlan_ports", re.compile(r"\b" + _ALL + r"vlan\s*(?P<vlan>\d{1,4})\s+(?P<noun>ports?)",
                              re.I)),
)
_TOKEN = re.compile(r"\b([A-Za-z][A-Za-z-]*)\s?(\d+(?:[/.:]\d+)*)\b")
_SPLIT = re.compile(r"^([A-Za-z][A-Za-z-]*)\s?(\d+(?:[/.:]\d+)*)$")
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"|“[^”]*”")
#: A description's value is words, never a reference or a name to resolve: after "description
#: to" (=, :) or "describe <what> as", up to the clause's end ("uplink to edge1" in "set Gi0/2's
#: description to uplink to edge1, and shut Gi0/3" stays as written). "description of <name> to"
#: is not matched there, so the name before "to" is still read.
#: Interface types that are no port: a reference ("the port to edge2") never means one.
NOT_PORTS = ("vlan", "loopback", "tunnel", "bdi", "null", "virtualportgroup")
_VALUE = re.compile(r"\b(?:description\s*(?:to|=|:)|describe\s+.+?\s+as)\s+"
                    r"(.+?)(?=,\s*and\b|;|\s+and\s+(?:shut|no\b|bring|add|remove|set|clear"
                    r"|describe|enable|disable)\b|$)", re.I)
#: Words a reference's noun is never confused with when read as shorthand.
_NOT_SHORTHAND = {"vlan", "vlans", "area", "process", "as", "asn", "ospf", "id"}


def _plural(m) -> bool:
    noun = (m.groupdict().get("noun") or "").lower().split()[-1]
    return bool(m.groupdict().get("all")) or (noun.endswith("s") and noun not in
                                               ("towards",))


def _word(x: str, text: str) -> bool:
    """*x* as a whole word of *text* (desk7 is not desk70, nor the desk7 of desk7-b)."""
    return bool(x) and re.search(rf"(?<![\w-]){re.escape(x)}(?![\w-])", text or "", re.I)


def interfaces_of(doc: dict) -> list:
    """The device's interfaces from its committed intent: name, description, shut,
    switchport mode and access VLAN."""
    out = []
    for i in (doc or {}).get("interfaces") or []:
        if not i.get("name"):
            continue
        out.append({"name": i["name"], "description": str(i.get("description") or ""),
                    "shutdown": bool(i.get("shutdown")),
                    "mode": str(i.get("switchport_mode") or ""),
                    "access_vlan": str(i.get("switchport_access_vlan") or "")})
    return out


def neighbours_of(network: str, device: str) -> dict:
    """``{"ports": {interface: [{"name", "role", "by"}]}, "said": [...]}``: each of *device*'s
    interfaces' managed neighbours, from the network model's shared subnets and the Topology
    read's physical links (the management path as "the management path"). What could not be
    read is said, never left out."""
    from modules import network_model as M
    from modules.nsot import ifnames

    ports, said = {}, []
    model, err = M.model_for(network)
    if model is None:
        return {"ports": {}, "said": [f"the network model could not be built: {err}"]}
    me = model["names"].get(device)
    nodes = model["nodes"]

    def add(port, peer, role, by):
        got = ports.setdefault(ifnames.canonical(port), [])
        if not any(p["name"] == peer for p in got):
            got.append({"name": peer, "role": role, "by": by})

    for link in model["links"].values():
        members = link.get("members") or []
        mine = [m for m in members if m["dev"] == me]
        for m in mine:
            others = [o for o in members if o["dev"] != me]
            if len(others) != 1:
                # A shared segment (a management LAN every device sits on) names no one
                # neighbour: it is a segment, never "toward edge1" or an uplink.
                add(m["interface"], f"the {link['subnet']} segment ({len(members)} devices)",
                    "segment", f"intent: the subnet {link['subnet']}")
                continue
            node = nodes.get(others[0]["dev"]) or {}
            add(m["interface"], node.get("name") or others[0]["dev"], node.get("role", ""),
                f"intent: the subnet {link['subnet']}")
    obs = M.observed(network, model)
    if obs["state"] != "read":
        said.append(f"the Topology read could not be used ({obs['why']}), so neighbours are "
                    "intent's only")
    for cable in obs.get("cables", {}).values():
        ends = cable.get("ends") or []
        for i, end in enumerate(ends):
            if end.get("dev") != me or len(ends) != 2:
                continue
            far = ends[1 - i]
            if far["dev"] == M.MANAGER_ID or cable.get("mercury_attaches_here"):
                add(end.get("port") or "", "the management path", "manager", "observed")
            else:
                node = nodes.get(far["dev"]) or {}
                add(end.get("port") or "", node.get("name") or far["dev"].replace("ext:", ""),
                    node.get("role", ""), "observed (LLDP)")
    return {"ports": ports, "said": said}


def _parts(name: str) -> tuple:
    """``(type word, numbers)`` of an interface name, or ``("", "")``."""
    m = _SPLIT.match((name or "").strip())
    return (m.group(1), m.group(2)) if m else ("", "")


def _shorthand(token: str, names: list) -> str:
    """*token* as the device names it, or "" when the device holds no such interface: the
    shared table's canonical form, else an unambiguous prefix of one of the device's own type
    words with the same numbers (as the device's CLI reads "g1/0")."""
    from modules.nsot import ifnames
    by_lower = {n.lower(): n for n in names}
    full = ifnames.canonical(token)
    if full.lower() in by_lower:
        return by_lower[full.lower()]
    word, numbers = _parts(token)
    if not word:
        return ""
    hits = [n for n in names if _parts(n)[1] == numbers
            and _parts(n)[0].lower().startswith(word.lower())]
    return hits[0] if len(hits) == 1 else ""


def _interface_shaped(token: str, names: list) -> bool:
    """A token that reads as an interface: the shared table knows its type, or its word is a
    prefix of a type the device holds (G, Gig) with slot numbers (x/y)."""
    from modules.nsot import ifnames
    word, numbers = _parts(token)
    if not word or word.lower() in _NOT_SHORTHAND:
        return False
    canonical = ifnames.canonical(token).lower()
    if any(canonical.startswith(full.lower()) for full, _a in ifnames.INTERFACE_PREFIXES):
        return True
    return "/" in numbers and any(_parts(n)[0].lower().startswith(word.lower()) for n in names)


def resolve(network: str, device: str, doc: dict, sentence: str, picks: dict = None,
            neighbours: dict = None, endpoints: list = None, now: float = None) -> dict:
    """*sentence* on *device*'s Intent tab, its names resolved against *doc* (the committed
    intent) and the device's neighbours: ``{"ok", "sentence", "resolutions", "ask",
    "unknown", "said"}``. *sentence* comes back with each reference and shorthand replaced by
    the device's own names, which is all the model is given. *picks* is the person's answer to
    an earlier question (``{phrase: [names]}``, or ``"*"`` for every candidate), so a choice
    continues the same draft. *neighbours* is `neighbours_of`'s answer, read when absent;
    *endpoints* the endpoint layer's, each said by its age at *now* (`endpoints.seen`)."""
    picks = {k.lower(): v for k, v in (picks or {}).items()}
    ifaces = interfaces_of(doc)
    names = [i["name"] for i in ifaces]
    by_name = {i["name"]: i for i in ifaces}
    nb = neighbours if neighbours is not None else neighbours_of(network, device)
    ports = nb.get("ports") or {}
    devices = _devices(network)
    # The endpoint layer's observations (C1772), read from its stored value when not given; a
    # drift between an observation and a description is said beside the resolutions.
    from modules import endpoints as E
    observed = endpoints if endpoints is not None else E.stored(network).get("endpoints") or []
    hours = E.stale_after_hours(network)
    observed = [dict(e, seen=E.seen(e, now=now, stale_hours=hours)) for e in observed]
    nb = dict(nb, said=list(nb.get("said") or []))
    notes = nb["said"]                  # the same list: every answer below carries the notes
    quoted = [m.span() for m in _QUOTED.finditer(sentence)] + [
        m.span(1) for m in _VALUE.finditer(sentence)]
    spans, resolutions = [], []

    def inside(a, b):
        return any(x <= a and b <= y for x, y in quoted + [s[:2] for s in spans])

    def label(name):
        i, peers = by_name.get(name) or {}, ports.get(name) or []
        if peers:
            return f"{name} ({', '.join(p['name'] for p in peers)})"
        return f"{name} ({i.get('description')})" if i.get("description") else name

    for kind, rx in REFERENCES:
        for m in rx.finditer(sentence):
            a, b = m.span()
            if inside(a, b):
                continue
            phrase = m.group(0).strip()
            got = _matches(kind, m, ifaces, ports, devices, device, observed, notes)
            chosen = picks.get(phrase.lower())
            if chosen:
                pool = {n for n, _b in got} if got else set(names)
                use = sorted(pool) if chosen == "*" else [n for n in chosen if n in pool]
                if use:
                    got = [(n, dict(got).get(n, "chosen")) for n in use]
            if not got:
                return _unknown(phrase, ifaces, nb, resolutions,
                                f"nothing on {device} is {_what(kind, m)}")
            if len(got) > 1 and not _plural(m) and not chosen:
                return {"ok": False, "sentence": sentence, "resolutions": resolutions,
                        "unknown": None, "said": nb.get("said") or [],
                        "ask": {"phrase": phrase, "question": (
                            f"{device} has {len(got)} {_what(kind, m, plural=True)}; which "
                            "one?"), "candidates": [{"name": n, "label": label(n)}
                                                     for n, _b in got],
                            "all": "Both" if len(got) == 2 else f"All {len(got)}"}}
            spans.append((a, b, " and ".join(n for n, _b in got)))
            resolutions.append({"said": phrase, "to": [n for n, _b in got],
                                "by": sorted({b_ for _n, b_ in got})})
    # Shorthand, outside every reference and quote.
    missing = []
    for m in _TOKEN.finditer(sentence):
        a, b = m.span()
        if inside(a, b) or any(sa <= a < sb for sa, sb, _r in spans):
            continue
        token = m.group(0)
        if sentence[max(0, a - 5):a].lower().strip().endswith("vlan"):
            continue
        if not _interface_shaped(token, names):
            continue
        chosen = picks.get(token.lower())
        full = chosen[0] if chosen and chosen != "*" and chosen[0] in by_name else \
            _shorthand(token, names)
        if not full:
            missing.append(token)
            continue
        if full != token:
            resolutions.append({"said": token, "to": [full], "by": ["shorthand"]})
        spans.append((a, b, full))
    if missing and not spans and not re.search(r"\bvlans?\s+\d", sentence, re.I):
        return _unknown(missing[0], ifaces, nb, resolutions,
                        f"{device} has no interface {missing[0]}")
    out = sentence
    for a, b, text in sorted(spans, key=lambda s: s[0], reverse=True):
        out = out[:a] + text + out[b:]
    return {"ok": True, "sentence": out, "resolutions": resolutions, "ask": None,
            "unknown": None, "said": nb.get("said") or []}


def _devices(network: str) -> dict:
    from modules.ai.nl_query import _inventory
    try:
        return {d["hostname"]: d.get("role") or "" for d in _inventory(network)
                if d.get("hostname")}
    except Exception as exc:                            # noqa: BLE001 (said by the caller)
        log.warning("intent_names: %s's inventory could not be read: %s", network, exc)
        return {}


def _what(kind: str, m, plural: bool = False) -> str:
    s = "s" if plural else ""
    got = m.groupdict() if m else {}
    x, vlan = got.get("x") or "", got.get("vlan") or ""
    return {"host": f"host port{s} (an access port, enabled, with no managed neighbour)",
            "trunk": f"trunk port{s}",
            "uplink": f"uplink{s}" + (f" to {x}" if x else " (toward a router or the "
                                                         "management path)"),
            "vlan_ports": f"VLAN {vlan} port{s} (access ports in it)",
            }.get(kind, f"port{s} to {x}")


def _matches(kind: str, m, ifaces: list, ports: dict, devices: dict, device: str = "",
             endpoints: list = None, notes: list = None) -> list:
    """``[(name, by)]``: the ports *m* refers to (never an SVI, loopback or tunnel), each
    with how it was found."""
    x = (m.groupdict().get("x") or "")
    ifaces = [i for i in ifaces if _parts(i["name"])[0].lower() not in NOT_PORTS]
    if kind == "host":
        return [(i["name"], "by role") for i in ifaces
                if i["mode"] == "access" and not i["shutdown"] and not ports.get(i["name"])]
    if kind == "trunk":
        return [(i["name"], "by intent (trunk)") for i in ifaces if i["mode"] == "trunk"]
    if kind == "vlan_ports":
        v = m.group("vlan")
        return [(i["name"], f"by intent (access VLAN {v})") for i in ifaces
                if i["mode"] == "access" and i["access_vlan"] == v]
    if kind == "uplink":
        got = []
        for i in ifaces:
            for p in ports.get(i["name"]) or []:
                if (x and p["name"].lower() == x.lower()) or (
                        not x and (p["role"] == "router" or p["role"] == "manager")):
                    got.append((i["name"], f"toward {p['name']} ({p['by']})"))
                    break
        return got
    # "the port to X" / "toward X"
    if x.lower() in {d.lower() for d in devices} or any(
            p["name"].lower() == x.lower() for ps in ports.values() for p in ps):
        return [(i["name"], f"toward {x} ({p['by']})") for i in ifaces
                for p in (ports.get(i["name"]) or []) if p["name"].lower() == x.lower()]
    described = [(i["name"], f"by description {i['description']!r}") for i in ifaces
                 if _word(x, i["description"])]
    # An endpoint: observation first (the endpoint layer, C1772), a description second, and a
    # disagreement between them said as drift (the operator's order of 2026-10-26). A stale
    # observation (past the network's endpoint_stale_after_hours) is a history: a description
    # naming X is used before it, and the observation said beside.
    from modules import endpoints as E
    from modules.nsot import ifnames
    seen = [e for e in E.find(endpoints or [], x) if e.get("device")]
    here = [e for e in seen if e["device"] == device]
    if here:
        found = sorted({ifnames.canonical(e["interface"]) for e in here})
        names = {i["name"] for i in ifaces}
        said = (here[0].get("seen") or {}).get("said") or (
            f"seen there {here[0].get('last_seen') or 'in the last read'}")
        observed = [(n, f"observed: {x}, {said}") for n in found if n in names]
        differs = bool(observed and described
                       and {n for n, _b in described} != {n for n, _b in observed})
        if observed and described and all((e.get("seen") or {}).get("stale") for e in here):
            notes.append(f"{x}'s observation is stale ({said}); the description of "
                         f"{', '.join(n for n, _b in described)} is used"
                         + ("; they disagree: drift" if differs else ""))
            return described
        if differs:
            notes.append(f"drift: {x} was observed on {', '.join(n for n, _b in observed)}, "
                         f"but the description of {', '.join(n for n, _b in described)} names "
                         f"{x}; the observation is used")
        if observed:
            return observed
    elif seen:
        where = ", ".join(f"{e['device']} {e['interface']}" for e in seen)
        notes.append(f"{x} was observed on {where}, not on {device}"
                     + ("; the description is used, and disagrees: drift" if described else ""))
    return described


def _unknown(said: str, ifaces: list, nb: dict, resolutions: list,
             why: str) -> dict:
    return {"ok": False, "sentence": "", "resolutions": resolutions, "ask": None,
            "said": nb.get("said") or [],
            "unknown": {"said": said, "why": why,
                        "interfaces": [{"name": i["name"], "label": (
                            f"{i['name']} ({i['description']})" if i["description"]
                            else i["name"])} for i in ifaces]}}
