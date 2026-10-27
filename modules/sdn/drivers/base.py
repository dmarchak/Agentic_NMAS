"""The SDN controller driver interface (PHASE8_PLAN 17.2).

A driver DECLARES what it can do, and Mercury offers only that:
- `kind` (the registry's key) and `label` (the words a person reads);
- `capabilities`, a subset of `CAPABILITIES`; a call needing one the driver does not declare
  answers a refusal naming it (and, where the driver says, why it is absent);
- `status`: `built`, `later` (`read_first` when its reads come before any write) or
  `unmaintained`. A driver that is not built is a declaration only: every call refuses,
  naming that.

**Every call answers `{"ok": bool, "error": str, ...}` and never raises.** It is bounded by the
connection's timeout as a whole: one deadline covers the connect, every retry and the reading of
the body, which is read in chunks against it (a trickling answer cannot outlast it), and capped
at `MAX_BODY_BYTES`, refused past that, never cut.

**A write's REST request is a value before it is a call.** Each write has a `render_*` twin
answering `{"ok", "method", "path", "body"}` with no I/O, the body the exact text to be sent.
The write is its render handed to `apply`, the ONE send path, which sends exactly that text:
so a preview can show the body, a confirm can hash it (`request_digest`) and the apply sends
what was hashed (CLAUDE.md, "What is confirmed is what is sent"). A write is never retried: an
answer lost on the way back does not say the request did not land.

**Credentials are resolved by a callable at each request**, never stored on the driver, its
session or its connection, never logged, and never in an answer: every string a call returns
has each credential value replaced, and an error's words are masked as every service's are.

One shape across drivers: `Flow`, `PortStats`, `Meter`, `MeterBand` and `MeterFeatures`, with
OpenFlow 1.3's OXM field names in a match (`OXM_FIELDS`) and actions as normalised dicts
(`ACTION_FIELDS`). A drop is an empty action list. Each driver translates its controller's
form both ways.

**Topology is one shape too** (`read_topology`, PHASE8_PLAN 17.1 S14): `links()` answers
``{"links": [{"src": end, "dst": end}]}``, `hosts()` ``{"hosts": [host]}`` and `topology()`
all three with the switches' ports, ``{"switches": [{"dpid", "dpid_hex", "ports": [port]}],
"links", "hosts", "hosts_note"}``. A port (`topo_port`) is ``{"dpid", "dpid_hex", "port_no",
"name", "hw_addr"}``, *port_no* a number; a link is one direction as the controller reports
it (a cable both ways is two); a host (`topo_host`) is ``{"mac", "ipv4", "ipv6", "dpid",
"dpid_hex", "port_no", "port_name", "port_hw_addr"}``, its addresses as the controller learned
them less the unspecified ones (`0.0.0.0`, `::`), which a host sends from before it has an
address. *hosts_note* is the driver's word on how current a listed host is (a controller that
keeps a host forever and records no time says so), never left for a reader to assume.
"""

import dataclasses
import hashlib
import logging
import time
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

#: What a driver may declare (17.2).
CAPABILITIES = frozenset({"read_topology", "read_flows", "read_port_stats", "read_meters",
                          "write_flows", "write_meters", "delete_flows"})
READS = frozenset({"read_topology", "read_flows", "read_port_stats", "read_meters"})
STATUSES = ("built", "later", "unmaintained")

DEFAULT_TIMEOUT = 5.0
#: The longest a connection's timeout may be: a controller that needs longer than this to
#: answer one request is not one a loop or a page can wait on.
MAX_TIMEOUT = 120.0
#: The largest answer read; past it the call is refused, never cut (a flow table read in part
#: would look whole).
MAX_BODY_BYTES = 32 * 1024 * 1024
#: The longest a controller's own words for a refusal are kept.
DETAIL_LIMIT = 500
#: Reads retried after a connection error or a 502/503/504, while the deadline allows.
READ_ATTEMPTS = 3
RETRY_PAUSE = 0.3
#: Credential values shorter than this are not replaced by value in an answer's text (a
#: one-letter value would take that letter out of every word); the positional mask still runs.
MIN_SCRUBBED = 4

UINT64_MAX = 2 ** 64 - 1
UINT32_MAX = 2 ** 32 - 1
#: OpenFlow 1.3's highest meter id a request may name (OFPM_MAX).
OFPM_MAX = 0xFFFF0000
#: OpenFlow 1.3's highest table a flow may be in (OFPTT_MAX).
OFPTT_MAX = 0xFE

#: OpenFlow 1.3's OXM match fields, by the names the specification gives them.
OXM_FIELDS = frozenset({
    "in_port", "in_phy_port", "metadata", "eth_dst", "eth_src", "eth_type", "vlan_vid",
    "vlan_pcp", "ip_dscp", "ip_ecn", "ip_proto", "ipv4_src", "ipv4_dst", "tcp_src", "tcp_dst",
    "udp_src", "udp_dst", "sctp_src", "sctp_dst", "icmpv4_type", "icmpv4_code", "arp_op",
    "arp_spa", "arp_tpa", "arp_sha", "arp_tha", "ipv6_src", "ipv6_dst", "ipv6_flabel",
    "icmpv6_type", "icmpv6_code", "ipv6_nd_target", "ipv6_nd_sll", "ipv6_nd_tll", "mpls_label",
    "mpls_tc", "mpls_bos", "pbb_isid", "tunnel_id", "ipv6_exthdr"})

