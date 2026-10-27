"""The network context model (PHASE8_PLAN 15.15; what it sends is the topology class, 15.11): a
network compiled from its inventory and its committed intent into nodes, links with their
computed subnets, and the adjacencies intent implies, so a model call can be given the part of
the network around an alert or a question, with stable ids it must cite. Deterministic and
read-only: no model is asked to build it, and nothing here writes.

**Its sources.**
- *The inventory* (`modules.device.load_saved_devices`, a NetBox list's served from memory, a
  local list's from its CSV): each device's name, NetBox id, role, site, platform and
  management address. Only those fields are copied: a row's credentials, still encrypted, are
  never read, and no free text (a NetBox description or comment) is carried.
- *Committed intent* (`neighbours.committed_intents`: the whole fleet in two git reads, a leased
  management address given to its interface): each interface's addresses, VRF, VLANs and
  shutdown, and OSPF, OSPFv3 and BGP membership (router id, areas, passive interfaces, AS and
  peers). What intent MEANS for the topology, never an intent document or a configuration
  line, and never a description.
- *The committed manifest* (`leased_address.committed_manifest`, one git read): each device's
  NetBox id, so its id is stable across a rename.
- *NetBox's cables* (C1863), for a network whose inventory is NetBox: each documented cable
  between two interfaces of devices the model knows (by their NetBox ids) is a link, read
  through the NetBox integration client (`netbox_cables`: one paged read of ``dcim/cables``,
  at most `CABLE_PAGES` pages, kept in this process's memory for the network's own inventory
  refresh interval, read only by `model_for`). A cable whose two devices share an intent
  subnet joins that subnet's link, which then says it came from both; one that joins none is
  its own link, ``link:netbox-cable:<NetBox cable id>``. Every link says its ``source``
  (``intent``, ``netbox_cable`` or ``both``). A cable whose ends are not two interfaces of
  devices the model knows (a console port, an end in another network, a cable with no ends)
  is counted, by why, and not drawn. A network on a local CSV inventory has no cables, and the
  model says so; a read that fails is said, never raised, and intent's links stand alone.
- **Observed**, never compiled into the model: the Topology reader's stored read
  (`topology-graph`: LLDP's links and the routing tables, the whole fleet per read, from
  Prometheus), each observed item with the read's time. **It is CAPTURED, never read when a
  subgraph is drawn** (C1712, the operator's ruling of 2026-10-25): `capture` reads it once,
  when an alert's evidence pack is built, keeps the part around the subject (the items
  touching any device within `CAPTURE_HOPS`), and the pack keeps it, "as of" the alert's time;
  `context_for` overlays the overlay it is GIVEN and reads no observed state itself, so Explain
  of a past alert never describes the network now. A read that cannot be used (absent,
  unreadable, older than its promise, later than the time it is captured for) is said as
  "could not read" with why, on every item it would have overlaid; never left out. **The
  controller layer** (PHASE8_PLAN 17.1 S14) comes in the same read: an SDN controller's links
  are cables naming their ``sources`` (``controller (<connection>)``, and a device's LLDP for a
  hybrid link), its switches ``of:<DPID>`` ends, and what each controller gave (read, or
  couldn't read with why, its switches as last read) is the coverage header's ``controller``
  layer (`controller_coverage`).

**What it reuses.** The adjacencies are the Neighbours tab's own rules (`neighbours.ospf_links`,
`ospfv3_links`, `bgp_peers`, `router_id`, `addresses`), each device's links computed ONCE and
grouped by subnet, so the fleet costs one pass rather than `neighbours.expected`'s pass per
device; the OSPF area is Topology's (`topology_graph._area`). The expected islands
(`topology_expected`) are declarations about the map, not links, and are not part of it.

**Its version** is the committed intent's tree (`HEAD:host_vars`) and manifest blob, and a
digest of the inventory's copied fields, which is NetBox's change as it reaches this
installation: the inventory reads no changelog id or change time (C1710); for a network on
NetBox, a digest of its cables' drawn fields joins them (C1863), so a recabling moves it once
it is read. The model is rebuilt only when one of them moves: a golden committed alone moves
HEAD and not the intent's tree, so it rebuilds nothing.

**Where it is kept:** in this process's memory (`_CACHE`), one model per network, replaced
whole under a lock; never on disk, so a read writes nothing (tests/test_reads_write_nothing.py)
and a second worker process builds its own. Asking costs one git call and the inventory's
digest; a build, two more git calls and one pass over the fleet.

**Its ids** (`ID_WORDS`), deterministic and stable while the network is: ``dev:<NetBox id>``
(``dev:u<8 hex>`` from a local device's manifest identity, ``dev:@<name>`` for a device no
manifest records); ``link:<subnet>`` (``link:<vrf>/<subnet>`` inside a VRF);
``link:netbox-cable:<id>`` for a cable NetBox documents that joins no intent subnet;
``adj:<protocol>:<a>~<b>:<subnet or address family>``; ``cable:<a>/<port>~<b>/<port>`` for an
observed LLDP link; ``ext:<address or name>`` for a peer outside management.
"""

import calendar
import hashlib
import ipaddress
import itertools
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

SCHEMA = 1
#: A segment of more than this many devices (a shared management subnet) is listed with its
#: count and not walked through: one hop across it would reach every device on it. Sixteen is
#: over the largest segment in a lab's intent (the core VLAN's six) and keeps a subgraph of one
#: hop to a few dozen devices.
MAX_SEGMENT = 16
#: The most hops a subgraph is asked for: three hops of a 900-device fleet is already most of a
#: site, and a prompt is bounded (profiles.TASKS).
MAX_HOPS = 3
#: The summary names every device (id, name, role) up to this many; above it, only the counts,
#: and it says so.
SUMMARY_DEVICES = 50
#: The observed overlay's reader (modules/readers/topology_graph.py).
OBSERVED_READER = "topology-graph"
#: How far a capture reaches (C1714's two hops for the health figures; the topology DETAIL
#: Explain sends stays at its own one hop).
CAPTURE_HOPS = 2
#: A stored read later than the time it is captured for by more than this is not of that
#: time (a replay of a past alert reading today's value): the clocks of one host, so a minute
#: of slack covers a read stored in the same second the alert was found.
LATER_SLACK_SECONDS = 60
ROUTING = ("ospf", "ospfv3", "bgp")
#: Mercury's own host on the observed map (topology_graph.MANAGER): an end, never a way through.
MANAGER_ID = "mercury"
#: NetBox's cables (C1863): one read of ``dcim/cables`` is at most this many pages of this many
#: cables; past them the read says it is truncated. The lab's NetBox held 17 cables, one page,
#: read in 0.37 s (2026-10-27); 5000 cables is several sites of a large fleet.
CABLE_PAGE = 1000
CABLE_PAGES = 5
#: A link's source (C1863), and a cable left out of the links, by why.
LINK_SOURCES = ("intent", "netbox_cable", "both")
NOT_DRAWN_WORDS = {
    "not_two_interfaces": "not between two interfaces (a console or power port, a circuit, "
                          "or a side with no end or several)",
    "unknown_device": "an end is on a device this network's model does not know",
    "one_device": "both ends are on one device",
}

