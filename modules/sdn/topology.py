"""Topology from an SDN controller (PHASE8_PLAN 17.1 S14, C1910): OpenFlow switches run no LLDP
of their own, so their links, and the hosts behind them, come from the controller that
discovered them.

**One source, one owner.** The controller's topology is read by the SDN reader
(`readers/sdn_controllers.py`, per connection, through the driver's `topology()`); this module
only READS that stored value (`stored`) and shapes it, never asking a controller itself. Its
three users each take their part:
- the Topology reader (`readers/topology_graph.network_graph`, *sdn*) adds the switches as
  nodes and the links to the physical layer (`layer`), and joins a device's LLDP neighbour
  whose chassis id is a switch's DPID to that switch's port (`hybrid_links`);
- the network model's coverage header lists the layer (`network_model.coverage`'s
  ``controller``), from the Topology read's record of it (`said`);
- the endpoint layer takes the hosts the controller learned (`endpoint_hosts`).

**Switches are keyed by DPID** (`switch_key`, ``of:<16 hex digits>``), never by a name: an
OpenFlow switch called edge1 and an IOS switch called edge1 are two devices. A switch is "discovered
via controller (<connection>)", its label the name it reports (its OpenFlow description's
``dp_desc``, read by the SDN reader) when it reports one. **A link names its source**:
``controller (<connection>)``, or, for a hybrid link, the LLDP of the device that reported it
as well; one link, both sources.

**Never let a wrong thing look like a working thing.** A controller that cannot be read is
said as "couldn't read: <why>", its switches and links kept as last read with that read's
time, never dropped and never drawn as now. An empty link list between two or more switches is
said with what it may mean (the driver's `links_note`), never as a fabric with no cables. A
host's "last seen" is when the controller last LISTED it, with the driver's note on what a
listing means (`hosts_note`). No controller is named here: what is particular to one (its
notes, its LLDP chassis id's prefix) is its driver's declaration (`drivers/`).
"""

import calendar
import logging
import re
import time

log = logging.getLogger(__name__)

#: A switch's node key on the map and in the network model: its DPID, never its name.
SWITCH_PREFIX = "of:"
#: The class a controller-managed switch is drawn as (`topology_layout.node_class`).
SWITCH_ROLE = "openflow switch"
#: The map's keys for a controller (by its connection's name) and a host it learned (by MAC):
#: drawn beside the fabric, never part of an analysis (`overlay`).
CONTROLLER_PREFIX = "ctl:"
HOST_PREFIX = "host:"
_HEX_PORT = re.compile(r"^(?:0x)?([0-9a-f]{2})[ :.-]?([0-9a-f]{2})[ :.-]?([0-9a-f]{2})"
                       r"[ :.-]?([0-9a-f]{2})$", re.I)
#: Above this many hosts in a network, the map does not draw them (they stay in the endpoint
#: layer): a host per edge port of a large fabric would bury its switches.
HOSTS_DRAWN_UP_TO = 64


def switch_key(dpid) -> str:
    """``of:<16 hex>`` for a datapath id (an int or the driver's hex)."""
    from modules.sdn.drivers.base import dpid_hex, parse_dpid
    return SWITCH_PREFIX + dpid_hex(parse_dpid(dpid))


def is_switch(name: str) -> bool:
    return str(name or "").startswith(SWITCH_PREFIX)


def short(key: str) -> str:
    """A switch key as a person reads it on the map: ``of:…0001`` (its last four digits)."""
    return f"{SWITCH_PREFIX}…{key[-4:]}" if is_switch(key) else key


def port_words(port_no) -> str:
    """How a switch port is named on the map: ``port 3`` (OpenFlow's number)."""
    return f"port {port_no}"


def chassis_prefixes() -> tuple:
    """Each built driver's LLDP chassis id prefix (`ControllerDriver.lldp_chassis_prefix`)."""
    from modules.sdn.drivers import DRIVERS
    return tuple(sorted({cls.lldp_chassis_prefix for cls in DRIVERS.values()
                         if cls.status == "built" and cls.lldp_chassis_prefix}))


def chassis_dpid(text, prefixes=None):
    """The DPID a neighbour's LLDP chassis id names: a driver's declared prefix and the DPID in
    sixteen hex digits (*prefixes*, every built driver's by default), or None: a MAC or a name
    is never read as one."""
    t = str(text or "").strip()
    for prefix in (chassis_prefixes() if prefixes is None else prefixes):
        if t.lower().startswith(prefix.lower()):
            rest = t[len(prefix):]
            if re.fullmatch(r"[0-9a-fA-F]{16}", rest):
                return int(rest, 16)
    return None


