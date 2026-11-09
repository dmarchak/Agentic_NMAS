"""The compile step: an app's START-TIME CONFIG, made by Mercury from what it knows of the network
(C2760; the SDN platform design revision 6, section 12, "the compile step"; decision K9). The one
home: the controller app deploy's plan (`modules/apps/deploy_op.build`) calls `compile_set` for
the chosen set before `channel.plan`, which stages each config as its own file, puts its sha256
in the request (so the compiled bytes are in the plan's hash) and refuses one holding a secret.

**What is compiled** is what the app's manifest declares under `compiled`
(`modules/apps/manifest.Compiled`): a top-level key holding, `per_switch`, each expected switch's
TABLE ROLES, keyed by its DPID in decimal. A role is placed by the flows it carries, through
`modules/sdn/placement` (the one home for which table takes a flow) on the switch's platform
profile (`modules/platforms/profile.select`, the expected switch's ``selected``):
- `forward_table`: a host's forwarding flow, an IPv4 or IPv6 destination out of a port;
- `punt_table`: the table miss, ARP and LLDP, each to the controller;
- `meter_table`: an IPv4 destination through a meter, then out of a port.
Each role is the FIRST table, by id, that accepts every flow of the role; where the forward and
punt tables differ, the forward table must also take a goto to the punt table, or the compile
refuses naming both. A profile entry that records no tables (its pipeline is discovered: the
Aristas, Open vSwitch) compiles every role to table 0, OpenFlow's first table, and says so.
So the app reads its tables and never branches on a vendor (the ProCurve's forward table 100 and
punt table 200, C2601, come from its profile, never from the app).

**The network's own config** (the registry's per-network config, when it carries one) is the
base; a key Mercury compiles that it also sets is refused (a set value would stand in for the
measured tables), the manifest's schema defaults are filled (`manifest.effective_config`) and
the result is validated against its `config_schema` (`manifest.validate_config`), each failure
named. An app that declares nothing compiled and is given no config gets no file.

Every answer says, per switch, what each role compiled to and from which record (`notes`),
which the preview draws beside the config. Nothing here reads a device or a file.
"""

import copy
import logging

from modules.apps.manifest import effective_config, validate_config

log = logging.getLogger(__name__)

_HOST = "a host's address"
_TO_CONTROLLER = {"type": "OUTPUT", "port": "CONTROLLER"}
_OUT = {"type": "OUTPUT", "port": 1}
#: Each table role and the flows it carries, in `modules/sdn/placement`'s form (the match's
#: values are not read there, only its fields).
ROLES = {
    "forward_table": (
        {"match": {"eth_type": 0x0800, "ipv4_dst": _HOST}, "actions": [_OUT]},
        {"match": {"eth_type": 0x86dd, "ipv6_dst": _HOST}, "actions": [_OUT]}),
    "punt_table": (
        {"match": {}, "actions": [_TO_CONTROLLER]},
        {"match": {"eth_type": 0x0806}, "actions": [_TO_CONTROLLER]},
        {"match": {"eth_type": 0x88cc}, "actions": [_TO_CONTROLLER]}),
    "meter_table": (
        {"match": {"eth_type": 0x0800, "ipv4_dst": _HOST},
         "actions": [{"type": "METER", "meter_id": 1}, _OUT]},),
}
#: What each role's flows are, in words (a refusal names them).
ROLE_WORDS = {"forward_table": "a host's IPv4 and IPv6 forwarding flows",
              "punt_table": "the table miss, ARP and LLDP to the controller",
              "meter_table": "a flow through a meter"}


def _basis(selected: dict) -> str:
    from modules.platforms.profile import range_words

    entry = selected["entry"]
    return (f"the platform profile {selected['profile']} ({selected.get('family', '')} "
            f"{range_words(entry['os'])})")


