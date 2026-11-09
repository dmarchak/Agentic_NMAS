"""The diagnosis runbooks (board H amendment item 1, part H14; docs/HEAL_TO_INTENT.md 19.3): a
fixed list of steps in code, each a read or a comparison of what was read with committed
intent, that sends no command that is not a read, changes nothing and calls no model. Its
output is a **diagnosis**: the steps with their results, a ranked list of hypotheses with their
evidence, and the checks that passed ("ruled out").

**The runbooks** (`RUNBOOKS`): "adjacency down with both ends at intent" (H14: OSPF, OSPFv3
and BGP, here), "A can't reach B" (H15, `modules/heal/diagnose_reach.py`, on `path_trace`:
IPv4, and IPv6 by `show ipv6 cef` since H18's captures, its limits said there) and "a
telemetry stream lost" (C2828, `modules/heal/diagnose_stream.py`: the device to its collector
on the stream's port, both ends, and the time since the stream's cause was put back).

**Every read goes through the one reads engine** (`modules/nsot/reads.py`), as its caller kind
``diagnosis``, whose `reads.EXTRAS` entry is empty: every command passes
`readonly_commands.refusal` with no extras (no `send log`, no `verify`, no `terminal`), each
device held while it is read (a device another operation holds is skipped by name, never
queued), masked, capped and recorded on History › Reads. A step names each read by
``read:<run>:<device>:<command>``; the step log never holds a device's text.

**Its commands are code templates** (`TEMPLATES`) whose arguments come from intent and the
network model, never typed: an interface is a name intent holds, in its interface-name shape;
an address is one `ipaddress` parses. tests/test_heal_diagnose.py renders every command every
runbook can produce, on each platform, and holds each to the reads engine's rule and the model's
read rule with `SAFE_MODIFIERS` (19.5's pipe rule, as a test, not a second path).

**Its bounds** (N24):
- at most `MAX_PER_DEVICE` (14) reads per device, the adjacency runbook's own count on a
  dual-stack OSPF and BGP link;
- at most `MAX_COMMANDS` (70) device commands per diagnosis, about 2.5 times the longest
  runbook's fixed count (28, both ends); a run reaching it stops and says where;
- **one diagnosis at a time per device** (`DiagnosisLock`): across processes, an exclusive
  `flock` the kernel releases with its holder, refused by name and never queued ("not
  diagnosed: edge1 is in diagnosis dg-..."), beside the reads engine's per-read hold;
- both ends read concurrently (`fanout.read_each`); each ping inside
  `readonly_commands.bound_seconds`; error counters read twice `DELTA_SECONDS` apart, and the
  difference is the evidence. **Never `clear counters`**: it erases what a diagnosis reads.

**"Diverges from intent," at each end.** The comparison is with the network model compiled from
committed intent (`modules/network_model.py`: links and subnets, each interface's addresses,
shutdown and OSPF area) and intent's own interface lines (OSPF's timers, network type,
authentication, passive, the MTU, the access lists bound). Where intent is silent the
platform's measured default is the expected value; none is measured for OSPF's timers or the
MTU today (`modules/nsot/interface_defaults.json`), and the step says so: the ends are then
compared with each other only. Both ends at intent, yet disagreeing, is its own finding: intent
disagrees with itself.

**How the hypotheses are ranked** (`RULES`, each with a planted case in its test):
1. by strength: decisive, strong, circumstantial;
2. a hypothesis whose evidence is incomplete (a read skipped, failed or not yet interpreted)
   below every complete one of its strength, naming the read it lacks;
3. bottom-up by layer: physical, link, network, protocol, policy;
4. by the number of independent reads that agree, both ends counting as two.
At most `MAX_SHOWN` (5) are shown, the rest counted. No rule fires: "no cause found in what
Mercury reads", with the ruled-out list. It never guesses.

**Records** (H6's store, `steplog`): the diagnosis is one ``diagnosis`` row, masked: attached
to its incident when the heal ran it, its own record when a person did. "Diagnosed" is not a
fix: a diagnosis clears nothing.
"""

import ipaddress
import json
import logging
import os
import re
import time
import uuid

log = logging.getLogger(__name__)

RUNBOOKS = {"adjacency_down": "adjacency down with both ends at intent",
            "cant_reach": "A can't reach B",
            "stream_lost": "a telemetry stream lost"}
#: The runbooks built so far.
BUILT = ("adjacency_down", "cant_reach", "stream_lost")
#: The reads engine's caller kind for a diagnosis (`reads.EXTRAS`: none).
KIND = "diagnosis"
#: Device commands per diagnosis (N24): about 2.5 x the longest runbook's 28.
MAX_COMMANDS = 70
#: Reads per device per diagnosis: the adjacency runbook's own count, dual-stack OSPF and BGP.
MAX_PER_DEVICE = 14
#: Between the two reads of an interface's error counters. To be measured (H18); 10 s is
#: 19.3's figure.
DELTA_SECONDS = 10.0
#: How far back the device's log is read for a configuration change outside Mercury.
LOG_WINDOW_SECONDS = 3600
#: A show read's bound in the worst-case time (the reads engine's config read bound).
SHOW_BOUND_SECONDS = 120
MAX_SHOWN = 5
STRENGTHS = ("decisive", "strong", "circumstantial")
LAYERS = ("physical", "link", "network", "protocol", "policy")
#: The diagnosis's steps, in order, as the manual names them (H16's how-it-works page).
STEPS = ("plan", "hold", "read", "read again", "logs", "compare", "rank", "record")
#: A round's reads: the first, then the second `DELTA_SECONDS` later.
ROUNDS = (1, 2)
LOCK_DIR = os.path.join("heal", "diagnosis")

#: An interface name intent holds, in its shape (a field spliced into a command is one token).
_IFNAME = re.compile(r"[A-Za-z][A-Za-z-]{0,30}[0-9][0-9/.:]{0,15}")
#: An access list's name or number as IOS takes it in `ip access-group`, one word.
_ACLNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
#: A MAC address as IOS prints it in ARP and the MAC table (captures: tests/fixtures/diagnose/).
_MAC = re.compile(r"[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4}")
#: A telemetry subscription's id as IOS-XE takes it (0 to 2147483647), one word of digits.
_SUBSCRIPTION = re.compile(r"[0-9]{1,10}")
_STUCK = ("EXSTART", "EXCHANGE")
_UP = ("FULL", "2WAY")


class Refused(ValueError):
    """The diagnosis asks no device; the words say why, naming both operands."""


class DiagnosisBusy(RuntimeError):
    """A device is in another diagnosis: refused by name, never queued."""

    def __init__(self, host: str, holder: dict):
        self.host, self.holder = host, holder or {}
        super().__init__(f"not diagnosed: {host} is in diagnosis "
                         f"{self.holder.get('diagnosis') or 'of an unrecorded id'} (by "
                         f"{self.holder.get('actor') or 'an unrecorded caller'}, since "
                         f"{self.holder.get('started_at') or 'an unrecorded time'}); one "
                         "diagnosis at a time per device, so nothing was read")


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def new_id() -> str:
    return "dg-" + uuid.uuid4().hex[:16]


# ── The per-device lock (N24) ───────────────────────────────────────────────────────────────

class DiagnosisLock:
    """One diagnosis per device at a time, across processes, for every device a diagnosis
    reads; a second raises `DiagnosisBusy` naming the first, never waits. Taken in the hosts'
    sorted order, all or none."""

    def __init__(self, network: str, hosts, diagnosis: str, actor: str):
        self.network, self.hosts = network, sorted(set(hosts))
        self.diagnosis, self.actor, self.fds = diagnosis, actor, []

    def _path(self, host: str) -> str:
        from modules.config import list_data_path
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", host)
        return os.path.join(list_data_path(self.network), LOCK_DIR, f"{safe}.lock")

    def __enter__(self):
        try:
            for host in self.hosts:
                self._take(host)
        except BaseException:
            self._release()
            raise
        return self

    def _take(self, host: str) -> None:
        import fcntl

        path = self._path(host)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            text = os.read(fd, 1 << 16).decode("utf-8", "replace")
            os.close(fd)
            try:
                holder = json.loads(text) if text.strip() else {}
            except ValueError:
                holder = {}
            raise DiagnosisBusy(host, holder) from None
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps({"pid": os.getpid(), "diagnosis": self.diagnosis,
                                 "actor": self.actor,
                                 "started_at": _iso(time.time())}).encode())
        self.fds.append(fd)

    def take(self, host: str) -> None:
        """Hold one more device while held (a path's next hop, found as it is followed): a
        device in another diagnosis raises `DiagnosisBusy` naming it, never waits; one already
        held is held once."""
        if host in self.hosts:
            return
        self._take(host)
        self.hosts.append(host)

    def _release(self):
        import fcntl
        while self.fds:
            fd = self.fds.pop()
            try:
                os.ftruncate(fd, 0)
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)

    def __exit__(self, *exc):
        self._release()
        return False


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
    except (OSError, ValueError, TypeError, OverflowError):
        return False
    return True


def in_diagnosis(network: str, hosts) -> dict:
    """``{host: holder}`` for each of *hosts* another diagnosis holds now, read WITHOUT taking
    the lock (the card asks before the press; the press's `DiagnosisLock` stays the authority,
    refusing by name). A holder is the lock file's record (`DiagnosisLock._take` writes it once
    held and empties it before release), counted only while the process it names lives: a
    holder that died left its record, and the kernel released its lock. A read creates
    nothing: a device never diagnosed has no file."""
    out = {}
    for host in sorted(set(hosts or ())):
        path = DiagnosisLock(network, [host], "", "")._path(host)
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read(1 << 16)
        except OSError:
            continue
        try:
            holder = json.loads(text) if text.strip() else {}
        except ValueError:
            continue
        if isinstance(holder, dict) and holder.get("diagnosis") and _alive(holder.get("pid")):
            out[host] = holder
    return out


# ── The templates: every command a runbook can send ─────────────────────────────────────────