def lldp_port_no(text):
    """The switch port a neighbour's LLDP port id names: a controller's link discovery packs
    the port number in four bytes (subtype port component), which a device's SNMP table may
    give raw (four characters), as its four bytes in hex (``00000003``, ``00 00 00 03``, ``0x00000003``:
    eight hex digits are always read as the four bytes, never as a decimal) or as a decimal of
    up to seven digits; None when it is none of those."""
    raw = str(text if text is not None else "")
    if len(raw) == 4 and any(ord(c) < 32 for c in raw) and all(ord(c) < 256 for c in raw):
        return int.from_bytes(raw.encode("latin-1"), "big")
    t = raw.strip()
    m = _HEX_PORT.match(t)
    if m:
        return int("".join(m.groups()), 16)
    if t.isdigit() and len(t) < 8:
        return int(t)
    return None


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _epoch(text: str):
    try:
        return calendar.timegm(time.strptime(text, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        return None


# ───────────────────────────────────────────────────────────────────────────── the stored read

def stored(network: str, now: float = None, cached=None) -> dict:
    """The SDN reader's stored topology for *network*: ``{"state", "why", "controllers"}``.
    *state* is ``none`` (the network has no controller connection), ``read`` (each controller
    says its own state) or ``could not read`` (the store, with why). Each controller is
    ``{"name", "label", "state", "why", "read_at", "switches", "links", "hosts", "hosts_note",
    "names"}``: *state* read, could not read (its last good read kept, with *read_at*) or
    not_declared; *names* each DPID's reported name. *cached* is the reader's answer in
    `reader_job.read_cached_for`'s shape (a test's), read from the store when None."""
    from modules import reader_job
    from modules.readers import sdn_controllers as R

    now = time.time() if now is None else now
    got = cached if cached is not None else reader_job.read_cached_for(R.READER_NAME, network)
    state = got.get("state")
    if state in ("not_applicable", "not_configured"):
        return {"state": "none", "why": got.get("why") or "no controller connection",
                "controllers": []}
    if state == "unreadable":
        return {"state": "could not read", "why": f"the SDN reader's store: {got.get('why')}",
                "controllers": []}
    good = ((got.get("doc") or {}).get("last_good") or {})
    value = good.get("value") or {}
    if not good:
        return {"state": "could not read", "controllers": [],
                "why": "the SDN reader has not read this network yet"}
    if value.get("state") in ("none", "not_applicable", "not_configured"):
        return {"state": "none", "why": "this network has no controller connection",
                "controllers": []}
    at = good.get("value_at") or value.get("read_at") or ""
    promise = reader_job.page_promise(R.READER)
    stamp = _epoch(at)
    late = ""
    if stamp is None:
        late = f"the SDN reader's stored read has no time ({at!r})"
    elif now - stamp > promise:
        late = (f"the SDN reader's last read, at {at}, is older than its promise of "
                f"{promise} s")
    out = []
    for c in value.get("controllers") or []:
        topo = c.get("topology") or {}
        names = {}
        for sw in c.get("switches") or []:
            if sw.get("name") and sw.get("dpid") is not None:
                names[int(sw["dpid"])] = str(sw["name"])
        entry = {"name": c.get("name", ""), "label": c.get("label", ""),
                 "read_at": topo.get("read_at") or "",
                 "switches": topo.get("switches") or [], "links": topo.get("links") or [],
                 "hosts": topo.get("hosts") or [], "hosts_note": topo.get("hosts_note", ""),
                 "links_note": topo.get("links_note", ""), "names": names}
        if c.get("state") == "not_built" or not topo or topo.get("state") == "not_declared":
            entry.update(state="not_declared", why=topo.get("error") or c.get("error") or
                         "the driver does not declare read_topology")
        elif topo.get("state") != "read":
            entry.update(state="could not read", why=topo.get("error") or "no answer")
        elif late:
            entry.update(state="could not read", why=late)
        else:
            entry.update(state="read", why="")
        out.append(entry)
    return {"state": "read", "why": "", "controllers": out}


# ───────────────────────────────────────────────────────────────────────────── the layer

def _age_words(at: str, now: float) -> str:
    stamp = _epoch(at)
    if stamp is None:
        return "never read"
    from modules.endpoints import _ago
    return f"as last read at {at} ({_ago(now - stamp)})"


def said(controllers: list) -> list:
    """What each controller contributes, for the coverage header: ``[{"name", "state",
    "source", "read_at", "switches", "links", "hosts", "why"}]`` (counts; `words` says it)."""
    out = []
    for c in controllers or []:
        out.append({"name": c["name"], "state": c["state"],
                    "source": f"controller ({c['name']})", "read_at": c.get("read_at", ""),
                    "switches": len(c.get("switches") or []),
                    "links": len({_pair(l) for l in c.get("links") or []}),
                    "hosts": len(c.get("hosts") or []), "why": c.get("why", ""),
                    "links_note": c.get("links_note", "")})
    return out


def _n(count: int, word: str, plural: str = "") -> str:
    return f"{count} {word if count == 1 else (plural or word + 's')}"


def words(entry: dict, now: float = None) -> str:
    """One controller's line in a coverage header: "controller (c1) · read <time> · 2
    switches, 1 link, 4 hosts", or "controller (c1): couldn't read: <why>; its switches as
    last read at <time> (<age>): ..."; an empty link list between two or more switches said
    with what it may mean."""
    now = time.time() if now is None else now
    counts = (f"{_n(entry['switches'], 'switch', 'switches')}, {_n(entry['links'], 'link')}, "
              f"{_n(entry['hosts'], 'host')}")
    source = entry["source"]
    if entry["state"] == "read":
        out = f"{source} · read {entry['read_at']} · {counts}"
        if entry["switches"] > 1 and not entry["links"]:
            out += (f" · no link reported between its {entry['switches']} switches: "
                    + (entry.get("links_note") or "none cabled, or the controller discovers "
                                                  "none"))
        return out
    if entry["state"] == "not_declared":
        return f"{source}: not read: {entry['why']}"
    out = f"{source}: couldn't read: {entry['why']}"
    if entry.get("read_at"):
        out += f"; its switches {_age_words(entry['read_at'], now)}: {counts}"
    return out


def _pair(link: dict) -> tuple:
    a = (int(link["src"]["dpid"]), link["src"]["port_no"])
    b = (int(link["dst"]["dpid"]), link["dst"]["port_no"])
    return tuple(sorted((a, b), key=str))


def layer(controllers: list) -> dict:
    """The controllers' switches as nodes and their links as physical links:
    ``{"nodes": {key: node}, "links": [link], "hosts": [host]}``. A node is ``{"managed":
    False, "role", "sdn": {"controller", "dpid", "dpid_hex", "label", "ports", "read_at",
    "state", "why"}}``; a link ``{"a", "port_a", "b", "port_b", "kind": "controller",
    "sources", "state", "directions", "ends_detail", "read_at"}`` with ``a < b``, the one
    cable both directions report; *state* up when its controller was read now, else unknown
    (kept from the last read). A host is the controller's, with its switch's key."""
    nodes, links, hosts = {}, {}, []
    for c in controllers or []:
        if c["state"] == "not_declared":
            continue
        now_read = c["state"] == "read"
        source = f"controller ({c['name']})"
        ports = {}
        for sw in c.get("switches") or []:
            key = switch_key(sw["dpid"])
            for p in sw.get("ports") or []:
                ports[(key, p["port_no"])] = p
            nodes[key] = {"managed": False, "role": SWITCH_ROLE, "polled": False,
                          "answering": now_read, "lldp_read": False,
                          "sdn": {"controller": c["name"], "dpid": int(sw["dpid"]),
                                  "dpid_hex": sw.get("dpid_hex") or key[3:],
                                  "label": (c.get("names") or {}).get(int(sw["dpid"]), ""),
                                  "ports": len(sw.get("ports") or []),
                                  "read_at": c.get("read_at", ""), "state": c["state"],
                                  "why": c.get("why", "")}}
        for l in c.get("links") or []:
            ka, kb = switch_key(l["src"]["dpid"]), switch_key(l["dst"]["dpid"])
            ends = sorted([(ka, l["src"]["port_no"], l["src"]), (kb, l["dst"]["port_no"],
                                                                 l["dst"])],
                          key=lambda e: (e[0], str(e[1])))
            ident = (ends[0][0], ends[0][1], ends[1][0], ends[1][1])
            got = links.get(ident)
            if got is None:
                links[ident] = got = {
                    "a": ends[0][0], "port_a": port_words(ends[0][1]),
                    "b": ends[1][0], "port_b": port_words(ends[1][1]),
                    "kind": "controller", "sources": [source],
                    "state": "up" if now_read else "unknown", "directions": 0,
                    "reported_by": [], "read_at": c.get("read_at", ""),
                    "ends_detail": {ends[0][0]: _port_detail(ends[0][2]),
                                    ends[1][0]: _port_detail(ends[1][2])}}
            got["directions"] += 1
        for h in c.get("hosts") or []:
            hosts.append(dict(h, switch=switch_key(h["dpid"]), controller=c["name"],
                              read_at=c.get("read_at", ""), state=c["state"]))
    return {"nodes": nodes, "links": [links[k] for k in sorted(links, key=str)],
            "hosts": hosts}


def _port_detail(port: dict) -> dict:
    return {"port_no": port.get("port_no"), "name": port.get("name", ""),
            "hw_addr": port.get("hw_addr", "")}


# ───────────────────────────────────────────────────────────────────────────── hybrid links

def lldp_chassis(results: dict) -> list:
    """Each LLDP neighbour a device reports with its chassis id: ``[{"device", "port",
    "chassis", "port_id"}]`` from the Topology reader's series (`lldpRemChassisId`, its
    ``lldpRemPortId`` by the same index, the local port's name by ``lldpLocPortDesc``)."""
    out = []
    for dev, metrics in (results or {}).items():
        desc = {}
        for metric in ("lldpLocPortDesc", "lldpRemEntry"):
            for row in metrics.get(metric) or []:
                m = row.get("metric") or {}
                if m.get("lldpLocPortNum") and m.get("lldpLocPortDesc"):
                    desc.setdefault(m["lldpLocPortNum"], m["lldpLocPortDesc"])
        port_ids = {}
        for row in metrics.get("lldpRemPortId") or []:
            m = row.get("metric") or {}
            port_ids[(m.get("lldpLocPortNum"), m.get("lldpRemIndex"))] = m.get("lldpRemPortId")
        for row in metrics.get("lldpRemChassisId") or []:
            m = row.get("metric") or {}
            idx = (m.get("lldpLocPortNum"), m.get("lldpRemIndex"))
            out.append({"device": dev,
                        "port": m.get("lldpLocPortDesc") or desc.get(m.get("lldpLocPortNum"), ""),
                        "chassis": m.get("lldpRemChassisId", ""),
                        "port_id": port_ids.get(idx)})
    return out


def hybrid_links(chassis_rows: list, managed: set, sdn_nodes: dict) -> tuple:
    """``(links, nodes)``: each managed device's LLDP neighbour whose chassis id is a DPID
    (`chassis_dpid`) joined to that switch: ONE link, its sources both the device's LLDP and,
    where the controller knows the switch, the controller; the switch's port from the
    neighbour's port id (`lldp_port_no`), "port ?" when it cannot be read. A DPID no
    controller knows is a node of its own, seen only by that device's LLDP."""
    links, nodes = [], {}
    for row in chassis_rows or []:
        if row["device"] not in managed:
            continue
        dpid = chassis_dpid(row.get("chassis"))
        if dpid is None:
            continue
        key = switch_key(dpid)
        port_no = lldp_port_no(row.get("port_id"))
        known = sdn_nodes.get(key)
        sources = [f"LLDP ({row['device']})"]
        if known:
            sources.append(f"controller ({known['sdn']['controller']})")
        else:
            nodes[key] = {"managed": False, "role": SWITCH_ROLE, "polled": False,
                          "answering": False, "lldp_read": False, "outside": True,
                          "seen_by": [row["device"]],
                          "sdn": {"controller": "", "dpid": dpid, "dpid_hex": key[3:],
                                  "label": "", "ports": 0, "read_at": "",
                                  "state": "unknown",
                                  "why": f"named only by {row['device']}'s LLDP; no "
                                         "controller of this network reports it"}}
        port = port_words(port_no) if port_no is not None else "port ?"
        (a, pa), (b, pb) = sorted([(row["device"], row.get("port") or ""), (key, port)])
        links.append({"a": a, "port_a": pa, "b": b, "port_b": pb, "kind": "hybrid",
                      "sources": sources, "reported_by": [row["device"]],
                      "chassis": row.get("chassis", ""), "lldp_port_id_read": port_no is not None,
                      "directions": 1})
    return links, nodes


# ───────────────────────────────────────────────────────────────────────────── endpoints

def endpoint_hosts(controllers: list) -> list:
    """The hosts the controllers learned, as the endpoint layer takes them: ``[{"mac",
    "addresses", "device", "interface", "last_seen", "source", "note"}]``. *device* is the
    switch's key, *interface* its port as the map names it (``port 2``, its name beside),
    *last_seen* when the controller last listed it (its read's time). A host on a port that
    is a link between switches locates nothing (the controller learns only on edge ports, but
    a port's role can change since)."""
    out = []
    for c in controllers or []:
        if c["state"] == "not_declared":
            continue
        inner = set()
        for l in c.get("links") or []:
            inner.add((int(l["src"]["dpid"]), l["src"]["port_no"]))
            inner.add((int(l["dst"]["dpid"]), l["dst"]["port_no"]))
        for h in c.get("hosts") or []:
            if (int(h["dpid"]), h["port_no"]) in inner:
                continue
            out.append({"mac": h["mac"], "addresses": list(h.get("ipv4") or [])
                        + list(h.get("ipv6") or []),
                        "device": switch_key(h["dpid"]), "interface": port_words(h["port_no"]),
                        "port_name": h.get("port_name", ""),
                        "last_seen": c.get("read_at", ""),
                        "source": f"controller ({c['name']})'s host table",
                        "note": c.get("hosts_note", "")})
    return out
