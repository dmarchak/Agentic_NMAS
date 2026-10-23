"""P.6: zero-touch provisioning -- the reservation writer and D4's posture.

ZTP is `dhcp` plus two things the tool does itself: it WRITES the Kea
reservation (this module) and it SERVES the bootstrap config (the responder).
Everything the node does after it fetches its config is Phase 2 unchanged.
Scope and decisions: docs/P6_ZTP.md. Measurements: docs/P6_ZTP_PROBE.md.

**The writer (D1).** A reservation is written into a fragment file the tool
owns, which one Kea subnet pulls in by `<?include?>`. Never by `config-set`
alone: kea-dhcp4.conf is root-owned, so `config-write` cannot persist, and a
reservation held only in memory answers every read correctly and is gone at
Kea's next restart (register C49, demonstrated by M5: the file's reservation
survived a restart and the config-set one did not, in the same run).

Every write is:
  1. checked per device (MAC or address already reserved; address leased to
     another MAC; no Kea subnet contains the address; D4);
  2. tested as a CANDIDATE with `kea-dhcp4 -t` against a copy of the main
     config that includes the candidate, before the live fragment is
     touched. A failed `config-reload` keeps the old config running and a
     bad file on disk, which the next restart would find;
  3. swapped in by rename, then `config-reload`;
  4. READ BACK from the running server, and refused unless exactly the
     intended reservations changed, naming both operands.

A set in, per-device outcomes out: P.6 proves one device, and the bulk job
that comes after Stage 7 must not need a different writer.

**D4 (decided 2026-09-26, refined by M3).** A configless IOS-XE node with a
resolver and a route out phones Cisco before it finds anything local, and its
parameter request list ASKS for routers (3), DNS (6) and static routes (33).
Kea sends a requested option wherever it is configured, so the posture held
only because nobody had configured them: held by absence. Two conditions,
both CHECKED:
  1. no route or resolver option reaches a reservation in the ZTP subnet, at
     any level: global, shared-network, subnet or the reservation itself;
     client classes are reported as not ruled out;
  2. nothing on the ZTP segment answers DNS. With no resolver the node
     broadcast its queries to 255.255.255.255:53 (M3: 8 queries, 0
     replies); a host that answered would hand it a resolver with no DHCP
     option at all.

**A device behind a relay (C1346)** is `modules/nsot/ztp_relayed.py`'s: a subnet declared
relayed for ZTP has its own reservations file (this writer routes to it), its server is the
relay's helper target that is this host's, option 3 may be the relay's own address on a
reservation that chose it, and D4's second condition is measured for the relayed segment.
"""

import ipaddress
import json
import logging
import os
import secrets
import shutil
import socket
import struct
import subprocess
import time

log = logging.getLogger(__name__)

#: D4's refusal list, by name and by code. Option 121 is on it because a
#: default route can arrive that way with no option 3 at all.
FORBIDDEN_OPTIONS = {"routers": 3, "domain-name-servers": 6,
                     "static-routes": 33, "classless-static-route": 121}

#: The config-source options a ZTP reservation carries (M3 measured the node
#: using both: `tftp server name <address> resolved`, `RRQ "<file>" octet`).
#: 66 carries an ADDRESS so no resolver is needed; 150 has no name in Kea
#: 2.4.1 and would need an option definition.
SERVER_OPTION = "tftp-server-name"
FILE_OPTION = "boot-file-name"
#: Option 3, only ever the relay's own address on a relayed ZTP subnet (C1346, D4 restated).
ROUTER_OPTION = "routers"

#: The address sources whose device fetches a bootstrap Mercury serves (P.6): ``ztp``, which
#: asks DHCP for its Kea reservation and fetches by AutoInstall, and ``ztp_console``,
#: OUT-OF-BAND ZTP's static path (C1592, the operator's decision of 2026-10-23): the console
#: kick-start types the plan's STATIC address and copies the bootstrap itself (C1594). The
#: static path touches no Kea (no subnet, no reservation): the responder serves its bootstrap to
#: the planned static address only while the device's console run holds it
#: (`ztp_responder.console_gate`). Both are rendered with the SSH key and no injected account.
ZTP_CONSOLE = "ztp_console"
ZTP_SOURCES = ("ztp", ZTP_CONSOLE)


def boot_file(hostname: str) -> str:
    """The bootstrap's file name a reservation names (option 67) and the responder serves: the
    one home of that name, read by the reservation and by the console kick-start's copy."""
    return f"{hostname}.cfg"

#: D4's second condition asks with a name nothing should resolve (RFC 6761),
#: so the probe itself cannot make anything reach for the internet.
DNS_PROBE_NAME = "nmas-ztp-probe.invalid"
DNS_PROBE_TIMEOUT = 2.0
#: How long a DNS measurement is reused at plan time. Every use states WHEN
#: it was measured, so a reused answer is never mistaken for a fresh one.
DNS_PROBE_REUSE_SECONDS = 300


class Refused(Exception):
    pass


# ── reading Kea's running config ───────────────────────────────────────────

def _dhcp4(config_result) -> dict:
    """The Dhcp4 object out of a Control Agent `config-get` result."""
    rows = config_result if isinstance(config_result, list) else [config_result]
    for row in rows:
        if isinstance(row, dict):
            dhcp4 = (row.get("arguments") or {}).get("Dhcp4")
            if isinstance(dhcp4, dict):
                return dhcp4
    raise Refused("Kea's config-get answer carries no Dhcp4 configuration")


def _all_subnets(dhcp4: dict) -> list:
    """Every subnet4, top level and inside shared networks, with the shared
    network (or None) it belongs to."""
    out = [(s, None) for s in dhcp4.get("subnet4") or []]
    for net in dhcp4.get("shared-networks") or []:
        out += [(s, net) for s in net.get("subnet4") or []]
    return out


