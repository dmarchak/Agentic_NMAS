"""The network's own controller apps as managed apps (C2670; lab/lab9/apps/of_versions/ and
switch_quirks/, beside fabric_forwarding/; the SDN platform design revision 6, sections 10 and
12; revision 7, section 11c.6), held to Mercury's app contract without a controller. Their
behaviour on real Ryu and Open vSwitch is the container harness's.

- **the app gate** passes every check it runs without the harness, on the controller's Python
  as the design records it (3.9) and on the oldest measured (3.5);
- **the manifest says what the code does,** read from the source: the name and version, the
  OpenFlow versions (`OFP_VERSIONS`), the REST routes, and the cookie the app writes;
- **each app's own tests pass** here, on Mercury's Python, as well as in the harness;
- **the set loads and connects:** of_versions before switch_quirks (`requires`), and with
  fabric_forwarding every switch the bring-up recorded accepts what the controller offers
  (conformance, T17);
- **what Mercury compiles is what each app takes** (C2760): the compile for the recorded
  switches, read by each app's own `parse_config`, gives the ProCurve forward 100, punt 200
  and meter 100 (C2601) and every other switch table 0; switch_quirks' LLDP flow lands, by
  `modules/sdn/placement`, in the table its config names.
"""

import ast
import importlib
import os
import sys

import pytest

from modules.apps import app_config, channel, conformance, gate
from modules.apps.manifest import load_manifest
from modules.platforms import profile
from modules.sdn import placement
from tests.fixtures.sdn import ryu_recorded as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS = os.path.join(ROOT, "lab", "lab9", "apps")
NAMES = ("of_versions", "switch_quirks", "fabric_forwarding")
#: Each app's logic module (its own name, so no two apps' modules collide in one Ryu).
LOGIC = {"of_versions": "of_versions_logic", "switch_quirks": "quirks_logic",
         "fabric_forwarding": "fabric_logic"}
CAPTURE = R.RecordedRyu()
MAKER_DRIVER = {"Arista Networks": "arista_eos", "HP": "hp_procurve",
                "Nicira, Inc.": "ovs_linux"}
PROCURVE = 56298109234905574
WIRE = {"ofproto_v1_0": "1.0", "ofproto_v1_3": "1.3"}


def folder(name):
    return os.path.join(APPS, name)


def source(name, file):
    with open(os.path.join(folder(name), file), encoding="utf-8") as fh:
        return ast.parse(fh.read())


def module_from(name, module):
    """*module* imported from app *name*'s folder, as Ryu imports it (the folder on the
    path), and forgotten afterwards so no other test sees it."""
    sys.path.insert(0, folder(name))
    try:
        sys.modules.pop(module, None)
        return importlib.import_module(module)
    finally:
        sys.path.remove(folder(name))


@pytest.fixture(autouse=True)
def _forget_app_modules():
    yield
    for module in list(LOGIC.values()) + ["fabric_paths", "test_of_versions_logic",
                                          "test_quirks_logic", "test_fabric_logic",
                                          "test_fabric_paths"]:
        sys.modules.pop(module, None)


def recorded_switches():
    out = []
    for dpid in CAPTURE.dpids():
        desc = CAPTURE.get(f"/stats/desc/{dpid}")[str(dpid)]
        out.append({"name": str(dpid), "dpid": dpid,
                    "selected": profile.select(MAKER_DRIVER[desc["mfr_desc"]],
                                               desc["sw_desc"])})
    return out


# ── the app gate ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("python", [(3, 9), (3, 5)])
@pytest.mark.parametrize("name", NAMES)
def test_the_app_gate_passes_every_check_it_can_run_without_the_harness(name, python):
    by_name = {c.name: c for c in gate.check(folder(name), python=python).checks}
    for check in ("manifest", "spec", "static", "examples", "asserts"):
        assert by_name[check].passed, (check, by_name[check].summary, by_name[check].details)
    assert f"allowed on Python {python[0]}.{python[1]}" in by_name["static"].summary
    for check in gate.HARNESS_CHECKS:
        assert not by_name[check].passed and by_name[check].summary == gate.HARNESS_NOT_RUN