ID_WORDS = (
    "dev:<NetBox id> is a managed device (dev:u<hex> a local one, dev:@<name> one no manifest "
    "records); ext:<address or name> a peer outside management; mercury is this tool's own "
    "host, where it attaches",
    "link:<subnet> is a subnet two or more devices' interfaces share by intent "
    "(link:<vrf>/<subnet> inside a VRF); link:netbox-cable:<id> a cable NetBox documents "
    "between two devices that no intent subnet joins; a link's source says which: intent, "
    "netbox_cable or both",
    "adj:<protocol>:<a>~<b>:<subnet or ipv4/ipv6> is an adjacency between two ends",
    "cable:<a>/<port>~<b>/<port> is a physical link LLDP reports (or, naming its sources, "
    "one an SDN controller reports, or both)",
    "of:<16 hex digits> is an OpenFlow switch discovered via its controller, keyed by its "
    "DPID",
)

_CACHE: dict = {}
#: NetBox's cables, by network: ``{"at": monotonic time read, "doc": netbox_cables' answer}``.
_CABLES: dict = {}
_LOCK = threading.Lock()
#: Builds run in this process, by network (tests count them: a rebuild only when the version
#: moves).
BUILDS: dict = {}


def _now() -> float:
    """The clock the observed overlay is judged against (one seam, so a test fixes it)."""
    return time.time()


# ----------------------------------------------------------------------------- the version

def _rows(inventory) -> list:
    out = []
    for d in inventory or []:
        name = (d.get("hostname") or "").strip()
        if not name:
            continue
        out.append({"name": name, "address": str(d.get("ip") or ""),
                    "role": str(d.get("role") or ""),
                    "platform": str(d.get("_platform") or d.get("platform")
                                    or d.get("device_type") or ""),
                    "site": str(d.get("_site") or d.get("site") or ""),
                    "netbox_id": d.get("_netbox_id")})
    return sorted(out, key=lambda r: r["name"])


def inventory_digest(inventory) -> str:
    """A sha256 over the inventory's copied fields, sorted: it moves only when what the model
    takes from NetBox (or the CSV) moves, never with a refresh that found nothing new."""
    blob = repr([sorted(r.items()) for r in _rows(inventory)]).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _intent_marker(repo: str) -> tuple:
    """``({"intent", "manifest"}, error)``: the committed tree of ``host_vars`` and the
    committed manifest's blob, in one git call; ``none`` for what nothing has committed."""
    from modules.nsot.repo import MANIFEST_REL, git

    out = {"intent": "none", "manifest": "none"}
    if not os.path.isdir(os.path.join(repo or "", ".git")):
        return out, ""
    rc, text, err = git(repo, "ls-tree", "HEAD", "host_vars", MANIFEST_REL)
    if rc != 0:
        if "Not a valid object name" in err or "not a tree" in err:
            return out, ""
        return out, f"the committed intent's version could not be read ({err or rc})"
    for line in text.splitlines():
        meta, _tab, path = line.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and path == "host_vars":
            out["intent"] = parts[2]
        elif len(parts) == 3 and path == MANIFEST_REL:
            out["manifest"] = parts[2]
    return out, ""


def version_of(repo: str, inventory, cables: dict = None) -> tuple:
    """``(version, error)``: ``{"intent", "manifest", "inventory", "cables", "key"}``, the key a
    short sha256 over them. *cables* is `netbox_cables`' answer: a network with none (a local
    CSV inventory) keeps the key it had before cables were a source."""
    marker, err = _intent_marker(repo)
    if err:
        return None, err
    ver = dict(marker, inventory=inventory_digest(inventory),
               cables=(cables or {}).get("digest") or "none")
    text = f"{ver['intent']} {ver['manifest']} {ver['inventory']}"
    if ver["cables"] != "none":
        text += f" {ver['cables']}"
    ver["key"] = "nm-" + hashlib.sha256(text.encode()).hexdigest()[:12]
    return ver, ""


# ----------------------------------------------------------------------------- NetBox's cables

def _clock() -> float:
    """The clock the cable read's age is judged by (one seam, so a test moves it)."""
    return time.monotonic()


def _cable_end(t: dict) -> dict:
    o = (t or {}).get("object") or {}
    dev = o.get("device") or {}
    return {"type": (t or {}).get("object_type") or "", "device_id": dev.get("id"),
            "device": dev.get("name") or "", "port": o.get("name") or ""}


def _cable(c: dict) -> dict:
    """One NetBox cable in the fields the model draws: its id, status and each side's ends
    (type, device id and name, port). Its label, NetBox free text, is never kept."""
    status = c.get("status")
    return {"id": c.get("id"),
            "status": (status.get("value") if isinstance(status, dict) else status) or "",
            "a": [_cable_end(t) for t in c.get("a_terminations") or []],
            "b": [_cable_end(t) for t in c.get("b_terminations") or []]}


def read_cables(network: str, client=None) -> dict:
    """NetBox's cables, as *network*'s NetBox integration client reads them (read-only: GETs of
    ``dcim/cables``, at most `CABLE_PAGES` pages, the network's site filter passed when its
    inventory has one): ``{"state": "read"|"could not read", "why", "read_at", "cables",
    "count", "truncated", "digest"}``. Never raises."""
    from modules.integrations import get_integration
    from modules.inventory import source_config

    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time()))
    out = {"state": "could not read", "why": "", "read_at": at, "cables": [], "count": 0,
           "truncated": "", "digest": "unreadable",
           "source": "NetBox's cables (dcim/cables), through the NetBox integration"}
    try:
        nb = client or get_integration("netbox", list_name=network)
        if not nb.is_configured():
            out["why"] = "NetBox is not configured (Settings › Installation, NetBox)"
            return out
        params = {"limit": CABLE_PAGE}
        site = ((source_config.load(network).get("filters") or {}).get("site") or "").strip()
        if site:
            params["site"] = site
        path, raw, count, pages = "api/dcim/cables/", [], 0, 0
        while path and pages < CABLE_PAGES:
            got = nb._get(path, **params)
            pages += 1
            if not got["ok"]:
                out["why"] = (f"NetBox's cables could not be read ({got.get('error')}"
                              + (f": {got['detail']}" if got.get("detail") else "") + ")")
                return out
            data = got["response"].json()
            count = int(data.get("count") or 0)
            raw += list(data.get("results") or [])
            nxt = data.get("next") or ""
            base = nb.url + "/"
            path, params = (nxt[len(base):], {}) if nxt.startswith(base) else ("", {})
            if nxt and not path:
                out["truncated"] = (f"NetBox named a next page outside its own address, so "
                                    f"{len(raw)} of {count} cables were read")
        if path:
            out["truncated"] = (f"{len(raw)} of {count} cables read, the most one read takes "
                                f"({CABLE_PAGES} pages of {CABLE_PAGE})")
    except Exception as exc:                            # noqa: BLE001 (said, never raised)
        out["why"] = f"NetBox's cables could not be read ({type(exc).__name__}: {exc})"
        log.warning("network model: %s", out["why"])
        return out
    cables = sorted((_cable(c) for c in raw), key=lambda c: (str(c["id"])))
    out.update(state="read", cables=cables, count=count or len(cables),
               digest=hashlib.sha256(repr([sorted((k, repr(v)) for k, v in c.items())
                                           for c in cables]).encode()).hexdigest()[:16])
    return out


