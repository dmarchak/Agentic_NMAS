"""T5 (the SDN platform design revision 6, section 15; section 4's "how every is held"): every
function that sends to a device, a controller or an app endpoint reaches the protected set's
guard (`modules/protected.py`) before it sends, or is declared, with why, as one whose send can
change no protected kind, or is a named gap with its register row.

**The populations, each defined by a property, never a list of names:**
- **device sends:** C101's command-string scan (`tests/test_session_write_guard._writer_sites`):
  every command the program sends that the read-only allowlist refuses, config-mode sends and
  saves included, grouped by the module-level function holding the send;
- **controller sends:** every call, outside the driver itself, of a `ControllerDriver` method
  whose own body writes (`_driver_writes`, read from modules/sdn/drivers/base.py by parsing: the
  public methods calling ``self._write``, ``self._apply`` or ``self._call("apply", ...)``), on a
  receiver that is not an imported module;
- **HTTP writes in the SDN, app and job code** (an app endpoint's policy push would be one): every
  ``.request``/``.post``/``.put``/``.patch``/``.delete`` call under modules/sdn, modules/apps and
  modules/jobs, which may live only in the driver's one channel (`ControllerDriver._http`).

**Reaching the guard** is read off the code: the send's function, or every function of its
module that calls it, calls the declared planner, and the planner calls the declared guard
function, which calls ``protected.<...>``. A planted sender the scan does not know fails it, and
so does a planner that stops asking.
"""

import ast
import os
import re
import sys

import pytest

from tests.source_index import tracked
from tests.test_session_write_guard import _writer_sites

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRIVER = "modules/sdn/drivers/base.py"

#: Each send that reaches B: (sender's file, its module-level function) -> (the planner the
#: sender's operation runs first, in the same file; the function that asks B, file and name).
GUARDED = {
    # The flow-operation core: SDN › Flows, the closed loop's responses and their re-apply all
    # send through `_send` (and `_rollback`'s undo of what landed), after `plan`, which asks
    # `protected.flow_refusal` itself (C2379).
    ("modules/sdn/flow_ops.py", "_send"): ("plan", ("modules/sdn/flow_ops.py", "plan")),
    ("modules/sdn/flow_ops.py", "_rollback"): ("plan", ("modules/sdn/flow_ops.py", "plan")),
    # An Open vSwitch server's OpenFlow configuration: `apply` plans again, and the plan renders
    # through `openflow_templates.render`, which asks `protected.ports_refusal` (C2588, C2589).
    ("modules/sdn/ovs_config.py", "apply"): ("plan",
                                             ("modules/sdn/openflow_templates.py", "render")),
    # A vendor switch's OpenFlow configuration (Lab 9 Objective 2, C2902): `_cli_apply` plans
    # again through `_cli_plan`, which renders through `openflow_templates.render` (B's
    # `protected.ports_refusal`) before the differences are computed.
    ("modules/sdn/openflow_config.py", "_cli_apply"): (
        "_cli_plan", ("modules/sdn/openflow_templates.py", "render")),
}

#: Sends that can change no protected kind (no interface, VLAN, prefix, address or flow), each
#: with why. A send here that starts to change one moves to GUARDED.
CHANGES_NO_PROTECTED_KIND = {
    ("modules/commands.py", "_run"): "the one send of a command its caller chose: the reads, "
                                     "Tier 2's clears and the OSPF reset (each declared below "
                                     "by its caller); request text reaches it only as an "
                                     "allowlisted read (tests/test_device_text_is_refused.py)",
    ("modules/device_reload.py", "reload_device"): "a reload changes no configuration (its "
                                                   "planned-restart window is its own rule)",
    ("modules/heal/propose.py", "reset"): "an OSPF process reset names no interface, VLAN or "
                                          "flow, and changes no configuration",
    ("modules/nsot/credential_rotation.py", "push_rotation"): "an account's secret, never an "
                                                              "interface, VLAN or flow",
    ("modules/nsot/onboard.py", "persist_on_device"): "write memory saves what is running and "
                                                      "changes nothing",
    ("modules/nsot/onboard.py", "remove_rw_communities"): "SNMP read-write communities only",
    ("modules/nsot/onboard.py", "send_profile_program"): "the monitoring profile's SNMP, "
                                                         "logging and NTP lines at onboarding",
    ("modules/nsot/privileged.py", "apply"): "Tier 2's clears (counters, ARP, logging, OSPF "
                                             "processes): no configuration changes",
    ("modules/nsot/privileged.py", "run_clear"): "a BGP session clear: no configuration changes",
    ("scripts/nmas-removal-probe", "main"): "a measured probe the operator runs on a staged "
                                            "device, outside the product",
    ("scripts/nmas-tier2-probe", "measure"): "a measured probe the operator runs, outside the "
                                             "product",
}

