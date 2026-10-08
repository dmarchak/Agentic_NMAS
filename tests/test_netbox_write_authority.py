"""C155: every NetBox write names the confirmation it stands on, and the check
is WHERE THE WRITE HAPPENS.

The one-shot token was consumed by the NetBox tab's routes before they called
the writer, and the chokepoints checked only the master switch, so onboarding,
Abandon, the host scripts and list deletion's cascade wrote on the switch
alone. Now a real write with no declared authority is refused at the
chokepoint, and each record row stores the authority beside the actor: WHO,
and ON WHAT BASIS.
"""

import ast
import os

import pytest

from tests.source_index import tracked

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def writes_on(monkeypatch):
    from modules import netbox_guard
    monkeypatch.setattr(netbox_guard, "writes_allowed", lambda: True)
    return netbox_guard


def test_a_real_write_with_no_authority_is_refused_at_the_chokepoint(writes_on):
    g = writes_on
    with g.for_list("Lab", actor="p@example.invalid"):
        with pytest.raises(g.NetBoxWriteUnauthorised) as exc:
            g.assert_writes_allowed("DELETE dcim/devices")
    assert "declares no authority" in str(exc.value)


def test_a_declared_authority_passes_and_a_dry_run_needs_none(writes_on):
    """The floors: the check does not refuse everything, and a preview
    (which writes nothing) is never refused for want of one."""
    g = writes_on
    with g.for_list("Lab", authority="Verify by p@example.invalid"):
        g.assert_writes_allowed("POST dcim/devices")
    with g.dry_run(), g.for_list("Lab"):
        g.assert_writes_allowed("POST dcim/devices")


def test_the_switch_off_still_refuses_first(monkeypatch):
    from modules import netbox_guard as g
    monkeypatch.setattr(g, "writes_allowed", lambda: False)
    with g.for_list("Lab", authority="x"):
        with pytest.raises(g.NetBoxWriteBlocked) as exc:
            g.assert_writes_allowed("POST x")
    assert not isinstance(exc.value, g.NetBoxWriteUnauthorised)


def test_the_records_say_who_and_on_what_basis(writes_on):
    g = writes_on
    fields = {"description": {"before": "a", "after": "b"}}
    with g.for_list("c155", actor="p@example.invalid", authority="Abandon by p@example.invalid"):
        g.record_created("c155", "dcim/devices", 41, name="bp1")
        g.record_modified("c155", "dcim/devices", 41, fields, name="bp1")
    row = g.get_created("c155", "dcim/devices")["dcim/devices"][0]
    assert (row["actor"], row["authority"]) == ("p@example.invalid",
                                                 "Abandon by p@example.invalid"), row
    data, _ = g.read_modified()
    mod = data["c155"]["dcim/devices"][-1]
    assert (mod["actor"], mod["authority"]) == ("p@example.invalid", "Abandon by p@example.invalid")
    g.forget_created("c155")


def _for_list_calls_missing_authority():
    found, missing = 0, []
    for base in ("modules", "routes", "scripts", "app.py"):
        path = os.path.join(ROOT, base)
        files = [path] if os.path.isfile(path) else [
            p for p in tracked(path)
            if p.endswith(".py") or (base == "scripts" and "." not in os.path.basename(p))]
        for p in files:
            try:
                tree = ast.parse(open(p, encoding="utf-8").read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                    if name == "for_list":
                        found += 1
                        if not any(k.arg == "authority" for k in node.keywords):
                            missing.append(f"{os.path.relpath(p, ROOT)}:{node.lineno}")
    return found, missing


def test_every_guard_context_in_the_program_declares_an_authority():
    """By construction: the writer functions' contexts pass the authority
    they are given, and the scripts name their --apply. (A dry run needs
    none, and the gate checks the real write, so this is the reading aid;
    the refusal above is the enforcement.)"""
    found, missing = _for_list_calls_missing_authority()
    assert found >= 10, found
    assert missing == [], missing