def no_cables(network: str) -> dict:
    """What a network on a local CSV inventory says of cables: it has none to read."""
    return {"state": "none", "read_at": "", "cables": [], "count": 0, "truncated": "",
            "digest": "none", "source": "none",
            "why": (f"{network}'s inventory is a local CSV, which holds no cables: its links "
                    "are intent's subnets alone")}


def netbox_cables(network: str, refresh_s: float = None, read=None) -> dict:
    """*network*'s cables: `no_cables` for a network not on NetBox; else the last read, kept in
    this process's memory while it is younger than the network's own inventory refresh
    interval (`source_config`'s ``refresh_interval``, 300 s by default; *refresh_s* in its
    place), read again past it. A read that failed is kept as long, so NetBox down is asked
    once an interval, never once per question. *read* stands in for `read_cables` (tests)."""
    from modules.inventory import source_config

    try:
        cfg = source_config.load(network)
    except Exception as exc:                            # noqa: BLE001 (said, never raised)
        return dict(no_cables(network), state="could not read", digest="unreadable",
                    why=f"{network}'s inventory source could not be read ({exc})")
    if cfg.get("source") != source_config.SOURCE_NETBOX:
        return no_cables(network)
    ttl = float(refresh_s if refresh_s is not None else cfg.get("refresh_interval") or 300)
    with _LOCK:
        hit = _CABLES.get(network)
    if hit and _clock() - hit["at"] < ttl:
        return hit["doc"]
    doc = (read or read_cables)(network)
    with _LOCK:
        _CABLES[network] = {"at": _clock(), "doc": doc}
    return doc


def _cable_links(network: str, cables: dict, nodes: dict, links: dict) -> dict:
    """Join *cables* (`netbox_cables`' answer) to the model's *links*, in place: a cable between
    two interfaces of devices the model knows (by NetBox id) joins each intent link both
    devices are members of where one end's interface is the member's (its source then
    ``both``), else is its own link ``link:netbox-cable:<id>``. ``{"state", "why", "read_at",
    "count", "drawn", "joined", "own", "not_drawn": {why: n}, "truncated"}``."""
    from modules.nsot.ifnames import abbreviate

    said = {"state": cables.get("state") or "none", "why": cables.get("why") or "",
            "read_at": cables.get("read_at") or "", "count": len(cables.get("cables") or []),
            "drawn": 0, "joined": 0, "own": 0, "not_drawn": {},
            "truncated": cables.get("truncated") or "", "source": cables.get("source") or ""}

    def skip(why):
        said["not_drawn"][why] = said["not_drawn"].get(why, 0) + 1

    at, devs = {}, {}
    for lid, link in links.items():
        devs[lid] = {m["dev"] for m in link["members"]}
        for m in link["members"]:
            at.setdefault((m["dev"], m.get("interface")), []).append(lid)
    for c in cables.get("cables") or []:
        a, b = c.get("a") or [], c.get("b") or []
        if len(a) != 1 or len(b) != 1 or any(e["type"] != "dcim.interface" for e in a + b):
            skip("not_two_interfaces")
            continue
        (ea,), (eb,) = a, b
        da, db = f"dev:{ea['device_id']}", f"dev:{eb['device_id']}"
        if da not in nodes or db not in nodes:
            skip("unknown_device")
            continue
        if da == db:
            skip("one_device")
            continue
        pa, pb = abbreviate(ea["port"]), abbreviate(eb["port"])
        said["drawn"] += 1
        # The intent links either end's interface is a member of, and the other device too:
        # one lookup per end, never a pass over every link per cable.
        joined = sorted({lid for lid in at.get((da, pa), []) + at.get((db, pb), [])
                         if {da, db} <= devs[lid]})
        for lid in joined:
            links[lid]["source"] = "both"
            links[lid].setdefault("netbox_cables", []).append(c["id"])
        if joined:
            said["joined"] += 1
            continue
        lid = f"link:netbox-cable:{c['id']}"
        # The cable's label is NetBox free text and is never carried (the model copies no free
        # text); its status is NetBox's enumerated value.
        links[lid] = {"id": lid, "source": "netbox_cable", "netbox_cable": c["id"],
                      "members": sorted([{"dev": da, "interface": pa},
                                         {"dev": db, "interface": pb}],
                                        key=lambda m: (m["dev"], m["interface"]))}
        if c.get("status") and c["status"] != "connected":
            links[lid]["status"] = c["status"]
        said["own"] += 1
    return said


# ----------------------------------------------------------------------------- the build

def _ids(rows: list, manifest: dict, hosts) -> dict:
    """``{name: id}``: the NetBox id the inventory or the committed manifest records, else a
    local device's manifest identity, else its name."""
    by_name = {}
    for ident, entry in ((manifest or {}).get("devices") or {}).items():
        name = (entry or {}).get("name") or ""
        if name:
            by_name[name.lower()] = (ident, entry)
    inv = {r["name"]: r for r in rows}
    out, taken = {}, set()
    for host in sorted(hosts):
        nb = (inv.get(host) or {}).get("netbox_id")
        ident, entry = by_name.get(host.lower(), ("", {}))
        if nb in (None, ""):
            nb = (entry or {}).get("netbox_id")
        if nb not in (None, ""):
            dev = f"dev:{nb}"
        elif ident.startswith("uid:"):
            hexes = ident[4:].replace("-", "")
            dev = f"dev:u{hexes[:8]}"
            n = 8
            while dev in taken and n < len(hexes):
                n += 4
                dev = f"dev:u{hexes[:n]}"
        else:
            dev = f"dev:@{host}"
        if dev in taken:
            dev = f"dev:@{host}"
        taken.add(dev)
        out[host] = dev
    return out


def _addresses(iface: dict) -> list:
    """The interface's addresses as ``IPv4Interface``/``IPv6Interface``, intent's order."""
    from modules.neighbours import _v4

    out = []
    v4 = _v4(iface.get("ipv4", ""))
    if v4 is not None:
        out.append(v4)
    for a in iface.get("ipv6") or []:
        try:
            out.append(ipaddress.ip_interface(a))
        except ValueError:
            continue
    return out


def _passive(settings) -> list:
    out = []
    for s in settings or []:
        words = s.strip().split()
        if words[:1] == ["passive-interface"] and len(words) == 2:
            out.append(words[1])
    return out


def _interfaces(hv: dict) -> list:
    from modules.nsot.ifnames import abbreviate
    from modules.readers.topology_graph import _area

    out = []
    for iface in (hv or {}).get("interfaces") or []:
        name = iface.get("name") or ""
        e = {"name": abbreviate(name)}
        addrs = [str(a).lower() for a in _addresses(iface)]
        if (iface.get("ipv4") or "").strip() == "dhcp":
            addrs.insert(0, "dhcp")
        if addrs:
            e["addresses"] = addrs
        for key, field in (("vrf", "vrf"), ("mode", "switchport_mode"),
                           ("vlan", "switchport_access_vlan")):
            if iface.get(field):
                e[key] = str(iface[field])
        if iface.get("switchport_trunk_vlans"):
            e["trunk_vlans"] = [str(v) for v in iface["switchport_trunk_vlans"]]
        if iface.get("shutdown"):
            e["shutdown"] = True
        area = _area(hv, "ospf", name)
        if area:
            e["ospf_area"] = area
        area6 = _area(hv, "ospfv3", name)
        if area6:
            e["ospfv3_area"] = area6
        if len(e) > 1:
            out.append(e)
    return out


