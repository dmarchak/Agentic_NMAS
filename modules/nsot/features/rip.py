"""The RIP packs: RIPv2 (`routing.rip`, `router rip`), RIPng (`routing.ripng[]`,
`ipv6 router rip <name>`), and an interface's RIPng settings
(`interfaces[].ripng_interface[]`). docs/FEATURE_PACKS.md.
"""

import ipaddress

from modules.nsot.features import (DictOf, ListOf, body_lines, compact, complete, is_int,
                                   reproduces, token, _scalar)
from modules.nsot.features.ospf import (REDISTRIBUTE, _bad, _is_set, _merge,
                                        parse_redistribute, passive_problems,
                                        redistribute_problems)

# ── the schema ───────────────────────────────────────────────────────────────

TIMERS = {"update": "", "invalid": "", "holddown": "", "flush": ""}
DEFAULT_INFORMATION = {"originate": False, "route_map": ""}
#: `routing.rip`'s structured fields; its unmodelled lines stay in ``settings`` and
#: ``networks``. ``classful_networks`` are RIP's own network statements (``192.0.2.0``): RIP
#: takes a classful network, so a subnet of one is refused, naming the class it falls in.
RIP = {"version": "", "timers": DictOf(TIMERS), "redistribute": ListOf(REDISTRIBUTE),
       "default_metric": "", "passive_default": False, "passive_interfaces": ListOf(),
       "no_passive_interfaces": ListOf(), "classful_networks": ListOf(),
       "default_information": DictOf(DEFAULT_INFORMATION), "distance": "",
       "auto_summary": None}
RAW_RIP = {"settings": ListOf(), "networks": ListOf(), "neighbors": ListOf()}
#: `routing.ripng[]`'s; its unmodelled lines stay in ``raw``.
RIPNG = {"redistribute": ListOf(REDISTRIBUTE)}
RAW_RIPNG = {"raw": ListOf()}
#: One RIPng process an interface takes part in (`ipv6 rip <name> enable`, and
#: `ipv6 rip <name> default-information originate|only`).
RIPNG_INTERFACE = {"name": "", "enable": False, "default_information": ""}

PROTOCOLS_RIP = {"connected": False, "static": False, "ospf": True, "bgp": True,
                 "eigrp": True}
PROTOCOLS_RIPNG = {"connected": False, "static": False, "ospf": True, "bgp": True}


def complete_rip(rip: dict) -> dict:
    return complete(rip, {**RIP, **RAW_RIP})


def complete_ripng(proc: dict) -> dict:
    return complete(proc, {**RIPNG, **RAW_RIPNG})


def classful(address: str):
    """The classful network *address* falls in (A: /8, B: /16, C: /24), or None."""
    try:
        addr = ipaddress.IPv4Address(address)
    except ValueError:
        return None
    first = int(str(addr).split(".")[0])
    length = 8 if first < 128 else 16 if first < 192 else 24
    return ipaddress.IPv4Network(f"{addr}/{length}", strict=False)


# ── parsing ──────────────────────────────────────────────────────────────────

def _fact(line: str):
    w = line.split()
    if not w:
        return None
    if w[0] == "version" and len(w) == 2:
        return {"version": w[1]}
    if w[:2] == ["timers", "basic"] and len(w) == 6:
        return {"timers": dict(zip(("update", "invalid", "holddown", "flush"), w[2:]))}
    if w[0] == "redistribute":
        r = parse_redistribute(w[1:], "ipv4", PROTOCOLS_RIP)
        return {"redistribute": [r]} if r else None
    if w[0] == "default-metric" and len(w) == 2:
        return {"default_metric": w[1]}
    if line == "passive-interface default":
        return {"passive_default": True}
    if w[0] == "passive-interface" and len(w) == 2:
        return {"passive_interfaces": [w[1]]}
    if w[:2] == ["no", "passive-interface"] and len(w) == 3:
        return {"no_passive_interfaces": [w[2]]}
    if w[0] == "network" and len(w) == 2:
        return {"classful_networks": [w[1]]}
    if w[:2] == ["default-information", "originate"]:
        if len(w) == 2:
            return {"default_information": {"originate": True}}
        if len(w) == 4 and w[2] == "route-map":
            return {"default_information": {"originate": True, "route_map": w[3]}}
        return None
    if w[0] == "distance" and len(w) == 2:
        return {"distance": w[1]}
    if line == "auto-summary":
        return {"auto_summary": True}
    if line == "no auto-summary":
        return {"auto_summary": False}
    return None


def _merge_rip(entry: dict, fact: dict) -> bool:
    key, value = next(iter(fact.items()))
    if key == "timers":
        if any(entry["timers"].values()):
            return False
        entry["timers"] = value
        return True
    if key == "auto_summary":
        if entry[key] is not None:
            return False
        entry[key] = value
        return True
    return _merge(entry, fact)


