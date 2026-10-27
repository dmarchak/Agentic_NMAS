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
- **Only a definite reference is resolved** (the operator's design for C1890, 2026-10-27): one
  after "the", "that", "this", "these" or "those", after "all", "both" or "every", or after
  the tab's own device as a possessive ("edge2's trunk" on edge2's tab). An indefinite or
  target-state phrase describes the state wanted, never a port: "a trunk", "an access port",
  "as a trunk", "to a routed port", "make gi0/1 a trunk" stay as words (the operations that
  would make them are refused by `intent_words.not_an_operation`, or by the model).

**Questions before any call** (the operator's order of 2026-10-27, item b): where code can tell
the words leave a choice only the person can make, Mercury asks, with no call and no cost, and
never chooses for the person (`questions`); each question carries its controls, and the
person's answer continues the same draft from the sentence as decided (`decide`, C1907):
- **Both ends** of a link (PHASE8_PLAN 16.10, never a half; C1908, `ends`): a both-ends
  quantifier, and its far end a device of the network (named, or read from the link): ONE
  draft of both devices, the sentence rewritten to name both ends. A far end Mercury does not
  manage, or one no read names, is asked about: this end only, or the device at the far end.
- **Alternatives**: "VLAN 40 or 41", "Gi0/1 or Gi0/2"; each said with what the committed intent
  holds of it (for a VLAN to add or remove, which of them can be), each possible one a button.
- **An OSPF network to add with no area**: the device's processes and areas said, each area a
  button, another typed in a field checked as an area.
- **A description to set with no text** ("set a description on Gi0/1"): its current one said,
  the text typed in a field (it reaches the model as a placeholder).
"""
import logging
import re

log = logging.getLogger(__name__)

#: Phrases, in the order they are read; each span is read once. A reference's noun decides
#: its kind; "all", "both" and "every" before it, or a plural noun, mean every match.
_ALL = (r"(?:(?P<all>all|both|every)\s+(?:of\s+)?)?"
        r"(?P<det>(?:the|that|this|these|those)\s+)?")
#: The tab's device as a possessive just before a reference ("edge2's trunk").
_OWNER = re.compile(r"(?<![\w.-])([\w][\w.-]*)['’]s\s+$")
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
#: A description's value is words, never a reference or a name to resolve: after "description
#: to" (=, :) or "describe <what> as", up to the clause's end ("uplink to edge1" in "set Gi0/2's
#: description to uplink to edge1, and shut Gi0/3" stays as written). "description of <name> to"
#: is not matched there, so the name before "to" is still read.
#: Interface types that are no port: a reference ("the port to edge2") never means one.
NOT_PORTS = ("vlan", "loopback", "tunnel", "bdi", "null", "virtualportgroup")
#: Where a value ends: ", and", ";", or the next clause's verb after "and" or a comma ("describe
#: Gi2 as to edge2, shut Gi3"); a comma before anything else is the value's ("spare port, desk 4").
_VALUE_END = (r"(?=,\s*and\b|;|(?:\s+and|,)\s+(?:shut|no\b|bring|add|remove|set|clear"
              r"|describe|enable|disable|rename|make)\b|$)")
_VALUE = re.compile(r"\b(?:description\s*(?:to|=|:)|describe\s+.+?\s+as)\s+"
                    r"(.+?)" + _VALUE_END, re.I)
#: The same value after "description of / on / for <what> to" (C1904, measured 2026-10-27:
#: "set the description of Gi0/1 to uplink to edge1", on a switch whose Gi0/2 faces edge1, was
#: sent as "... to GigabitEthernet0/2"). <what> is an interface as written, or a definite
#: reference ("the host port", "the port to desk7", "the VLAN 10 ports"), read to its end, so
#: the name in it is still read and only what follows "to" is the value.
_VALUE_OF = re.compile(
    r"\bdescriptions?\s+(?:of|on|for)\s+(?:[A-Za-z][A-Za-z-]*\s?\d+(?:[/.:]\d+)*"
    r"|(?:the|that|this|both|all)\s+(?:host[- ]?ports?|uplinks?|trunks?|(?:ports?|links?"
    r"|interfaces?)\s+(?:to|toward|towards|facing)\s+[\w][\w.-]*|vlan\s*\d{1,4}\s+ports?))"
    r"\s+(?:to|=|:)\s+(.+?)" + _VALUE_END, re.I)
#: Words a reference's noun is never confused with when read as shorthand.
_NOT_SHORTHAND = {"vlan", "vlans", "area", "process", "as", "asn", "ospf", "id"}


def _plural(m) -> bool:
    noun = (m.groupdict().get("noun") or "").lower().split()[-1]
    return bool(m.groupdict().get("all")) or (noun.endswith("s") and noun not in
                                               ("towards",))


def _word(x: str, text: str) -> bool:
    """*x* as a whole word of *text* (desk7 is not desk70, nor the desk7 of desk7-b)."""
    return bool(x) and re.search(rf"(?<![\w-]){re.escape(x)}(?![\w-])", text or "", re.I)


def definite(kind: str, m, before: str, device: str) -> bool:
    """Whether the reference *m* names ports rather than a state (C1890, the operator's design
    of 2026-10-27): "the", "that", "this", "these", "those", "all", "both" or "every" in it, or
    *device* as the possessive just *before* it ("edge2's trunk" on its tab). "toward X" names a
    neighbour, never a state, and is always read. Anything else ("a trunk", "an uplink", "make
    gi0/1 a trunk") stays as words."""
    if kind == "toward":
        return True
    got = m.groupdict()
    if got.get("all") or got.get("det"):
        return True
    owner = _OWNER.search(before)
    return bool(owner and device and owner.group(1).lower() == device.lower())


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


def neighbours_of(network: str, device: str, far: bool = False) -> dict:
    """``{"ports": {interface: [{"name", "role", "by"}]}, "said": [...]}``: each of *device*'s
    interfaces' managed neighbours, from the network model's shared subnets and the Topology
    read's physical links (the management path as "the management path"). An SDN switch is
    named by its key, ``of:<DPID>`` (S14), its links the controller's, each naming its sources.
    What could not be read is said, never left out. With *far*, each neighbour also carries
    ``port``, its own end of the link ("" when no read names it), for one draft of both ends
    (`ends`); off by default, so what other readers hold (and send, Explain's needs) is
    unchanged. *network* is its display name or its id, one network either way (C1903: the
    id read no observed link); a name no network answers to raises `listref.UnknownList`."""
    from modules import network_model as M
    from modules.nsot import ifnames, listref

    listref.network_id(network)
    ports, said = {}, []
    model, err = M.model_for(network)
    if model is None:
        return {"ports": {}, "said": [f"the network model could not be built: {err}"]}
    me = model["names"].get(device) or (device if device.startswith("of:") else None)
    nodes = model["nodes"]

    def add(port, peer, role, by, other=""):
        got = ports.setdefault(ifnames.canonical(port), [])
        known = next((p for p in got if p["name"] == peer), None)
        if known is None:
            got.append(dict({"name": peer, "role": role, "by": by},
                            **({"port": ifnames.canonical(other) if other else ""} if far
                               else {})))
        elif far and other and not known.get("port"):
            known["port"] = ifnames.canonical(other)

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
                f"intent: the subnet {link['subnet']}", others[0].get("interface") or "")
    obs = M.observed(network, model)
    if obs["state"] != "read":
        said.append(f"the Topology read could not be used ({obs['why']}), so neighbours are "
                    "intent's only")
    for cable in obs.get("cables", {}).values():
        ends = cable.get("ends") or []
        for i, end in enumerate(ends):
            if end.get("dev") != me or len(ends) != 2:
                continue
            far_end = ends[1 - i]
            if far_end["dev"] == M.MANAGER_ID or cable.get("mercury_attaches_here"):
                add(end.get("port") or "", "the management path", "manager", "observed")
            else:
                node = nodes.get(far_end["dev"]) or {}
                by = " and ".join(cable.get("sources") or ["LLDP"])
                add(end.get("port") or "", node.get("name") or far_end["dev"].replace("ext:", ""),
                    node.get("role", ""), f"observed ({by})", far_end.get("port") or "")
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
    # Quotes by the one quote reader (C1906: an apostrophe, "Gi0/1's", never opens one).
    from modules.ai.intent_words import quote_spans
    quoted = [(i, j + 1) for i, j in quote_spans(sentence)[0]] + [
        m.span(1) for rx in (_VALUE, _VALUE_OF) for m in rx.finditer(sentence)]
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
            if inside(a, b) or not definite(kind, m, sentence[:a], device):
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


# ── questions before any call (the operator's order of 2026-10-27, item b) ──────────────

#: A value a sentence gives, whose words are never a request: a description's text (as
#: `_VALUE` reads it, and after "desc"), and a VLAN's name after "named", "called" or "name".
_VALUES = (_VALUE, _VALUE_OF,
           re.compile(r"\bdesc\s*(?:to|=|:)?\s+(?:\S+\s+)?as\s+(.+?)" + _VALUE_END, re.I),
           re.compile(r"\b(?:named|called|name)\s+(\S+)", re.I))
#: A both-ends quantifier (PHASE8_PLAN 16.10).
BOTH_ENDS = re.compile(r"\b(?:both|each|either)\s+(?:of\s+the\s+)?(?:ends?|sides?)\b"
                       r"|\bat\s+(?:each|both)\s+ends?\b|\bon\s+both\b", re.I)
_IFACE_WORDS = r"[A-Za-z][A-Za-z-]*\s?\d+(?:[/.:]\d+)*"
#: Alternatives offered: VLANs ("VLAN 40 or 41", "vlans 40, 41 or 42") and interfaces.
_VLAN_OR = re.compile(r"\bvlans?\s+(\d{1,4}(?:\s*,\s*(?:vlan\s+)?\d{1,4})*\s*,?\s+or\s+"
                      r"(?:vlan\s+)?\d{1,4})\b", re.I)
_IFACE_OR = re.compile(rf"(?<![\w/])({_IFACE_WORDS})\s*,?\s+or\s+(?:on\s+)?({_IFACE_WORDS})"
                       r"(?![\w/])", re.I)
_ADDS = re.compile(r"\b(?:add|create|advertise|include)\b", re.I)
_REMOVES = re.compile(r"\b(?:remove|delete|drop|withdraw|move|take)\b", re.I)
#: A description to set, with no text: the whole sentence, nothing after the interface.
_NO_TEXT = (
    re.compile(rf"^\s*(?:please\s+)?(?:set|change|update|edit|give|add|put)\s+(?:a\s+|an\s+|"
               rf"the\s+|its\s+)?(?:new\s+)?desc(?:ription)?\s+(?:on|of|for|to)\s+"
               rf"(?P<x>{_IFACE_WORDS})\s*[.!?]?\s*$", re.I),
    re.compile(rf"^\s*(?:please\s+)?(?:give|set)\s+(?P<x>{_IFACE_WORDS})(?:['’]s)?\s+(?:a\s+|"
               rf"an\s+|the\s+)?(?:new\s+)?desc(?:ription)?\s*[.!?]?\s*$", re.I),
)


def blank_values(sentence: str) -> str:
    """*sentence* with each value it gives (`_VALUES`) blanked to spaces, same length, so a
    signal read from the rest never fires on a description's or a VLAN name's own words."""
    out = list(sentence or "")
    for rx in _VALUES:
        for m in rx.finditer(sentence or ""):
            a, b = m.span(1)
            out[a:b] = " " * (b - a)
    return "".join(out)


def _named_devices(sentence: str, device: str, devices: dict) -> list:
    """The devices of the network *sentence* names, other than *device*: each name as a whole
    word, a hyphen or slash allowed beside it ("the edge1-edge2 link")."""
    return [d for d in devices if d.lower() != (device or "").lower() and re.search(
        rf"(?<![\w.]){re.escape(d)}(?![\w.])", sentence or "", re.I)]


#: A both-ends phrase that names the link (PHASE8_PLAN 16.10; C1908): the quantifier, then the
#: link as said ("the link to edge2", "the trunk to edge2", "the edge1-edge2 link", "Gi0/3").
PAIR = re.compile(
    r"(?P<quant>\b(?:both|each|either)\s+(?:of\s+the\s+)?(?:ends?|sides?)\s+(?:of\s+)?)"
    r"(?P<what>(?:(?:the|this|that)\s+)?(?:[\w./]+-[\w./]+\s+)?(?:links?|trunks?|connections?"
    r"|uplinks?|ports?|interfaces?|" + _IFACE_WORDS + r")"
    r"(?:\s+(?:to|toward|towards|with)\s+(?P<to>[\w][\w.-]*))?)", re.I)
#: The words that leave the choice to Mercury, dropped once the person has chosen.
_WHICHEVER = re.compile(r",?\s*\b(?:whichever|either one|i forget which)\b[^,;.]*", re.I)
#: An OSPF area as the person may type it: a number, or dotted.
AREA = re.compile(r"^(?:\d{1,10}|\d{1,3}(?:\.\d{1,3}){3})$")


def _link(network: str, device: str, other: str, nb: dict) -> list:
    """``[(port, far port)]``: *device*'s links toward *other*, from *device*'s neighbours, and
    from *other*'s toward *device* when *device*'s reads name none or no far port (a link one
    end's LLDP sees)."""
    mine = sorted({(port, p.get("port") or "") for port, peers in (nb.get("ports") or {}).items()
                   for p in peers if p["name"].lower() == other.lower()})
    if mine and all(far for _p, far in mine):
        return mine
    theirs = neighbours_of(network, other, far=True)
    back = sorted({(p.get("port") or "", port) for port, peers in
                   (theirs.get("ports") or {}).items() for p in peers
                   if p["name"].lower() == device.lower() and p.get("port")})
    if not mine:
        return back
    found = dict(back)
    return [(port, far or found.get(port, "")) for port, far in mine]


def _local_ports(network: str, device: str, doc: dict, what: str, nb: dict) -> list:
    """The ports of *device* the both-ends phrase's link names ("the trunk", "Gi0/3", "the link
    to desk7"), as the resolver reads them; ``[]`` when it names no port of *device*."""
    from modules.ai.intent_words import touched
    got = resolve(network, device, doc, what, neighbours=nb)
    if not got["ok"]:
        return []
    held = {i["name"] for i in interfaces_of(doc)}
    return [n for n in touched(got["sentence"])["interfaces"] if n in held]


def ends(network: str, device: str, doc: dict, sentence: str, neighbours: dict = None,
         devices: dict = None) -> dict:
    """A request for both ends of a link from *device*'s tab (PHASE8_PLAN 16.10, never a half;
    C1908, the operator's ruling on board F7-Q): ``None`` with no both-ends quantifier
    (`BOTH_ENDS`) outside the values the sentence gives; ``{"kind": "pair", ...}`` when the
    phrase (`PAIR`) names exactly one link and its far end is a device of the network (its own
    inventory, `_devices`, never a pattern) with a known far port: the sentence rewritten to
    name both ends ("edge1 GigabitEthernet4 and edge2 GigabitEthernet4"), for ONE draft holding both
    devices' patches; else the question Mercury asks, with its controls (`decide`): draft
    this end only (a far end Mercury does not manage, or none found), the device at an
    unknown far end, or which of several links."""
    text = blank_values(sentence)
    q = BOTH_ENDS.search(text)
    if not q:
        return None
    devs = devices if devices is not None else _devices(network)
    nb = neighbours if neighbours is not None else neighbours_of(network, device, far=True)
    others = _named_devices(sentence, device, devs)
    m = PAIR.search(text)
    local = _local_ports(network, device, doc, sentence[m.start("what"):m.end("what")], nb) \
        if m else []
    links, unmanaged = [], []
    if others:
        for other in others:
            links += [(port, other, far) for port, far in _link(network, device, other, nb)
                      if not local or port in local]
    else:
        for port in local:
            for p in (nb.get("ports") or {}).get(port) or []:
                if p["name"] in devs and p["name"] != device:
                    far = p.get("port") or dict(_link(network, device, p["name"], nb)).get(port, "")
                    links.append((port, p["name"], far))
                else:
                    unmanaged.append((port, p["name"]))
        # The phrase names its far end, and that is no device of the network ("the link to
        # desk7"): the far end is outside Mercury, whatever the reads say.
        if m and m.group("to") and not links and local:
            unmanaged = unmanaged or [(local[0], m.group("to"))]
    said = nb.get("said") or []
    note = f" ({'; '.join(said)})" if said else ""
    if m and len(links) == 1 and links[0][2]:
        port, far, far_port = links[0]
        return {"kind": "pair", "phrase": m.group(0), "device": device, "port": port,
                "far": far, "far_port": far_port,
                "sentence": (sentence[:m.start()] + f"{device} {port} and {far} {far_port}"
                             + sentence[m.end():])}
    this_end = [{"label": f"Draft {device}'s end only", "value": "this-end"}] \
        if m and local else []
    base = {"kind": "two_ended", "phrase": q.group(0), "field": None, "links": [
        {"port": p, "device": o, "far": f} for p, o, f in links]}
    if len(links) > 1:
        return dict(base, choices=[{"label": f"{p} (to {o}" + (f" {f}" if f else "") + ")",
                                    "value": f"port:{p}:{o}"} for p, o, f in links],
                    question=(f"{device} has {len(links)} links that fit the words: which one? "
                              "Both ends of the one you choose are drafted together" + note))
    if links:                       # one link, its far port unknown
        p, o, _f = links[0]
        return dict(base, choices=this_end, question=(
            f"{device} {p} links to {o}, and no read names {o}'s port, so {o}'s end cannot be "
            f"drafted; draft {device}'s end only, or add {o}'s port from {o}'s tab" + note))
    if others:
        return dict(base, choices=this_end, question=(
            f"nothing on {device} links to {', '.join(others)} (neither intent's point-to-point "
            f"subnets nor the Topology read show one, from either end), so the far end cannot be "
            f"drafted here; draft {device}'s end only, or name {device}'s interface" + note))
    if unmanaged:
        port, peer = unmanaged[0]
        return dict(base, choices=this_end, question=(
            f"{peer} is not a device Mercury manages, so only {device}'s end, {port}, can be "
            "drafted" + note))
    pick = [{"label": d, "value": f"far:{d}"} for d in sorted(devs) if d != device]
    if local:
        return dict(base, choices=this_end + pick, question=(
            f"Mercury does not know what {' or '.join(local)} links to (neither intent's "
            "point-to-point subnets nor the Topology read show a neighbour): name the device at "
            f"the far end, or draft {device}'s end only" + note))
    return dict(base, choices=[], question=(
        f"the words ask for both ends, and name no interface of {device} and no device at the "
        f"far end; name {device}'s interface (and the far device) and draft again" + note))


def _iface_state(i: dict) -> str:
    bits = [f"\"{i['description']}\"" if i["description"] else "no description",
            "shut" if i["shutdown"] else "up"]
    if i["mode"] == "access" and i["access_vlan"]:
        bits.append(f"access VLAN {i['access_vlan']}")
    elif i["mode"]:
        bits.append(i["mode"])
    return ", ".join(bits)


def alternatives(device: str, doc: dict, sentence: str) -> dict:
    """Alternatives the person offers, which Mercury never chooses between: ``{"kind":
    "alternatives", "phrase", "question", "choices", "field"}`` or ``None``. VLANs ("VLAN 40 or
    41, whichever is free"): each said with whether the committed intent holds it, and, for a
    VLAN to add (or remove), which of them can be, each that can a button (when exactly one
    can, the question says so, and it is the one button: the choice is still the person's).
    Interfaces ("Gi0/1 or Gi0/2, whichever is unused"): each a button with its committed
    description and state, and Both; what "unused" means is the person's, so nothing is
    judged."""
    text = blank_values(sentence)
    m = _VLAN_OR.search(text)
    if m:
        numbers = list(dict.fromkeys(re.findall(r"\d+", m.group(1))))
        held = {str(v.get("id")): str(v.get("name") or "") for v in (doc or {}).get("vlans")
                or [] if isinstance(v, dict)}
        have = [f"VLAN {n}" + (f" (named {held[n]})" if held[n] else "") for n in numbers
                if n in held]
        lack = [f"VLAN {n}" for n in numbers if n not in held]
        said = f"{device}'s committed intent holds " + (
            ("neither" if len(numbers) == 2 else "none of them") if not have else
            ("both" if len(numbers) == 2 else "all of them") + f" ({', '.join(have)})"
            if not lack else f"{' and '.join(have)} and not {' or '.join(lack)}")
        verb = ("add" if _ADDS.search(text) and not _REMOVES.search(text) else
                "remove" if _REMOVES.search(text) and not _ADDS.search(text) else "")
        can, able = "", numbers
        if verb:
            able = [n for n in numbers if (n not in held) == (verb == "add")]
            done = "added" if verb == "add" else "removed"
            can = (f"; so only VLAN {able[0]} can be {done}" if len(able) == 1 else
                   f"; so none of them can be {done}" if not able else
                   f"; so {'either' if len(able) == 2 else 'any'} can be {done}")
        return {"kind": "alternatives", "phrase": m.group(0).strip(), "field": None,
                "span": list(m.span()), "choices": [{"label": f"VLAN {n}", "value": n}
                                                    for n in able],
                "question": (f"you offer VLAN {' or '.join(numbers)}, and Mercury does not "
                             f"choose for you: {said}{can}. Which one?")}
    m = _IFACE_OR.search(text)
    if not m:
        return None
    ifaces = interfaces_of(doc)
    names = [i["name"] for i in ifaces]
    tokens = [m.group(1), m.group(2)]
    if not all(_interface_shaped(t, names) for t in tokens):
        return None
    by_name = {i["name"]: i for i in ifaces}
    said, choices = [], []
    for t in tokens:
        full = _shorthand(t, names)
        said.append(f"{full} ({_iface_state(by_name[full])})" if full
                    else f"{t} ({device} holds no such interface)")
        if full:
            choices.append({"label": f"{full} ({_iface_state(by_name[full])})", "value": full})
    if len(choices) == 2:
        choices.append({"label": "Both", "value": "*"})
    return {"kind": "alternatives", "phrase": m.group(0).strip(), "field": None,
            "span": list(m.span()), "choices": choices, "question": (
                f"you offer {' or '.join(tokens)}, and Mercury does not choose for you: "
                f"{'; '.join(said)}. Which one?")}


def _areas(doc: dict) -> list:
    """``[(process, [areas])]`` of *doc*'s committed OSPF, its areas in order."""
    from modules.nsot import intent_patch
    routing = (doc or {}).get("routing") if isinstance((doc or {}).get("routing"), dict) \
        else {}
    out = []
    for proc in routing.get("ospf") or []:
        if isinstance(proc, dict):
            out.append((str(proc.get("process")), sorted(
                {str(a) for _k, a, _w in intent_patch._statements(proc)},
                key=lambda a: (len(a), a))))
    return out


def no_area(device: str, doc: dict, sentence: str) -> dict:
    """An OSPF network to add with no area given: ``{"kind": "no_area", "phrase", "question",
    "choices", "field"}`` or ``None``. The operation needs an area, and the words give none, so
    any area would be a guess: the device's processes and their areas are said, each area a
    button, and another typed in a field checked as a number or a dotted area. Read only from
    a sentence that adds (and removes or moves nothing), names OSPF and a prefix, and has no
    "area"."""
    from modules.ai.intent_words import _PREFIX

    text = blank_values(sentence)
    if not (_ADDS.search(text) and not _REMOVES.search(text) and re.search(r"\bospf\b", text,
                                                                           re.I)
            and not re.search(r"\barea\b", text, re.I)):
        return None
    prefix = _PREFIX.search(text)
    if not prefix:
        return None
    procs = _areas(doc)
    shown = [f"process {p}" + (f" (areas {', '.join(a)})" if a else " (no network yet)")
             for p, a in procs]
    held = (f"{device}'s committed OSPF holds {'; '.join(shown)}" if procs else
            f"{device}'s committed intent holds no OSPF process")
    areas = list(dict.fromkeys(a for _p, got in procs for a in got))
    return {"kind": "no_area", "phrase": prefix.group(0),
            "choices": [{"label": f"Area {a}", "value": a} for a in areas],
            "field": {"kind": "area", "label": "Another area", "placeholder": "e.g. 10",
                      "pattern": r"\d{1,10}|\d{1,3}(\.\d{1,3}){3}"},
            "question": (f"which area should {prefix.group(0)} join? The words give none, and "
                         f"Mercury does not guess one: {held}")}


def no_value(device: str, doc: dict, sentence: str) -> dict:
    """A description to set with no text (the whole sentence "set a description on Gi0/1",
    nothing after the interface): ``{"kind": "no_value", "phrase", "question", "choices",
    "field"}`` or ``None``. The interface's current description is said, and the text is typed
    in a field: it reaches the model as a placeholder, never as words to follow."""
    for rx in _NO_TEXT:
        m = rx.match(sentence or "")
        if m:
            names = [i["name"] for i in interfaces_of(doc)]
            full = _shorthand(m.group("x"), names)
            if not full:
                return None             # the device lacks it: `resolve` says so
            now = next(i["description"] for i in interfaces_of(doc) if i["name"] == full)
            return {"kind": "no_value", "phrase": m.group("x"), "interface": full,
                    "choices": [], "field": {
                        "kind": "text", "label": "The description",
                        "placeholder": "the description, exactly as it should read",
                        "pattern": ""},
                    "question": (f"what should {full}'s description say? The words give no "
                                 "text" + (f"; it reads \"{now}\" now" if now
                                           else "; it has none now"))}
    return None


def questions(network: str, device: str, doc: dict, sentence: str,
              neighbours: dict = None, devices: dict = None) -> dict:
    """The first of `ends` (both ends: one two-device draft, ``kind`` "pair", or its
    question), `alternatives`, `no_area` and `no_value`, or ``None``."""
    return (ends(network, device, doc, sentence, neighbours, devices)
            or alternatives(device, doc, sentence) or no_area(device, doc, sentence)
            or no_value(device, doc, sentence))


def quoted_value(text: str) -> tuple:
    """``(the text in quotes, "")`` for a typed answer to go as a value (so `hold_quotes` makes it
    a placeholder): straight quotes, or curly ones when it holds a straight double quote;
    ``("", why)`` when it holds both."""
    if '"' not in text:
        return f'"{text}"', ""
    if "“" not in text and "”" not in text:
        return f"“{text}”", ""
    return "", ("the text holds both a straight and a curly double quote, so it cannot be "
                "quoted as one value; type it without one of them")


def decide(network: str, device: str, doc: dict, sentence: str, kind: str, value: str,
           neighbours: dict = None, devices: dict = None) -> dict:
    """The person's answer to Mercury's own question (C1907): ``{"ok", "sentence", "error"}``,
    *sentence* rewritten as decided, so the same draft continues with no retyping. The
    question is asked again of the same words (`questions`); an answer it did not offer (a
    button's value, or a field's text that fails its check) is refused, naming both."""
    q = questions(network, device, doc, sentence, neighbours, devices)
    if not q or q["kind"] != kind:
        return {"ok": False, "sentence": "", "error": (
            f"Mercury no longer asks {kind!r} of these words (it asks "
            f"{(q or {}).get('kind') or 'nothing'}); draft again")}
    value = (value or "").strip()
    offered = [str(c["value"]) for c in q.get("choices") or []]
    field = q.get("field") or {}

    def refused(why):
        return {"ok": False, "sentence": "", "error": why}

    if kind == "two_ended":
        if value not in offered:
            return refused(f"{value!r} is not an answer Mercury offered ({', '.join(offered) or 'none'})")
        text = blank_values(sentence)
        m = PAIR.search(text)
        if value == "this-end":
            local = _local_ports(network, device, doc, sentence[m.start("what"):m.end("what")],
                                 neighbours if neighbours is not None
                                 else neighbours_of(network, device, far=True))
            if len(local) == 1:
                return {"ok": True, "error": "", "sentence": (
                    sentence[:m.start()] + local[0] + sentence[m.end():])}
            return {"ok": True, "error": "", "sentence": (
                sentence[:m.start("quant")] + sentence[m.end("quant"):])}
        if value.startswith("far:"):
            far = value[4:]
            if m.group("to"):
                return {"ok": True, "error": "", "sentence": (
                    sentence[:m.start("to")] + far + sentence[m.end("to"):])}
            return {"ok": True, "error": "", "sentence": (
                sentence[:m.end("what")] + f" to {far}" + sentence[m.end("what"):])}
        port, other = value[len("port:"):].rsplit(":", 1)
        return {"ok": True, "error": "", "sentence": (
            sentence[:m.start("what")] + f"{port} to {other}" + sentence[m.end("what"):])}
    if kind == "alternatives":
        if value not in offered:
            return refused(f"{value!r} is not an answer Mercury offered ({', '.join(offered) or 'none'})")
        a, b = q["span"]
        if value.isdigit():
            chosen = f"VLAN {value}"
        elif value == "*":
            pair = [c["value"] for c in q["choices"] if c["value"] != "*"]
            chosen = " and ".join(pair)
        else:
            chosen = value
        out = sentence[:a] + chosen + sentence[b:]
        return {"ok": True, "error": "", "sentence": _WHICHEVER.sub("", out).strip()}
    if kind == "no_area":
        if value not in offered and not AREA.match(value):
            return refused(f"{value!r} is no OSPF area: an area is a number (0 to 4294967295) "
                           "or dotted, as 0.0.0.10")
        if value.isdigit() and int(value) > 4294967295:
            return refused(f"{value} is past the largest OSPF area, 4294967295")
        return {"ok": True, "error": "", "sentence": (
            sentence.rstrip().rstrip(".!?") + f" area {value}")}
    if kind == "no_value":
        if not value:
            return refused("the description is empty: to clear it, say so (\"clear the "
                           "description on " + q["interface"] + "\")")
        if len(value) > 240 or any(not (c.isprintable() and ord(c) < 127) for c in value):
            return refused("a description is printable ASCII, at most 240 characters; "
                           f"this one is {len(value)}" + ("" if value.isascii() else
                                                          ", and holds other characters"))
        quoted, why = quoted_value(value)
        if why:
            return refused(why)
        return {"ok": True, "error": "", "sentence": (
            f"set the description of {q['interface']} to {quoted}")}
    return refused(f"{kind!r} is no question Mercury asks")
