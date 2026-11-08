"""B, the protected set: what no write may break, derived from NetBox, and the one guard every
write that could break it asks (the SDN platform design revision 6, section 4; C2379, C2588,
C2589). Deterministic; no AI; reads only (nothing here writes to NetBox or a device).

**Protected objects, per device** (`device_objects`), each with why, so a refusal names it:
- **derived**, with nothing to set: the interface holding the device's primary IPv4, primary
  IPv6 or OOB address, or marked ``mgmt_only``; then, from each, its parent, its LAG and its
  bridge (and a protected LAG's members); the VLAN when that interface is a VLAN interface (a
  virtual interface named ``vlan<N>``/``Vlan<N>`` or carrying one untagged VLAN, as ``eno1.100``
  does); and every physical port carrying a protected VLAN, tagged or untagged (``tagged-all``
  carries every VLAN). For Lab 9 that is Management1, eno1 and eno1.100, VLAN 100 and the
  ProCurve's port 1 (C2588, C2589), with no NetBox tag;
- **declared:** the tag ``mercury-protected`` (`TAG`) on an interface, a VLAN, an IP address or
  a prefix (an interface holding an address inside such a prefix is protected). An IP address's
  own tag is read only where its record carries tags: neither the NSOT export nor the live
  interface read (`nsot.context._fetch_interfaces`) keeps them yet, so tag the prefix or the
  interface instead (the register's row for it).

**Protected flow classes** (`flow_classes`), each a match (alternatives of OpenFlow match fields,
`CLASS_FIELDS`), an invariant, its owners and its NetBox source:
- the **control channel**: TCP to and from each ``openflow`` Service's address and port
  (`untouchable`), beside `control_plane`'s own rules for the controller connection (LLDP, the
  connection's addresses, OpenFlow's ports), which stay where they are (C2022);
- **management**: traffic between two addresses of a prefix holding a device's management
  address (IPv4, IPv6, and ARP inside an IPv4 one), `untouchable`; an address in no recorded
  prefix is its own host prefix;
- a **Service tagged** ``mercury-protected``: its protocol and ports to and from its addresses
  (its own, else its device's primary ones), ``must_reach <service>``;
- the config context's ``mercury.protected_flows`` (`CONTEXT_KEY`): a list of ``{name, match,
  invariant, reason, owners}``, the match in `CLASS_FIELDS`' names, assigned by site or role.
  An entry not of its shape makes the whole set unreadable, and an unreadable set refuses
  every write it guards (an unreadable store refuses writes).

**A rule overlaps a class** (`overlap`) when, on every field both name, their values meet: equal
numbers, intersecting prefixes (IPv4 and IPv6 alike); a field the rule leaves unset meets every
value. A rule from anyone not among the class's owners that overlaps it is refused, naming the
rule, the class, each overlapping field with both values, and the class's NetBox source. A
removal is refused only when the removed flow NAMES the class (one of its addresses or ports
inside the class's): taking off a flow that covers it by breadth restores what was there
(C2022's rule). ``must_reach``'s path check after a change is H's and J's (`trace.py`), not here.

**Where the set comes from** (`for_network`): the network's committed NSOT export
(`modules/nsot/export.py`) when there is one, else NetBox read now (`export.build`, reads only);
a network whose devices are not NetBox's has none, and says so (only the controller
connection's control channel is guarded there); a committed export that does not verify, or a
NetBox that cannot be read, is ``unreadable``. Its SHA-256 is the export's, so a plan can bind it.

**Who asks** (tests/test_every_write_asks_protected.py holds every sender to it): the flow
operation core (`flow_ops.plan`, so SDN › Flows, the closed loop's responses and their re-apply
share one guard; `flow_refusal`) and the OpenFlow render (`openflow_templates.render`, so every
switch's OpenFlow configuration; `ports_refusal`).
"""

import hashlib
import ipaddress
import json
import logging
import re

log = logging.getLogger(__name__)

