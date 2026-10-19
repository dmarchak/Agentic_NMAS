"""Does NetBox hold what each device's committed golden describes? A reader job (C1344, Lab 8's
objective (b): "the NSoT is updated appropriately when the new devices are added").

**Why it exists.** Onboarding writes NetBox once, from the bootstrap golden (Verify's `netbox`
step: the device, its platform, its management interface and address), and nothing writes it
again: a deploy commits the device's golden and NetBox never hears. So a device whose intent
was deployed after onboarding has interfaces, addresses and links NetBox does not, and nothing
said so. This reader says it, per device, and Needs attention draws it until the import (the
NetBox page's, scoped to the device from its NetBox tab) brings NetBox up to the golden.

**What it compares**, per managed device of each network, with what the import would add
(`netbox_client`'s own parser, so the two cannot disagree on what a golden holds):
- *interfaces*: each interface block of the committed golden NetBox's record does not hold by
  name;
- *addresses*: each IPv4 and IPv6 address on those blocks (primary and secondary) NetBox holds
  on none of the device's interfaces, an excluded VRF's left out as the import leaves them out
  (`netbox_excluded_vrfs`);
- *cables*: each link the Topology reader's stored LLDP has both ends reporting between two
  managed devices of the network (`netbox_client.lldp_cable_plan`) where NetBox holds a cable at
  neither end.
Prefixes are not counted: one is the network's, made by whichever device's import comes first,
and a row per device would count it again for each.

**Its population** is each network's inventory with a committed golden, judged only where the
network is in NetBox at all (its site exists, or a device of it carries a NetBox id): a network
nobody imports into NetBox is not a lag. A device with no record there, in a network that is,
lags by everything its golden holds.

**What it costs.** No device, and nothing per request: per network, one `git ls-tree` and one
`git cat-file --batch` for the committed goldens, and NetBox's site, devices, interfaces and
addresses read in pages of `CHUNK` devices (four requests per 50 devices). Consumers read the
stored value.
"""

import logging
import re
import subprocess

from modules import reader_job

log = logging.getLogger(__name__)

NAME = "netbox-lag"
#: An import, an onboarding's Verify, an adoption and a deploy each wake it at once
#: (`reader_wakes`), so the schedule only catches an edit made in NetBox's own screens and an
#: LLDP link the Topology reader found since: five minutes.
INTERVAL_SECONDS = 300
#: Devices per NetBox request (each id a query parameter): 50 keeps a request's address well
#: under common 8 KiB limits.
CHUNK = 50