def _protocols(hv: dict) -> dict:
    from modules.neighbours import bgp_peers, router_id
    from modules.nsot.ifnames import abbreviate

    routing = (hv or {}).get("routing") or {}
    out = {}
    if routing.get("ospf"):
        settings = [s for p in routing["ospf"] for s in p.get("settings") or []]
        areas = sorted({n.split()[-1] for p in routing["ospf"] for n in p.get("networks") or []
                        if n.split()[-2:-1] == ["area"]})
        e = {"router_id": router_id(hv), "areas": areas}
        passive = _passive(settings)
        if "default" in passive:
            e["passive"] = "default"
        elif passive:
            e["passive"] = [abbreviate(p) for p in passive]
        out["ospf"] = {k: v for k, v in e.items() if v}
    if routing.get("ospfv3"):
        raw = [s for p in routing["ospfv3"] for s in p.get("raw") or []]
        e = {"router_id": router_id(hv)}
        passive = _passive(raw)
        if passive:
            e["passive"] = "default" if "default" in passive else [abbreviate(p) for p in passive]
        out["ospfv3"] = {k: v for k, v in e.items() if v}
    bgp = routing.get("bgp") or {}
    if bgp:
        out["bgp"] = {k: v for k, v in {
            "asn": str(bgp.get("asn") or ""),
            "peers": [{"address": str(a).lower(), "remote_as": asn}
                      for a, asn in bgp_peers(hv)]}.items() if v}
    return out


def _adj_id(proto: str, a: str, b: str, where: str) -> str:
    x, y = sorted((a, b))
    return f"adj:{proto}:{x}~{y}:{where}"


def build(network: str, inventory, intents: dict, manifest: dict = None, version: dict = None,
          errors=(), cables: dict = None) -> dict:
    """The model of *network*: pure, from the inventory's rows, committed intent
    (``{name: host_vars}``), the committed manifest and *cables* (`netbox_cables`' answer,
    C1863; None is a network with none). Never raises on a device's intent: one that cannot be
    read is named in ``errors``."""
    from modules import neighbours as N
    from modules.nsot.ifnames import abbreviate

    rows = _rows(inventory)
    lines = N._all_lines(intents or {})
    inv = {r["name"]: r for r in rows}
    hosts = sorted(set(inv) | set(lines))
    ids = _ids(rows, manifest, hosts)
    errors = list(errors)
    nodes = {}
    for host in hosts:
        r = inv.get(host) or {}
        node = {"id": ids[host], "name": host}
        for key in ("role", "site", "platform", "address"):
            if r.get(key):
                node[key] = r[key]
        if host not in inv:
            node["inventory"] = "not in the inventory: known by its committed intent only"
        if host in lines:
            try:
                node["interfaces"] = _interfaces(lines[host])
                node.update(_protocols(lines[host]))
            except Exception as exc:                    # noqa: BLE001 (said, never raised)
                errors.append(f"{host}'s intent could not be compiled ({type(exc).__name__})")
                node["intent"] = "could not be compiled"
        else:
            node["intent"] = "none committed: nothing is implied"
        nodes[ids[host]] = node

    # Links: every subnet two or more devices' interfaces share, by VRF.
    segs = {}
    for host in sorted(lines):
        for iface in (lines[host] or {}).get("interfaces") or []:
            for ip in _addresses(iface):
                if ip.network.prefixlen >= ip.max_prefixlen or ip.ip.is_link_local:
                    continue
                seg = segs.setdefault((iface.get("vrf") or "", ip.network), {})
                seg.setdefault(host, (abbreviate(iface.get("name") or ""), str(ip).lower()))
    links, link_of = {}, {}
    for (vrf, net), members in sorted(segs.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        if len(members) < 2:
            continue
        lid = f"link:{vrf}/{net}" if vrf else f"link:{net}"
        links[lid] = {"id": lid, "subnet": str(net), "source": "intent", "members": [
            {"dev": ids[h], "interface": p, "address": a} for h, (p, a) in sorted(members.items())]}
        if vrf:
            links[lid]["vrf"] = vrf
        if len(members) > MAX_SEGMENT:
            links[lid]["expanded"] = False
        held = {}
        for _p, a in members.values():
            held[a] = held.get(a, 0) + 1
        shared = sum(n for n in held.values() if n > 1)
        if shared:
            # Two devices holding one address are not on one segment, or are in conflict:
            # intent cannot say which, so the link is drawn and not walked through.
            links[lid]["expanded"] = False
            links[lid]["note"] = (f"{shared} members hold an address another member holds: "
                                  "separate segments or an address conflict, so it is not "
                                  "walked through")
        link_of[(vrf, str(net))] = lid

    # NetBox's documented cables (C1863): each joins the intent link it carries, or is a link
    # of its own; one whose ends the model does not know is counted, never drawn.
    cabled = _cable_links(network, cables or no_cables(network), nodes, links)

    # Expected adjacencies: each device's own links once, grouped by subnet.
    adjs = {}
    for proto, fn in (("ospf", N.ospf_links), ("ospfv3", N.ospfv3_links)):
        groups = {}
        for host in sorted(lines):
            for name, ip in fn(lines[host]):
                groups.setdefault(str(ip.network), {}).setdefault(host, name)
        for net, members in sorted(groups.items()):
            lid = link_of.get(("", net))
            if len(members) > MAX_SEGMENT:
                adjs[f"adj:{proto}:{net}"] = {
                    "id": f"adj:{proto}:{net}", "proto": proto, "link": lid,
                    "between": f"{len(members)} devices on one segment, not listed pairwise"}
                continue
            for a, b in itertools.combinations(sorted(members), 2):
                aid = _adj_id(proto, ids[a], ids[b], net)
                e ={"id": aid, "proto": proto, "between": sorted((ids[a], ids[b])),
                     "via": {ids[a]: abbreviate(members[a]), ids[b]: abbreviate(members[b])}}
                if lid:
                    e["link"] = lid
                adjs[aid] = e
    owners = N.addresses(lines)
    for host in sorted(lines):
        asn = str((((lines[host] or {}).get("routing") or {}).get("bgp") or {}).get("asn") or "")
        for addr, remote in N.bgp_peers(lines[host]):
            peer = owners.get(addr, "")
            fam = f"ipv{addr.version}"
            far = ids[peer] if peer in ids else f"ext:{str(addr).lower()}"
            aid = _adj_id("bgp", ids[host], far, fam)
            e = adjs.setdefault(aid, {"id": aid, "proto": "bgp",
                                      "between": sorted((ids[host], far)), "asn": {}})
            if asn:
                e["asn"][ids[host]] = asn
            e["asn"].setdefault(far, str(remote))
            if far.startswith("ext:"):
                e["outside_management"] = True
    # The walk's edges: a link's members to each other (a segment over MAX_SEGMENT is not
    # walked), and an adjacency's two ends (BGP between loopbacks shares no link).
    edges = {}

    def edge(a, b, via):
        if a != b:
            edges.setdefault(a, {}).setdefault(b, via)
            edges.setdefault(b, {}).setdefault(a, via)

    for lid, link in links.items():
        if link.get("expanded") is False:
            continue
        for x, y in itertools.combinations([m["dev"] for m in link["members"]], 2):
            edge(x, y, lid)
    for aid, a in adjs.items():
        if isinstance(a["between"], list) and "link" not in a:
            edge(a["between"][0], a["between"][1], aid)
    counts = {"devices": len(nodes), "links": len(links),
              "links_by_source": {s: sum(1 for x in links.values() if x.get("source") == s)
                                  for s in LINK_SOURCES},
              "adjacencies": {p: sum(1 for a in adjs.values() if a["proto"] == p)
                              for p in ROUTING}}
    BUILDS[network] = BUILDS.get(network, 0) + 1
    return {"schema": SCHEMA, "network": network, "version": dict(version or {}),
            "nodes": nodes, "links": links, "adjacencies": adjs, "names": ids,
            "edges": edges, "counts": counts, "errors": errors, "netbox_cables": cabled,
            # When the inventory and committed intent were read into it: the age the coverage
            # header gives those two layers.
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(_now()))}