TAG = "mercury-protected"
CONTEXT_KEY = ("mercury", "protected_flows")
SERVICE = "openflow"
INVARIANTS = ("untouchable", "must_reach")
#: The match fields a class is stated in and a rule is compared on (the SDN design revision 6,
#: section 4: the
#: EtherType, the IP protocol, the transport ports and the address prefixes).
ADDRESS_FIELDS = ("ipv4_src", "ipv4_dst", "ipv6_src", "ipv6_dst", "arp_spa", "arp_tpa")
PORT_FIELDS = ("tcp_src", "tcp_dst", "udp_src", "udp_dst", "sctp_src", "sctp_dst")
CLASS_FIELDS = ("eth_type", "ip_proto") + PORT_FIELDS + ADDRESS_FIELDS
ETH_IPV4, ETH_IPV6, ETH_ARP = 0x0800, 0x86DD, 0x0806
PROTOCOLS = {"tcp": 6, "udp": 17, "sctp": 132}
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")
_VLAN_NAME = re.compile(r"(?i)^vlan[ ._-]?([0-9]{1,4})$")
OFPVID_PRESENT = 0x1000


class Unreadable(ValueError):
    """The protected set could not be read or is not of its shape, in words."""


# --------------------------------------------------------------------------- shapes

def _name(obj) -> str:
    if isinstance(obj, dict):
        return str(obj.get("name") or obj.get("display") or "")
    return str(obj or "")


def _slug(obj) -> str:
    if isinstance(obj, dict):
        return str(obj.get("value") or obj.get("slug") or "")
    return str(obj or "")


def _vid(vlan):
    value = vlan.get("vid") if isinstance(vlan, dict) else vlan
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _tags(obj) -> set:
    out = set()
    for t in (obj or {}).get("tags") or []:
        out.add(str(t.get("slug") or t.get("name") or "").lower() if isinstance(t, dict)
                else str(t).lower())
    return out


def _host(text) -> str:
    """The address of ``192.0.2.5/24`` (or of a NetBox address record), or ``""``."""
    if isinstance(text, dict):
        text = text.get("address")
    try:
        return str(ipaddress.ip_interface(str(text or "").strip()).ip) if text else ""
    except ValueError:
        return ""


def _addresses(iface: dict) -> list:
    """``[(address, tags)]`` an interface holds, from NetBox's records or the export's strings."""
    out = []
    for a in iface.get("ip_addresses") or []:
        host = _host(a)
        if host:
            out.append((host, _tags(a) if isinstance(a, dict) else set()))
    return out


def interface_of(i: dict) -> dict:
    """An interface record, from NetBox's REST shape or the export's, in one shape."""
    return {"name": _name(i), "type": _slug(i.get("type")), "mode": _slug(i.get("mode")),
            "mgmt_only": bool(i.get("mgmt_only")), "untagged": _vid(i.get("untagged_vlan")),
            "tagged": sorted(v for v in (_vid(t) for t in i.get("tagged_vlans") or [])
                             if v is not None),
            "parent": _name(i.get("parent")), "lag": _name(i.get("lag")),
            "bridge": _name(i.get("bridge")), "tags": _tags(i), "addresses": _addresses(i),
            "openflow_port": (i.get("custom_fields") or {}).get("openflow_port")}


def _management(device: dict) -> list:
    """``[(words, address)]``: the device's primary IPv4, primary IPv6 and OOB addresses."""
    return [(words, _host(device.get(key))) for key, words in
            (("primary_ip4", "primary IPv4"), ("primary_ip6", "primary IPv6"),
             ("oob_ip", "OOB"))
            if _host(device.get(key))]


def _networks(prefixes) -> list:
    out = []
    for p in prefixes or []:
        try:
            out.append((ipaddress.ip_network(str(p.get("prefix") or ""), strict=False), p))
        except ValueError:
            continue
    return out


# --------------------------------------------------------------------------- objects

def vlan_of(iface: dict):
    """The VLAN a VLAN interface is (``vlan100``, ``Vlan100``, or a virtual interface carrying
    one untagged VLAN, such as ``eno1.100``), or None for any other interface."""
    i = iface if "untagged" in iface else interface_of(iface)
    m = _VLAN_NAME.match(i["name"])
    if m:
        return int(m.group(1))
    if i["type"] == "virtual" and i["untagged"] is not None and not i["tagged"]:
        return i["untagged"]
    return None