#: Each read kind's command per dialect (`{if}` an interface intent holds, `{far}` and `{peer}`
#: addresses, `{mtu}` intent's MTU, `{src}` an update source intent holds). IOS-XE prints
#: OSPFv3's neighbours with `show ospfv3 neighbor`, vIOS with `show ipv6 ospf neighbor`
#: (measured on three fleet devices' captures).
TEMPLATES = {
    "interfaces": {"*": "show interfaces {if}"},
    "ip_interface": {"*": "show ip interface {if}"},
    "ipv6_interface": {"*": "show ipv6 interface {if}"},
    "cdp": {"*": "show cdp neighbors {if} detail"},
    "lldp": {"*": "show lldp neighbors {if} detail"},
    "ospf_interface": {"*": "show ip ospf interface {if}"},
    "ospf_neighbor": {"*": "show ip ospf neighbor {if} detail"},
    "ospfv3_interface": {"*": "show ipv6 ospf interface {if}"},
    "ospfv3_neighbor": {"cisco_iosxe": "show ospfv3 neighbor",
                        "cisco_ios": "show ipv6 ospf neighbor"},
    "link_ping": {"*": "ping {far} source {if} repeat 5 timeout 2"},
    "link_ping6": {"*": "ping ipv6 {far} source {if} repeat 5 timeout 2"},
    "df_ping": {"*": "ping {far} size {mtu} df-bit repeat 2 timeout 2"},
    "bgp_summary": {"*": "show ip bgp summary"},
    "bgp_summary6": {"*": "show bgp ipv6 unicast summary"},
    "bgp_neighbor": {"*": "show ip bgp neighbors {peer}"},
    "bgp_neighbor6": {"*": "show bgp ipv6 unicast neighbors {peer}"},
    "bgp_ping": {"*": "ping {peer} repeat 5 timeout 2"},
    "bgp_ping_src": {"*": "ping {peer} source {src} repeat 5 timeout 2"},
    "bgp_ping6": {"*": "ping ipv6 {peer} repeat 5 timeout 2"},
    "bgp_ping6_src": {"*": "ping ipv6 {peer} source {src} repeat 5 timeout 2"},
    # "A can't reach B" (H15; `diagnose_reach`): `{dest}` is B, `{nh}` a hop's next hop, `{acl}`
    # an access list a hop's interface binds. `cef` is the path trace's own read
    # (`path_trace.COMMAND`).
    "reach_ping": {"*": "ping {dest} repeat 5 timeout 2"},
    "reach_ping_src": {"*": "ping {dest} source {src} repeat 5 timeout 2"},
    "cef": {"*": "show ip cef {dest}"},
    # vIOS-L2 refuses every option after a traceroute's address, IPv4 and IPv6 (H18, measured
    # on an IOS switch: the invalid-input marker at `numeric`, and at `timeout` without it), so
    # there the read answers "no such read" (C2681); the AI's read set takes this form only.
    "traceroute": {"*": "traceroute {dest} numeric timeout 2 probe 1 ttl 1 16"},
    "route": {"*": "show ip route {dest}"},
    "arp": {"*": "show ip arp {nh}"},
    "acl_counters": {"*": "show ip access-lists {acl}"},
    # The IPv6 form (H15's rest, H18's captures): B's forwarding, route and ping, and the next
    # hop's neighbour entry by its address (the AI's shape; vIOS-L2 refuses it, measured on an
    # IOS switch, so there it is "no such read", C2681).
    "cef6": {"*": "show ipv6 cef {dest}"},
    "route6": {"*": "show ipv6 route {dest}"},
    "reach_ping6": {"*": "ping ipv6 {dest} repeat 5 timeout 2"},
    "reach_ping6_src": {"*": "ping ipv6 {dest} source {src} repeat 5 timeout 2"},
    "traceroute6": {"*": "traceroute ipv6 {dest} numeric timeout 2 probe 1 ttl 1 16"},
    "nd": {"*": "show ipv6 neighbors {nh}"},
    # A switch on the path (an SVI's egress): where the next hop's MAC is learned, and that
    # port's spanning-tree state (both captured on an IOS switch).
    "mac": {"*": "show mac address-table address {mac}"},
    "stp": {"*": "show spanning-tree interface {if}"},
    # "a telemetry stream lost" (C2828; `diagnose_stream`): the device's subscriptions and
    # their states (captured on IOS-XE), and one subscription's receiver as the device holds it
    # (`{sub}` a subscription id intent declares; not captured yet, C2890). IOS-XE's; on an
    # IOS device intent declares no subscription, so the plan never sends them there.
    "telemetry_brief": {"*": "show telemetry ietf subscription all"},
    "telemetry_receiver": {"*": "show telemetry ietf subscription {sub} receiver"},
}
#: The kind a template's answer is parsed as (an IPv6 form is its IPv4 kind's twin).
PARSE_KIND = {"link_ping6": "link_ping", "bgp_summary6": "bgp_summary",
              "bgp_neighbor6": "bgp_neighbor", "bgp_ping_src": "bgp_ping",
              "bgp_ping6": "bgp_ping", "bgp_ping6_src": "bgp_ping",
              "reach_ping_src": "reach_ping", "reach_ping6": "reach_ping",
              "reach_ping6_src": "reach_ping", "route6": "route", "traceroute6": "traceroute"}
#: What each read is for, in the step's words.
READ_WORDS = {
    "interfaces": "interface state, MTU and error counters",
    "ip_interface": "IPv4 address, IP MTU and access lists bound",
    "ipv6_interface": "IPv6 addresses and access lists bound",
    "cdp": "who CDP says is cabled there", "lldp": "who LLDP says is cabled there",
    "ospf_interface": "OSPF on the interface: area, network type, timers, authentication",
    "ospf_neighbor": "OSPF's view of its neighbours there",
    "ospfv3_interface": "OSPFv3 on the interface", "ospfv3_neighbor": "OSPFv3's neighbours",
    "link_ping": "the far end reachable on the link", "link_ping6": "the far end reachable "
    "on the link (IPv6)", "df_ping": "the MTU across the link, don't fragment",
    "bgp_summary": "the BGP session's state", "bgp_summary6": "the BGP session's state "
    "(IPv6)", "bgp_neighbor": "the BGP session's last reset, hold time and update source",
    "bgp_neighbor6": "the BGP session's last reset (IPv6)",
    "bgp_ping": "the peer reachable", "bgp_ping_src": "the peer reachable from the update "
    "source", "bgp_ping6": "the peer reachable (IPv6)", "bgp_ping6_src": "the peer reachable "
    "from the update source (IPv6)",
    "reach_ping": "does A reach B", "reach_ping_src": "does A reach B, from its loopback",
    "cef": "the forwarding path toward B", "traceroute": "the path past the managed devices",
    "route": "the route toward B and its source", "arp": "the next hop resolved (ARP)",
    "acl_counters": "an access list's match counters",
    "cef6": "the IPv6 forwarding path toward B", "route6": "the IPv6 route toward B and its "
    "source", "reach_ping6": "does A reach B (IPv6)", "reach_ping6_src": "does A reach B "
    "(IPv6), from its loopback", "traceroute6": "the IPv6 path past the managed devices",
    "nd": "the next hop resolved (IPv6 neighbours)",
    "mac": "where the next hop's MAC is learned", "stp": "that port's spanning-tree state",
    "telemetry_brief": "the device's telemetry subscriptions and their states",
    "telemetry_receiver": "a subscription's receiver as the device holds it"}
_DIALECT = {"cisco_iosxe": "cisco_iosxe", "cisco_xe": "cisco_iosxe", "cisco_ios": "cisco_ios"}


def dialect_of(value: str, host: str = "") -> str:
    """A device's config dialect, keyed by its platform (intent's or the inventory's). An
    unknown platform is refused, naming it, never read as IOS (C452:
    tests/test_unknown_platform_refused.py; a guessed dialect would send one platform's reads
    to another)."""
    got = _DIALECT.get(str(value or "").strip().lower())
    if got is None:
        from modules.nsot import platform
        raise Refused(platform.unknown_words({"hostname": host, "platform": str(value or "")}))
    return got


def render(kind: str, dialect: str, **args) -> str:
    """*kind*'s command on *dialect*, each argument checked as one token of its shape: an
    interface name (`_IFNAME`), an address of the template's family (`ipaddress`, no zone), a
    probe size the allowlist takes (`readonly_commands.PING_OPTIONS`), an access list's name
    (`_ACLNAME`), a MAC address (`_MAC`). Raises Refused naming the argument and its shape."""
    from modules.readonly_commands import PING_OPTIONS

    forms = TEMPLATES[kind]
    template = forms.get(dialect) or forms.get("*")
    family = 6 if "ipv6" in template else 4
    values = {}
    for key, value in args.items():
        text = str(value)
        if key in ("if", "src"):
            if not _IFNAME.fullmatch(text):
                raise Refused(f"{text!r} is not an interface name, so `{template}` is not sent")
        elif key == "acl":
            if not _ACLNAME.fullmatch(text):
                raise Refused(f"{text!r} is not an access list's name, so `{template}` is not "
                              "sent")
        elif key in ("far", "peer", "dest", "nh"):
            try:
                address = None if "%" in text else ipaddress.ip_address(text)
            except ValueError:
                address = None
            if address is None or address.version != family:
                raise Refused(f"{text!r} is not one IPv{family} address, so `{template}` is "
                              "not sent")
            text = str(address)
        elif key == "mtu":
            low, high = PING_OPTIONS["size"]
            if not (text.isdigit() and low <= int(text) <= high):
                raise Refused(f"{text!r} is not a probe size from {low} to {high}, so "
                              f"`{template}` is not sent")
        elif key == "mac":
            if not _MAC.fullmatch(text):
                raise Refused(f"{text!r} is not a MAC address, so `{template}` is not sent")
        elif key == "sub":
            if not (_SUBSCRIPTION.fullmatch(text) and int(text) <= 2147483647):
                raise Refused(f"{text!r} is not a telemetry subscription id, so `{template}` "
                              "is not sent")
        values[key] = text
    return template.format(**values)


