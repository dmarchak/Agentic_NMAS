"""dns_blacklist's logic over plain data, apart from Ryu (as fabric_forwarding's fabric_logic is):
the config, the steering flows each switch should hold, the verdict service's answer read, the
cache, the lookups in flight, and the decision. Nothing here sends, reads a switch or keeps
time of its own (the caller passes `now`), so all of it is tested without a controller.
Python 3.5 (C2646): no f-strings, no variable annotations, nothing that depends on a dict's
order (3.5's dicts have none): every answer is sorted.

**The steering flows**, each tagged with the app's cookie (`COOKIE_PREFIX` under
`COOKIE_MASK`, the manifest's `owns_flows`; the low bits name the kind): in each switch's
FORWARD table (the table fabric_forwarding's host flows are in, so a query is caught before a
host flow forwards it; Mercury compiles it from the switch's platform profile, the ProCurve's
hardware table 100, table 0 elsewhere), at `PRIORITY` (above every forwarding flow's 100), one
flow per EDGE port and address family: `in_port`, `eth_type` IPv4 or IPv6, `ip_proto` 17 and
`udp_dst` 53, to the controller. An edge port is one that is up and is not an end of a link the
topology reported (`edge_ports`). Matching the port is what lets an allowed query be
re-injected into the same switch's tables from the controller (`in_port` CONTROLLER) without
meeting its own steering flow again. Nothing else is matched: DHCP (UDP 67 and 68), the
management traffic, TCP and every reply (UDP SOURCE port 53) take their normal path untouched.

**The verdict** (`read_verdict`), from Cloudflare's malware-filtering resolver over
DNS-over-HTTPS JSON (`verdict_path`): BAD only when an Answer record is an A of 0.0.0.0 AND the
Comment carries Extended DNS Error 16 (Censored), the two marks the measured answer for
`malware.testcategory.com` carried (2026-11-10); GOOD for any other readable answer (Status 0,
NOERROR, or 3, NXDOMAIN); UNKNOWN for an answer not read (no answer, a non-2xx, a body that is
not a JSON object, a Status that is not a number, records not in a list) or a Status other
than 0 or 3 (SERVFAIL and the like: the service could not judge the name). UNKNOWN follows the
fail mode (`decide`).

**The cache** (`Cache`): a verdict is kept for the lesser of the answer's TTL (the smallest of
its records', the Answer's and the Authority's) and the config's cap, or the cap when the
answer carries none; a TTL of 0 is not kept. An UNKNOWN is kept for `UNKNOWN_HOLD_S`, so a
service that is down is asked once in that time, not once per query. At most `max_entries`
names: an expired entry goes first, then the oldest stored.

**The lookups in flight** (`Pending`): one lookup per name at a time; a query for a name
already being asked waits for that answer (at most `MAX_WAITING` per name); at most
`MAX_LOOKUPS` names are asked at once. A query past either bound, and every query still
waiting at its lookup's deadline (the config's `timeout_s`), is decided as UNKNOWN, so the
fail mode answers it in time; a late answer still fills the cache.
"""

import collections
import ipaddress
import json
import re

#: The app's cookie (the manifest's owns_flows: "0x444e000000000000" under
#: "0xffff000000000000", "DN"); the low bits carry the flow's kind.
COOKIE_PREFIX = 0x444e000000000000
COOKIE_MASK = 0xffff000000000000
PUNT_IPV4, PUNT_IPV6 = 1, 2
KINDS = {PUNT_IPV4: "punt-ipv4", PUNT_IPV6: "punt-ipv6"}
ETH_TYPES = {PUNT_IPV4: 0x0800, PUNT_IPV6: 0x86dd}
#: Above every forwarding flow (fabric_forwarding's host flows are at 100).
PRIORITY = 1000
UDP, DNS_PORT = 17, 53
CONTROLLER = ("CONTROLLER",)