def device_objects(device: dict, interfaces: list, vlans=(), prefixes=()) -> dict:
    """*device*'s protected objects: ``{"interfaces": {name: why}, "vlans": {vid: why}}``, from
    its record, its *interfaces* and the network's *vlans* and *prefixes* records (NetBox's
    REST shapes or the export's). Each why names what it was derived from."""
    name = _name(device)
    ifs = [interface_of(i) for i in interfaces or []]
    by_name = {i["name"]: i for i in ifs}
    held = {a: words for words, a in _management(device)}
    tagged_prefixes = [(net, p) for net, p in _networks(prefixes) if TAG in _tags(p)]
    out_if, out_vlan = {}, {}

    def add(iface_name, why):
        if iface_name and iface_name not in out_if:
            out_if[iface_name] = why
            return True
        return False

    for i in ifs:
        for address, tags in i["addresses"]:
            if address in held:
                add(i["name"], f"it holds {name}'s {held[address]} address {address}")
            elif TAG in tags:
                add(i["name"], f"its address {address} is tagged {TAG}")
            else:
                for net, p in tagged_prefixes:
                    if ipaddress.ip_address(address) in net:
                        add(i["name"], f"its address {address} is in the prefix {net}, "
                                       f"tagged {TAG}")
        if i["mgmt_only"]:
            add(i["name"], "NetBox marks it mgmt_only")
        if TAG in i["tags"]:
            add(i["name"], f"it is tagged {TAG}")
    for v in vlans or []:
        vid = _vid(v)
        if vid is not None and TAG in _tags(v):
            out_vlan.setdefault(vid, f"VLAN {vid} is tagged {TAG}")

    # Upward: a protected interface's parent, LAG and bridge carry what it carries; a protected
    # LAG's members carry it too. Then the VLAN of each protected VLAN interface, and every
    # physical port carrying a protected VLAN. Repeated until nothing is added.
    changed = True
    while changed:
        changed = False
        for child, why in list(out_if.items()):
            i = by_name.get(child)
            if i is None:
                continue
            for rel in ("parent", "lag", "bridge"):
                if i[rel] and add(i[rel], f"it is the {rel} of {child} ({why})"):
                    changed = True
            vid = vlan_of(i)
            if vid is not None and vid not in out_vlan:
                out_vlan[vid] = f"the VLAN of {child} ({why})"
                changed = True
        for i in ifs:
            if i["lag"] in out_if and add(i["name"], f"it is a member of the LAG {i['lag']} "
                                                     f"({out_if[i['lag']]})"):
                changed = True
            if i["type"] == "virtual" or i["name"] in out_if:
                continue
            carried = []
            if i["untagged"] in out_vlan:
                carried.append((i["untagged"], "untagged"))
            carried += [(t, "tagged") for t in i["tagged"] if t in out_vlan]
            if i["mode"] == "tagged-all" and out_vlan:
                carried.append((min(out_vlan), "tagged, as tagged-all carries every VLAN"))
            if carried:
                vid, how = carried[0]
                add(i["name"], f"it carries the protected VLAN {vid} ({how}; {out_vlan[vid]})")
                changed = True
    return {"interfaces": dict(sorted(out_if.items())),
            "vlans": {str(k): v for k, v in sorted(out_vlan.items())}}


def ports_refusal(device: str, takes: list, objects: dict) -> str:
    """Why a configuration whose OpenFlow instance takes the ports *takes* (``[{"port",
    "why"}]``) may not be rendered for *device*, or ``""``: each taken port that is a
    protected object (*objects*, `device_objects`' answer), with both reasons."""
    if not isinstance(objects, dict) or "interfaces" not in objects:
        return (f"{device}'s protected objects were not read (the values carry no "
                "protected.objects), so no OpenFlow port can be checked against them: nothing "
                "is rendered")
    hits = [f"{t['port']} ({t['why']}) is protected: {objects['interfaces'][t['port']]}"
            for t in takes or [] if t.get("port") in objects["interfaces"]]
    if hits:
        return (f"{device}'s OpenFlow instance would take a protected port, and no write may "
                f"take one (B, C2588, C2589): {'; '.join(hits)}. Nothing is rendered")
    return ""