#: Each normalised action or instruction type and the fields it carries (OpenFlow 1.3). An
#: instruction (GOTO_TABLE, METER, WRITE_METADATA, WRITE_ACTIONS, CLEAR_ACTIONS) sits in the
#: same list as the apply-actions, in the order the switch reports them.
ACTION_FIELDS = {
    "OUTPUT": ("port",),
    "GOTO_TABLE": ("table_id",),
    "METER": ("meter_id",),
    "WRITE_METADATA": ("metadata", "metadata_mask"),
    "WRITE_ACTIONS": ("actions",),
    "CLEAR_ACTIONS": (),
    "SET_FIELD": ("field", "value"),
    "COPY_TTL_OUT": (), "COPY_TTL_IN": (), "DEC_MPLS_TTL": (), "POP_VLAN": (),
    "DEC_NW_TTL": (), "POP_PBB": (),
    "PUSH_VLAN": ("ethertype",), "PUSH_MPLS": ("ethertype",), "POP_MPLS": ("ethertype",),
    "PUSH_PBB": ("ethertype",),
    "SET_MPLS_TTL": ("mpls_ttl",), "SET_NW_TTL": ("nw_ttl",), "SET_QUEUE": ("queue_id",),
    "GROUP": ("group_id",),
}
#: The instruction types (the rest are actions, which alone may sit inside WRITE_ACTIONS).
INSTRUCTION_TYPES = frozenset({"GOTO_TABLE", "METER", "WRITE_METADATA", "WRITE_ACTIONS",
                               "CLEAR_ACTIONS"})
#: An action read back that the driver could not translate: kept with the controller's own
#: text, never guessed at, and refused if it is ever sent.
UNPARSED = "UNPARSED"
#: OpenFlow's reserved ports, by the names a match or an OUTPUT may give instead of a number.
RESERVED_PORTS = frozenset({"IN_PORT", "TABLE", "NORMAL", "FLOOD", "ALL", "CONTROLLER",
                            "LOCAL", "ANY"})
METER_FLAGS = ("KBPS", "PKTPS", "BURST", "STATS")
METER_BAND_TYPES = ("DROP", "DSCP_REMARK")


# ───────────────────────────────────────────────────────────────────────────── the connection

@dataclasses.dataclass(frozen=True)
class Connection:
    """Where a controller answers, and how long a call may take. `credentials` is a callable
    answering a mapping (`username` and `password`, or `token`) at the moment of each request;
    the values are never kept here (17.1 S2 stores them as device credentials are)."""

    url: str
    verify_tls: bool = True
    timeout: float = DEFAULT_TIMEOUT
    credentials: Optional[Callable[[], Mapping[str, str]]] = dataclasses.field(
        default=None, repr=False, compare=False)

    @property
    def base_url(self) -> str:
        return (self.url or "").strip().rstrip("/")


def connection_problem(connection) -> str:
    """Why *connection* cannot be used, in words, or "" when it can. An IPv6 literal host is
    written bracketed (`http://[2001:db8::1]:8080`), as a URL must."""
    if not isinstance(connection, Connection):
        return f"no controller connection was given (got {type(connection).__name__})"
    url = connection.base_url
    if not url:
        return "the controller's URL is not set"
    try:
        parts = urlsplit(url)
        host, _port = parts.hostname, parts.port      # .port raises on a malformed port
    except ValueError as exc:
        return f"the controller's URL is not a URL ({exc})"
    if parts.scheme not in ("http", "https"):
        return f"the controller's URL must be http or https, not {parts.scheme or 'none'!r}"
    if not host:
        return "the controller's URL names no host"
    if parts.username is not None or parts.password is not None:
        return ("the controller's URL carries a user part; its credentials belong in the "
                "connection's credentials, never in the URL")
    if parts.query or parts.fragment:
        return "the controller's URL carries a query or a fragment; give its base URL only"
    timeout = connection.timeout
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) \
            or not 0 < timeout <= MAX_TIMEOUT:
        return (f"the connection's timeout must be more than 0 and at most {MAX_TIMEOUT:g} "
                f"seconds, not {timeout!r}")
    return ""


class SpecError(ValueError):
    """A datapath id, flow or meter refused before anything is sent, in words naming why."""


