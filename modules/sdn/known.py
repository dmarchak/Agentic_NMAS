"""What Mercury knows of an OpenFlow fabric's switches and hosts beside what its controller
lists: NetBox's names, read from the network's committed NSOT export (C3013, C3010, C2950; the
charter's "What Mercury knows is chosen, never typed").

**One read, one pass, three users.** `read` takes the network's committed export once (through
`export.read_in` in the network's own repository, so nothing is resolved or created by name: a
read creates no list) and `shaped` walks it once:
- ``names``: each switch's NetBox name by its datapath id (`openflow_values.datapath_names`, the
  device's custom field ``openflow_datapath_id``): the name a switch is drawn by wherever a
  controller gives only a DPID (`switch_name`, `switch_words`);
- ``rows``: every interface of an end host, and of a device that is not itself a switch, that
  records a MAC or is cabled to a switch port: its name, MAC and addresses, and where its
  cable ends (the switch's DPID and the port's OpenFlow number, each None where NetBox records
  none). Nothing here is keyed on a device's name: every name is the export's.
The SDN trace finds its ends through `resolve`; its form's choices are `options`; Topology's
reader names a learnt host by `host_names`.

**An end of a trace** (`resolve`), for text that is an address, a MAC or a NAME:
1. a host a controller lists with that address or MAC, as before (one at two places is refused,
   each named), carrying its NetBox name and, in a family the controller lists no global
   address for, NetBox's;
2. else NetBox's interface with that name, address or MAC: the host the controller lists with
   its MAC, or, where the controller lists none, NetBox's own place for it (the far end of its
   cable: the switch's DPID and the port's number), said as NetBox's ("the controller has not
   learnt it"); two interfaces at two places are refused, each named;
3. else, for a DESTINATION that is an address: an address-only destination (`address_only`),
   whose MAC nobody knows. Its packet carries `UNKNOWN_MAC` and the answer says so;
4. else refused, naming what was compared with what.

**The states are kept apart** (`read`'s ``state``): ``read``, ``absent`` (no repository, or no
export committed: nothing to look in, which is not "NetBox names none") and ``unreadable`` (an
export that does not verify, or a read that raised), each with its why.
"""

import ipaddress
import logging
import os
import re

log = logging.getLogger(__name__)

_MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
#: The destination MAC of a packet to an address no controller and no NetBox interface holds:
#: the all-zero "not known" value an ARP request itself carries as its target hardware address
#: (RFC 826: the field the request asks to have filled in). A flow that names a destination MAC
#: takes the packet only if it names this one.
UNKNOWN_MAC = "00:00:00:00:00:00"
#: Nothing was read: a caller that asked for no NetBox view (the heal loop's verify, a test).
NOT_ASKED = {"state": "absent", "why": "", "sha": "", "rows": [], "names": {}, "hosts": None,
             "devices": 0}


def _address(text):
    try:
        return ipaddress.ip_address(str(text or "").strip())
    except ValueError:
        return None


def _mac(text) -> str:
    t = str(text or "").strip().lower()
    return t if _MAC.match(t) else ""


def _n(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count != 1 else ''}"


# ───────────────────────────────────────────────────────────────────────────── the export

