"""Flow intent: every flow Mercury installs on an SDN controller, what Mercury expects of it, and
whose each installed flow is (PHASE8_PLAN 17.1 S5). Deterministic; no AI.

**Mercury's cookie.** Every flow Mercury installs carries a cookie whose high 16 bits are
`PREFIX` (``0x4d45``, "ME") and whose low 48 bits are the flow's id (`mercury_cookie`,
`new_cookie`). A controller application's own flows carry its own cookies (each connection
declares them, `[0]` by default: the operator's decision, 2026-10-27), which may never fall in
Mercury's range (`connections.check` refuses one).

**The store** (`flow_intent`, a records store as Mercury's others are: `records_migrate`'s line
store, one file per network, `flow_intent.jsonl` in the network's folder, or the records
database once moved; `records_store_flow_intent`): append-only, one line per event:
- ``installed``: the cookie, the connection and switch, the expected table, priority, match
  (OpenFlow 1.3 OXM names), actions (the drivers' one shape) and timeouts, who installed it and
  when (``installed_at``, Mercury's clock at the install), and the response that installed it;
- ``withdrawn``: Mercury removed it (a rollback, a removal), who, when and why; it is then no
  longer expected;
- ``amended``: Mercury edited it in place (modify-strict keeps the cookie): its new actions or
  timeouts, who, when and why;
- ``meter`` and ``meter_withdrawn``: a meter Mercury added on a switch (its id, flags and
  bands, and when Mercury removes it: a meter has no timeout of its own), and its removal;
- ``operation``: one flow operation's whole run (`flow_ops.apply`): its requests and their
  hash, who confirmed it, each answer, Verify's checks, the rollback and the outcome, which
  History reads.
Each append holds the store's cross-process lock across its read (a cookie is recorded once)
and its write (`records_migrate.store_append`, owner-only, a line at a time).

**Whose each installed flow is** (`classify`):
- ``mercury``: its cookie is recorded (installed, not withdrawn) for this connection, and its
  switch, table, priority, match and actions are the record's;
- ``mercury_differs``: recorded, and one of those is not the record's, each difference named
  with both values;
- ``controller_own``: its cookie is one the connection declares as its application's own;
- ``unauthorised``: anything else (an unknown cookie; Mercury's prefix with no record, a record
  withdrawn, or another connection's record), reported like an intent departure.
And each recorded flow not installed: ``expired`` when its hard timeout, as set, has passed
since it was installed (not a fault: the switch removed it as asked), else ``missing``. Only a
switch whose table was read whole is judged; a record on any other switch is ``not_judged``,
never missing (absent and unread are different).

**What an unauthorised flow displaced and what it does** (C2004, C2021; deterministic, from the
switch's table as read, never the model's inference):
- `displaced`: the Mercury records an unauthorised flow took the place of: each recorded on its
  switch and ``missing`` (not installed, not expired) at the same table, priority and match
  (`flow_ops._same_place`), which an OpenFlow add with that match and priority replaces;
- `effect`: one of `EFFECTS`, in words and as a field, with the flows it rests on.
  ``lifts`` when it displaced a Mercury drop or meter, or sits above an installed one taking its
  traffic, and does not keep it (it outputs where Mercury's dropped; it lacks Mercury's meter);
  ``shadows`` when it does so to a Mercury flow with other actions; else, compared with the flow
  below it that would take each part of its traffic without it (the highest flow below whose
  match overlaps its own, no single flow above that one covering the overlap), where that flow
  is the controller application's own or Mercury's as recorded: ``drops`` when it has no
  output; ``diverts`` when any such flow outputs elsewhere; ``forwards`` when every such flow
  outputs where it does, rewriting the same. ``unknown`` when the table cannot tell: a flow above
  it takes all its traffic first; it continues to another table, a group, or an action Mercury
  could not read; it rewrites the packet where the controller's flow does not; or no flow below
  it decides its traffic but the table-miss (which asks the controller), a flow at its own
  priority (OpenFlow leaves the order undefined) or another flow not authorised. A part of its
  traffic decided only by the table-miss is named as the controller's to decide. Whether a
  higher flow takes a part is judged one flow at a time, never by a union of several.

SDN › Flows draws `classify`'s answer as the SDN reader stored it
(`modules/readers/sdn_controllers.py`), each record with its ``expires_at``; a response's
flows or meter (`meter_records`) missing while their hard timeout has time left are a Needs
attention row (`attention.sdn_mitigation_source`, C2018) and its Re-apply…
(`modules/sdn/reapply.py`).
"""

import ipaddress
import json
import logging
import os
import secrets
import time

log = logging.getLogger(__name__)

STORE = "flow_intent"
FILE_NAME = "flow_intent.jsonl"
#: Mercury's cookie: "ME" in the high 16 bits, the flow's id in the low 48.
PREFIX = 0x4D45
SHIFT = 48
ID_MASK = (1 << SHIFT) - 1
STATES = ("mercury", "mercury_differs", "controller_own", "unauthorised")
RECORD_STATES = ("missing", "expired", "not_judged")
#: What a flow's record holds of it, compared with what is installed.
COMPARED = ("dpid", "table_id", "priority", "match", "actions")


class IntentRefused(ValueError):
    """A flow-intent record refused, in words naming why."""


# ───────────────────────────────────────────────────────────────────────────── the cookie

def mercury_cookie(fid: int) -> int:
    """The cookie of Mercury's flow *fid* (1 to 2^48-1)."""
    if isinstance(fid, bool) or not isinstance(fid, int) or not 0 < fid <= ID_MASK:
        raise IntentRefused(f"a Mercury flow id is from 1 to 2^48-1, not {fid!r}")
    return (PREFIX << SHIFT) | fid


def is_mercury(cookie) -> bool:
    """Whether *cookie* is in Mercury's range (its high 16 bits are `PREFIX`)."""
    return (isinstance(cookie, int) and not isinstance(cookie, bool)
            and 0 <= cookie < 1 << 64 and cookie >> SHIFT == PREFIX
            and cookie & ID_MASK != 0)


