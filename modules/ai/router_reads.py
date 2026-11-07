"""The AI read set for routers and switches (`AI_READS`; board H, part H24; docs/HEAL_TO_INTENT.md
19.5, the operator's N20 and N21; OWASP LLM06:2025, Excessive Agency).

An allow-list the tool enforces, narrower than a person's Show commands: the model asks for a
read by operation and arguments (`read_loop`'s ``{op, args, why, hypothesis}``), and code
decides whether it runs. `AI_READS` is one `read_loop.ReadFamily` over the ``cli`` transport,
so every operation is held to the transport's read rule when it is declared (the whole command
passing `readonly_commands.refusal` with no extras, its verb show, ping or traceroute), and
every rendered request is held to it again before it runs.

**A request runs only when both checks pass:**
- `readonly_commands.refusal(command)`, with no extras;
- it is exactly one of `AI_READS`' command shapes (`SHAPES`), each argument one token of its
  shape, compared with what Mercury holds now (`scope_for`):
  - **the device** is one the incident (or the pack as sent) names, in the incident's network,
    and it has a read-only account; a device without one is refused by name ("no read-only
    account for edge1"), never read with the deploy account;
  - **an interface** is in the platform's interface-name shape and the device's committed
    golden holds it (`interface <name>`, compared in its long form);
  - **an address** is one IPv4 or IPv6 address (`ipaddress`, no zone, no prefix) of the
    operation's family, and of the network: an address its committed intent holds, or one
    inside a subnet intent's interfaces carry;
  - **a BGP peer** is an address the device's committed intent names as a neighbour;
  - **a MAC** is in IOS's dotted form.

**The whole command is matched** (`match`, N21): verb, words and arguments, against one shape,
token by token; a word the shape does not name is refused, naming it. Output modifiers are
`readonly_commands.SAFE_MODIFIERS`' five, in full (one list for a person's reads and the
model's, C2423); `| redirect`, `| tee`, `| append` and every other modifier are refused, as
are newlines, control characters, ``?`` and any URL (`readonly_commands.refusal`). The loop's
own requests carry no modifier: an operation renders its fixed command, and the answer is cut at
`read_loop.AI_READ_CAP`. `match` is the same check for a command that arrives as text (the
diagnosis runbooks' pipe-rule test, and the planted table of 19.5); it judges the command it
parsed through `read_loop.check`, one path.

**The fixed numbers:** a ping is ``repeat 5 timeout 2``, a traceroute ``numeric timeout 2
probe 1 ttl 1 16`` (19.5: repeat at most 5, timeout at most 2, probe 1, ttl at most 16). They
are part of each shape, never the model's to choose.

**`show running-config` is the configuration class's** (N20), never the device state class's:
its forms are declared with ``egress_class="configuration"``, so they are refused, naming the
class, wherever that class is off (every network, until `egress_classes.configuration_allowed`
and C1720's marking are built).

**Left out on purpose** (`LEFT_OUT`), each refused with its reason: a secret's position, other
forms of configuration, files, and the device's log.

**The device state class** (N20, H28's `egress_classes.device_state_allowed`): off by default
on every network, on per network by an admin with a reason; while it is off,
`read_loop.class_state` refuses every device state read, naming the class and why.
**The read-only account** (H28, C2420): the scope asks the reads engine's own resolver
(`reads.read_account_for`, the credential chain's read role, `credentials.resolve_read`) for
each device the incident names, so a device without one is refused by name at the check ("no
read-only account for edge1: ..."), never read with the deploy account. The executor (`run`)
has no session of its own: it hands the allowed requests to the reads engine as kind
``ai_analysis`` (`reads.READ_ACCOUNT_KINDS`), which resolves the account again at the read,
refuses a device without one by name before any session opens, signs in as it through
`connection.with_plain_connection` (never `enable()`) and records whom it signed in as.
"""

import ipaddress
import logging
import re

from modules.ai import read_loop as RL

log = logging.getLogger(__name__)

