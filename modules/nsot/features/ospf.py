"""The OSPF packs: OSPFv2 (`routing.ospf[]`, `router ospf <process>`) and OSPFv3
(`routing.ospfv3[]`, `ipv6 router ospf <process>`), and an interface's own OSPF settings
(`interfaces[].ospf_interface`, `interfaces[].ospfv3_interface`). docs/FEATURE_PACKS.md.

The fields are OSPF's own concepts, not IOS's words: a process has a router id, areas (each
with its type, its networks, its summary ranges), redistribution, passive interfaces and a
default route; an interface joins an area with a cost, a network type and a priority. The
partial (`templates/_routing.j2`) writes them in a dialect's words.
"""

import ipaddress

from modules.nsot.features import (DictOf, ListOf, area_number, body_lines, compact,
                                   complete, dotted, is_int, is_ipv4, reproduces, token,
                                   _scalar)

# ── the schema ───────────────────────────────────────────────────────────────

#: A network statement (OSPFv2): the address and wildcard as IOS holds them, or an authored
#: ``prefix`` (an address and its length) that the render writes out as both.
NETWORK = {"address": "", "wildcard": "", "prefix": ""}
#: A summary range an ABR advertises for an area: IPv4 as address and mask (or an authored
#: ``prefix``), IPv6 as a prefix. ``advertise`` false is IOS's `not-advertise`.
RANGE = {"address": "", "mask": "", "prefix": "", "advertise": True, "cost": ""}
AREA = {"id": "", "type": "", "no_summary": False, "default_cost": "",
        "networks": ListOf(NETWORK), "ranges": ListOf(RANGE)}
AREA_V3 = {"id": "", "type": "", "no_summary": False, "default_cost": "",
           "ranges": ListOf(RANGE)}
REDISTRIBUTE = {"protocol": "", "process": "", "metric": "", "metric_type": "",
                "subnets": False, "tag": "", "route_map": "", "include_connected": False}
DEFAULT_INFORMATION = {"originate": False, "always": False, "metric": "", "metric_type": "",
                       "route_map": ""}
_COMMON = {"router_id": "", "log_adjacency_changes": None, "reference_bandwidth": "",
           "redistribute": ListOf(REDISTRIBUTE), "passive_default": False,
           "passive_interfaces": ListOf(), "no_passive_interfaces": ListOf(),
           "default_information": DictOf(DEFAULT_INFORMATION), "distance": ""}
#: `routing.ospf[]`'s structured fields; the lines no pack models stay in ``settings`` and
#: ``networks`` (the shape intent had before the packs).
PROCESS = {**_COMMON, "areas": ListOf(AREA)}
#: `routing.ospfv3[]`'s; its unmodelled lines stay in ``raw``.
PROCESS_V3 = {**_COMMON, "areas": ListOf(AREA_V3)}
RAW_V2 = {"settings": ListOf(), "networks": ListOf(), "neighbors": ListOf()}
RAW_V3 = {"raw": ListOf()}
#: An interface's own OSPF settings (`ip ospf ...` / `ipv6 ospf ...`).
INTERFACE = {"process": "", "area": "", "cost": "", "network_type": "", "priority": "",
             "hello_interval": "", "dead_interval": ""}

AREA_TYPES = ("", "normal", "stub", "nssa")
NETWORK_TYPES = ("broadcast", "non-broadcast", "point-to-point", "point-to-multipoint")
#: What OSPF may redistribute, and whether each names a process (an OSPF process or BGP/EIGRP
#: AS number; OSPFv3's RIP is RIPng, which has a name).
PROTOCOLS = {"ipv4": {"connected": False, "static": False, "rip": False, "bgp": True,
                      "ospf": True, "eigrp": True},
             "ipv6": {"connected": False, "static": False, "rip": True, "bgp": True,
                      "ospf": True, "eigrp": True}}

_SPECS = {"ipv4": (PROCESS, RAW_V2, "ospf_body"), "ipv6": (PROCESS_V3, RAW_V3, "ospfv3_body")}