#: Sends that can change a protected kind and do not ask B yet, each with the register row that
#: wires it in (CLAUDE.md: a known-gap list only shrinks; tests/ratchet_lists.py). Each keeps
#: its own older rule meanwhile, named.
GUARD_GAPS = {
    ("modules/pipeline.py", "_push_via_netmiko"): "C2782 (B for the Cisco pipeline; removal's "
                                                  "management rule and the repair-path class "
                                                  "stand meanwhile)",
    ("modules/pipeline.py", "_restore_config"): "C2782 (B for the Cisco pipeline's rollback)",
    ("modules/heal/bounce.py", "send"): "C2783 (B for the port bounce; its path_refusal reads "
                                        "the device's management interface meanwhile)",
    ("modules/apps/transport.py", "send"): "C2784 (B for H: an app's owned classes against "
                                           "NetBox's owners, at the app deploy's plan)",
}

#: Calls of a name the driver writes with whose receiver is not a controller driver, each with
#: what it is.
NOT_A_CONTROLLER = {
    ("modules/heal/act.py", "src.apply"): "self-healing's Cisco source (heal.act), a device op",
    ("modules/heal/propose.py", "src.apply"): "self-healing's Cisco source, a device op",
    ("modules/heal/dampening.py", "src.apply"): "the dampening proposal's Cisco source",
}

#: The one place an HTTP write may be made in the SDN, app and job code.
HTTP_CHANNEL = (DRIVER, "_http")
HTTP_VERBS = ("request", "post", "put", "patch", "delete")


def _parse(rel: str):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _functions(tree) -> dict:
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef,
                                                          ast.AsyncFunctionDef))}


def _calls(func) -> set:
    """The names *func* calls: ``f(...)`` as ``f``, ``m.f(...)`` as ``m.f`` and ``f``."""
    out = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
                if isinstance(f.value, ast.Name):
                    out.add(f"{f.value.id}.{f.attr}")
    return out


def device_sends() -> set:
    """``{(file, module-level function)}`` holding a device send (C101's population)."""
    return {(rel, chain[-1].name) for rel, chain, _text, _line in _writer_sites() if chain}


def _driver_writes() -> set:
    """The ControllerDriver's public methods whose own body writes."""
    cls = next(n for n in _parse(DRIVER).body
               if isinstance(n, ast.ClassDef) and n.name == "ControllerDriver")
    out = set()
    for m in cls.body:
        if not isinstance(m, ast.FunctionDef) or m.name.startswith("_"):
            continue
        for node in ast.walk(m):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                    isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                if node.func.attr in ("_write", "_apply") or (
                        node.func.attr == "_call" and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value == "apply"):
                    out.add(m.name)
    return out


def _module_aliases(tree) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.asname or a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            out |= {a.asname or a.name for a in node.names}
    return out


def _files(*dirs) -> list:
    files = tracked(*dirs, suffix=".py", root=ROOT)
    return [os.path.relpath(f if os.path.isabs(f) else os.path.join(ROOT, f), ROOT)
            for f in files]


def _enclosing(tree) -> dict:
    """node -> its module-level function's name."""
    out = {}
    for func in _functions(tree).values():
        for node in ast.walk(func):
            out[node] = func.name
    return out


