"""A network has one key (C1903, the operator's design of 2026-10-27): every store or reader
value that holds something per network is keyed by the network's one id
(`listref.network_id`, its lower-case slug), and every lookup in one goes through the resolver
(`listref.keyed`, or a reader's own function over it, `topology_graph.network_of`), which
takes either spelling and raises for a name no network answers to.

The defect this constrains: the Topology reader keyed its value by the display name
(``Default``), `network_model.observed` looked it up by whatever it was given, and a caller
holding the id (``default``) read "holds nothing for default" and lost every observed link.

**The shape, found by parsing** (never by matching text): in the product (`modules/`,
`routes/`, `scripts/`, `app.py`), within one function,

- a READ: ``.get(key)`` or ``[key]`` on a per-network map, which is an expression
  ``<x>.get("networks"|"lists")`` or ``<x>["networks"|"lists"]`` (``or {}`` around it allowed),
  or a name bound to one in the same function;
- a WRITE: ``name[key] = ...`` where *name* is the value of a ``"networks"`` or ``"lists"`` key
  of a dict literal built in the same function, or ``.setdefault(key, ...)`` on a per-network
  map, and *key* is not a call of `network_id`.

A literal string key (``out["error"]``) is not a network's name and is not counted.

**What the scan assumes stays true** (CLAUDE.md, populations by property): a per-network map
travels under the key ``networks`` or ``lists``; a lookup in one is in the function that took
it from its value. A map handed through a return value and read in another function (the RIP
reader's ``lists`` returned by `topology_graph.rip_answer`) is out of its sight: such a read is
fixed by hand and named in docs/ARCHITECTURE.md, Key Architecture Decisions, "A network has
one id, and every key is it". So is an in-process cache keyed by network (the network model's
`_CACHE` and `_CABLES`), which no stored value's key names.

`KNOWN_GAPS` are the stores still keyed by the display name at C1903 (each read or written by
the raw name; their conversion is a register row of its own): they only shrink, and each
one listed must still be found, so a fixed one leaves the list in the same commit.
`REGISTRY_EXEMPT` is the device-list registry itself, ``{display name: slug}``: the one map
whose key IS the display name, read to resolve a name to its id.
"""

import ast
import os

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The keys a per-network map travels under in a stored value.
MAP_KEYS = {"networks", "lists"}

#: The scan's population floor: the product files it parses (459 at C1903, 2026-10-27).
FILES_FLOOR = 450

#: (file, function, kind) -> the store, still keyed by the display name: they only shrink.
KNOWN_GAPS = {
    ("modules/attention.py", "_baseline_usability_row", "read"):
        "the baseline-usability reader's value, by list name",
    ("modules/netbox_jobs.py", "start_import.on_end", "read"):
        "NetBox sync status, by list name",
    ("modules/readers/baseline_usability.py", "read", "read"):
        "the baseline-usability reader's previous value, by list name",
    ("modules/readers/baseline_usability.py", "read", "write"):
        "the baseline-usability reader's value, by list name",
    ("modules/readers/endpoints.py", "read", "write"):
        "the endpoint reader's value, by list name (read through `listref.keyed` since C1903)",
    ("modules/readers/intent_format.py", "read", "read"):
        "the intent-format reader's previous value, by list name",
    ("modules/readers/intent_format.py", "read", "write"):
        "the intent-format reader's value, by list name",
    ("modules/readers/netbox_lag.py", "read", "write"):
        "the NetBox-lag reader's value, by network name",
    ("modules/readers/netbox_lag.py", "stored_for", "read"):
        "the NetBox-lag reader's value, by network name",
    ("modules/readers/remote_publication.py", "read", "write"):
        "the remote-publication reader's value, by list name",
    ("modules/readers/remote_publication.py", "status_for", "read"):
        "the remote-publication reader's value, by list name",
    ("modules/sdn/closed_loop.py", "detection_pack", "read"):
        "the SDN detection state, by network name (S7's classify, landed beside C1903)",
    ("modules/sdn/detect.py", "observe", "write"):
        "the SDN detection state, by network name",
    ("routes/netbox_v2.py", "_networks", "read"):
        "NetBox sync status, by list name",
    ("routes/v2.py", "_history_ctx", "read"):
        "the baseline-usability reader's value, by the page's network name",
}

#: (file, function) -> why: the device-list registry, keyed by the display name by definition.
REGISTRY_EXEMPT = {
    ("modules/device.py", "get_current_device_list"):
        "the registry, {display name: slug}, read to find the current list's slug",
    ("modules/device.py", "delete_device_list"):
        "the registry, {display name: slug}, read to find the deleted list's folder",
}


def product_files(root=ROOT) -> list:
    """Every tracked product source: Python under modules/ and routes/, app.py, and scripts/'
    Python programs (a `.py` file, or one whose first line names python)."""
    out = list(tracked("app.py", "modules", "routes", suffix=".py", root=root))
    for path in tracked("scripts", root=root):
        if path.endswith(".py"):
            out.append(path)
            continue
        if "." in os.path.basename(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                first = fh.readline()
        except (OSError, UnicodeDecodeError):
            continue
        if first.startswith("#!") and "python" in first:
            out.append(path)
    return sorted(set(out))


def _str(node) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _is_map(node, names: set) -> bool:
    """Is *node* a per-network map: ``x.get("networks")``, ``x["lists"]``, either ``or {}``,
    or a name bound to one in this function?"""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(_is_map(v, names) for v in node.values)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr in ("get", "setdefault") and node.args and _str(node.args[0]) \
            and node.args[0].value in MAP_KEYS:
        return True
    if isinstance(node, ast.Subscript) and _str(node.slice) and node.slice.value in MAP_KEYS:
        return True
    return isinstance(node, ast.Name) and node.id in names


def _own(scope):
    """*scope*'s nodes, not descending into a nested function or class (its own scope)."""
    todo = list(ast.iter_child_nodes(scope))
    while todo:
        node = todo.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            todo.extend(ast.iter_child_nodes(node))


def _scopes(tree):
    """``(qualified name, node)`` for the module and every function in it."""
    out = [("<module>", tree)]

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                out.append((name, child))
                walk(child, name + ".")
            elif isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}{child.name}.")
            else:
                walk(child, prefix)
    walk(tree, "")
    return out


