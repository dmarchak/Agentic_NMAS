"""C1346: ZTP for a device BEHIND A DHCP RELAY (docs/P6_ZTP.md, "Relayed ZTP (C1346)").

P.6 built ZTP for a device on the segment Kea listens on, and every rule it set holds that
segment's shape: the config server is this host's own address in the device's subnet (D3), the
reservation goes in the one fragment the directly attached subnet includes (D1), and D4's second
condition is a broadcast DNS probe on that segment. A device behind a relay has none of these:
this host owns no address in its subnet, its subnet includes its own reservations file, and a
broadcast from it never reaches this host as a broadcast. Each is answered here, by measurement or
from committed intent, never by a setting:

- **Which subnets are relayed ZTP subnets: a declaration on the subnet.** Kea's subnet carries
  ``"user-context": {"mercury-ztp": "relayed"}``, set by the DHCP page's Add (``dhcp_subnets``,
  the one write path for subnets) and recorded with the subnet in ``dhcp/subnets.yml``. Nothing
  measurable tells a ZTP segment from a host VLAN behind the same relay (both are relayed to this
  host), so it is one declaration, kept where the subnet is.
- **The fragment: the subnet's own reservations file, and it is ZTP's whole.** A declared subnet's
  ``reservations-<id>.json`` is written by ZTP's writer only; the DHCP page refuses a reservation
  there, as it does in the directly attached ZTP subnet. One owner per file.
- **The config server (D3 for a relayed subnet).** The address the relay forwards the device's
  DISCOVER to: the one ``ip helper-address`` target, in the relay's COMMITTED intent on that
  prefix, that is also one of this host's own addresses on an interface Kea listens on (measured
  from the host's interfaces each time). That is where Kea hears the device, so it is the address
  the device can reach. None, or more than one, is refused naming both sides.
- **Option 3 (D4 restated, the operator, 2026-10-19):** on a relayed ZTP subnet a reservation may
  carry ``routers`` as the relay's own interface address (Kea's ``relay.ip-addresses``, which must
  agree with intent) and nothing else; option 6 is never sent. A choice per reservation, off by
  default, recorded in the reservation and in the plan's hash.
- **D4's second condition on a relayed segment.** The relay forwards UDP broadcasts for its
  default ports, DNS (53) among them, to every helper target (IOS's ``ip forward-protocol``
  default). So a device's broadcast DNS query reaches each helper target as a unicast, and the
  relay itself answers it if it runs ``ip dns server``. MEASURED: a unicast query (the RFC 6761
  name P.6 uses) to every helper target, sent from the server address; READ from the relay's
  committed golden: no ``ip dns server``. Either one answering is D4 violated; a probe that could
  not be sent, or a golden that cannot be read, is unknown, never silent.
- **The route back.** The TFTP reply and phase 2's SSH both leave this host for the device's
  address: ``ip -4 route get <address> from <server>`` must find a route (a read, no root).
- **The firewall.** ufw admits udp/69 from the management subnet only (docs/DEPLOY_LINUX.md).
  The host step ``scripts/host-steps/c1346-ztp-relayed-firewall.sh`` admits each declared subnet
  and writes what ``ufw status`` showed it (root reads ufw; this process cannot) to a record
  beside the ZTP fragment; job health compares the declared subnets with that record, an absent
  record and an unreadable one kept apart.

**IPv4 only (C1245).** ZTP reserves through DHCPv4; an IPv6 relayed subnet or address is refused
by name. **A relay Mercury does not manage is refused**: its helper target, its own address
(option 3's only value) and its config (the DNS check) would all have to be typed in, and a typed
copy of the server address is how ``tftp_server_ip`` came to name an address the host does not
have (C48).

**Not changed:** the discovery classes (board L) test ``pkt4.giaddr == 0.0.0.0``, so they never
match a relayed client; a reserved client is KNOWN, so they would not match it anyway.
"""

import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import struct
import subprocess
import time

from modules.nsot.ztp import DNS_PROBE_NAME, Refused

log = logging.getLogger(__name__)

#: The declaration on a Kea subnet: ``"user-context": {DECLARATION: RELAYED}``.
DECLARATION = "mercury-ztp"
RELAYED = "relayed"