#: The reads engine's caller kind for the AI's reads (`modules/nsot/reads.py` EXTRAS: none).
KIND = "ai_analysis"
#: An interface name, in the platform's interface-name shape (as `modules/heal/diagnose.py`
#: renders one): letters, then a number and its slot, port and subinterface parts.
IFNAME = r"[A-Za-z][A-Za-z-]{0,30}[0-9][0-9/.:]{0,15}"
DEVICE = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}"


class Family(RL.Shape):
    """One address of one IP family (4 or 6), by `ipaddress`: no zone, no prefix."""

    def __init__(self, version: int):
        self.version = int(version)
        self.words = f"one IPv{self.version} address"
        self._any = RL.Address(self.words)

    def parse(self, value):
        text = self._any.parse(value)
        if ipaddress.ip_address(text).version != self.version:
            raise RL.ShapeError(f"{RL._shown(value)} is not {self.words}")
        return text


IFACE = RL.Text(IFNAME, "an interface name in the platform's interface-name shape", most=48)
V4, V6 = Family(4), Family(6)
MAC = RL.Mac(dotted=True)


# ── The comparisons with what Mercury holds (`scope_for`) ─────────────────────────────────────

def _listed(items, most: int = 6) -> str:
    items = [str(i) for i in items]
    if not items:
        return "none"
    shown = items[:most] + ([f"{len(items) - most} more"] if len(items) > most else [])
    return shown[0] if len(shown) == 1 else ", ".join(shown[:-1]) + " and " + shown[-1]


def _device_named(value, scope) -> str:
    devices = (scope or {}).get("devices") or {}
    network = (scope or {}).get("network") or "the network"
    if value not in devices:
        return (f"{value} is not a device the incident names in {network} (it names "
                f"{_listed(sorted(devices))})")
    if not devices[value].get("read_account"):
        why = devices[value].get("read_account_why") or ""
        return f"no read-only account for {value}" + (f": {why}" if why else "")
    return ""


def _held_interface(args, scope) -> str:
    from modules.nsot.ifnames import canonical

    host, name = args["device"], args["interface"]
    held = (((scope or {}).get("devices") or {}).get(host) or {}).get("interfaces") or ()
    if canonical(name).lower() not in {canonical(h).lower() for h in held}:
        return (f"{name} is not an interface {host}'s golden holds (it holds "
                f"{_listed(held)})")
    return ""


def _of_network(value: str, scope) -> str:
    scope = scope or {}
    network = scope.get("network") or "the network"
    address = ipaddress.ip_address(value)
    if value in set(scope.get("addresses") or ()):
        return ""
    for prefix in scope.get("prefixes") or ():
        net = ipaddress.ip_network(prefix, strict=False)
        if net.version == address.version and address in net:
            return ""
    return (f"{value} is not an address of {network}: neither one its intent holds nor one "
            f"inside a subnet its interfaces carry")


def _address_of_network(args, scope) -> str:
    return _of_network(args["address"], scope)


def _peer_named(args, scope) -> str:
    host, peer = args["device"], args["peer"]
    named = (((scope or {}).get("devices") or {}).get(host) or {}).get("peers") or ()
    if peer not in set(named):
        return (f"{peer} is not a BGP peer {host}'s intent names (it names "
                f"{_listed(named)})")
    return ""


def _dialect(want: str):
    def check(args, scope) -> str:
        host = args["device"]
        got = (((scope or {}).get("devices") or {}).get(host) or {}).get("dialect") or ""
        if got != want:
            return (f"{host}'s platform is {got or 'not known'}, and this form is "
                    f"{want}'s")
        return ""
    return check


def _all(*checks):
    def check(args, scope) -> str:
        for one in checks:
            why = one(args, scope)
            if why:
                return why
        return ""
    return check


# ── The shapes ────────────────────────────────────────────────────────────────────────────────

_IF = (("interface", IFACE),)
_ADDR4, _ADDR6 = (("address", V4),), (("address", V6),)
_PING = "repeat 5 timeout 2"
_TRACE = "numeric timeout 2 probe 1 ttl 1 16"

