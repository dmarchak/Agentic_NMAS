"""fabric_forwarding v0 against Mercury's app contract (the SDN platform design revision 6,
section 14 and section 12's I-2; revision 7, section 11c.6; P7a). The app is the network's code,
`lab/lab9/apps/fabric_forwarding/`; its behaviour on real Ryu and Open vSwitch is the container
harness's acceptance (`lab/lab9/fabric_forwarding_acceptance.py`), and this file holds
what Mercury checks without a controller:

- **the app gate** (`modules/apps/gate.py`) passes every check it runs without the harness on
  the controller's Python, 3.5 (C2646): manifest, spec, static, examples and asserts; and the
  3.5 check bites on this folder (a planted f-string refused);
- **the manifest says what the code does:** its OpenFlow versions are the app's
  `OFP_VERSIONS`, its REST endpoints the app's routes, its `owns_flows` the cookie the app
  writes, all read from the source;
- **conformance (T17):** with the app's 1.3 pin, the controller still speaks to every switch
  the bring-up recorded (`modules/apps/conformance.py` over each switch's own version text);
- **table placement (C2601):** every flow the app builds for Mercury's compile of the ProCurve
  (forward table 100, punt table 200) lands, by `modules/sdn/placement.py` on its measured
  pipeline, in the table the config names; on Open vSwitch's recorded tables, in table 0;
- **the recorded ring:** the app's tests' inline copy of the ring is the capture's links, and
  its paths over the capture are the shortest ones, rerouting when a ring link goes.
"""

import ast
import os
import shutil
import sys

import pytest

from modules.apps import conformance, gate
from modules.apps.manifest import load_manifest
from modules.platforms import profile
from modules.sdn import placement
from tests.fixtures.sdn import ryu_recorded as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "lab", "lab9", "apps", "fabric_forwarding")
CAPTURE = R.RecordedRyu()
HARNESS = R.RecordedRyu(R.HARNESS)
#: Each recorded switch maker and the driver Mercury knows it by (tests/test_platform_profiles.py).
MAKER_DRIVER = {"Arista Networks": "arista_eos", "HP": "hp_procurve",
                "Nicira, Inc.": "ovs_linux"}
PROCURVE = 56298109234905574
H4, H6 = "192.0.2.13", "2001:db8::14"


@pytest.fixture(scope="module")
def logic():
    """The app's fabric_logic (and fabric_paths), imported from its folder as Ryu imports it."""
    sys.path.insert(0, APP)
    try:
        import fabric_logic
        yield fabric_logic
    finally:
        sys.path.remove(APP)


def _source(name: str) -> ast.Module:
    with open(os.path.join(APP, name), encoding="utf-8") as fh:
        return ast.parse(fh.read())


def _recorded_links() -> set:
    """The capture's links, both directions, as `(dpid, port, dpid, port)`."""
    return {(int(link["src"]["dpid"], 16), int(link["src"]["port_no"], 16),
             int(link["dst"]["dpid"], 16), int(link["dst"]["port_no"], 16))
            for link in CAPTURE.get("/v1.0/topology/links")}


def _recorded_graph(logic, without=()):
    links = {l for l in _recorded_links() if (l[0], l[2]) not in without
             and (l[2], l[0]) not in without}
    ports = {}
    for (a, pa, _b, _pb) in links:
        ports.setdefault(a, set()).add(pa)
    return logic.graph_of(links, ports, CAPTURE.dpids())


# ───────────────────────────────────────────────────────────── the app gate

def test_the_app_gate_passes_every_check_it_can_run_without_the_harness():
    verdict = gate.check(APP, python=(3, 5))
    by_name = {c.name: c for c in verdict.checks}
    for name in ("manifest", "spec", "static", "examples", "asserts"):
        assert by_name[name].passed, (name, by_name[name].summary, by_name[name].details)
    assert "allowed on Python 3.5" in by_name["static"].summary
    assert "each of 3 examples is covered" == by_name["examples"].summary
    # The checks that run the app's code wait for the harness, and say so: never a pass.
    for name in gate.HARNESS_CHECKS:
        assert not by_name[name].passed and by_name[name].summary == gate.HARNESS_NOT_RUN


def test_the_python_35_check_refuses_an_f_string_planted_in_the_app(tmp_path):
    folder = tmp_path / "fabric_forwarding"
    shutil.copytree(APP, folder)
    with open(folder / "fabric_logic.py", "a", encoding="utf-8") as fh:
        fh.write('\n\ndef planted(x):\n    return f"{x}"\n')
    by_name = {c.name: c for c in gate.check(str(folder), python=(3, 5)).checks}
    assert not by_name["static"].passed
    assert any("fabric_logic.py line" in d and "f-string" in d
               for d in by_name["static"].details), by_name["static"].details


# ───────────────────────────────────────────────────────────── the manifest says what the code does