def controller_sends() -> set:
    """``{(file, module-level function, receiver.method)}``: each call of a driver write."""
    writes = _driver_writes()
    out = set()
    for rel in ["app.py"] + _files("modules", "routes"):
        if rel == DRIVER:
            continue
        tree = _parse(rel)
        aliases, owner = _module_aliases(tree), _enclosing(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in writes):
                continue
            recv = node.func.value
            if isinstance(recv, ast.Name) and recv.id in aliases:
                continue                              # a module's own function, not a driver
            said = f"{recv.id if isinstance(recv, ast.Name) else '?'}.{node.func.attr}"
            out.add((rel, owner.get(node, "<module>"), said))
    return out


def http_writes() -> set:
    """``{(file, module-level function)}`` making an HTTP write in the SDN, app and job code."""
    out = set()
    for rel in _files("modules/sdn", "modules/apps", "modules/jobs"):
        tree = _parse(rel)
        owner = {}
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for m in node.body:
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        for sub in ast.walk(m):
                            owner[sub] = m.name
        owner.update(_enclosing(tree))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                    node.func.attr in HTTP_VERBS and not (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id in ("requests_mock",)):
                recv = node.func.value
                if isinstance(recv, ast.Name) and recv.id in ("os", "shutil", "dict", "self"):
                    continue
                out.add((rel, owner.get(node, "<module>")))
    return out


def _asks_protected(rel: str, func: str) -> bool:
    calls = _calls(_functions(_parse(rel))[func])
    return any(c.startswith("protected.") for c in calls)


def _reaches(rel: str, sender: str, planner: str) -> list:
    """Why *sender* in *rel* does not run after *planner*, or ``[]``: it calls the planner,
    or every function of its module calling it does."""
    funcs = _functions(_parse(rel))
    if planner in _calls(funcs[sender]):
        return []
    callers = [n for n, f in funcs.items() if n != sender and sender in _calls(f)]
    if not callers:
        return [f"{rel}:{sender} calls no {planner} and nothing in its module calls it"]
    return [f"{rel}:{c} calls {sender} without calling {planner}" for c in callers
            if planner not in _calls(funcs[c])]


# --------------------------------------------------------------------------- the scan

def test_every_device_send_is_guarded_declared_or_a_named_gap():
    found = device_sends()
    assert len(found) >= 12, f"the device-send scan found {len(found)}: too few to trust"
    known = set(GUARDED) | set(CHANGES_NO_PROTECTED_KIND) | set(GUARD_GAPS)
    unknown = sorted(found - known)
    assert not unknown, ("these functions send to a device and neither ask B "
                         "(modules/protected.py) nor are declared: " + ", ".join(
                             f"{f}:{n}" for f, n in unknown))
    gone = sorted(k for k in set(CHANGES_NO_PROTECTED_KIND) | set(GUARD_GAPS) if k not in found)
    assert not gone, f"declared senders the scan no longer finds (remove them): {gone}"


def test_every_controller_send_is_guarded_or_not_a_controller():
    found = controller_sends()
    assert len(found) >= 2, f"the controller-send scan found {len(found)}: too few to trust"
    for rel, func, said in sorted(found):
        if (rel, said) in NOT_A_CONTROLLER:
            continue
        assert (rel, func) in GUARDED, (
            f"{rel}:{func} sends to a controller ({said}) and does not ask B "
            "(modules/protected.py)")
    gone = sorted(k for k in NOT_A_CONTROLLER if not any((r, s) == k for r, _f, s in found))
    assert not gone, f"declared receivers the scan no longer finds (remove them): {gone}"


def test_http_writes_in_sdn_and_app_code_are_only_the_driver_s_channel():
    found = http_writes()
    assert HTTP_CHANNEL in found, "the scan does not find the driver's own channel"
    assert found == {HTTP_CHANNEL}, (
        "an HTTP write outside ControllerDriver._http in the SDN, app or job code (an app "
        "endpoint's push, say) must go through the guarded path: "
        f"{sorted(found - {HTTP_CHANNEL})}")