def complete_process(proc: dict, family: str) -> dict:
    """*proc* with every field present, an authored IPv4 prefix written out in IOS's notation
    (and emptied, so the result is itself a valid process: completing it twice is completing
    it once)."""
    spec, raw, _macro = _SPECS[family]
    out = complete(proc, {**spec, **raw})
    for area in out["areas"]:
        for net in area.get("networks") or []:
            if net["prefix"] and not net["address"]:
                n = ipaddress.IPv4Network(net["prefix"])
                net["address"], net["wildcard"] = str(n.network_address), str(n.hostmask)
                net["prefix"] = ""
        for rng in area["ranges"]:
            if family == "ipv4" and rng["prefix"] and not rng["address"]:
                n = ipaddress.IPv4Network(rng["prefix"])
                rng["address"], rng["mask"] = str(n.network_address), str(n.netmask)
                rng["prefix"] = ""
    return out


def empty_process(family: str) -> dict:
    """Every structured field of a process, at its empty value (an unset default route as
    ``{}``, as a parser emits it)."""
    spec, _raw, _macro = _SPECS[family]
    return {**complete({}, spec), "default_information": {}}


# ── parsing: one line at a time, kept only when the partial reproduces it ────

def parse_redistribute(words: list, family: str, protocols: dict = None):
    """``redistribute``'s words after the keyword as a field, or None when a word is not one
    the pack models (the line then stays verbatim)."""
    protocols = protocols or PROTOCOLS[family]
    if not words or words[0] not in protocols:
        return None
    out, i = {"protocol": words[0]}, 1
    if protocols[words[0]]:
        if len(words) < 2:
            return None
        out["process"], i = words[1], 2
    options = {"metric": "metric", "metric-type": "metric_type", "tag": "tag",
               "route-map": "route_map"}
    while i < len(words):
        word = words[i]
        if word in options and i + 1 < len(words):
            out[options[word]] = words[i + 1]
            i += 2
        elif word == "subnets":
            out["subnets"], i = True, i + 1
        elif word == "include-connected":
            out["include_connected"], i = True, i + 1
        else:
            return None
    return out


def _fact(line: str, family: str):
    """The one field *line* states, as a process holding only it, or None."""
    w = line.split()
    if not w:
        return None
    if w[0] == "router-id" and len(w) == 2:
        return {"router_id": w[1]}
    if line == "log-adjacency-changes":
        return {"log_adjacency_changes": True}
    if line == "log-adjacency-changes detail":
        return {"log_adjacency_changes": "detail"}
    if line == "no log-adjacency-changes":
        return {"log_adjacency_changes": False}
    if w[:2] == ["auto-cost", "reference-bandwidth"] and len(w) == 3:
        return {"reference_bandwidth": w[2]}
    if w[0] == "area" and len(w) >= 3:
        area = {"id": w[1]}
        if w[2] in ("stub", "nssa") and (len(w) == 3 or w[3:] == ["no-summary"]):
            area.update(type=w[2], no_summary=len(w) == 4)
        elif w[2] == "default-cost" and len(w) == 4:
            area["default_cost"] = w[3]
        elif w[2] == "range":
            rest = w[3:]
            if family == "ipv4" and len(rest) >= 2:
                rng, rest = {"address": rest[0], "mask": rest[1]}, rest[2:]
            elif family == "ipv6" and rest:
                rng, rest = {"prefix": rest[0]}, rest[1:]
            else:
                return None
            while rest:
                if rest[0] == "not-advertise":
                    rng["advertise"], rest = False, rest[1:]
                elif rest[0] == "cost" and len(rest) >= 2:
                    rng["cost"], rest = rest[1], rest[2:]
                else:
                    return None
            area["ranges"] = [rng]
        else:
            return None
        return {"areas": [area]}
    if family == "ipv4" and w[0] == "network" and len(w) == 5 and w[3] == "area":
        return {"areas": [{"id": w[4], "networks": [{"address": w[1], "wildcard": w[2]}]}]}
    if w[0] == "redistribute":
        r = parse_redistribute(w[1:], family)
        return {"redistribute": [r]} if r else None
    if line == "passive-interface default":
        return {"passive_default": True}
    if w[0] == "passive-interface" and len(w) == 2:
        return {"passive_interfaces": [w[1]]}
    if w[:2] == ["no", "passive-interface"] and len(w) == 3:
        return {"no_passive_interfaces": [w[2]]}
    if w[:2] == ["default-information", "originate"]:
        d, rest = {"originate": True}, w[2:]
        while rest:
            if rest[0] == "always":
                d["always"], rest = True, rest[1:]
            elif rest[0] in ("metric", "metric-type", "route-map") and len(rest) >= 2:
                d[rest[0].replace("-", "_")], rest = rest[1], rest[2:]
            else:
                return None
        return {"default_information": d}
    if w[0] == "distance" and len(w) == 2:
        return {"distance": w[1]}
    return None