def _probe_size(mtu: str) -> str:
    """Intent's MTU as the df-bit probe's size, when the allowlist takes it; else ``""`` (a
    jumbo MTU's probe would fragment past what a read may send, so the MTUs the ends print
    are compared instead)."""
    from modules.readonly_commands import PING_OPTIONS
    low, high = PING_OPTIONS["size"]
    return mtu if str(mtu).isdigit() and low <= int(mtu) <= high else ""


# ── The plan: the two ends, from the model and intent ───────────────────────────────────────

def _intent_iface(hv: dict, short: str) -> dict:
    from modules.nsot.ifnames import same_interface
    return next((i for i in (hv or {}).get("interfaces") or []
                 if same_interface(i.get("name") or "", short)), {})


def _ospf_lines(iface: dict, family: str) -> dict:
    """Intent's OSPF settings on one interface, from its lines (`neighbours._lines`' view):
    ``{hello, dead, network, authentication, area, mtu_ignore}`` where intent states them."""
    out = {}
    # The field holds each line after its `ip ospf ` (`ipv6 ospf `, `ospfv3 `) prefix, as the
    # interface's lines render it (`features.raw_view`: `hello-interval 5`, `1 area 0`).
    prefixes = ("ip ospf ",) if family == "ipv4" else ("ipv6 ospf ", "ospfv3 ")
    for line in iface.get("ospf" if family == "ipv4" else "ospfv3") or []:
        words = line.strip()
        words = next((words[len(p):] for p in prefixes if words.startswith(p)), words)
        w = words.split()
        if not w:
            continue
        if w and w[0].isdigit():                       # `ip ospf 1 area 0`, `ospfv3 1 ipv6 area 0`
            if "area" in w:
                out["area"] = w[w.index("area") + 1] if w.index("area") + 1 < len(w) else ""
            continue
        if w[:1] == ["hello-interval"] and len(w) > 1:
            out["hello"] = w[1]
        elif w[:1] == ["dead-interval"] and len(w) > 1:
            out["dead"] = w[1]
        elif w[:1] == ["network"] and len(w) > 1:
            out["network"] = w[1]
        elif w[:1] == ["authentication"]:
            out["authentication"] = " ".join(w[1:2]) or "plain"
        elif w[:1] == ["mtu-ignore"]:
            out["mtu_ignore"] = True
    return out


def _passive(hv: dict, family: str, name: str) -> bool:
    from modules.neighbours import _passive as passive
    routing = (hv or {}).get("routing") or {}
    if family == "ipv4":
        return any(passive(p.get("settings"), name) for p in routing.get("ospf") or [])
    return any(passive(p.get("raw"), name) for p in routing.get("ospfv3") or [])


def _acls(iface: dict) -> dict:
    """The access lists intent binds on the interface: ``{"in": name, "out": name}``."""
    out = {}
    for line in iface.get("unmodeled") or []:
        w = line.strip().split()
        if w[:2] == ["ip", "access-group"] and len(w) == 4 and w[3] in ("in", "out"):
            out[w[3]] = w[2]
    return out


def _bgp(hv: dict) -> list:
    """Intent's BGP neighbours: ``[{address, remote_as, update_source}]``."""
    from modules.neighbours import bgp_peers
    bgp = ((hv or {}).get("routing") or {}).get("bgp") or {}
    sources = {}
    for line in bgp.get("neighbors") or []:
        m = re.match(r"^neighbor (\S+) update-source (\S+)$", line.strip())
        if m:
            sources[m.group(1).lower()] = m.group(2)
    out = []
    for addr, remote in bgp_peers(hv):
        key = str(addr)
        src = next((v for k, v in sources.items() if k in (key, key.upper(), key.lower())), "")
        out.append({"address": key, "remote_as": str(remote), "update_source": src,
                    "family": f"ipv{addr.version}"})
    return out


def _ends_on_link(model: dict, a: str, b: str, interface: str = "") -> tuple:
    """``(link, refusal)``: the one link *a* and *b* share (on *a*'s *interface* when named)."""
    from modules.nsot.ifnames import same_interface
    ids = model.get("names") or {}
    ia, ib = ids.get(a), ids.get(b)
    links = []
    for link in (model.get("links") or {}).values():
        ma = [m for m in link.get("members") or [] if m["dev"] == ia]
        mb = [m for m in link.get("members") or [] if m["dev"] == ib]
        if ma and mb and (not interface or same_interface(ma[0]["interface"], interface)):
            links.append(link)
    by_if = {}
    for link in links:
        port = next(m["interface"] for m in link["members"] if m["dev"] == ia)
        by_if.setdefault(port, []).append(link)
    if len(by_if) > 1:
        return None, (f"{a} and {b} share links on {', '.join(sorted(by_if))}: name "
                      f"{a}'s interface, so one link is diagnosed")
    if not by_if:
        where = f" on {interface}" if interface else ""
        return None, f"intent holds no link between {a}{where} and {b}"
    return list(by_if.values())[0], ""


def plan(network: str, runbook: str, target: dict, model: dict = None,
         intents: dict = None) -> dict:
    """The diagnosis a run would make, read from intent and the model alone (nothing asks a
    device): its two ends, every command on each device by round, the count and the worst
    case. Raises Refused naming why, with nothing read. *target* for "adjacency down":
    ``{"device", "neighbour", "interface"?}`` (an intended neighbour), or ``{"device", "peer"}``
    (a BGP neighbour intent names)."""
    if runbook not in RUNBOOKS:
        raise Refused(f"{runbook!r} is not a runbook ({', '.join(sorted(RUNBOOKS))})")
    if runbook not in BUILT:
        raise Refused(f"the runbook \"{RUNBOOKS[runbook]}\" is not built yet, so nothing was "
                      "read")
    if model is None or intents is None:
        model, intents = _sources(network, model, intents)
    from modules.neighbours import _all_lines
    lines = _all_lines(intents or {})
    target = dict(target or {})
    if runbook == "cant_reach":
        from modules.heal import diagnose_reach
        return diagnose_reach.plan(network, target, lines)
    if runbook == "stream_lost":
        from modules.heal import diagnose_stream
        return diagnose_stream.plan(network, target, lines)
    a = str(target.get("device") or "")
    if a not in lines:
        raise Refused(f"{a or 'no device'} has no committed intent in {network}, so there is "
                      "nothing to compare with")
    if target.get("peer"):
        return _plan_bgp(network, model, lines, a, str(target["peer"]))
    b = str(target.get("neighbour") or "")
    if b not in lines:
        raise Refused(f"{b or 'no neighbour'} is not a device with committed intent in "
                      f"{network}, so it cannot be {a}'s intended neighbour")
    return _plan_link(network, target, model, lines, a, b, str(target.get("interface") or ""))


def _plan_link(network: str, target: dict, model: dict, lines: dict, a: str, b: str,
               interface: str, peer: str = "") -> dict:
    """The plan for the link *a* and *b* share: each end's interface and addresses on it, its
    OSPF and OSPFv3 as intent holds them, and the BGP session over it (*peer*, or the first
    intent names on the far end's address)."""
    links, why = _ends_on_link(model, a, b, interface)
    if why:
        raise Refused(why)
    ids = model.get("names") or {}
    ends, notes = [], []
    for host, other in ((a, b), (b, a)):
        hv = lines[host]
        port = next(m["interface"] for l in links for m in l["members"] if m["dev"] == ids[host])
        iface = _intent_iface(hv, port)
        v4 = v6 = far4 = far6 = None
        for link in links:
            mine = next(m for m in link["members"] if m["dev"] == ids[host])
            theirs = next(m for m in link["members"] if m["dev"] == ids[other])
            ip = ipaddress.ip_interface(mine["address"])
            if ip.version == 4:
                v4, far4 = str(ip), str(ipaddress.ip_interface(theirs["address"]).ip)
            else:
                v6, far6 = str(ip), str(ipaddress.ip_interface(theirs["address"]).ip)
        node = (model.get("nodes") or {}).get(ids[host]) or {}
        mi = next((i for i in node.get("interfaces") or [] if i["name"] == port), {})
        peers = [p for p in _bgp(hv) if p["address"] in ({far4, far6} - {None})]
        if host == a and peer:
            peers = [p for p in peers if p["address"] == peer] or peers
        elif host == b and peer:
            fam = f"ipv{ipaddress.ip_address(peer).version}"
            peers = [p for p in peers if p["family"] == fam] or peers
        if len(peers) > 1:
            notes.append(f"{host}'s session to {peers[1]['address']} over this link is not read "
                         "(one BGP session per end)")
        name = iface.get("name") or port
        ends.append({
            "host": host, "neighbour": other, "dialect": dialect_of(hv.get("platform"), host),
            "interface": name, "short": port, "v4": v4, "v6": v6,
            "far4": far4, "far6": far6, "cabled": not _logical(name),
            "ospf": bool(mi.get("ospf_area")) and v4 is not None,
            "ospfv3": bool(mi.get("ospfv3_area")) and v6 is not None,
            "ospf_area": mi.get("ospf_area") or "", "ospfv3_area": mi.get("ospfv3_area") or "",
            "router_id": node.get("ospf", {}).get("router_id") or "",
            "intent": {"shutdown": bool(iface.get("shutdown")),
                       "mtu": str(iface.get("mtu") or ""),
                       "ospf": _ospf_lines(iface, "ipv4"), "ospfv3": _ospf_lines(iface, "ipv6"),
                       "passive4": _passive(hv, "ipv4", name),
                       "passive6": _passive(hv, "ipv6", name), "acls": _acls(iface)},
            "bgp": peers[0] if peers else None})
        if _logical(name):
            notes.append(f"CDP and LLDP run on physical ports, and {host} {port} is not one, so "
                         "they are not read there")
    if not any(e["ospf"] or e["ospfv3"] or e["bgp"] for e in ends):
        raise Refused(f"intent runs no OSPF, OSPFv3 or BGP between {a} {ends[0]['short']} and "
                      f"{b} {ends[1]['short']}, so no adjacency is expected there")
    return _finish(network, "adjacency_down", target, ends, outside="; ".join(notes))


