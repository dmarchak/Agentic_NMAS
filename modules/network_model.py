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
- **Observed**, overlaid when a subgraph is asked for, never compiled into the model: the
  Topology reader's stored read (`topology-graph`: LLDP's links and the routing tables, the
  whole fleet per read, from Prometheus), each observed item with the read's time. A read that
  cannot be used (absent, unreadable, older than its promise) is said as "could not read" with
  why, on every item it would have overlaid; never left out.

**What it reuses.** The adjacencies are the Neighbours tab's own rules (`neighbours.ospf_links`,
`ospfv3_links`, `bgp_peers`, `router_id`, `addresses`), each device's links computed ONCE and
grouped by subnet, so the fleet costs one pass rather than `neighbours.expected`'s pass per
device; the OSPF area is Topology's (`topology_graph._area`). The expected islands
(`topology_expected`) are declarations about the map, not links, and are not part of it.

**Its version** is the committed intent's tree (`HEAD:host_vars`) and manifest blob, and a
digest of the inventory's copied fields, which is NetBox's change as it reaches this
installation: the inventory reads no changelog id or change time (C1710). The model is rebuilt
only when one of them moves: a golden committed alone moves HEAD and not the intent's tree, so
it rebuilds nothing.

**Where it is kept:** in this process's memory (`_CACHE`), one model per network, replaced
whole under a lock; never on disk, so a read writes nothing (tests/test_reads_write_nothing.py)
and a second worker process builds its own. Asking costs one git call and the inventory's
digest; a build, two more git calls and one pass over the fleet.

**Its ids** (`ID_WORDS`), deterministic and stable while the network is: ``dev:<NetBox id>``
(``dev:u<8 hex>`` from a local device's manifest identity, ``dev:@<name>`` for a device no
manifest records); ``link:<subnet>`` (``link:<vrf>/<subnet>`` inside a VRF);
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
ROUTING = ("ospf", "ospfv3", "bgp")
#: Mercury's own host on the observed map (topology_graph.MANAGER): an end, never a way through.
MANAGER_ID = "mercury"

ID_WORDS = (
    "dev:<NetBox id> is a managed device (dev:u<hex> a local one, dev:@<name> one no manifest "
    "records); ext:<address or name> a peer outside management; mercury is this tool's own "
    "host, where it attaches",
    "link:<subnet> is a subnet two or more devices' interfaces share by intent "
    "(link:<vrf>/<subnet> inside a VRF)",
    "adj:<protocol>:<a>~<b>:<subnet or ipv4/ipv6> is an adjacency between two ends",
    "cable:<a>/<port>~<b>/<port> is a physical link LLDP reports",
)

_CACHE: dict = {}
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