def _merge(entry: dict, fact: dict) -> bool:
    """Fold *fact* into *entry*; False, changing nothing, when it would overwrite a field
    already set (the line then stays verbatim, so nothing is lost)."""
    key, value = next(iter(fact.items()))
    if key == "areas":
        new = value[0]
        same = [a for a in entry["areas"] if area_number(a["id"]) == area_number(new["id"])]
        if same and same[0]["id"] != new["id"]:
            return False                   # one area written two ways: keep the line as typed
        if not same:
            entry["areas"].append({"id": new["id"]})
            same = entry["areas"][-1:]
        area = same[0]
        for field in ("type", "default_cost"):
            if new.get(field) and area.get(field):
                return False
        for field, val in new.items():
            if field in ("networks", "ranges"):
                area.setdefault(field, []).extend(val)
            elif field != "id":
                area[field] = val
        return True
    if isinstance(value, list):
        entry[key].extend(value)
        return True
    if key == "default_information":
        if (entry[key] or {}).get("originate"):
            return False
        entry[key] = value
        return True
    if entry[key] not in ("", None, False):
        return False
    entry[key] = value
    return True


def claim_process(lines: list, family: str, platform: str) -> dict:
    """A process's lines (its header's children, in order) as the pack's fields, every line
    the pack does not model or cannot reproduce kept verbatim, in order: OSPFv2's network
    statements in ``networks``, the rest in ``settings``; OSPFv3's in ``raw``."""
    _spec, _raw, macro = _SPECS[family]
    area_spec = AREA if family == "ipv4" else AREA_V3
    entry = empty_process(family)
    extras = []
    for line in lines:
        fact = _fact(line, family)
        ok = (fact is not None
              and not process_problems(fact, family, (), cross=False)
              and reproduces(platform, macro, (complete_process(fact, family),), line)
              and _merge(entry, fact))
        if not ok:
            extras.append(line)
    if process_problems(entry, family, (), cross=True):
        # The lines together break a rule each passes alone: model none of them.
        entry, extras = empty_process(family), list(lines)
    for i, area in enumerate(entry["areas"]):
        entry["areas"][i] = compact(complete(area, area_spec), area_spec, keep=("id",))
    entry["redistribute"] = [compact(complete(r, REDISTRIBUTE), REDISTRIBUTE,
                                     keep=("protocol",)) for r in entry["redistribute"]]
    if entry["default_information"]:
        entry["default_information"] = compact(complete(entry["default_information"],
                                                        DEFAULT_INFORMATION),
                                               DEFAULT_INFORMATION)
    if family == "ipv4":
        entry["networks"] = [l for l in extras if l.startswith("network ")]
        entry["settings"] = [l for l in extras if not l.startswith("network ")]
        entry["neighbors"] = []
    else:
        entry["raw"] = extras
    return entry


def claim_interface_line(entry: dict, kind: str, text: str, platform: str) -> bool:
    """Model one ``ip ospf <text>`` (*kind* ``ospf``) or ``ipv6 ospf <text>`` (``ospfv3``)
    interface line in ``<kind>_interface``; False when the pack does not model it or cannot
    reproduce it (the caller keeps it verbatim)."""
    w = text.split()
    fact = None
    if len(w) == 3 and w[1] == "area":
        fact = {"process": w[0], "area": w[2]}
    elif len(w) == 2 and w[0] in ("cost", "priority", "network", "hello-interval",
                                  "dead-interval"):
        fact = {{"network": "network_type"}.get(w[0], w[0].replace("-", "_")): w[1]}
    if fact is None or interface_problems(fact, (), "", None):
        return False
    prefix = "ip ospf" if kind == "ospf" else "ipv6 ospf"
    if not reproduces(platform, "ospf_interface", (complete(fact, INTERFACE), prefix),
                      f"{prefix} {text}"):
        return False
    own = entry.setdefault(f"{kind}_interface", {})
    if any(own.get(k) for k in fact):
        return False
    own.update(fact)
    return True