#: Interfaces CDP and LLDP do not run on (they run on the physical ports beneath).
_LOGICAL = ("vlan", "loopback", "tunnel", "port-channel", "bdi", "nve")


def _logical(name: str) -> bool:
    return str(name or "").lower().startswith(_LOGICAL)


def _owners(lines: dict) -> dict:
    """``{ip_address: host}`` for every IPv4 and IPv6 interface address in intent."""
    from modules.neighbours import addresses
    owners = addresses(lines)
    for host, hv in lines.items():
        for i in hv.get("interfaces") or []:
            for addr in i.get("ipv6") or []:
                try:
                    owners.setdefault(ipaddress.ip_interface(addr).ip, host)
                except ValueError:
                    continue
    return owners


def _plan_bgp(network: str, model: dict, lines: dict, a: str, peer: str) -> dict:
    """A BGP neighbour intent names on *a*: over a link the two share, the link's plan with
    that session; else (between loopbacks, or outside management) each managed end's BGP
    reads alone."""
    try:
        peer = str(ipaddress.ip_address(peer))
    except ValueError:
        raise Refused(f"{peer!r} is not one IPv4 or IPv6 address") from None
    mine = next((p for p in _bgp(lines[a]) if p["address"] == peer), None)
    if mine is None:
        raise Refused(f"intent names no BGP neighbour {peer} on {a}")
    target = {"device": a, "peer": peer}
    owners = _owners(lines)
    b = owners.get(ipaddress.ip_address(peer), "")
    if b:
        ids = model.get("names") or {}
        link = next((l for l in (model.get("links") or {}).values()
                     if ipaddress.ip_address(peer) in ipaddress.ip_network(l["subnet"])
                     and {ids.get(a), ids.get(b)} <= {m["dev"] for m in l["members"]}), None)
        if link is not None:
            port = next(m["interface"] for m in link["members"] if m["dev"] == ids.get(a))
            return _plan_link(network, target, model, lines, a, b, port, peer=peer)
    ends = [_bgp_end(a, lines[a], mine, b)]
    if b:
        fam = mine["family"]
        back = [p for p in _bgp(lines[b]) if p["family"] == fam
                and owners.get(ipaddress.ip_address(p["address"])) == a]
        if back:
            ends.append(_bgp_end(b, lines[b], back[0], a))
    return _finish(network, "adjacency_down", target, ends,
                   outside=("" if b else f"{peer} is outside management, so only {a} is read"))


def _bgp_end(host: str, hv: dict, peer: dict, other: str) -> dict:
    return {"host": host, "neighbour": other, "dialect": dialect_of(hv.get("platform"), host),
            "interface": "", "short": "", "v4": None, "v6": None, "far4": None, "far6": None,
            "cabled": False, "ospf": False, "ospfv3": False, "ospf_area": "", "ospfv3_area": "",
            "router_id": "", "intent": {}, "bgp": peer}


def commands_for(end: dict) -> list:
    """``[{"kind", "command", "round"}]``: every read the runbook makes on *end*, in order."""
    out, d = [], end["dialect"]

    def add(kind, rnd, **args):
        out.append({"kind": kind, "command": render(kind, d, **args), "round": rnd})

    port = end["interface"]
    if port:
        add("interfaces", 1, **{"if": port})
        if end["v4"]:
            add("ip_interface", 1, **{"if": port})
        elif end["v6"]:
            add("ipv6_interface", 1, **{"if": port})
        if end["cabled"]:
            add("cdp", 1, **{"if": port})
            add("lldp", 1, **{"if": port})
        if end["ospf"]:
            add("ospf_interface", 1, **{"if": port})
            add("ospf_neighbor", 1, **{"if": port})
        if end["ospfv3"]:
            add("ospfv3_interface", 1, **{"if": port})
            add("ospfv3_neighbor", 1)
        add("interfaces", 2, **{"if": port})
        if end["far4"]:
            add("link_ping", 2, far=end["far4"], **{"if": port})
            mtu = _probe_size((end.get("intent") or {}).get("mtu") or "")
            if end["ospf"] and mtu:
                add("df_ping", 2, far=end["far4"], mtu=mtu)
        elif end["far6"]:
            add("link_ping6", 2, far=end["far6"], **{"if": port})
    peer = end.get("bgp")
    if peer:
        six = peer["family"] == "ipv6"
        add("bgp_summary6" if six else "bgp_summary", 2)
        add("bgp_neighbor6" if six else "bgp_neighbor", 2, peer=peer["address"])
        if peer["update_source"]:
            add("bgp_ping6_src" if six else "bgp_ping_src", 2, peer=peer["address"],
                src=peer["update_source"])
        else:
            add("bgp_ping6" if six else "bgp_ping", 2, peer=peer["address"])
    return out


def _bound(command: str) -> int:
    from modules.readonly_commands import bound_seconds
    return bound_seconds(command) or SHOW_BOUND_SECONDS


def _finish(network: str, runbook: str, target: dict, ends: list, outside: str = "") -> dict:
    reads = {e["host"]: commands_for(e) for e in ends}
    for host, cmds in reads.items():
        if len(cmds) > MAX_PER_DEVICE:
            raise Refused(f"{len(cmds)} reads on {host}, past the {MAX_PER_DEVICE} a device "
                          "may be asked in one diagnosis")
    count = sum(len(c) for c in reads.values())
    worst = sum(max((sum(_bound(c["command"]) for c in cmds if c["round"] == r)
                     for cmds in reads.values()), default=0) for r in ROUNDS)
    first = ends[0]
    words = (f"{first['host']} {first['short']} to {first['neighbour']}" if first["short"]
             else f"{first['host']} to BGP neighbour {target.get('peer')}")
    return {"network": network, "runbook": runbook, "runbook_words": RUNBOOKS[runbook],
            "target": target, "words": words, "ends": ends, "reads": reads, "count": count,
            "cap": MAX_COMMANDS, "outside": outside,
            "worst_s": worst + (int(DELTA_SECONDS) if any(
                c["round"] == 1 for cmds in reads.values() for c in cmds) else 0)}


def _sources(network: str, model=None, intents=None) -> tuple:
    from modules import network_model
    from modules.neighbours import committed_intents
    from modules.nsot import listref
    if model is None:
        model, why = network_model.model_for(network)
        if model is None:
            raise Refused(f"{network}'s network model could not be built: {why}")
    if intents is None:
        intents, why = committed_intents(listref.resolve(network).repo_dir)
        if why and not intents:
            raise Refused(f"{network}'s committed intent could not be read: {why}")
    return model, intents


# ── The run ─────────────────────────────────────────────────────────────────────────────────

def _reads_engine(network, host, commands, actor, purpose, session):
    """One device's round through THE reads engine, as kind ``diagnosis``."""
    from modules.nsot import reads
    try:
        rec = reads.run(network, [host], commands, actor, by=KIND, purpose=purpose,
                        session=session)
    except reads.Refused as exc:
        return {"run": "", "state": "refused", "why": str(exc), "answers": {}}
    r = (rec.get("results") or {}).get(host) or {}
    return {"run": rec["id"], "state": r.get("state") or "", "why": r.get("why") or "",
            "answers": {a["command"]: a for a in r.get("answers") or []}}


def _logs(network: str, host: str, now: float) -> dict:
    """*host*'s configuration lines in the window, from Loki (`device_logs.change_lines`):
    nothing reaches the device."""
    from modules import device_logs
    got = device_logs.change_lines({"hostname": host}, since=now - LOG_WINDOW_SECONDS, now=now)
    if not got.get("configured"):
        return {"state": "unread", "why": "Loki is not configured", "lines": []}
    if got.get("error"):
        return {"state": "unread", "why": got["error"], "lines": []}
    return {"state": "read", "why": "", "lines": [
        {"mnemonic": l.get("mnemonic") or "", "at": l.get("at_iso") or "",
         "text": (l.get("text") or "")[:200]} for l in got.get("lines") or []
        if "CONFIG" in (l.get("mnemonic") or "")]}


