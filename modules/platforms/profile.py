"""Platform capability profiles (the SDN platform design revision 6, section 6 D; P2a's minimum):
one YAML file per platform family in `profiles/`, each naming the netmiko drivers it covers and
its entries, one per OS version range, selected by the device's own version text (its `show
version`, `ovs-vsctl --version` or the switch's OpenFlow description, `sw_desc`).

What an entry holds, in P2a:
- `openflow.versions`: the versions the switch's hello offers;
- `openflow.hello.rejects_above`: the highest version whose hello it accepts (None: it answers
  any hello by its version bitmap and refuses none);
- `openflow.port_state.live_reliable`: whether LIVE means working (it is never read for health
  either way: health is LINK_DOWN, C2602);
- `openflow.pipeline` (`discover` or `single_table`) and, where measured, `openflow.tables`: the
  flow tables a flow may be placed in (`modules/sdn/placement.py`).

What P2 adds, read by the OpenFlow templates (`modules/sdn/openflow_templates.py`, as
``profile.openflow.<key>``):
- `openflow.bind_change_requires`: `agent_restart` when a change to the bound ports takes effect
  only after the OpenFlow agent is shut down and started again (C2599), or null;
- `openflow.openflow_ports_require`: what each OpenFlow port needs besides binding, from
  `PORT_REQUIREMENTS` (`lldp_off`: the switch's own LLDP agent consumes the controller's
  probes, C2600), or an empty list;
- `openflow.port_numbering`: how the switch numbers its OpenFlow ports, from `PORT_NUMBERING`
  (`interface_number`, `port_number`, or `add_order`, where NetBox's number must be requested,
  C2603).

What P3 adds (B, the protected set): `openflow.instance_takes`, which ports an OpenFlow
instance takes, from `INSTANCE_TAKES` (`named_ports`, or `vlan_members`: every port carrying
its member VLAN, C2588), so the render names every port the switch will hand the controller
and refuses a protected one (`protected.ports_refusal`).

**Every value names how it is known.** `sources` maps a value's path to the keys of the file's
`measurements` (a register row with its evidence, a fixture, or the vendor's guide), and a value
no source settles is listed in `unconfirmed` with `unconfirmed_why`. `problems` refuses a file
with a value that does neither, a source key it does not define, or a range that is not one.

**A device whose version no entry covers is refused by name** (`select`), never given a
neighbouring entry: "no platform profile covers <family> <version>". No code here names a
vendor: the files do.
"""

import os
import re

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")
#: The OpenFlow versions a profile may name.
OPENFLOW_VERSIONS = ("1.0", "1.1", "1.2", "1.3", "1.4", "1.5")
PIPELINES = ("discover", "single_table")
#: What a change to the bound ports needs (`openflow.bind_change_requires`), or null.
BIND_CHANGES = ("agent_restart",)
#: What an OpenFlow port may need besides binding (`openflow.openflow_ports_require`).
PORT_REQUIREMENTS = ("lldp_off",)
#: How a switch numbers its OpenFlow ports (`openflow.port_numbering`).
PORT_NUMBERING = ("interface_number", "port_number", "add_order")
#: Which ports an OpenFlow instance takes (`openflow.instance_takes`, C2588): only the ports
#: the configuration names (`named_ports`: EOS's `bind interface`, OVS's `add-port`), or every
#: port carrying its member VLAN, tagged or untagged, named or not (`vlan_members`).
INSTANCE_TAKES = ("named_ports", "vlan_members")
#: A table's list-valued fields; each is a list or the word "any".
TABLE_LISTS = ("match", "match_excludes", "eth_types", "instructions", "apply_actions",
               "apply_setfield", "next_tables")
TABLE_FIELDS = frozenset(TABLE_LISTS) | {"table_id", "reserved", "hardware", "max_entries",
                                         "software_pps"}
ANY = "any"
_LEADING = re.compile(r"^\s*(?:(?P<train>[A-Za-z]+)\.)?(?P<numbers>[0-9]+(?:\.[0-9]+)*)")


class Refused(ValueError):
    """A profile file that cannot be used, or a version no profile covers, in words."""


def names() -> list:
    return sorted(f[:-4] for f in os.listdir(HERE) if f.endswith(".yml"))