# ── the readers' view: the fields back as lines ──────────────────────────────

def raw_process(proc: dict, family: str, platform: str) -> dict:
    """A completed process with its fields written back as lines (`features.raw_view`)."""
    _spec, _raw, macro = _SPECS[family]
    lines = body_lines(platform, macro, proc)
    out = {**proc, **empty_process(family)}
    if family == "ipv4":
        out["settings"] = [l for l in lines if not l.startswith("network ")] \
            + list(proc.get("settings") or [])
        out["networks"] = [l for l in lines if l.startswith("network ")] \
            + list(proc.get("networks") or [])
    else:
        out["raw"] = lines + list(proc.get("raw") or [])
    return out


def raw_interface(iface: dict, platform: str, kinds=("ospf", "ospfv3")) -> dict:
    """A completed interface with its OSPF fields (of *kinds*) written back as lines."""
    out = dict(iface)
    for kind, prefix in (("ospf", "ip ospf"), ("ospfv3", "ipv6 ospf")):
        if kind not in kinds:
            continue
        own = iface.get(f"{kind}_interface") or {}
        lines = body_lines(platform, "ospf_interface", complete(own, INTERFACE), prefix)
        out[kind] = [l[len(prefix) + 1:] for l in lines] + list(iface.get(kind) or [])
        out[f"{kind}_interface"] = {}
    return out


# ── the checks ───────────────────────────────────────────────────────────────

def _bad(path, key, value, rule) -> tuple:
    return (path, key, f"{dotted(path, key)} is {value!r}: {rule}")


def _is_set(value) -> bool:
    return value not in (None, "")


AREA_RULE = ("an OSPF area is a number from 0 to 4294967295, or the same number written as "
             "a dotted quad")


def process_problems(proc: dict, family: str, path: tuple, cross: bool = True) -> list:
    """What a pack refuses in one process (*path* is where it sits, for the words); *cross*
    False leaves out the rules between fields (a parser judges one line at a time)."""
    found = []
    key = "ospf" if family == "ipv4" else "ospfv3"
    if "process" in proc and not is_int(proc.get("process"), 1, 65535):
        found.append(_bad(path, "process", proc.get("process"),
                          f"an {key.upper()} process is a number from 1 to 65535"))
    if _is_set(proc.get("router_id")) and not is_ipv4(proc.get("router_id")):
        found.append(_bad(path, "router_id", proc.get("router_id"),
                          "a router id is written as an IPv4 address (OSPFv3's too), such "
                          "as 192.0.2.1"))
    if proc.get("log_adjacency_changes") not in (None, True, False, "detail"):
        found.append(_bad(path, "log_adjacency_changes", proc.get("log_adjacency_changes"),
                          "it is true, false or 'detail'"))
    if _is_set(proc.get("reference_bandwidth")) and \
            not is_int(proc.get("reference_bandwidth"), 1, 4294967):
        found.append(_bad(path, "reference_bandwidth", proc.get("reference_bandwidth"),
                          "the reference bandwidth is a number of Mbit/s from 1 to 4294967"))
    if _is_set(proc.get("distance")) and not is_int(proc.get("distance"), 1, 255):
        found.append(_bad(path, "distance", proc.get("distance"),
                          "an administrative distance is a number from 1 to 255"))
    found += _area_problems(proc.get("areas"), family, path)
    found += redistribute_problems(proc.get("redistribute"), family, path,
                                   PROTOCOLS[family], ospf=True)
    found += passive_problems(proc, path, cross)
    found += _default_information_problems(proc.get("default_information"), path)
    return found