#: (operation, the command it sends, its arguments in order, its comparison, its class or None
#: for the family's, what it reads). 19.5's set: the diagnosis's state reads (19.3's table).
SHAPES = (
    ("interfaces", "show interfaces {interface}", _IF, None, None,
     "interface state, MTU and error counters"),
    ("ip_interface", "show ip interface {interface}", _IF, None, None,
     "IPv4 address, IP MTU and access lists bound"),
    ("ipv6_interface", "show ipv6 interface {interface}", _IF, None, None,
     "IPv6 addresses and access lists bound"),
    ("cdp", "show cdp neighbors {interface} detail", _IF, None, None,
     "who CDP says is cabled there"),
    ("lldp", "show lldp neighbors {interface} detail", _IF, None, None,
     "who LLDP says is cabled there"),
    ("ospf_interface", "show ip ospf interface {interface}", _IF, None, None,
     "OSPF on the interface"),
    ("ospf_neighbor", "show ip ospf neighbor {interface} detail", _IF, None, None,
     "OSPF's neighbours there"),
    ("ospfv3_interface", "show ipv6 ospf interface {interface}", _IF, None, None,
     "OSPFv3 on the interface"),
    ("ospfv3_neighbor", "show ospfv3 neighbor", (), _dialect("cisco_iosxe"), None,
     "OSPFv3's neighbours (IOS-XE)"),
    ("ipv6_ospf_neighbor", "show ipv6 ospf neighbor", (), _dialect("cisco_ios"), None,
     "OSPFv3's neighbours (IOS)"),
    ("bgp_summary", "show ip bgp summary", (), None, None, "the BGP sessions' state"),
    ("bgp_summary6", "show bgp ipv6 unicast summary", (), None, None,
     "the BGP sessions' state (IPv6)"),
    ("bgp_neighbor", "show ip bgp neighbors {peer}", (("peer", V4),), _peer_named, None,
     "a BGP session's last reset, hold time and update source"),
    ("bgp_neighbor6", "show bgp ipv6 unicast neighbors {peer}", (("peer", V6),), _peer_named,
     None, "a BGP session's last reset (IPv6)"),
    ("route", "show ip route {address}", _ADDR4, _address_of_network, None,
     "the route toward an address and its source"),
    ("route6", "show ipv6 route {address}", _ADDR6, _address_of_network, None,
     "the route toward an address and its source (IPv6)"),
    ("cef", "show ip cef {address}", _ADDR4, _address_of_network, None,
     "the forwarding path toward an address"),
    ("cef6", "show ipv6 cef {address}", _ADDR6, _address_of_network, None,
     "the forwarding path toward an address (IPv6)"),
    ("arp", "show ip arp {address}", _ADDR4, _address_of_network, None,
     "a neighbour resolved (ARP)"),
    ("nd", "show ipv6 neighbors {address}", _ADDR6, _address_of_network, None,
     "a neighbour resolved (IPv6 neighbour discovery)"),
    ("mac", "show mac address-table address {mac}", (("mac", MAC),), None, None,
     "where a MAC address is learned"),
    ("stp", "show spanning-tree interface {interface}", _IF, None, None,
     "spanning tree on the interface"),
    ("ping", "ping {address} " + _PING, _ADDR4, _address_of_network, None,
     "an address reachable"),
    ("ping_from", "ping {address} source {interface} " + _PING, _ADDR4 + _IF,
     _address_of_network, None, "an address reachable from an interface"),
    ("ping6", "ping ipv6 {address} " + _PING, _ADDR6, _address_of_network, None,
     "an address reachable (IPv6)"),
    ("ping6_from", "ping ipv6 {address} source {interface} " + _PING, _ADDR6 + _IF,
     _address_of_network, None, "an address reachable from an interface (IPv6)"),
    ("traceroute", "traceroute {address} " + _TRACE, _ADDR4, _address_of_network, None,
     "the path toward an address"),
    ("traceroute6", "traceroute ipv6 {address} " + _TRACE, _ADDR6, _address_of_network, None,
     "the path toward an address (IPv6)"),
    ("running_config", "show running-config", (), None, "configuration",
     "the running configuration (the configuration class's)"),
    ("running_config_interface", "show running-config interface {interface}", _IF, None,
     "configuration", "one interface's running configuration (the configuration class's)"),
)

