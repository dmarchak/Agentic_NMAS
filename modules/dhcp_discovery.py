"""Board L's discovery range (NSOT_STAGE7_PLAN 16; canvas `ZtpDiscovery.dc.html`): addresses on
the ZTP segment for a device no reservation names, so it can ask, be seen, and be picked by a
person. Never a boot file, router or DNS option: a configless device given one reaches out.

Two parts, both measured on a throwaway kea-dhcp4 2.4.1 before they were relied on (2026-10-11):

- **Two client classes in Kea's main file** (root's, so the one-time host step installs them):
  ``nmas-discovery-pnp`` (vendor class ``ciscopnp``, option 60) and ``nmas-discovery`` (any), each
  a 300 s lease. Kea's classes are GLOBAL and a class's lease time beats every subnet's
  (measured: an unreserved client in a 365-day subnet was offered 300 s), so each class is
  confined to the ZTP subnet's own clients: not KNOWN (no reservation), not relayed, and arrived
  on the ZTP subnet's interface. Measured: such a client is offered 300 s from its pool; a
  reserved one its reservation and boot file at the subnet's lifetime; an unknown client RELAYED
  into another subnet keeps that subnet's lifetime, with or without ``ciscopnp``.
- **Two pools in the ZTP subnet**, ``ciscopnp``'s first, written to Mercury's subnet file through
  board C's one write path (`dhcp_subnets.apply_edit`, this module's `plan` as its planner): Kea's
  own check on a candidate, ``config-reload``, read back (exactly the ZTP subnet changed),
  recorded. The pool a lease came from then says its vendor class.

The ZTP subnet is ZTP's own rule (`ztp.ztp_subnets`: the subnet holding this host's address on
an interface Kea listens on), so it is reached directly, never through a relay.
"""

import hashlib
import ipaddress
import json
import logging
import re

log = logging.getLogger(__name__)

PNP, ANY = "nmas-discovery-pnp", "nmas-discovery"
CLASSES = (PNP, ANY)
#: What each discovery pool is for, drawn under its range where the pool carries no description
#: of its own (C709, board C revised).
CLASS_WORDS = {PNP: "discovery: Cisco PnP (vendor class ciscopnp)",
               ANY: "discovery: any other vendor"}
#: The vendor class a C8000v sends (option 60, measured in the throwaway session 2026-10-05).
VENDOR = "ciscopnp"
#: Board L's lease: five minutes, so a device that stops asking leaves the range soon and the
#: page's "asking now" is a lease within this time. A design value (board L), not a measurement.
LEASE_S = 300
#: Thirty-two addresses, two pools of sixteen: sixteen devices of each kind asking at once.
SIZE = 32
_IFACE = re.compile(r"^[A-Za-z0-9_.:-]{1,15}$")


class Refused(Exception):
    pass


def host_addrs() -> dict:
    """This host's IPv4 addresses by interface (what `ztp.ztp_subnets` reads)."""
    import socket

    import psutil
    return {name: [a.address for a in entries if a.family == socket.AF_INET]
            for name, entries in psutil.net_if_addrs().items()}


def segment(dhcp4: dict, addrs=None) -> dict:
    """``{id, prefix, iface, address}``: the ZTP subnet and the interface Kea answers it on.
    Refused unless exactly one subnet is ZTP's."""
    from modules.nsot import ztp

    if addrs is None:
        addrs = host_addrs()
    found = ztp.ztp_subnets(dhcp4, addrs)
    if len(found) != 1:
        raise Refused(f"{len(found)} subnets are ZTP's (a subnet holding this host's address on "
                      "an interface Kea listens on); the discovery range needs exactly one")
    subnet, address = found[0]
    iface = next((i for i, a in addrs.items() if address in a), "")
    if not _IFACE.match(iface or ""):
        raise Refused(f"the ZTP subnet's interface {iface!r} is not a name Kea's expression can "
                      "carry")
    return {"id": subnet.get("id"), "prefix": subnet.get("subnet", ""), "iface": iface,
            "address": address}


def confined(iface: str) -> str:
    """The test every discovery class carries: the ZTP subnet's own clients only."""
    if not _IFACE.match(iface or ""):
        raise Refused(f"{iface!r} is not an interface name")
    return f"not member('KNOWN') and pkt4.giaddr == 0.0.0.0 and pkt.iface == '{iface}'"


def classes(iface: str) -> list:
    base = confined(iface)
    return [{"name": PNP, "test": f"{base} and substring(option[60].hex,0,8) == '{VENDOR}'",
             "valid-lifetime": LEASE_S},
            {"name": ANY, "test": base, "valid-lifetime": LEASE_S}]


def _ours(found) -> list:
    return [{k: c.get(k) for k in ("name", "test", "valid-lifetime")}
            for c in found or [] if isinstance(c, dict) and c.get("name") in CLASSES]