def _area_problems(areas, family, path) -> list:
    if areas is None:
        return []
    if not isinstance(areas, list):
        return [_bad(path, "areas", areas, "a list of areas, each with an id")]
    found, seen = [], {}
    for i, area in enumerate(areas):
        where = path + ("areas", i)
        if not isinstance(area, dict):
            found.append(_bad(path + ("areas",), i, area, "an area is a mapping with an id"))
            continue
        number = area_number(area.get("id"))
        if number is None:
            found.append(_bad(where, "id", area.get("id"), AREA_RULE))
        elif number in seen:
            j = seen[number]
            found.append(_bad(where, "id", area.get("id"),
                              f"the same area as {dotted(path + ('areas', j), 'id')} "
                              f"({areas[j].get('id')!r}); one entry per area"))
        else:
            seen[number] = i
        kind = _scalar(area.get("type"))
        if kind not in AREA_TYPES:
            found.append(_bad(where, "type", area.get("type"),
                              f"an area's type is one of {', '.join(repr(t) for t in AREA_TYPES[1:])}"))
        elif area.get("no_summary") and kind not in ("stub", "nssa"):
            found.append(_bad(where, "no_summary", area.get("no_summary"),
                              f"no-summary applies to a stub or NSSA area, and this one's "
                              f"type is {kind or 'normal'!r}"))
        if kind in ("stub", "nssa") and number == 0:
            found.append(_bad(where, "type", kind, "the backbone, area 0, is never a stub or "
                                                   "NSSA area"))
        if _is_set(area.get("default_cost")) and not is_int(area.get("default_cost"), 0,
                                                            16777215):
            found.append(_bad(where, "default_cost", area.get("default_cost"),
                              "a default cost is a number from 0 to 16777215"))
        for j, net in enumerate(area.get("networks") or []):
            found += _network_problems(net, where + ("networks", j))
        for j, rng in enumerate(area.get("ranges") or []):
            found += _range_problems(rng, family, where + ("ranges", j))
    return found


def _network_problems(net, path) -> list:
    if not isinstance(net, dict):
        return [_bad(path[:-1], path[-1], net, "a network is a mapping: address and "
                                               "wildcard, or prefix")]
    found = []
    if _is_set(net.get("prefix")):
        try:
            ipaddress.IPv4Network(_scalar(net.get("prefix")))
        except ValueError as exc:
            found.append(_bad(path, "prefix", net.get("prefix"),
                              f"not an IPv4 network ({exc})"))
        if _is_set(net.get("address")) or _is_set(net.get("wildcard")):
            found.append(_bad(path, "prefix", net.get("prefix"),
                              f"a network is a prefix OR an address and wildcard, and this "
                              f"one also has address {net.get('address')!r} and wildcard "
                              f"{net.get('wildcard')!r}"))
        return found
    if not is_ipv4(net.get("address")):
        found.append(_bad(path, "address", net.get("address"),
                          "a network statement's address is an IPv4 address"))
    if not is_ipv4(net.get("wildcard")):
        found.append(_bad(path, "wildcard", net.get("wildcard"),
                          "a wildcard is written as an IPv4 address (the mask's inverse)"))
    return found


def _range_problems(rng, family, path) -> list:
    if not isinstance(rng, dict):
        return [_bad(path[:-1], path[-1], rng, "a range is a mapping with a prefix")]
    found = []
    if family == "ipv6":
        try:
            ipaddress.IPv6Network(_scalar(rng.get("prefix")))
        except ValueError as exc:
            found.append(_bad(path, "prefix", rng.get("prefix"),
                              f"an OSPFv3 range is an IPv6 network such as 2001:db8:10::/48 "
                              f"({exc})"))
    elif _is_set(rng.get("prefix")):
        try:
            ipaddress.IPv4Network(_scalar(rng.get("prefix")))
        except ValueError as exc:
            found.append(_bad(path, "prefix", rng.get("prefix"),
                              f"not an IPv4 network ({exc})"))
    else:
        address, mask = _scalar(rng.get("address")), _scalar(rng.get("mask"))
        try:
            net = ipaddress.IPv4Network(f"{address}/{mask}", strict=False)
            if str(net.network_address) != address:
                found.append(_bad(path, "address", rng.get("address"),
                                  f"not the network of mask {mask} (that is "
                                  f"{net.network_address})"))
        except ValueError as exc:
            found.append(_bad(path, "mask", rng.get("mask"),
                              f"address {address!r} and mask {mask!r} are not a network "
                              f"({exc})"))
    if rng.get("advertise") not in (None, True, False):
        found.append(_bad(path, "advertise", rng.get("advertise"), "it is true or false"))
    if _is_set(rng.get("cost")) and not is_int(rng.get("cost"), 0, 16777215):
        found.append(_bad(path, "cost", rng.get("cost"),
                          "a range's cost is a number from 0 to 16777215"))
    return found