def _empty_rip() -> dict:
    """Every structured field of `routing.rip` at its empty value, as a parser emits it (an
    unset timer and default route as ``{}``, not four empty strings)."""
    return {**complete({}, RIP), "timers": {}, "default_information": {}}


def claim_rip(lines: list, platform: str) -> dict:
    """`router rip`'s lines as the pack's fields; every line it does not model or cannot
    reproduce kept verbatim, in order (network statements in ``networks``, the rest in
    ``settings``)."""
    entry = _empty_rip()
    extras = []
    for line in lines:
        fact = _fact(line)
        ok = (fact is not None
              and not rip_problems(fact, (), cross=False)
              and reproduces(platform, "rip_body", (complete_rip(fact),), line)
              and _merge_rip(entry, fact))
        if not ok:
            extras.append(line)
    entry["redistribute"] = [compact(complete(r, REDISTRIBUTE), REDISTRIBUTE,
                                     keep=("protocol",)) for r in entry["redistribute"]]
    if rip_problems(entry, (), cross=True):
        # The lines together break a rule each passes alone: model none of them.
        entry, extras = _empty_rip(), list(lines)
    entry["networks"] = [l for l in extras if l.startswith("network ")]
    entry["settings"] = [l for l in extras if not l.startswith("network ")]
    entry["neighbors"] = []
    return entry


def claim_ripng(lines: list, platform: str) -> dict:
    """`ipv6 router rip <name>`'s lines: redistribution modelled, the rest kept in ``raw``."""
    entry = {"redistribute": []}
    extras = []
    for line in lines:
        w = line.split()
        r = parse_redistribute(w[1:], "ipv6", PROTOCOLS_RIPNG) if w[:1] == ["redistribute"] \
            else None
        fact = {"redistribute": [r]} if r else None
        ok = (fact is not None
              and not ripng_problems(fact, ())
              and reproduces(platform, "ripng_body", (complete_ripng(fact),), line))
        if ok:
            entry["redistribute"].append(r)
        else:
            extras.append(line)
    entry["redistribute"] = [compact(complete(r, REDISTRIBUTE), REDISTRIBUTE,
                                     keep=("protocol",)) for r in entry["redistribute"]]
    entry["raw"] = extras
    return entry


def claim_interface_line(entry: dict, text: str, platform: str) -> bool:
    """Model one ``ipv6 rip <text>`` interface line in ``ripng_interface``; False when the pack
    does not model it or cannot reproduce it (the caller keeps it verbatim)."""
    w = text.split()
    if len(w) == 2 and w[1] == "enable":
        fact = {"name": w[0], "enable": True}
    elif len(w) == 3 and w[1] == "default-information" and w[2] in ("originate", "only"):
        fact = {"name": w[0], "default_information": w[2]}
    else:
        return False
    if _ripng_interface_problems([fact], (), None):
        return False
    if not reproduces(platform, "ripng_interface", ([complete(fact, RIPNG_INTERFACE)],),
                      f"ipv6 rip {text}"):
        return False
    own = entry.setdefault("ripng_interface", [])
    same = next((e for e in own if e["name"] == fact["name"]), None)
    if same is None:
        own.append(dict(fact))
        return True
    if any(same.get(k) for k in fact if k != "name"):
        return False
    same.update(fact)
    return True


# ── the readers' view ────────────────────────────────────────────────────────

def raw_rip(rip: dict, platform: str) -> dict:
    lines = body_lines(platform, "rip_body", rip)
    out = {**rip, **_empty_rip()}
    out["settings"] = [l for l in lines if not l.startswith("network ")] \
        + list(rip.get("settings") or [])
    out["networks"] = [l for l in lines if l.startswith("network ")] \
        + list(rip.get("networks") or [])
    return out


def raw_ripng(proc: dict, platform: str) -> dict:
    lines = body_lines(platform, "ripng_body", proc)
    return {**proc, "redistribute": [], "raw": lines + list(proc.get("raw") or [])}


def raw_interface(iface: dict, platform: str) -> dict:
    entries = [complete(e, RIPNG_INTERFACE) for e in iface.get("ripng_interface") or []]
    lines = body_lines(platform, "ripng_interface", entries)
    return {**iface, "ripng": [l[len("ipv6 rip "):] for l in lines]
            + list(iface.get("ripng") or []), "ripng_interface": []}


# ── the checks ───────────────────────────────────────────────────────────────