def parse_dpid(value) -> int:
    """A datapath id as an integer. An int is taken as it is; a string only in a hexadecimal
    form (`0x1`, sixteen hex digits as Ryu's topology and OpenFlow tools print it, or eight
    colon-separated bytes), never a decimal string, which sixteen digits would make ambiguous.
    Raises SpecError naming the value; a call turns that into its refusal."""
    if isinstance(value, bool):
        raise SpecError(f"a datapath id is a number, not {value!r}")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str):
        text = value.strip().lower()
        digits = text.replace(":", "") if ":" in text else text
        try:
            if text.startswith("0x"):
                number = int(text, 16)
            elif ":" in text and len(text.split(":")) == 8 and len(digits) == 16:
                number = int(digits, 16)
            elif len(text) == 16:
                number = int(text, 16)
            else:
                raise ValueError
        except ValueError:
            raise SpecError(f"{value!r} is not a datapath id: give an integer, 0x-prefixed "
                             "hex, sixteen hex digits or eight colon-separated bytes") from None
    else:
        raise SpecError(f"a datapath id is a number, not a {type(value).__name__}")
    if not 1 <= number <= UINT64_MAX:
        raise SpecError(f"a datapath id is from 1 to 2^64-1, not {number}")
    return number


def dpid_hex(dpid: int) -> str:
    """The sixteen-hex-digit form a person reads a datapath id in."""
    return f"{dpid:016x}"