def redistribute_problems(items, family, path, protocols: dict, ospf: bool) -> list:
    """Shared with RIP (*ospf* False: no metric type, no subnets, a metric up to 16)."""
    if items is None:
        return []
    if not isinstance(items, list):
        return [_bad(path, "redistribute", items, "a list of protocols to redistribute")]
    found = []
    for i, r in enumerate(items):
        where = path + ("redistribute", i)
        if not isinstance(r, dict):
            found.append(_bad(path + ("redistribute",), i, r,
                              "an entry is a mapping with a protocol"))
            continue
        proto = _scalar(r.get("protocol"))
        if proto not in protocols:
            found.append(_bad(where, "protocol", r.get("protocol"),
                              f"this pack redistributes {', '.join(sorted(protocols))}"))
            continue
        if protocols[proto] and not token(r.get("process")):
            found.append(_bad(where, "process", r.get("process"),
                              f"redistributing {proto} names its "
                              + ("name" if proto == "rip" else "process or AS number")))
        elif not protocols[proto] and _is_set(r.get("process")):
            found.append(_bad(where, "process", r.get("process"),
                              f"{proto} has no process to name"))
        elif protocols[proto] and proto != "rip" and not is_int(r.get("process"), 1,
                                                                 4294967295):
            found.append(_bad(where, "process", r.get("process"),
                              f"{proto}'s process or AS number is a number"))
        top = 16777214 if ospf else 16
        if _is_set(r.get("metric")) and not is_int(r.get("metric"), 0, top):
            found.append(_bad(where, "metric", r.get("metric"),
                              f"a metric here is a number from 0 to {top}"))
        if _is_set(r.get("metric_type")) and (not ospf or _scalar(r.get("metric_type"))
                                              not in ("1", "2")):
            found.append(_bad(where, "metric_type", r.get("metric_type"),
                              "an OSPF external metric type is 1 or 2" if ospf
                              else "RIP has no metric type"))
        if r.get("subnets") and not (ospf and family == "ipv4"):
            found.append(_bad(where, "subnets", r.get("subnets"),
                              "only OSPFv2 takes `subnets`"))
        if r.get("include_connected") and family != "ipv6":
            found.append(_bad(where, "include_connected", r.get("include_connected"),
                              "only the IPv6 protocols take `include-connected`"))
        if _is_set(r.get("tag")) and (not ospf or not is_int(r.get("tag"), 0, 4294967295)):
            found.append(_bad(where, "tag", r.get("tag"),
                              "a tag is a number from 0 to 4294967295" if ospf
                              else "RIP takes no tag here"))
        if _is_set(r.get("route_map")) and not token(r.get("route_map")):
            found.append(_bad(where, "route_map", r.get("route_map"),
                              "a route-map's name is one word"))
    return found


def passive_problems(proc: dict, path: tuple, cross: bool = True) -> list:
    found = []
    default = proc.get("passive_default")
    if default not in (None, True, False):
        found.append(_bad(path, "passive_default", default, "it is true or false"))
    for key in ("passive_interfaces", "no_passive_interfaces"):
        names = proc.get(key)
        if names is None:
            continue
        if not isinstance(names, list):
            found.append(_bad(path, key, names, "a list of interface names"))
            continue
        for i, name in enumerate(names):
            if not token(name):
                found.append(_bad(path + (key,), i, name, "an interface name is one word"))
    if cross and default and proc.get("passive_interfaces"):
        found.append(_bad(path, "passive_interfaces", proc.get("passive_interfaces"),
                          "passive_default is true, so every interface is passive already; "
                          "list the ones that are NOT in no_passive_interfaces"))
    if cross and not default and proc.get("no_passive_interfaces"):
        found.append(_bad(path, "no_passive_interfaces", proc.get("no_passive_interfaces"),
                          "passive_default is false, so no interface is passive by default; "
                          "list the passive ones in passive_interfaces"))
    return found