def flow_id(cookie: int) -> int:
    return cookie & ID_MASK


def new_cookie() -> int:
    """A fresh Mercury cookie, its id drawn at random from 2^48 (so a preview can carry it
    before anything is recorded; `record_installed` refuses one already recorded)."""
    while True:
        drawn = secrets.randbits(SHIFT)
        if drawn:
            return mercury_cookie(drawn)


def cookie_hex(cookie) -> str:
    return f"{cookie:#018x}" if isinstance(cookie, int) and not isinstance(cookie, bool) \
        else str(cookie)


# ───────────────────────────────────────────────────────────────────────────── the store

def _network(network: str) -> str:
    """The store's network: the list's folder name, verbatim, as on disk (never re-slugged, as
    every store kept per network names it)."""
    return os.path.basename(os.path.dirname(_path(network)))


def _path(network: str) -> str:
    from modules.config import list_data_path

    return os.path.join(list_data_path(network), FILE_NAME)


def read(network: str) -> dict:
    """*network*'s records, oldest first: ``{"state": "ok"|"absent"|"unreadable", "rows",
    "error"}``. Absent (nothing installed yet) and unreadable are different answers."""
    from modules import records_migrate

    if not network:
        return {"state": "unreadable", "rows": [], "error": "no network was named"}
    got = records_migrate.store_rows(STORE, _path(network), network=_network(network))
    if got["state"] == "unreadable":
        log.error("flow_intent: %s's store is unreadable (%s)", network, got["error"])
    return got


def _active(rows: list) -> dict:
    """``{cookie: installed row}`` of every record installed and not withdrawn, each as its
    last amendment left it (an edit by modify-strict keeps the cookie and changes the actions
    or timeouts)."""
    out = {}
    for r in rows:
        if r.get("kind") == "installed":
            out[r.get("cookie")] = r
        elif r.get("kind") == "withdrawn":
            out.pop(r.get("cookie"), None)
        elif r.get("kind") == "amended" and r.get("cookie") in out:
            held = out[r.get("cookie")]
            if held.get("connection") == r.get("connection"):
                out[r.get("cookie")] = dict(held, **{k: r[k] for k in AMENDABLE if k in r},
                                            amended_at=r.get("at"))
    return out


#: What an amendment may change of a recorded flow (an edit by modify-strict).
AMENDABLE = ("actions", "idle_timeout", "hard_timeout", "installed_at")


def intent(network: str, connection: str = None) -> dict:
    """What Mercury expects installed on *network* (one *connection*'s when named):
    ``{"state", "flows": [installed rows], "withdrawn": {cookie: row}, "error"}``. Absent is
    ``ok`` with none expected; unreadable says so and expects nothing it could know."""
    got = read(network)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "flows": [], "withdrawn": {}, "error": got["error"]}
    active = _active(got["rows"])
    withdrawn = {r.get("cookie"): r for r in got["rows"] if r.get("kind") == "withdrawn"}
    flows = [r for r in active.values()
             if connection is None or r.get("connection") == connection]
    return {"state": "ok", "flows": flows, "withdrawn": withdrawn, "error": ""}


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _append(network: str, row: dict, check) -> dict:
    """Append *row* under the store's lock, after ``check(rows)`` (raising to refuse)."""
    from modules import records_migrate
    from modules.filestore import PathLock

    path = _path(network)
    with PathLock(lambda: path):
        got = read(network)
        if got["state"] == "unreadable":
            raise IntentRefused(f"{network}'s flow intent cannot be read ({got['error']}), so "
                                "nothing was recorded")
        check(got["rows"])
        records_migrate.store_append(STORE, path, row, network=_network(network))
    return row


def record_installed(network: str, *, connection: str, flow, actor: str, response,
                     actor_verified: str = "", at: float = None) -> dict:
    """Record a flow Mercury installed on *network*'s controller *connection*: *flow* a
    `Flow` or its mapping (its ``dpid`` the switch, its ``cookie`` Mercury's), *response* what
    installed it (the response's id and action, a mapping). Refuses a cookie outside Mercury's
    range, one already recorded, a flow the drivers' spec check refuses, or no actor. Answers
    the row recorded; raises `IntentRefused` naming why."""
    from modules.sdn.drivers.base import Flow, SpecError, flow_from_spec

    if not network or not connection:
        raise IntentRefused("a flow is recorded FOR a network and its connection; both are "
                            "named")
    if not actor:
        raise IntentRefused("a flow's record names who installed it, and no actor was given")
    values = flow.as_dict() if isinstance(flow, Flow) else dict(flow or {})
    spec = {k: v for k, v in values.items()
            if k not in ("packet_count", "byte_count", "duration_sec")}
    try:
        f = flow_from_spec(values.get("dpid"), spec)
    except SpecError as exc:
        raise IntentRefused(f"the flow is not one Mercury could have sent: {exc}") from None
    if not is_mercury(f.cookie):
        raise IntentRefused(f"cookie {cookie_hex(f.cookie)} is not Mercury's (its high 16 bits "
                            f"must be {PREFIX:#06x}): every flow Mercury installs carries one")
    if not isinstance(response, dict):
        raise IntentRefused("a flow's record names the response that installed it (a mapping)")
    at = time.time() if at is None else float(at)
    row = {"kind": "installed", "cookie": f.cookie, "cookie_hex": cookie_hex(f.cookie),
           "network": network, "connection": connection, "dpid": f.dpid,
           "table_id": f.table_id, "priority": f.priority, "match": dict(f.match),
           "actions": [dict(a) for a in f.actions], "idle_timeout": f.idle_timeout,
           "hard_timeout": f.hard_timeout, "installed_at": at, "at": _iso(at),
           "actor": actor, "actor_verified": actor_verified, "response": dict(response)}

    def unique(rows):
        held = [r for r in rows if r.get("kind") == "installed" and r.get("cookie") == f.cookie]
        if held:
            raise IntentRefused(f"cookie {cookie_hex(f.cookie)} is already recorded (installed "
                                f"{held[0].get('at')} on {held[0].get('connection')}); a "
                                "cookie names one flow, once")

    return _append(network, row, unique)


