"""switch_quirks' logic over plain data, apart from Ryu (C2670, C2760): each switch's tables as
Mercury compiled them, the pipeline flows a multi-table switch needs before anything else
works on it, reconcile, and what `/health` says. Nothing here sends or reads a switch or keeps
time; all of it is tested without a controller. Python 3.5 (C2646): no f-strings, no variable
annotations, every answer sorted.

**The tables are the network's, never the app's.** The config (the start-time file Mercury
compiles from each switch's platform profile: the manifest's `compiled`) names, per switch by
its DPID in decimal, its `forward_table` (where a host's forwarding flow goes), `punt_table`
(where the miss, ARP and LLDP go to the controller) and `meter_table` (where a meter is taken).
On the ProCurve's measured pipeline (C2601) they are 100, 200 and 100; on a switch whose profile
records no tables, 0, 0 and 0. A switch the config does not name is NOT SERVED, and `/health`
names it.

**The pipeline flows, each under the app's cookie** (`COOKIE_PREFIX` under `COOKIE_MASK`, the
manifest's `owns_flows`; the low bits name the kind):
- where the forward table is not the punt table: the forward table's MISS goes on to the punt
  table (`MISS_GOTO`, priority 0, matching everything), so a frame no host flow matches (ARP,
  LLDP, an unknown destination) reaches the table that can send it to the controller. On the
  ProCurve, without it, table 100 drops what it does not match;
- where the punt table is not table 0: LLDP to the controller there (`LLDP`, priority
  `LLDP_PRIORITY`), since Ryu's own LLDP flow goes only in table 0, which the ProCurve refuses
  (BAD_MATCH, C2601), and link discovery would find no link through the switch.
A switch on table 0 for every role (Open vSwitch, the Aristas) needs neither and gets none.
OpenFlow 1.0 has one table: a 1.0 switch the config gives another table is a problem.

**Reconcile** (`difference`): against a switch's flows as read, only the app's own cookie is
added or removed; another owner's flow on a key the app wants is a CONFLICT, named and never
overwritten.
"""

COOKIE_PREFIX = 0x5351000000000000
COOKIE_MASK = 0xffff000000000000
MISS_GOTO, LLDP = 1, 2
KINDS = {MISS_GOTO: "miss_goto", LLDP: "lldp"}
#: LLDP's priority in the punt table: above every other flow there.
LLDP_PRIORITY = 65535
ETH_LLDP = 0x88cc
#: An action, as the app compares them: ("GOTO", table), ("CONTROLLER",) or ("OUTPUT", port).
CONTROLLER = ("CONTROLLER",)
ROLES = ("forward_table", "punt_table", "meter_table")
MAX_TABLE = 254
#: OpenFlow's wire version 1.0 (one table).
OF10 = 0x01
#: What the app says when the app SDK is not on its import path.
NO_SDK = ("the app SDK mercury_app is not importable on this controller, so the start-time "
          "config Mercury staged cannot be read")


def cookie(kind):
    return COOKIE_PREFIX | kind


def is_ours(value):
    return (value & COOKIE_MASK) == COOKIE_PREFIX


# ── the config ──────────────────────────────────────────────────────────────────────────────

def _tables(where, value, problems):
    if not isinstance(value, dict):
        problems.append("%s is a mapping of %s, not %r" % (where, ", ".join(ROLES), value))
        return None
    extra = sorted(k for k in value if k not in ROLES)
    if extra:
        problems.append("%s takes %s, not %s" % (where, ", ".join(ROLES),
                                                 ", ".join(repr(k) for k in extra)))
    out = {}
    for role in ROLES:
        got = value.get(role)
        if isinstance(got, bool) or not isinstance(got, int) or not 0 <= got <= MAX_TABLE:
            problems.append("%s.%s is a table id, 0 to %d, not %r" % (where, role, MAX_TABLE,
                                                                     got))
            return None
        out[role] = got
    return out


def parse_config(data):
    """`(config, problems)`: *data* (the start-time file's JSON) as the app keeps it,
    `{"switches": {dpid: {role: table}}}`, or None with one line per field refused, each naming
    the field, the value and the rule."""
    if not isinstance(data, dict):
        return None, ["the config is a JSON object, not %r" % (data,)]
    problems = []
    extra = sorted(k for k in data if k != "switches")
    if extra:
        problems.append("the config takes switches, not %s" % ", ".join(repr(k) for k in extra))
    raw = data.get("switches", {})
    if not isinstance(raw, dict):
        return None, problems + ["switches is a mapping of datapath ids to tables, not %r"
                                 % (raw,)]
    switches = {}
    for key in sorted(raw):
        if not (isinstance(key, str) and key.isdigit()):
            problems.append("switches: %r is not a datapath id in decimal" % (key,))
            continue
        tables = _tables("switches.%s" % key, raw[key], problems)
        if tables is not None:
            switches[int(key)] = tables
    if problems:
        return None, problems
    return {"switches": switches}, []


