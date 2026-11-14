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
    golden holds it (`interface <name>`, compared in its long form); CDP's and LLDP's is
    never a loopback (`_cabled_interface`: nothing is cabled to one, and the device refuses
    the form, measured 2026-11-13);
  - **a switch's read** (spanning tree) is refused, as another platform's form, on a device
    declared or measured to have no VLAN database (`_switch_form`, `vlan_capability`), as a
    dialect's own form is on the other dialect (`other_platform` names either);
  - **an address** is one IPv4 or IPv6 address (`ipaddress`, no zone, no prefix) of the
    operation's family, and of the network: an address its committed intent holds, or one
    inside a subnet intent's interfaces carry;
  - **a BGP peer** is an address the device's committed intent names as a neighbour;
  - **a MAC** is in IOS's dotted form;
  - **a telemetry subscription** is 1 to 10 digits, one the device's committed intent
    declares, and one the incident names when the scope carries the incident's own
    (AI troubleshooting's, `modules/ai/fixit_reads.py`).

**The whole command is matched** (`match`, N21): verb, words and arguments, against one shape,
token by token; a word the shape does not name is refused, naming it. Output modifiers are
`readonly_commands.SAFE_MODIFIERS`' five, in full (one list for a person's reads and the
model's, C2423); `| redirect`, `| tee`, `| append` and every other modifier are refused, as
are newlines, control characters, ``?`` and any URL (`readonly_commands.refusal`). The loop's
own requests carry no modifier: an operation renders its fixed command, and the answer is cut at
`read_loop.AI_READ_CAP`. `match` is the same check for a command that arrives as text (the
diagnosis runbooks' pipe-rule test, and the planted table of 19.5); it judges the command it
parsed through `read_loop.check`, one path.

**The fixed numbers:** a ping is 5 echoes with a 2 second timeout, a traceroute ``numeric
timeout 2 probe 1 ttl 1 16`` (19.5: repeat at most 5, timeout at most 2, probe 1, ttl at most
16). They are part of each shape, never the model's to choose.

**Ping and traceroute as the read-only account** (the operator, 2026-11-13). The options of
ping and traceroute are privileged on IOS and IOS-XE (Cisco, "Using the Extended ping and
Extended traceroute Commands", Document ID 13730; measured: an IOS-XE router refused the
read-only account at ``repeat``, ``source`` and ``numeric``), and a ``privilege exec`` line
that opens them to the account's level takes ping or traceroute away from every account
below it. So:
- ``ping`` and ``ping6`` send the plain form, ``ping <address>``: 5 echoes and a 2 second
  timeout are the device's defaults (the same document), so the plain form is the same
  measurement, and it answers at privilege 1;
- ``ping_from``, ``ping6_from``, ``traceroute`` and ``traceroute6`` carry options that are
  not defaults (``source``; ``numeric timeout 2 probe 1 ttl 1 16``), so they are asked only
  under the installation choice "Let the read-only account ping and traceroute"
  (`PING_CHOICE`, the setting `PING_CHOICE_KEY`, off by default; then the account's level
  holds the two ``privilege exec all`` lines, `privilege_exec.read_account_lines`). With the
  choice off each is refused by name, naming the choice, never silently (`choice_off`).

**`show running-config` is the configuration class's** (N20), never the device state class's:
its forms are declared with ``egress_class="configuration"``, so they are refused, naming the
class, wherever that class is off (every network, until `egress_classes.configuration_allowed`
and C1720's marking are built).

**Left out on purpose** (`LEFT_OUT`), each refused with its reason: a secret's position, other
forms of configuration, files, and the device's log.

**The device state class** (N20, H28's `egress_classes.device_state_allowed`): off by default
on every network, on per network by an admin with a reason; while it is off,
`read_loop.class_state` refuses every device state read, naming the class and why.
**Whom the reads sign in as** (C3661, the operator's change of approach of 2026-11-14): the
installation choice "AI device reads sign in as" (`reads.ai_reads_as`, read by the scope as
``reads_as`` when it is built, and by the engine again at the read; each reads the setting
through that one function, and both fail closed, to the read-only account). Mercury's account
by default: the
reads engine signs the read in exactly as Show commands does, and the device check asks no
read-only account. Under the read-only choice, what follows holds.
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
#: A telemetry subscription id, as the stream runbook takes one (`diagnose_stream.SUBSCRIPTION`).
SUBSCRIPTION = RL.Text(r"[0-9]{1,10}", "a telemetry subscription id, 1 to 10 digits", most=10)


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
    # Whom the reads sign in as (C3661): the account is asked of a device only under the
    # read-only choice; a scope built without the answer is read as that choice (the closed
    # side, `reads_as_of`).
    if reads_as_of(scope) == "read_only" and not devices[value].get("read_account"):
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


def _subscription_named(args, scope) -> str:
    """A telemetry subscription the device's committed intent declares, and, when the scope
    names the incident's own (``subscriptions``: AI troubleshooting's), one of those."""
    host, sub = args["device"], args["subscription"]
    declared = (((scope or {}).get("devices") or {}).get(host) or {}).get("subscriptions") or ()
    if sub not in set(declared):
        return (f"subscription {sub} is not one {host}'s intent declares (it declares "
                f"{_listed(declared)})")
    named = (scope or {}).get("subscriptions")
    if named is not None and sub not in set(named):
        return (f"subscription {sub} is not one the incident names (it names "
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

    def other(args, scope) -> str:
        host = args["device"]
        got = (((scope or {}).get("devices") or {}).get(host) or {}).get("dialect") or ""
        return check(args, scope) if got else ""

    check.other_platform = other
    return check


def _switch_form(args, scope) -> str:
    """Spanning tree is a switch's read, asked only of a switch (the operator, 2026-11-14:
    "spanning-tree only on switches. Fix both, so they agree"; C3582). A switch is a device
    with a VLAN database, DECLARED or MEASURED (`modules/nsot/vlan_capability.py`, never a name
    or a role); anywhere else the form is another platform's. That includes a device whose
    answer is unknown: on the host every router's was unknown (2026-11-14: the Default list's
    inventory names no device type, and no router was measured), so asking the unknown asked
    every router, and a router refused `show spanning-tree interface Loopback0`. Its words say how
    Mercury comes to know (the capability's own words)."""
    host = args["device"]
    dev = ((scope or {}).get("devices") or {}).get(host) or {}
    has = dev.get("vlan_database")
    if has is True:
        return ""
    if has is False:
        return (f"{host} has no VLAN database ({dev.get('vlan_database_words') or 'declared'})"
                ", and this form is a switch's")
    return (f"{host} is not known to have a VLAN database "
            f"({dev.get('vlan_database_words') or 'not declared and not measured'}), and this "
            "form is a switch's, asked only of a device known to be one")


_switch_form.other_platform = _switch_form


def _cabled_interface(args, scope) -> str:
    """CDP and LLDP name who is cabled to an interface, and nothing is cabled to a loopback:
    an IOS-XE router refuses ``show cdp neighbors Loopback0 detail`` and its LLDP form with
    ``% Invalid input`` at the interface's name, for the deploy account as for the read-only
    one (measured 2026-11-13). Refused here, by name, before it is asked."""
    from modules.nsot.ifnames import canonical

    name = args["interface"]
    if canonical(name).lower().startswith("loopback"):
        return (f"{name} is a loopback, and nothing is cabled to a loopback: this read is of "
                "an interface a link is on")
    return ""


def other_platform(op: str, host: str, scope: dict) -> str:
    """Why the operation *op* is another platform's form on *host* (a dialect's own form on
    the other dialect; a switch's read on a device with no VLAN database), or ``""``: it is
    this platform's, or the platform is not known (then the check refuses or asks, said in its
    own words). The read-only account probe leaves such a form out by this, the AI's check
    refuses it by the same comparison: one home."""
    for name, _send, _args, against, _cls, _words in SHAPES:
        asks = getattr(against, "other_platform", None)
        if name == op and asks is not None:
            return asks({"device": host}, scope)
    return ""


def _all(*checks):
    def check(args, scope) -> str:
        for one in checks:
            why = one(args, scope)
            if why:
                return why
        return ""
    return check


#: The installation choice, in the operator's words (2026-11-13), and its setting: whether the
#: read-only account's level holds ping's and traceroute's options (off by default: the lines
#: that open them take ping and traceroute from every account below that level).
PING_CHOICE = "Let the read-only account ping and traceroute"
PING_CHOICE_KEY = "ai_read_account_ping_traceroute"
#: The operations asked only under the choice: each carries an option that is not the
#: device's default, which the read-only account's level does not hold without it.
CHOICE_OPS = ("ping_from", "ping6_from", "traceroute", "traceroute6")


def ping_traceroute_on() -> bool:
    """Whether the installation choice `PING_CHOICE` is on (`PING_CHOICE_KEY`; off by default,
    and off when the setting cannot be read: the closed side)."""
    from modules.settings_schema import get_setting

    try:
        return get_setting("ai_read_account_ping_traceroute", False) is True  # PING_CHOICE_KEY
    except Exception as exc:                            # noqa: BLE001 (closed, and said)
        log.warning("router reads: %s could not be read (%s): read as off", PING_CHOICE_KEY,
                    type(exc).__name__)
        return False


def choice_off(op: str, scope: dict) -> str:
    """Why the operation *op* is not asked while the installation choice is off, or ``""`` (it
    is not one of `CHOICE_OPS`, or the scope says the choice is on). The scope carries the
    choice (`scope_for`); one built without it is read as off."""
    if op not in CHOICE_OPS or (scope or {}).get("ping_traceroute") is True:
        return ""
    return (f"it needs the installation choice \"{PING_CHOICE}\" ({PING_CHOICE_KEY} is off): "
            "its options are above the read-only account's level without it, and the lines "
            "that open them take ping and traceroute from every account below that level")


def _choice_for(op: str):
    def check(args, scope) -> str:
        return choice_off(op, scope)
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
    ("cdp", "show cdp neighbors {interface} detail", _IF, _cabled_interface, None,
     "who CDP says is cabled there"),
    ("lldp", "show lldp neighbors {interface} detail", _IF, _cabled_interface, None,
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
    ("stp", "show spanning-tree interface {interface}", _IF, _switch_form, None,
     "spanning tree on the interface"),
    # The plain ping: 5 echoes, a 2 second timeout, the device's defaults (`_PING`'s numbers).
    ("ping", "ping {address}", _ADDR4, _address_of_network, None,
     "an address reachable"),
    ("ping_from", "ping {address} source {interface} " + _PING, _ADDR4 + _IF,
     _all(_choice_for("ping_from"), _address_of_network), None,
     "an address reachable from an interface"),
    ("ping6", "ping ipv6 {address}", _ADDR6, _address_of_network, None,
     "an address reachable (IPv6)"),
    ("ping6_from", "ping ipv6 {address} source {interface} " + _PING, _ADDR6 + _IF,
     _all(_choice_for("ping6_from"), _address_of_network), None,
     "an address reachable from an interface (IPv6)"),
    ("traceroute", "traceroute {address} " + _TRACE, _ADDR4,
     _all(_choice_for("traceroute"), _address_of_network), None,
     "the path toward an address"),
    ("traceroute6", "traceroute ipv6 {address} " + _TRACE, _ADDR6,
     _all(_choice_for("traceroute6"), _address_of_network), None,
     "the path toward an address (IPv6)"),
    # AI troubleshooting's S6 (the fix-it plan): a lost stream's two device reads, each the
    # stream runbook's own command (`diagnose.COMMANDS`), measured on captures read through
    # Mercury's reads engine (tests/fixtures/diagnose/: one brief, two devices' receivers).
    ("telemetry_brief", "show telemetry ietf subscription all", (), None, None,
     "every telemetry subscription the device holds, and its state"),
    ("telemetry_receiver", "show telemetry ietf subscription {subscription} receiver",
     (("subscription", SUBSCRIPTION),), _subscription_named, None,
     "one subscription's receiver: its address, port, connection and state"),
    # The device's side of a half-open session (C3640): its telemetry connections, each one's
    # index (a receiver's connection id), peer, source and state ("Disconnecting" while the
    # collector still holds the session). IOS-XE 17's form, the operator's of 2026-11-14;
    # another platform's form on IOS. Whether the read-only account's level may run it is
    # measured by the probe, never assumed: no privilege line names it.
    ("telemetry_connection", "show telemetry internal connection", (),
     _dialect("cisco_iosxe"), None,
     "the device's telemetry connections: each one's peer, source and state (IOS-XE)"),
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


#: The shapes AI troubleshooting's family alone asks for (`modules/ai/fixit_reads.py`, S6):
#: the heal analysis's read set stays as its released pass-1 schema (heal_analysis v2)
#: declares it, so a feature's reads widen only with its own schema.
TELEMETRY = ("telemetry_brief", "telemetry_receiver", "telemetry_connection")
#: Those shapes' operations, declared over the same rule as every other.
TELEMETRY_OPS = tuple(_operation(*s) for s in SHAPES if s[0] in TELEMETRY)

#: The router read family: answers go out under the device state class (N20), the
#: configuration forms under the configuration class. The heal analysis's and the SDN
#: analyst's set: every shape but `TELEMETRY`.
AI_READS = RL.ReadFamily(name="router_cli", transport="cli", egress_class="device_state",
                         operations=tuple(_operation(*s) for s in SHAPES
                                          if s[0] not in TELEMETRY), run=run,
                         words="the AI read set for routers and switches")


# ── The AI's reads by command family (the operator, 2026-11-14, C3661; the review's BLOCKER) ──
#
# "replace the fixed read SHAPES with the Show commands engine ... on devices in the incident's
# scope", and, from Tier 1's review (the coordinator's decision, 2026-11-14): "the AI's `show`
# becomes a POSITIVE allowlist of command families, never 'anything Show commands allows minus a
# list'". With Mercury's account (privilege 15 after enable) a show can print a secret's
# position the left-out list never named (`show crypto isakmp key`, `show vtp password`, HSRP's
# authentication text), so a read the AI asks must be one of `SHOW_FAMILIES`, an engineer's
# troubleshooting reads, each naming the argument shapes it takes. The model names a read by its
# verb (an operation: `show`, `show_config`, `ping`, `traceroute`) and its words after the verb;
# code decides whether it runs, in this order:
# 1. Mercury's one allowlist (`readonly_commands.refusal`, the whole command, no Tier 1 extra), as
#    for Show commands, and a `;` refused; the read loop's transport rule asks it again;
# 2. the left-out list (`COMMAND_LEFT_OUT`), a second layer under the families;
# 3. a configuration form is `show_config`'s alone, under the configuration class (off on every
#    network until C1720), and `show_config` takes nothing else (`CONFIG_FAMILIES`);
# 4. `show` takes only a family of `SHOW_FAMILIES`: its words (each abbreviated as IOS takes
#    them, two letters or more), then one of its tails, each slot of its shape compared with what
#    Mercury holds: an interface resolved by a unique canonical type (`resolve_interface`) to one
#    the device's committed golden holds, an address or prefix of the network (IPv4 and IPv6), a
#    netmask only right after an address, a subscription the device's intent declares and the
#    incident names, a VLAN or a number. Anything else is refused, naming the families, and is a
#    missing capability for review (`modules/ai/missing.py`): that is how Mercury learns what to
#    add. Spanning tree only of a known switch; the telemetry connections only on IOS-XE;
# 5. a ping's or traceroute's target is an address of the network, its source an interface the
#    golden holds or an address of the network, its worst case inside 19.5's bounds; under the
#    read-only account its options need the installation choice `PING_CHOICE`.
# It then runs through `run`: the reads engine as kind ``ai_analysis``, Show commands' own
# engine and session path, recorded on History › Reads with whom it signed in as.

#: The words after a read's verb: one line of printable text (the families judge it).
COMMAND_WORDS = RL.Text(r"[!-~](?:[ -~]{0,238}[!-~])?",
                        "the command's words after its verb, on one line: a read of one of "
                        "the AI's command families", most=240)

#: Refused whatever the families say (each by its whole words, any of them abbreviated): a
#: second layer, what the answer would print being a secret's position, the device's log (read
#: from Loki, masked, by the `logs` read), a heavy dump, or the commands people typed.
COMMAND_LEFT_OUT = (
    (("show", "key", "chain"), "it prints a secret's position"),
    (("show", "snmp"), "it prints a secret's position"),
    (("show", "users"), "it prints a secret's position"),
    (("show", "history"), "it prints the commands people typed, which may hold a secret"),
    (("show", "logging"), "the device's log reaches the model only from Loki, masked: ask the "
                          "logs read"),
    (("show", "tech-support"), "it runs for minutes, loads the device's CPU and prints its "
                               "configuration"),
    (("show", "crypto"), "it prints keys and key material"),
    (("show", "vtp", "password"), "it prints a secret's position"),
)

#: `show`'s families: ``(words, (tail, ...))``, each tail a space-separated pattern of literal
#: words and slots: ``{if}`` an interface the golden holds, ``{a4}`` ``{a6}`` an address of the
#: network, ``{p4}`` ``{p6}`` a prefix of it, ``{mask}`` an IPv4 netmask (only after an address),
#: ``{vlan}`` 1 to 4094, ``{n}`` a number of up to 10 digits, ``{sub}`` a telemetry
#: subscription, ``{mac}`` a MAC in IOS's dotted form, ``{name}`` a VRF's name. ``""`` is the
#: family's words alone. The floor is the AI read set's shapes and the heal runbooks' commands
#: (tests/test_ai_engineer_reads.py holds both to these).
SHOW_FAMILIES = (
    ("interfaces", ("", "{if}", "description", "status", "counters", "trunk", "summary",
                    "{if} counters", "{if} status", "{if} switchport", "{if} trunk")),
    ("ip interface", ("", "brief", "{if}")),
    ("ipv6 interface", ("", "brief", "{if}")),
    ("ip route", ("", "summary", "{a4}", "{a4} {mask}", "{p4}", "vrf {name}", "vrf {name} {a4}",
                  "connected", "static", "ospf", "bgp")),
    ("ipv6 route", ("", "summary", "{a6}", "{p6}", "connected", "static", "ospf", "bgp")),
    ("ip cef", ("", "{a4}", "{a4} detail", "{p4}", "summary")),
    ("ipv6 cef", ("", "{a6}", "{p6}", "summary")),
    ("ip bgp", ("summary", "neighbors", "neighbors {a4}", "neighbors {a4} routes",
                "neighbors {a4} advertised-routes", "{a4}", "{p4}")),
    ("bgp ipv6 unicast", ("summary", "neighbors", "neighbors {a6}", "neighbors {a6} routes",
                          "{a6}", "{p6}")),
    ("ip ospf", ("", "neighbor", "neighbor detail", "neighbor {if}", "neighbor {if} detail",
                 "interface", "interface brief", "interface {if}", "database")),
    ("ipv6 ospf", ("neighbor", "neighbor detail", "interface", "interface brief",
                   "interface {if}")),
    ("ospfv3", ("neighbor", "neighbor detail", "interface brief")),
    ("ip protocols", ("", "summary")),
    ("bfd neighbors", ("", "details")),
    ("cdp neighbors", ("", "detail", "{if}", "{if} detail")),
    ("lldp neighbors", ("", "detail", "{if}", "{if} detail")),
    ("ip arp", ("", "{a4}", "{if}")),
    ("arp", ("",)),
    ("ipv6 neighbors", ("", "{a6}", "{if}")),
    ("mac address-table", ("address {mac}", "interface {if}", "vlan {vlan}", "dynamic", "count")),
    ("spanning-tree", ("", "summary", "root", "blockedports", "interface {if}",
                       "interface {if} detail", "vlan {vlan}")),
    ("vlan", ("brief", "id {vlan}")),
    ("etherchannel", ("summary",)),
    ("telemetry ietf subscription", ("all", "all brief", "all detail", "{sub}", "{sub} detail",
                                     "{sub} receiver")),
    ("telemetry internal connection", ("",)),
    ("version", ("",)),
    ("inventory", ("",)),
    ("platform", ("",)),
    ("processes cpu", ("", "sorted", "history", "platform sorted")),
    ("processes memory", ("", "sorted")),
    ("environment", ("", "all")),
    ("clock", ("", "detail")),
    ("ntp associations", ("", "detail")),
    ("ntp status", ("",)),
    ("ip sla statistics", ("", "{n}")),
    ("ip sla summary", ("",)),
    ("track", ("", "brief", "{n}")),
    # Their brief forms only: the detail forms print the authentication text.
    ("standby", ("brief",)),
    ("vrrp", ("brief",)),
)
#: `show_config`'s families: the configuration forms, under the configuration class.
CONFIG_FAMILIES = (
    ("running-config", ("", "interface {if}")),
    ("startup-config", ("",)),
    ("derived-config", ("", "interface {if}")),
    ("configuration", ("",)),
    ("archive", ("",)),
    ("access-lists", ("",)),
    ("ip access-lists", ("", "{name}")),
    ("ipv6 access-list", ("", "{name}")),
)
#: The configuration forms as whole words, so `show` refuses them by name.
CONFIG_FORMS = tuple(("show",) + tuple(w.split()) for w, _t in CONFIG_FAMILIES)

#: The most an AI ping or traceroute may hold its device, in seconds, by its own arguments and
#: IOS's defaults (`readonly_commands.bound_seconds` less its slack): 19.5's fixed bounds, a
#: traceroute of ttl 1 to 16, one probe, 2 s each (32 s), with 8 s beside it. A person's Show
#: commands allows 300 s; a model's reads stay inside the bounds 19.5 set for them.
AI_TARGET_SECONDS = 40
#: An interface-shaped token: a type word, then its number and its slot, port and subinterface.
_IF_TOKEN = re.compile(r"([A-Za-z][A-Za-z-]*)([0-9][0-9/.:]*)\Z")
_NUMBERS = re.compile(r"[0-9][0-9/.:]*\Z")
_VRF = re.compile(r"[A-Za-z0-9_.-]{1,32}\Z")
_MAC = re.compile(r"[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\Z")


def _abbreviates(words: list, full: tuple) -> bool:
    """*words* begin with an abbreviation of *full*, word by word: each a prefix of its word,
    one letter or more, without case. Wider than IOS's own matching on purpose: refusing by
    resemblance is safe (``show r`` is read as the running configuration, and refused as it)."""
    if len(words) < len(full):
        return False
    return all(w and f.startswith(w.lower()) for w, f in zip(words, full))


def _word_is(typed: str, word: str) -> bool:
    """*typed* names *word* as IOS takes it: the word, or its prefix of two letters or more."""
    low = typed.lower()
    return low == word or (len(low) >= 2 and word.startswith(low))


def _interface_type(word: str) -> str:
    """The canonical interface type *word* names: a type or an abbreviation `ifnames` lists, or
    a unique prefix of one canonical type (``Gig`` and ``G`` → ``GigabitEthernet``, ``Loop`` →
    ``Loopback``); ``""`` for no type or more than one (``T``: TenGigabitEthernet, Tunnel and
    TwentyFiveGigE)."""
    from modules.nsot.ifnames import INTERFACE_PREFIXES

    low = word.lower()
    for canon, abbrevs in INTERFACE_PREFIXES:
        if any(low == a.lower() for a in abbrevs):
            return canon
    hits = {canon for canon, _a in INTERFACE_PREFIXES if canon.lower().startswith(low)}
    return next(iter(hits)) if len(hits) == 1 else ""


def resolve_interface(token: str, host: str, scope: dict) -> tuple:
    """``(the golden's interface name, "")`` when *token* names, by a unique canonical type and
    its number, an interface *host*'s committed golden holds; ``("", why)`` otherwise, naming the
    token and what the golden holds."""
    from modules.nsot.ifnames import canonical

    held = ((((scope or {}).get("devices") or {}).get(host) or {}).get("interfaces") or ())
    m = _IF_TOKEN.fullmatch(token or "")
    kind = _interface_type(m.group(1)) if m else ""
    if not kind:
        return "", (f"{token!r} is not an interface Mercury can name: its type is none of the "
                    f"interface types Mercury knows, or more than one (it holds "
                    f"{_listed(held)})")
    wanted = (kind + m.group(2)).lower()
    for h in held:
        if canonical(h).lower() == wanted:
            return h, ""
    return "", f"{token} is not an interface {host}'s golden holds (it holds {_listed(held)})"


def _address_token(token: str):
    """``(kind, value)`` for a token that is an address (``"address"``) or a prefix
    (``"prefix"``), else ``(None, None)``. A netmask is an address here: it is a mask only in a
    slot that takes one, right after an address (`_slot`)."""
    if "/" in token:
        try:
            return "prefix", ipaddress.ip_network(token, strict=False)
        except ValueError:
            return None, None
    try:
        return "address", ipaddress.ip_address(token)
    except ValueError:
        return None, None


def _is_netmask(token: str) -> bool:
    try:
        bits = int(ipaddress.IPv4Address(token))
    except ValueError:
        return False
    low = ~bits & 0xFFFFFFFF
    return (low + 1) & low == 0


def _prefix_of_network(net, scope) -> str:
    network = (scope or {}).get("network") or "the network"
    for prefix in (scope or {}).get("prefixes") or ():
        held = ipaddress.ip_network(prefix, strict=False)
        if held.version == net.version and (net.subnet_of(held) or held.subnet_of(net)):
            return ""
    return (f"{net} is not a prefix of {network}: it neither holds nor lies inside a subnet "
            "its interfaces carry")


def _slot(slot: str, token: str, host: str, scope: dict) -> str:
    """``""`` when *token* fills *slot* (`SHOW_FAMILIES`' shapes), else why."""
    if slot == "if":
        return resolve_interface(token, host, scope)[1]
    if slot in ("a4", "a6"):
        kind, value = _address_token(token)
        if kind != "address" or value.version != int(slot[1]):
            return f"{token!r} is not one IPv{slot[1]} address"
        return _of_network(str(value), scope)
    if slot in ("p4", "p6"):
        kind, value = _address_token(token)
        if kind != "prefix" or value.version != int(slot[1]):
            return f"{token!r} is not one IPv{slot[1]} prefix"
        return _prefix_of_network(value, scope)
    if slot == "mask":
        return "" if _is_netmask(token) else f"{token!r} is not an IPv4 netmask"
    if slot == "vlan":
        return "" if token.isdigit() and 1 <= int(token) <= 4094 else (
            f"{token!r} is not a VLAN, 1 to 4094")
    if slot == "n":
        return "" if token.isdigit() and len(token) <= 10 else f"{token!r} is not a number"
    if slot == "sub":
        if not (token.isdigit() and len(token) <= 10):
            return f"{token!r} is not a telemetry subscription id"
        return _subscription_named({"device": host, "subscription": token}, scope)
    if slot == "mac":
        return "" if _MAC.fullmatch(token) else f"{token!r} is not a MAC in IOS's dotted form"
    if slot == "name":
        return "" if _VRF.fullmatch(token) else f"{token!r} is not a name"
    return f"no slot {slot}"


def _tail_refusal(tail: str, rest: list, host: str, scope: dict) -> tuple:
    """``(matched, why)``: whether *rest* has *tail*'s shape word for word, and, when it does,
    why a slot's value is refused (``""``: it may be read)."""
    pattern = tail.split()
    if len(pattern) != len(rest):
        return False, ""
    for want, token in zip(pattern, rest):
        if not (want.startswith("{") and want.endswith("}")) and not _word_is(token, want):
            return False, ""
    for want, token in zip(pattern, rest):
        if want.startswith("{") and want.endswith("}"):
            why = _slot(want[1:-1], token, host, scope)
            if why:
                return True, why
    return True, ""


def family_refusal(words: list, host: str, scope: dict, families=SHOW_FAMILIES) -> str:
    """``""`` when *words* (after `show`) are one of *families* in one of its tails, every slot
    compared, else why. A split interface name (``GigabitEthernet 4``) is refused, asking for one
    word, so it is compared with the golden; anything outside the families is refused naming
    them, the words a missing capability records."""
    why = _family_refusal(words, host, scope, families)
    if why and ("read families" in why or "is not an interface Mercury can name" in why):
        # A refused form holding a type word and a number apart (``GigabitEthernet 4``) is said
        # as that, so the model writes one word; a family's own `vlan 10` is no interface.
        for i, token in enumerate(words[:-1]):
            if _interface_type(token) and not _IF_TOKEN.fullmatch(token) \
                    and _NUMBERS.fullmatch(words[i + 1]):
                return (f"write the interface as one word, `{token}{words[i + 1]}`, so "
                        f"Mercury can compare it with {host}'s golden")
    return why


def _family_refusal(words: list, host: str, scope: dict, families) -> str:
    best = ""
    for family, tails in sorted(families, key=lambda f: -len(f[0].split())):
        fixed = family.split()
        if len(words) < len(fixed) or not all(_word_is(t, w) for t, w in zip(words, fixed)):
            continue
        rest = words[len(fixed):]
        shapes = []
        for tail in tails:
            matched, why = _tail_refusal(tail, rest, host, scope)
            if matched and not why:
                return ""
            if matched:
                # A comparison with what Mercury holds says more than a shape that did not fit
                # (a shape's refusal names the token quoted first): it is the one said.
                if why.startswith("'"):
                    shapes.append(why)
                elif not best:
                    best = why
        best = best or (shapes[0] if shapes else "")
        if best:
            return best
        shown = "; ".join(f"`show {family}{' ' + t if t else ''}`" for t in tails)
        return (f"`show {' '.join(words)}` is not one of the AI's read families' forms (show "
                f"{family} takes: {shown})")
    return (f"`show {' '.join(words)}` is not one of the AI's read families: "
            + ", ".join(f for f, _t in families))


def _target_refusal(verb: str, rest: list, command: str, host: str, scope: dict) -> str:
    """A ping's or traceroute's own checks: its target and source, its bounds, the choice."""
    from modules import readonly_commands

    args = list(rest)
    if args and args[0].lower() == "vrf":
        args = args[2:]
    if args and args[0].lower() in ("ip", "ipv6"):
        args = args[1:]
    kind, value = _address_token(args[0]) if args else (None, None)
    if kind != "address":
        return (f"a {verb}'s target is one address of the network, and "
                f"{(args or ['nothing'])[0]!r} is not an address")
    why = _of_network(str(value), scope)
    if why:
        return why
    lowered = [a.lower() for a in args]
    if "source" in lowered:
        i = lowered.index("source")
        source = args[i + 1] if i + 1 < len(args) else ""
        skind, sval = _address_token(source)
        why = (_of_network(str(sval), scope) if skind == "address"
               else resolve_interface(source, host, scope)[1])
        if why:
            return f"its source: {why}"
    worst = readonly_commands.bound_seconds(command) - readonly_commands.SLACK_SECONDS
    if worst > AI_TARGET_SECONDS:
        return (f"its worst case is {worst} s, over the {AI_TARGET_SECONDS} s an AI {verb} "
                "may hold the device (19.5's bounds: give repeat, timeout, probe and ttl, "
                f"for example `{verb} <address> "
                + ("repeat 5 timeout 2" if verb == "ping"
                   else "numeric timeout 2 probe 1 ttl 1 16") + "`)")
    if (len(args) > 1 and reads_as_of(scope) == "read_only"
            and (scope or {}).get("ping_traceroute") is not True):
        return (f"its options need the installation choice \"{PING_CHOICE}\" "
                f"({PING_CHOICE_KEY} is off): under the read-only account they are above "
                "its level without it")
    return ""


def reads_as_of(scope: dict) -> str:
    """Whom a scope's reads sign in as: its ``reads_as`` (`scope_for` reads the setting), and a
    scope that names none is the read-only account's, the closed side."""
    return "mercury" if (scope or {}).get("reads_as") == "mercury" else "read_only"


def command_refusal(command: str, host: str, scope: dict, *, config: bool = False) -> str:
    """``""`` when *command* may be read on *host* as the model asked it, else why, naming the
    word or argument and what it was compared with (the block's comment above, in its order).
    *config*: the `show_config` operation's, which takes only a configuration form. The device
    itself (in scope, its account) is the device argument's check (`_device_named`)."""
    from modules import readonly_commands

    why = readonly_commands.refusal(command)
    if why:
        return f"Mercury's read-only allowlist refuses `{command}`: {why}"
    if ";" in command:
        # IOS reads it as a word, not a separator; another platform's shell may not, and no read
        # needs one (19.5's planted `; reload`). Refused by resemblance, which is safe.
        return f"a ';' is never part of a read, and `{command}` holds one"
    head = command.split("|", 1)[0]
    words = head.split()
    verb = words[0].lower() if words else ""
    for full, reason in COMMAND_LEFT_OUT:
        if _abbreviates(words, full):
            return f"`{' '.join(full)}` is left out of the AI's reads on purpose: {reason}"
    rest = words[1:]
    if verb in ("ping", "traceroute"):
        return _target_refusal(verb, rest, command, host, scope)
    is_config = any(_abbreviates(words, full) for full in CONFIG_FORMS)
    if config and not is_config:
        return (f"`{head.strip()}` is not a configuration form: show_config reads only "
                + ", ".join(f"`show {f}`" for f, _t in CONFIG_FAMILIES) + "; ask show for it")
    if is_config and not config:
        return (f"`{head.strip()}` prints the device's configuration: it is show_config's, "
                "under the configuration class")
    why = family_refusal(rest, host, scope, CONFIG_FAMILIES if config else SHOW_FAMILIES)
    if why:
        return why
    if _abbreviates(rest, ("telemetry", "internal", "connection")):
        # IOS-XE 17's form (C3640's `telemetry_connection` shape, the operator's of 2026-11-14):
        # on IOS, or a device whose platform is not known, another platform's form, never asked.
        why = _dialect("cisco_iosxe")({"device": host}, scope)
        if why:
            return why
    if rest and len(rest[0]) >= 2 and "spanning-tree".startswith(rest[0].lower()):
        why = _switch_form({"device": host}, scope)
        if why:
            return why
    return ""


def _command_check(verb: str, config: bool = False):
    def check(args, scope) -> str:
        return command_refusal(f"{verb} {args['words']}", args["device"], scope, config=config)
    return check


def _command_op(name: str, verb: str, words: str, cls=None, config: bool = False):
    spec = {"device": RL.Arg(RL.Text(DEVICE, "a device name"), against=_device_named),
            "words": RL.Arg(COMMAND_WORDS)}
    return RL.Operation(name, args=spec, sends=(verb + " {words}",), egress_class=cls,
                        against=_command_check(verb, config), words=words)


#: The device's reads by Mercury's allowlist (C3661): each names its verb, and the model gives
#: the words after it.
COMMAND_OPS = (
    _command_op("show", "show", "a show of one of the AI's command families, in one of its "
                "forms (listed below; its output filtered only by include, exclude, begin, "
                "section or count); a configuration form is show_config's"),
    _command_op("show_config", "show", "a configuration form (running-config, startup-config, "
                "derived-config, archive, access lists), under the configuration class",
                cls="configuration", config=True),
    _command_op("ping", "ping", "a bounded ping of an address of the network (ip or ipv6, and "
                "repeat, size, timeout, source, df-bit; its worst case at most 40 s)"),
    _command_op("traceroute", "traceroute", "a bounded traceroute toward an address of the "
                "network (numeric, timeout, probe, ttl, source; its worst case at most 40 s, so "
                "give them: numeric timeout 2 probe 1 ttl 1 16)"),
)


# ── The scope: what the comparisons read ──────────────────────────────────────────────────────

_IFACE_LINE = re.compile(r"^interface (\S+)\s*$", re.M)


def golden_interfaces(text: str) -> list:
    """The interfaces a golden holds: each ``interface <name>`` line, as written."""
    return list(dict.fromkeys(_IFACE_LINE.findall(text or "")))


def vlan_databases(network: str, hosts) -> dict:
    """``{host: (has, words)}``: whether each of *hosts* has a VLAN database, as Mercury's
    platform table declares it or the device's own recorded answer measured it
    (`vlan_capability.of`: stored data only, never a device read); ``(None, why)`` when neither
    says, or it could not be read. A network with no data folder has recorded no answer, and
    is asked its declaration alone: a read makes no folder."""
    import os

    from modules import config
    from modules.nsot import vlan_capability

    out = {}
    recorded = os.path.isdir(config.list_data_path(network))
    for host in hosts or ():
        try:
            got = vlan_capability.of(network, host, measure=recorded)
        except Exception as exc:                        # noqa: BLE001 (unknown, and said)
            log.warning("router reads: %s's VLAN database could not be read: %s", host, exc)
            got = {"has": None, "words": f"it could not be read ({type(exc).__name__})"}
        out[host] = (got.get("has"), got.get("words") or "")
    return out


def scope_for(network: str, hosts, *, incident: str = "", turned_on_by: str = "",
              intents: dict = None, goldens: dict = None, dialects: dict = None,
              capabilities: dict = None, ping_traceroute: bool = None,
              reads_as: str = None) -> dict:
    """What `AI_READS`' comparisons read for an incident's *hosts* in *network*: each device's
    golden interfaces, intent's BGP peers, its dialect, whether it has a VLAN database (a
    switch's reads) and whether it has a read-only account (`read_accounts`, the reads engine's
    resolver, always: never given); the network's addresses and subnets from committed intent.
    *intents* (``{host: host vars}``), *goldens* (``{host: text}``), *dialects* and
    *capabilities* (`vlan_databases`' shape) are read from the committed stores when not given,
    and *ping_traceroute* (the installation choice, `ping_traceroute_on`) from its setting.
    The reads are recorded as "the AI analysis of incident <id>, turned on by <admin>"."""
    from modules.neighbours import _v4, addresses, bgp_peers

    hosts = [h for h in dict.fromkeys(hosts or ()) if h]
    if intents is None or goldens is None:
        got_i, got_g = _committed(network, hosts)
        intents = got_i if intents is None else intents
        goldens = got_g if goldens is None else goldens
    if dialects is None:
        dialects = {h: _dialect_of((intents.get(h) or {}).get("platform"), h) for h in hosts}
    accounts = read_accounts(network, hosts)
    if capabilities is None:
        capabilities = vlan_databases(network, hosts)
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
            "subscriptions": _declared_subscriptions((intents or {}).get(host) or {}),
            "vlan_database": (capabilities.get(host) or (None, ""))[0],
            "vlan_database_words": (capabilities.get(host) or (None, ""))[1],
            "read_account": accounts[host][0], "read_account_why": accounts[host][1]}
    actor = (f"the AI analysis of incident {incident}, turned on by "
             f"{turned_on_by or 'nobody named'}") if incident else "the AI analysis"
    from modules.nsot import reads

    return {"network": network, "devices": devices,
            # Whom the reads sign in as (C3661), as the setting stands now; the reads engine reads
            # the setting again at the read, by the same function, and either fails closed.
            "reads_as": (reads.ai_reads_as() if reads_as is None
                         else ("mercury" if reads_as == "mercury" else "read_only")),
            "ping_traceroute": (ping_traceroute_on() if ping_traceroute is None
                                else ping_traceroute is True),
            "addresses": sorted(str(a) for a in addresses(intents or {})),
            "prefixes": sorted(prefixes), "actor": actor}


def _declared_subscriptions(hv: dict) -> list:
    """The telemetry subscription ids the device's committed intent declares, as text."""
    out = []
    for s in (hv or {}).get("telemetry") or []:
        sub = str((s or {}).get("subscription") or "") if isinstance(s, dict) else ""
        if sub and sub not in out:
            out.append(sub)
    return out


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