def record_withdrawn(network: str, cookie: int, *, connection: str, actor: str, why: str,
                     actor_verified: str = "", at: float = None) -> dict:
    """Record that Mercury removed its flow *cookie* (a rollback, a removal): it is then no
    longer expected. Refuses a cookie with no installed record on that connection, one already
    withdrawn, or no reason."""
    if not actor or not (why or "").strip():
        raise IntentRefused("a withdrawal names who made it and why")
    at = time.time() if at is None else float(at)
    row = {"kind": "withdrawn", "cookie": cookie, "cookie_hex": cookie_hex(cookie),
           "network": network, "connection": connection, "at": _iso(at), "withdrawn_at": at,
           "actor": actor, "actor_verified": actor_verified, "why": why.strip()}

    def held(rows):
        active = _active(rows).get(cookie)
        if active is None or active.get("connection") != connection:
            raise IntentRefused(f"cookie {cookie_hex(cookie)} has no flow recorded as installed "
                                f"on {connection} and not withdrawn; nothing was recorded")

    return _append(network, row, held)


def record_amended(network: str, cookie: int, *, connection: str, actor: str, why: str,
                   changes: dict, actor_verified: str = "", at: float = None) -> dict:
    """Record that Mercury edited its flow *cookie* in place (modify-strict keeps the cookie):
    *changes* the new ``actions`` and timeouts. Refuses a cookie with no installed record on
    that connection, a field an edit cannot change, or no reason."""
    if not actor or not (why or "").strip():
        raise IntentRefused("an amendment names who made it and why")
    unknown = sorted(set(changes or {}) - set(AMENDABLE))
    if unknown or not changes:
        raise IntentRefused(f"an amendment changes {', '.join(AMENDABLE)} only, not "
                            f"{', '.join(unknown) or 'nothing'}")
    at = time.time() if at is None else float(at)
    row = {"kind": "amended", "cookie": cookie, "cookie_hex": cookie_hex(cookie),
           "network": network, "connection": connection, "at": _iso(at), "amended_at": at,
           "actor": actor, "actor_verified": actor_verified, "why": why.strip(),
           **{k: v for k, v in changes.items()}}

    def held(rows):
        active = _active(rows).get(cookie)
        if active is None or active.get("connection") != connection:
            raise IntentRefused(f"cookie {cookie_hex(cookie)} has no flow recorded as installed "
                                f"on {connection} and not withdrawn; nothing was recorded")

    return _append(network, row, held)


# ───────────────────────────────────────────────────────────────────────────── meters

def record_meter(network: str, *, connection: str, dpid: int, meter: dict, actor: str,
                 response, expires_at: float = None, actor_verified: str = "",
                 at: float = None) -> dict:
    """Record a meter Mercury added on *connection*'s switch *dpid*: *meter* its id, flags and
    bands; *expires_at* when Mercury removes it (a meter has no timeout of its own in OpenFlow,
    so a response's meter is removed by Mercury once its flows have expired: `flow_ops.
    expire_meters`). Refuses a meter id already recorded on that switch and not withdrawn."""
    if not network or not connection or not actor:
        raise IntentRefused("a meter is recorded for a network and its connection, by someone")
    meter_id = (meter or {}).get("meter_id")
    at = time.time() if at is None else float(at)
    row = {"kind": "meter", "network": network, "connection": connection, "dpid": dpid,
           "meter_id": meter_id, "flags": list(meter.get("flags") or []),
           "bands": [dict(b) for b in meter.get("bands") or []], "at": _iso(at),
           "installed_at": at, "expires_at": expires_at, "actor": actor,
           "actor_verified": actor_verified, "response": dict(response or {})}

    def unique(rows):
        if _meter_key(row) in active_meters_of(rows):
            raise IntentRefused(f"meter {meter_id} on switch {dpid} ({connection}) is already "
                                "recorded as Mercury's")

    return _append(network, row, unique)


def record_meter_withdrawn(network: str, *, connection: str, dpid: int, meter_id: int,
                           actor: str, why: str, actor_verified: str = "",
                           at: float = None) -> dict:
    """Record that Mercury removed its meter (a rollback, an expiry, a removal)."""
    if not actor or not (why or "").strip():
        raise IntentRefused("a meter's withdrawal names who made it and why")
    at = time.time() if at is None else float(at)
    row = {"kind": "meter_withdrawn", "network": network, "connection": connection,
           "dpid": dpid, "meter_id": meter_id, "at": _iso(at), "withdrawn_at": at,
           "actor": actor, "actor_verified": actor_verified, "why": why.strip()}

    def held(rows):
        if _meter_key(row) not in active_meters_of(rows):
            raise IntentRefused(f"meter {meter_id} on switch {dpid} ({connection}) has no "
                                "record as Mercury's; nothing was recorded")

    return _append(network, row, held)


def _meter_key(row: dict) -> tuple:
    return (row.get("connection"), row.get("dpid"), row.get("meter_id"))


def active_meters_of(rows: list) -> dict:
    """``{(connection, dpid, meter_id): meter row}`` of Mercury's meters not withdrawn."""
    out = {}
    for r in rows:
        if r.get("kind") == "meter":
            out[_meter_key(r)] = r
        elif r.get("kind") == "meter_withdrawn":
            out.pop(_meter_key(r), None)
    return out