# ----------------------------------------------------------------------------- coverage

#: The layers a network context can hold, in the order the coverage header lists them (the
#: operator, 2026-10-26: "make gaps explicit"). Flows remain roadmap. ``controller`` is an SDN
#: controller's topology (PHASE8_PLAN 17.1 S14): its switches, links and hosts.
LAYERS = ("inventory", "intent", "adjacency", "controller", "performance", "events",
          "endpoints", "flows")
#: A layer's state: all of it here, some of it, or none collected.
PRESENT, PARTIAL, NOT_COLLECTED = "present", "partial", "not_collected"


def coverage(model: dict, obs: dict, devices: dict, carried: dict = None) -> dict:
    """The coverage header of a context bundle: ``{layer: {"state", "source", "age", "why"}}``
    for every layer of `LAYERS`, so a gap is said, never left for the model to infer.
    *devices* is the bundle's devices (by id); *carried* the layers the caller holds beside
    this bundle (an evidence pack's health and log sections), each ``{"state", "source",
    "age"}``, said as the caller's. A layer nobody collects is not_collected, with why."""
    built = model.get("built_at", "")
    nodes = [model["nodes"][n] for n in devices if n in model["nodes"]]
    out = {}
    outside = [n["name"] for n in nodes if n.get("inventory")]
    out["inventory"] = {
        "state": PARTIAL if outside else PRESENT,
        "source": "the network's inventory (name, NetBox id, role, site, platform, address)",
        "age": built, "why": (f"{', '.join(sorted(outside))} known by committed intent only"
                              if outside else "")}
    lacking = [n["name"] for n in nodes if n.get("intent")]
    out["intent"] = {
        "state": (NOT_COLLECTED if nodes and len(lacking) == len(nodes)
                  else PARTIAL if lacking else PRESENT),
        "source": "committed intent (host_vars), what it implies for the topology",
        "age": built, "why": (f"{', '.join(sorted(lacking))}: none committed or not compiled"
                              if lacking else "")}
    read = obs.get("state") == "read"
    out["adjacency"] = {
        "state": PRESENT if read else PARTIAL,
        "source": "expected from intent; observed: " + (obs.get("source") or "the Topology "
                                                          "reader"),
        "age": obs.get("read_at") or built,
        "why": "" if read else f"observed state could not be read ({obs.get('why', '')}); "
                               "only what intent expects is here"}
    out["controller"] = controller_coverage(obs)
    carried = carried or {}
    for layer, words in (("performance", "health figures (CPU, memory, interfaces)"),
                         ("events", "log lines and alerts")):
        out[layer] = (dict(carried[layer]) if layer in carried else {
            "state": NOT_COLLECTED, "source": "", "age": "",
            "why": f"{words} are not in this bundle"})
    # Endpoints are observed state: as performance and events, only as the caller captured
    # them (C1712: a bundle reads no observed state itself, so a past alert's never describes
    # the network now); `endpoints.coverage_layer` is the endpoint store's own answer.
    out["endpoints"] = (dict(carried["endpoints"]) if "endpoints" in carried else {
        "state": NOT_COLLECTED, "source": "", "age": "",
        "why": "no endpoint state was captured with this bundle (the endpoint layer, C1772)"})
    out["flows"] = {"state": NOT_COLLECTED, "source": "", "age": "",
                    "why": "flows are not collected (roadmap)"}
    return {layer: out[layer] for layer in LAYERS}


def controller_coverage(obs: dict, now: float = None) -> dict:
    """The controller layer as a coverage header states it (S14), from the observed read:
    present when every controller's topology was read, partial when one could not be ("couldn't
    read: <why>", its switches as last read with that read's age), not_collected when the
    network has no controller or the Topology read itself could not be used."""
    from modules.sdn import topology as SDN

    if obs.get("state") != "read":
        return {"state": NOT_COLLECTED, "source": "", "age": "",
                "why": f"the Topology read could not be used ({obs.get('why', '')})"}
    got = obs.get("controllers")
    if not got or got.get("state") == "none":
        return {"state": NOT_COLLECTED, "source": "", "age": "",
                "why": "this network has no SDN controller connection"}
    said = got.get("controllers") or []
    if not said:
        return {"state": NOT_COLLECTED, "source": "", "age": "",
                "why": f"the controllers' topology could not be read ({got.get('why', '')})"}
    unread = [c for c in said if c["state"] != "read"]
    ages = sorted(c["read_at"] for c in said if c.get("read_at"))
    return {"state": PARTIAL if unread else PRESENT,
            "source": "; ".join(SDN.words(c, now) for c in said if c["state"] == "read")
                      or ", ".join(c["source"] for c in said),
            "age": ages[0] if ages else "",
            "why": "; ".join(SDN.words(c, now) for c in unread)}


# ----------------------------------------------------------------------------- the cache

def model_for(network: str) -> tuple:
    """``(model, error)``: *network*'s model, from this process's memory while its version
    holds, else built and kept."""
    from modules.device import load_saved_devices
    from modules.neighbours import committed_intents
    from modules.nsot import leased_address, listref

    try:
        ref = listref.resolve(network)
        inventory = load_saved_devices(ref.csv_path)
    except Exception as exc:                            # noqa: BLE001 (said, never raised)
        return None, f"{network}'s inventory could not be read ({type(exc).__name__}: {exc})"
    # NetBox's cables (C1863): read at most once per the network's inventory refresh interval,
    # kept in memory between; their digest is part of the version, so a recabling rebuilds.
    cables = netbox_cables(ref.name)
    ver, err = version_of(ref.repo_dir, inventory, cables)
    if ver is None:
        return None, err
    with _LOCK:
        hit = _CACHE.get(ref.name)
    if hit and hit["version"]["key"] == ver["key"]:
        return hit, ""
    intents, ierr = committed_intents(ref.repo_dir)
    manifest, merr = leased_address.committed_manifest(ref.repo_dir)
    model = build(ref.name, inventory, intents, manifest, version=ver,
                  errors=[e for e in (ierr, merr) if e], cables=cables)
    with _LOCK:
        _CACHE[ref.name] = model
    return model, ""