def run(network: str, runbook: str, target: dict, actor: str, *, incident: str = "",
        session=None, logs=None, sleep=time.sleep, model: dict = None, intents: dict = None,
        now: float = None, record: bool = True, collector=None) -> dict:
    """Run *runbook* on *target* and answer the diagnosis (recorded in the step log unless
    *record* is False). A refusal is a diagnosis too (``state`` ``refused`` or ``busy``,
    nothing read), never raised. *session* (tests) is the reads engine's seam; *logs* is
    ``logs(network, host, now) -> {state, why, lines}``; *sleep* waits between the rounds;
    *collector* (tests) replaces the lost-stream runbook's local read of the collector's
    sockets (`diagnose_stream.read_collector`)."""
    started = time.time() if now is None else float(now)
    did = new_id()
    out = {"id": did, "network": network, "runbook": runbook,
           "runbook_words": RUNBOOKS.get(runbook, runbook), "target": dict(target or {}),
           "incident": incident, "actor": actor, "started_at": _iso(started),
           "finished_at": "", "state": "done", "words": "", "steps": [], "hypotheses": [],
           "more": 0, "ruled_out": [], "not_checked": [], "commands": 0,
           "cap": MAX_COMMANDS, "runs": [], "stopped": "", "devices": []}
    try:
        p = plan(network, runbook, target, model=model, intents=intents)
    except Refused as exc:
        out.update(state="refused", words=f"not diagnosed: {exc}", finished_at=_iso(time.time()))
        out["steps"].append({"step": "plan", "result": "refused", "words": str(exc)})
        return _recorded(network, out, record)
    if runbook == "cant_reach":
        from modules.heal import diagnose_reach
        out["runbook_words"] = p["runbook_words"]           # by its two ends (C2829)
        diagnose_reach.run_plan(p, out, actor, session=session, logs=logs or _logs,
                                sleep=sleep, started=started)
        out["finished_at"] = _iso(time.time())
        return _recorded(network, out, record)
    if runbook == "stream_lost":
        from modules.heal import diagnose_stream
        diagnose_stream.run_plan(p, out, actor, session=session, logs=logs or _logs,
                                 collector=collector, started=started)
        out["finished_at"] = _iso(time.time())
        return _recorded(network, out, record)
    out["devices"] = [e["host"] for e in p["ends"]]
    out["steps"].append({"step": "plan", "result": "ok", "words": (
        f"\"{p['runbook_words']}\" on {p['words']}: {p['count']} reads on "
        f"{len(p['ends'])} device(s), at most {p['cap']}" + (f"; {p['outside']}" if p["outside"]
                                                             else ""))})
    try:
        with DiagnosisLock(network, out["devices"], did, actor):
            out["steps"].append({"step": "hold", "result": "ok", "words": (
                "held for this diagnosis: " + ", ".join(out["devices"]))})
            got = _read_all(network, p, actor, did, session, sleep, out)
            log_reader = logs or _logs
            from modules import fanout
            got_logs = fanout.read_each(lambda h: log_reader(network, h, started),
                                        out["devices"], name="diagnosis-logs")
    except DiagnosisBusy as exc:
        out.update(state="busy", words=str(exc), finished_at=_iso(time.time()))
        out["steps"].append({"step": "hold", "result": "refused", "words": str(exc)})
        return _recorded(network, out, record)
    logs_by = {}
    for host, g in zip(out["devices"], got_logs):
        logs_by[host] = (g if isinstance(g, dict) else
                         {"state": "unread", "why": str(g), "lines": []})
        out["steps"].append({"step": "logs", "device": host,
                             "result": "ok" if logs_by[host]["state"] == "read" else "not_read",
                             "words": (f"{len(logs_by[host]['lines'])} configuration line(s) "
                                       "logged in the last hour"
                                       if logs_by[host]["state"] == "read"
                                       else f"the log was not read: {logs_by[host]['why']}")})
    ctx = Context(p, got, logs_by)
    _judge(ctx, out)
    out["finished_at"] = _iso(time.time())
    return _recorded(network, out, record)


def _read_all(network, p, actor, did, session, sleep, out) -> dict:
    """Both rounds on every end, concurrently per round; the cap counted before each read."""
    from modules import fanout
    got = {e["host"]: {} for e in p["ends"]}
    for rnd in ROUNDS:
        batch = {h: [c for c in cmds if c["round"] == rnd] for h, cmds in p["reads"].items()}
        if rnd == 2 and any(c["round"] == 1 for cmds in p["reads"].values() for c in cmds):
            sleep(DELTA_SECONDS)
        want = sum(len(c) for c in batch.values())
        if out["commands"] + want > MAX_COMMANDS:
            out["stopped"] = (f"stopped at the {MAX_COMMANDS}-command cap before round {rnd}; "
                              "its reads were not made")
            out["steps"].append({"step": "read", "result": "stopped", "words": out["stopped"]})
            break
        hosts = [h for h, c in batch.items() if c]

        def one(host, rnd=rnd, batch=batch):
            return _reads_engine(network, host, [c["command"] for c in batch[host]], actor,
                                 f"diagnosis {did}, round {rnd}", session)

        answers = fanout.read_each(one, hosts, name="diagnosis")
        out["commands"] += want
        for host, ans in zip(hosts, answers):
            if isinstance(ans, fanout.Failed):
                ans = {"run": "", "state": "failed", "why": str(ans), "answers": {}}
            if ans.get("run"):
                out["runs"].append(ans["run"])
            got[host][rnd] = ans
            out["steps"].append(_read_step(host, rnd, batch[host], ans))
    return got


def _read_step(host: str, rnd: int, cmds: list, ans: dict) -> dict:
    from modules.nsot import reads
    step = "read" if rnd == 1 else "read again"
    if ans["state"] == reads.SKIPPED:
        return {"step": step, "device": host, "result": "not_read",
                "words": f"not read: {ans['why']}"}
    if ans["state"] in ("refused", "failed", reads.UNKNOWN) or not ans["answers"]:
        return {"step": step, "device": host, "result": "failed",
                "words": f"not read: {ans.get('why') or ans['state']}"}
    refs = [ref(ans["run"], host, c["command"]) for c in cmds]
    return {"step": step, "device": host, "result": "ok", "reads": refs,
            "words": f"{len(cmds)} read(s): " + "; ".join(
                READ_WORDS.get(c["kind"], c["kind"]) for c in cmds)}


def ref(run_id: str, host: str, command: str) -> str:
    """A read's reference: History › Reads holds its masked answer. Joined, not an f-string of
    colons, which is a template-secret key's shape (tests/test_hostvars_secrets.py)."""
    return ":".join(("read", run_id, host, command))


# ── What was read, as facts ─────────────────────────────────────────────────────────────────

class Context:
    """The plan, each end's parsed reads by round, and its logs: what the rules compare."""

    def __init__(self, p: dict, got: dict, logs: dict):
        from modules.heal import diagnose_parse as P
        self.plan, self.logs = p, logs
        self.ends = p["ends"]
        # Keyed by the PARSE kind: an IPv6 form, or a ping with a source, is its kind's twin.
        self.parsed, self.refs, self.why, self.command = {}, {}, {}, {}
        for e in self.ends:
            h = e["host"]
            for c in p["reads"][h]:
                kind = PARSE_KIND.get(c["kind"], c["kind"])
                key = (h, kind, c["round"])
                self.command[key] = c["command"]
                ans = (got.get(h) or {}).get(c["round"]) or {}
                a = (ans.get("answers") or {}).get(c["command"])
                if a is None or a.get("state") != "answered":
                    self.why[key] = ((a or {}).get("why") or ans.get("why")
                                     or "it was not read")
                    continue
                self.refs[key] = ref(ans["run"], h, c["command"])
                got_p = P.parse(kind, a.get("answer") or "", e["interface"])
                if got_p["state"] == P.PARSED:
                    self.parsed[key] = got_p["facts"]
                else:
                    self.why[key] = got_p["why"]

    def end(self, i: int) -> dict:
        return self.ends[i] if i < len(self.ends) else None

    def facts(self, e: dict, kind: str, rnd: int = 1):
        return None if e is None else self.parsed.get((e["host"], kind, rnd))

    def ref_of(self, e: dict, kind: str, rnd: int = 1) -> str:
        return "" if e is None else self.refs.get((e["host"], kind, rnd)) or ""

    def missing(self, e: dict, kind: str, rnd: int = 1) -> str:
        """Why *e*'s *kind* read has no facts, in words naming the read."""
        if e is None:
            return f"{READ_WORDS.get(kind, kind)}: the far end is not read"
        key = (e["host"], kind, rnd)
        if key not in self.command:
            return f"{e['host']}: no read of {READ_WORDS.get(kind, kind)} is in this runbook"
        return f"`{self.command[key]}` on {e['host']}: {self.why.get(key) or 'read'}"

    def name(self, e: dict) -> str:
        return f"{e['host']} {e['short']}".strip()


def finding(rule, claim: str, evidence: list, *, rule_out: str = "", todo: str = "",
            incomplete=(), strength: str = "", agree: int = 1, case: str = "",
            at: dict = None) -> dict:
    """One hypothesis. *case* names which of a rule's findings it is, where `ACTIONS` tells
    them apart (``far_end_up``); *at* is the end it names (``{"host", "interface"}``), what an
    action would act on. Both are kept only when given."""
    out = {"rule": rule.name, "layer": rule.layer, "strength": strength or rule.strength,
           "claim": claim, "evidence": [e for e in evidence if e], "rule_out": rule_out,
           "todo": todo, "incomplete": [w for w in incomplete if w], "agree": agree}
    if case:
        out["case"] = case
    if at:
        out["at"] = dict(at)
    return out


def ev(reference: str, line: str = "", intent: str = "") -> dict:
    """One piece of evidence: the read it came from, the masked fact that fired, and the intent
    value it was compared with."""
    if not reference and not intent:
        return {}
    return {"read": reference, "line": line, "intent": intent}


# ── The rules (`RULES`): each answers its findings, a check passed, or nothing checked ──────

class Rule:
    def __init__(self, name, layer, strength, words, fn):
        assert layer in LAYERS and strength in STRENGTHS
        self.name, self.layer, self.strength, self.words, self.fn = (name, layer, strength,
                                                                     words, fn)

    def said(self, ctx) -> str:
        """The rule's words as this diagnosis draws them (a runbook's rule may name its ends,
        `diagnose_reach.PathRule.said`, C2878)."""
        return self.words


def _r_admin_down(rule, ctx):
    hits, seen = [], 0
    for e in ctx.ends:
        f = ctx.facts(e, "interfaces")
        if f is None:
            continue
        seen += 1
        if f["state"] == "admin_down":
            shut = (e.get("intent") or {}).get("shutdown")
            hits.append(finding(rule, f"{ctx.name(e)} is administratively down" + (
                ", as intent holds it shut" if shut else
                ", though intent holds it up: it was shut outside intent"),
                [ev(ctx.ref_of(e, "interfaces"), f"{f['name']} is administratively down",
                    "shutdown" if shut else "no shutdown")],
                rule_out=f"`show interfaces {e['interface']}` reading up",
                todo=("Intent shuts it: change intent to bring it up" if shut else
                      "Check drift now…: it departs from intent")))
    return hits, ("neither end is administratively down"
                  if seen == len(ctx.ends) and seen and not hits else "")