def meter_records(connection: str, dpid: int, read_ids, meter_rows: list,
                  now: float = None) -> list:
    """Mercury's recorded meters on *connection*'s switch *dpid* that the switch does not hold
    (C2018): *read_ids* the meter ids its read answered (None when its meters were not read:
    then each is ``not_judged``); *meter_rows* `meters()`'s. Each ``{"meter_id", "state",
    "expires_at", "response", "flags", "bands", "words"}``, *state* ``expired`` once its
    expiry (its response's flows' hard timeout) has passed, else ``missing``."""
    now = time.time() if now is None else now
    out = []
    for m in meter_rows or []:
        if m.get("connection") != connection or m.get("dpid") != dpid:
            continue
        if read_ids is not None and m.get("meter_id") in set(read_ids):
            continue
        base = {"meter_id": m.get("meter_id"), "expires_at": m.get("expires_at"),
                "response": m.get("response") or {}, "flags": m.get("flags") or [],
                "bands": m.get("bands") or [], "installed_at": m.get("at")}
        exp = m.get("expires_at")
        if read_ids is None:
            out.append(dict(base, state="not_judged",
                            words=f"switch {dpid}'s meters were not read, so whether meter "
                                  f"{m.get('meter_id')} is there is not known"))
        elif isinstance(exp, (int, float)) and now >= exp:
            out.append(dict(base, state="expired",
                            words=f"its response's flows expired at {_iso(exp)}"))
        else:
            out.append(dict(base, state="missing",
                            words=f"meter {m.get('meter_id')} is recorded as added by Mercury "
                                  "and the switch does not hold it"))
    return out


def meters(network: str) -> dict:
    """Mercury's meters on *network*: ``{"state", "meters": [rows], "error"}``."""
    got = read(network)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "meters": [], "error": got["error"]}
    return {"state": "ok", "meters": list(active_meters_of(got["rows"]).values()), "error": ""}


# ───────────────────────────────────────────────────────────────────────────── operations

def record_operation(network: str, row: dict) -> dict:
    """Record one flow operation's whole run (`flow_ops.apply`): what was previewed, its hash,
    who confirmed it and how, each request and its answer, Verify's checks, the rollback and
    the outcome. History reads these (`history_sources.sdn_operations`)."""
    row = dict(row, kind="operation", network=network)
    if not row.get("id") or not row.get("actor"):
        raise IntentRefused("an operation's record names its id and who confirmed it")
    return _append(network, row, lambda rows: None)


def operations(network: str) -> dict:
    """*network*'s operation records, oldest first: ``{"state", "rows", "error"}``."""
    got = read(network)
    if got["state"] == "unreadable":
        return {"state": "unreadable", "rows": [], "error": got["error"]}
    return {"state": got["state"], "rows": [r for r in got["rows"]
                                            if r.get("kind") == "operation"], "error": ""}


# ───────────────────────────────────────────────────────────────────────────── comparing

_INT_FIELDS = frozenset({"in_port", "in_phy_port", "eth_type", "vlan_vid", "vlan_pcp", "ip_dscp",
                         "ip_ecn", "ip_proto", "tcp_src", "tcp_dst", "udp_src", "udp_dst",
                         "sctp_src", "sctp_dst", "icmpv4_type", "icmpv4_code", "arp_op",
                         "icmpv6_type", "icmpv6_code", "mpls_label", "mpls_tc", "mpls_bos",
                         "ipv6_flabel", "pbb_isid", "tunnel_id", "metadata", "ipv6_exthdr"})
_ADDRESS_FIELDS = frozenset({"ipv4_src", "ipv4_dst", "arp_spa", "arp_tpa", "ipv6_src",
                             "ipv6_dst", "ipv6_nd_target"})
_MAC_FIELDS = frozenset({"eth_src", "eth_dst", "arp_sha", "arp_tha", "ipv6_nd_sll",
                         "ipv6_nd_tll"})


def _prefix_len(mask: str):
    """A mask written as a prefix length or as a contiguous address mask, as a prefix length;
    None for a mask that is not contiguous."""
    if mask.isdigit():
        return int(mask)
    try:
        m = ipaddress.ip_address(mask)
    except ValueError:
        return None
    bits = m.max_prefixlen
    value = int(m)
    length = bin(value).count("1")
    return length if value == ((1 << length) - 1) << (bits - length) else None


def _address(value: str) -> str:
    """An address or a masked address in one canonical form (its prefix length), so a record
    written with a dotted mask and a switch's read of it with a prefix length compare equal.
    A mask that is not contiguous is kept as written, lower-cased."""
    text = str(value).strip().lower()
    address, slash, mask = text.partition("/")
    try:
        if not slash:
            return ipaddress.ip_address(address).compressed
        length = _prefix_len(mask)
        if length is None:
            return text
        net = ipaddress.ip_network(f"{address}/{length}", strict=False)
        full = net.max_prefixlen
        return net.network_address.compressed if length == full else net.compressed
    except ValueError:
        return text


def _value(field: str, value):
    if field in _INT_FIELDS and isinstance(value, str):
        try:
            return int(value.strip(), 0)
        except ValueError:
            return value
    if field in _ADDRESS_FIELDS and isinstance(value, str):
        return _address(value)
    if field in _MAC_FIELDS and isinstance(value, str):
        return value.strip().lower()
    return value


def normal_match(match: dict) -> dict:
    return {k: _value(k, v) for k, v in sorted((match or {}).items())}


def _action(action: dict) -> dict:
    a = dict(action)
    if a.get("type") == "OUTPUT" and isinstance(a.get("port"), str) and a["port"].isdigit():
        a["port"] = int(a["port"])
    if a.get("type") == "SET_FIELD":
        a["value"] = _value(a.get("field"), a.get("value"))
    if a.get("type") == "WRITE_ACTIONS":
        a["actions"] = [_action(x) for x in a.get("actions") or []]
    return a


def normal_actions(actions: list) -> tuple:
    """``(instructions, apply-actions)``: the instructions (meter, goto, write-actions,
    metadata) as a set, since a switch reports them in its own order, and the apply-actions in
    order, since their order is what they do."""
    from modules.sdn.drivers.base import INSTRUCTION_TYPES

    actions = [_action(a) for a in actions or []]
    instructions = sorted(json.dumps(a, sort_keys=True) for a in actions
                          if a.get("type") in INSTRUCTION_TYPES)
    applied = [json.dumps(a, sort_keys=True) for a in actions
               if a.get("type") not in INSTRUCTION_TYPES]
    return tuple(instructions), tuple(applied)