def rows_of(export: dict) -> list:
    """Every interface of *export* that can be an end of a trace: ``[{"name", "kind" ("end
    host" or "device"), "interface", "mac", "ipv4", "ipv6", "switch", "switch_interface",
    "dpid", "port_no"}]``. An end host's every interface; a device's (one that is not itself a
    switch: no datapath id and no OpenFlow port) only where it records a MAC or its cable
    ends on a switch;
    and the far end of a switch port's cable that the export holds no interface for (a device
    outside the network's list), by its name and place alone. *dpid* (an int) and *port_no*
    are the far end's, None where NetBox records no cable, no datapath id for the switch or no
    OpenFlow number for the port. Pure, one pass."""
    from modules.nsot import export as X
    from modules.sdn import openflow_values as OV

    body = export.get("body") or {}
    dpid_of = {name: int(dpid, 16) for dpid, name in OV.datapath_names(export).items()}
    port_of = OV.port_numbers(export)
    # A switch is a device NetBox gives a datapath id, or one with an OpenFlow port (a switch
    # whose datapath id NetBox does not record is still no trace's end).
    switches = set(dpid_of) | {device for device, _iface in port_of}
    peer = {}
    for c in body.get("cables") or []:
        a, b = c.get("a") or [], c.get("b") or []
        if len(a) == 1 and len(b) == 1:
            peer[tuple(a[0])], peer[tuple(b[0])] = tuple(b[0]), tuple(a[0])

    def row(name, kind, iface, mac, addresses, far):
        v4, v6 = [], []
        for text in addresses or []:
            try:
                a = ipaddress.ip_interface(text).ip
            except ValueError:
                continue
            (v4 if a.version == 4 else v6).append(str(a))
        far = tuple(far) if far else None
        return {"name": str(name), "kind": kind, "interface": str(iface), "mac": _mac(mac),
                "ipv4": v4, "ipv6": v6, "switch": far[0] if far else "",
                "switch_interface": far[1] if far else "",
                "dpid": dpid_of.get(far[0]) if far else None,
                "port_no": port_of.get(far) if far else None}

    out = {}
    for h in X.hosts_of(export) or []:
        for i in h.get("interfaces") or []:
            out[(h.get("name"), i.get("name"))] = row(
                h.get("name"), "end host", i.get("name"), i.get("mac"), i.get("ip_addresses"),
                i.get("attached") or peer.get((h.get("name"), i.get("name"))))
    for i in body.get("interfaces") or []:
        device = i.get("device")
        if not device or device in switches or (device, i.get("name")) in out:
            continue
        far = peer.get((device, i.get("name")))
        if i.get("mac") or (far and far[0] in switches):
            out[(device, i.get("name"))] = row(device, "device", i.get("name"), i.get("mac"),
                                               i.get("ip_addresses"), far)
    # A switch port's cable names its far end even when that device is outside the export
    # (the network's list does not hold it): its name and place, no MAC and no address.
    for near, far in peer.items():
        if near[0] in switches and far[0] and far[0] not in switches and far not in out:
            out[far] = row(far[0], "device", far[1], "", [], near)
    return [out[k] for k in sorted(out, key=lambda k: (str(k[0]), str(k[1])))]


def shaped(export_read: dict) -> dict:
    """`export.read`'s answer as this module's view: ``{"state", "why", "sha", "rows",
    "names": {dpid (int): the switch's NetBox name}, "hosts": the end hosts recorded (None when
    the export predates them), "devices"}``."""
    from modules.nsot import export as X
    from modules.sdn import openflow_values as OV

    if not (export_read or {}).get("ok"):
        return dict(NOT_ASKED, state="absent" if (export_read or {}).get("absent")
                    else "unreadable", why=str((export_read or {}).get("error") or ""))
    doc = export_read["export"]
    hosts = X.hosts_of(doc)
    return {"state": "read", "why": "",
            "sha": str(export_read.get("sha256") or doc.get("sha256") or "")[:12],
            "rows": rows_of(doc),
            "names": {int(d, 16): n for d, n in OV.datapath_names(doc).items()},
            "hosts": None if hosts is None else len(hosts),
            "devices": len((doc.get("body") or {}).get("devices") or [])}


def read(network: str) -> dict:
    """`shaped`'s view of *network*'s committed NSOT export, read in the network's own
    repository and only where one is there: a network with no repository has no export, and
    nothing is made to find out (a read creates no list). A read that raises is ``unreadable``,
    said, never raised."""
    from modules import config
    from modules.nsot import export as X
    from modules.nsot import listref
    from modules.nsot.repo import has_repository

    try:
        if not listref.exists(network):
            return dict(NOT_ASKED, why=f"{network} is not a network")
        repo = os.path.join(config.list_data_path(network), "config_repo")
        if not has_repository(repo):
            return dict(NOT_ASKED, why=f"{network} has no committed NSOT export (its "
                                       "repository holds no commit yet)")
        return shaped(X.read_in(repo, network=network))
    except Exception as exc:                            # noqa: BLE001 (said, never a raise)
        log.warning("sdn known: %s's NSOT export could not be read: %s", network,
                    type(exc).__name__)
        return dict(NOT_ASKED, state="unreadable", why=f"{type(exc).__name__}: {exc}")


# ───────────────────────────────────────────────────────────────────────────── a switch's name

def switch_name(dpid, names: dict) -> str:
    """The NetBox name of the switch with datapath id *dpid* (an int, or 16 hex digits), or
    "" when NetBox names none: *names* is `shaped`'s ``names``."""
    try:
        key = dpid if isinstance(dpid, int) else int(str(dpid), 16)
    except (TypeError, ValueError):
        return ""
    return str((names or {}).get(key) or "")