def _r_down_admin_up(rule, ctx):
    hits, up = [], 0
    for i, e in enumerate(ctx.ends):
        f = ctx.facts(e, "interfaces")
        if f is None:
            continue
        up += f["state"] == "up"
        if f["state"] != "down":
            continue
        far = ctx.end(1 - i)
        ff = ctx.facts(far, "interfaces")
        line = f"{f['name']} is down, line protocol is {f['protocol']}" + (
            f" ({f['reason']})" if f["reason"] else "")
        evid = [ev(ctx.ref_of(e, "interfaces"), line, "no shutdown")]
        if ff is not None and ff["state"] == "up":
            for kind in ("cdp", "lldp"):
                evid.append(ev(ctx.ref_of(far, kind), f"{far['host']}'s {kind.upper()} read"))
            hits.append(finding(rule, f"{ctx.name(e)} is down while administratively up, and "
                                f"{ctx.name(far)} is up: the fault is at {ctx.name(e)}'s port, "
                                "its cable or optic", evid + [
                                    ev(ctx.ref_of(far, "interfaces"),
                                       f"{ff['name']} is up, line protocol is {ff['protocol']}")],
                                rule_out=f"{ctx.name(e)} reading up", agree=2,
                                case="far_end_up",
                                at={"host": e["host"], "interface": e["interface"],
                                    "far_host": far["host"], "far_interface": far["interface"]},
                                todo="Check the cable and the port at "
                                     f"{ctx.name(e)}" + (f" ({f['reason']})" if f["reason"]
                                                         else "")))
        elif ff is not None:
            hits.append(finding(rule, f"{ctx.name(e)} and {ctx.name(far)} are both down while "
                                "administratively up: the link between them", evid + [
                                    ev(ctx.ref_of(far, "interfaces"), f"{ff['name']} is "
                                       f"{ff['state'].replace('_', ' ')}")],
                                strength="strong", agree=2,
                                rule_out="either end reading up",
                                todo="Check the cable, or the segment between the two ends"))
        else:
            hits.append(finding(rule, f"{ctx.name(e)} is down while administratively up", evid,
                                incomplete=[ctx.missing(far, "interfaces")],
                                rule_out=f"{ctx.name(e)} reading up",
                                todo=f"Check the cable and the port at {ctx.name(e)}"))
    return hits, ("each end is up" if up == len(ctx.ends) and up and not hits else "")


def _r_protocol_down(rule, ctx):
    hits, seen = [], 0
    for e in ctx.ends:
        f = ctx.facts(e, "interfaces")
        if f is None:
            continue
        seen += 1
        if f["state"] == "up" and f["protocol"] == "down":
            hits.append(finding(rule, f"{ctx.name(e)} is up and its line protocol is down: "
                                "the link layer does not come up (keepalives, encapsulation or "
                                "the far end's port)",
                                [ev(ctx.ref_of(e, "interfaces"),
                                    f"{f['name']} is up, line protocol is down")],
                                rule_out="the line protocol reading up"))
    return hits, ("both ends' line protocol is up" if seen == len(ctx.ends) and seen and not hits
                  else "")


def _r_cabled_elsewhere(rule, ctx):
    from modules.nsot.ifnames import same_interface
    hits, matched, empty = [], 0, 0
    for i, e in enumerate(ctx.ends):
        far = ctx.end(1 - i)
        if far is None or not e["short"]:
            continue
        rows = {k: ctx.facts(e, k) for k in ("cdp", "lldp")}
        named = {k: r for k, r in rows.items() if r}
        if not named:
            empty += 1
            continue
        wrong = []
        for kind, r in named.items():
            for row in r:
                # The far end's port is compared only where it is a physical port (an SVI's
                # neighbour is cabled to one of the switch's ports, which intent's link names
                # not).
                if row["host"].lower() != far["host"].lower() or (
                        far.get("cabled") and not same_interface(row["port"], far["short"])):
                    wrong.append((kind, row))
        if wrong and len(wrong) == sum(len(r) for r in named.values()):
            kind, row = wrong[0]
            hits.append(finding(rule, f"{kind.upper()} on {ctx.name(e)} names {row['host']} "
                                f"{row['port']}; intent cables it to {ctx.name(far)}",
                                [ev(ctx.ref_of(e, k), f"{k.upper()}: {w['host']} {w['port']}",
                                    f"{far['host']} {far['short']}") for k, w in wrong],
                                agree=len(wrong), rule_out=f"CDP or LLDP naming {ctx.name(far)}",
                                todo="Recable to intent, or change intent's link"))
        else:
            matched += 1
    passed = ("CDP or LLDP names the intended neighbour at each end"
              if matched == len(ctx.ends) and matched else "")
    return hits, passed


def _r_errors_rising(rule, ctx):
    hits, seen = [], 0
    for e in ctx.ends:
        a, b = ctx.facts(e, "interfaces", 1), ctx.facts(e, "interfaces", 2)
        if a is None or b is None or a.get("input_errors") is None:
            continue
        seen += 1
        di = (b["input_errors"] or 0) - (a["input_errors"] or 0)
        dc = (b["crc"] or 0) - (a["crc"] or 0)
        if di > 0 or dc > 0:
            hits.append(finding(rule, f"{ctx.name(e)}'s input errors rose by {di} and its CRC "
                                f"count by {dc} in {int(DELTA_SECONDS)} s: a physical fault on "
                                "the link (cable, optic, duplex)",
                                [ev(ctx.ref_of(e, "interfaces", 1),
                                    f"{a['input_errors']} input errors, {a['crc']} CRC"),
                                 ev(ctx.ref_of(e, "interfaces", 2),
                                    f"{b['input_errors']} input errors, {b['crc']} CRC")],
                                agree=2, rule_out="the two reads' counters equal",
                                todo=f"Check the cable and optic at {ctx.name(e)}"))
    return hits, (f"no error counter rose in {int(DELTA_SECONDS)} s at either end"
                  if seen == len(ctx.ends) and seen and not hits else "")


def _mtu_of(ctx, e):
    ip = ctx.facts(e, "ip_interface")
    if ip and ip.get("ip_mtu"):
        return ip["ip_mtu"], ctx.ref_of(e, "ip_interface"), "IP MTU"
    f = ctx.facts(e, "interfaces")
    if f and f.get("mtu"):
        return f["mtu"], ctx.ref_of(e, "interfaces"), "MTU"
    return None, "", ""


def _neighbour_rows(ctx, e, far, kind):
    """*e*'s rows for its neighbour *far*: by *far*'s address on the link (OSPF prints it), or
    by *far*'s router id as intent holds it."""
    rows = ctx.facts(e, kind) or []
    rid = far.get("router_id") or ""
    return [r for r in rows if (kind == "ospf_neighbor" and far.get("v4")
                                and r.get("address") == str(ipaddress.ip_interface(
                                    far["v4"]).ip)) or (rid and r["router_id"] == rid)]


def _r_mtu(rule, ctx):
    if len(ctx.ends) < 2 or not ctx.ends[0]["short"]:
        return [], ""
    (ma, ra, wa), (mb, rb, wb) = _mtu_of(ctx, ctx.ends[0]), _mtu_of(ctx, ctx.ends[1])
    if ma is None or mb is None:
        return [], ""
    a, b = ctx.ends
    if ma == mb:
        return [], f"the MTU is {ma} at both ends"
    stuck = []
    for e, far in ((a, b), (b, a)):
        for r in _neighbour_rows(ctx, e, far, "ospf_neighbor"):
            if r["state"] in _STUCK:
                stuck.append(ev(ctx.ref_of(e, "ospf_neighbor"),
                                f"neighbour {r['router_id']} in {r['state']}"))
    mtu_a = (a.get("intent") or {}).get("mtu") or "silent (no measured default)"
    mtu_b = (b.get("intent") or {}).get("mtu") or "silent (no measured default)"
    return [finding(rule, f"the MTU differs: {ctx.name(a)} {ma} against {ctx.name(b)} {mb}" + (
        ", and OSPF is stuck exchanging databases" if stuck else ""),
        [ev(ra, f"{wa} {ma}", f"mtu {mtu_a}"), ev(rb, f"{wb} {mb}", f"mtu {mtu_b}")] + stuck,
        strength="decisive" if stuck else "strong", agree=2 + len(stuck),
        rule_out="the two ends printing one MTU",
        todo="Set one MTU at both ends, in intent")], ""


def _r_subnet(rule, ctx):
    hits, ok = [], 0
    for e in ctx.ends:
        f = ctx.facts(e, "ip_interface")
        if f is None or not e["v4"]:
            continue
        if f.get("address") and f["address"] != e["v4"]:
            hits.append(finding(rule, f"{ctx.name(e)} holds {f['address']}; intent holds "
                                f"{e['v4']}", [ev(ctx.ref_of(e, "ip_interface"),
                                                  f"Internet address is {f['address']}",
                                                  e["v4"])],
                                rule_out="the address reading as intent holds it",
                                todo="Check drift now…: it departs from intent"))
        elif f.get("address"):
            ok += 1
    if len(ctx.ends) == 2:
        fa, fb = (ctx.facts(e, "ip_interface") for e in ctx.ends)
        if fa and fb and fa.get("address") and fb.get("address"):
            na = ipaddress.ip_interface(fa["address"]).network
            nb = ipaddress.ip_interface(fb["address"]).network
            if na != nb:
                hits.append(finding(rule, f"the ends are on different subnets: "
                                    f"{ctx.name(ctx.ends[0])} {na} against "
                                    f"{ctx.name(ctx.ends[1])} {nb}",
                                    [ev(ctx.ref_of(e, "ip_interface"),
                                        f"Internet address is {f['address']}", e["v4"] or "")
                                     for e, f in zip(ctx.ends, (fa, fb))], agree=2,
                                    rule_out="both ends on one subnet",
                                    todo="Address both ends on one subnet, in intent"))
    return hits, (f"both ends' IPv4 addresses are as intent holds, on "
                  f"{ipaddress.ip_interface(ctx.ends[0]['v4']).network}"
                  if ok == len(ctx.ends) == 2 and not hits else "")


_OSPF_FIELDS = (("area", "area", "decisive"), ("hello", "hello interval", "decisive"),
                ("dead", "dead interval", "decisive"), ("authentication", "authentication",
                                                        "decisive"),
                ("network", "network type", "strong"))