def action_words(actions: list) -> str:
    """Actions as a person reads them (`METER:1, OUTPUT:2`; `drop` for none)."""
    if not actions:
        return "drop"
    out = []
    for a in actions:
        fields = [v for k, v in a.items() if k != "type"]
        if a.get("type") == "WRITE_ACTIONS":
            out.append(f"WRITE_ACTIONS[{action_words(a.get('actions') or [])}]")
        elif a.get("type") == "SET_FIELD":
            out.append(f"SET_FIELD:{a.get('field')}={a.get('value')}")
        else:
            out.append(a.get("type", "?") + (":" + ",".join(map(str, fields)) if fields else ""))
    return ", ".join(out)


def differences(record: dict, flow: dict) -> list:
    """What of *flow* (installed) is not *record*'s (expected): ``[{"field", "expected",
    "installed", "words"}]``, a match field by field; empty when it is the record."""
    out = []

    def say(field, expected, installed, words):
        out.append({"field": field, "expected": expected, "installed": installed,
                    "words": words})

    if record.get("dpid") != flow.get("dpid"):
        say("dpid", record.get("dpid"), flow.get("dpid"),
            f"on switch {flow.get('dpid')}, recorded for switch {record.get('dpid')}")
    for field in ("table_id", "priority"):
        if record.get(field) != flow.get(field):
            say(field, record.get(field), flow.get(field),
                f"{field} {flow.get(field)}, recorded {record.get(field)}")
    want, have = normal_match(record.get("match")), normal_match(flow.get("match"))
    for key in sorted(set(want) | set(have)):
        if want.get(key) != have.get(key):
            say(f"match.{key}", want.get(key), have.get(key),
                f"match {key}: installed "
                f"{have[key] if key in have else 'not matched'}, recorded "
                f"{want[key] if key in want else 'not matched'}")
    if normal_actions(record.get("actions")) != normal_actions(flow.get("actions")):
        say("actions", record.get("actions"), flow.get("actions"),
            f"actions: installed {action_words(flow.get('actions'))}, recorded "
            f"{action_words(record.get('actions'))}")
    return out


# ───────────────────────────────────────────────────────────────────────────── classifying

def classify(flows: list, connection: dict, intent_rows: list, *, read_switches=None,
             withdrawn: dict = None, now: float = None) -> dict:
    """Whose each installed flow is, and which recorded flows are not installed.

    *flows*: the flows read from *connection*'s switches (the drivers' one shape, each with its
    ``dpid``); *connection*: the connection (its ``name`` and ``own_cookies``); *intent_rows*:
    the installed records (`intent()`'s ``flows``); only those for this connection count.
    *read_switches*: the switches whose tables were read whole (default: those *flows* came
    from); a record on any other is ``not_judged``. *withdrawn*: `intent()`'s, so a flow
    Mercury withdrew and still installed is named as such. *now*: the clock a hard timeout is
    judged by (Mercury's).

    ``{"connection", "flows": [flow + {"owner", "differs", "words", "record"}], "records":
    [{"cookie", "state", "words", ...}], "counts"}``. *intent_rows* may be `intent()`'s whole
    answer: an unreadable one classifies nothing and says so (``state`` ``unreadable``), since
    without the records no flow can be called Mercury's or unauthorised."""
    if isinstance(intent_rows, dict):
        if intent_rows.get("state") != "ok":
            return {"connection": (connection or {}).get("name"), "state": "unreadable",
                    "error": f"the flow intent could not be read "
                             f"({intent_rows.get('error') or 'no reason given'}), so no flow "
                             "was classified", "flows": [], "records": [], "counts": {}}
        withdrawn = intent_rows.get("withdrawn") if withdrawn is None else withdrawn
        intent_rows = intent_rows.get("flows") or []
    name = (connection or {}).get("name")
    own = set((connection or {}).get("own_cookies") or [])
    now = time.time() if now is None else now
    records = {r.get("cookie"): r for r in intent_rows or []
               if r.get("kind", "installed") == "installed" and r.get("connection") == name}
    others = {r.get("cookie"): r for r in intent_rows or [] if r.get("connection") != name}
    withdrawn = withdrawn or {}
    judged = set(read_switches) if read_switches is not None else \
        {f.get("dpid") for f in flows or []}
    seen = set()
    out_flows = []
    for flow in flows or []:
        cookie = flow.get("cookie")
        record = records.get(cookie)
        row = dict(flow)
        if record is not None:
            seen.add(cookie)
            diff = differences(record, flow)
            row.update(owner="mercury_differs" if diff else "mercury", differs=diff,
                       record=cookie_hex(cookie),
                       words=("Mercury's, as recorded" if not diff else
                              "Mercury's, and not as recorded: "
                              + "; ".join(d["words"] for d in diff)))
        elif cookie in own:
            row.update(owner="controller_own", differs=[], record=None,
                       words=f"the controller's own (cookie {cookie_hex(cookie)} is declared "
                             f"as its application's on {name})")
        else:
            why = f"cookie {cookie_hex(cookie)} is neither Mercury's nor declared as the " \
                  f"controller's own on {name}"
            if cookie in withdrawn:
                why = (f"Mercury's cookie {cookie_hex(cookie)}, withdrawn "
                       f"{withdrawn[cookie].get('at')} ({withdrawn[cookie].get('why')}), and "
                       "still installed")
            elif cookie in others:
                why = (f"Mercury's cookie {cookie_hex(cookie)} is recorded for "
                       f"{others[cookie].get('connection')}, not {name}")
            elif is_mercury(cookie):
                why = f"it carries Mercury's prefix, but cookie {cookie_hex(cookie)} has no record"
            row.update(owner="unauthorised", differs=[], record=None, words=why)
        out_flows.append(row)
    out_records = []
    for cookie, record in sorted(records.items(), key=lambda kv: str(kv[0])):
        if cookie in seen:
            continue
        base = {"cookie": cookie, "cookie_hex": cookie_hex(cookie), "dpid": record.get("dpid"),
                "table_id": record.get("table_id"), "priority": record.get("priority"),
                "match": record.get("match"), "actions": record.get("actions"),
                "installed_at": record.get("at"), "hard_timeout": record.get("hard_timeout"),
                "idle_timeout": record.get("idle_timeout"), "response": record.get("response")}
        hard = record.get("hard_timeout") or 0
        installed_at = record.get("installed_at")
        # When its hard timeout ends (Mercury's clock), so a reader of the stored answer judges
        # the time left at its own moment (C2018); None for a flow with no hard timeout.
        base["expires_at"] = (installed_at + hard if hard and isinstance(installed_at,
                                                                         (int, float))
                              else None)
        if record.get("dpid") not in judged:
            out_records.append(dict(base, state="not_judged",
                                    words=f"switch {record.get('dpid')}'s table was not read, "
                                          "so whether it is installed is not known"))
        elif hard and isinstance(installed_at, (int, float)) and now >= installed_at + hard:
            out_records.append(dict(base, state="expired",
                                    words=f"expired at its hard timeout ({hard} s, as set), "
                                          f"{_iso(installed_at + hard)}: removed as asked"))
        else:
            idle = record.get("idle_timeout") or 0
            out_records.append(dict(base, state="missing",
                                    words="recorded as installed by Mercury and not installed"
                                          + (f" (its idle timeout of {idle} s may have removed "
                                             "it)" if idle else "")))
    counts = {s: 0 for s in STATES + RECORD_STATES}
    for f in out_flows:
        counts[f["owner"]] += 1
    for r in out_records:
        counts[r["state"]] += 1
    return {"connection": name, "state": "ok", "error": "", "flows": out_flows,
            "records": out_records, "counts": counts}