def rip_problems(rip: dict, path: tuple, cross: bool = True) -> list:
    """What the pack refuses in `routing.rip`; *cross* False leaves out the rules between
    fields (a parser judges one line at a time)."""
    found = []
    if _is_set(rip.get("version")) and _scalar(rip.get("version")) not in ("1", "2"):
        found.append(_bad(path, "version", rip.get("version"), "RIP's version is 1 or 2"))
    timers = rip.get("timers")
    # A completed document carries the four as "": unset, not four bad values.
    if timers and not (isinstance(timers, dict)
                       and not any(_is_set(v) for v in timers.values())):
        if not isinstance(timers, dict):
            found.append(_bad(path, "timers", timers,
                              "a mapping: update, invalid, holddown, flush"))
        else:
            for field in TIMERS:
                if not is_int(timers.get(field), 0, 4294967295):
                    found.append(_bad(path + ("timers",), field, timers.get(field),
                                      "the four timers are given together, each a number "
                                      "of seconds"))
    networks = rip.get("classful_networks")
    if networks is not None and not isinstance(networks, list):
        found.append(_bad(path, "classful_networks", networks,
                          "a list of classful networks, such as 192.0.2.0"))
    for i, net in enumerate(networks if isinstance(networks, list) else []):
        own = classful(_scalar(net))
        if own is None:
            found.append(_bad(path + ("classful_networks",), i, net,
                              "a RIP network is an IPv4 classful network, such as 192.0.2.0"))
        elif str(own.network_address) != _scalar(net):
            found.append(_bad(path + ("classful_networks",), i, net,
                              f"RIP's network statement is classful, so {net} is "
                              f"{own} to the device; write {own.network_address}"))
    for field, low, high in (("default_metric", 1, 16), ("distance", 1, 255)):
        if _is_set(rip.get(field)) and not is_int(rip.get(field), low, high):
            found.append(_bad(path, field, rip.get(field), f"a number from {low} to {high}"))
    if rip.get("auto_summary") not in (None, True, False):
        found.append(_bad(path, "auto_summary", rip.get("auto_summary"),
                          "true (auto-summary), false (no auto-summary) or absent"))
    found += redistribute_problems(rip.get("redistribute"), "ipv4", path, PROTOCOLS_RIP,
                                   ospf=False)
    d = rip.get("default_information")
    if d and not isinstance(d, dict):
        found.append(_bad(path, "default_information", d, "a mapping: originate, route_map"))
    elif d and d.get("route_map") and not d.get("originate"):
        found.append(_bad(path + ("default_information",), "originate", d.get("originate"),
                          "a route_map qualifies an originated default route, and originate "
                          "is not true"))
    if cross:
        found += passive_problems(rip, path)
    return found


def ripng_problems(proc: dict, path: tuple) -> list:
    found = []
    if "name" in proc and not token(proc.get("name")):
        found.append(_bad(path, "name", proc.get("name"), "a RIPng process's name is one word"))
    found += redistribute_problems(proc.get("redistribute"), "ipv6", path, PROTOCOLS_RIPNG,
                                   ospf=False)
    return found


def _ripng_interface_problems(entries, path: tuple, names) -> list:
    if not entries:
        return []
    key = "ripng_interface"
    if not isinstance(entries, list):
        return [_bad(path, key, entries, "a list: name, enable, default_information")]
    found, seen = [], set()
    for i, e in enumerate(entries):
        where = path + (key, i)
        if not isinstance(e, dict):
            found.append(_bad(path + (key,), i, e, "a mapping with a name"))
            continue
        name = _scalar(e.get("name"))
        if not token(name):
            found.append(_bad(where, "name", e.get("name"), "a RIPng process's name is one "
                                                            "word"))
        elif name in seen:
            found.append(_bad(where, "name", e.get("name"),
                              "named twice on this interface; one entry per process"))
        elif names is not None and name not in names:
            found.append(_bad(where, "name", e.get("name"),
                              f"routing declares RIPng process(es) {sorted(names)}, and an "
                              "interface naming another makes IOS create a process intent "
                              "does not hold"))
        seen.add(name)
        if e.get("enable") not in (None, True, False):
            found.append(_bad(where, "enable", e.get("enable"), "it is true or false"))
        if _scalar(e.get("default_information")) not in ("", "originate", "only"):
            found.append(_bad(where, "default_information", e.get("default_information"),
                              "it is 'originate', 'only' or absent"))
    return found


def problems(hv: dict) -> list:
    found = []
    routing = hv.get("routing")
    names = None
    if isinstance(routing, dict):
        rip = routing.get("rip")
        if isinstance(rip, dict):
            found += rip_problems(rip, ("routing", "rip"))
        elif rip not in (None, {}):
            found.append(_bad(("routing",), "rip", rip, "a mapping (RIPv2's settings)"))
        procs = routing.get("ripng")
        if procs is not None and not isinstance(procs, list):
            found.append(_bad(("routing",), "ripng", procs, "a list of RIPng processes"))
        elif procs is not None:
            names = {_scalar(p.get("name")) for p in procs if isinstance(p, dict)}
            for i, proc in enumerate(procs):
                if isinstance(proc, dict):
                    found += ripng_problems(proc, ("routing", "ripng", i))
    for i, iface in enumerate(hv.get("interfaces") or []):
        if isinstance(iface, dict):
            found += _ripng_interface_problems(iface.get("ripng_interface"),
                                               ("interfaces", i), names)
    return found