def subnet_for_address(dhcp4: dict, address: str):
    """``(subnet, shared_network_or_None)`` whose CIDR contains *address*.
    Refuses when none does, or more than one does."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        raise Refused(f"{address!r} is not an address")
    hits = []
    for subnet, net in _all_subnets(dhcp4):
        try:
            if ip in ipaddress.ip_network(str(subnet.get("subnet")), strict=False):
                hits.append((subnet, net))
        except ValueError:
            continue
    if len(hits) != 1:
        raise Refused(f"expected exactly one Kea subnet containing {address}, "
                      f"found {len(hits)}")
    return hits[0]


def reservations(dhcp4: dict) -> dict:
    """``{mac: (subnet_id, address)}`` for every reservation Kea holds, in
    subnets, shared networks and the global list."""
    found = {}
    for subnet, _net in _all_subnets(dhcp4):
        for r in subnet.get("reservations") or []:
            if isinstance(r, dict) and r.get("hw-address"):
                found[_mac(r["hw-address"])] = (subnet.get("id"), r.get("ip-address", ""))
    for r in dhcp4.get("reservations") or []:
        if isinstance(r, dict) and r.get("hw-address"):
            found[_mac(r["hw-address"])] = ("global", r.get("ip-address", ""))
    return found


def _mac(value: str) -> str:
    return (value or "").strip().lower().replace("-", ":")


# ── D4, condition 1: no route or resolver option ───────────────────────────

def forbidden_options(dhcp4: dict, address: str, relay_address: str = "") -> list:
    """Every route or resolver option a reservation for *address* would
    EFFECTIVELY receive, as ``(level, name_or_code)``. Empty means none.

    *relay_address* (C1346, D4 restated 2026-10-19): on a RELAYED ZTP subnet, a reservation's
    own ``routers`` equal to the relay's own address is that reservation's declared choice and
    is not reported; ``routers`` anywhere else, or with any other value, still is, naming the
    value and the one it may be.

    Kea sends an option the client requests from the most specific level
    that has it, so every level is looked at: global, every client class, the
    shared network, the subnet, its pools and every reservation in it. A
    class counts whatever its test says (the discovery classes, board L,
    match only the ZTP subnet's own clients, and a class carrying a route
    would still be a breach): its option-data is read directly, so a class
    with none is clean and one with a forbidden option is named. Until
    2026-10-12 any defined class read "could not be ruled out" (the operator:
    D4 is a security guarantee and cannot stay unknown).
    """
    subnet, net = subnet_for_address(dhcp4, address)
    codes, names = set(FORBIDDEN_OPTIONS.values()), set(FORBIDDEN_OPTIONS)
    levels = [("global", dhcp4.get("option-data") or [])]
    for c in dhcp4.get("client-classes") or []:
        if isinstance(c, dict):
            levels.append((f"client-class {c.get('name')}", c.get("option-data") or []))
    if net is not None:
        levels.append((f"shared-network {net.get('name')}", net.get("option-data") or []))
    levels.append((f"subnet {subnet.get('id')}", subnet.get("option-data") or []))
    for p in subnet.get("pools") or []:
        levels.append((f"pool {p.get('pool')}", p.get("option-data") or []))
    for r in subnet.get("reservations") or []:
        levels.append((f"reservation {r.get('hw-address')}", r.get("option-data") or []))
    out = []
    for level, opts in levels:
        for o in opts:
            if not (o.get("name") in names or o.get("code") in codes):
                continue
            is_router = o.get("name") == "routers" or o.get("code") == 3
            if is_router and relay_address and level.startswith("reservation "):
                from modules.nsot import ztp_relayed

                why = ztp_relayed.routers_refusal(str(o.get("data", "")), relay_address)
                if not why:
                    continue
                out.append((level, why))
                continue
            out.append((level, o.get("name") or o.get("code")))
    return out


# ── D3: the server address is derived, never stored ────────────────────────

def server_address(subnet_cidr: str, addrs=None) -> str:
    """This host's own IPv4 address inside *subnet_cidr* (D3).

    Derived from the host's interfaces every time, because a configured copy
    of this fact is how `tftp_server_ip` came to name an address the host
    does not have (C48). Refuses when the host has none, or more than one,
    in that subnet.
    """
    net = ipaddress.ip_network(subnet_cidr, strict=False)
    if addrs is None:
        import psutil

        addrs = {name: [a.address for a in entries if a.family == socket.AF_INET]
                 for name, entries in psutil.net_if_addrs().items()}
    hits = sorted({(name, a) for name, found in addrs.items() for a in found
                   if ipaddress.ip_address(a) in net})
    if len(hits) != 1:
        raise Refused(f"expected exactly one address of this host in {subnet_cidr}, "
                      f"found {len(hits)}: {[a for _n, a in hits]}"
                      + ("; a subnet this host is not on is reached through a relay, and a "
                         "ZTP reservation there needs the subnet added for ZTP behind its "
                         "relay (DHCP › Add a subnet, For ZTP onboarding; C1346)"
                         if not hits else ""))
    return hits[0][1]


# ── D4, condition 2: nothing on the segment answers DNS ────────────────────

def _dns_query(name: str) -> tuple:
    qid = secrets.randbelow(0xFFFF)
    header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0"
    return qid, header + qname + struct.pack(">HH", 1, 1)


def dns_answerers(source: str, timeout: float = DNS_PROBE_TIMEOUT,
                  sock_factory=None, clock=time.time) -> dict:
    """Does anything on the segment answer a BROADCAST DNS query?

    Sent exactly as the node sent its own (M3): to 255.255.255.255:53, from
    this host's address on the segment, which the kernel routes out of that
    interface (measured: `ip route get 255.255.255.255 from <the host's
    address on the segment>` names the segment's interface). Any reply with the query's id is an answerer, whatever
    it says: an NXDOMAIN is still a resolver the node would use.

    ``{"state": "silent" | "answered" | "unknown", "answerers": [...],
    "measured_at": float, "error": str}``. A probe that could not be sent is
    UNKNOWN, never silent.
    """
    sock_factory = sock_factory or (lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
    out = {"state": "unknown", "answerers": [], "measured_at": clock(), "error": ""}
    qid, query = _dns_query(DNS_PROBE_NAME)
    try:
        s = sock_factory()
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((source, 0))
            s.settimeout(0.2)
            s.sendto(query, ("255.255.255.255", 53))
            deadline = clock() + timeout
            answerers = set()
            while clock() < deadline:
                try:
                    data, (peer, _port) = s.recvfrom(4096)
                except socket.timeout:
                    continue
                if len(data) >= 2 and struct.unpack(">H", data[:2])[0] == qid:
                    answerers.add(peer)
        finally:
            s.close()
    except OSError as exc:
        out["error"] = f"the probe could not be sent from {source}: {exc}"
        return out
    out["answerers"] = sorted(answerers)
    out["state"] = "answered" if answerers else "silent"
    return out


_dns_cache = {}


def dns_posture(source: str, probe=dns_answerers, clock=time.time) -> dict:
    """`dns_answerers`, reused for :data:`DNS_PROBE_REUSE_SECONDS`. The
    result always carries `measured_at`, so a reader can see its age."""
    hit = _dns_cache.get(source)
    if hit and hit["state"] != "unknown" and clock() - hit["measured_at"] < DNS_PROBE_REUSE_SECONDS:
        return dict(hit, reused=True)
    result = probe(source)
    _dns_cache[source] = result
    return dict(result, reused=False)


# ── the whole posture, for a plan and for job health ───────────────────────

def _link_subnet(address: str, dhcp4: dict, *, kea, list_name: str, hostname: str,
                 relayed: dict) -> dict:
    """C1460: when no Kea subnet holds *address*, the relayed ZTP subnet Add device would ADD
    for the device's link, derived from committed intent (`ztp_relayed.link_for_address`) and
    planned by the one subnet writer (`dhcp_subnets.plan`, declared for ZTP, recording the
    onboarding that adds it). ``{"add", "candidate"}``: *add* is what the plan carries and its
    preview states (prefix, relay, id, the writer's values and hash); *candidate* is Kea's
    configuration with that subnet in it, so every D4 check reads what would be written.
    Refused, naming why, as the derivation or the writer refuses.

    **No pool (C1600): the device's reservation is the subnet's only address.** The pool was
    the device's own address, so once the reservation was removed (Abandon, Retire) Kea leased
    that address to whatever asked on the link next. A subnet with reservations and no pool
    answers only the clients reserved in it; ``pool`` is ``""`` here, said by the preview."""
    import copy

    from modules import dhcp_subnets
    from modules.nsot import ztp_relayed

    facts = (relayed or {}).get("facts") or ztp_relayed.intent_everywhere()
    link = ztp_relayed.link_for_address(address, facts)
    values = {"op": "add", "family": "IPv4", "prefix": link["prefix"], "ztp": "1"}
    made = {"device": hostname, "list": list_name}
    p = dhcp_subnets.plan(list_name, values, kea=kea, intent=facts, created_by=made)
    if not p.get("ok"):
        raise Refused(f"its link's ZTP subnet {link['prefix']} cannot be added: "
                      f"{p.get('refused') or 'the subnet writer refused'}")
    relay = link["relay"]
    candidate = copy.deepcopy(dhcp4)
    candidate.setdefault("subnet4", []).append(dict(p["after"], reservations=[]))
    return {"add": {"prefix": link["prefix"], "pool": "", "id": p["id"],
                    "relay": f"{relay['device']} {relay['iface']} ({relay['address']})",
                    "values": values, "hash": p["hash"], "created_by": made},
            "candidate": candidate}


def _no_subnet_holds(dhcp4: dict, address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    for subnet, _net in _all_subnets(dhcp4):
        try:
            if ip in ipaddress.ip_network(str(subnet.get("subnet")), strict=False):
                return False
        except ValueError:
            continue
    return True


def posture(address: str, *, kea=None, dns=dns_posture, addrs=None, relayed=None,
            list_name: str = "", hostname: str = "") -> dict:
    """D4 for a reservation at *address*: both conditions, plus D3's derived
    server address. ``{"ok", "reasons", "server", "subnet_id", "dns", "relayed", "relay"}``.

    Every failure to ASK is a reason too: a check that did not run has not
    passed, and a ZTP plan refused here has written nothing.

    A subnet declared relayed for ZTP (C1346) is asked by `ztp_relayed.posture`: the server is
    the relay's helper target that is this host's, the DNS check is made for the relayed
    segment, and option 3 equal to the relay's own address is a reservation's allowed choice.
    *relayed* holds that check's seams (``facts``, ``golden``, ``dns``, ``route``).
    """
    from modules.nsot import ztp_relayed

    out = {"ok": False, "reasons": [], "server": "", "subnet_id": None, "dns": {},
           "relayed": False, "relay": {}}
    try:
        ztp_relayed.ipv4_only(address, "the address")
    except Refused as exc:
        out["reasons"].append(str(exc))
        return out
    kea = kea or _kea()
    got = kea.command("config-get")
    if not got.get("ok"):
        out["reasons"].append(f"Kea could not be asked for its configuration: {got.get('error')}")
        return out
    try:
        dhcp4 = _dhcp4(got["result"])
        if list_name and hostname and _no_subnet_holds(dhcp4, address):
            # C1460: Add device behind a relay adds its link's subnet, checked as it would be.
            link = _link_subnet(address, dhcp4, kea=kea, list_name=list_name,
                                hostname=hostname, relayed=relayed or {})
            out["subnet_to_add"] = link["add"]
            dhcp4 = link["candidate"]
        subnet, _net = subnet_for_address(dhcp4, address)
        out["subnet_id"] = subnet.get("id")
        if ztp_relayed.declared(subnet):
            return _relayed_posture(out, dhcp4, subnet, address, addrs, relayed or {})
        bad = forbidden_options(dhcp4, address)
        out["server"] = server_address(str(subnet.get("subnet")), addrs)
    except Refused as exc:
        out["reasons"].append(str(exc))
        return out
    for level, what in bad:
        out["reasons"].append(
            f"D4: {what} reaches a reservation in subnet {subnet.get('id')} "
            f"(at {level}). The node requests route and resolver options, so a "
            f"configless device would be handed a path to Cisco's PnP and Call "
            f"Home services")
    out["dns"] = dns(out["server"])
    state = out["dns"].get("state")
    if state == "answered":
        out["reasons"].append(
            "D4: something on the ZTP segment answers broadcast DNS "
            f"({', '.join(out['dns']['answerers'])}), which would give a "
            "configless node a resolver with no DHCP option at all")
    elif state != "silent":
        out["reasons"].append(
            "D4: whether anything on the ZTP segment answers DNS could not be "
            f"measured ({out['dns'].get('error') or 'no answer'}); a check that "
            "did not run has not passed")
    out["ok"] = not out["reasons"]
    return out


def _relayed_posture(out: dict, dhcp4: dict, subnet: dict, address: str, addrs,
                     seams: dict) -> dict:
    """:func:`posture` for a subnet declared relayed for ZTP (C1346)."""
    from modules.nsot import ztp_relayed

    got = ztp_relayed.posture(dhcp4, subnet, address=address, addrs=addrs, **seams)
    out.update(relayed=True, relay=got["relay"], server=got["server"], dns=got["dns"])
    out["reasons"] += got["reasons"]
    if got["relay"]:
        for level, what in forbidden_options(dhcp4, address, got["relay"]["address"]):
            out["reasons"].append(
                f"D4: {what} reaches a reservation in subnet {subnet.get('id')} (at {level}). "
                "On a relayed ZTP subnet only a reservation's own option 3, the relay's own "
                "address, is allowed; no resolver or other route option is")
    out["ok"] = not out["reasons"]
    return out


def _kea(owner: str = ""):
    """Kea's client: the one *owner* (a network that owns a Kea, :func:`kea_home`) sets, for a
    check or write made for a network (C1235: the writer built it for no network, so a device
    onboarded into a network with a Kea of its own was reserved on Default's). With no network,
    the client built for no list (job health's D4 rows, a pending row's progress)."""
    from modules.integrations.kea import KeaIntegration

    return KeaIntegration(list_name=owner) if owner else KeaIntegration()


def kea_home(list_name: str) -> dict:
    """Where *list_name*'s ZTP reservations go: ``{"owner", "fragment", "main_config"}``, its
    Kea OWNER's (`list_settings.kea_owner`: the network where Kea is set, never one inheriting
    it; C1181), the owner's ZTP fragment and Kea's IPv4 configuration (C1235). Raises
    `list_settings.ListSettingsUnreadable` when whose Kea it is cannot be read."""
    from modules.list_settings import kea_owner, value

    owner, _why = kea_owner(list_name)
    return {"owner": owner,
            "fragment": value(owner, "kea_ztp_fragment", "") or "",
            "main_config": (value(owner, "kea_dhcp4_config", "/etc/kea/kea-dhcp4.conf")
                            or "/etc/kea/kea-dhcp4.conf")}


def ztp_subnets(dhcp4: dict, addrs=None) -> list:
    """``[(subnet, host_address)]``: every Kea subnet holding one of THIS
    host's addresses on an interface Kea listens on. That is where a node
    asking by broadcast is answered, and where the config server is (D3), so
    it is the ZTP segment without anything having to name it."""
    if addrs is None:
        import psutil

        addrs = {name: [a.address for a in entries if a.family == socket.AF_INET]
                 for name, entries in psutil.net_if_addrs().items()}
    listening = [str(i).split("/", 1)[0] for i in
                 (dhcp4.get("interfaces-config") or {}).get("interfaces") or []]
    out = []
    for iface in listening:
        for address in addrs.get(iface, []):
            try:
                subnet, _net = subnet_for_address(dhcp4, address)
            except Refused:
                continue
            out.append((subnet, address))
    return out


def posture_rows(kea=None, dns=dns_posture, addrs=None, get=None, relayed=None,
                 firewall=None) -> list:
    """Job-health rows for D4, one per ZTP subnet. None while ZTP is not
    configured: an empty `kea_ztp_fragment` is already its own row
    (`unset_guard`), and a second row saying the same thing is noise.

    C1346: one row per subnet declared relayed for ZTP too (`ztp_relayed.posture`: its relay,
    server, route and DNS on the relayed segment, and D4's options), and one `ztp-firewall`
    row while any is declared (udp/69 admitted from each, `ztp_relayed.firewall_row`).
    *relayed* holds the relayed check's seams; *firewall* is ``(record, path)``."""
    fragment = _job_fragment(get)
    if not fragment:
        return []
    return (_direct_posture_rows(kea, dns, addrs)
            + _relayed_posture_rows(kea, addrs, relayed or {}, firewall, fragment))


def _job_fragment(get=None) -> str:
    """The ZTP fragment job health's ZTP rows ask under: "" while ZTP is not configured, when
    they are none. One read for D4's rows and C1403's (*get* a test's seam)."""
    if get is None:
        from modules.list_settings import default_layer as get   # one fragment, every list
    return (get("kea_ztp_fragment", "") or "").strip()


def lease_identity_rows(kea=None, addrs=None, get=None) -> list:
    """C1403: one job-health row per ZTP subnet, whether Kea matches its leases by MAC
    (`dhcp_lease_identity.rows`). None while ZTP is not configured, as D4's rows; Kea not
    answering is D4's own `ztp-posture` row already."""
    from modules import dhcp_lease_identity

    if not _job_fragment(get):
        return []
    got = (kea or _kea()).command("config-get")
    if not got.get("ok"):
        return []
    try:
        dhcp4 = _dhcp4(got["result"])
    except Refused:
        return []
    return dhcp_lease_identity.rows(dhcp4, addrs)


def _relayed_posture_rows(kea, addrs, seams: dict, firewall, fragment: str) -> list:
    from modules.nsot import ztp_relayed

    what = ("D4 on a relayed ZTP subnet: the relay forwards to this host, a route back, no "
            "resolver option, option 3 only the relay's own address, and nothing answers DNS")
    kea = kea or _kea()
    got = kea.command("config-get")
    if not got.get("ok"):
        return []                      # the direct rows already say Kea could not be asked
    try:
        dhcp4 = _dhcp4(got["result"])
    except Refused:
        return []
    subnets = ztp_relayed.relayed_subnets(dhcp4)
    rows = []
    for subnet in subnets:
        relay_out = {"reasons": []}
        try:
            ztp_relayed.ipv4_only(str(subnet.get("subnet", "")), "the subnet")
            relay_out = ztp_relayed.posture(dhcp4, subnet, addrs=addrs, **seams)
        except Refused as exc:
            relay_out = {"reasons": [str(exc)], "relay": {}, "dns": {}}
        reasons = list(relay_out["reasons"])
        if relay_out.get("relay"):
            reasons += [f"D4: {w} at {lvl}" for lvl, w in
                        _subnet_forbidden(dhcp4, subnet, relay_out["relay"]["address"])]
        measured = (relay_out.get("dns") or {}).get("measured_at")
        when = (time.strftime(" (DNS measured %H:%M:%S)", time.localtime(measured))
                if measured else "")
        state = "ok" if not reasons else ("unknown" if any("could not" in r for r in reasons)
                                          else "d4_violated")
        relay = relay_out.get("relay") or {}
        rows.append({"unit": f"ztp-posture:subnet-{subnet.get('id')}", "what": what,
                     "state": state, "max_age_minutes": 0,
                     "detail": ("; ".join(reasons) or
                                f"relayed subnet {subnet.get('id')} {subnet.get('subnet')} "
                                f"behind {relay.get('device')} {relay.get('iface')} "
                                f"({relay.get('address')}): served from "
                                f"{relay_out.get('server')}, a route back, no resolver option, "
                                "and nothing answered DNS") + when})
    if subnets:
        if firewall is None:
            path = ztp_relayed.firewall_record_path(fragment)
            firewall = (ztp_relayed.read_firewall_record(path), path)
        record, path = firewall
        rows.append(ztp_relayed.firewall_row(
            [(s.get("id"), str(s.get("subnet", ""))) for s in subnets], record, path))
    return rows


def _subnet_forbidden(dhcp4: dict, subnet: dict, relay_address: str) -> list:
    """D4's options for a whole relayed subnet (job health has no one address): asked of the
    subnet's own first address, which `forbidden_options` places in that subnet."""
    first = str(ipaddress.ip_network(str(subnet.get("subnet")), strict=False).network_address)
    try:
        return forbidden_options(dhcp4, first, relay_address)
    except Refused as exc:
        return [("the subnet", str(exc))]


def _direct_posture_rows(kea, dns, addrs) -> list:
    """The rows for the ZTP subnets this host is on."""
    what =("D4: a ZTP reservation gets no route or resolver option, and "
            "nothing on the segment answers DNS")
    kea = kea or _kea()
    got = kea.command("config-get")
    if not got.get("ok"):
        return [{"unit": "ztp-posture", "what": what, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": f"Kea could not be asked: {got.get('error')} -- not the same as ok"}]
    try:
        found = ztp_subnets(_dhcp4(got["result"]), addrs)
    except Refused as exc:
        found, error = [], str(exc)
    else:
        error = ""
    if not found:
        return [{"unit": "ztp-posture", "what": what, "state": "unknown",
                 "max_age_minutes": 0,
                 "detail": ("no Kea subnet holds this host's address on an interface "
                            f"Kea listens on {error}").strip()}]
    rows = []
    for subnet, address in found:
        p = posture(address, kea=kea, dns=dns, addrs=addrs)
        measured = p.get("dns", {}).get("measured_at")
        when = (time.strftime(" (DNS measured %H:%M:%S)", time.localtime(measured))
                if measured else "")
        state = "ok" if p["ok"] else ("unknown" if any("could not" in r for r in p["reasons"])
                                       else "d4_violated")
        rows.append({"unit": f"ztp-posture:subnet-{subnet.get('id')}", "what": what,
                     "state": state, "max_age_minutes": 0,
                     "detail": ("; ".join(p["reasons"]) or
                                f"subnet {subnet.get('id')} {subnet.get('subnet')}: no route "
                                f"or resolver option, and nothing answered DNS") + when})
    return rows


# ── the writer (D1) ────────────────────────────────────────────────────────

def reservation_entry(mac: str, address: str, hostname: str, server: str,
                      router: str = "") -> dict:
    """The one shape the writer puts in the fragment. Both config-source
    options are `always-send`, as M3 offered them, so what the node gets
    does not depend on what it happens to request.

    `hostname` is sent as option 12. M3 showed AutoInstall APPLIES option 12
    ("Setting hostname router from DHCP reply", from Kea echoing the node's
    own name), so a reservation that names the device makes it name itself
    correctly before its config arrives, rather than after an echo.

    *router* (C1346, D4 restated): on a relayed ZTP subnet only, the relay's own address as
    option 3, when the onboarding chose to offer it; empty (no option 3, D4 as decided) by
    default. The writer refuses any other value, naming both."""
    opts = [{"name": SERVER_OPTION, "data": server, "always-send": True},
            {"name": FILE_OPTION, "data": boot_file(hostname), "always-send": True}]
    if router:
        opts.append({"name": ROUTER_OPTION, "data": router, "always-send": True})
    return {"hw-address": _mac(mac), "ip-address": address, "hostname": hostname,
            "option-data": opts}


def _read_fragment(path: str) -> list:
    if not os.path.exists(path):
        raise Refused(f"the fragment {path} does not exist. D1's host change "
                      "creates it (docs/DEPLOY_LINUX.md, the Kea section)")
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
    except (OSError, ValueError) as exc:
        raise Refused(f"the fragment {path} is unreadable ({exc}); refusing to "
                      "write over something that cannot be read")
    if not isinstance(value, list):
        raise Refused(f"the fragment {path} is not a list of reservations")
    return value


def _write_file(path: str, text: str) -> None:
    """Create *path* with mode 0644 set explicitly: a rename carries the new
    inode's mode, and the host shell's umask is 0002 (measured)."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.fchmod(fd, 0o644)
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)


def _replace(path: str, text: str) -> None:
    tmp = os.path.join(os.path.dirname(path), f".{os.path.basename(path)}.{os.getpid()}.tmp")
    _write_file(tmp, text)
    os.replace(tmp, path)


def _config_test(main_text: str, fragment: str, candidate_text: str,
                 run=None) -> tuple:
    """``(ok, detail)``: `kea-dhcp4 -t` on a copy of the main config whose
    include names a CANDIDATE fragment. Both copies live beside the fragment,
    because Kea's AppArmor profile allows reads under /etc/kea only (measured:
    /tmp/kea-broken.conf was denied)."""
    import re

    def include(path):
        return f'<?include "{path}"?>'

    directive = include(fragment)
    folder = os.path.dirname(fragment)
    tag = f"{os.getpid()}-{secrets.token_hex(4)}"
    candidate = os.path.join(folder, f".candidate-{tag}.json")
    test_main = os.path.join(folder, f".test-main-{tag}.conf")
    middle = os.path.join(folder, f".test-sub-{tag}.json")
    run = run or _run_kea_test
    try:
        _write_file(candidate, candidate_text)
        if directive in main_text:
            _write_file(test_main, main_text.replace(directive, include(candidate)))
        else:
            # C701: after C529 step 5's move Kea's file includes Mercury's subnet file, and IT
            # names the fragment. Substituting in Kea's file alone changed nothing, so Kea
            # checked the live files and never the candidate.
            via, text = "", ""
            for path in re.findall(r'<\?include "([^"]+)"\?>', main_text):
                try:
                    with open(path, encoding="utf-8") as fh:
                        text = fh.read()
                except OSError:
                    continue
                if directive in text:
                    via = path
                    break
            if not via:
                return False, (f"no file Kea's configuration includes names {fragment}, so the "
                               "candidate could not be checked where Kea would read it")
            _write_file(middle, text.replace(directive, include(candidate)))
            _write_file(test_main, main_text.replace(include(via), include(middle)))
        return run(test_main)
    finally:
        for p in (candidate, test_main, middle):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass


def _run_kea_test(config_path: str, program: str = "kea-dhcp4") -> tuple:
    """``(ok, detail)``: *program* (`kea-dhcp4`, or `kea-dhcp6` for DHCP's IPv6 reservations,
    C529) checks *config_path* without serving it."""
    binary = shutil.which(program)
    if not binary:
        return False, f"{program} is not on this host's PATH, so the candidate cannot be tested"
    try:
        proc = subprocess.run([binary, "-t", config_path], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"kea-dhcp4 -t could not run: {exc}"
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
    return proc.returncode == 0, " | ".join(tail)


def fragment_lock(fragment: str):
    """The lock every write of *fragment* holds from its read to its read-back, across
    processes (CONCURRENCY_AUDIT R22: two onboardings at once each replaced the fragment with
    their own reservation alone, and the earlier device later got no address). Kept in the
    app's data folder, keyed by the fragment's path, never beside the fragment under /etc/kea."""
    import hashlib

    from modules import config
    from modules.filestore import PathLock

    key = hashlib.sha256(os.path.abspath(fragment).encode()).hexdigest()[:16]
    folder = os.path.join(config.DATA_DIR, "locks")
    os.makedirs(folder, exist_ok=True)
    return PathLock(os.path.join(folder, f"kea-fragment-{key}"))


def write_reservations(adds=(), removes=(), *, list_name: str = "", actor: str = "",
                       message: str = "", kea=None, fragment: str = None,
                       main_config: str = None, run_test=None) -> dict:
    """Write and remove ZTP reservations. ``{"ok", "outcomes", "error",
    "reloaded", "record"}``; `outcomes` is ``{mac: {"outcome", "detail"}}`` with outcome
    ``written | unchanged | removed | absent | refused``.

    *adds* are dicts from :func:`reservation_entry`. *removes* are MACs.
    A device refused alone does not stop the others. A failure after the
    live fragment is touched restores the previous fragment and reloads.
    The whole write holds :func:`fragment_lock` (R22).

    *list_name* is the network the write is made for (onboarding's): the write goes to its
    Kea OWNER's Kea and fragment (:func:`kea_home`, C1235), and, still holding the fragment's
    lock, `record` is the commit of :data:`RECORD` in the owner's repository as *actor* with
    *message* (:func:`record_commit`, C1243), or why it failed. A write for no network names
    its fragment, Kea's configuration and Kea itself, and records nothing (`record` None).

    C1346: a write for a network ROUTES each reservation to its subnet's ZTP file: an address
    in a subnet declared relayed for ZTP goes in that subnet's own reservations file (ZTP's
    whole, `ztp_relayed`), every other in the network's fragment; a removal goes to the ZTP
    file holding its MAC. Each file is written under its own lock, and the record (every ZTP
    file) is taken under the network fragment's lock after the last write.
    """
    from modules.list_settings import ListSettingsUnreadable

    out = {"ok": False, "outcomes": {}, "error": "", "reloaded": False, "record": None}
    owner = ""
    routed = False
    if list_name:
        try:
            home = kea_home(list_name)
        except ListSettingsUnreadable as exc:
            out["error"] = (f"whose Kea {list_name} uses could not be read ({exc}), so where its "
                            "reservation goes cannot be said. Nothing was written")
            return out
        owner = home["owner"]
        routed = fragment is None
        fragment = home["fragment"] if fragment is None else fragment
        main_config = main_config or home["main_config"]
    elif fragment is None or not main_config or kea is None:
        out["error"] = ("a ZTP reservation is written for a network (whose Kea, fragment and "
                        "record it is), or names its fragment, Kea's configuration and Kea; "
                        "this write did neither. Nothing was written")
        return out
    if not fragment:
        out["error"] = ("kea_ztp_fragment is not configured: a reservation written "
                        "anywhere else lives in Kea's memory until its next restart (C49)")
        return out
    kea = kea or _kea(owner)
    if routed:
        groups, error = _route(adds, removes, fragment, main_config)
        if error:
            out["error"] = error + ". Nothing was written"
            return out
    else:
        groups = {fragment: (list(adds), list(removes), None)}
    errors, oks = [], []
    for path, (some_adds, some_removes, sid) in groups.items():
        part = {"ok": False, "outcomes": {}, "error": "", "reloaded": False}
        with fragment_lock(path):
            _write_reservations_locked(part, some_adds, some_removes, kea, path, main_config,
                                       run_test, relayed_id=sid)
        out["outcomes"].update(part["outcomes"])
        out["reloaded"] = out["reloaded"] or part["reloaded"]
        if part["error"]:
            errors.append(part["error"] if len(groups) == 1 else f"{path}: {part['error']}")
        oks.append(part["ok"])
    out["ok"] = bool(oks) and all(oks)
    out["error"] = "; ".join(errors)
    # THE RECORD, under the network fragment's lock, so a write's commit holds what it left.
    # Taken whenever Kea was reloaded with a new file (even one whose read-back then failed: it
    # is in Kea) or the write succeeded unchanged (which commits nothing unless an earlier
    # record failed: the record is every ZTP file whole, so this one catches up).
    if list_name and (out["reloaded"] or out["ok"]):
        with fragment_lock(fragment):
            out["record"] = record_commit(list_name, fragment, message=message, actor=actor,
                                          main_config=main_config)
        if not out["record"].get("ok"):
            log.error("ztp: the reservation record for %s was NOT committed: %s",
                      list_name, out["record"].get("error"))
    return out


def fragments(fragment: str, main_config: str) -> tuple:
    """``([(subnet_id_or_None, path)], error)``: every file ZTP's writer owns for a Kea: the
    network's fragment (``None``: the subnet this host is on), then each subnet declared relayed
    for ZTP's own reservations file (C1346). *error* names Mercury's subnet file when it could
    not be read, so a reader can say which reservations it did not look at."""
    from modules.nsot import ztp_relayed

    out = [(None, fragment)] if fragment else []
    if not main_config:
        return out, ""
    relayed, error = ztp_relayed.declared_in_file(main_config)
    out += [(sid, path) for sid, _prefix, path in relayed if path != fragment]
    return out, error


def _route(adds, removes, fragment: str, main_config: str) -> tuple:
    """``({path: (adds, removes, relayed_subnet_id_or_None)}, error)``: each add to the ZTP
    file of the subnet holding its address, each removal to the ZTP file holding its MAC."""
    from modules.nsot import ztp_relayed

    relayed, error = ztp_relayed.declared_in_file(main_config)
    groups = {fragment: ([], [], None)}
    if error and (adds or removes):
        return {}, (f"Mercury's subnet file could not be read ({error}), so whether a "
                    "reservation belongs in a relayed ZTP subnet's file cannot be told")
    nets = []
    for sid, prefix, path in relayed:
        try:
            nets.append((ipaddress.ip_network(prefix, strict=False), sid, path))
        except ValueError:
            continue
    for entry in adds:
        try:
            ip = ipaddress.ip_address(str(entry.get("ip-address", "")))
        except ValueError:
            ip = None
        hit = next(((sid, path) for net, sid, path in nets
                    if ip is not None and ip.version == net.version and ip in net), None)
        if hit:
            groups.setdefault(hit[1], ([], [], hit[0]))[0].append(entry)
        else:
            groups[fragment][0].append(entry)
    for raw in removes:
        mac, where = _mac(raw), fragment
        for sid, _prefix, path in relayed:
            try:
                held = _read_fragment(path)
            except Refused:
                continue
            if any(_mac(e.get("hw-address", "")) == mac for e in held if isinstance(e, dict)):
                where = path
                groups.setdefault(path, ([], [], sid))
                break
        groups[where][1].append(raw)
    busy = {p: g for p, g in groups.items() if g[0] or g[1]}
    # An empty write still asks the network's fragment, as it always has.
    return busy or {fragment: groups[fragment]}, ""


#: ZTP's record (C1243): every reservation in the ZTP fragment, as the writer left it, committed
#: in the Kea owner's repository with the DHCP page's records (`dhcp_reservations.RECORD`
#: excludes ZTP's subnet: its reservations are onboarding's, recorded here).
RECORD = "dhcp/ztp-reservations.yml"


def record_rows(entries, subnet_id=None) -> list:
    """The record's rows: each reservation's MAC, address, hostname and the two config-source
    options (:func:`reservation_entry`'s shape), in the fragment's order. A reservation in a
    relayed ZTP subnet's file (C1346) also names that subnet, and its option 3 when it was
    chosen (the relay's own address), so the record holds the choice."""
    rows = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        opts = {o.get("name"): o.get("data") for o in e.get("option-data") or []
                if isinstance(o, dict)}
        row = {"mac": _mac(e.get("hw-address", "")), "address": e.get("ip-address", ""),
               "hostname": e.get("hostname", ""), "server": opts.get(SERVER_OPTION, ""),
               "file": opts.get(FILE_OPTION, "")}
        if subnet_id is not None:
            row["relayed_subnet"] = subnet_id
        if opts.get(ROUTER_OPTION):
            row["router"] = opts[ROUTER_OPTION]
        rows.append(row)
    return rows


def record_commit(list_name: str, fragment: str, *, message: str, actor: str,
                  main_config: str = "") -> dict:
    """Commit :data:`RECORD`, read now from *fragment* and (C1346, given *main_config*) from
    every relayed ZTP subnet's file, through the one commit of a Kea record
    (`dhcp_reservations.commit_in_owner`: the Kea owner's repository, `From-Network:` when
    *list_name* is another network). ``{"ok", "commit", "owner", "error"}``."""
    import yaml

    from modules import dhcp_reservations as D

    every, error = fragments(fragment, main_config)
    if error:
        return {"ok": False, "commit": "", "owner": "",
                "error": f"the relayed ZTP subnets could not be read for the record: {error}"}
    rows = []
    for sid, path in every:
        try:
            rows += record_rows(_read_fragment(path), sid)
        except Refused as exc:
            return {"ok": False, "commit": "", "owner": "",
                    "error": f"the fragment could not be read for the record: {exc}"}
    text = ("# Kea reservations ZTP's onboarding holds in its fragment (C1243); written on "
            "each change.\n" + yaml.safe_dump({"reservations": rows}, sort_keys=False))
    return D.commit_in_owner(list_name, RECORD, lambda _owner: text,
                             message or "ztp: reservations changed", actor=actor or "unknown")


def _includer(main_config: str, main_text: str, fragment: str) -> str:
    """The file that includes *fragment*, asked of the shape Kea's files have now (C701):
    Kea's own IPv4 file before C529 step 5's subnet move, Mercury's subnet file after it (the
    move carried each subnet's include there). ``""`` when neither does."""
    directive = f'<?include "{fragment}"?>'
    if directive in main_text:
        return main_config
    from modules import dhcp_subnets
    if dhcp_subnets.move_plan(main_text, main_config, "IPv4")["state"] != "done":
        return ""
    path = dhcp_subnets.subnets_file(main_config, "IPv4")
    try:
        with open(path, encoding="utf-8") as fh:
            return path if directive in fh.read() else ""
    except OSError:
        return ""


def _placement_refusal(dhcp4: dict, address: str, relayed_id) -> tuple:
    """``(why, relay_address)``: why a reservation for *address* may not go in this file (one
    whose relayed subnet is *relayed_id*, or the network's fragment when None), and, in a
    relayed ZTP subnet, the relay's own address (Kea's ``relay.ip-addresses``), option 3's only
    allowed value (C1346)."""
    from modules.nsot import ztp_relayed

    try:
        subnet, _net = subnet_for_address(dhcp4, address)
    except Refused as exc:
        return str(exc), ""
    is_relayed = ztp_relayed.declared(subnet)
    if relayed_id is None and is_relayed:
        return (f"{address} is in subnet {subnet.get('id')}, declared relayed for ZTP: its "
                "reservation goes in that subnet's own file, not this fragment"), ""
    if relayed_id is not None and (subnet.get("id") != relayed_id or not is_relayed):
        return (f"{address} is in Kea's subnet {subnet.get('id')}, not in the relayed ZTP "
                f"subnet {relayed_id} whose file this is"), ""
    relay = ztp_relayed.kea_relay(subnet) if is_relayed else []
    return "", (relay[0] if len(relay) == 1 else "")


def _write_reservations_locked(out, adds, removes, kea, fragment, main_config,
                               run_test, relayed_id=None) -> dict:
    try:
        with open(main_config, encoding="utf-8") as fh:
            main_text = fh.read()
        including = _includer(main_config, main_text, fragment)
        if not including:
            raise Refused(f"{main_config} does not include {fragment}, nor does Mercury's "
                          "subnet file it includes, so a reservation written there would never "
                          "reach Kea")
        current = _read_fragment(fragment)
        got = kea.command("config-get")
        if not got.get("ok"):
            raise Refused(f"Kea could not be asked for its configuration: {got.get('error')}")
        dhcp4 = _dhcp4(got["result"])
        leased = _leases(kea)
    except (OSError, Refused) as exc:
        out["error"] = str(exc)
        return out

    before = reservations(dhcp4)
    mine = {_mac(r.get("hw-address")): r for r in current if isinstance(r, dict)}
    candidate = dict(mine)

    def refuse(mac, why):
        out["outcomes"][mac] = {"outcome": "refused", "detail": why}

    for entry in adds:
        mac, address = _mac(entry.get("hw-address")), entry.get("ip-address", "")
        if mine.get(mac) == entry:
            out["outcomes"][mac] = {"outcome": "unchanged",
                                    "detail": f"{mac} -> {address} is already in the fragment"}
            continue
        found = conflicts(dhcp4, leased, mac, address)
        if found:
            refuse(mac, "; ".join(found))
            continue
        placed, relay_address = _placement_refusal(dhcp4, address, relayed_id)
        if placed:
            refuse(mac, placed)
            continue
        try:
            bad = forbidden_options(dhcp4, address, relay_address)
        except Refused as exc:
            refuse(mac, str(exc))
            continue
        for o in entry.get("option-data") or []:
            if not (o.get("name") in FORBIDDEN_OPTIONS
                    or o.get("code") in FORBIDDEN_OPTIONS.values()):
                continue
            if o.get("name") == ROUTER_OPTION or o.get("code") == 3:
                # C1346, D4 restated: the relay's own address on a relayed ZTP subnet only.
                from modules.nsot import ztp_relayed

                why = ztp_relayed.routers_refusal(str(o.get("data", "")), relay_address)
                if why:
                    bad.append(("this reservation", why))
                continue
            bad.append(("this reservation", o.get("name") or o.get("code")))
        if bad:
            refuse(mac, "D4: " + "; ".join(f"{w} at {lvl}" for lvl, w in bad))
            continue
        candidate[mac] = entry
        out["outcomes"][mac] = {"outcome": "written", "detail": f"{mac} -> {address}"}

    for raw in removes:
        mac = _mac(raw)
        if mac in mine:
            candidate.pop(mac, None)
            out["outcomes"][mac] = {"outcome": "removed", "detail": f"{mac} -> {mine[mac].get('ip-address')}"}
        elif mac in before:
            refuse(mac, f"{mac} is reserved outside {fragment}; the tool removes only what it wrote")
        else:
            out["outcomes"][mac] = {"outcome": "absent", "detail": f"{mac} has no reservation"}

    if candidate == mine:
        out["ok"] = all(o["outcome"] != "refused" for o in out["outcomes"].values())
        return out

    candidate_text = json.dumps(list(candidate.values()), indent=2) + "\n"
    previous_text = json.dumps(current, indent=2) + "\n"
    ok, detail = _config_test(main_text, fragment, candidate_text, run_test)
    if not ok:
        return _refuse_all(out, f"kea-dhcp4 -t refused the candidate: {detail}. "
                                "The live fragment was not touched")

    _replace(fragment, candidate_text)
    reload = kea.command("config-reload")
    if not reload.get("ok"):
        _replace(fragment, previous_text)
        again = kea.command("config-reload")
        return _refuse_all(out, f"config-reload failed ({reload.get('error')}); the previous "
                                "fragment was restored" + ("" if again.get("ok") else
                                f" and ITS reload failed too ({again.get('error')})"))
    out["reloaded"] = True

    # READ BACK, and name both operands on any difference.
    after_got = kea.command("config-get")
    if not after_got.get("ok"):
        out["error"] = f"written and reloaded, and the read-back failed: {after_got.get('error')}"
        return out
    after = {m: ip for m, (_sid, ip) in reservations(_dhcp4(after_got["result"])).items()}
    expected = {m: ip for m, (_sid, ip) in before.items()}
    for mac, o in out["outcomes"].items():
        if o["outcome"] == "written":
            expected[mac] = candidate[mac]["ip-address"]
        elif o["outcome"] == "removed":
            expected.pop(mac, None)
    if after != expected:
        missing = {m: ip for m, ip in expected.items() if after.get(m) != ip}
        extra = {m: ip for m, ip in after.items() if expected.get(m) != ip}
        out["error"] = (f"the running server does not hold what was written: expected "
                        f"{missing or 'nothing more'}, but it holds {extra or 'nothing more'}")
        return out
    if _read_fragment(fragment) != list(candidate.values()):
        out["error"] = f"{fragment} does not read back as the candidate that was tested"
        return out
    out["ok"] = all(o["outcome"] != "refused" for o in out["outcomes"].values())
    return out


def conflicts(dhcp4: dict, leased: dict, mac: str, address: str) -> list:
    """Why a NEW reservation *mac* -> *address* may not be written. One
    rule for the plan and the writer, so the review screen refuses exactly
    what the write would. *leased* is ``{address: mac}``."""
    mac = _mac(mac)
    held = reservations(dhcp4)
    reasons = []
    if mac in held:
        reasons.append(f"{mac} is already reserved -> {held[mac][1]} in subnet {held[mac][0]}")
    taken = [m for m, (_sid, ip) in held.items() if ip == address and m != mac]
    if taken:
        reasons.append(f"{address} is already reserved for {taken[0]}")
    if leased.get(address) and leased[address] != mac:
        reasons.append(f"{address} is leased to {leased[address]} right now")
    return reasons


def _leases(kea) -> dict:
    got = kea.command("lease4-get-all", service=["dhcp4"])
    if not got.get("ok"):
        raise Refused(f"Kea could not be asked for its leases: {got.get('error')}")
    leased = {}
    for row in (got["result"] if isinstance(got["result"], list) else [got["result"]]):
        for lease in ((row or {}).get("arguments") or {}).get("leases") or []:
            leased[lease.get("ip-address", "")] = _mac(lease.get("hw-address", ""))
    return leased


def plan_check(mac: str, address: str, *, kea=None, dns=dns_posture, addrs=None,
               get=None, list_name: str = "", relayed=None, hostname: str = "") -> dict:
    """Everything a `ztp` plan must know before anything is created:
    ``{"ok", "reasons", "server", "subnet_id", "dns", "relayed", "relay"}`` (*relayed*: the
    relayed check's seams, :func:`posture`; ``relay`` is the relay's device, interface and own
    address when the subnet is declared relayed for ZTP, C1346).

    The writer's own preconditions (configured, no conflict) plus D4's two
    conditions and D3's derived server. Found at PLAN time, so the review
    screen, which promises that nothing has been created yet, is where a
    refusal lands. A check that could not run is a reason, never a pass.

    *list_name*, the onboarding's network: asked of the Kea and fragment the writer will
    write, its Kea owner's (:func:`kea_home`, C1235)."""
    owner = ""
    if get is None and list_name:
        from modules.list_settings import value

        owner = kea_home(list_name)["owner"]

        def get(key, default=""):
            return value(owner, key, default)
    if get is None:
        from modules.list_settings import default_layer as get   # one fragment, every list
    out = {"ok": False, "reasons": [], "server": "", "subnet_id": None, "dns": {},
           "relayed": False, "relay": {}, "subnet_to_add": {}}
    if not (get("kea_ztp_fragment", "") or "").strip():
        out["reasons"].append(
            "kea_ztp_fragment is not configured: a reservation written anywhere "
            "else lives in Kea's memory until its next restart (C49)")
        return out
    if not mac or not address:
        return out
    kea = kea or _kea(owner)
    # *hostname* given (Add device's plan, C1460): an address no Kea subnet holds is checked
    # on the link's subnet Add device would add, derived from committed intent.
    p = posture(address, kea=kea, dns=dns, addrs=addrs, relayed=relayed,
                list_name=list_name if hostname else "", hostname=hostname)
    out.update(server=p["server"], subnet_id=p["subnet_id"], dns=p["dns"],
               relayed=p.get("relayed", False), relay=p.get("relay") or {},
               subnet_to_add=p.get("subnet_to_add") or {})
    out["reasons"] += p["reasons"]
    try:
        got = kea.command("config-get")
        if got.get("ok"):
            out["reasons"] += conflicts(_dhcp4(got["result"]), _leases(kea), mac, address)
    except Refused as exc:
        out["reasons"].append(str(exc))
    out["ok"] = not out["reasons"]
    return out


#: The stages a pending ZTP device can be in, in order. Each is DERIVED from
#: the facts below, never stored, so no stage can be claimed that its own
#: source does not show (P6_ZTP.md section 2).
STAGES = ("reservation_missing", "reserved_not_leased", "leased_not_fetched",
          "asked_not_served", "fetched_not_reached")

#: What M4 measured about the device's patience, stated where a person reads
#: the stage it explains: IOS-XE 17.6 AutoInstall gave up after about 2.5
#: minutes and nine unanswered requests. A responder that cannot serve in that
#: window FAILS the onboarding rather than delaying it.
AUTOINSTALL_PATIENCE = ("AutoInstall gives up after a bounded window (measured on IOS-XE "
                        "17.6: about 2.5 minutes, nine requests), and then the device "
                        "needs a reload to ask again")


def _peer_host(value: str) -> str:
    """A recorded peer, with a v4-mapped form (rows written before M4's fix)
    read as its IPv4 address."""
    try:
        ip = ipaddress.ip_address(str(value).split("%", 1)[0])
    except ValueError:
        return str(value)
    return str(ip.ipv4_mapped) if ip.version == 6 and ip.ipv4_mapped else str(ip)


def progress(entry: dict, *, kea=None, fetches=None, list_name: str = "") -> dict:
    """Where a pending ZTP device has got to, each fact from its own source:

    - the reservation, read from Kea's RUNNING config (what the device will
      be offered), not from the fragment (what the tool meant to write);
    - the lease, from Kea's lease table;
    - the fetch, from the responder's own audit rows.

    "Reached" needs no fact here: a pending device has not been reached, and
    phase 2's verify is what ends pending.

    *list_name* is the device's network: its Kea is its Kea OWNER's (`kea_home`, C1252: this
    asked a client built for no network, so a device in a network with a Kea of its own read
    as ``reservation_missing``).
    """
    mac, want = entry.get("mgmt_mac", ""), entry.get("reserved_address", "")
    name = entry.get("name", "")
    kea = kea or _kea(kea_home(list_name)["owner"] if list_name else "")
    out = {"reservation": {}, "lease": {}, "fetch": {}, "stage": "unknown", "summary": ""}

    r = kea.reservation_for(mac)
    if r.get("state") == "reserved":
        out["reservation"] = ({"state": "written", "address": r.get("address")}
                              if r.get("address") == want else
                              {"state": "differs", "address": r.get("address")})
    elif r.get("state") == "not_reserved":
        out["reservation"] = {"state": "missing"}
    else:
        out["reservation"] = {"state": "unknown", "error": r.get("error", "")}

    lease = kea.lease_for(mac)
    out["lease"] = ({"state": "leased", "address": lease.get("address")}
                    if lease.get("state") == "found" else
                    {"state": "none"} if lease.get("state") == "none" else
                    {"state": "unknown", "error": lease.get("error", "")})

    if fetches is None:
        from modules import reveal_audit
        fetches = reveal_audit.entries(limit=2000)
    # BY NAME OR BY ADDRESS. A request the responder could not attribute is
    # recorded against "?" with the requesting address (M4: nine of them), and
    # it is still this device asking.
    # Only an UNATTRIBUTED row matches by address: a row naming another
    # device is that device's, whatever address it came from.
    # ONLY THIS ONBOARDING'S (C1187). A name re-created after an Abandon is a new
    # onboarding with a new credential, and the first one's fetch is still in the
    # record under the same name and address: the second s6 drew the first one's
    # "fetched", so Verify would have met a device holding the old credential. A
    # fetch counts from this onboarding's Create (`onboarded_at`, stamped before the
    # reservation is written, so nothing of its own can precede it); the responder
    # renders each serve from the credential staged at that Create. Both stamps are
    # `%Y-%m-%dT%H:%M:%SZ`, compared as text. An entry with no `onboarded_at` (none
    # is pending without one) is not bounded.
    since = entry.get("onboarded_at") or ""
    rows = [f for f in fetches if str(f.get("actor", "")).startswith("ztp:")
            and str(f.get("at") or "") >= since
            and (f.get("target") == name
                 or (f.get("target") in ("?", "", None)
                     and _peer_host(f.get("peer", "")) == want))]
    served = [f for f in rows if f.get("what") == "bootstrap_config"]
    refused = [f for f in rows if f.get("what") == "bootstrap_config_refused"]
    if served:
        f = served[0]
        out["fetch"] = {"state": "fetched", "at": f.get("at"), "peer": f.get("peer"),
                        "sha256": f.get("sha256", ""), "count": len(served),
                        "first": served[-1].get("at")}
    elif refused:
        f = refused[0]
        out["fetch"] = {"state": "refused", "at": f.get("at"), "peer": f.get("peer"),
                        "reason": f.get("detail", ""), "count": len(refused),
                        "first": refused[-1].get("at")}
    else:
        out["fetch"] = {"state": "none"}

    res, ls, fe = out["reservation"]["state"], out["lease"]["state"], out["fetch"]["state"]
    if res == "unknown" or ls == "unknown":
        out["summary"] = ("Kea could not be asked: "
                          + (out["reservation"].get("error") or out["lease"].get("error") or ""))
    elif res != "written":
        out["stage"] = "reservation_missing"
        out["summary"] = (f"the Kea reservation {mac} -> {want} is NOT in Kea"
                          + (f" (Kea reserves it -> {out['reservation']['address']})"
                             if res == "differs" else "")
                          + ". Abandon and re-create")
    elif ls == "none":
        out["stage"] = "reserved_not_leased"
        out["summary"] = (f"reserved {mac} -> {want}; no lease yet: the device has "
                          "not asked, or has not booted")
    elif fe == "refused":
        # THE DEVICE ASKED AND WAS NOT SERVED, a different state from "has not
        # asked yet", and the more urgent one: its patience is finite.
        f = out["fetch"]
        out["stage"] = "asked_not_served"
        out["summary"] = (f"leased {out['lease']['address']}; it ASKED {f['count']} time(s) "
                          f"between {f['first']} and {f['at']} and was not served "
                          f"(last reason: {f['reason']}). {AUTOINSTALL_PATIENCE}")
    elif fe != "fetched":
        out["stage"] = "leased_not_fetched"
        out["summary"] = (f"leased {out['lease']['address']}; it has not asked for its "
                          "config yet (the responder has recorded nothing from it)")
    else:
        # NO CLAIM THAT VERIFY WILL REACH IT: M4 fetched and applied its
        # config and still refused SSH. Fetched is a fact; reachable is what
        # Verify finds out.
        f = out["fetch"]
        out["stage"] = "fetched_not_reached"
        out["summary"] = (f"fetched its config {f['count']} time(s) between {f['first']} "
                          f"and {f['at']} (sha256 {f['sha256'][:12]}); next, Verify must "
                          "reach it over SSH with the staged credential")
    return out


def _refuse_all(out: dict, why: str) -> dict:
    out["error"] = why
    for mac, o in out["outcomes"].items():
        if o["outcome"] in ("written", "removed"):
            out["outcomes"][mac] = {"outcome": "refused", "detail": why}
    return out