# ─────────────────────────────────────────── what an unauthorised flow displaced and does

#: An unauthorised flow's effect on the traffic it takes (`effect`; C2021).
EFFECTS = ("forwards", "diverts", "drops", "shadows", "lifts", "unknown")
#: The most flows an effect's words name (and its evidence holds) per list; the rest counted.
EFFECT_NAMED = 3
#: A field matched with no mask: every bit, wider than any OpenFlow 1.3 field (IPv6's 128).
_ALL_BITS = (1 << 128) - 1
_IPV4, _ARP, _IPV6 = ("eth_type", 0x0800), ("eth_type", 0x0806), ("eth_type", 0x86DD)
#: Each field's prerequisites, implied where a match leaves them out (OpenFlow 1.3.5's table of
#: match field prerequisites): an IPv4 address is matched only on IPv4, a TCP port only on
#: TCP, so a flow matching ``ipv4_dst`` alone does not overlap one matching ``eth_type`` 0x86dd.
_PREREQUISITES = {
    **{f: (_IPV4,) for f in ("ipv4_src", "ipv4_dst")},
    **{f: (_ARP,) for f in ("arp_op", "arp_spa", "arp_tpa", "arp_sha", "arp_tha")},
    **{f: (_IPV6,) for f in ("ipv6_src", "ipv6_dst", "ipv6_flabel", "ipv6_exthdr",
                             "ipv6_nd_target", "ipv6_nd_sll", "ipv6_nd_tll")},
    **{f: (("ip_proto", 6),) for f in ("tcp_src", "tcp_dst")},
    **{f: (("ip_proto", 17),) for f in ("udp_src", "udp_dst")},
    **{f: (("ip_proto", 132),) for f in ("sctp_src", "sctp_dst")},
    **{f: (("ip_proto", 1), _IPV4) for f in ("icmpv4_type", "icmpv4_code")},
    **{f: (("ip_proto", 58), _IPV6) for f in ("icmpv6_type", "icmpv6_code")},
}
_OWNER_WORDS = {"controller_own": "the controller's own flow", "mercury": "Mercury's flow",
                "mercury_differs": "Mercury's flow, not as recorded",
                "unauthorised": "another unauthorised flow"}


class _CannotTell(ValueError):
    """A match whose overlap with another cannot be computed, in words."""


def _int(text) -> int:
    text = str(text).strip()
    try:
        return int(text, 0)
    except ValueError:
        return int(text, 10)


def _bits(field: str, value) -> tuple:
    """A match field's value as ``(value, mask)`` integers, the bits outside the mask zero; a
    field not read as bits is ``("raw", its text)``, which compares only as equal."""
    if isinstance(value, bool):
        raise _CannotTell(f"match {field}={value!r} is not a value a switch matches")
    try:
        if field in _ADDRESS_FIELDS:
            net = ipaddress.ip_network(_address(value), strict=False)
            return int(net.network_address), int(net.netmask)
        if field in _MAC_FIELDS:
            addr, slash, mask = str(value).strip().lower().partition("/")
            m = int(mask.replace(":", ""), 16) if slash else (1 << 48) - 1
            return int(addr.replace(":", ""), 16) & m, m
        if field in _INT_FIELDS:
            if isinstance(value, int):
                return value, _ALL_BITS
            v, slash, mask = str(value).partition("/")
            m = _int(mask) if slash else _ALL_BITS
            return _int(v) & m, m
    except ValueError:
        if "/" in str(value):
            raise _CannotTell(f"its match {field}={value} cannot be read as bits") from None
    if isinstance(value, str) and "/" in value:
        raise _CannotTell(f"its match {field}={value} is masked, and the mask cannot be read")
    return "raw", json.dumps(value, sort_keys=True)


def _fields(match: dict) -> dict:
    """A match as ``{field: (value, mask)}``, its prerequisites implied."""
    out = {k: _bits(k, v) for k, v in (match or {}).items()}
    for k in list(out):
        for need, value in _PREREQUISITES.get(k, ()):
            out.setdefault(need, (value, _ALL_BITS))
    return out