def table_roles(selected: dict, roles) -> dict:
    """``{"ok", "tables": {role: table id}, "notes": [words], "error"}`` for *roles* on a switch
    whose profile selection is *selected* (`profile.select`'s answer)."""
    from modules.platforms import profile
    from modules.sdn import placement

    if not (selected or {}).get("ok"):
        return {"ok": False, "tables": {}, "notes": [],
                "error": (selected or {}).get("error") or "no platform profile was selected"}
    basis = _basis(selected)
    if not profile.tables(selected["entry"]):
        return {"ok": True, "tables": {r: 0 for r in roles}, "error": "",
                "notes": [f"table 0 for {', '.join(roles)}: {basis} records no tables (its "
                          "pipeline is discovered), so OpenFlow's first table"]}
    tables = placement.from_profile(selected["entry"])
    out, notes = {}, []
    for role in roles:
        found = None
        why = []
        for table in tables:
            refused = [w for flow in ROLES[role] for w in placement.refusals(table, flow)]
            if not refused:
                found = table
                break
            why.append("; ".join(dict.fromkeys(refused)))
        if found is None:
            return {"ok": False, "tables": {}, "notes": [],
                    "error": (f"no table of {basis} takes {ROLE_WORDS[role]} ({role}): "
                              + " | ".join(why))}
        out[role] = found.table_id
        if found.hardware is False:
            rate = f", at {found.software_pps} packets a second" if found.software_pps else ""
            notes.append(f"{role} {found.table_id} is a software table{rate}")
    if "forward_table" in out and "punt_table" in out \
            and out["forward_table"] != out["punt_table"]:
        forward = next(t for t in tables if t.table_id == out["forward_table"])
        goto = {"match": {"eth_type": 0x0800},
                "actions": [{"type": "GOTO_TABLE", "table_id": out["punt_table"]}]}
        refused = placement.refusals(forward, goto)
        if refused:
            return {"ok": False, "tables": {}, "notes": [],
                    "error": (f"the forward table {out['forward_table']} cannot go on to the "
                              f"punt table {out['punt_table']} on {basis}: "
                              + "; ".join(refused))}
    notes.insert(0, f"from {basis}, its measured tables")
    return {"ok": True, "tables": out, "notes": notes, "error": ""}


def _dpid_key(dpid):
    if isinstance(dpid, bool) or not isinstance(dpid, int) or dpid < 0:
        return None
    return str(dpid)


#: The start-time config's reserved key (C2645; the SDK's `RESERVED`): what Mercury adds for the
#: SDK after the app's own config is validated, never the app's, and stripped by
#: `mercury_app.start_config` before the app reads its config.
RESERVED = "_mercury"


def _at(config: dict, dotted: str):
    node = config
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def egress_problem(value) -> str:
    """Why *value* is not an address an app's egress may reach: an http or https URL with a host,
    no user or password, query or fragment; or ""."""
    from urllib.parse import urlsplit

    if not isinstance(value, str) or not value:
        return f"is {type(value).__name__ if not isinstance(value, str) else 'empty'}, not a URL"
    try:
        parts = urlsplit(value)
        _ = parts.port          # a port out of range or not a number raises here
    except ValueError as exc:
        return f"does not parse as a URL ({exc})"
    if parts.scheme not in ("http", "https"):
        return f"is a {parts.scheme or 'schemeless'} address, not http or https"
    if not parts.hostname:
        return "names no host"
    if "@" in parts.netloc:
        return "carries a user or password; a secret never goes in a config file"
    if parts.query or parts.fragment:
        return "carries a query or a fragment; the call gives its own path"
    return ""


def egress_targets(manifest, config) -> tuple:
    """``({destination: url}, problems)``: each destination *manifest* declares under `egress`,
    its address read from *config* at its `from_config` key (C2645), the one place an app's
    egress may go; a missing or malformed address is a problem naming the key."""
    who = f"{manifest.name} {manifest.version}"
    targets, problems = {}, []
    for e in manifest.egress:
        value = _at(config or {}, e.from_config)
        why = egress_problem(value) if value is not None else (
            "is not set in the network's config")
        if why:
            problems.append(f"{who}'s egress {e.name!r}: its address at {e.from_config} {why}")
            continue
        targets[e.name] = value
    return targets, problems