def load(name: str) -> dict:
    import yaml
    if name not in names():
        raise Refused(f"no platform profile is named {name!r}: {', '.join(names())}")
    with open(os.path.join(HERE, f"{name}.yml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def parse_os(text) -> tuple:
    """`(train, numbers)` from a version text: `4.17.0F (Indigo-2 OpenFlow)` is `("", (4, 17,
    0))`, `K.16.02.0020` is `("K", (16, 2, 20))`, `3.3.4` is `("", (3, 3, 4))`. Raises Refused
    for a text with no leading version."""
    found = _LEADING.match(str(text or ""))
    if not found:
        raise Refused(f"{text!r} is not a version (it starts with no number)")
    return ((found.group("train") or "").upper(),
            tuple(int(n) for n in found.group("numbers").split(".")))


def _bound(text) -> tuple:
    return tuple(int(n) for n in str(text).split("."))


def covers(os_range: dict, version_text) -> bool:
    """Whether *version_text* is in *os_range* (`{train?, from, below}`: from <= v < below)."""
    train, numbers = parse_os(version_text)
    if (os_range.get("train") or "").upper() != train:
        return False
    return _bound(os_range["from"]) <= numbers < _bound(os_range["below"])


def _paths(node, prefix="") -> list:
    """Every leaf's dotted path under *node* (a list's items are one leaf)."""
    if isinstance(node, dict):
        out = []
        for key, value in node.items():
            out += _paths(value, f"{prefix}.{key}" if prefix else str(key))
        return out
    return [prefix]


def _settled(path: str, settled: set) -> bool:
    """A path is settled when it or an ancestor of it is sourced or listed unconfirmed."""
    parts = path.split(".")
    return any(".".join(parts[:i]) in settled for i in range(1, len(parts) + 1))


def _table_problems(tables) -> list:
    if not isinstance(tables, list) or not tables:
        return ["openflow.tables is a non-empty list of tables"]
    out, seen = [], set()
    for i, table in enumerate(tables):
        if not isinstance(table, dict):
            out.append(f"openflow.tables[{i}] is a mapping, not {table!r}")
            continue
        tid = table.get("table_id")
        if not isinstance(tid, int) or isinstance(tid, bool) or not 0 <= tid <= 0xFE:
            out.append(f"openflow.tables[{i}]'s table_id {tid!r} is not a table id (0 to 254)")
        elif tid in seen:
            out.append(f"openflow.tables names table {tid} twice")
        seen.add(tid)
        unknown = sorted(set(table) - TABLE_FIELDS)
        if unknown:
            out.append(f"table {tid} has no field {', '.join(unknown)}")
        for key in TABLE_LISTS:
            if key in table and table[key] != ANY and not isinstance(table[key], list):
                out.append(f"table {tid}'s {key} is a list or {ANY!r}, not {table[key]!r}")
    return out


def problems(doc: dict) -> list:
    """What is wrong with profile *doc*, in words (empty when it can be used)."""
    out = []
    if not doc.get("drivers") or not isinstance(doc.get("drivers"), list):
        out.append("it names no drivers")
    if not doc.get("family"):
        out.append("it names no family")
    measurements = doc.get("measurements") or {}
    for key, m in sorted(measurements.items()):
        missing = [f for f in ("record", "what", "evidence", "read")
                   if not str((m or {}).get(f) or "").strip()]
        if missing:
            out.append(f"measurement {key!r} names no {', '.join(missing)}")
    entries = doc.get("entries")
    if not isinstance(entries, list) or not entries:
        return out + ["it has no entries"]
    for i, entry in enumerate(entries):
        where = f"entry {i + 1}"
        os_range = entry.get("os") or {}
        try:
            if _bound(os_range["from"]) >= _bound(os_range["below"]):
                out.append(f"{where}'s range is empty ({os_range['from']} to below "
                           f"{os_range['below']})")
        except (KeyError, ValueError):
            out.append(f"{where}'s os is {{from, below}} as dotted numbers, not {os_range!r}")
        of = entry.get("openflow") or {}
        versions = of.get("versions")
        if not isinstance(versions, list) or not versions \
                or any(v not in OPENFLOW_VERSIONS for v in versions):
            out.append(f"{where}'s openflow.versions are from {', '.join(OPENFLOW_VERSIONS)}, "
                       f"not {versions!r}")
        above = (of.get("hello") or {}).get("rejects_above", "absent")
        if above == "absent" or (above is not None and above not in OPENFLOW_VERSIONS):
            out.append(f"{where}'s openflow.hello.rejects_above is a version or null, not "
                       f"{above!r}")
        if of.get("pipeline") not in PIPELINES:
            out.append(f"{where}'s openflow.pipeline is one of {', '.join(PIPELINES)}, not "
                       f"{of.get('pipeline')!r}")
        if "tables" in of:
            out += [f"{where}: {p}" for p in _table_problems(of["tables"])]
        if "bind_change_requires" in of and of["bind_change_requires"] is not None \
                and of["bind_change_requires"] not in BIND_CHANGES:
            out.append(f"{where}'s openflow.bind_change_requires is one of "
                       f"{', '.join(BIND_CHANGES)} or null, not {of['bind_change_requires']!r}")
        if "openflow_ports_require" in of and (
                not isinstance(of["openflow_ports_require"], list)
                or any(r not in PORT_REQUIREMENTS for r in of["openflow_ports_require"])):
            out.append(f"{where}'s openflow.openflow_ports_require is a list from "
                       f"{', '.join(PORT_REQUIREMENTS)}, not {of['openflow_ports_require']!r}")
        if "port_numbering" in of and of["port_numbering"] not in PORT_NUMBERING:
            out.append(f"{where}'s openflow.port_numbering is one of "
                       f"{', '.join(PORT_NUMBERING)}, not {of['port_numbering']!r}")
        if "instance_takes" in of and of["instance_takes"] not in INSTANCE_TAKES:
            out.append(f"{where}'s openflow.instance_takes is one of "
                       f"{', '.join(INSTANCE_TAKES)}, not {of['instance_takes']!r}")
        sources = entry.get("sources") or {}
        for path, keys in sorted(sources.items()):
            for key in keys or []:
                if key not in measurements:
                    out.append(f"{where}: {path} cites {key!r}, which the file does not define")
        unconfirmed = entry.get("unconfirmed") or []
        unknown = sorted(set(entry) - {"os", "openflow", "sources", "unconfirmed",
                                       "unconfirmed_why", "note"})
        if unknown:
            out.append(f"{where} has no field {', '.join(unknown)}")
        if unconfirmed and not entry.get("unconfirmed_why"):
            out.append(f"{where} lists unconfirmed values and does not say why")
        settled = set(sources) | {u.split("[")[0] for u in unconfirmed}
        if of.get("pipeline") == "discover":
            settled.add("openflow.pipeline")       # it claims nothing: E reads the pipeline
        for path in _paths({"openflow": of}):
            if not _settled(path, settled):
                out.append(f"{where}: {path} names no source and is not listed unconfirmed")
    return out


def for_driver(driver: str):
    """The profile name covering netmiko *driver*, or None."""
    for name in names():
        if driver in (load(name).get("drivers") or []):
            return name
    return None


def select(driver: str, version_text) -> dict:
    """`{"ok": True, "profile", "family", "entry"}` for the entry covering *version_text* on
    *driver*, or `{"ok": False, "error"}` naming the driver, the version and the ranges there
    are. A profile with problems is refused, naming them."""
    name = for_driver(driver)
    if name is None:
        return {"ok": False, "error": f"no platform profile covers the driver {driver!r} "
                                      f"(profiles: {', '.join(names())})"}
    doc = load(name)
    found = problems(doc)
    if found:
        return {"ok": False, "error": f"the platform profile {name} cannot be used: "
                                      + "; ".join(found)}
    try:
        parse_os(version_text)
    except Refused as exc:
        return {"ok": False, "error": str(exc)}
    for entry in doc["entries"]:
        if covers(entry["os"], version_text):
            return {"ok": True, "profile": name, "family": doc["family"], "entry": entry}
    ranges = ", ".join(range_words(e["os"]) for e in doc["entries"])
    return {"ok": False, "error": f"no platform profile covers {doc['family']} "
                                  f"{version_text}: {name} covers {ranges}"}


def range_words(os_range: dict) -> str:
    train = f"{os_range['train']}." if os_range.get("train") else ""
    return f"{train}{os_range['from']} to below {train}{os_range['below']}"


def offered_versions(entry: dict) -> list:
    return list(entry["openflow"]["versions"])


def rejects_above(entry: dict):
    """The highest OpenFlow version whose hello the switch accepts, or None for none refused."""
    return entry["openflow"]["hello"]["rejects_above"]


def tables(entry: dict):
    """The entry's measured flow tables, or None where the pipeline is to be discovered."""
    return entry["openflow"].get("tables")


#: What `value` answers for a path the entry does not hold (distinct from a held null).
ABSENT = object()


def value(entry: dict, path: str):
    """The entry's value at dotted *path* (``openflow.port_numbering``), or `ABSENT`."""
    node = entry
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return ABSENT
        node = node[part]
    return node