def _meet(x: tuple, y: tuple):
    """The values one field takes under both *x* and *y*, or None for none."""
    if "raw" in (x[0], y[0]):
        return x if x == y else None
    (v1, m1), (v2, m2) = x, y
    if (v1 ^ v2) & m1 & m2:
        return None
    return v1 | v2, m1 | m2


def _covers(x: tuple, y: tuple) -> bool:
    """Whether field value *x* takes every value *y* does."""
    if "raw" in (x[0], y[0]):
        return x == y
    (v1, m1), (v2, m2) = x, y
    return not (m1 & ~m2) and not ((v1 ^ v2) & m1)


def _match_meet(a: dict, b: dict):
    """The match of the packets both *a* and *b* match, or None when no packet does."""
    out = dict(a)
    for k, y in b.items():
        if k in out:
            got = _meet(out[k], y)
            if got is None:
                return None
            out[k] = got
        else:
            out[k] = y
    return out


def _match_covers(a: dict, b: dict) -> bool:
    """Whether match *a* matches every packet match *b* does."""
    return all(k in b and _covers(x, b[k]) for k, x in a.items())


def _does(actions) -> dict:
    """What *actions* do to a packet: ``{"out": the ports it leaves by, "meters", "rewrites"
    (each packet-changing action, in order), "onward": what takes it beyond this table, in
    words}``. No ``out`` (and nothing onward) is a drop."""
    from modules.sdn.drivers.base import ACTION_FIELDS

    out = {"out": set(), "meters": set(), "rewrites": [], "onward": []}
    for a in actions or []:
        a = _action(a)
        kind = a.get("type")
        if kind == "OUTPUT":
            out["out"].add(a.get("port"))
        elif kind == "METER":
            out["meters"].add(a.get("meter_id"))
        elif kind == "WRITE_ACTIONS":
            inner = _does(a.get("actions"))
            out["out"] |= inner["out"]
            out["meters"] |= inner["meters"]
            out["rewrites"] += inner["rewrites"]
            out["onward"] += inner["onward"]
        elif kind == "GOTO_TABLE":
            out["onward"].append(f"continues to table {a.get('table_id')}")
        elif kind == "GROUP":
            out["onward"].append(f"goes to group {a.get('group_id')}")
        elif kind in ("CLEAR_ACTIONS", "WRITE_METADATA"):
            continue
        elif kind in ACTION_FIELDS:
            out["rewrites"].append(json.dumps(a, sort_keys=True))
        else:
            out["onward"].append(f"carries an action Mercury could not read "
                                 f"({a.get('text') or kind})")
    return out


def _ports_words(ports) -> str:
    return " and ".join(f"port {p}" if isinstance(p, int) else f"the reserved port {p}"
                        for p in sorted(ports, key=str))


def _send_words(does: dict) -> str:
    """What a flow does with a packet, as a person reads it."""
    if not does["out"]:
        return "drops it"
    words = f"sends it out {_ports_words(does['out'])}"
    if does["meters"]:
        words += " through meter " + " and ".join(str(m) for m in sorted(does["meters"], key=str))
    return words


def displaced(flow: dict, records: list) -> list:
    """The Mercury records unauthorised *flow* (a row of `classify`'s ``flows``) displaced (C2004):
    each of `classify`'s *records* that is ``missing`` on its switch at its place, the same
    table, priority and match (`flow_ops._same_place`), where an OpenFlow add with that match
    and priority replaces the flow there. An expired record was removed as asked: never
    displaced."""
    from modules.sdn import flow_ops

    return [r for r in records or [] if r.get("state") == "missing"
            and r.get("dpid") == flow.get("dpid") and flow_ops._same_place(r, flow)]