def described(text) -> str:
    """A switch's own description (its OpenFlow ``dp_desc``) where it gives one: "" for none,
    and for "None", which Open vSwitch reports for a bridge nobody described (the operator's
    kit, 2026-11-11: "'None' for OVS"), so a placeholder is never drawn as a name."""
    said = str(text or "").strip()
    return "" if said.lower() in ("", "none") else said


def labels_of(controllers: list, nb: dict = None) -> dict:
    """``{dpid (int): the switch's name}`` for a fabric (`trace.fabric`'s controllers): the
    NetBox name matched by datapath id (*nb*'s ``names``), else the description the switch
    gives of itself where it gives one (`described`). A switch in neither has no entry, and is
    said by its datapath id (`switch_words`). One pass over the switches."""
    out = {}
    for c in controllers or []:
        for dpid, sw in (c.get("switches") or {}).items():
            own = described((sw or {}).get("name"))
            if own:
                out[int(dpid)] = own
    out.update((nb or {}).get("names") or {})
    return out


def switch_words(dpid, names: dict) -> str:
    """How a switch is named for a person: its name in *names* (`labels_of`'s: NetBox's
    matched by datapath id first), else its datapath id said as one
    (``DPID 0000000000000002``)."""
    name = switch_name(dpid, names)
    if name:
        return name
    try:
        key = dpid if isinstance(dpid, int) else int(str(dpid), 16)
    except (TypeError, ValueError):
        return f"DPID {dpid}"
    return f"DPID {key:016x}"


def names_for(network: str) -> dict:
    """``{dpid (int): the switch's NetBox name}`` for *network*: `read`'s ``names``, {} when
    no export is committed or it cannot be read (logged by `read`). One read for a page that
    draws switches (SDN › Flows, the capability matrix), never one per switch."""
    return dict(read(network).get("names") or {})


def drawn_name(dpid, names: dict, reported="") -> str:
    """The name a page draws a switch by (C3010's one helper): NetBox's, matched by datapath
    id (*names*, `names_for`'s), else the description the switch gives of itself where it
    gives one (`described`: never a placeholder), else "": the page then draws its datapath
    id, shown as one."""
    return switch_name(dpid, names) or described(reported)


def host_names(rows: list) -> dict:
    """``{MAC: (name, interface)}`` for each MAC NetBox records on exactly one interface: the
    device a host a controller learnt is named by (C3010). A MAC on two interfaces names
    neither."""
    seen = {}
    for r in rows or []:
        if r.get("mac"):
            seen.setdefault(r["mac"], set()).add((r["name"], r["interface"]))
    return {mac: next(iter(owners)) for mac, owners in seen.items() if len(owners) == 1}


# ───────────────────────────────────────────────────────────────────────────── a trace's ends

def _where(h: dict, names: dict = None) -> str:
    port = f"port {h['port_no']}" + (f" ({h['port_name']})" if h.get("port_name") else "")
    return f"{switch_words(h['dpid'], names)} {port}"


def end_words(e: dict, names: dict = None) -> str:
    """An end as a person names it: its NetBox name first, then its first global address, its
    MAC, and where it is; an address-only destination by its address."""
    from modules.sdn import topology as T

    if e.get("address_only"):
        return f"{e['address']} (an address no controller lists)"
    address = next((a for a in list(e.get("ipv4") or []) + list(e.get("ipv6") or [])
                    if T.is_global(a)), "")
    lead = ", ".join(x for x in (e.get("name"), address) if x) or e.get("mac", "")
    words = f"{lead} ({e.get('mac', '')}) on {_where(e, names)}"
    return words if e.get("learnt", True) else f"{words}, by NetBox's cable"


def _has(h: dict, addr, mac: str) -> bool:
    if mac and h.get("mac") == mac:
        return True
    if addr is None:
        return False
    return addr in {_address(a) for a in list(h.get("ipv4") or []) + list(h.get("ipv6") or [])}


def _row_has(r: dict, addr, mac: str) -> bool:
    if mac and r.get("mac") == mac:
        return True
    return addr is not None and str(addr) in (r["ipv4"] if addr.version == 4 else r["ipv6"])


def _row_words(r: dict) -> str:
    where = (f", cabled to {r['switch']} {r['switch_interface']}" if r.get("switch") else "")
    return f"{r['interface']}{where}"