GOOD, BAD, UNKNOWN = "good", "bad", "unknown"
ALLOW, ANSWER, DROP = "allow", "answer", "drop"
FAIL_OPEN, FAIL_CLOSED = "open", "closed"
#: The marks of a blocked name in the verdict service's answer (measured 2026-11-10).
BLOCKED_ADDRESS = "0.0.0.0"
EDE_CENSORED = "EDE(16)"
#: How long an UNKNOWN is kept, so a service that is down is asked once in this time.
UNKNOWN_HOLD_S = 5.0
#: Lookups asked at once, and queries waiting on one name's lookup.
MAX_LOOKUPS = 32
MAX_WAITING = 8
#: The config's bounds and defaults (the manifest's config_schema says the same).
DEFAULTS = {"timeout_s": 2.0, "ttl_cap_s": 300, "max_entries": 10000, "fail_mode": FAIL_OPEN}
LIMITS = {"timeout_s": (0.1, 10.0), "ttl_cap_s": (1, 86400), "max_entries": (1, 100000)}
MAX_TABLE = 254
VERDICT_URL = re.compile(r"^https://security\.cloudflare-dns\.com(:443)?$")
#: A name as the verdict path takes it (what blacklist_wire.parse_query gives, re-checked here,
#: so nothing else ever reaches the path).
NAME = re.compile(r"^[a-z0-9_-]{1,63}(\.[a-z0-9_-]{1,63})*$")


def cookie(kind):
    return COOKIE_PREFIX | kind


def is_ours(value):
    return isinstance(value, int) and (value & COOKIE_MASK) == COOKIE_PREFIX


# ── the config ──────────────────────────────────────────────────────────────────────────────

def _number(where, value, low, high, integer, problems):
    if isinstance(value, bool) or not isinstance(value, int if integer else (int, float)) \
            or not low <= value <= high:
        problems.append("%s is %s, %g to %g, not %r" % (
            where, "a whole number" if integer else "a number", low, high, value))
        return None
    return value if integer else float(value)


def _table(where, value, problems):
    if not isinstance(value, dict) or sorted(value) != ["forward_table"]:
        problems.append("%s is a mapping of forward_table alone, not %r" % (where, value))
        return None
    table = value["forward_table"]
    if isinstance(table, bool) or not isinstance(table, int) or not 0 <= table <= MAX_TABLE:
        problems.append("%s.forward_table is a table id, 0 to %d, not %r" % (where, MAX_TABLE,
                                                                           table))
        return None
    return table


def _address(where, value, version, problems):
    try:
        address = ipaddress.ip_address(str(value))
    except ValueError:
        address = None
    if address is None or address.version != version or address.is_unspecified \
            or address.is_multicast or address.is_loopback:
        problems.append("%s is a unicast IPv%d address, not %r" % (where, version, value))
        return None
    return address.compressed


def _mapping(where, value, keys, problems):
    if value is None:
        return {}
    if not isinstance(value, dict):
        problems.append("%s is a mapping, not %r" % (where, value))
        return {}
    extra = sorted(k for k in value if k not in keys)
    if extra:
        problems.append("%s takes %s, not %s" % (where, ", ".join(keys),
                                                 ", ".join(repr(k) for k in extra)))
    return value