# ── the manifest says what the code does ─────────────────────────────────────────────────────

def _code_facts(name):
    tree = source(name, f"{name}.py")
    facts = {"routes": {}}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 \
                and isinstance(node.targets[0], ast.Name):
            target = node.targets[0].id
            if target == "OFP_VERSIONS":
                facts["versions"] = [WIRE[e.value.id] for e in node.value.elts]
            elif target in ("NAME", "VERSION") and isinstance(node.value, ast.Constant):
                facts[target] = node.value.value
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "id", "") == "route":
                    path = dec.args[1].right.value
                    methods = [m.value for m in dec.keywords[0].value.elts]
                    facts["routes"].setdefault(path, []).extend(methods)
    return facts


@pytest.mark.parametrize("name", NAMES)
def test_the_manifest_names_the_codes_versions_routes_and_cookie(name):
    manifest = load_manifest(folder(name))
    facts = _code_facts(name)
    assert (facts["NAME"], facts["VERSION"]) == (manifest.name, manifest.version) and \
        manifest.name == name
    assert facts["versions"] == list(manifest.openflow_versions)
    assert manifest.rest.prefix == "/" + name
    assert facts["routes"] == {e.path: list(e.methods) for e in manifest.rest.endpoints}
    logic = module_from(name, LOGIC[name])
    if manifest.owns_flows is None:
        assert not hasattr(logic, "COOKIE_PREFIX")
    else:
        assert int(manifest.owns_flows.cookie_prefix, 16) == logic.COOKIE_PREFIX
        assert int(manifest.owns_flows.cookie_mask, 16) == logic.COOKIE_MASK
        assert all(logic.is_ours(logic.cookie(k)) for k in logic.KINDS)


@pytest.mark.parametrize("name", NAMES)
def test_an_app_mercury_compiles_for_reads_its_start_time_config_at_load(name):
    """An app whose manifest declares `compiled` calls `mercury_app.start_config(NAME,
    VERSION)` in its RyuApp's `__init__` and hands the answer to its logic's
    `from_start_config` (C2729); one that declares nothing compiled makes no such call."""
    tree = source(name, f"{name}.py")
    calls = []
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef)
                   and n.name == "__init__"):
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    owner = getattr(node.func.value, "id", "")
                    calls.append((owner, node.func.attr,
                                  [getattr(a, "id", None) for a in node.args]))
    reads = [c for c in calls if c[:2] == ("mercury_app", "start_config")]
    if load_manifest(folder(name)).compiled:
        assert reads == [("mercury_app", "start_config", ["NAME", "VERSION"])], calls
        assert [c for c in calls if c[:2] == ("logic", "from_start_config")] == \
            [("logic", "from_start_config", ["answer"])]
    else:
        assert reads == []


def test_of_versions_pins_exactly_the_versions_its_logic_reports():
    logic = module_from("of_versions", "of_versions_logic")
    assert [logic.TEXT[w] for w in logic.PINNED] == ["1.0", "1.3"]
    assert _code_facts("of_versions")["versions"] == ["1.0", "1.3"]


def test_the_cookies_of_the_apps_never_overlap():
    owned = []
    for name in NAMES:
        m = load_manifest(folder(name))
        if m.owns_flows is not None:
            owned.append((int(m.owns_flows.cookie_prefix, 16), int(m.owns_flows.cookie_mask, 16)))
    assert len(owned) == 2
    (p1, m1), (p2, m2) = owned
    assert (p1 & m1 & m2) != (p2 & m1 & m2)


# ── each app's own tests ─────────────────────────────────────────────────────────────────────

def _app_tests():
    out = []
    for name in NAMES:
        for test in load_manifest(folder(name)).tests:
            out.append((name, test))
    return out