def classes_plan(main_text: str, main: str, running: dict, iface: str) -> dict:
    """Kea's main file with the two classes: ``{state: add|done|refused, refused, candidate}``.
    Done when Kea RUNS exactly these classes; refused when Kea's file has client classes of its
    own (adding to someone's list is not this step's) or the subnet key is not found once."""
    from modules import dhcp_subnets as S

    want = classes(iface)
    out = {"state": "refused", "refused": "", "candidate": main_text}
    have = running.get("client-classes") or []
    if _ours(have) == want and len(have) == len(want):
        out["state"] = "done"
        return out
    if have or S._keys(main_text, "client-classes"):                       # noqa: SLF001
        names = ", ".join(str(c.get("name")) for c in have if isinstance(c, dict))
        out["refused"] = (f"{main} already has client classes ({names or 'in its text'}): the "
                          "discovery classes are added only where there are none")
        return out
    hits = S._keys(main_text, "subnet4")                                   # noqa: SLF001
    if len(hits) != 1:
        out["refused"] = f'"subnet4" is found {len(hits)} times as a key in {main}; expected once'
        return out
    at = hits[0][0]
    line_start = main_text.rfind("\n", 0, at) + 1
    indent = main_text[line_start:at]
    if indent.strip():
        out["refused"] = f'"subnet4" in {main} does not start its own line'
        return out
    block = json.dumps(want, indent=4).replace("\n", "\n" + indent)
    out.update(state="add", candidate=(main_text[:line_start] + indent + '"client-classes": '
                                       + block + ",\n" + main_text[line_start:]))
    return out


def pools(rng: str) -> list:
    """The two pools of *rng* (a /27): ``ciscopnp``'s the lower half, the rest's the upper."""
    net = ipaddress.ip_network(rng, strict=True)
    if net.version != 4 or net.num_addresses != SIZE:
        raise Refused(f"{rng} is not an IPv4 block of {SIZE} addresses")
    half = list(net.subnets(prefixlen_diff=1))
    return [{"pool": f"{h[0]} - {h[-1]}", "client-class": c} for h, c in zip(half, CLASSES)]


def _taken(dhcp4: dict, subnet: dict, leases: list, intent: dict, host: str) -> list:
    """Every address in the ZTP subnet something already holds, with what holds it."""
    from modules import dhcp_reservations as D

    out = []
    for r in D.every_reservation(dhcp4, "IPv4"):
        out += [(a, f"a reservation ({r.get('identity')})") for a in r.get("addresses") or []]
    out += [(l.get("ip-address", ""), "a lease") for l in leases if l.get("state", 0) == 0]
    from modules.dhcp_subnets import pool_span

    for p in subnet.get("pools") or []:
        try:
            a, b = pool_span(p.get("pool", ""))
        except ValueError:
            continue
        out += [(str(a), f"the pool {p.get('pool')}"), (str(b), f"the pool {p.get('pool')}")]
    for rows in (intent or {}).get("IPv4", {}).values():
        for row in rows:
            out.append((row.get("address", ""), f"{row.get('device')} {row.get('iface')} "
                                                "(committed intent)"))
            out += [(g, f"{row.get('device')}'s VRRP address (committed intent)")
                    for g in row.get("gateway") or []]
    out.append((host, "this host (the ZTP server)"))
    return [(a, why) for a, why in out if a]


def free_range(dhcp4: dict, subnet: dict, leases: list, intent: dict, host: str) -> str:
    """The highest block of 32 aligned addresses in the ZTP subnet that holds nothing (no
    reservation, lease, pool, intent address or this host) and not the broadcast address."""
    net = ipaddress.ip_network(subnet.get("subnet", ""), strict=False)
    if net.num_addresses < 2 * SIZE:
        raise Refused(f"the ZTP subnet {net} is too small for a discovery range of {SIZE}")
    taken = []
    for a, why in _taken(dhcp4, subnet, leases, intent, host):
        try:
            taken.append((ipaddress.ip_address(a), why))
        except ValueError:
            continue
    for block in reversed(list(net.subnets(new_prefix=32 - (SIZE.bit_length() - 1)))):
        if net.broadcast_address in block or net.network_address in block:
            continue
        if not any(a in block for a, _w in taken):
            return str(block)
    raise Refused(f"no block of {SIZE} addresses in {net} is free of reservations, leases, "
                  "pools and intent's addresses")


def check_range(rng: str, dhcp4: dict, subnet: dict, leases: list, intent: dict, host: str):
    """Refused, naming what holds an address in *rng*, unless it is free and inside the subnet."""
    block = ipaddress.ip_network(rng, strict=True)
    net = ipaddress.ip_network(subnet.get("subnet", ""), strict=False)
    if not block.subnet_of(net):
        raise Refused(f"{rng} does not lie inside the ZTP subnet {net}")
    if net.broadcast_address in block or net.network_address in block:
        raise Refused(f"{rng} holds {net}'s network or broadcast address")
    held = [f"{a} ({why})" for a, why in _taken(dhcp4, subnet, leases, intent, host)
            if _in(a, block)]
    if held:
        raise Refused(f"{rng} is not free: " + "; ".join(held[:5])
                      + (f"; and {len(held) - 5} more" if len(held) > 5 else ""))