def parse_config(data):
    """`(config, problems)`: *data* (the start-time config, or a push) as the app keeps it,
    ``{"switches": {dpid: table}, "default_table": table or None, "timeout_s", "fail_mode",
    "ttl_cap_s", "max_entries", "block_ipv4", "block_ipv6", "upstream": (dpid, port) or None}``,
    or None with one line per field refused, each naming the field, the value and the rule."""
    problems = []
    if not isinstance(data, dict):
        return None, ["the config is a JSON object, not %r" % (data,)]
    known = ("block_page", "cache", "default_tables", "fail_mode", "switches", "upstream",
             "verdict_service")
    _mapping("the config", data, known, problems)
    switches = {}
    raw = data.get("switches", {})
    if not isinstance(raw, dict):
        problems.append("switches is a mapping of datapath ids to tables, not %r" % (raw,))
        raw = {}
    for key in sorted(raw, key=str):
        if not (isinstance(key, str) and key.isdigit()):
            problems.append("switches: %r is not a datapath id in decimal" % (key,))
            continue
        table = _table("switches.%s" % key, raw[key], problems)
        if table is not None:
            switches[int(key)] = table
    default = None
    if data.get("default_tables") is not None:
        default = _table("default_tables", data["default_tables"], problems)
    out = {"switches": switches, "default_table": default}
    service = _mapping("verdict_service", data.get("verdict_service"), ("timeout_s", "url"),
                       problems)
    if "url" in service and not (isinstance(service["url"], str)
                                 and VERDICT_URL.match(service["url"])):
        problems.append("verdict_service.url is Cloudflare's malware-filtering resolver, "
                        "https://security.cloudflare-dns.com (port 443), not %r"
                        % (service["url"],))
    out["timeout_s"] = _number("verdict_service.timeout_s",
                               service.get("timeout_s", DEFAULTS["timeout_s"]),
                               LIMITS["timeout_s"][0], LIMITS["timeout_s"][1], False, problems)
    mode = data.get("fail_mode", DEFAULTS["fail_mode"])
    if mode not in (FAIL_OPEN, FAIL_CLOSED):
        problems.append("fail_mode is %s or %s, not %r" % (FAIL_OPEN, FAIL_CLOSED, mode))
    out["fail_mode"] = mode
    cache = _mapping("cache", data.get("cache"), ("max_entries", "ttl_cap_s"), problems)
    for field in ("max_entries", "ttl_cap_s"):
        low, high = LIMITS[field]
        out[field] = _number("cache.%s" % field, cache.get(field, DEFAULTS[field]), low, high,
                             True, problems)
    page = _mapping("block_page", data.get("block_page"), ("ipv4", "ipv6"), problems)
    out["block_ipv4"] = _address("block_page.ipv4", page["ipv4"], 4, problems) \
        if page.get("ipv4") is not None else None
    out["block_ipv6"] = _address("block_page.ipv6", page["ipv6"], 6, problems) \
        if page.get("ipv6") is not None else None
    out["upstream"] = None
    up = data.get("upstream")
    if up is not None:
        up = _mapping("upstream", up, ("dpid", "port"), problems)
        dpid, port = up.get("dpid"), up.get("port")
        if not (isinstance(dpid, str) and dpid.isdigit()):
            problems.append("upstream.dpid is a datapath id in decimal, not %r" % (dpid,))
        elif isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 0xffffff00:
            problems.append("upstream.port is a switch port number, not %r" % (port,))
        else:
            out["upstream"] = (int(dpid), port)
    if problems:
        return None, problems
    return out, []


#: What the app says when the app SDK is not on its import path (C2729).
NO_SDK = ("the app SDK mercury_app is not importable on this controller, so the start-time "
          "config Mercury staged cannot be read")


def from_start_config(answer):
    """`(config, why)`: the app's config from *answer*, what `mercury_app.start_config` gave at
    load (None when the SDK could not be imported), as `parse_config` keeps it, with why "";
    or None and why in words, which the app's /health names until a config is in force."""
    if answer is None:
        return None, NO_SDK
    if not answer.get("ok"):
        return None, "its start-time config was not read: %s" % (answer.get("error") or
                                                                 "no reason was given")
    config, problems = parse_config(answer.get("config"))
    if config is None:
        return None, "its start-time config %s is refused: %s" % (answer.get("path") or "",
                                                                  "; ".join(problems))
    return config, ""


def table_for(config, dpid):
    """The forward table *dpid*'s steering flows go in, or None (the switch is not served)."""
    if config is None:
        return None
    return config["switches"].get(dpid, config["default_table"])


# ── the steering flows ──────────────────────────────────────────────────────────────────────

def edge_ports(up_ports, links, dpid):
    """*dpid*'s edge ports, sorted: up (`up_ports`, ``{dpid: set of ports}``) and no end of a
    link (`links`: ``(src_dpid, src_port, dst_dpid, dst_port)``)."""
    ends = set()
    for (a, pa, b, pb) in links:
        ends.add((a, pa))
        ends.add((b, pb))
    return sorted(p for p in up_ports.get(dpid, ()) if (dpid, p) not in ends)


