"""C149: every NetBox write names who made it.

Measured on the host 2026-09-28: 56 of the 58 modifications NMAS had ever
recorded read `unattributed`. `record_modified()` takes the actor from
`netbox_guard.for_list(list_name, actor=...)`, and no caller passed one, so
every write a verified person made through the import, the removal or
onboarding was recorded as nobody's. NetBox's own changelog cannot fill it:
every NMAS write there is the operator's token (C100).
"""

import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The functions that write to NetBox on a person's behalf, and the guard
#: context that carries the actor into the modification record.
WRITERS = {"sync_list_to_netbox", "sync_all_lists_to_netbox", "remove_list_from_netbox",
           "remove_device_from_netbox", "create_netbox_record"}


def _sources():
    for base in ("modules", "routes", "scripts", "app.py"):
        path = os.path.join(ROOT, base)
        if os.path.isfile(path):
            yield path
            continue
        for d, _dirs, files in os.walk(path):
            for f in files:
                p = os.path.join(d, f)
                if f.endswith(".py") or (base == "scripts" and "." not in f):
                    yield p


def _calls(tree, names):
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in names:
                yield node


def _missing_actor(source_text, names, label="x"):
    tree = ast.parse(source_text)
    found, missing = 0, []
    for call in _calls(tree, names):
        found += 1
        if not any(k.arg == "actor" for k in call.keywords):
            missing.append(f"{label}:{call.lineno}")
    return found, missing


def _scan(names):
    found, missing = 0, []
    for path in _sources():
        try:
            text = open(path, encoding="utf-8").read()
            if "def " not in text and "import" not in text:
                continue
            f, m = _missing_actor(text, names, os.path.relpath(path, ROOT))
        except (SyntaxError, UnicodeDecodeError):
            continue
        found += f
        missing += m
    return found, missing


def test_every_guard_context_carries_the_actor():
    found, missing = _scan({"for_list"})
    assert found >= 6, found
    assert missing == [], missing


def test_every_call_of_a_netbox_writer_passes_the_actor():
    found, missing = _scan(WRITERS)
    assert found >= 14, found
    assert missing == [], missing


def test_the_planted_omission_is_found():
    """The control: the scan sees a call that leaves the actor out, and
    leaves one that passes it alone."""
    found, missing = _missing_actor(
        "sync_list_to_netbox('L', [])\n"
        "remove_list_from_netbox('L', actor=a)\n"
        "with g.for_list('L'):\n    pass\n",
        WRITERS | {"for_list"})
    assert found == 3 and missing == ["x:1", "x:3"], (found, missing)


def test_the_actor_given_is_the_actor_recorded():
    """The value path, through the real guard and the real record: inside
    `for_list(actor=...)` a modification names that person; outside it, the
    record says `unattributed` rather than blank (the floor, and the state
    the host held 56 times)."""
    from modules import netbox_guard as g

    fields = {"description": {"before": "a", "after": "b"}}
    with g.for_list("c149", actor="p@example.invalid"):
        g.record_modified("c149", "dcim/devices", 7, fields, name="r1")
    with g.for_list("c149"):
        g.record_modified("c149", "dcim/devices", 8, fields, name="r2")
    data, reason = g.read_modified()
    assert not reason, reason
    rows = {r["id"]: r["actor"] for r in data["c149"]["dcim/devices"]}
    assert rows == {7: "p@example.invalid", 8: "unattributed"}, rows