def test_the_manifest_pins_the_versions_the_routes_and_the_cookie_the_code_uses(logic):
    manifest = load_manifest(APP)
    tree = _source("fabric_forwarding.py")
    versions, routes, prefix = [], {}, None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and [t.id for t in node.targets
                                             if isinstance(t, ast.Name)] == ["OFP_VERSIONS"]:
            versions = [e.value.id for e in node.value.elts]
        if isinstance(node, ast.Assign) and [t.id for t in node.targets
                                             if isinstance(t, ast.Name)] == ["NAME"]:
            prefix = "/" + node.value.value
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "id", "") == "route":
                    path = dec.args[1].right.value
                    methods = [m.value for m in dec.keywords[0].value.elts]
                    routes.setdefault(path, []).extend(methods)
    assert versions == ["ofproto_v1_3"] and list(manifest.openflow_versions) == ["1.3"]
    assert prefix == manifest.rest.prefix
    assert routes == {e.path: list(e.methods) for e in manifest.rest.endpoints}
    assert int(manifest.owns_flows.cookie_prefix, 16) == logic.COOKIE_PREFIX
    assert int(manifest.owns_flows.cookie_mask, 16) == logic.COOKIE_MASK
    assert all(logic.is_ours(logic.cookie(k)) for k in logic.KINDS)


def test_every_switch_the_bring_up_recorded_accepts_the_apps_one_version():
    switches = []
    for dpid in CAPTURE.dpids():
        desc = CAPTURE.get(f"/stats/desc/{dpid}")[str(dpid)]
        switches.append({"name": str(dpid), "selected": profile.select(
            MAKER_DRIVER[desc["mfr_desc"]], desc["sw_desc"])})
    got = conformance.check([load_manifest(APP)], switches)
    assert got["ok"], got["problems"]
    assert got["offered"] == ["1.3"] and len(got["checked"]) == 5
    assert all(c["common"] == ["1.3"] for c in got["checked"])


# ───────────────────────────────────────────────────────────── table placement

def _placement_flow(key, actions) -> dict:
    """An app flow in `placement`'s terms."""
    out = []
    for act in actions:
        if act[0] == "GOTO":
            out.append({"type": "GOTO_TABLE", "table_id": act[1]})
        elif act[0] == "CONTROLLER":
            out.append({"type": "OUTPUT", "port": "CONTROLLER"})
        else:
            out.append({"type": "OUTPUT", "port": act[1]})
    return {"match": dict(key[2]), "actions": out}


def _app_flows(logic, config_data):
    config, problems = logic.parse_config(config_data)
    assert problems == []
    graph = logic.graph_of(set(), {}, [PROCURVE])
    flows, problems = logic.desired_flows(config, graph, {H4: (PROCURVE, 5),
                                                          H6: (PROCURVE, 6)})
    assert problems == []
    return flows[PROCURVE]


def test_on_the_procurve_each_flow_lands_in_the_table_the_compile_names(logic):
    flows = _app_flows(logic, {"switches": {str(PROCURVE): {"forward_table": 100,
                                                            "punt_table": 200}}})
    tables = placement.from_profile(profile.select("hp_procurve", "K.16.02.0020")["entry"])
    kinds = set()
    for key, (actions, cookie) in sorted(flows.items()):
        got = placement.place(_placement_flow(key, actions), tables)
        assert got["ok"] and got["table_id"] == key[0], (key, actions, got)
        kinds.add(logic.KINDS[logic.kind_of(cookie)])
        if key[0] == 100:
            assert got["notes"] == []                   # hardware
        else:
            assert got["notes"] == ["table 200 is a software table, at 100 packets a second "
                                    "(the platform profile)"]
    assert kinds == {"miss", "arp", "goto", "deliver"}
    hosts = [k for k, (_a, c) in flows.items() if logic.kind_of(c) == logic.DELIVER]
    assert sorted(dict(k[2]).get("ipv4_dst", dict(k[2]).get("ipv6_dst")) for k in hosts) == \
        sorted([H4, H6])


def test_on_open_vswitchs_recorded_tables_every_flow_lands_in_table_0(logic):
    flows = _app_flows(logic, {"default_tables": {"forward_table": 0, "punt_table": 0}})
    tables = placement.from_features(HARNESS.driver().table_features(3))
    for key, (actions, _cookie) in sorted(flows.items()):
        got = placement.place(_placement_flow(key, actions), tables)
        assert got["ok"] and got["table_id"] == key[0] == 0, (key, got)
    assert not [k for k, (_a, c) in flows.items() if logic.kind_of(c) == logic.GOTO]


# ───────────────────────────────────────────────────────────── the recorded ring

def test_the_apps_tests_copy_the_recorded_ring_exactly():
    tree = _source(os.path.join("tests", "test_fabric_paths.py"))
    names = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Tuple):
            for t, v in zip(node.targets[0].elts, node.value.elts):
                names[t.id] = ast.literal_eval(v)
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            names[node.targets[0].id] = node.value
    copied = set()
    for elt in names["RECORDED"].elts:
        a, pa, b, pb = (names[e.id] if isinstance(e, ast.Name) else ast.literal_eval(e)
                        for e in elt.elts)
        copied |= {(a, pa, b, pb), (b, pb, a, pa)}
    assert copied == _recorded_links() and len(copied) == 10


def test_over_the_capture_paths_are_shortest_and_reroute_when_a_ring_link_goes(logic):
    graph = _recorded_graph(logic)
    from fabric_paths import shortest_path

    assert shortest_path(graph, 3, 4) == [3, 4]
    hops, problems = logic.next_hops(graph, 4)
    assert problems == [] and logic.forwarding_loop(hops, 4) is None
    assert set(hops) == set(CAPTURE.dpids()) - {4}
    cut = _recorded_graph(logic, without=[(3, 4)])
    assert shortest_path(cut, 3, 4) == [3, 2214744208935, PROCURVE, 4]
    hops, problems = logic.next_hops(cut, 4)
    assert problems == [] and logic.forwarding_loop(hops, 4) is None
    assert hops[3] == (2214744208935, 1)