#: The record the firewall host step writes beside the ZTP fragment (root reads ufw, this
#: process cannot): ``{"read_at", "interface", "admitted": [prefix], "source"}``.
FIREWALL_RECORD = "ztp-firewall.json"
FIREWALL_STEP = "scripts/host-steps/c1346-ztp-relayed-firewall.sh"
#: The responder's socket unit, whose `BindToDevice=` names the interface udp/69 is served on.
RESPONDER_SOCKET_UNIT = "/etc/systemd/system/nmas-ztp-responder.socket"

DNS_PROBE_TIMEOUT = 2.0
DNS_PROBE_REUSE_SECONDS = 300
ROUTE_TIMEOUT = 5


# ── the declaration ────────────────────────────────────────────────────────────────────────

def declared(subnet) -> bool:
    """Is *subnet* (a Kea subnet dict, from config-get or Mercury's subnet file) a relayed ZTP
    subnet?"""
    if not isinstance(subnet, dict):
        return False
    ctx = subnet.get("user-context")
    return isinstance(ctx, dict) and ctx.get(DECLARATION) == RELAYED


def declaration() -> dict:
    """The user-context a relayed ZTP subnet carries."""
    return {DECLARATION: RELAYED}


def relayed_subnets(dhcp4: dict) -> list:
    """Every declared subnet in Kea's IPv4 configuration, those in shared networks too."""
    every = list(dhcp4.get("subnet4") or [])
    for net in dhcp4.get("shared-networks") or []:
        every += list(net.get("subnet4") or [])
    return [s for s in every if declared(s)]


def ipv4_only(text: str, what: str) -> None:
    """Refuse an IPv6 *text* by name (C1245: ZTP is IPv4 only)."""
    value = str(text or "").strip()
    try:
        version = (ipaddress.ip_network(value, strict=False) if "/" in value
                   else ipaddress.ip_address(value)).version
    except ValueError:
        return
    if version == 6:
        raise Refused(f"{what} {value} is IPv6: ZTP reserves and serves IPv4 (DHCPv4) "
                      "addresses only (C1245), so a relayed IPv6 subnet is never a ZTP subnet")


def fragment(main_config: str, subnet_id) -> str:
    """A declared subnet's reservations file: the subnet's own (`dhcp_reservations.fragment`)."""
    from modules import dhcp_reservations as D

    return D.fragment(main_config, "IPv4", subnet_id)


def declared_in_file(main_config: str) -> tuple:
    """``([(subnet_id, prefix, fragment)], error)``: the declared subnets as Mercury's IPv4 subnet
    file holds them, read without asking Kea (the responder and the host step read this way).
    An absent subnet file is no declared subnet (the subnets were never moved, C529 step 5); an
    unreadable one is the error, never "none"."""
    from modules import dhcp_subnets as S

    path = S.subnets_file(main_config, "IPv4")
    try:
        with open(path, encoding="utf-8") as fh:
            subnets = S.load(fh.read())
    except FileNotFoundError:
        return [], ""
    except (OSError, S.Refused) as exc:
        return [], f"{path} could not be read: {exc}"
    return [(s.get("id"), str(s.get("subnet", "")), fragment(main_config, s.get("id")))
            for s in subnets if declared(s)], ""


# ── the relay, from committed intent ───────────────────────────────────────────────────────

def intent_everywhere() -> dict:
    """Committed intent's IPv4 interface facts across every network
    (`readers.dhcp.intent_facts`), each entry naming its network: ``{"IPv4": {prefix:
    [entry]}, "errors": [str]}``."""
    from modules.device import get_device_lists
    from modules.readers.dhcp import intent_facts

    out = {"IPv4": {}, "errors": []}
    for item in get_device_lists():
        got = intent_facts(item["name"])
        if got.get("error"):
            out["errors"].append(f"{item['name']}: {got['error']}")
        for prefix, entries in (got.get("IPv4") or {}).items():
            out["IPv4"].setdefault(prefix, []).extend(dict(e, network=item["name"])
                                                       for e in entries)
    return out