def _r_ospf_intent(rule, ctx):
    if len(ctx.ends) < 2:
        return [], ""
    a, b = ctx.ends
    hits, compared = [], []
    for fam, key, area_key, read in (("OSPF", "ospf", "ospf_area", "ospf_interface"),
                                     ("OSPFv3", "ospfv3", "ospfv3_area", "ospfv3_interface")):
        if not (a[key] and b[key]):
            continue
        ia = dict((a.get("intent") or {}).get(key) or {}, area=a[area_key])
        ib = dict((b.get("intent") or {}).get(key) or {}, area=b[area_key])
        for field, words, strength in _OSPF_FIELDS:
            va, vb = ia.get(field) or "", ib.get(field) or ""
            if va == vb:
                if va:
                    compared.append(f"{fam} {words} {va}")
                continue
            sa = va or "silent: the platform's default (not measured)"
            sb = vb or "silent: the platform's default (not measured)"
            both = bool(va and vb)
            hits.append(finding(rule, f"intent disagrees with itself on {fam}'s {words}: "
                                f"{ctx.name(a)} {sa}, {ctx.name(b)} {sb}",
                                [ev("", "", f"{a['host']}: {sa}"),
                                 ev("", "", f"{b['host']}: {sb}")],
                                strength=strength if both else "strong", agree=2,
                                incomplete=[] if both else [ctx.missing(a, read),
                                                            ctx.missing(b, read)],
                                rule_out=f"`{TEMPLATES[read]['*'].format(**{'if': a['interface']})}`"
                                         f" on both ends showing one {words}",
                                todo=f"Set one {fam} {words} at both ends, in intent"))
    passed = ("intent agrees with itself at both ends on " + ", ".join(compared)
              if compared and not hits else "")
    return hits, passed


def _r_passive(rule, ctx):
    if len(ctx.ends) < 2:
        return [], ""
    hits, checked = [], False
    for fam, key, pkey in (("OSPF", "ospf", "passive4"), ("OSPFv3", "ospfv3", "passive6")):
        ends = [e for e in ctx.ends if e[key]]
        if len(ends) < 2:
            continue
        checked = True
        passive = [e for e in ends if (e.get("intent") or {}).get(pkey)]
        if passive:
            names = " and ".join(ctx.name(e) for e in passive)
            hits.append(finding(rule, f"{fam} is passive on {names} in intent: it sends no "
                                "hellos there, so no adjacency forms",
                                [ev("", "", f"{e['host']}: passive-interface {e['interface']}")
                                 for e in passive], agree=len(passive),
                                rule_out="`show ip ospf interface` saying it sends hellos",
                                todo="Remove passive from the interface in intent, or the "
                                     "expected adjacency from intent"))
    return hits, ("neither end is passive in intent" if checked and not hits else "")


def _r_one_way(rule, ctx):
    if len(ctx.ends) < 2:
        return [], ""
    hits, up = [], 0
    for fam, kind, key in (("OSPF", "ospf_neighbor", "ospf"),
                           ("OSPFv3", "ospfv3_neighbor", "ospfv3")):
        a, b = ctx.ends
        if not (a[key] and b[key]):
            continue
        va, vb = ctx.facts(a, kind), ctx.facts(b, kind)
        if va is None or vb is None:
            continue
        ra, rb = _neighbour_rows(ctx, a, b, kind), _neighbour_rows(ctx, b, a, kind)
        if (any(r["state"] in _UP for r in ra) and any(r["state"] in _UP for r in rb)):
            up += 1
            continue
        for e, far, mine, theirs in ((a, b, ra, rb), (b, a, rb, ra)):
            if any(r["state"] == "INIT" for r in mine) and not theirs:
                hits.append(finding(rule, f"{fam} is one-way: {e['host']} hears {far['host']} "
                                    f"(INIT) and {far['host']} lists no neighbour {e['host']}: "
                                    f"{far['host']} does not receive {e['host']}'s hellos "
                                    "(a filter, a one-way link or a mismatched parameter)",
                                    [ev(ctx.ref_of(e, kind),
                                        f"neighbour {far['router_id'] or far['v4']} INIT"),
                                     ev(ctx.ref_of(far, kind),
                                        f"no neighbour {e['router_id'] or e['v4']}")],
                                    agree=2, rule_out="both ends listing each other",
                                    todo=f"Read {far['host']}'s OSPF interface and any access "
                                         "list bound on the link"))
    return hits, ("the adjacency is up now at both ends" if up and not hits else "")


def _r_ospf_one_neighbour(rule, ctx):
    """19.4's OSPF reset (H20): an end whose interface is up/up and holds exactly one OSPF
    neighbour, that neighbour the far end by intent, stuck short of FULL and past DOWN (its
    hellos arrive: the neighbour is reachable on the link). The bounce on that interface resets
    that one adjacency and no other. Two or more neighbours on the interface is Alert, never
    this rule. A decisive configuration cause ranks above it, so no action follows."""
    if len(ctx.ends) < 2:
        return [], ""
    hits, full = [], 0
    for i, e in enumerate(ctx.ends):
        far = ctx.end(1 - i)
        if not e.get("ospf"):
            continue
        rows, port = ctx.facts(e, "ospf_neighbor"), ctx.facts(e, "interfaces")
        if rows is None or port is None:
            continue
        if any(r["state"] in _UP for r in rows):
            full += 1
            continue
        mine = _neighbour_rows(ctx, e, far, "ospf_neighbor")
        if len(rows) != 1 or len(mine) != 1 or port["state"] != "up" \
                or port.get("protocol") != "up":
            continue
        st = rows[0]["state"] or "?"
        # DOWN hears nothing (not reachable on the link); INIT is one-way, `_r_one_way`'s.
        if st.upper() in ("DOWN", "INIT", "?"):
            continue
        hits.append(finding(rule, (f"{ctx.name(e)} holds exactly one OSPF neighbour, "
                                   f"{far['host']}, stuck in {st} with the link up: its hellos "
                                   "arrive, and no configuration cause was found"),
                            [ev(ctx.ref_of(e, "ospf_neighbor"),
                                f"one neighbour on {e['short']}: {rows[0]['router_id']} {st}"),
                             ev(ctx.ref_of(e, "interfaces"),
                                f"{port['name']} is up, line protocol is up")],
                            rule_out="the neighbour reading FULL", agree=2,
                            at={"host": e["host"], "interface": e["interface"],
                                "far_host": far["host"], "far_interface": far["interface"]},
                            todo=f"Reset the one adjacency on {ctx.name(e)} (a bounce of its "
                                 "interface), or read the far end's OSPF state"))
    return hits, ("the adjacency is FULL" if full and not hits else "")


def _summary_row(ctx, e):
    peer = e.get("bgp")
    s = ctx.facts(e, "bgp_summary", 2)
    if not peer or s is None:
        return peer, None, False
    row = next((r for r in s.get("peers") or [] if r["address"] == peer["address"]), None)
    return peer, row, True


def _r_bgp_admin(rule, ctx):
    hits, seen = [], 0
    for e in ctx.ends:
        peer, row, read = _summary_row(ctx, e)
        if not read:
            continue
        seen += 1
        if row and "admin" in row["state"].lower():
            hits.append(finding(rule, f"{e['host']}'s BGP neighbour {peer['address']} is "
                                f"{row['state']}: shut by configuration, so a clear would not "
                                "bring it up", [ev(ctx.ref_of(e, "bgp_summary", 2),
                                                   f"{peer['address']} {row['state']}",
                                                   "no shutdown on the neighbour")],
                                rule_out="the neighbour's state not Idle (Admin)",
                                todo="Check drift now…; nothing is cleared"))
    return hits, ""


def _r_bgp_remote_as(rule, ctx):
    hits = []
    for e in ctx.ends:
        peer, row, read = _summary_row(ctx, e)
        if not read:
            continue
        if row is None:
            hits.append(finding(rule, f"intent names BGP neighbour {peer['address']} on "
                                f"{e['host']}, and its BGP summary lists no such neighbour",
                                [ev(ctx.ref_of(e, "bgp_summary", 2), "no such neighbour",
                                    f"neighbor {peer['address']} remote-as {peer['remote_as']}")],
                                rule_out="the summary listing the neighbour",
                                todo="Check drift now…: it departs from intent"))
        elif row["remote_as"] != peer["remote_as"]:
            hits.append(finding(rule, f"{e['host']}'s BGP neighbour {peer['address']} is "
                                f"configured in AS {row['remote_as']}; intent holds AS "
                                f"{peer['remote_as']}: the OPEN is refused (Bad Peer AS)",
                                [ev(ctx.ref_of(e, "bgp_summary", 2),
                                    f"{peer['address']} AS {row['remote_as']}",
                                    f"remote-as {peer['remote_as']}")],
                                rule_out="the summary's AS reading as intent holds it",
                                todo="Check drift now…: it departs from intent"))
    return hits, ""


def _r_bgp_not_established(rule, ctx):
    hits, up = [], 0
    for e in ctx.ends:
        peer, row, read = _summary_row(ctx, e)
        if not read or row is None:
            continue
        if row["established"]:
            up += 1
            continue
        if "admin" in row["state"].lower() or row["remote_as"] != peer["remote_as"]:
            continue
        hits.append(finding(rule, f"{e['host']}'s BGP session to {peer['address']} is "
                            f"{row['state']}, with no configuration cause in what Mercury reads",
                            [ev(ctx.ref_of(e, "bgp_summary", 2),
                                f"{peer['address']} {row['state']}",
                                f"remote-as {peer['remote_as']}")],
                            incomplete=[ctx.missing(e, "bgp_ping", 2),
                                        ctx.missing(e, "bgp_neighbor", 2)],
                            at={"host": e["host"], "peer": peer["address"]},
                            rule_out="a ping from the update source failing (then the peer "
                                     "is unreachable, a network cause)",
                            todo="Read the session's last reset reason on History › Reads"))
    return hits, ("the BGP session is Established" if up and not hits else "")