def _port_number(value):
    """A port number from a number or the controller's text (decimal, 0x-prefixed, or the
    eight hex digits Ryu's topology prints), or the text kept when it is a reserved port's
    name; None for anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if text.upper() in RESERVED_PORTS:
        return text.upper()
    try:
        if text.lower().startswith("0x"):
            return int(text, 16)
        if len(text) == 8 and all(c in "0123456789abcdefABCDEF" for c in text):
            return int(text, 16)
        return int(text, 10)
    except ValueError:
        return None


def topo_port(dpid, port_no, name="", hw_addr="") -> dict:
    """One switch port in the topology shape; raises SpecError for a datapath id or port that
    is not one."""
    number = parse_dpid(dpid)
    port = _port_number(port_no)
    if port is None:
        raise SpecError(f"{port_no!r} is not a port number")
    return {"dpid": number, "dpid_hex": dpid_hex(number), "port_no": port,
            "name": str(name or ""), "hw_addr": str(hw_addr or "").lower()}


#: Addresses a host sends from before it has one (DHCP's and IPv6 duplicate detection's),
#: which locate nothing.
UNSPECIFIED = frozenset({"0.0.0.0", "::"})


def topo_host(mac, ipv4, ipv6, port: dict) -> dict:
    """One host a controller learned, in the topology shape: its addresses kept as learned,
    in order, less the unspecified ones; each checked to be an address of its family."""
    import ipaddress

    def keep(values, version):
        out = []
        for v in values or []:
            text = str(v or "").strip()
            if not text or text in UNSPECIFIED:
                continue
            try:
                if ipaddress.ip_address(text).version != version:
                    continue
            except ValueError:
                continue
            if text not in out:
                out.append(text)
        return out

    return {"mac": str(mac or "").lower(), "ipv4": keep(ipv4, 4), "ipv6": keep(ipv6, 6),
            "dpid": port["dpid"], "dpid_hex": port["dpid_hex"], "port_no": port["port_no"],
            "port_name": port["name"], "port_hw_addr": port["hw_addr"]}


def request_digest(rendered: Mapping) -> str:
    """The sha256 a confirm binds to: the method, the path and the exact body text."""
    text = f"{rendered.get('method', '')}\n{rendered.get('path', '')}\n{rendered.get('body', '')}"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ───────────────────────────────────────────────────────────────────────────── the one shape

def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


@dataclasses.dataclass
class Flow:
    """One flow entry, the same for every driver. Counters are None in a spec (a flow to
    install) and numbers in a flow read from a switch."""

    dpid: int
    table_id: int = 0
    priority: int = 0
    cookie: int = 0
    match: dict = dataclasses.field(default_factory=dict)
    actions: list = dataclasses.field(default_factory=list)
    idle_timeout: int = 0
    hard_timeout: int = 0
    packet_count: Optional[int] = None
    byte_count: Optional[int] = None
    duration_sec: Optional[int] = None

    @property
    def drops(self) -> bool:
        """A flow with no actions drops what it matches."""
        return not self.actions

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


FLOW_FIELDS = tuple(f.name for f in dataclasses.fields(Flow))


@dataclasses.dataclass
class PortStats:
    """One port's counters on one switch. `port_no` is a number, or a reserved port's name
    (`LOCAL`)."""

    dpid: int
    port_no: Any
    rx_packets: int = 0
    tx_packets: int = 0
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_dropped: int = 0
    tx_dropped: int = 0
    rx_errors: int = 0
    tx_errors: int = 0
    duration_sec: int = 0

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class MeterBand:
    """One band of a meter: its type (`DROP` or `DSCP_REMARK`), rate (in the meter's unit) and
    burst; `prec_level` for a DSCP remark; the band's counters when read."""

    type: str
    rate: int
    burst_size: int = 0
    prec_level: Optional[int] = None
    packet_band_count: Optional[int] = None
    byte_band_count: Optional[int] = None

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Meter:
    """One meter: its id, flags (`KBPS` or `PKTPS`, and `BURST`, `STATS`) and bands; its
    counters when read (None in a spec, and None when the switch reported no statistics for
    it)."""

    dpid: int
    meter_id: int
    flags: list = dataclasses.field(default_factory=list)
    bands: list = dataclasses.field(default_factory=list)
    flow_count: Optional[int] = None
    packet_in_count: Optional[int] = None
    byte_in_count: Optional[int] = None
    duration_sec: Optional[int] = None

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


METER_FIELDS = tuple(f.name for f in dataclasses.fields(Meter))


@dataclasses.dataclass
class MeterFeatures:
    """What a switch's meters can do."""

    dpid: int
    max_meter: int = 0
    band_types: list = dataclasses.field(default_factory=list)
    capabilities: list = dataclasses.field(default_factory=list)
    max_bands: int = 0
    max_color: int = 0

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


def _match_problems(match) -> list:
    if not isinstance(match, Mapping):
        return [f"a match is a mapping of OXM field names, not a {type(match).__name__}"]
    out = []
    for key, value in match.items():
        if key not in OXM_FIELDS:
            out.append(f"{key!r} is not an OpenFlow 1.3 OXM field name")
        elif not (_is_int(value) or isinstance(value, str)):
            out.append(f"match field {key} must be a number or a string, not {value!r}")
    return out


def _action_problems(actions, nested=False) -> list:
    if not isinstance(actions, list):
        return [f"actions are a list, not a {type(actions).__name__}"]
    out = []
    for action in actions:
        if not isinstance(action, Mapping):
            out.append(f"an action is a mapping with a type, not {action!r}")
            continue
        kind = action.get("type")
        if kind not in ACTION_FIELDS:
            out.append(f"{kind!r} is not an action this interface can send"
                       + (f" (read back as the controller's {action.get('text')!r})"
                          if kind == UNPARSED else ""))
            continue
        if nested and kind in INSTRUCTION_TYPES:
            out.append(f"WRITE_ACTIONS holds actions, not the instruction {kind}")
            continue
        wanted = set(ACTION_FIELDS[kind])
        given = set(action) - {"type"}
        if kind == "WRITE_METADATA":
            wanted.discard("metadata_mask")
            given.discard("metadata_mask")
        if given != wanted:
            out.append(f"{kind} carries {sorted(wanted) or 'no fields'}, not {sorted(given)}")
            continue
        for name in given:
            value = action[name]
            if name == "actions":
                out += _action_problems(value, nested=True)
            elif name in ("port", "value"):
                if not (_is_int(value) or isinstance(value, str)):
                    out.append(f"{kind}'s {name} must be a number or a string, not {value!r}")
                elif name == "port" and isinstance(value, str) and value not in RESERVED_PORTS:
                    out.append(f"{value!r} is not a port number or a reserved port's name")
            elif name == "field":
                if value not in OXM_FIELDS:
                    out.append(f"SET_FIELD's {value!r} is not an OpenFlow 1.3 OXM field name")
            elif not _is_int(value) or value < 0:
                out.append(f"{kind}'s {name} must be a whole number, not {value!r}")
        if "metadata_mask" in action and (not _is_int(action["metadata_mask"])
                                          or action["metadata_mask"] < 0):
            out.append(f"WRITE_METADATA's metadata_mask must be a whole number, not "
                       f"{action['metadata_mask']!r}")
    return out


def _bounded(name, value, low, high) -> list:
    if not _is_int(value) or not low <= value <= high:
        return [f"{name} must be a whole number from {low} to {high}, not {value!r}"]
    return []


def flow_from_spec(dpid, spec) -> Flow:
    """A `Flow` to send, from a `Flow` or a mapping of its fields; the call's *dpid* is the
    switch, and a spec naming another is refused. Raises SpecError naming every problem."""
    dpid = parse_dpid(dpid)
    if isinstance(spec, Flow):
        values = spec.as_dict()
    elif isinstance(spec, Mapping):
        unknown = sorted(set(spec) - set(FLOW_FIELDS))
        if unknown:
            raise SpecError(f"a flow has no field {', '.join(unknown)}; its fields are "
                             f"{', '.join(FLOW_FIELDS)}")
        values = dict(spec)
    else:
        raise SpecError(f"a flow spec is a Flow or a mapping, not a {type(spec).__name__}")
    named = values.get("dpid", dpid)
    if named is not None and named != dpid:
        try:
            same = parse_dpid(named) == dpid
        except SpecError:
            same = False
        if not same:
            raise SpecError(f"the spec names switch {named!r}, the call switch {dpid}")
    values["dpid"] = dpid
    flow = Flow(**values)
    problems = (_bounded("table_id", flow.table_id, 0, OFPTT_MAX)
                + _bounded("priority", flow.priority, 0, 0xFFFF)
                + _bounded("cookie", flow.cookie, 0, UINT64_MAX)
                + _bounded("idle_timeout", flow.idle_timeout, 0, 0xFFFF)
                + _bounded("hard_timeout", flow.hard_timeout, 0, 0xFFFF)
                + _match_problems(flow.match) + _action_problems(flow.actions))
    if problems:
        raise SpecError("; ".join(problems))
    return flow


def meter_from_spec(dpid, spec, *, delete=False) -> Meter:
    """A `Meter` to send (for a delete, only its id counts). Raises SpecError naming every
    problem: exactly one rate unit (KBPS or PKTPS), known flags, at least one band of a known
    type with a positive rate."""
    dpid = parse_dpid(dpid)
    if isinstance(spec, Meter):
        values = spec.as_dict()
    elif isinstance(spec, Mapping):
        unknown = sorted(set(spec) - set(METER_FIELDS))
        if unknown:
            raise SpecError(f"a meter has no field {', '.join(unknown)}; its fields are "
                             f"{', '.join(METER_FIELDS)}")
        values = dict(spec)
    else:
        raise SpecError(f"a meter spec is a Meter or a mapping, not a {type(spec).__name__}")
    named = values.get("dpid", dpid)
    if named is not None and named != dpid:
        raise SpecError(f"the spec names switch {named!r}, the call switch {dpid}")
    values["dpid"] = dpid
    if "meter_id" not in values:
        raise SpecError("a meter spec names its meter_id")
    meter = Meter(**values)
    problems = _bounded("meter_id", meter.meter_id, 1, OFPM_MAX)
    if delete:
        if problems:
            raise SpecError("; ".join(problems))
        return meter
    flags = meter.flags
    if not isinstance(flags, list) or any(f not in METER_FLAGS for f in flags):
        problems.append(f"a meter's flags are from {', '.join(METER_FLAGS)}, not {flags!r}")
    elif ("KBPS" in flags) == ("PKTPS" in flags):
        problems.append("a meter's flags name exactly one rate unit, KBPS or PKTPS")
    bands = meter.bands
    if not isinstance(bands, list) or not bands:
        problems.append("a meter has at least one band")
    else:
        for band in bands:
            values = band.as_dict() if isinstance(band, MeterBand) else band
            if not isinstance(values, Mapping):
                problems.append(f"a band is a mapping, not {band!r}")
                continue
            if values.get("type") not in METER_BAND_TYPES:
                problems.append(f"a band's type is {' or '.join(METER_BAND_TYPES)}, not "
                                f"{values.get('type')!r}")
            problems += _bounded("a band's rate", values.get("rate"), 1, UINT32_MAX)
            problems += _bounded("a band's burst_size", values.get("burst_size", 0), 0,
                                 UINT32_MAX)
            if values.get("type") == "DSCP_REMARK":
                problems += _bounded("a DSCP remark's prec_level", values.get("prec_level"),
                                     0, 0xFF)
    if problems:
        raise SpecError("; ".join(problems))
    meter.bands = [b.as_dict() if isinstance(b, MeterBand) else dict(b) for b in bands]
    return meter


# ───────────────────────────────────────────────────────────────────────────── the driver

class _Deadline(Exception):
    """The connection's timeout passed while a body was still being read."""


class _TooLarge(Exception):
    """An answer past MAX_BODY_BYTES."""


#: Each call, and the capability it needs (None: every built driver answers it).
CALL_CAPABILITY = {
    "test": None, "switches": None, "switch_desc": None,
    "links": "read_topology", "hosts": "read_topology", "topology": "read_topology",
    "flows": "read_flows",
    "port_stats": "read_port_stats",
    "meters": "read_meters", "meter_features": "read_meters",
    "add_flow": "write_flows", "render_add_flow": "write_flows",
    "modify_flow_strict": "write_flows", "render_modify_flow_strict": "write_flows",
    "delete_flow_strict": "delete_flows", "render_delete_flow_strict": "delete_flows",
    "add_meter": "write_meters", "render_add_meter": "write_meters",
    "delete_meter": "write_meters", "render_delete_meter": "write_meters",
}


class ControllerDriver:
    """The interface every controller driver implements. A subclass declares `kind`, `label`,
    `capabilities` and `status`, and implements the `_`-prefixed hooks of what it declares;
    the public calls here gate each on its capability, bound it, and turn anything it raises
    into an answer. A subclass never overrides a public call."""

    kind: str = ""
    label: str = ""
    capabilities: frozenset = frozenset()
    status: str = "later"
    #: A later driver whose reads come before any write.
    read_first: bool = False
    #: What a driver not yet built is meant to offer when it is (informational: Mercury offers
    #: only `capabilities`).
    planned: frozenset = frozenset()
    #: capability -> why this driver lacks it, said in its refusal.
    absent: Mapping = {}
    #: (method, path prefix) -> the capability a write path needs; `apply` sends nothing else.
    write_routes: Mapping = {}
    #: Where the controller's own link discovery sends LLDP (`read_topology`, S14): the prefix
    #: its chassis id carries before the DPID's sixteen hex digits, so a neighbouring device's
    #: LLDP names the switch (`sdn.topology.chassis_dpid`); "" when it sends none Mercury reads.
    lldp_chassis_prefix: str = ""
    #: What an empty link list may mean for this controller, said beside it (never "no cables"
    #: when the controller may simply not be discovering links).
    links_note: str = ""

    def __init__(self, connection: Connection, *, session=None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.connection = connection
        self._session_given = session
        self._session_built = None
        self._clock = clock
        self._sleep = sleep

    def __repr__(self) -> str:
        url = self.connection.base_url if isinstance(self.connection, Connection) else "?"
        return f"<{type(self).__name__} {self.kind} {url}>"

    # ── the declaration, read whole ─────────────────────────────────────────────────────────

    @classmethod
    def declaration(cls) -> dict:
        return {"kind": cls.kind, "label": cls.label, "status": cls.status,
                "read_first": cls.read_first, "capabilities": sorted(cls.capabilities),
                "planned": sorted(cls.planned),
                "absent": {k: cls.absent[k] for k in sorted(cls.absent)}}

    @classmethod
    def declaration_problems(cls) -> list:
        """What is wrong with this class's declaration, in words (the registry's test)."""
        out = []
        if not cls.kind or not cls.label:
            out.append(f"{cls.__name__} names no kind or label")
        if cls.status not in STATUSES:
            out.append(f"{cls.kind}: status {cls.status!r} is not one of {STATUSES}")
        for name, caps in (("capabilities", cls.capabilities), ("planned", cls.planned)):
            if not isinstance(caps, frozenset) or not caps <= CAPABILITIES:
                out.append(f"{cls.kind}: {name} {caps!r} is not a frozenset of "
                           f"{sorted(CAPABILITIES)}")
        if cls.status != "built" and cls.capabilities:
            out.append(f"{cls.kind} is {cls.status}, so it declares no capability")
        if cls.read_first and cls.status != "later":
            out.append(f"{cls.kind}: read_first is a later driver's")
        if set(cls.absent) & set(cls.capabilities):
            out.append(f"{cls.kind}: declares as absent what it declares")
        return out

    # ── the calls ──────────────────────────────────────────────────────────────────────────

    def test(self) -> dict:
        """Whether the controller answers, and its version where it reports one."""
        return self._call("test", self._test)

    def switches(self) -> dict:
        """`{"switches": [{"dpid", "dpid_hex"}]}`: the switches connected to the controller."""
        return self._call("switches", self._switches)

    def switch_desc(self, dpid) -> dict:
        """`{"dpid", "desc"}`: what a switch says it is."""
        return self._call("switch_desc", self._switch_desc, dpid, dpid_arg=True)

    def links(self) -> dict:
        """`{"links": [{"src": port, "dst": port}]}`: the links between switches the controller
        knows, each direction as it reports it."""
        return self._call("links", self._links)

    def hosts(self) -> dict:
        """`{"hosts": [topo_host], "hosts_note"}`: the hosts the controller learned, each on
        the switch port it learned it on."""
        return self._call("hosts", self._hosts)

    def topology(self) -> dict:
        """`{"switches": [{"dpid", "dpid_hex", "ports"}], "links", "hosts", "hosts_note"}`:
        one read of the controller's whole topology."""
        return self._call("topology", self._topology)

    def flows(self, dpid) -> dict:
        """`{"dpid", "flows": [Flow.as_dict()]}`: a switch's whole flow table."""
        return self._call("flows", self._flows, dpid, dpid_arg=True)

    def port_stats(self, dpid) -> dict:
        """`{"dpid", "ports": [PortStats.as_dict()]}`."""
        return self._call("port_stats", self._port_stats, dpid, dpid_arg=True)

    def meters(self, dpid) -> dict:
        """`{"dpid", "meters": [Meter.as_dict()]}`: each meter's configuration and counters."""
        return self._call("meters", self._meters, dpid, dpid_arg=True)

    def meter_features(self, dpid) -> dict:
        """`{"dpid", "features": MeterFeatures.as_dict() or None}`."""
        return self._call("meter_features", self._meter_features, dpid, dpid_arg=True)

    def render_add_flow(self, dpid, spec) -> dict:
        return self._call("render_add_flow", self._render_add_flow, dpid, spec,
                          io=False, dpid_arg=True)

    def render_modify_flow_strict(self, dpid, spec) -> dict:
        """OFPFC_MODIFY_STRICT: the flow with exactly this match and priority in this table
        has its instructions replaced; what else the switch keeps of it is the switch's (read
        back: `flow_ops.MODIFY_KEEPS`)."""
        return self._call("render_modify_flow_strict", self._render_modify_flow_strict, dpid,
                          spec, io=False, dpid_arg=True)

    def render_delete_flow_strict(self, dpid, spec) -> dict:
        return self._call("render_delete_flow_strict", self._render_delete_flow_strict, dpid,
                          spec, io=False, dpid_arg=True)

    def render_add_meter(self, dpid, spec) -> dict:
        return self._call("render_add_meter", self._render_add_meter, dpid, spec, io=False,
                          dpid_arg=True)

    def render_delete_meter(self, dpid, spec) -> dict:
        return self._call("render_delete_meter", self._render_delete_meter, dpid, spec,
                          io=False, dpid_arg=True)

    def add_flow(self, dpid, spec) -> dict:
        return self._write(self.render_add_flow(dpid, spec))

    def modify_flow_strict(self, dpid, spec) -> dict:
        return self._write(self.render_modify_flow_strict(dpid, spec))

    def delete_flow_strict(self, dpid, spec) -> dict:
        return self._write(self.render_delete_flow_strict(dpid, spec))

    def add_meter(self, dpid, spec) -> dict:
        return self._write(self.render_add_meter(dpid, spec))

    def delete_meter(self, dpid, spec) -> dict:
        return self._write(self.render_delete_meter(dpid, spec))

    def apply(self, rendered: Mapping) -> dict:
        """THE send path for a write: exactly *rendered*'s method, path and body text, which a
        render twin answered (and a confirm hashed). Only this driver's write routes, each
        under the capability it needs."""
        if not isinstance(rendered, Mapping) or not rendered.get("ok"):
            return {"ok": False, "error": "apply needs a rendered request (a render_* answer "
                                          "that is ok)"}
        method, path, body = rendered.get("method"), rendered.get("path"), rendered.get("body")
        capability = self.write_routes.get((method, path))
        if capability is None:
            return {"ok": False, "error": f"{self.label} has no write {method} {path}"}
        if not isinstance(body, str):
            return {"ok": False, "error": "a rendered body is the exact text to send"}
        return self._call("apply", self._apply, method, path, body, capability=capability)

    # ── what a driver implements (only what it declares is reached) ──────────────────────────

    def _not_implemented(self, *_args):
        raise NotImplementedError(f"{self.kind} declares this call but does not implement it")

    _test = _switches = _switch_desc = _links = _flows = _port_stats = _not_implemented
    _hosts = _topology = _not_implemented
    _meters = _meter_features = _not_implemented
    _render_add_flow = _render_modify_flow_strict = _render_delete_flow_strict = _not_implemented
    _render_add_meter = _render_delete_meter = _not_implemented

    def _apply(self, method, path, body) -> dict:
        """Send one write; the driver reads the answer (`_write_answer`)."""
        got = self._http(method, path, body=body)
        if not got.get("ok"):
            return got
        return self._write_answer(method, path, body, got)

    def _write_answer(self, method, path, body, got) -> dict:
        if 200 <= got["status"] < 300:
            return {"ok": True, "error": "", "status": got["status"]}
        return {"ok": False, "error": f"HTTP {got['status']}", "status": got["status"]}

    # ── the gate, the bound and the answer ──────────────────────────────────────────────────

    def _write(self, rendered) -> dict:
        """A write is its render, applied: the one way a body reaches the controller."""
        if not rendered.get("ok"):
            return rendered
        out = self.apply(rendered)
        out["request"] = {k: rendered[k] for k in ("method", "path", "body")}
        out["digest"] = request_digest(rendered)
        return self._scrub(out)

    def _call(self, name, hook, *args, io=True, dpid_arg=False, capability="") -> dict:
        try:
            refused = self._refusal(name, capability, io)
            if refused:
                return self._scrub({"ok": False, "error": refused, "refused": True})
            if dpid_arg:
                try:
                    args = (parse_dpid(args[0]),) + tuple(args[1:])
                except SpecError as exc:
                    return self._scrub({"ok": False, "error": str(exc)})
            out = hook(*args)
            if not isinstance(out, dict) or not isinstance(out.get("ok"), bool):
                out = {"ok": False, "error": f"{self.label}'s {name} answered no result"}
            out.setdefault("error", "")
        except SpecError as exc:                      # a spec refused, in its words
            out = {"ok": False, "error": str(exc)}
        except Exception as exc:                      # noqa: BLE001 - a call never raises
            log.warning("sdn %s: %s failed: %s", self.kind, name, type(exc).__name__)
            out = {"ok": False, "error": f"{name} failed: {type(exc).__name__}: {exc}"}
        return self._scrub(out)

    def _refusal(self, name, capability, io) -> str:
        if self.status != "built":
            return (f"the {self.label} driver is not built (status: {self.status}), so "
                    f"{name} is not available")
        needed = capability if capability else CALL_CAPABILITY.get(name)
        if needed and needed not in self.capabilities:
            why = self.absent.get(needed, "")
            return (f"{self.label} does not declare {needed}, so {name} is refused"
                    + (f": {why}" if why else ""))
        if io:
            return connection_problem(self.connection)
        return ""

    def _credentials(self) -> Mapping:
        source = self.connection.credentials if isinstance(self.connection, Connection) else None
        if source is None:
            return {}
        got = source()
        if got is None:
            return {}
        if not isinstance(got, Mapping):
            raise TypeError("the connection's credentials answered no mapping")
        return got

    def _credential_values(self) -> list:
        """The secret values (every credential but the user's name, which names, not opens)."""
        try:
            values = [v for k, v in self._credentials().items()
                      if k != "username" and isinstance(v, str) and v]
        except Exception:                             # noqa: BLE001 - nothing to scrub by value
            return []
        return sorted(values, key=len, reverse=True)

    def _scrub(self, answer):
        """Every string in *answer* with each credential value replaced, then masked as every
        service's words are (`redact_text`, by position and by known value): an error's words
        and anything else the controller sent, a switch's description or a flow's field, since
        a URL with its user part can arrive in any of them (the masking scan,
        tests/test_url_userinfo_masked.py, found a list's strings unmasked)."""
        from modules.redact import redact_text

        values = [v for v in self._credential_values() if len(v) >= MIN_SCRUBBED]

        def walk(node):
            if isinstance(node, str):
                for value in values:
                    node = node.replace(value, "<redacted>")
                return redact_text(node) if node else node
            if isinstance(node, dict):
                return {k: walk(v) for k, v in node.items()}
            if isinstance(node, list):
                return [walk(v) for v in node]
            return node

        return walk(answer)

    # ── HTTP: one session, one deadline ─────────────────────────────────────────────────────

    def _session(self):
        if self._session_given is not None:
            return self._session_given
        if self._session_built is None:
            s = requests.Session()
            s.headers.update({"Accept": "application/json"})
            self._session_built = s
        return self._session_built

    def _auth(self):
        """`(headers, auth)` for one request, from the credentials callable, never kept."""
        creds = self._credentials()
        if creds.get("token"):
            return {"Authorization": f"Bearer {creds['token']}"}, None
        if creds.get("username") or creds.get("password"):
            return {}, (creds.get("username", ""), creds.get("password", ""))
        return {}, None

    def _http(self, method, path, body=None) -> dict:
        """One request against the connection's deadline: `{"ok": True, "status", "text",
        "content_type"}` for any HTTP answer, else `{"ok": False, "error"}`. A read is retried
        after a connection error or a 502/503/504 while the deadline allows; a write never."""
        timeout = float(self.connection.timeout)
        deadline = self._clock() + timeout
        url = self.connection.base_url + path
        attempts = READ_ATTEMPTS if method == "GET" else 1
        try:
            headers, auth = self._auth()
        except Exception as exc:                      # noqa: BLE001
            return {"ok": False, "error": "the controller's credentials could not be read "
                                          f"({type(exc).__name__})"}
        headers = dict(headers, Accept="application/json")
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = body.encode("utf-8")
        last = ""
        for attempt in range(1, attempts + 1):
            remaining = deadline - self._clock()
            if remaining <= 0:
                return {"ok": False, "error": f"no answer within {timeout:g} s"
                                              + (f" ({last})" if last else ""),
                        "timeout": True, "attempts": attempt - 1}
            try:
                response = self._session().request(
                    method, url, data=data, headers=headers, auth=auth,
                    timeout=(remaining, remaining), verify=self.connection.verify_tls,
                    allow_redirects=False, stream=True)
                try:
                    text = self._read(response, deadline)
                finally:
                    close = getattr(response, "close", None)
                    if close:
                        close()
            except requests.exceptions.SSLError as exc:
                return {"ok": False, "error": f"TLS error: {exc}", "attempts": attempt}
            except (requests.exceptions.Timeout, _Deadline):
                return {"ok": False, "error": f"no answer within {timeout:g} s",
                        "timeout": True, "attempts": attempt}
            except _TooLarge:
                return {"ok": False, "error": f"the answer is larger than {MAX_BODY_BYTES} "
                                              "bytes, so it was not read",
                        "attempts": attempt}
            except requests.exceptions.ConnectionError:
                last = f"could not connect to {self.connection.base_url}"
                if attempt < attempts and self._pause(deadline):
                    continue
                return {"ok": False, "error": last, "attempts": attempt}
            status = response.status_code
            if status in (502, 503, 504) and attempt < attempts and self._pause(deadline):
                last = f"HTTP {status}"
                continue
            content_type = ((getattr(response, "headers", None) or {}).get("Content-Type")
                            or "")
            if 300 <= status < 400:
                return {"ok": False, "status": status, "attempts": attempt,
                        "error": f"HTTP {status}: the controller answered a redirect (to "
                                 f"{(response.headers or {}).get('Location', '?')}); set "
                                 "the URL it names"}
            return {"ok": True, "status": status, "text": text,
                    "content_type": content_type.lower(), "attempts": attempt}
        return {"ok": False, "error": last or "no answer", "attempts": attempts}

    def _pause(self, deadline) -> bool:
        """Wait before a retry if the deadline leaves room for it and an attempt after it."""
        if deadline - self._clock() <= RETRY_PAUSE:
            return False
        self._sleep(RETRY_PAUSE)
        return True

    def _read(self, response, deadline) -> str:
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            if self._clock() > deadline:
                raise _Deadline()
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                raise _TooLarge()
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")