def forget(network: str = "") -> None:
    """Drop the kept model(s) (tests; nothing in the product needs it: the version decides)."""
    with _LOCK:
        if network:
            _CACHE.pop(network, None)
            _CABLES.pop(network, None)
        else:
            _CACHE.clear()
            _CABLES.clear()


# ----------------------------------------------------------------------------- observed

def observed(network: str, model: dict, now: float = None, stored: dict = None) -> dict:
    """The Topology reader's stored read for *network*, mapped onto the model's ids:
    ``{"state": "read"|"could not read", "why", "cause", "read_at", "routing": {adj id: entry},
    "cables": {cable id: entry}}``. One stored value read; no source is asked. *stored* is a
    read in the store's own shape (``{"value", "value_at"}``) given in place of the store's
    (a replay of a past alert reads the reader's sources as they were then). *cause* is the
    pack's state for a read that could not be used: ``absent`` (never read),
    ``not_configured`` (no Prometheus) or ``unreadable`` (everything else)."""
    from modules import reader_job
    from modules.readers import topology_graph as T
    from modules.sdn import topology as SDN

    now = _now() if now is None else now
    out = {"state": "could not read", "why": "", "cause": "unreadable", "read_at": "",
           "routing": {}, "cables": {},
           "source": "the Topology reader's last read of Prometheus (LLDP and the routing "
                     "tables)"}
    if stored is None:
        got = reader_job.read_cached(OBSERVED_READER)
        good = (got.get("doc") or {}).get("last_good") or {}
        state, why = got["state"], got.get("why")
    else:
        good, state, why = dict(stored or {}), "ok", ""
    if not good:
        out["why"] = ("the Topology reader has not read yet" if state in ("absent", "ok")
                      else f"the Topology reader's store {state}: {why}")
        if state in ("absent", "ok"):
            out["cause"] = "absent"
        return out
    at = good.get("value_at") or (good.get("value") or {}).get("read_at") or ""
    out["read_at"] = at
    try:
        stamp = calendar.timegm(time.strptime(at, "%Y-%m-%dT%H:%M:%SZ"))
    except (TypeError, ValueError):
        out["why"] = f"the Topology reader's stored read has no time ({at!r})"
        return out
    promise = reader_job.page_promise(T.READER)
    if now - stamp > promise:
        out["why"] = (f"the Topology reader's last read, at {at}, is older than its promise "
                      f"of {promise} s, so it is not current")
        return out
    if stamp - now > LATER_SLACK_SECONDS:
        out["why"] = (f"the Topology reader's last read, at {at}, is later than "
                      f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(now))}, the time it "
                      "is asked for, so it describes a later network")
        return out
    value = good.get("value") or {}
    if value.get("configured") is False:
        out["why"] = "Prometheus is not configured, so nothing is observed"
        out["cause"] = "not_configured"
        return out
    net = (value.get("networks") or {}).get(network)
    if net is None:
        out["why"] = f"the Topology reader's last read holds nothing for {network}"
        return out
    out["state"], out["why"], out["cause"] = "read", "", ""
    names = model["names"]

    def end(name, link=None):
        if name == T.MANAGER:
            return MANAGER_ID
        if name in names:
            return names[name]
        if SDN.is_switch(name):
            return name                     # an OpenFlow switch, keyed by its DPID (S14)
        # An outside peer the reader named through LLDP keeps the address intent names it by
        # (topology_graph.network_graph: `external` the name, `address` the address).
        if link and name == link.get("external") and link.get("address"):
            return f"ext:{str(link['address']).lower()}"
        return f"ext:{name}"

    for proto in ROUTING:
        for link in (net.get("layers") or {}).get(proto) or []:
            a, b = sorted((end(link.get("a", ""), link), end(link.get("b", ""), link)))
            where = str(link.get("network") or "")
            if proto != "bgp":
                try:
                    where = str(ipaddress.ip_network(where, strict=False))
                except ValueError:
                    pass
            # The same parts make the same id: an expected adjacency's observed state lands on
            # it by construction, one lookup, never a search.
            aid = _adj_id(proto, a, b, where)
            state = link.get("state") or "not measured"
            entry = {"state": {"not_seen": "not reported"}.get(state, state), "read_at": at}
            if link.get("words"):
                entry["words"] = link["words"]
            if not link.get("intended"):
                entry["expected"] = False
                entry["between"] = [a, b]
                entry["proto"] = proto
            if link.get("since"):
                entry["since"] = link["since"]
            out["routing"][aid] = entry
    if net.get("sdn") is not None:
        # The controller layer (S14): what each controller gave, for the coverage header.
        out["controllers"] = net["sdn"]
    for link in (net.get("layers") or {}).get("physical") or []:
        if link.get("overlay"):
            continue                        # a controller's hosts and itself: not cables
        ea = (end(link.get("a", "")), link.get("port_a") or "")
        eb = (end(link.get("b", "")), link.get("port_b") or "")
        (x, px), (y, py) = sorted((ea, eb))
        cid = f"cable:{x}/{px}~{y}/{py}"
        entry = {"ends": [{"dev": x, "port": px}, {"dev": y, "port": py}],
                 "state": link.get("state") or "unknown", "read_at": at}
        if link.get("kind"):
            entry["reported"] = {"both": "by both ends", "one_silent": "by one end, the "
                                 "other polled and silent", "far_not_polled": "by one end, the "
                                 "other not polled"}.get(link["kind"], link["kind"])
        if link.get("down_at"):
            entry["down_at"] = [end(d) for d in link["down_at"]]
        if link.get("manager"):
            entry["mercury_attaches_here"] = True
        if link.get("sources"):
            # A link a controller reported, or a hybrid one (a device's LLDP and the
            # controller): each source named (S14). LLDP's own links say nothing more.
            entry["sources"] = list(link["sources"])
        out["cables"][cid] = entry
    return out


# ----------------------------------------------------------------------------- the subgraph

def _walk(model: dict, extra: dict, seeds: list, hops: int) -> dict:
    """``{id: (hop, via)}``: every node within *hops* of *seeds*, breadth first, the first
    way reached kept (sorted, so the same each time). Outside peers and Mercury's host are
    reached and never walked through."""
    reached = {s: (0, "") for s in seeds}
    frontier = list(seeds)
    for hop in range(1, hops + 1):
        nxt = []
        for node in sorted(frontier):
            if node.startswith("ext:") or node == MANAGER_ID:
                continue
            near = dict(model["edges"].get(node) or {})
            for k, v in (extra.get(node) or {}).items():
                near.setdefault(k, v)
            for other, via in sorted(near.items()):
                if other not in reached:
                    reached[other] = (hop, via)
                    nxt.append(other)
        frontier = nxt
    return reached


def _yaml(doc) -> str:
    import yaml
    return yaml.safe_dump(doc, sort_keys=True, default_flow_style=None, allow_unicode=True,
                          width=100)