def from_start_config(answer):
    """`(config, why)`: the config from `mercury_app.start_config`'s *answer* (None when the SDK
    could not be imported) with why "", or None and why in words, which `/health` names while
    no config is in force: a missing file is never an ok."""
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


def tables_for(config, dpid):
    """*dpid*'s `{role: table}`, or None when the config names none (the switch is not
    served)."""
    if config is None:
        return None
    return config["switches"].get(dpid)


# ── the flows ───────────────────────────────────────────────────────────────────────────────

def desired_flows(tables, wire_version):
    """`(flows, problems)`: `{(table, priority, match): (actions, cookie)}` a switch with
    *tables* (`tables_for`'s) on OpenFlow *wire_version* should hold (the module's docstring),
    and why it cannot, in words."""
    if wire_version == OF10:
        named = sorted(set(t for t in tables.values() if t != 0))
        if named:
            return {}, ["it speaks OpenFlow 1.0, which has one table, and the config names "
                        "table %s" % ", ".join(str(t) for t in named)]
        return {}, []
    flows = {}
    forward, punt = tables["forward_table"], tables["punt_table"]
    if forward != punt:
        flows[(forward, 0, ())] = ((("GOTO", punt),), cookie(MISS_GOTO))
    if punt != 0:
        flows[(punt, LLDP_PRIORITY, (("eth_type", ETH_LLDP),))] = ((CONTROLLER,), cookie(LLDP))
    return flows, []


def difference(desired, current):
    """`{"add": [(key, actions, cookie)], "delete": [(key, cookie)], "conflicts": [words]}`:
    what to send so a switch holding *current* (`[(table, priority, match, actions, cookie)]`,
    as read) holds *desired*. Only the app's own cookie is added or removed; another owner's
    flow on a key the app wants is a conflict, left as it is."""
    mine, others = {}, {}
    for (table, priority, match, actions, value) in current:
        key = (table, priority, tuple(sorted(match)))
        if is_ours(value):
            mine[key] = (tuple(actions), value)
        else:
            others[key] = value
    add, delete, conflicts = [], [], []
    for key in sorted(desired):
        actions, value = desired[key]
        if key in others:
            conflicts.append("table %d priority %d %s is held by another owner (cookie %#x): "
                             "left as it is" % (key[0], key[1], dict(key[2]), others[key]))
            continue
        if mine.get(key) != (tuple(actions), value):
            add.append((key, tuple(actions), value))
    for key in sorted(mine):
        if key not in desired:
            delete.append((key, mine[key][1]))
    return {"add": add, "delete": delete, "conflicts": conflicts}


# ── what /health says ───────────────────────────────────────────────────────────────────────

def health(config, start_error, connected, reconciled, problems_by_switch, errors_by_switch):
    """`/health`'s ``{"ok", "configured", "switches", "served", "problems"}``: *connected* the
    connected switches' DPIDs, *reconciled* those whose flows were read and reconciled,
    *problems_by_switch* and *errors_by_switch* `{dpid: [words]}` (a config the switch cannot
    take, a conflict; what the switch refused). Not ok while no config is in force (naming
    why), while a connected switch is not named, not yet reconciled, or has a problem."""
    problems = []
    if config is None:
        problems.append("%s: no switch is served" % start_error)
    served = sorted(d for d in connected if tables_for(config, d) is not None)
    if config is not None:
        problems += ["switch %d is connected and the config names no tables for it: not "
                     "served" % d for d in sorted(connected) if d not in served]
    problems += ["switch %d: its flows are not read and reconciled yet" % d for d in served
                 if d not in reconciled]
    for dpid in sorted(problems_by_switch):
        problems += ["switch %d: %s" % (dpid, p) for p in problems_by_switch[dpid]]
    for dpid in sorted(errors_by_switch):
        if errors_by_switch[dpid]:
            problems.append("switch %d refused: %s" % (dpid, ", ".join(errors_by_switch[dpid])))
    return {"ok": not problems, "configured": config is not None,
            "switches": len(connected), "served": len(served), "problems": problems}


def tables_view(config):
    """`GET /tables`'s answer: every switch's tables as the config names them."""
    if config is None:
        return {"configured": False, "switches": {}}
    return {"configured": True,
            "switches": dict((str(d), dict(t)) for d, t in sorted(config["switches"].items()))}