def _r_acl(rule, ctx):
    hits, seen = [], 0
    for e in ctx.ends:
        f = ctx.facts(e, "ip_interface")
        if f is None:
            continue
        seen += 1
        intent = (e.get("intent") or {}).get("acls") or {}
        for way, key in (("in", "acl_in"), ("out", "acl_out")):
            if (f.get(key) or "") != (intent.get(way) or ""):
                hits.append(finding(rule, f"{ctx.name(e)} has access list "
                                    f"{f.get(key) or 'none'} bound {way}; intent binds "
                                    f"{intent.get(way) or 'none'}",
                                    [ev(ctx.ref_of(e, "ip_interface"),
                                        f"{'Inbound' if way == 'in' else 'Outgoing'} access list "
                                        f"is {f.get(key) or 'not set'}",
                                        f"ip access-group {intent.get(way) or '(none)'} {way}")],
                                    rule_out="the bindings reading as intent holds them",
                                    todo="A person's change: an access list is never healed "
                                         "(Never)"))
    return hits, ("no access list is bound that intent does not hold"
                  if seen == len(ctx.ends) and seen and not hits else "")


def _r_config_changed(rule, ctx):
    hits, read = [], 0
    for e in ctx.ends:
        got = ctx.logs.get(e["host"]) or {}
        if got.get("state") != "read":
            continue
        read += 1
        if got["lines"]:
            last = got["lines"][0]
            hits.append(finding(rule, f"{e['host']}'s configuration was changed in the last "
                                f"hour ({len(got['lines'])} line(s) logged, the last at "
                                f"{last['at']})", [ev(f"log:{e['host']}:{last['at']}",
                                                      f"%{last['mnemonic']}")],
                                rule_out="no configuration line logged",
                                todo="Find who changed it on History"))
    return hits, ("no configuration change was logged on either end in the last hour"
                  if read == len(ctx.ends) and read and not hits else "")


RULES = (
    Rule("admin_down", "physical", "decisive", "an end administratively down", _r_admin_down),
    Rule("down_admin_up", "physical", "decisive",
         "an interface down while administratively up, the far end up", _r_down_admin_up),
    Rule("cabled_elsewhere", "physical", "decisive",
         "CDP or LLDP names a neighbour intent does not cable there", _r_cabled_elsewhere),
    Rule("errors_rising", "physical", "strong",
         "input errors or CRC rising across the two reads", _r_errors_rising),
    Rule("protocol_down", "link", "strong", "up, line protocol down", _r_protocol_down),
    Rule("mtu", "link", "decisive", "the MTU differs between the ends", _r_mtu),
    Rule("subnet", "network", "decisive", "an address not intent's, or the ends on different "
         "subnets", _r_subnet),
    Rule("ospf_intent", "protocol", "decisive",
         "OSPF area, timers, authentication or network type differ in intent", _r_ospf_intent),
    Rule("passive", "protocol", "decisive", "passive on an end", _r_passive),
    Rule("one_way", "protocol", "strong", "one end hears the other, the other nothing",
         _r_one_way),
    Rule("ospf_not_full_one_neighbour", "protocol", "strong",
         "the interface's one OSPF neighbour stuck short of FULL, the link up",
         _r_ospf_one_neighbour),
    Rule("bgp_admin", "protocol", "decisive", "a BGP peer in Idle (Admin)", _r_bgp_admin),
    Rule("bgp_remote_as", "protocol", "decisive",
         "a BGP peer missing, or its remote AS not intent's", _r_bgp_remote_as),
    Rule("bgp_not_established", "protocol", "strong",
         "a BGP session not Established, no configuration cause", _r_bgp_not_established),
    Rule("acl", "policy", "decisive", "an access list bound that intent does not hold", _r_acl),
    Rule("config_changed", "policy", "circumstantial",
         "a configuration change on an end in the last hour", _r_config_changed),
)


def rank(hypotheses: list) -> list:
    """*hypotheses* in 19.3's order: strength, complete before incomplete, layer bottom-up,
    then the most agreeing reads."""
    order = {r.name: i for i, r in enumerate(RULES)}
    return sorted(hypotheses, key=lambda h: (STRENGTHS.index(h["strength"]),
                                             1 if h["incomplete"] else 0,
                                             LAYERS.index(h["layer"]), -h["agree"],
                                             order.get(h["rule"], 99)))


#: The fixed table from a diagnosis rule to the action it may choose (19.4, "When an action is
#: chosen"; H19). Chosen only from the deterministic diagnosis, never from AI text: an action
#: is chosen only when the diagnosis's FIRST hypothesis is complete and is the action's own
#: rule (and its case, where the rule has several findings). Anything above it, a decisive MTU
#: mismatch, a cabling mismatch or an access list, means no action: the action could not fix
#: it. Each entry: the rule, its case ("" for any), the action kind (`heal.actions.KINDS`) and
#: its variant. The dampening proposal is not chosen here: it is guard 13d's second need.
ACTIONS = (
    {"rule": "down_admin_up", "case": "far_end_up", "kind": "port_bounce", "variant": ""},
    {"rule": "bgp_not_established", "case": "", "kind": "session_clear", "variant": "hard"},
    {"rule": "bgp_fewer_routes", "case": "", "kind": "session_clear", "variant": "soft"},
    {"rule": "ospf_not_full_one_neighbour", "case": "", "kind": "ospf_reset", "variant": ""},
)
#: The rules `ACTIONS` names that no runbook has yet, each with the part that builds it: the
#: soft clear's "Established, fewer routes than intent expects": its operation is built and
#: measured (H21, `privileged.SESSION_CLEARS`), but intent holds no count of the routes a
#: neighbour is expected to send, so no rule can compare one yet. The OSPF reset's "exactly one
#: neighbour on the interface, not FULL" is H20's (`_r_ospf_one_neighbour`).
ACTION_RULES_NOT_BUILT = {"bgp_fewer_routes": "intent's expected routes per neighbour (none)"}


def action_for(diagnosis: dict) -> dict:
    """The action *diagnosis* chooses by `ACTIONS`: ``{"state", "kind", "variant", "rule",
    "at", "hypothesis", "words"}``, *state* ``chosen`` or ``none`` (then *kind* is "" and
    *words* say why, naming the first hypothesis). Never a guess: no hypothesis, a first one
    whose evidence is incomplete, or a first one that is no action's rule, chooses none."""
    hyps = (diagnosis or {}).get("hypotheses") or []
    none = {"state": "none", "kind": "", "variant": "", "rule": "", "at": {}, "hypothesis": ""}
    if not hyps:
        return dict(none, words="no action: the diagnosis found no cause, and an action is "
                                "never a guess")
    first = hyps[0]
    said = f"the first hypothesis ({first.get('rule')}, {first.get('strength')})"
    if first.get("incomplete"):
        return dict(none, rule=first.get("rule") or "", hypothesis=first.get("id") or "",
                    words=(f"no action: {said} lacks evidence "
                           f"({(first.get('incomplete') or [''])[0]}), and an action is chosen "
                           "only on a complete one"))
    row = next((a for a in ACTIONS if a["rule"] == first.get("rule")
                and a["case"] in ("", first.get("case") or "")), None)
    if row is None:
        return dict(none, rule=first.get("rule") or "", hypothesis=first.get("id") or "",
                    words=f"no action: {said} is no action's rule, so an action could not fix it")
    return {"state": "chosen", "kind": row["kind"], "variant": row["variant"],
            "rule": row["rule"], "at": dict(first.get("at") or {}),
            "hypothesis": first.get("id") or "",
            "words": f"{said} is the {row['kind'].replace('_', ' ')}'s rule: {first['claim']}"}


def _judge(ctx, out: dict, rules=None) -> None:
    """Every rule of the runbook's table (*rules*, `RULES` by default) on *ctx*, ranked into
    *out*: the hypotheses, the ruled-out list and what was not checked."""
    rules = RULES if rules is None else rules
    found, ruled_out = [], []
    not_checked = list(out.get("not_checked") or [])
    for rule in rules:
        try:
            hits, passed = rule.fn(rule, ctx)
        except Exception as exc:                      # noqa: BLE001 (a rule's own failure)
            log.exception("diagnosis %s: rule %s failed", out["id"], rule.name)
            not_checked.append({"check": rule.said(ctx),
                                "why": f"the rule failed ({type(exc).__name__})"})
            continue
        found += hits
        if passed:
            ruled_out.append({"check": passed, "rule": rule.name})
        elif not hits:
            not_checked.append({"check": rule.said(ctx), "rule": rule.name,
                                "why": "what it compares was not read, or does not apply"})
    ranked = rank(found)
    for n, h in enumerate(ranked, 1):
        h["id"] = f"diag:{n}"
    out["hypotheses"], out["more"] = ranked[:MAX_SHOWN], max(0, len(ranked) - MAX_SHOWN)
    out["ruled_out"], out["not_checked"] = ruled_out, not_checked
    out["steps"].append({"step": "compare", "result": "ok", "words": (
        f"{len(rules)} checks: {len(found)} found something, {len(ruled_out)} ruled out, "
        f"{len(not_checked)} not checked")})
    if ranked:
        first = ranked[0]
        out["words"] = (f"{len(ranked)} hypothes{'i' if len(ranked) == 1 else 'e'}s, the first "
                        f"{first['strength']}" + (" (evidence incomplete)" if first["incomplete"]
                                                  else "") + f": {first['claim']}")
    else:
        out["words"] = "no cause found in what Mercury reads"
    out["steps"].append({"step": "rank", "result": "ok", "words": out["words"]})


def _recorded(network: str, out: dict, record: bool) -> dict:
    if not record:
        return out
    from modules.heal import steplog
    step = {"step": "record", "result": "ok", "words": f"diagnosis {out['id']} recorded"}
    out["steps"].append(step)
    try:
        steplog.record_diagnosis(network, out)
    except Exception as exc:                          # noqa: BLE001 (said, never raised)
        log.exception("diagnosis %s could not be recorded", out["id"])
        step.update(result="failed", words=f"not recorded: {type(exc).__name__}: {exc}")
        out["recorded"] = False
    else:
        out["recorded"] = True
    return out