def _extra(obs: dict) -> dict:
    """The walk's observed edges: an LLDP cable between two devices (never through Mercury's
    host) and an adjacency intent does not imply."""
    extra = {}
    for cid, c in (obs.get("cables") or {}).items():
        (a, b) = [e["dev"] for e in c["ends"]]
        if a != MANAGER_ID and b != MANAGER_ID:
            extra.setdefault(a, {}).setdefault(b, cid)
            extra.setdefault(b, {}).setdefault(a, cid)
    for aid, o in (obs.get("routing") or {}).items():
        if o.get("expected") is False:
            a, b = o["between"]
            extra.setdefault(a, {}).setdefault(b, aid)
            extra.setdefault(b, {}).setdefault(a, aid)
    return extra


def _seeds(network: str, model: dict, subject: str) -> tuple:
    """``(subject id, seeds, error)``: a device by its NetBox id, its model id or its name; a
    link by its id (its members are the seeds)."""
    subject = str(subject or "").strip()
    if subject.startswith("link:"):
        link = model["links"].get(subject)
        if link is None:
            return subject, [], f"{network} has no link {subject[:60]}"
        return subject, [m["dev"] for m in link["members"]], ""
    names = model["names"]
    sid = (subject if subject in model["nodes"] else f"dev:{subject}"
           if f"dev:{subject}" in model["nodes"] else names.get(subject))
    if sid is None:
        return subject, [], f"{network}'s model holds no device {subject[:60]}"
    return sid, [sid], ""


def unread(why: str) -> dict:
    """An overlay that holds nothing, saying why (a pack built before overlays were captured,
    C1712): every item it would have overlaid says "could not read" with *why*."""
    return {"state": "could not read", "why": why, "cause": "absent", "read_at": "",
            "routing": {}, "cables": {}, "source": "none"}


#: What a walk of the model as it is now says of itself, when nothing observed then can be had
#: (a pack rebuilt from the alert history, C1851): the model's own sources, read now.
AS_NOW_WORDS = ("the network model as it is now (the inventory and committed intent, read "
                "{built}), not as it was at the alert's time {at}: it may differ from then")


def as_now_words(model: dict, at: str) -> str:
    """`AS_NOW_WORDS` for *model*, the alert's time *at*."""
    return AS_NOW_WORDS.format(built=model.get("built_at") or "now", at=at or "not recorded")


def capture(network: str, subject: str, hops: int = CAPTURE_HOPS, now: float = None,
            stored: dict = None, observe: bool = True) -> dict:
    """The observed overlay around *subject*, read ONCE, for an evidence pack to keep (C1712):
    ``{"ok", "error", "overlay", "reached", "nodes", "subject", "version", "names"}``.
    *overlay* is `observed`'s answer kept to the items touching a device within *hops* (walked
    with the overlay's own cables, as `context_for` walks); *reached* each device's ``{"hop",
    "via"}``; *nodes* each reached managed device's ``{"name", "role", "platform"}`` (who the
    health figures are read for, C1714); *names* every device's id by name (C1849: one id per
    device in everything a pack names). *now* is the time it is captured for (the alert's);
    *stored* a read in the store's shape given in place of the store's (a replay).

    *observe* False (a pack rebuilt from the alert history, C1851) reads no observed state:
    the walk is the model's own, intent and inventory as they are now, the overlay says it
    could not be read, and ``as_now`` says the walk is of now, which may differ from then."""
    try:
        hops = max(0, min(int(hops), MAX_HOPS))
    except (TypeError, ValueError):
        hops = CAPTURE_HOPS
    model, err = model_for(network)
    if model is None:
        return {"ok": False, "error": err}
    sid, seeds, err = _seeds(network, model, subject)
    if err:
        return {"ok": False, "error": err}
    as_now = ""
    if observe:
        obs = observed(network, model, now=now, stored=stored)
    else:
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)) if now is not None else ""
        as_now = as_now_words(model, at)
        obs = unread("the network as observed then was not captured when the alert fired; "
                     "a later read is never put in its place")
    reached = _walk(model, _extra(obs), seeds, hops)
    near = set(reached)
    kept = dict(obs, routing={}, cables={})
    for aid, o in obs["routing"].items():
        a = model["adjacencies"].get(aid) or {}
        ends = o.get("between") or (a.get("between") if isinstance(a.get("between"), list)
                                    else [])
        if any(e in near for e in ends):
            kept["routing"][aid] = o
    for cid, c in obs["cables"].items():
        if any(e["dev"] in near for e in c["ends"]):
            kept["cables"][cid] = c
    nodes = {n: {k: model["nodes"][n][k] for k in ("name", "role", "platform")
                 if k in model["nodes"][n]}
             for n in reached if n in model["nodes"]}
    return {"ok": True, "error": "", "overlay": kept, "subject": sid,
            "reached": {n: {"hop": h, "via": v} for n, (h, v) in reached.items()},
            "nodes": nodes, "version": model["version"].get("key", ""),
            "names": dict(model["names"]), "as_now": as_now}