def _source(r: dict) -> str:
    return "NetBox's end hosts" if r["kind"] == "end host" else "NetBox's devices"


def _by_mac(rows: list) -> dict:
    """``{MAC: its row}`` for each MAC NetBox records on exactly one interface."""
    owners = host_names(rows)
    return {r["mac"]: r for r in rows or []
            if r["mac"] in owners and owners[r["mac"]] == (r["name"], r["interface"])}


def _enriched(c: dict, h: dict, nb: dict, row: dict = None, index: dict = None) -> dict:
    """A controller's host as an end: its own fields, its controller's name, its NetBox name
    (by *row*, else by its MAC where NetBox records that MAC once: *index* is `_by_mac`'s, for
    a caller with many hosts) and, in a family the controller lists no global address for,
    NetBox's addresses."""
    from modules.sdn import topology as T

    end = dict(h, controller=c.get("name", ""), learnt=True, name="", interface="", kind="")
    if row is None:
        row = (_by_mac(nb.get("rows")) if index is None else index).get(h.get("mac"))
    if row is not None:
        end.update(name=row["name"], interface=row["interface"], kind=row["kind"])
        for family in ("ipv4", "ipv6"):
            if not any(T.is_global(a) for a in h.get(family) or []) and row[family]:
                end[family] = list(h.get(family) or []) + list(row[family])
                end["netbox_addresses"] = True
    return end


def _one_place(found: list, text: str, nb: dict):
    """The one (controller, host) of *found*, or `Refused` naming each place."""
    from modules.sdn.trace import Refused

    places = {(c["name"], h["mac"], int(h["dpid"]), h["port_no"]) for c, h in found}
    if len(places) > 1:
        names = nb.get("names")
        said = " and ".join(sorted(end_words(dict(h, learnt=True), names) for _c, h in found))
        shown = sorted((dict(h, words=end_words(dict(h, learnt=True), names))
                        for _c, h in found), key=lambda h: h["words"])
        raise Refused(f"{text} is listed at {len(places)} places: {said}; the controller keeps "
                      "a host until it restarts, so one may be old: give its MAC", places=shown)
    return found[0]


def resolve(controllers: list, text: str, nb: dict = None, end: str = "source") -> dict:
    """The end of a trace *text* names (the module's four steps), among the hosts
    *controllers* (`trace.fabric`'s) list on an edge port and NetBox's view *nb* (`read`'s;
    None: no NetBox view was asked for). ``{"mac", "dpid", "port_no", "port_name", "ipv4",
    "ipv6", "controller", "name", "interface", "kind", "learnt", "note"}``, or, for an
    address-only destination, ``{"address_only": True, "address", "mac": UNKNOWN_MAC, ...}``.
    *note* says how a name or a NetBox address was resolved, for the answer. Raises
    `trace.Refused` naming what was compared."""
    from modules.sdn.trace import Refused

    # Every place is said by the switch's name: NetBox's, else its own (`labels_of`).
    nb = dict(nb or NOT_ASKED)
    nb["names"] = labels_of(controllers, nb)
    text = str(text or "").strip()
    addr, mac = _address(text), _mac(text)
    listed = [(c, h) for c in controllers for h in c["hosts"]]
    if addr is not None or mac:
        found = [(c, h) for c, h in listed if _has(h, addr, mac)]
        if found:
            c, h = _one_place(found, text, nb)
            return dict(_enriched(c, h, nb), note="")
        rows = [r for r in nb.get("rows") or [] if _row_has(r, addr, mac)]
        if rows:
            return _by_rows(controllers, listed, rows, text, nb)
        if addr is not None and end == "destination":
            family = "ipv4" if addr.version == 4 else "ipv6"
            return {"address_only": True, "address": str(addr), "mac": UNKNOWN_MAC,
                    "ipv4": [], "ipv6": [], family: [str(addr)], "name": "", "learnt": False,
                    "note": ""}
        words = (f"no controller lists a host with {text} on an edge port "
                 f"({_n(len(listed), 'host')} listed)")
        if nb["state"] == "read":
            words += f", and NetBox's NSOT export ({nb['sha']}) records no interface with it"
        elif nb["state"] == "unreadable":
            words += f", and NetBox's NSOT export could not be read: {nb['why']}"
        raise Refused(words)
    # A name: NetBox's, from the committed export.
    head = f"{text!r} is not an IPv4 or IPv6 address or a MAC"
    if nb["state"] != "read":
        if not nb.get("why"):
            raise Refused(head)
        raise Refused(f"{head}, and no end host can be looked up by name: {nb['why']}")
    rows = [r for r in nb["rows"] if r["name"].lower() == text.lower()]
    if not rows:
        if nb["hosts"] is None:
            raise Refused(f"{head}, and NetBox's NSOT export ({nb['sha']}) was built before "
                          "end hosts were recorded, so it names none, and it names no device "
                          f"{text!r} with a MAC or a cable to a switch: commit the export "
                          "again")
        raise Refused(f"{head}, and NetBox's NSOT export ({nb['sha']}) names no end host "
                      f"{text!r} ({_n(nb['hosts'], 'end host')} recorded) and no device "
                      f"{text!r} with a MAC or a cable to a switch")
    return _by_rows(controllers, listed, rows, text, nb)