# --------------------------------------------------------------------------- flow classes

def _alt(**fields) -> dict:
    return {k: v for k, v in fields.items() if v is not None}


def _eth(address: str) -> int:
    return ETH_IPV6 if ipaddress.ip_address(address).version == 6 else ETH_IPV4


def _family(address: str) -> str:
    return "ipv6" if ipaddress.ip_address(address).version == 6 else "ipv4"


def _service_alts(proto: int, l4: str, addresses: list, ports: list) -> list:
    out = []
    for a in addresses:
        fam, host = _family(a), f"{a}/{ipaddress.ip_address(a).max_prefixlen}"
        for port in ports:
            out.append(_alt(eth_type=_eth(a), ip_proto=proto, **{f"{fam}_dst": host,
                                                                  f"{l4}_dst": port}))
            out.append(_alt(eth_type=_eth(a), ip_proto=proto, **{f"{fam}_src": host,
                                                                  f"{l4}_src": port}))
    return out


def _service_addresses(svc: dict, devices: dict) -> list:
    own = [_host(a) for a in svc.get("ipaddresses") or [] if _host(a)]
    if own:
        return own
    parent = devices.get(_parent(svc)) or {}
    return [a for w, a in _management(parent) if w != "OOB"]


def _parent(svc: dict) -> str:
    """A Service's device (NetBox before 4.3: ``device``; after: ``parent``; the export: a
    name)."""
    return _name(svc.get("device") or svc.get("virtual_machine") or svc.get("parent"))


def _context_entry(entry, where: str) -> dict:
    """One ``mercury.protected_flows`` entry as a class, or raises Unreadable naming what."""
    if not isinstance(entry, dict):
        raise Unreadable(f"{where}: an entry is a mapping of name, match, invariant, reason "
                         f"and owners, not {type(entry).__name__}")
    name = str(entry.get("name") or "")
    if not SLUG.match(name):
        raise Unreadable(f"{where}: a class's name is a slug, not {name!r}")
    match = entry.get("match")
    if not isinstance(match, dict) or not match:
        raise Unreadable(f"{where}: {name}'s match is a mapping of {', '.join(CLASS_FIELDS)}")
    unknown = sorted(set(match) - set(CLASS_FIELDS))
    if unknown:
        raise Unreadable(f"{where}: {name}'s match names {', '.join(unknown)}, and a class is "
                         f"stated in {', '.join(CLASS_FIELDS)}")
    clean = {}
    for field, value in match.items():
        if field in ADDRESS_FIELDS:
            try:
                clean[field] = str(ipaddress.ip_network(str(value), strict=False))
            except ValueError:
                raise Unreadable(f"{where}: {name}'s {field} {value!r} is not an address or "
                                 "prefix") from None
        else:
            from modules.sdn.match_rules import number
            n = number(value)
            if n is None or n < 0:
                raise Unreadable(f"{where}: {name}'s {field} {value!r} is not a number")
            clean[field] = n
    invariant = str(entry.get("invariant") or "")
    kind = invariant.split()[0] if invariant.split() else ""
    if kind not in INVARIANTS or (kind == "must_reach" and len(invariant.split()) != 2) or (
            kind == "untouchable" and invariant != "untouchable"):
        raise Unreadable(f"{where}: {name}'s invariant is 'untouchable' or 'must_reach "
                         f"<service>', not {invariant!r}")
    owners = entry.get("owners") or []
    if not isinstance(owners, list) or not all(isinstance(o, str) and o for o in owners):
        raise Unreadable(f"{where}: {name}'s owners are a list of names")
    reason = str(entry.get("reason") or "")
    if not reason:
        raise Unreadable(f"{where}: {name} says no reason")
    return {"name": name, "invariant": invariant, "owners": sorted(owners), "match": [clean],
            "source": f"NetBox: {where}", "reason": reason}