#: The commands left out on purpose, each refused with its reason (19.5), by its whole words.
LEFT_OUT = (
    (("show", "key", "chain"), "it prints a secret's position"),
    (("show", "snmp"), "it prints a secret's position"),
    (("show", "users"), "it prints a secret's position"),
    (("show", "startup-config"), "it prints configuration in another form"),
    (("show", "archive"), "it prints configuration in another form"),
    (("show", "access-lists"), "an access list's entries are configuration"),
    (("show", "ip", "access-lists"), "an access list's entries are configuration"),
    (("show", "ipv6", "access-list"), "an access list's entries are configuration"),
    (("show", "tech-support"), "it prints configuration in another form"),
    (("more",), "a file may be configuration"),
    (("dir",), "a file may be configuration"),
    (("show", "logging"), "the logs reach the model only from Loki, masked, in the pack"),
)


def _operation(name, send, args, against, cls, words) -> RL.Operation:
    spec = {"device": RL.Arg(RL.Text(DEVICE, "a device name"), against=_device_named)}
    for arg, shape in args:
        spec[arg] = RL.Arg(shape)
    checks = ([_held_interface] if "interface" in spec else []) + ([against] if against else [])
    return RL.Operation(name, args=spec, sends=(send,), egress_class=cls,
                        against=_all(*checks) if checks else None, words=words)


def read_accounts(network: str, hosts) -> dict:
    """``{host: (has one, why not)}``: whether each of *hosts* of *network* has a read-only
    account, by the reads engine's own resolver on the device's inventory entry
    (`reads.read_account_for`, H28, C2420), so the check and the read ask one question. A
    device the inventory does not hold, or an inventory or chain that cannot be read, is no
    account, said. Only whether it resolved leaves here, never the account."""
    from modules.device import load_saved_devices
    from modules.nsot import listref, reads

    hosts = list(hosts or ())
    try:
        inventory = {d.get("hostname"): d
                     for d in load_saved_devices(listref.resolve(network).csv_path)}
    except Exception as exc:                            # noqa: BLE001 (closed, and said)
        log.warning("router reads: %s's inventory could not be read: %s", network, exc)
        return {h: (False, f"{network}'s inventory could not be read "
                           f"({type(exc).__name__})") for h in hosts}
    out = {}
    for host in hosts:
        dev = inventory.get(host)
        if dev is None:
            out[host] = (False, f"{host} is not a device of {network}")
            continue
        try:
            got = reads.read_account_for(dev)
        except Exception as exc:                        # noqa: BLE001 (closed, and said)
            log.warning("router reads: %s's read-only account could not be resolved: %s",
                        host, exc)
            got = {"ok": False, "error": f"it could not be resolved ({type(exc).__name__})"}
        out[host] = (bool(got.get("ok")), "" if got.get("ok") else got.get("error") or "")
    return out


def _answer_of(record: dict, host: str) -> str:
    got = (record.get("results") or {}).get(host) or {}
    if got.get("state") == "skipped":
        raise RuntimeError(f"skipped: {got.get('why') or host + ' is held'}")
    answers = got.get("answers") or []
    if not answers:
        raise RuntimeError(got.get("why") or f"{host} gave no answer")
    out = []
    for a in answers:
        if a.get("state") != "answered":
            raise RuntimeError(f"`{a.get('command')}`: {a.get('why') or 'not answered'}")
        out.append(a.get("answer") or "")
    return "\n".join(out)


