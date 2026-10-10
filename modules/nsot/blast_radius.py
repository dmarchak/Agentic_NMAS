"""nsot/blast_radius.py — what else Mercury loses reach to while one device restarts (P.14,
gate 6; cutover blocker 6, 2026-10-10).

From records, never a probe: committed intent gives every device's IPv4 interfaces (each
interface a subnet it is attached to), and this host's own interface addresses say which
subnets Mercury is attached to. Devices and subnets form a graph; a device is reachable while a
path joins one of Mercury's subnets to a subnet holding the device's management address. The
blast radius of restarting X is every device reachable with X present and unreachable without
it.

Two rules make it conservative, never optimistic:
- **A switch's VLAN subnets go down with it.** A `Vlan<n>` interface is a switch routing a
  VLAN it most likely carries at layer 2 too, so its subnets are removed with it (other
  members of that VLAN may hang off it). A subnet carried at layer 2 by a switch with no
  address in it cannot be seen from intent at all: the result says so.
- An interface intent marks shut is no attachment.

What it cannot say, stated with the answer: routing may not follow every link (a path intent
connects that the routing does not use still counts as reach); a device with no committed
intent is no node; and this host's addresses are read where Mercury runs.
"""

import ipaddress
import logging

log = logging.getLogger(__name__)

CAVEAT = ("from committed intent's subnets and this host's addresses: a path the routing does "
          "not use still counts as reach, and a switch carrying a subnet at layer 2 with no "
          "address in it is not seen")


def _attachments(intents: dict) -> dict:
    """``{device: [(network, interface_name), ...]}`` for every addressed, not-shut IPv4
    interface in committed intent."""
    out = {}
    for host, hv in (intents or {}).items():
        rows = []
        for iface in (hv or {}).get("interfaces") or []:
            if iface.get("shutdown"):
                continue
            raw = (iface.get("ipv4") or "").strip()
            if not raw:
                continue
            try:
                ip = ipaddress.ip_interface(raw.replace(" ", "/"))
            except ValueError:
                continue
            rows.append((ip.network, iface.get("name", "")))
        out[host] = rows
    return out


def _addresses(intents: dict) -> dict:
    """``{device: {ip, ...}}``: every address a device holds (its management address is one)."""
    out = {}
    for host, hv in (intents or {}).items():
        found = set()
        for iface in (hv or {}).get("interfaces") or []:
            raw = (iface.get("ipv4") or "").strip()
            try:
                found.add(ipaddress.ip_interface(raw.replace(" ", "/")).ip)
            except ValueError:
                pass
        out[host] = found
    return out


def _reachable(attach: dict, mine: list, gone: str = "") -> set:
    """The devices a path reaches from Mercury's subnets, *gone* removed with its VLAN
    subnets."""
    removed_nets = {net for net, name in attach.get(gone, [])
                    if name.lower().startswith("vlan")} if gone else set()
    nets_of = {d: {n for n, _name in rows} - removed_nets
               for d, rows in attach.items() if d != gone}
    frontier = {n for n in mine if n not in removed_nets}
    seen_nets, seen_devs = set(frontier), set()
    while frontier:
        nxt = set()
        for dev, nets in nets_of.items():
            if dev in seen_devs or not (nets & frontier):
                continue
            seen_devs.add(dev)
            nxt |= nets - seen_nets
        seen_nets |= nxt
        frontier = nxt
    return seen_devs


def radius(intents: dict, host_networks: list, device: str) -> dict:
    """PURE. ``{"state", "cut", "attached", "why"}`` for restarting *device*.

    *state* is ``known`` (``cut`` lists the devices Mercury loses reach to, sorted, possibly
    none) or ``unknown`` with *why* (no intent for the device, or no subnet of this host's
    holds any device)."""
    attach = _attachments(intents)
    if device not in attach:
        return {"state": "unknown", "cut": [], "attached": [],
                "why": f"{device} has no committed intent, so its links are not known"}
    mine = []
    for net in host_networks or []:
        try:
            mine.append(ipaddress.ip_network(net, strict=False))
        except ValueError:
            continue
    devices_on_mine = sorted(d for d, rows in attach.items()
                             if any(n in mine for n, _ in rows))
    if not devices_on_mine:
        return {"state": "unknown", "cut": [], "attached": [],
                "why": ("no subnet this host is on holds any device's interface, so where "
                        "Mercury attaches to the network is not known")}
    before = _reachable(attach, mine)
    after = _reachable(attach, mine, gone=device)
    cut = sorted(before - after - {device})
    return {"state": "known", "cut": cut, "attached": devices_on_mine, "why": CAVEAT}


def host_networks() -> list:
    """This host's IPv4 networks, from its interfaces (loopback left out), read every time."""
    import socket

    import psutil

    out = []
    for _name, entries in psutil.net_if_addrs().items():
        for a in entries:
            if a.family != socket.AF_INET or not a.netmask:
                continue
            try:
                net = ipaddress.ip_network(f"{a.address}/{a.netmask}", strict=False)
            except ValueError:
                continue
            if not net.is_loopback:
                out.append(str(net))
    return out


def for_device(repo: str, device: str) -> dict:
    """The radius of restarting *device* in the network whose repository is *repo*: committed
    intent read in two git calls (`neighbours.committed_intents`), this host's networks read
    now. A failure to read either is ``unknown`` with its reason, never "none"."""
    from modules.neighbours import committed_intents

    intents, error = committed_intents(repo)
    if not intents and error:
        return {"state": "unknown", "cut": [], "attached": [], "why": error}
    try:
        nets = host_networks()
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        return {"state": "unknown", "cut": [], "attached": [],
                "why": f"this host's addresses could not be read ({exc})"}
    return radius(intents, nets, device)