def flow_classes(devices: list, prefixes: list, services: list) -> list:
    """The network's protected flow classes, from its NetBox records (REST shapes or the
    export's), sorted by name: ``[{"name", "invariant", "owners", "match": [alternative],
    "source", "reason"}]``. Raises Unreadable naming a config-context entry not of its
    shape."""
    by_name = {_name(d): d for d in devices or []}
    out = []
    control = []
    for svc in services or []:
        if str(svc.get("name") or "") != SERVICE:
            continue
        ports = sorted(int(p) for p in svc.get("ports") or [])
        addrs = _service_addresses(svc, by_name)
        parent = _parent(svc)
        control.append((parent, addrs, ports))
    if control:
        out.append({"name": "control-channel", "invariant": "untouchable", "owners": [],
                    "match": [a for _p, addrs, ports in control
                              for a in _service_alts(6, "tcp", addrs, ports)],
                    "source": "NetBox: the openflow Service on " + ", ".join(
                        f"{p} ({', '.join(a)} TCP {', '.join(map(str, ports))})"
                        for p, a, ports in control),
                    "reason": "every switch's channel to its controller"})
    nets = _networks(prefixes)
    mgmt, said = [], []
    for d in devices or []:
        for words, address in _management(d):
            ip = ipaddress.ip_address(address)
            holding = sorted((n for n, _p in nets if n.version == ip.version and ip in n),
                             key=lambda n: -n.prefixlen)
            net = holding[0] if holding else ipaddress.ip_network(address)
            if net not in mgmt:
                mgmt.append(net)
                said.append(f"{net} (holding {_name(d)}'s {words} address {address})" if holding
                            else f"{net} ({_name(d)}'s {words} address, in no recorded prefix)")
    if mgmt:
        alts = []
        for net in mgmt:
            fam = "ipv6" if net.version == 6 else "ipv4"
            alts.append(_alt(eth_type=ETH_IPV6 if net.version == 6 else ETH_IPV4,
                             **{f"{fam}_src": str(net), f"{fam}_dst": str(net)}))
            if net.version == 4:
                alts.append(_alt(eth_type=ETH_ARP, arp_spa=str(net), arp_tpa=str(net)))
        out.append({"name": "management", "invariant": "untouchable", "owners": [],
                    "match": alts, "source": "NetBox: the management prefixes " + "; ".join(said),
                    "reason": "the path Mercury reaches every device on"})
    for svc in services or []:
        if TAG not in _tags(svc):
            continue
        proto_word = _slug(svc.get("protocol")).lower()
        name = str(svc.get("name") or "").lower().replace(" ", "-")
        parent = _parent(svc)
        if proto_word not in PROTOCOLS or not SLUG.match(name):
            raise Unreadable(f"the Service {svc.get('name')!r} on {parent} is tagged {TAG}, and "
                             f"its protocol {proto_word or 'none'} or its name is not one a "
                             "class can be stated in (tcp, udp or sctp; a slug)")
        ports = sorted(int(p) for p in svc.get("ports") or [])
        addrs = _service_addresses(svc, by_name)
        out.append({"name": name, "invariant": f"must_reach {name}", "owners": [],
                    "match": _service_alts(PROTOCOLS[proto_word], proto_word, addrs, ports),
                    "source": f"NetBox: the Service {svc.get('name')} on {parent}, tagged {TAG}",
                    "reason": f"{svc.get('name')} ({proto_word} "
                              f"{', '.join(map(str, ports))} to {', '.join(addrs) or 'none'})"})
    seen = {}
    for d in devices or []:
        ctx = (d.get("config_context") or {})
        entries = (ctx.get(CONTEXT_KEY[0]) or {}).get(CONTEXT_KEY[1]) if isinstance(
            ctx.get(CONTEXT_KEY[0]), dict) else None
        if entries is None:
            continue
        where = f"{_name(d)}'s config context {'.'.join(CONTEXT_KEY)}"
        if not isinstance(entries, list):
            raise Unreadable(f"{where} is a list of classes, not {type(entries).__name__}")
        for n, entry in enumerate(entries):
            c = _context_entry(entry, f"{where}[{n}]")
            key = (c["name"], json.dumps(c["match"], sort_keys=True))
            if key not in seen:
                seen[key] = c
                out.append(c)
    return sorted(out, key=lambda c: (c["name"], c["source"]))