def _by_rows(controllers: list, listed: list, rows: list, text: str, nb: dict) -> dict:
    """The end NetBox's interfaces *rows* name: the host a controller lists with one of their
    MACs, else NetBox's own place for the one that has one."""
    from modules.sdn.trace import Refused

    named, sha = rows[0]["name"], nb.get("sha", "")
    by_mac = {r["mac"]: r for r in rows if r["mac"]}
    learnt = [(c, h) for c, h in listed if h.get("mac") in by_mac]
    if learnt:
        if len({h["mac"] for _c, h in learnt}) > 1:
            shown = sorted({h["mac"]: {"mac": h["mac"], "words": f"{named} "
                                       f"{by_mac[h['mac']]['interface']} ({h['mac']})"}
                            for _c, h in learnt}.values(), key=lambda p: p["words"])
            raise Refused(
                f"{_source(rows[0])[:-1]} {named} (the NSOT export {sha}) has {len(shown)} "
                "interfaces a controller lists: " + " and ".join(p["words"] for p in shown)
                + ": give the one to trace", places=shown)
        c, h = _one_place(learnt, text, nb)
        r = by_mac[h["mac"]]
        return dict(_enriched(c, h, nb, r),
                    note=f"{r['name']} is {r['mac']} ({_row_words(r)}) by {_source(r)}, in "
                         f"the NSOT export {sha}")
    # No MAC of its own in NetBox: the host a controller lists on the port its cable ends on.
    by_port = {}
    for r in rows:
        if not r["mac"] and r["dpid"] is not None and r["port_no"] is not None:
            for c, h in listed:
                if (int(h["dpid"]), h["port_no"]) == (r["dpid"], r["port_no"]):
                    by_port[(c["name"], h["mac"], r["dpid"], r["port_no"])] = (c, h, r)
    if len(by_port) > 1:
        names = nb.get("names")
        shown = sorted(({"mac": h["mac"], "words": end_words(dict(h, learnt=True), names)}
                        for _c, h, _r in by_port.values()), key=lambda p: p["words"])
        raise Refused(f"NetBox (the NSOT export {sha}) records no MAC for {named}, and "
                      f"{len(shown)} hosts are listed where its cable ends: "
                      + " and ".join(p["words"] for p in shown) + ": give the one to trace",
                      places=shown)
    if by_port:
        c, h, r = next(iter(by_port.values()))
        return dict(_enriched(c, h, nb), name=r["name"], interface=r["interface"],
                    kind=r["kind"],
                    note=f"{r['name']} is {h['mac']}: NetBox (the NSOT export {sha}) cables "
                         f"{r['name']} {r['interface']} to {r['switch']} "
                         f"{r['switch_interface']} (port {r['port_no']}) and records no MAC "
                         f"for it, and {c['name']} lists that one host on the port")
    if not by_mac:
        raise Refused(f"{_source(rows[0])[:-1]} {named} (the NSOT export {sha}) records no MAC "
                      f"on {', '.join(r['interface'] for r in rows)}, so the controller's "
                      "hosts cannot be matched to it"
                      + ("" if not any(r["dpid"] is not None and r["port_no"] is not None
                                       for r in rows) else
                         ", and no controller lists a host on the port its cable ends on"))
    placed = {(r["mac"], r["dpid"], r["port_no"]): r for r in by_mac.values()
              if r["dpid"] is not None and r["port_no"] is not None}
    if not placed:
        raise Refused(
            f"no controller lists a host with {named}'s MAC ("
            + ", ".join(f"{r['interface']} {r['mac']}" for r in by_mac.values())
            + f"), and NetBox (the NSOT export {sha}) records no switch port for it: "
            + "; ".join(_unplaced(r) for r in by_mac.values()))
    if len(placed) > 1:
        shown = sorted(({"mac": r["mac"], "words": f"{named} {r['interface']} ({r['mac']})"}
                        for r in placed.values()), key=lambda p: p["words"])
        raise Refused(f"{_source(rows[0])[:-1]} {named} (the NSOT export {sha}) has "
                      f"{len(shown)} interfaces with a MAC: "
                      + " and ".join(f"{r['interface']} {r['mac']}" for r in placed.values())
                      + ": give the one to trace", places=shown)
    r = next(iter(placed.values()))
    c = next((c for c in controllers if r["dpid"] in c["switches"]), None)
    if c is None:
        raise Refused(f"NetBox (the NSOT export {sha}) cables {named} {r['interface']} to "
                      f"{r['switch']} {r['switch_interface']} (datapath id {r['dpid']:016x}, "
                      f"port {r['port_no']}), a switch no controller of this network lists")
    sw = c["switches"][r["dpid"]]
    return {"mac": r["mac"], "dpid": r["dpid"], "port_no": r["port_no"],
            "port_name": str((sw.get("ports") or {}).get(r["port_no"]) or ""),
            "ipv4": list(r["ipv4"]), "ipv6": list(r["ipv6"]), "controller": c["name"],
            "name": r["name"], "interface": r["interface"], "kind": r["kind"],
            "learnt": False, "netbox_addresses": True,
            "note": (f"{c['name']} has not learnt {r['name']} ({r['mac']}): its place, "
                     f"{r['switch']} {r['switch_interface']} (port {r['port_no']}), and its "
                     f"addresses are NetBox's ({_row_words(r)}, by {_source(r)}, in the NSOT "
                     f"export {sha})")}