def desired_flows(table, ports):
    """``{(table, priority, match): (actions, cookie)}``: the steering flows for *ports* in
    *table* (see the module's docstring); ``match`` a sorted tuple of (field, value)."""
    out = {}
    for port in ports:
        for kind in sorted(KINDS):
            match = tuple(sorted([("eth_type", ETH_TYPES[kind]), ("in_port", port),
                                  ("ip_proto", UDP), ("udp_dst", DNS_PORT)]))
            out[(table, PRIORITY, match)] = ((CONTROLLER,), cookie(kind))
    return out


def difference(desired, current):
    """``{"add": [(key, actions, cookie)], "delete": [(key, cookie)]}``, each sorted: what
    makes *current* (the app's own flows as read, ``{key: (actions, cookie)}``) *desired*. A
    flow already right is not sent again; only the app's own cookie is ever removed."""
    add = [(k, desired[k][0], desired[k][1]) for k in sorted(desired)
           if current.get(k) != desired[k]]
    delete = [(k, current[k][1]) for k in sorted(current)
              if k not in desired and is_ours(current[k][1])]
    return {"add": add, "delete": delete}


# ── the verdict ─────────────────────────────────────────────────────────────────────────────

#: The verdict service's JSON media type, the egress call's Accept: Cloudflare's resolver
#: answered 405 to `application/json` (and to a `ct=application/dns-json` query parameter
#: beside it) and 200 to `application/dns-json` (measured 2026-11-10).
VERDICT_ACCEPT = "application/dns-json"


def verdict_path(name):
    """The verdict service's path and query for *name* (an A lookup; JSON is asked for by the
    egress call's Accept, `VERDICT_ACCEPT`), or ValueError for a name not of the shape the DNS
    parser gives."""
    if not isinstance(name, str) or len(name) > 253 or not NAME.match(name):
        raise ValueError("%r is not a name the verdict service is asked about" % (name,))
    return "/dns-query?name=%s&type=A" % name


def _records(body, key):
    records = body.get(key, [])
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        return None
    return records


def read_verdict(answer):
    """`(verdict, ttl, why)` from *answer*, what `mercury_app.egress` gave (see the module's
    docstring): ``ttl`` the smallest record TTL, or None when the answer carries none; ``why``
    says what an UNKNOWN could not read, and is "" otherwise."""
    if not isinstance(answer, dict):
        return UNKNOWN, None, "the verdict service's answer is not a mapping"
    if not answer.get("ok"):
        return UNKNOWN, None, answer.get("error") or "the verdict service did not answer"
    body = answer.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return UNKNOWN, None, "the verdict service's answer is not JSON"
    if not isinstance(body, dict):
        return UNKNOWN, None, "the verdict service's answer is not a JSON object"
    status = body.get("Status")
    if isinstance(status, bool) or not isinstance(status, int):
        return UNKNOWN, None, "the verdict service's answer carries no Status number"
    answers, authority = _records(body, "Answer"), _records(body, "Authority")
    comments = body.get("Comment", [])
    if isinstance(comments, str):
        comments = [comments]
    if answers is None or authority is None or not isinstance(comments, list):
        return UNKNOWN, None, "the verdict service's records are not lists of objects"
    ttls = [r["TTL"] for r in answers + authority
            if isinstance(r.get("TTL"), int) and not isinstance(r.get("TTL"), bool)
            and r["TTL"] >= 0]
    ttl = min(ttls) if ttls else None
    censored = any(isinstance(c, str) and c.startswith(EDE_CENSORED) for c in comments)
    sinkholed = any(r.get("type") == 1 and r.get("data") == BLOCKED_ADDRESS for r in answers)
    if censored and sinkholed:
        return BAD, ttl, ""
    if status not in (0, 3):
        return UNKNOWN, None, ("the verdict service answered Status %d, neither NOERROR nor "
                               "NXDOMAIN, so it did not judge the name" % status)
    return GOOD, ttl, ""


def decide(verdict, config):
    """`ALLOW`, `ANSWER` (a reply with the block page's address) or `DROP` for *verdict*:
    GOOD is allowed; BAD is answered when a block page is configured, else dropped; UNKNOWN
    follows the fail mode, open allowing it, closed blocking it as BAD is."""
    if verdict == GOOD or (verdict == UNKNOWN and config["fail_mode"] == FAIL_OPEN):
        return ALLOW
    if config["block_ipv4"] or config["block_ipv6"]:
        return ANSWER
    return DROP