# --------------------------------------------------------------------------- overlap

def _meet(field: str, a, b) -> bool:
    if field in ADDRESS_FIELDS:
        try:
            x = ipaddress.ip_network(str(a).strip(), strict=False)
            y = ipaddress.ip_network(str(b).strip(), strict=False)
        except ValueError:
            return True                       # an unreadable value is not shown apart
        return x.version == y.version and x.overlaps(y)
    from modules.sdn.match_rules import number
    return number(a) is None or number(b) is None or number(a) == number(b)


def _inside(field: str, rule_value, class_value) -> bool:
    """Whether the rule's value is inside the class's (it names the class's own traffic)."""
    if field in ADDRESS_FIELDS:
        try:
            x = ipaddress.ip_network(str(rule_value).strip(), strict=False)
            y = ipaddress.ip_network(str(class_value).strip(), strict=False)
        except ValueError:
            return False
        return x.version == y.version and x.subnet_of(y)
    from modules.sdn.match_rules import number
    return number(rule_value) is not None and number(rule_value) == number(class_value)


def _implied(match: dict) -> dict:
    """*match* with the EtherType and IP protocol its fields imply (OpenFlow's prerequisites:
    an IPv4 field means 0x0800, a TCP port means protocol 6), so an unset prerequisite is not
    read as any."""
    from modules.sdn.match_rules import normalise
    m = normalise(dict(match or {}))
    if "eth_type" not in m:
        if any(k.startswith("ipv4_") for k in m):
            m["eth_type"] = ETH_IPV4
        elif any(k.startswith("ipv6_") for k in m):
            m["eth_type"] = ETH_IPV6
        elif any(k.startswith("arp_") for k in m):
            m["eth_type"] = ETH_ARP
    if "ip_proto" not in m:
        for word, number_ in PROTOCOLS.items():
            if any(k.startswith(word + "_") for k in m):
                m["ip_proto"] = number_
    return m


def overlap(match: dict, cls: dict) -> list:
    """How *match* (a rule's) meets class *cls*: the alternative it meets and each of its fields
    with both values, ``[words]``; ``[]`` when it meets none."""
    m = _implied(match)
    for alt in cls.get("match") or []:
        if all(_meet(f, m[f], v) for f, v in alt.items() if f in m):
            return [f"{f} {m[f]} meets the class's {v}" if f in m
                    else f"{f} unset in the rule (so every {f}) meets the class's {v}"
                    for f, v in sorted(alt.items())]
    return []


def names_class(match: dict, cls: dict) -> bool:
    """Whether *match* names *cls*'s own traffic: it meets an alternative and one of its address
    or port fields is inside that alternative's (never by breadth alone)."""
    m = _implied(match)
    for alt in cls.get("match") or []:
        if all(_meet(f, m[f], v) for f, v in alt.items() if f in m) and any(
                f in m and _inside(f, m[f], v) for f, v in alt.items()
                if f in ADDRESS_FIELDS + PORT_FIELDS):
            return True
    return False


# --------------------------------------------------------------------------- the set