def _unplaced(r: dict) -> str:
    if not r["switch"]:
        return f"{r['interface']} has no cable recorded"
    if r["dpid"] is None:
        return f"{r['switch']} records no openflow_datapath_id"
    return f"{r['switch']} {r['switch_interface']} records no openflow_port"


# ───────────────────────────────────────────────────────────────────────────── the choices

def options(controllers: list, nb: dict = None) -> list:
    """The hosts Mercury knows, as a form offers them (the charter: the NetBox name first, then
    the MAC, then the address; a host with no NetBox match by its switch and port):
    ``[{"value", "label", "name", "mac", "address", "learnt"}]``, NetBox-named ones first by
    name, then the rest by switch and port. *value* is what a trace takes: the host's MAC,
    which names one host whatever its interfaces. A host on a port that is a link, and a NetBox interface with
    no MAC or no place, is not offered: no trace can start or end there."""
    from modules.sdn import topology as T

    nb = nb or NOT_ASKED
    names = labels_of(controllers, nb)
    index = _by_mac(nb.get("rows"))
    out, seen = [], set()

    def address(e):
        return next((a for a in list(e.get("ipv4") or []) + list(e.get("ipv6") or [])
                     if T.is_global(a)), "")

    for c in controllers or []:
        for h in c["hosts"]:
            key = (h["mac"], int(h["dpid"]), h["port_no"])
            if key in seen:
                continue
            seen.add(key)
            e = _enriched(c, h, nb, index=index)
            name = e["name"]
            parts = [name or _where(h, names), h["mac"], address(e)]
            if name:
                parts.append(f"on {_where(h, names)}")
            out.append({"value": h["mac"], "label": " · ".join(p for p in parts if p),
                        "name": name, "mac": h["mac"], "address": address(e),
                        "learnt": True})
    known = {o["mac"] for o in out}
    for r in nb.get("rows") or []:
        if not r["mac"] or r["mac"] in known or r["dpid"] is None or r["port_no"] is None \
                or not any(r["dpid"] in c["switches"] for c in controllers or []):
            continue
        known.add(r["mac"])
        parts = [r["name"], r["mac"], address(r),
                 f"on {switch_words(r['dpid'], names)} port {r['port_no']}, by NetBox's cable "
                 "(not learnt by the controller)"]
        out.append({"value": r["mac"], "label": " · ".join(p for p in parts if p),
                    "name": r["name"], "mac": r["mac"], "address": address(r),
                    "learnt": False})
    return sorted(out, key=lambda o: (not o["name"], o["name"].lower(), o["label"]))