def _in(a: str, block) -> bool:
    try:
        return ipaddress.ip_address(a) in block
    except ValueError:
        return False


def running(dhcp4: dict, addrs=None) -> dict:
    """The discovery range as Kea RUNS it: ``{state: on|off|partial, id, prefix, iface, pools:
    [{pool, class}], classes: [names], lifetime, problem}``. A read of Kea's configuration."""
    out = {"state": "off", "id": None, "prefix": "", "iface": "", "pools": [], "classes": [],
           "lifetime": None, "problem": ""}
    try:
        seg = segment(dhcp4, addrs)
    except Refused as exc:
        out["problem"] = str(exc)
        return out
    out.update(id=seg["id"], prefix=seg["prefix"], iface=seg["iface"])
    have = _ours(dhcp4.get("client-classes"))
    out["classes"] = [c["name"] for c in have]
    out["lifetime"] = next((c["valid-lifetime"] for c in have), None)
    subnet = next((s for s in dhcp4.get("subnet4") or [] if s.get("id") == seg["id"]), {})
    out["pools"] = [{"pool": p.get("pool", ""), "class": p.get("client-class")}
                    for p in subnet.get("pools") or [] if p.get("client-class") in CLASSES]
    if have == classes(seg["iface"]) and [p["class"] for p in out["pools"]] == list(CLASSES):
        out["state"] = "on"
    elif have or out["pools"]:
        out["state"] = "partial"
        out["problem"] = (f"Kea runs {len(have)} of the 2 discovery classes as written and "
                          f"{len(out['pools'])} of the 2 pools")
    return out


def plan(list_name: str, values, kea=None, intent=None, addrs=None) -> dict:
    """The pools' change, shaped as board C's subnet plan (op "edit" on the ZTP subnet) so board
    C's one write path applies it. *values*: ``{"family": "IPv4", "range": <a /27, or empty for
    the free one>}``. A read: Kea is asked, Mercury's subnet file and intent are read."""
    from modules import dhcp_reservations as D
    from modules import dhcp_subnets as S

    p = {"ok": False, "refused": "", "op": "edit", "family": "IPv4", "id": None, "prefix": "",
         "title": "", "change": [], "checks": [], "leases": [], "survives": [], "ack": False,
         "before": None, "after": None, "path": "", "version": "", "hash": "", "subject": "",
         "range": ""}
    try:
        subnets, config, kea = S._state(list_name, {"family": "IPv4"}, p, kea, None,  # noqa: SLF001
                                        D)
        seg = segment(config, addrs)
        if _ours(config.get("client-classes")) != classes(seg["iface"]):
            raise Refused("Kea does not run the two discovery classes yet: the host step "
                          "installs them in Kea's main file before the pools")
        hit = [x for x in subnets if x.get("id") == seg["id"]]
        if len(hit) != 1:
            raise Refused(f"the ZTP subnet {seg['id']} is in Mercury's IPv4 subnet file "
                          f"{len(hit)} times")
        before = hit[0]
        if [x.get("client-class") for x in before.get("pools") or []
                if x.get("client-class") in CLASSES]:
            raise Refused(f"the ZTP subnet {seg['id']} already has discovery pools")
        if before.get("pools"):
            raise Refused(f"the ZTP subnet {seg['id']} has pools of its own "
                          f"({', '.join(x.get('pool', '') for x in before['pools'])}): it hands "
                          "out addresses already, and the discovery range is added only to a "
                          "reservations-only ZTP subnet")
        if intent is None:
            from modules.readers.dhcp import intent_facts
            intent = intent_facts(list_name)
        leases = D.kea_leases(kea, "IPv4")
        rng = (dict(values or {}).get("range") or "").strip()
        if rng:
            check_range(rng, config, before, leases, intent, seg["address"])
        else:
            rng = free_range(config, before, leases, intent, seg["address"])
        new = pools(rng)
    except (Refused, S.Refused, D.Refused, ValueError) as exc:
        p["refused"] = str(exc)
        return p
    after = json.loads(json.dumps(before))
    after["pools"] = new
    p.update(id=seg["id"], prefix=seg["prefix"], before=before, after=after, range=rng,
             title=f"The discovery range {rng} in the ZTP subnet {seg['prefix']}",
             subject=f"dhcp: the discovery range {rng} in the ZTP subnet {seg['id']} "
                     f"({seg['prefix']})")
    p["change"] = [(" ", f"subnet {seg['id']} ({seg['prefix']}), ZTP's: reservations only")] + [
        ("+", f"pool {x['pool']} for {x['client-class']}") for x in new]
    p["checks"] = [("pass", f"{rng} holds no reservation, lease, pool, intent address or this "
                            "host's address"),
                   ("pass", f"Kea runs the two discovery classes, confined to {seg['iface']}'s "
                            f"own clients, {LEASE_S} s each")]
    p["hash"] = hashlib.sha256(json.dumps(
        {k: p[k] for k in ("op", "family", "id", "before", "after", "version")},
        sort_keys=True).encode("utf-8")).hexdigest()
    p["ok"] = True
    return p