def derive(body: dict) -> dict:
    """The protected set of an export's *body* (or NetBox's records in its kinds): ``{"objects":
    {device: device_objects}, "classes", "switches": {dpid: device}, "ports": {device: {number:
    interface}}}``. Raises Unreadable."""
    devices = list(body.get("devices") or [])
    interfaces = list(body.get("interfaces") or [])
    vlans, prefixes = list(body.get("vlans") or []), list(body.get("prefixes") or [])
    by_device: dict = {}
    for i in interfaces:
        by_device.setdefault(_name(i.get("device")) or str(i.get("device") or ""), []).append(i)
    objects, switches, ports = {}, {}, {}
    for d in devices:
        name = _name(d)
        site = _slug(d.get("site"))
        local_vlans = [v for v in vlans if not _slug(v.get("site")) or _slug(v.get("site")) == site]
        objects[name] = device_objects(d, by_device.get(name, []), local_vlans, prefixes)
        dpid = str((d.get("custom_fields") or {}).get("openflow_datapath_id") or "")
        if re.fullmatch(r"[0-9a-fA-F]{16}", dpid) and int(dpid, 16):
            switches[str(int(dpid, 16))] = name
        numbered = {}
        for i in by_device.get(name, []):
            n = (i.get("custom_fields") or {}).get("openflow_port")
            if isinstance(n, int) and not isinstance(n, bool) or (isinstance(n, str)
                                                                    and n.isdigit()):
                numbered[str(int(n))] = _name(i)
        ports[name] = numbered
    return {"objects": objects, "switches": switches, "ports": ports,
            "classes": flow_classes(devices, prefixes, body.get("services") or [])}


def _digest(pset: dict) -> str:
    return hashlib.sha256(json.dumps({k: pset.get(k) for k in ("objects", "classes", "switches",
                                                                "ports")},
                                     sort_keys=True).encode()).hexdigest()


def for_network(network: str) -> dict:
    """*network*'s protected set: ``{"state": "ok"|"none"|"unreadable", "source", "sha256",
    "objects", "classes", "switches", "ports", "error"}``. From the committed NSOT export,
    else NetBox read now; ``none`` for a network whose devices are not NetBox's (said in
    ``source``); ``unreadable`` with ``error`` naming why."""
    from modules.inventory import source_config
    from modules.nsot import export as X

    out = {"state": "unreadable", "source": "", "sha256": "", "objects": {}, "classes": [],
           "switches": {}, "ports": {}, "error": ""}
    try:
        source = (source_config.load(network) or {}).get("source") or "local"
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        out["error"] = f"{network}'s inventory source could not be read: {exc}"[:300]
        return out
    if source != source_config.SOURCE_NETBOX:
        out.update(state="none", source=(
            f"{network}'s devices come from {source!r}, not NetBox, so no protected objects "
            "or NetBox classes are derived: only the controller connection's control channel "
            "is guarded (with its devices from NetBox, the management path and the protected "
            "services are too)"))
        return out
    got = X.read(network)
    if got["ok"]:
        doc, out["source"] = got["export"], f"the committed NSOT export {got['sha256'][:12]}"
    elif got.get("absent"):
        built = X.build(network)
        if not built["ok"]:
            out["error"] = (f"{network} has no committed NSOT export and NetBox could not be "
                            f"read now ({built['error']}), so the protected set is unknown")
            return out
        doc = X.parse(built["bytes"])
        out["source"] = f"NetBox read now ({doc['sha256'][:12]}; no export is committed)"
    else:
        out["error"] = f"{network}'s committed NSOT export cannot be used: {got['error']}"
        return out
    try:
        out.update(derive(doc.get("body") or {}))
    except Unreadable as exc:
        out["error"] = f"{network}'s protected set is not of its shape: {exc}"
        return out
    out["state"], out["sha256"] = "ok", str(doc.get("sha256") or "")
    return out


# --------------------------------------------------------------------------- flows

def _vlan_number(value):
    from modules.sdn.match_rules import number
    n = number(value)
    if n is None:
        return None
    return n & 0x0FFF if n & OFPVID_PRESENT else n