def effect(flow: dict, table: list, displaced_flows: list = ()) -> dict:
    """Unauthorised *flow*'s effect on the traffic it takes (C2021), from its switch's table as
    read: *flow* a row of `classify`'s ``flows``, *table* every row of them for its switch
    (each with its ``owner`` and evidence ``id``), *displaced_flows* the Mercury flows it
    displaced (`displaced`), each as an evidence piece with its ``id``, ``cookie`` and
    ``actions``. ``{"class": one of `EFFECTS`, "words", "evidence": [the ids the words name]}``;
    how each class is decided is the module's docstring's. Never raises: what it cannot compare
    is ``unknown``, naming why."""
    def ref(f):
        return f.get("id") or cookie_hex(f.get("cookie"))

    def answer(cls, words, ids=()):
        return {"class": cls, "words": words, "evidence": list(dict.fromkeys(i for i in ids if i))}

    def unknown(why, ids=()):
        return answer("unknown", f"has an effect the table cannot tell: {why}", ids)

    def named(items, say):
        shown = items[:EFFECT_NAMED]
        words = "; ".join(say(x) for x in shown)
        if len(items) > len(shown):
            words += f"; and {len(items) - len(shown)} more"
        return words, shown

    moved = [p.get("id") for p in displaced_flows]
    try:
        mine = _fields(flow.get("match"))
    except _CannotTell as exc:
        return unknown(str(exc), moved)
    table_id, prio = flow.get("table_id", 0), flow.get("priority", 0)
    others = []
    for f in table or []:
        if f is flow or ref(f) == ref(flow) or f.get("table_id", 0) != table_id:
            continue
        try:
            others.append((f, _fields(f.get("match"))))
        except _CannotTell as exc:
            return unknown(f"{ref(f)} beside it in table {table_id}: {exc}", [ref(f)] + moved)
    others.sort(key=lambda fm: -(fm[0].get("priority") or 0))
    does = _does(flow.get("actions"))
    for f, m in others:
        if (f.get("priority") or 0) > prio and _match_covers(m, mine):
            return unknown(f"it takes no traffic while {ref(f)} "
                           f"({_OWNER_WORDS.get(f.get('owner'), 'a flow')}, priority "
                           f"{f.get('priority')}) above it matches all of it first",
                           [ref(f)] + moved)
    if does["onward"]:
        return unknown(f"it {'; '.join(does['onward'])}, and what happens there is not judged",
                       moved)
    # Each part of its traffic: the highest flow below it that would take the part without it.
    parts, cannot = [], []
    for f, m in others:
        p = f.get("priority") or 0
        both = None if p > prio else _match_meet(mine, m)
        if both is None:
            continue
        if p == prio:
            cannot.append((f, "at its own priority, where OpenFlow leaves the order undefined"))
            continue
        if any((g.get("priority") or 0) > p and _match_covers(gm, both) for g, gm in others):
            continue
        parts.append((f, _match_covers(mine, m)))
    mercury = [(p, True, "displaced") for p in displaced_flows]
    decided, controller = [], []
    for f, whole in parts:
        d = _does(f.get("actions"))
        if f.get("owner") == "mercury":
            mercury.append((f, whole, "installed"))
            decided.append(f)
        elif f.get("owner") != "controller_own":
            cannot.append((f, _OWNER_WORDS.get(f.get("owner"), "a flow")))
        elif d["onward"]:
            cannot.append((f, f"the controller's own flow, which {'; '.join(d['onward'])}"))
        elif d["out"] == {"CONTROLLER"}:
            controller.append(f)
        else:
            decided.append(f)
    rest, rest_ids = "", []
    if controller:
        said, shown = named(controller, ref)
        rest = (f"; the rest of its traffic would reach {said}, which sends it to the "
                "controller, so the controller decides it")
        rest_ids = [ref(f) for f in shown]

    def mercury_words(m):
        resp = m.get("response") or {}
        return (f"Mercury's flow {ref(m)} (cookie {cookie_hex(m.get('cookie'))}, "
                f"{action_words(m.get('actions'))}"
                + (f", installed by a {resp['action']} response" if resp.get("action") else "")
                + ")")

    def where(whole, how):
        if how == "displaced":
            return "it took that flow's place (the same table, priority and match) and"
        return f"above it, it takes {'all' if whole else 'part'} of that flow's traffic and"

    def keeps(m) -> bool:
        md = _does(m.get("actions"))
        if not md["out"] and not md["onward"] and does["out"]:
            return False
        return not (md["meters"] - does["meters"])

    lifted = [x for x in mercury if not keeps(x[0])]
    def lift_words(x):
        m, whole, how = x
        md = _does(m.get("actions"))
        gone = sorted(md["meters"] - does["meters"], key=str)
        undone = "drop" if not md["out"] else "meter " + " and ".join(str(i) for i in gone)
        return (f"{mercury_words(m)}: {where(whole, how)} {_send_words(does)}, so Mercury's "
                f"{undone} is undone")

    def shadow_words(x):
        m, whole, how = x
        return (f"{mercury_words(m)}: {where(whole, how)} does "
                f"{action_words(flow.get('actions'))} where Mercury's does "
                f"{action_words(m.get('actions'))}")

    lifted = [x for x in mercury if not keeps(x[0])]
    if lifted:
        said, shown = named(lifted, lift_words)
        return answer("lifts", f"lifts {said}", [ref(x[0]) for x in shown])
    shadowed = [x for x in mercury
                if normal_actions(x[0].get("actions")) != normal_actions(flow.get("actions"))]
    if shadowed:
        said, shown = named(shadowed, shadow_words)
        return answer("shadows", f"shadows {said}", [ref(x[0]) for x in shown])

    def their(f):
        return f"{_OWNER_WORDS[f.get('owner')]} {ref(f)} {_send_words(_does(f.get('actions')))}"

    if not does["out"]:
        if decided:
            said, shown = named(decided, their)
            return answer("drops", f"drops the traffic it takes, where without it {said}{rest}",
                          [ref(f) for f in shown] + rest_ids)
        reach = [f"{ref(f)} ({why})" for f, why in cannot[:EFFECT_NAMED]]
        if controller:
            reach.append(f"{named(controller, ref)[0]} (which sends it to the controller)")
        said = "; ".join(reach) or "no flow (the switch would drop it too: no table-miss flow)"
        return answer("drops", f"drops the traffic it takes; without it, its traffic would "
                      f"reach {said}", [ref(f) for f, _w in cannot[:EFFECT_NAMED]] + rest_ids)
    elsewhere = [f for f in decided if _does(f.get("actions"))["out"] != does["out"]]
    if elsewhere:
        said, shown = named(elsewhere, their)
        return answer("diverts", f"diverts the traffic it takes: it {_send_words(does)}, where "
                      f"without it {said}{rest}", [ref(f) for f in shown] + rest_ids)
    rewritten = [f for f in decided if _does(f.get("actions"))["rewrites"] != does["rewrites"]]
    if rewritten:
        said, shown = named(rewritten, their)
        return unknown(f"it {_send_words(does)} as {said}, but changes the packet otherwise "
                       f"({action_words(flow.get('actions'))}), and what that change does is "
                       "not judged", [ref(f) for f in shown])
    if decided:
        said, shown = named(decided, their)
        return answer("forwards", f"forwards as the controller would: it {_send_words(does)}, "
                      f"as without it {said}{rest}", [ref(f) for f in shown] + rest_ids)
    why = []
    if controller:
        said, _shown = named(controller, ref)
        why.append(f"below it only {said} would take its traffic, which sends it to the "
                   "controller, so where the controller would send it is not in the table")
    for f, w in cannot[:EFFECT_NAMED]:
        why.append(f"{ref(f)} below it is {w}")
    if not why:
        why.append("no flow below it matches its traffic, so without it the switch would drop "
                   "it (no table-miss flow), and where the controller would send it is not in "
                   "the table")
    return unknown("; ".join(why), rest_ids + [ref(f) for f, _w in cannot[:EFFECT_NAMED]])