@pytest.mark.parametrize("name, test", _app_tests())
def test_each_apps_own_tests_pass_on_mercurys_python(name, test):
    tests_dir = os.path.dirname(os.path.join(folder(name), test))
    module = os.path.splitext(os.path.basename(test))[0]
    sys.path.insert(0, folder(name))
    sys.path.insert(0, tests_dir)
    try:
        sys.modules.pop(module, None)
        mod = importlib.import_module(module)
    finally:
        sys.path.remove(tests_dir)
        sys.path.remove(folder(name))
    found = [f for n, f in sorted(vars(mod).items()) if n.startswith("test_") and callable(f)]
    assert len(found) >= 2, (name, test)
    for f in found:
        f()


# ── the set loads and connects ───────────────────────────────────────────────────────────────

def test_of_versions_loads_before_switch_quirks_and_the_set_connects_every_recorded_switch():
    manifests = [load_manifest(folder(n)) for n in ("fabric_forwarding", "switch_quirks",
                                                    "of_versions")]
    ordered = [m.name for m in channel.load_order(manifests)]
    assert ordered.index("of_versions") < ordered.index("switch_quirks")
    switches = recorded_switches()
    got = conformance.check(manifests, switches)
    assert got["ok"], got["problems"]
    assert got["offered"] == ["1.3"] and len(got["checked"]) == 5
    pair = conformance.check(manifests[1:], switches)
    assert pair["ok"] and pair["offered"] == ["1.0", "1.3"]


def test_switch_quirks_alone_is_refused_for_want_of_of_versions():
    with pytest.raises(channel.ChannelRefused) as raised:
        channel.load_order([load_manifest(folder("switch_quirks"))])
    assert "of_versions" in str(raised.value)


# ── what Mercury compiles is what each app takes ─────────────────────────────────────────────

def test_switch_quirks_takes_the_compile_for_the_recorded_switches():
    got = app_config.compile_config(load_manifest(folder("switch_quirks")), None,
                                    recorded_switches())
    assert got["ok"], got["problems"]
    logic = module_from("switch_quirks", "quirks_logic")
    config, problems = logic.parse_config(got["config"])
    assert problems == []
    assert config["switches"][PROCURVE] == {"forward_table": 100, "punt_table": 200,
                                            "meter_table": 100}
    others = [d for d in CAPTURE.dpids() if d != PROCURVE]
    assert len(others) == 4
    for dpid in others:
        assert config["switches"][dpid] == {"forward_table": 0, "punt_table": 0,
                                            "meter_table": 0}
        assert logic.desired_flows(config["switches"][dpid], 0x04) == ({}, [])


def test_fabric_forwarding_takes_the_compile_and_serves_every_recorded_switch():
    got = app_config.compile_config(load_manifest(folder("fabric_forwarding")), None,
                                    recorded_switches())
    assert got["ok"], got["problems"]
    logic = module_from("fabric_forwarding", "fabric_logic")
    config, why = logic.from_start_config({"ok": True, "path": "p", "config": got["config"]})
    assert why == ""
    assert logic.tables_for(config, PROCURVE) == (100, 200)
    assert all(logic.tables_for(config, d) == (0, 0) for d in CAPTURE.dpids() if d != PROCURVE)
    assert config["settle_s"] == 3.0 and config["dedup_s"] == 0.5


def test_switch_quirks_lldp_flow_lands_where_its_config_names_on_the_procurve():
    logic = module_from("switch_quirks", "quirks_logic")
    flows, problems = logic.desired_flows({"forward_table": 100, "punt_table": 200,
                                           "meter_table": 100}, 0x04)
    assert problems == []
    tables = placement.from_profile(profile.select("hp_procurve", "K.16.02.0020")["entry"])
    (key, (actions, _cookie)), = [(k, v) for k, v in flows.items() if k[1] != 0]
    got = placement.place({"match": dict(key[2]),
                           "actions": [{"type": "OUTPUT", "port": "CONTROLLER"}]}, tables)
    assert got["ok"] and got["table_id"] == key[0] == 200
    assert actions == (logic.CONTROLLER,)