def _object_hits(pset: dict, dpid, flow: dict) -> list:
    """The protected objects *flow* (on switch *dpid*) names: its in_port and OUTPUT ports by
    NetBox's ``openflow_port``, and a VLAN it matches or sets."""
    device = pset.get("switches", {}).get(str(dpid))
    hits = []
    if device:
        objs = pset["objects"].get(device) or {"interfaces": {}, "vlans": {}}
        numbers = pset.get("ports", {}).get(device) or {}
        named = [("in_port", (flow.get("match") or {}).get("in_port"))]
        named += [("an OUTPUT action", a.get("port")) for a in flow.get("actions") or []
                  if isinstance(a, dict) and a.get("type") == "OUTPUT"]
        for what, port in named:
            iface = numbers.get(str(port)) if port is not None else None
            if iface and iface in objs["interfaces"]:
                hits.append(f"{what} {port} is {device}'s {iface}, protected: "
                            f"{objs['interfaces'][iface]}")
        vlan_sets = {str(k): v for k, v in objs["vlans"].items()}
    else:
        vlan_sets = {}
        for dev, objs in sorted(pset.get("objects", {}).items()):
            for vid, why in objs["vlans"].items():
                vlan_sets.setdefault(str(vid), f"{why}, on {dev}")
    vids = [("vlan_vid", (flow.get("match") or {}).get("vlan_vid"))]
    vids += [("a SET_FIELD vlan_vid", a.get("value")) for a in flow.get("actions") or []
             if isinstance(a, dict) and a.get("type") == "SET_FIELD"
             and a.get("field") == "vlan_vid"]
    for what, value in vids:
        vid = _vlan_number(value) if value is not None else None
        if vid is not None and str(vid) in vlan_sets:
            hits.append(f"{what} {vid} is the protected VLAN {vid}: {vlan_sets[str(vid)]}")
    return hits


def flow_refusal(pset: dict, changes: list, dpid, connection: dict, *, writer: str) -> str:
    """Why *changes* (`flow_ops`' ask's) on switch *dpid* may not run for *writer* (``person``,
    ``response``, ``reapply``, or an owner's name such as ``app:dns-blacklist``), or ``""``:
    the controller connection's control channel (`control_plane`, C2022), then the NetBox
    classes *writer* does not own, then the protected objects a flow names. An unreadable
    *pset* refuses every change, naming why."""
    from modules.sdn import control_plane

    refused = control_plane.refusal(changes, connection, who=writer)
    if refused:
        return refused
    if pset.get("state") == "unreadable":
        return (f"the protected set could not be read ({pset.get('error')}), so no flow can be "
                "checked against it: nothing is sent")
    for n, change in enumerate(changes or []):
        do = change.get("do")
        flows = []
        if do == "add_flow":
            flows = [("adds", change.get("flow") or {}, False)]
        elif do == "edit_flow":
            # The edited flow is Mercury's own, asked when it was added; what it becomes is new.
            flows = [("edits to", change.get("flow") or {}, False)]
        elif do == "remove_flow":
            flows = [("removes", change.get("target") or {}, True)]
        for verb, flow, removal in flows:
            match = flow.get("match") or {}
            for cls in pset.get("classes") or []:
                if writer in (cls.get("owners") or []):
                    continue
                if removal:
                    if not names_class(match, cls):
                        continue
                    met = overlap(match, cls)
                else:
                    met = overlap(match, cls)
                    if not met:
                        continue
                owners = ", ".join(cls.get("owners") or []) or "none"
                return (f"change {n + 1} {verb} a flow whose match meets the protected class "
                        f"{cls['name']} ({cls['invariant']}; {cls['source']}): "
                        f"{'; '.join(met)}. Its owners are {owners}, and this write is "
                        f"{writer}'s: nothing is sent (B, C2379)")
            if not removal:
                hits = _object_hits(pset, dpid, flow)
                if hits:
                    return (f"change {n + 1} {verb} a flow naming a protected object: "
                            f"{'; '.join(hits)}. No write may: nothing is sent (B, C2379)")
    return ""


def switch_note(pset: dict, dpid) -> str:
    """What the guard could not compare on switch *dpid*, said in the preview, or ``""``."""
    if pset.get("state") == "none":
        return pset.get("source", "")
    if pset.get("state") == "ok" and str(dpid) not in (pset.get("switches") or {}):
        return (f"switch {dpid} is no device NetBox names by its openflow_datapath_id, so its "
                "ports are not compared with the protected objects (its VLANs are, with every "
                "device's)")
    return ""