def relay_for(prefix: str, facts: dict) -> dict:
    """The one interface in committed intent on *prefix*, with its IPv4 helper targets:
    ``{device, iface, address, relays, network}``. Refused naming what was found."""
    ipv4_only(prefix, "the subnet")
    entries = list(((facts or {}).get("IPv4") or {}).get(prefix) or [])
    if not entries:
        errors = list((facts or {}).get("errors") or [])
        raise Refused(
            f"no device Mercury manages has an interface on {prefix} in committed intent, so "
            "this relayed ZTP subnet's relay cannot be read: its ip helper-address names the "
            "config server, its own address is option 3's only value, and its committed golden "
            "is what D4's DNS check reads. A relay Mercury does not manage is refused rather "
            "than typed in (C48)" + (f"; these networks' intent could not be read, so it may "
                                     f"be there: {'; '.join(errors)}" if errors else ""))
    if len(entries) != 1:
        names = ", ".join(f"{e.get('device')} {e.get('iface')} ({e.get('address')})"
                          for e in entries)
        raise Refused(f"expected exactly one relay interface on {prefix} in committed intent, "
                      f"found {len(entries)}: {names}")
    e = entries[0]
    helpers = []
    for h in e.get("relays") or []:
        try:
            if ipaddress.ip_address(str(h)).version == 4:
                helpers.append(str(h))
        except ValueError:
            continue
    if not helpers:
        raise Refused(f"{e.get('device')} {e.get('iface')} ({e.get('address')}) is on {prefix} "
                      "and relays to no DHCP server in committed intent (no ip helper-address), "
                      "so a device there is answered by nobody")
    return {"device": e.get("device", ""), "iface": e.get("iface", ""),
            "address": e.get("address", ""), "relays": helpers,
            "network": e.get("network", "")}


def kea_relay(subnet: dict) -> list:
    """Kea's ``relay.ip-addresses`` for *subnet* (the giaddr it matches the subnet on)."""
    relay = subnet.get("relay") if isinstance(subnet, dict) else None
    return [str(a) for a in ((relay or {}).get("ip-addresses") or [])]


def relay_agrees(subnet: dict, relay: dict) -> None:
    """Kea's relay address for the subnet is intent's relay address, and only it."""
    got = kea_relay(subnet)
    if got != [relay["address"]]:
        raise Refused(f"Kea's subnet {subnet.get('id')} names relay address(es) "
                      f"{got or '(none)'}; committed intent puts the relay {relay['device']} "
                      f"{relay['iface']} at {relay['address']}. Option 3's only value is the "
                      "relay's own address, so the two must be that one address")


# ── the server address (D3 for a relayed subnet) ───────────────────────────────────────────

def _host_addrs(addrs=None) -> dict:
    if addrs is not None:
        return addrs
    import psutil

    return {name: [a.address for a in entries if a.family == socket.AF_INET]
            for name, entries in psutil.net_if_addrs().items()}


def listening_addresses(dhcp4: dict, addrs=None) -> list:
    """This host's IPv4 addresses on the interfaces Kea listens on (``interfaces-config``: an
    interface, an ``interface/address``, or ``*`` for every one)."""
    addrs = _host_addrs(addrs)
    out = set()
    for item in (dhcp4.get("interfaces-config") or {}).get("interfaces") or []:
        name, _, only = str(item).partition("/")
        names = list(addrs) if name == "*" else [name]
        for n in names:
            for a in addrs.get(n, []):
                if not only or a == only:
                    out.add(a)
    return sorted(out)


def server_for(relay: dict, dhcp4: dict, addrs=None) -> str:
    """The config server for a device behind *relay*: the one helper target that is this
    host's own address on an interface Kea listens on."""
    mine = listening_addresses(dhcp4, addrs)
    hits = sorted(set(relay["relays"]) & set(mine))
    if len(hits) != 1:
        raise Refused(f"expected exactly one of {relay['device']} {relay['iface']}'s helper "
                      f"targets {relay['relays']} (committed intent) to be an address of this "
                      f"host on an interface Kea listens on {mine}, found {len(hits)}"
                      + (f": {hits}" if hits else "; the relay forwards the device's DISCOVER "
                         "somewhere Kea does not hear it"))
    return hits[0]


def host_in(prefix: str, addrs=None) -> list:
    """This host's addresses inside *prefix* (a relayed subnet has none)."""
    net = ipaddress.ip_network(prefix, strict=False)
    return sorted({a for found in _host_addrs(addrs).values() for a in found
                   if ipaddress.ip_address(a) in net})


# ── option 3, the relay's own address and nothing else ────────────────────────────────────

def routers_refusal(value: str, relay_address: str) -> str:
    """Why *value* may not be a relayed ZTP reservation's option 3, or ""."""
    if not relay_address:
        return (f"routers {value}: option 3 is allowed only on a relayed ZTP subnet, as the "
                "relay's own address (D4 restated); this subnet names no relay address")
    if str(value).strip() != relay_address:
        return (f"routers {value}: on a relayed ZTP subnet option 3 may be only the relay's own "
                f"address, {relay_address} (D4 restated)")
    return ""