# ── the cache ───────────────────────────────────────────────────────────────────────────────

class Cache(object):
    """Verdicts by name, each until its expiry (see the module's docstring)."""

    def __init__(self, max_entries, ttl_cap_s):
        self.max_entries, self.ttl_cap_s = max_entries, ttl_cap_s
        self.entries = collections.OrderedDict()        # name -> (verdict, expires)

    def get(self, name, now):
        """The verdict kept for *name*, or None (absent or expired, which is dropped)."""
        got = self.entries.get(name)
        if got is None:
            return None
        if got[1] <= now:
            del self.entries[name]
            return None
        return got[0]

    def lifetime(self, verdict, ttl):
        """How long *verdict* with *ttl* is kept, in seconds."""
        if verdict == UNKNOWN:
            return UNKNOWN_HOLD_S
        return self.ttl_cap_s if ttl is None else min(ttl, self.ttl_cap_s)

    def put(self, name, verdict, ttl, now):
        """Keep *verdict* for *name*; answers how long, 0 when it is not kept."""
        keep = self.lifetime(verdict, ttl)
        self.entries.pop(name, None)
        if keep <= 0:
            return 0
        if len(self.entries) >= self.max_entries:
            for old in [n for n, (_v, e) in self.entries.items() if e <= now]:
                del self.entries[old]
        while len(self.entries) >= self.max_entries:
            self.entries.popitem(last=False)
        self.entries[name] = (verdict, now + keep)
        return keep

    def size(self):
        return len(self.entries)


# ── the lookups in flight ───────────────────────────────────────────────────────────────────

class Pending(object):
    """The names being asked, each with its deadline and the queries waiting on it."""

    ASK, JOINED, FULL = "ask", "joined", "full"

    def __init__(self, max_lookups=MAX_LOOKUPS, max_waiting=MAX_WAITING):
        self.max_lookups, self.max_waiting = max_lookups, max_waiting
        self.names = {}                 # name -> (deadline, [items])

    def start(self, name, item, now, timeout_s):
        """`ASK` (a new lookup: the caller asks), `JOINED` (*item* waits on the lookup in
        flight) or `FULL` (a bound is reached: the caller decides *item* as UNKNOWN now)."""
        if name in self.names:
            deadline, items = self.names[name]
            if len(items) >= self.max_waiting:
                return self.FULL
            items.append(item)
            return self.JOINED
        if len(self.names) >= self.max_lookups:
            return self.FULL
        self.names[name] = (now + timeout_s, [item])
        return self.ASK

    def finish(self, name):
        """The items waiting on *name*'s lookup, which is over; [] when none waits (its
        deadline passed first)."""
        got = self.names.pop(name, None)
        return got[1] if got is not None else []

    def expired(self, now):
        """``[(name, items)]`` of every lookup past its deadline, sorted by name, and forgotten:
        each item is decided as UNKNOWN by the caller."""
        late = sorted(n for n, (deadline, _items) in self.names.items() if deadline <= now)
        return [(n, self.names.pop(n)[1]) for n in late]

    def size(self):
        return len(self.names)


class Recent(object):
    """Frames the app re-injected in the last *window_s*, by digest, at most *size*: a frame
    the app already allowed that comes back to it from the next switch (a port not yet known
    as a link) is re-injected again without a second lookup. Only ALLOWED frames are kept, so
    a host's retry of a blocked query is never let through as a repeat."""

    def __init__(self, window_s=2.0, size=1024):
        self.window_s, self.size = window_s, size
        self.seen = collections.OrderedDict()           # digest -> when

    def allowed(self, digest, now):
        self.seen.pop(digest, None)
        self.seen[digest] = now
        while len(self.seen) > self.size:
            self.seen.popitem(last=False)

    def is_repeat(self, digest, now):
        when = self.seen.get(digest)
        return when is not None and now - when < self.window_s