def version_of(repo: str, inventory) -> tuple:
    """``(version, error)``: ``{"intent", "manifest", "inventory", "key"}``, the key a short
    sha256 over the three."""
    marker, err = _intent_marker(repo)
    if err:
        return None, err
    ver = dict(marker, inventory=inventory_digest(inventory))
    ver["key"] = "nm-" + hashlib.sha256(
        f"{ver['intent']} {ver['manifest']} {ver['inventory']}".encode()).hexdigest()[:12]
    return ver, ""


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
          errors=()) -> dict:
    """The model of *network*: pure, from the inventory's rows, committed intent
    (``{name: host_vars}``) and the committed manifest. Never raises on a device's intent: one
    that cannot be read is named in ``errors``."""
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
        links[lid] = {"id": lid, "subnet": str(net), "members": [
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
              "adjacencies": {p: sum(1 for a in adjs.values() if a["proto"] == p)
                              for p in ROUTING}}
    BUILDS[network] = BUILDS.get(network, 0) + 1
    return {"schema": SCHEMA, "network": network, "version": dict(version or {}),
            "nodes": nodes, "links": links, "adjacencies": adjs, "names": ids,
            "edges": edges, "counts": counts, "errors": errors}


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
    ver, err = version_of(ref.repo_dir, inventory)
    if ver is None:
        return None, err
    with _LOCK:
        hit = _CACHE.get(ref.name)
    if hit and hit["version"]["key"] == ver["key"]:
        return hit, ""
    intents, ierr = committed_intents(ref.repo_dir)
    manifest, merr = leased_address.committed_manifest(ref.repo_dir)
    model = build(ref.name, inventory, intents, manifest, version=ver,
                  errors=[e for e in (ierr, merr) if e])
    with _LOCK:
        _CACHE[ref.name] = model
    return model, ""


def forget(network: str = "") -> None:
    """Drop the kept model(s) (tests; nothing in the product needs it: the version decides)."""
    with _LOCK:
        if network:
            _CACHE.pop(network, None)
        else:
            _CACHE.clear()


# ----------------------------------------------------------------------------- observed

def observed(network: str, model: dict, now: float = None) -> dict:
    """The Topology reader's stored read for *network*, mapped onto the model's ids:
    ``{"state": "read"|"could not read", "why", "read_at", "routing": {adj id: entry},
    "cables": {cable id: entry}}``. One stored value read; no source is asked."""
    from modules import reader_job
    from modules.readers import topology_graph as T

    now = _now() if now is None else now
    out = {"state": "could not read", "why": "", "read_at": "", "routing": {}, "cables": {},
           "source": "the Topology reader's last read of Prometheus (LLDP and the routing "
                     "tables)"}
    got = reader_job.read_cached(OBSERVED_READER)
    good = (got.get("doc") or {}).get("last_good") or {}
    if not good:
        out["why"] = ("the Topology reader has not read yet" if got["state"] == "absent"
                      else f"the Topology reader's store {got['state']}: {got.get('why')}")
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
    value = good.get("value") or {}
    if value.get("configured") is False:
        out["why"] = "Prometheus is not configured, so nothing is observed"
        return out
    net = (value.get("networks") or {}).get(network)
    if net is None:
        out["why"] = f"the Topology reader's last read holds nothing for {network}"
        return out
    out["state"], out["why"] = "read", ""
    names = model["names"]

    def end(name, link=None):
        if name == T.MANAGER:
            return MANAGER_ID
        if name in names:
            return names[name]
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
    for link in (net.get("layers") or {}).get("physical") or []:
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


def context_for(network: str, subject: str, hops: int = 1, now: float = None) -> dict:
    """The subgraph of *network* around *subject* (a device by its NetBox id, its model id or
    its name; or a link by its id), within *hops*, the observed overlaid. ``{"ok", "error",
    "yaml", "summary", "ids", "reached", "version"}``: *yaml* compact (sorted keys, no
    anchors), *ids* every id it holds (what a citation may name), *reached* each device's
    ``(hop, via)``."""
    try:
        hops = max(0, min(int(hops), MAX_HOPS))
    except (TypeError, ValueError):
        hops = 1
    model, err = model_for(network)
    if model is None:
        return {"ok": False, "error": err}
    subject = str(subject or "").strip()
    names = model["names"]
    if subject.startswith("link:"):
        link = model["links"].get(subject)
        if link is None:
            return {"ok": False, "error": f"{network} has no link {subject[:60]}"}
        seeds = [m["dev"] for m in link["members"]]
    else:
        sid = (subject if subject in model["nodes"] else f"dev:{subject}"
               if f"dev:{subject}" in model["nodes"] else names.get(subject))
        if sid is None:
            return {"ok": False, "error": f"{network}'s model holds no device {subject[:60]}"}
        subject, seeds = sid, [sid]
    obs = observed(network, model, now=now)
    extra = {}
    for cid, c in obs["cables"].items():
        (a, b) = [e["dev"] for e in c["ends"]]
        if a != MANAGER_ID and b != MANAGER_ID:
            extra.setdefault(a, {}).setdefault(b, cid)
            extra.setdefault(b, {}).setdefault(a, cid)
    for aid, o in obs["routing"].items():
        if o.get("expected") is False:
            a, b = o["between"]
            extra.setdefault(a, {}).setdefault(b, aid)
            extra.setdefault(b, {}).setdefault(a, aid)
    reached = _walk(model, extra, seeds, hops)
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
    if model["errors"]:
        doc["model_errors"] = list(model["errors"])
    ids = set(devices) | set(links) | set(adjacencies) | set(cables)
    return {"ok": True, "error": "", "yaml": _yaml(doc), "summary": summary(model),
            "ids": sorted(ids), "reached": {n: {"hop": h, "via": v}
                                            for n, (h, v) in reached.items()},
            "version": model["version"].get("key", ""), "observed": obs["state"]}


def reach(network: str, subject: str, hops: int = 1, now: float = None) -> list:
    """``[(hop, id, name, via)]``, sorted: which devices *subject* and *hops* reach, for a
    person reading what a call was given."""
    got = context_for(network, subject, hops, now=now)
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
    "or more devices share by intent), adjacencies (what intent implies, each with what was "
    "observed) and cables (what LLDP reports).",
    "Ids: " + "; ".join(ID_WORDS) + ". Cite an item by its id exactly as written.",
    "Each device has its hop from the subject and the item it was reached by (via); devices "
    "at the last hop carry identity only.",
    "observed is the Topology reader's last read, with its time (read_at). It may be later "
    "than the alert: compare read_at with the alert's onset before using it. 'could not read' "
    "means nothing was observed, never that nothing is there; 'not in the read' means the "
    "read did not hold it.",
    "Intent says what should be; observed says what was reported. Neither is a configuration "
    "line.",
])