def _keys_by_id(key) -> bool:
    """A write's key that is the network's one id: a call of `network_id`."""
    if not isinstance(key, ast.Call):
        return False
    f = key.func
    return (isinstance(f, ast.Name) and f.id == "network_id") or \
        (isinstance(f, ast.Attribute) and f.attr == "network_id")


def scan(source: str) -> list:
    """``[(function, kind, line)]``: every read or write of a per-network map by a raw key."""
    found = []
    for name, scope in _scopes(ast.parse(source)):
        nodes = list(_own(scope))
        names, built = set(), set()
        for n in nodes:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 \
                    and isinstance(n.targets[0], ast.Name) and _is_map(n.value, set()):
                names.add(n.targets[0].id)
            if isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values):
                    if k is not None and _str(k) and k.value in MAP_KEYS \
                            and isinstance(v, ast.Name):
                        built.add(v.id)
        for n in nodes:
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr == "get" and n.args and not _str(n.args[0]) \
                    and _is_map(n.func.value, names):
                found.append((name, "read", n.lineno))
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr == "setdefault" and n.args and not _str(n.args[0]) \
                    and not _keys_by_id(n.args[0]) and _is_map(n.func.value, names):
                found.append((name, "write", n.lineno))
            elif isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Load) \
                    and _is_map(n.value, names) and not isinstance(n.slice, (ast.Constant,
                                                                              ast.Slice,
                                                                              ast.UnaryOp)):
                found.append((name, "read", n.lineno))
            elif isinstance(n, (ast.Assign, ast.AugAssign)):
                for t in (n.targets if isinstance(n, ast.Assign) else [n.target]):
                    if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) \
                            and t.value.id in built and not _str(t.slice) \
                            and not _keys_by_id(t.slice):
                        found.append((name, "write", n.lineno))
    return found


def findings(root=ROOT, files=None) -> list:
    """``[(file, function, kind, line)]`` over the product, the registry's own reads left out."""
    out = []
    for path in files if files is not None else product_files(root):
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        for fn, kind, line in scan(source):
            if (rel, fn) not in REGISTRY_EXEMPT:
                out.append((rel, fn, kind, line))
    return sorted(set(out))


# --------------------------------------------------------------------------------- the tests

def test_the_scan_finds_a_planted_read_and_write_by_a_raw_name():
    """Purpose: the scan is able to fail. A read and a write keyed by a raw network name,
    planted, are both found; the same through the resolver are not."""
    planted = (
        "def read(population):\n"
        "    networks = {}\n"
        "    for name, ref, hosts in population():\n"
        "        networks[name] = 1\n"
        "    return {'networks': networks}\n"
        "def look(value, network):\n"
        "    return (value.get('networks') or {}).get(network)\n"
        "def look_bound(value, network):\n"
        "    nets = value.get('lists') or {}\n"
        "    return nets[network]\n"
        "def state(doc, network):\n"
        "    return doc.setdefault('networks', {}).setdefault(network, {})\n")
    assert sorted((f, k) for f, k, _l in scan(planted)) == [
        ("look", "read"), ("look_bound", "read"), ("read", "write"), ("state", "write")]
    resolved = (
        "def read(population):\n"
        "    networks = {}\n"
        "    for name, ref, hosts in population():\n"
        "        networks[listref.network_id(ref)] = 1\n"
        "    return {'networks': networks}\n"
        "def look(value, network):\n"
        "    return listref.keyed(value.get('networks'), network)\n"
        "def state(doc, network):\n"
        "    return doc.setdefault('networks', {}).setdefault(listref.network_id(network), {})\n")
    assert not scan(resolved)


def test_no_store_or_reader_is_keyed_by_a_raw_network_name_beyond_the_known_gaps():
    """Purpose: the shape is constrained across the product. Every per-network map read or
    written by a raw key is a known gap (only shrinking), and every known gap is still found,
    over a population of at least `FILES_FLOOR` files."""
    files = product_files()
    assert len(files) >= FILES_FLOOR, f"the scan parsed {len(files)} files"
    found = {(f, fn, kind) for f, fn, kind, _line in findings(files=files)}
    new = sorted(found - set(KNOWN_GAPS))
    assert not new, ("a store or reader keyed by a raw network name (key it by "
                     "`listref.network_id` and read it through `listref.keyed`): " + repr(new))
    fixed = sorted(set(KNOWN_GAPS) - found)
    assert not fixed, f"no longer found, so take them out of KNOWN_GAPS: {fixed!r}"


def test_the_registry_exemption_names_the_registrys_own_reads():
    """Purpose: the exemption cannot hide anything else. Each exempt function still reads the
    registry by name (the scan finds it when not exempted), and both are in modules/device.py."""
    with open(os.path.join(ROOT, "modules", "device.py"), encoding="utf-8") as fh:
        raw = {fn for fn, _k, _l in scan(fh.read())}
    assert {fn for _f, fn in REGISTRY_EXEMPT} <= raw
    assert {f for f, _fn in REGISTRY_EXEMPT} == {"modules/device.py"}