def run(op: str, args: dict, requests: list, scope: dict) -> RL.Answered:
    """The family's executor: *requests* (exactly what the check allowed) through THE reads
    engine as kind ``ai_analysis``, the device held while it is read (a held device skipped by
    name, never queued), masked and recorded on History › Reads. The engine signs in as the
    device's read-only account (H28: `reads.READ_ACCOUNT_KINDS`) and refuses a device without
    one by name before any session opens; that refusal is raised here in its words. No session
    is opened here: one way in, the engine's. Answered with the run's id and whom it signed in
    as (`read_loop.Answered`), so the send log names the read on History › Reads (H26)."""
    from modules.nsot import reads

    host = args["device"]
    record = reads.run(scope["network"], [host], list(requests),
                       scope.get("actor") or "the AI analysis", by=KIND,
                       purpose=scope.get("purpose") or f"the AI's read: {op}")
    signed = ((record.get("results") or {}).get(host) or {}).get("signed_in_as") or {}
    return RL.Answered(_answer_of(record, host), run=record.get("id") or "",
                       signed_in_as=dict(signed))


#: The router read family: answers go out under the device state class (N20), the
#: configuration forms under the configuration class.
AI_READS = RL.ReadFamily(name="router_cli", transport="cli", egress_class="device_state",
                         operations=tuple(_operation(*s) for s in SHAPES), run=run,
                         words="the AI read set for routers and switches")


# ── The scope: what the comparisons read ──────────────────────────────────────────────────────

_IFACE_LINE = re.compile(r"^interface (\S+)\s*$", re.M)


def golden_interfaces(text: str) -> list:
    """The interfaces a golden holds: each ``interface <name>`` line, as written."""
    return list(dict.fromkeys(_IFACE_LINE.findall(text or "")))


def scope_for(network: str, hosts, *, incident: str = "", turned_on_by: str = "",
              intents: dict = None, goldens: dict = None, dialects: dict = None) -> dict:
    """What `AI_READS`' comparisons read for an incident's *hosts* in *network*: each device's
    golden interfaces, intent's BGP peers, its dialect and whether it has a read-only account
    (`read_accounts`, the reads engine's resolver, always: never given); the network's
    addresses and subnets from committed intent. *intents* (``{host: host vars}``), *goldens*
    (``{host: text}``) and *dialects* are read from the committed stores when not given. The
    reads are recorded as "the AI analysis of incident <id>, turned on by <admin>"."""
    from modules.neighbours import _v4, addresses, bgp_peers

    hosts = [h for h in dict.fromkeys(hosts or ()) if h]
    if intents is None or goldens is None:
        got_i, got_g = _committed(network, hosts)
        intents = got_i if intents is None else intents
        goldens = got_g if goldens is None else goldens
    if dialects is None:
        dialects = {h: _dialect_of((intents.get(h) or {}).get("platform"), h) for h in hosts}
    accounts = read_accounts(network, hosts)
    prefixes = set()
    for hv in intents.values():
        for iface in (hv or {}).get("interfaces") or []:
            v4 = _v4(iface.get("ipv4") or "")
            if v4 is not None:
                prefixes.add(str(v4.network))
            for text in iface.get("ipv6") or []:
                try:
                    prefixes.add(str(ipaddress.ip_interface(text).network))
                except ValueError:
                    continue
    devices = {}
    for host in hosts:
        devices[host] = {
            "interfaces": golden_interfaces((goldens or {}).get(host) or ""),
            "peers": [str(a) for a, _ in bgp_peers((intents or {}).get(host) or {})],
            "dialect": (dialects or {}).get(host) or "",
            "read_account": accounts[host][0], "read_account_why": accounts[host][1]}
    actor = (f"the AI analysis of incident {incident}, turned on by "
             f"{turned_on_by or 'nobody named'}") if incident else "the AI analysis"
    return {"network": network, "devices": devices,
            "addresses": sorted(str(a) for a in addresses(intents or {})),
            "prefixes": sorted(prefixes), "actor": actor}


def _dialect_of(platform, host: str) -> str:
    """The device's dialect from intent's platform (`diagnose.dialect_of`), "" when unknown:
    a dialect-specific shape is then refused, naming "not known", never read as IOS (C452)."""
    from modules.heal.diagnose import Refused, dialect_of

    try:
        return dialect_of(platform, host)
    except Refused:
        return ""