def compile_config(manifest, given=None, switches=()) -> dict:
    """``{"ok", "config" (a JSON object, or None: no file), "notes": [words], "problems":
    [words]}`` for *manifest*'s app, from *given* (the network's own config, or None) and the
    expected *switches* (``[{"name", "dpid", "selected"}]``). A switch with no DPID is left out
    (the plan refuses it by name). An app that declares egress gets, under `RESERVED`, each
    destination's address (`egress_targets`), so the SDK's `egress` reaches those and nothing
    else, under the confirmed hash."""
    who = f"{manifest.name} {manifest.version}"
    if not manifest.compiled and given is None and not manifest.egress:
        return {"ok": True, "config": None, "notes": [], "problems": []}
    if isinstance(given, dict) and RESERVED in given:
        return {"ok": False, "config": None, "notes": [],
                "problems": [f"{who}: the network's config sets {RESERVED}, the key Mercury "
                             "reserves for the app SDK's egress addresses"]}
    if given is not None and not isinstance(given, dict):
        return {"ok": False, "config": None, "notes": [],
                "problems": [f"{who}: the network's config is a mapping, not a "
                             f"{type(given).__name__}"]}
    config = copy.deepcopy(given) if given is not None else {}
    problems, notes = [], []
    for item in manifest.compiled:
        if item.key in config:
            problems.append(f"{who}: the network's config sets {item.key}, which Mercury "
                            "compiles from the platform profiles; a value set by hand would "
                            "stand in for the measured tables, so it is refused")
            continue
        compiled = {}
        for sw in switches:
            if sw.get("dpid") in (None, ""):
                continue
            name = sw.get("name") or "?"
            key = _dpid_key(sw.get("dpid"))
            if key is None:
                problems.append(f"{who}'s {item.key}: {name}'s DPID {sw.get('dpid')!r} is not "
                                "a whole number, so it cannot be keyed")
                continue
            got = table_roles(sw.get("selected"), item.per_switch)
            if not got["ok"]:
                problems.append(f"{who}'s {item.key} for {name}: {got['error']}")
                continue
            compiled[key] = got["tables"]
            notes.append(f"{name} (DPID {key}): "
                         + ", ".join(f"{r} {t}" for r, t in got["tables"].items())
                         + "; " + "; ".join(got["notes"]))
        config[item.key] = compiled
    if problems:
        return {"ok": False, "config": None, "notes": notes, "problems": problems}
    config = effective_config(manifest, config)
    failed = validate_config(manifest, config)
    if failed:
        return {"ok": False, "config": None, "notes": notes,
                "problems": [f"{who}'s compiled config fails its config_schema: {w}"
                             for w in failed]}
    if manifest.egress:
        targets, problems = egress_targets(manifest, config)
        if problems:
            return {"ok": False, "config": None, "notes": notes, "problems": problems}
        config[RESERVED] = {"egress": targets}
        notes.append("egress: " + "; ".join(f"{n} to {u}" for n, u in sorted(targets.items()))
                     + " (the only destinations its egress calls reach)")
    return {"ok": True, "config": config, "notes": notes, "problems": []}


def compile_set(items, switches) -> tuple:
    """``(notes, problems)``: each of *items* (`deploy_op.stage_set`'s, `channel.plan`'s
    *enabled* shape) given its compiled start-time config in place (``config``, removed where
    the app gets none); *notes* ``{app: [words]}``."""
    notes, problems = {}, []
    for item in items:
        got = compile_config(item["manifest"], item.get("config"), switches)
        notes[item["manifest"].name] = got["notes"]
        if not got["ok"]:
            problems += got["problems"]
            continue
        if got["config"] is None:
            item.pop("config", None)
        else:
            item["config"] = got["config"]
    return notes, problems