@pytest.mark.parametrize("sender", sorted(GUARDED), ids=lambda s: f"{s[0]}:{s[1]}")
def test_each_guarded_send_runs_after_a_planner_that_asks_b(sender):
    planner, (guard_file, guard) = GUARDED[sender]
    assert _reaches(sender[0], sender[1], planner) == []
    chain = _calls(_functions(_parse(sender[0]))[planner])
    assert guard_file == sender[0] and guard == planner or guard in chain, (
        f"{sender[0]}:{planner} does not call {guard_file}:{guard}")
    assert _asks_protected(guard_file, guard), f"{guard_file}:{guard} asks nothing of B"


def test_each_gap_names_its_row():
    """Each gap opens with a register row's number, and that row is in the register (open or
    closed): a placeholder or a typed number no row holds is not a row."""
    with open(os.path.join(ROOT, "docs", "OPEN_FINDINGS.md"), encoding="utf-8") as fh:
        rows = set(re.findall(r"^\| (C\d{4}) \|", fh.read(), re.M))
    assert len(rows) >= 1000, f"the register's rows read: {len(rows)}, too few to trust"
    for sender, why in GUARD_GAPS.items():
        rid = why.split()[0]
        assert re.fullmatch(r"C\d{4}", rid) and rid in rows, (
            f"{sender}'s gap names no register row: {why!r}")


# --------------------------------------------------------------------------- shown able to fail

PLANTED_DEVICE = '''
def sneak(conn):
    conn.send_config_set(["interface Management1", "shutdown"])
'''

PLANTED_CONTROLLER = '''
def sneak(made):
    drv = made["driver"]
    return drv.add_flow(1, {"match": {}})
'''

PLANTED_HTTP = '''
import requests
def push(url, body):
    return requests.post(url, json=body)
'''


def _planted(tmp_path, monkeypatch, rel, text):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    me = sys.modules[__name__]
    real_parse, real_files = me._parse, me._files

    def parse(r):
        return ast.parse(text) if r == rel else real_parse(r)

    def files(*dirs):
        return real_files(*dirs) + [rel]
    monkeypatch.setattr(me, "_parse", parse)
    monkeypatch.setattr(me, "_files", files)


def test_a_planted_controller_sender_is_found(tmp_path, monkeypatch):
    _planted(tmp_path, monkeypatch, "modules/sdn/planted_writer.py", PLANTED_CONTROLLER)
    assert ("modules/sdn/planted_writer.py", "sneak", "drv.add_flow") in controller_sends()
    with pytest.raises(AssertionError, match="planted_writer.py:sneak sends to a controller"):
        test_every_controller_send_is_guarded_or_not_a_controller()


def test_a_planted_http_write_is_found(tmp_path, monkeypatch):
    _planted(tmp_path, monkeypatch, "modules/apps/planted_push.py", PLANTED_HTTP)
    assert ("modules/apps/planted_push.py", "push") in http_writes()
    with pytest.raises(AssertionError, match="planted_push"):
        test_http_writes_in_sdn_and_app_code_are_only_the_driver_s_channel()


def test_a_planted_device_sender_is_found(monkeypatch):
    me = sys.modules[__name__]
    real = me.device_sends
    monkeypatch.setattr(me, "device_sends",
                        lambda: real() | {("modules/planted.py", "sneak")})
    with pytest.raises(AssertionError, match="modules/planted.py:sneak"):
        me.test_every_device_send_is_guarded_declared_or_a_named_gap()


def test_a_planner_that_stops_asking_b_is_found(monkeypatch):
    me = sys.modules[__name__]
    real = me._asks_protected
    monkeypatch.setattr(me, "_asks_protected",
                        lambda rel, func: False if func == "plan" else real(rel, func))
    with pytest.raises(AssertionError, match="asks nothing of B"):
        test_each_guarded_send_runs_after_a_planner_that_asks_b(
            ("modules/sdn/flow_ops.py", "_send"))