def _committed(network: str, hosts: list) -> tuple:
    """``(intents, goldens)`` for *hosts*, from the network's committed stores (C104)."""
    from modules.neighbours import committed_intents
    from modules.nsot import listref, manifest
    from modules.nsot.repo import committed_golden_for

    repo = listref.resolve(network).repo_dir
    intents, why = committed_intents(repo)
    if why:
        log.warning("router reads: %s's committed intent: %s", network, why)
    goldens = {}
    for host in hosts:
        _ident, entry = manifest.find_by_name(repo, host)
        goldens[host] = (committed_golden_for(repo, entry).get("text") or "") if entry else ""
    return intents or {}, goldens


# ── The whole command, matched ────────────────────────────────────────────────────────────────

def _template_words(send: str) -> list:
    return send.split()


def _placeholder(word: str) -> str:
    return word[1:-1] if word.startswith("{") and word.endswith("}") else ""


def match(command: str, device: str, scope: dict, *, network: str = "") -> dict:
    """*command* for *device*, matched whole against `AI_READS`: ``{"verdict": "allowed" |
    "refused", "op", "args", "command", "reason"}``. ``command`` is what would be sent: the
    operation's rendered command, and its one output modifier when it carried one. The
    refusal names the word, the argument or the class it compared."""
    from modules import readonly_commands

    network = network or (scope or {}).get("network") or ""

    def refused(reason, op=""):
        return {"verdict": "refused", "op": op, "args": {}, "command": "", "reason": reason}

    if not isinstance(command, str):
        return refused("a command is text")
    why = readonly_commands.refusal(command)
    if why:
        return refused(why)
    head, bar, tail = command.strip().partition("|")
    modifier = ""
    if bar:
        parts = tail.split()
        if not parts or parts[0] not in readonly_commands.SAFE_MODIFIERS:
            return refused(f"{(parts or [''])[0]!r} is not one of the output modifiers, in "
                           f"full: {', '.join(readonly_commands.SAFE_MODIFIERS)}")
        if len(parts) < 2:
            return refused(f"| {parts[0]} needs what it filters by")
        modifier = " ".join(parts)
    words = head.split()
    for left, reason in LEFT_OUT:
        if [w.lower() for w in words[:len(left)]] == list(left):
            return refused(f"`{' '.join(left)}` is left out of the AI read set on purpose: "
                           f"{reason}")
    best = (-1, f"`{head.strip()}` is not one of the AI read set's commands")
    for op in AI_READS.operations:
        template = _template_words(op.sends[0])
        # A shape is recognised by its words up to its first argument; past that, a word out
        # of place or a command cut short is that shape's refusal, said.
        args, n, why, named = {"device": device}, 0, "", False
        for i, want in enumerate(template):
            name = _placeholder(want)
            if i >= len(words):
                if name or named:
                    why = (f"`{' '.join(words)}` stops before `{' '.join(template[i:])}`, "
                           f"the rest of the shape `{op.sends[0]}`")
                break
            if name:
                named = True
                try:
                    args[name] = op.args[name].shape.parse(words[i])
                except RL.ShapeError as exc:
                    why = f"{op.name}'s argument {name}: {exc}"
                    break
            elif words[i] != want:
                if named:
                    why = (f"{words[i]!r} is a word the shape `{op.sends[0]}` does not name "
                           f"there (it names {want!r})")
                break
            n = i + 1
        else:
            if len(words) > len(template):
                why = (f"{words[len(template)]!r} is a word the shape `{op.sends[0]}` does not "
                       "name")
            else:
                verdict = RL.check(AI_READS, [{"op": op.name, "args": args, "why": "matched",
                                               "hypothesis": "matched"}],
                                   network=network, scope=scope)[0]
                if verdict["verdict"] != "allowed":
                    return refused(verdict["reason"], op.name)
                sent = verdict["requests"][0] + (f" | {modifier}" if modifier else "")
                return {"verdict": "allowed", "op": op.name, "args": verdict["args"],
                        "command": sent, "reason": ""}
        if why and n > best[0]:
            best = (n, why)
    return refused(best[1])