def _default_information_problems(d, path) -> list:
    if d is None or d == {}:
        return []
    if not isinstance(d, dict):
        return [_bad(path, "default_information", d, "a mapping: originate, always, metric, "
                                                     "metric_type, route_map")]
    where = path + ("default_information",)
    found = []
    if not d.get("originate") and any(d.get(k) for k in ("always", "metric", "metric_type",
                                                         "route_map")):
        found.append(_bad(where, "originate", d.get("originate"),
                          "always, metric, metric_type and route_map qualify an originated "
                          "default route, and originate is not true"))
    if _is_set(d.get("metric")) and not is_int(d.get("metric"), 0, 16777214):
        found.append(_bad(where, "metric", d.get("metric"),
                          "a metric is a number from 0 to 16777214"))
    if _is_set(d.get("metric_type")) and _scalar(d.get("metric_type")) not in ("1", "2"):
        found.append(_bad(where, "metric_type", d.get("metric_type"),
                          "an OSPF external metric type is 1 or 2"))
    if _is_set(d.get("route_map")) and not token(d.get("route_map")):
        found.append(_bad(where, "route_map", d.get("route_map"),
                          "a route-map's name is one word"))
    return found


def interface_problems(own, path: tuple, key: str, processes) -> list:
    """One interface's ``ospf_interface`` or ``ospfv3_interface``; *processes* the process
    numbers intent declares for that family (None: not compared)."""
    if not own:
        return []
    where = path + ((key,) if key else ())
    if not isinstance(own, dict):
        return [_bad(path, key, own, "a mapping: process, area, cost, network_type, "
                                     "priority, hello_interval, dead_interval")]
    found = []
    has_process, has_area = _is_set(own.get("process")), _is_set(own.get("area"))
    if has_process != has_area:
        found.append(_bad(where, "area" if has_process else "process",
                          own.get("area") if has_process else own.get("process"),
                          f"an interface joins an area of a process, so process "
                          f"({own.get('process')!r}) and area ({own.get('area')!r}) are "
                          "given together"))
    if has_process and not is_int(own.get("process"), 1, 65535):
        found.append(_bad(where, "process", own.get("process"),
                          "a process is a number from 1 to 65535"))
    elif has_process and processes is not None and _scalar(own.get("process")) \
            not in processes:
        found.append(_bad(where, "process", own.get("process"),
                          f"routing declares process(es) {sorted(processes)}, and an "
                          "interface naming another makes IOS create a process intent does "
                          "not hold"))
    if has_area and area_number(own.get("area")) is None:
        found.append(_bad(where, "area", own.get("area"), AREA_RULE))
    for field, low, high in (("cost", 1, 65535), ("priority", 0, 255),
                             ("hello_interval", 1, 65535), ("dead_interval", 1, 65535)):
        if _is_set(own.get(field)) and not is_int(own.get(field), low, high):
            found.append(_bad(where, field, own.get(field),
                              f"a number from {low} to {high}"))
    if _is_set(own.get("network_type")) and own.get("network_type") not in NETWORK_TYPES:
        found.append(_bad(where, "network_type", own.get("network_type"),
                          f"one of {', '.join(NETWORK_TYPES)}"))
    return found


def problems(hv: dict) -> list:
    """Every OSPF field of *hv* the pack refuses."""
    found = []
    routing = hv.get("routing")
    declared = {"ospf": None, "ospfv3": None}
    if isinstance(routing, dict):
        for family, key in (("ipv4", "ospf"), ("ipv6", "ospfv3")):
            procs = routing.get(key)
            if procs is None:
                continue
            if not isinstance(procs, list):
                found.append(_bad(("routing",), key, procs, "a list of processes"))
                continue
            declared[key] = {_scalar(p.get("process")) for p in procs if isinstance(p, dict)}
            for i, proc in enumerate(procs):
                if isinstance(proc, dict):
                    found += process_problems(proc, family, ("routing", key, i))
    for i, iface in enumerate(hv.get("interfaces") or []):
        if not isinstance(iface, dict):
            continue
        for kind in ("ospf", "ospfv3"):
            found += interface_problems(iface.get(f"{kind}_interface"), ("interfaces", i),
                                        f"{kind}_interface", declared[kind])
    return found