def context_for(network: str, subject: str, hops: int = 1, overlay: dict = None,
                carried: dict = None, as_now: str = "") -> dict:
    """The subgraph of *network* around *subject* (a device by its NetBox id, its model id or
    its name; or a link by its id), within *hops*, *overlay* overlaid: the observed state
    `capture` kept (C1712: this reads no observed state itself, so a subgraph of a past alert
    is never the network now). No overlay is said as could not read on every item.
    ``{"ok", "error", "yaml", "summary", "ids", "reached", "version"}``: *yaml* compact
    (sorted keys, no anchors), *ids* every id it holds (what a citation may name), *reached*
    each device's ``(hop, via)``. Its ``coverage`` (`coverage`), in the bundle and the
    answer, lists every layer as present, partial or not_collected, with its source and age;
    *carried* the layers the caller holds beside it (an evidence pack's health and logs).
    *as_now* (C1851), when the subgraph stands for a past network it is not of (a pack rebuilt
    afterwards), is said in it as ``as_now``, so it is never read as the network then; the
    answer's ``names`` is every device's id by name (C1849)."""
    try:
        hops = max(0, min(int(hops), MAX_HOPS))
    except (TypeError, ValueError):
        hops = 1
    model, err = model_for(network)
    if model is None:
        return {"ok": False, "error": err}
    subject, seeds, err = _seeds(network, model, subject)
    if err:
        return {"ok": False, "error": err}
    obs = overlay if overlay is not None else unread("no observed state was given")
    reached = _walk(model, _extra(obs), seeds, hops)
    inner = {n for n, (h, _v) in reached.items() if h < hops or h == 0}
    could_not = f"could not read ({obs['why']})" if obs["state"] != "read" else ""

    devices = {}
    for nid, (hop, via) in sorted(reached.items()):
        node = model["nodes"].get(nid)
        if node is None:
            devices[nid] = {"hop": hop, "via": via,
                            "managed": False} if nid != MANAGER_ID else {
                "hop": hop, "via": via, "what": "this tool's own host"}
            continue
        if nid in inner:
            d = {k: v for k, v in node.items() if k != "id"}
        else:
            d = {k: node[k] for k in ("name", "role", "site", "platform", "address")
                 if k in node}
            d["detail"] = "beyond the hops asked: identity only"
        d["hop"] = hop
        if via:
            d["via"] = via
        devices[nid] = d

    def touches(ends) -> bool:
        return any(e in inner for e in ends)

    links = {}
    for lid, link in model["links"].items():
        members = [m["dev"] for m in link["members"]]
        if not (touches(members) or lid == subject):
            continue
        e = {k: v for k, v in link.items() if k not in ("id", "members")}
        shown = (link["members"] if link.get("expanded") is not False
                 else [m for m in link["members"] if m["dev"] in reached])
        e["members"] = shown
        if len(shown) < len(link["members"]):
            e["members_total"] = len(link["members"])
            e["listed"] = (f"only the {len(shown)} of its {len(link['members'])} members in "
                           "this subgraph")
            if len(link["members"]) > MAX_SEGMENT:
                e.setdefault("note", f"a segment of {len(link['members'])} devices is not "
                                     "walked through")
        links[lid] = e
    adjacencies = {}
    for aid, a in model["adjacencies"].items():
        ends = a["between"] if isinstance(a["between"], list) else []
        if not ends and a.get("link") not in links:
            continue
        if ends and not touches(ends):
            continue
        e = {k: v for k, v in a.items() if k != "id"}
        e["expected"] = True
        e["observed"] = (could_not or (
            {k: v for k, v in obs["routing"][aid].items() if k not in ("between", "proto")}
            if aid in obs["routing"] else f"not in the read of {obs['read_at']}"))
        adjacencies[aid] = e
    for aid, o in obs["routing"].items():
        if o.get("expected") is False and touches(o["between"]):
            adjacencies[aid] = {"proto": o["proto"], "between": o["between"], "expected": False,
                                "observed": {k: v for k, v in o.items()
                                             if k not in ("between", "proto", "expected")}}
    cables = {cid: c for cid, c in obs["cables"].items()
              if touches([e["dev"] for e in c["ends"]])}
    doc = {"network": network, "model": model["version"].get("key", ""),
           "subject": subject, "hops": hops, "devices": devices, "links": links,
           "adjacencies": adjacencies,
           "cables": cables or (could_not or "none reported for these devices"),
           "observed": {"source": obs["source"], "read_at": obs["read_at"] or "never",
                        "state": "read" if obs["state"] == "read" else could_not}}
    if obs.get("as_of"):
        doc["observed"]["as_of"] = obs["as_of"]
    doc["netbox_cables"] = cables_said(model)
    if as_now:
        doc["as_now"] = as_now
    doc["coverage"] = coverage(model, obs, devices, carried)
    if model["errors"]:
        doc["model_errors"] = list(model["errors"])
    ids = set(devices) | set(links) | set(adjacencies) | set(cables)
    return {"ok": True, "error": "", "yaml": _yaml(doc), "summary": summary(model),
            "ids": sorted(ids), "reached": {n: {"hop": h, "via": v}
                                            for n, (h, v) in reached.items()},
            "version": model["version"].get("key", ""), "observed": obs["state"],
            "coverage": doc["coverage"], "names": dict(model["names"])}


def cables_said(model: dict) -> object:
    """What a subgraph says of the network's NetBox cables (C1863): for a network on NetBox,
    when they were read, how many, how many are links and how many were left out, by why; else
    why there are none, or why they could not be read. Every link's own ``source`` says which
    of its links came from them."""
    c = model.get("netbox_cables") or {}
    if c.get("state") == "read":
        out = {"source": c.get("source") or "NetBox", "read_at": c.get("read_at") or "",
               "cables": c.get("count", 0), "drawn": c.get("drawn", 0),
               "joined_to_an_intent_subnet": c.get("joined", 0),
               "links_of_their_own": c.get("own", 0)}
        if c.get("not_drawn"):
            out["not_drawn"] = [{"count": n, "why": NOT_DRAWN_WORDS.get(k, k)}
                                for k, n in sorted(c["not_drawn"].items())]
        if c.get("truncated"):
            out["truncated"] = c["truncated"]
        return out
    if c.get("state") == "could not read":
        return f"could not read ({c.get('why') or 'no reason given'}): links are intent's alone"
    return c.get("why") or "none: links are intent's subnets alone"


def reach(network: str, subject: str, hops: int = 1, overlay: dict = None) -> list:
    """``[(hop, id, name, via)]``, sorted: which devices *subject* and *hops* reach, for a
    person reading what a call was given."""
    got = context_for(network, subject, hops, overlay=overlay)
    if not got["ok"]:
        return []
    model, _err = model_for(network)
    nodes = (model or {}).get("nodes") or {}
    return sorted((r["hop"], n, (nodes.get(n) or {}).get("name", n), r["via"])
                  for n, r in got["reached"].items())


# ----------------------------------------------------------------------------- the summary

def summary(model: dict) -> str:
    """The network in a few lines, the same bytes on every call while the model holds (no
    time, no read, nothing observed): what a feature puts in its cached prefix."""
    nodes = model["nodes"].values()

    def tally(key):
        out = {}
        for n in nodes:
            v = n.get(key) or "not recorded"
            out[v] = out.get(v, 0) + 1
        return out

    doc = {"network": model["network"], "devices": len(model["nodes"]),
           "by_role": tally("role"), "by_platform": tally("platform"), "by_site": tally("site"),
           "links": len(model["links"]),
           "links_by_source": dict(model["counts"].get("links_by_source") or {}),
           "segments_not_walked": sum(1 for l in model["links"].values()
                                      if l.get("expanded") is False),
           "adjacencies_expected": dict(model["counts"]["adjacencies"]),
           "devices_without_intent": sum(1 for n in nodes if "intent" in n),
           "ids": list(ID_WORDS)}
    if len(model["nodes"]) <= SUMMARY_DEVICES:
        doc["device_index"] = {n["id"]: f"{n['name']} ({n.get('role') or 'no role'})"
                               for n in nodes}
    else:
        doc["device_index"] = (f"not listed: {len(model['nodes'])} devices, over "
                               f"{SUMMARY_DEVICES}; the subgraph names those it reaches")
    return _yaml(doc)


#: What a prompt's context says of the subgraph's layout, the same bytes on every call.
FORMAT = "\n".join([
    "The topology is compact YAML from the tool's network model: devices, links (subnets two "
    "or more devices share by intent, and cables NetBox documents; each link's source says "
    "which: intent, netbox_cable or both), adjacencies (what intent implies, each with what "
    "was observed) and cables (what LLDP reports). netbox_cables says when NetBox's cables "
    "were read and how many were left out, or why there are none.",
    "Ids: " + "; ".join(ID_WORDS) + ". Cite an item by its id exactly as written.",
    "Each device has its hop from the subject and the item it was reached by (via); devices "
    "at the last hop carry identity only.",
    "observed is the Topology reader's read captured with the evidence pack when the alert "
    "was found firing (as_of), each item with the read's own time (read_at); it is never read "
    "again later. Compare read_at with the alert's onset before using it. 'could not read' "
    "means nothing was observed, never that nothing is there; 'not in the read' means the "
    "read did not hold it.",
    "Intent says what should be; observed says what was reported. Neither is a configuration "
    "line.",
])