def committed_goldens(repo: str) -> tuple:
    """``({rel path: text}, error)`` for every file under ``golden/`` at HEAD: one `git ls-tree`
    and one `git cat-file --batch`, never a read per device (the scale rule). Committed, never
    the working tree (C104). No HEAD yet holds nothing, which is not an error."""
    from modules.nsot.repo import GIT_TIMEOUT, _git_env, git, run_git

    rc, out, err = git(repo, "ls-tree", "-r", "HEAD", "--", "golden/")
    if rc != 0:
        if "Not a valid object name" in err or "not a tree" in err:
            return {}, ""
        return {}, f"the committed goldens could not be listed ({err or rc})"
    entries = []
    for line in out.splitlines():
        m = re.match(r"^\d+ blob ([0-9a-f]+)\t(golden/.+)$", line)
        if m:
            entries.append((m.group(2), m.group(1)))
    if not entries:
        return {}, ""
    try:
        proc = run_git(repo, "cat-file", "--batch", text=False,
                       input="".join(f"{sha}\n" for _r, sha in entries).encode(),
                       timeout=GIT_TIMEOUT, env=_git_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, f"the committed goldens could not be read ({exc})"
    if proc.returncode != 0:
        return {}, ("the committed goldens could not be read "
                    f"({proc.stderr.decode(errors='replace').strip()})")
    data, pos, texts = proc.stdout, 0, {}
    for rel, _sha in entries:
        nl = data.index(b"\n", pos)
        size = int(data[pos:nl].split()[2])
        texts[rel] = data[nl + 1:nl + 1 + size].decode("utf-8", errors="replace")
        pos = nl + 1 + size + 1
    return texts, ""


def goldens_by_device(list_name: str, ref, hosts) -> tuple:
    """``({host: golden text}, {host: NetBox id}, error)`` for the inventory's *hosts*, through
    the manifest (the one place a device's golden path and NetBox id are recorded)."""
    from modules.nsot import manifest

    repo = ref.repo_dir
    try:
        entries = manifest.load(repo).get("devices") or {}
    except Exception as exc:                          # noqa: BLE001 (the network's error)
        return {}, {}, f"{list_name}'s manifest could not be read ({exc})"
    texts, err = committed_goldens(repo)
    wanted = set(hosts)
    goldens, ids = {}, {}
    for entry in entries.values():
        name = entry.get("name") or ""
        if name not in wanted:
            continue
        rel = (entry.get("golden") or "").replace("\\", "/")
        if rel in texts:
            goldens[name] = texts[rel]
        if entry.get("netbox_id") not in (None, ""):
            ids[name] = entry["netbox_id"]
    return goldens, ids, err


def _chunks(items, n=CHUNK):
    items = list(items)
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _ref_id(value):
    """An id NetBox gave as a nested object or as the bare id."""
    return value.get("id") if isinstance(value, dict) else value


def netbox_holds(session, base: str, list_name: str, netbox_ids: dict, hosts) -> dict:
    """What NetBox holds for one network: ``{"site", "devices": {host: record}, "interfaces":
    {device id: [interface]}, "addresses": {device id: [address]}}``. Raises when NetBox does
    not answer, so a failed read keeps the last good value (reader_job rule 3)."""
    from modules.netbox_client import _nb_first, _nb_get, _slug

    site = _nb_first(session, base, "dcim/sites/", slug=_slug(list_name))
    devices = {}
    if site:
        for d in _nb_get(session, base, "dcim/devices/", site_id=site["id"]):
            if d.get("name") in hosts:
                devices.setdefault(d["name"], d)
    by_id = {}
    for chunk in _chunks(i for h, i in netbox_ids.items() if h not in devices):
        for d in _nb_get(session, base, "dcim/devices/", id=chunk):
            by_id[d.get("id")] = d
    for h, i in netbox_ids.items():
        if h not in devices and i in by_id:
            devices[h] = by_id[i]
    ifaces, addrs = {}, {}
    ids = [d["id"] for d in devices.values()]
    for chunk in _chunks(ids):
        for i in _nb_get(session, base, "dcim/interfaces/", device_id=chunk):
            ifaces.setdefault(_ref_id(i.get("device")), []).append(i)
    owner = {i.get("id"): dev for dev, held in ifaces.items() for i in held}
    for chunk in _chunks(ids):
        for a in _nb_get(session, base, "ipam/ip-addresses/", device_id=chunk):
            dev = owner.get(a.get("assigned_object_id")) \
                or owner.get(_ref_id(a.get("assigned_object")))
            if dev is not None:
                addrs.setdefault(dev, []).append(a)
    return {"site": bool(site), "devices": devices, "interfaces": ifaces, "addresses": addrs}


def golden_holds(text: str, excluded: set) -> tuple:
    """``([interface name], [address])`` the import would model from a golden: every interface
    block, and each address on one outside an excluded VRF."""
    from modules.netbox_client import _parse_all_interfaces_from_config

    names, addresses = [], []
    for intf in _parse_all_interfaces_from_config(text or ""):
        names.append(intf["name"])
        if (intf.get("vrf_name") or "").lower() in excluded and intf.get("vrf_name"):
            continue
        addresses += [a for a in ([intf.get("cidr")] + list(intf.get("secondary_ips") or [])
                                  + list(intf.get("ipv6_addresses") or [])) if a]
    return names, addresses


def device_lag(host: str, golden: str, held: dict, cables: list, excluded: set,
               golden_ports: dict = None) -> dict:
    """``{"interfaces", "addresses", "cables", "absent", "netbox_id"}``: what *host*'s committed
    golden and its LLDP *cables* (`lldp_cable_plan`'s, for this device) hold that NetBox
    (*held*, `netbox_holds`'s) does not. A cable counts only where the import can make it: at
    each end, an interface NetBox holds or that end's committed golden has (*golden_ports*,
    ``{device: {name and abbreviation}}``), and a cable at neither end."""
    from modules.netbox_client import _iface_alias_map, _same_address, _shorten_iface_name

    record = held["devices"].get(host)
    names, addresses = golden_holds(golden, excluded)
    nb_ifaces = held["interfaces"].get(record["id"], []) if record else []
    nb_addrs = [a.get("address") for a in held["addresses"].get(record["id"], [])] \
        if record else []
    have = {i.get("name") for i in nb_ifaces}
    ports = dict(golden_ports or {})
    ports.setdefault(host, set(names) | {_shorten_iface_name(n) for n in names})

    def end(dev: str, port: str) -> tuple:
        """(the import can make this end, a cable is on it already)."""
        rec = held["devices"].get(dev)
        held_ifaces = held["interfaces"].get(rec["id"], []) if rec else []
        iid = _iface_alias_map(held_ifaces).get(port)
        on = any(i.get("id") == iid and i.get("cable") for i in held_ifaces) if iid else False
        return bool(iid) or port in (ports.get(dev) or ()), on

    def to_add(c) -> bool:
        (a_ok, a_on), (b_ok, b_on) = end(c["a"], c["port_a"]), end(c["b"], c["port_b"])
        return a_ok and b_ok and not (a_on or b_on)

    return {"absent": record is None,
            "netbox_id": record.get("id") if record else None,
            "interfaces": [n for n in names if n not in have],
            "addresses": [a for a in addresses
                          if not any(_same_address(a, b) for b in nb_addrs)],
            "cables": [f"{c['a']} {c['port_a']} to {c['b']} {c['port_b']}" for c in cables
                       if to_add(c)]}


def network_lag(list_name: str, hosts, goldens: dict, held: dict, stored: dict,
                excluded: set) -> dict:
    """One network's value: ``{"in_netbox", "checked", "devices": {host: lag}, "lldp_error",
    "lldp_at"}``, *devices* holding only the devices that lag."""
    from modules.netbox_client import _shorten_iface_name, lldp_cable_plan

    in_netbox = bool(held["site"] or held["devices"])
    out = {"in_netbox": in_netbox, "checked": 0, "devices": {},
           "lldp_error": stored.get("error", ""), "lldp_at": stored.get("value_at", "")}
    if not in_netbox:
        return out
    ports = {}
    for h, text in goldens.items():
        names = golden_holds(text, excluded)[0]
        ports[h] = set(names) | {_shorten_iface_name(n) for n in names}
    for host in sorted(h for h in hosts if h in goldens):
        out["checked"] += 1
        cables, _reported = lldp_cable_plan(stored.get("links") or [],
                                            stored.get("managed") or {}, {host})
        lag = device_lag(host, goldens[host], held, cables, excluded, golden_ports=ports)
        if lag["interfaces"] or lag["addresses"] or lag["cables"]:
            out["devices"][host] = lag
    return out


def read(population=None, ready=None, goldens_for=None, links_for=None,
         excluded=None) -> dict:
    """``{"configured", "networks": {list: network_lag or {"error"}}}``. Raises when NetBox is
    configured and does not answer. Each argument stands in for its store in a test."""
    from modules import netbox_client as N
    from modules.readers.adjacencies import lists

    ok, why, session, base = (ready or N._nb_ready)()
    if not ok:
        return {"configured": False, "why": why, "networks": {}}
    skip = N.excluded_vrfs() if excluded is None else excluded
    networks = {}
    for list_name, ref, hosts in (population or lists)():
        goldens, ids, err = (goldens_for or goldens_by_device)(list_name, ref, hosts)
        if err:
            networks[list_name] = {"error": err}
            continue
        held = netbox_holds(session, base, list_name, ids, set(hosts))
        stored = (links_for or N.stored_lldp_links)(list_name)
        networks[list_name] = network_lag(list_name, hosts, goldens, held, stored, skip)
    return {"configured": True, "networks": networks}


def stored_for(list_name: str, host: str, cached=None) -> dict:
    """The stored answer for one device, for its NetBox tab: ``{"state": "behind" | "level" |
    "not_judged" | "unread", "lag", "value_at", "why"}``. Read from the store, never NetBox."""
    got = reader_job.read_cached(NAME) if cached is None else cached
    good = (got.get("doc") or {}).get("last_good") or {}
    if not good:
        return {"state": "unread", "lag": None, "value_at": "",
                "why": got.get("why") or "the reader has stored no value yet"}
    v = good.get("value") or {}
    net = (v.get("networks") or {}).get(list_name)
    at = good.get("value_at", "")
    if not v.get("configured") or net is None or net.get("error") or not net.get("in_netbox"):
        why = (v.get("why") if not v.get("configured") else (net or {}).get("error")
               or f"{list_name} is not in NetBox (no site or device record)")
        return {"state": "not_judged", "lag": None, "value_at": at, "why": why or ""}
    lag = (net.get("devices") or {}).get(host)
    return {"state": "behind" if lag else "level", "lag": lag, "value_at": at, "why": "",
            "lldp_error": net.get("lldp_error", "")}


READER = reader_job.register(reader_job.Reader(
    name=NAME,
    what=("whether NetBox holds each device's committed golden: its interfaces, addresses and "
          "LLDP cables the import would add (C1344)"),
    endpoints=("each list's config repository: golden/ at HEAD (one ls-tree, one cat-file "
               "--batch) and the manifest",
               "NetBox: GET /api/dcim/sites/, /api/dcim/devices/, /api/dcim/interfaces/ and "
               "/api/ipam/ip-addresses/ (each network's, 50 devices a request)",
               "this host: the Topology reader's stored LLDP links"),
    interval_seconds=INTERVAL_SECONDS,
    interval_basis=("every write that moves it wakes it at once (an import, an adoption, an "
                    "onboarding's Verify, a deploy's or a save's golden commit: reader_wakes); "
                    "the schedule catches an edit made in NetBox's own screens, and an LLDP link "
                    "the Topology reader found since, within five minutes"),
    read=read,
    invalidates=("netbox",),
    remedy="Read the error above: it names what NetBox or the repository answered",
    window="each device's committed golden and NetBox's records at the read",
))