# ── D4's second condition on a relayed segment ─────────────────────────────────────────────

def _dns_query(name: str) -> tuple:
    qid = secrets.randbelow(0xFFFF)
    header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\0"
    return qid, header + qname + struct.pack(">HH", 1, 1)


def unicast_answers(target: str, source: str, timeout: float = DNS_PROBE_TIMEOUT,
                    sock_factory=None, clock=time.time) -> dict:
    """Does *target* answer a DNS query on udp/53, sent from *source*? What the relay makes of
    the device's broadcast query: a unicast to each helper target. Any reply carrying the
    query's id is an answer, whatever it says. ``{"state": "silent"|"answered"|"unknown",
    "error"}``; a query that could not be sent is unknown, never silent."""
    sock_factory = sock_factory or (lambda: socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
    qid, query = _dns_query(DNS_PROBE_NAME)
    try:
        s = sock_factory()
        try:
            s.bind((source, 0))
            s.settimeout(0.2)
            s.sendto(query, (target, 53))
            deadline = clock() + timeout
            while clock() < deadline:
                try:
                    data, (peer, _port) = s.recvfrom(4096)
                except socket.timeout:
                    continue
                except ConnectionRefusedError:
                    # An ICMP port unreachable: nothing listens there, measured.
                    return {"state": "silent", "error": ""}
                if peer == target and len(data) >= 2 and struct.unpack(">H", data[:2])[0] == qid:
                    return {"state": "answered", "error": ""}
        finally:
            s.close()
    except OSError as exc:
        return {"state": "unknown",
                "error": f"the query to {target} could not be sent from {source}: {exc}"}
    return {"state": "silent", "error": ""}


def relay_dns_lines(golden_text: str) -> dict:
    """What the relay's committed golden says about DNS: ``{"dns_server": bool,
    "forwards_dns": bool}`` (``ip dns server`` at the top level; udp/53 forwarded to the
    helper targets unless ``no ip forward-protocol udp domain`` or ``... udp 53``)."""
    lines = (golden_text or "").splitlines()
    server = any(re.match(r"^ip dns server\b", l) for l in lines)
    stopped = any(re.match(r"^no ip forward-protocol udp (domain|53)\b", l) for l in lines)
    return {"dns_server": server, "forwards_dns": not stopped}


_probe_cache = {}


def dns_posture(server: str, relay: dict, golden: dict, probe=unicast_answers,
                clock=time.time) -> dict:
    """D4's second condition for a relayed segment: ``{"state", "answerers", "measured_at",
    "error", "read", "probed"}``. MEASURED: each helper target asked by unicast from *server*
    (each answer reused for :data:`DNS_PROBE_REUSE_SECONDS`, its time kept). READ: the relay's
    committed golden (*golden*: ``{"text", "refused"}``), which must not run ``ip dns server``."""
    out = {"state": "unknown", "answerers": [], "measured_at": clock(), "error": "",
           "read": {}, "probed": {}}
    text = (golden or {}).get("text")
    if text is None:
        out["error"] = (f"{relay['device']}'s committed golden could not be read "
                        f"({(golden or {}).get('refused') or 'it has none'}), so whether the "
                        "relay itself answers DNS cannot be told")
        return out
    out["read"] = relay_dns_lines(text)
    if out["read"]["dns_server"]:
        out["answerers"].append(f"{relay['device']} (ip dns server, in its committed golden)")
    unknown = []
    for target in relay["relays"]:
        key = (server, target)
        hit = _probe_cache.get(key)
        if hit and hit["state"] != "unknown" and clock() - hit["at"] < DNS_PROBE_REUSE_SECONDS:
            got = hit
        else:
            got = dict(probe(target, server), at=clock())
            _probe_cache[key] = got
        out["probed"][target] = got["state"]
        out["measured_at"] = min(out["measured_at"], got["at"])
        if got["state"] == "answered":
            out["answerers"].append(f"{target} (a helper target: the relay forwards udp/53 "
                                    "broadcasts to it)")
        elif got["state"] != "silent":
            unknown.append(got.get("error") or f"{target}: no answer could be measured")
    if out["answerers"]:
        out["state"] = "answered"
    elif unknown:
        out["error"] = "; ".join(unknown)
    else:
        out["state"] = "silent"
    return out


def relay_golden(relay: dict) -> dict:
    """The relay's committed golden (`repo.committed_golden_for`), ``{"text", "refused"}``."""
    from modules.nsot import listref, manifest
    from modules.nsot import repo as R

    try:
        if not listref.exists(relay["network"]):      # a read creates no list (C51)
            return {"text": None, "refused": f"no network named {relay['network']!r}"}
        ref = listref.resolve(relay["network"])
        _identity, entry = manifest.find_by_name(ref.repo_dir, relay["device"])
    except Exception as exc:                          # noqa: BLE001 (said as the refusal)
        return {"text": None, "refused": f"its manifest could not be read: {exc}"}
    if not entry:
        return {"text": None, "refused": f"{relay['device']} has no manifest entry in "
                                          f"{relay['network']}"}
    got = R.committed_golden_for(ref.repo_dir, entry)
    if got.get("text") is None:
        return {"text": None, "refused": got.get("refused") or "it has no committed golden"}
    return got


# ── the route back ─────────────────────────────────────────────────────────────────────────

def _run(cmd: list) -> tuple:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=ROUTE_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    return proc.returncode, (proc.stdout or proc.stderr or "").strip()


def route_to(address: str, server: str, run=None) -> dict:
    """``ip -4 -o route get <address> from <server>``: ``{"state": "routed"|"none"|"unknown",
    "via", "dev", "detail"}``. The TFTP reply and phase 2's SSH both take this route."""
    rc, text = (run or _run)(["ip", "-4", "-o", "route", "get", address, "from", server])
    if rc is None:
        return {"state": "unknown", "via": "", "dev": "",
                "detail": f"ip route get could not run: {text}"}
    if rc != 0 or re.search(r"\b(unreachable|prohibit|blackhole)\b", text):
        return {"state": "none", "via": "", "dev": "", "detail": text or f"exit {rc}"}
    via = re.search(r"\bvia (\S+)", text)
    dev = re.search(r"\bdev (\S+)", text)
    return {"state": "routed", "via": via.group(1) if via else "",
            "dev": dev.group(1) if dev else "", "detail": text}


# ── the posture of a relayed subnet ────────────────────────────────────────────────────────

def posture(dhcp4: dict, subnet: dict, *, address: str = "", addrs=None, facts=None,
            golden=None, dns=None, route=None) -> dict:
    """What a relayed ZTP subnet needs before a reservation there can work, each a reason when
    it does not hold: ``{"reasons", "server", "relay", "dns", "route"}``. *facts*, *golden*,
    *dns* and *route* are seams (committed intent everywhere, the relay's committed golden,
    :func:`dns_posture`, :func:`route_to`)."""
    out = {"reasons": [], "server": "", "relay": {}, "dns": {}, "route": {}}
    prefix = str(subnet.get("subnet", ""))
    try:
        ipv4_only(prefix, "the subnet")
        mine = host_in(prefix, addrs)
        if mine:
            raise Refused(f"subnet {subnet.get('id')} ({prefix}) is declared relayed for ZTP, "
                          f"and this host has {', '.join(mine)} in it: a subnet this host is on "
                          "is not relayed")
        relay = relay_for(prefix, intent_everywhere() if facts is None else facts)
        relay_agrees(subnet, relay)
        out["relay"] = relay
        out["server"] = server_for(relay, dhcp4, addrs)
    except Refused as exc:
        out["reasons"].append(str(exc))
        return out
    out["route"] = route_to(address or relay["address"], out["server"], route)
    if out["route"]["state"] == "none":
        out["reasons"].append(f"this host has no route to {address or relay['address']} from "
                              f"{out['server']} ({out['route']['detail']}): the device's TFTP "
                              "reply and phase 2's SSH both need one")
    elif out["route"]["state"] != "routed":
        out["reasons"].append(f"whether this host routes to {address or relay['address']} "
                              f"could not be measured ({out['route']['detail']}); a check that "
                              "did not run has not passed")
    out["dns"] = (dns or dns_posture)(out["server"], relay,
                                      (golden or relay_golden)(relay))
    state = out["dns"].get("state")
    if state == "answered":
        out["reasons"].append(
            f"D4: something answers DNS for the relayed ZTP segment {prefix} "
            f"({'; '.join(out['dns']['answerers'])}), which would give a configless node a "
            "resolver with no DHCP option at all")
    elif state != "silent":
        out["reasons"].append(
            f"D4: whether anything answers DNS for the relayed ZTP segment {prefix} could not "
            f"be measured ({out['dns'].get('error') or 'no answer'}); a check that did not run "
            "has not passed")
    return out


# ── the firewall: udp/69 admitted from each declared subnet ────────────────────────────────

def firewall_record_path(fragment: str) -> str:
    """The firewall record, beside the network's ZTP fragment (`kea_ztp_fragment`, in the
    folder of Mercury's Kea files the NMAS user owns, D1)."""
    return os.path.join(os.path.dirname(fragment), FIREWALL_RECORD)


def responder_interface(unit_path: str = RESPONDER_SOCKET_UNIT) -> str:
    """The interface the responder's socket is bound to (`BindToDevice=`), or ""."""
    try:
        with open(unit_path, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^\s*BindToDevice\s*=\s*(\S+)", line)
                if m:
                    return m.group(1)
    except OSError:
        return ""
    return ""


def parse_ufw_status(text: str, interface: str) -> list:
    """The sources ``ufw status`` shows admitted to udp/69 on *interface* (or on every
    interface): each an IPv4 network (``Anywhere`` as ``0.0.0.0/0``)."""
    out = []
    for line in (text or "").splitlines():
        line = line.split("#", 1)[0].strip()
        m = re.match(r"^69(?:/udp)?(?:\s+on\s+(\S+))?\s+ALLOW(?:\s+IN)?\s+(\S+)", line)
        if not m or "(v6)" in line:
            continue
        on, source = m.group(1), m.group(2)
        if on and interface and on != interface:
            continue
        if source == "Anywhere":
            out.append("0.0.0.0/0")
            continue
        try:
            out.append(str(ipaddress.ip_network(source, strict=False)))
        except ValueError:
            continue
    return out


def admitted(prefix: str, sources: list) -> bool:
    net = ipaddress.ip_network(prefix, strict=False)
    for s in sources:
        try:
            if net.subnet_of(ipaddress.ip_network(s, strict=False)):
                return True
        except (ValueError, TypeError):
            continue
    return False


def read_firewall_record(path: str) -> dict:
    """``{"state": "absent"|"unreadable"|"read", "admitted", "read_at", "interface",
    "error"}``: absent (the host step has not run) and unreadable kept apart."""
    out = {"state": "absent", "admitted": [], "read_at": "", "interface": "", "error": ""}
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return out
    except (OSError, ValueError) as exc:
        return dict(out, state="unreadable", error=str(exc))
    if not isinstance(doc, dict) or not isinstance(doc.get("admitted"), list):
        return dict(out, state="unreadable", error="it is not the host step's record")
    return dict(out, state="read", admitted=[str(a) for a in doc["admitted"]],
                read_at=str(doc.get("read_at") or ""), interface=str(doc.get("interface") or ""))


def firewall_row(declared_subnets: list, record: dict, path: str) -> dict:
    """Job health's row: every declared subnet's prefix admitted to udp/69, as the host step's
    record says ``ufw status`` showed it. *declared_subnets* is ``[(id, prefix)]``."""
    what = "the firewall admits udp/69 (the ZTP responder) from every relayed ZTP subnet"
    row = {"unit": "ztp-firewall", "what": what, "max_age_minutes": 0}
    if record["state"] == "absent":
        return dict(row, state="unknown",
                    detail=(f"{path} is absent: what the firewall admits has not been read. "
                            f"Run {FIREWALL_STEP} on the host (it admits each relayed ZTP "
                            "subnet and records what ufw status shows) -- not the same as ok"))
    if record["state"] == "unreadable":
        return dict(row, state="unknown",
                    detail=f"{path} could not be read ({record['error']}) -- not the same as ok")
    closed = [f"subnet {sid} ({prefix})" for sid, prefix in declared_subnets
              if not admitted(prefix, record["admitted"])]
    when = f" (ufw status as the host step read it at {record['read_at'] or 'an unstated time'})"
    if closed:
        return dict(row, state="firewall_closed",
                    detail=(f"udp/69 is not admitted from {', '.join(closed)}{when}: a device "
                            f"there is never answered. Run {FIREWALL_STEP} on the host"))
    return dict(row, state="ok",
                detail=(f"udp/69 admitted from {', '.join(p for _i, p in declared_subnets)}"
                        f"{when}"))
