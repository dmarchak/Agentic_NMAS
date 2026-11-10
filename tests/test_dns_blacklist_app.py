"""dns_blacklist (Lab 9 Objective 3, `lab/lab9/apps/dns_blacklist/`) against Mercury's app
contract, without a controller; its own tests run in the container harness on Python 3.5 and
3.9 (`scripts/nmas-harness test --app`), and here on Mercury's:

- **the app gate** passes every check it runs without the harness, on 3.9 and 3.5;
- **the manifest says what the code does,** read from the source: the name and version, the
  OpenFlow versions, the REST routes, the cookie, and the start-time config read at load;
- **what Mercury compiles is what the app takes:** with no network config at all, the compile
  for the recorded switches gives the ProCurve forward table 100 and the rest 0, and the one
  egress destination, Cloudflare's resolver, which the SDK's egress takes with the app's path;
- **the protected classes it owns are the config context's** (docs/LAB9_NETBOX_STEPS.md
  section 9: the classes whose owners name `app:dns_blacklist`), and its cookie overlaps no
  other Lab 9 app's.
"""

import ast
import importlib
import json
import os
import re
import sys

import pytest

from modules.apps import app_config, gate
from modules.apps.manifest import load_manifest
from modules.apps.sdk import mercury_app
from modules.platforms import profile
from tests.fixtures.sdn import ryu_recorded as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APPS = os.path.join(ROOT, "lab", "lab9", "apps")
APP = os.path.join(APPS, "dns_blacklist")
OWNER = "app:dns_blacklist"
PROCURVE = 56298109234905574
MAKER_DRIVER = {"Arista Networks": "arista_eos", "HP": "hp_procurve",
                "Nicira, Inc.": "ovs_linux"}
OWN = ("blacklist_logic", "blacklist_wire", "test_blacklist_logic", "test_blacklist_wire")


@pytest.fixture
def logic():
    """A loader of the app's own blacklist_logic, called in the test's body, so where the app
    is absent the test's own body fails rather than its setup."""
    sys.path.insert(0, APP)
    try:
        sys.modules.pop("blacklist_logic", None)
        yield lambda: importlib.import_module("blacklist_logic")
    finally:
        sys.path.remove(APP)
        for name in OWN:
            sys.modules.pop(name, None)


@pytest.mark.parametrize("python", [(3, 9), (3, 5)])
def test_the_app_gate_passes_every_check_it_can_run_without_the_harness(python):
    by_name = {c.name: c for c in gate.check(APP, python=python).checks}
    for check in ("manifest", "spec", "static", "examples", "asserts"):
        assert by_name[check].passed, (check, by_name[check].summary, by_name[check].details)
    assert "1 egress calls" in by_name["static"].summary
    for check in gate.HARNESS_CHECKS:
        assert not by_name[check].passed and by_name[check].summary == gate.HARNESS_NOT_RUN


def test_the_manifest_names_the_codes_versions_routes_cookie_and_start_config(logic):
    manifest = load_manifest(APP)
    logic = logic()
    with open(os.path.join(APP, "dns_blacklist.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    facts, routes, calls = {}, {}, []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("NAME", "VERSION"):
                facts[node.targets[0].id] = node.value.value
            elif node.targets[0].id == "OFP_VERSIONS":
                facts["versions"] = [e.value.id for e in node.value.elts]
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "id", "") == "route":
                    routes.setdefault(dec.args[1].right.value, []).extend(
                        m.value for m in dec.keywords[0].value.elts)
            if node.name == "__init__":
                calls += [(getattr(c.func.value, "id", ""), c.func.attr,
                           [getattr(a, "id", None) for a in c.args])
                          for c in ast.walk(node) if isinstance(c, ast.Call)
                          and isinstance(c.func, ast.Attribute)]
    assert (facts["NAME"], facts["VERSION"]) == (manifest.name, manifest.version) == \
        ("dns_blacklist", "0.1.0")
    assert facts["versions"] == ["ofproto_v1_3"] and manifest.openflow_versions == ("1.3",)
    assert routes == {e.path: list(e.methods) for e in manifest.rest.endpoints}
    assert int(manifest.owns_flows.cookie_prefix, 16) == logic.COOKIE_PREFIX
    assert int(manifest.owns_flows.cookie_mask, 16) == logic.COOKIE_MASK
    assert ("mercury_app", "start_config", ["NAME", "VERSION"]) in calls
    assert ("logic", "from_start_config", ["answer"]) in calls


def _recorded_switches():
    capture = R.RecordedRyu()
    out = []
    for dpid in capture.dpids():
        desc = capture.get(f"/stats/desc/{dpid}")[str(dpid)]
        out.append({"name": str(dpid), "dpid": dpid,
                    "selected": profile.select(MAKER_DRIVER[desc["mfr_desc"]],
                                               desc["sw_desc"])})
    return out


def test_the_compile_with_no_network_config_serves_every_switch_and_reaches_cloudflare(logic):
    logic = logic()
    switches = _recorded_switches()
    assert len(switches) == 5
    got = app_config.compile_config(load_manifest(APP), None, switches)
    assert got["ok"], got["problems"]
    url = got["config"][app_config.RESERVED]["egress"]["verdict_service"]
    assert url == "https://security.cloudflare-dns.com:443" and app_config.egress_problem(url) == ""
    config, why = logic.from_start_config({"ok": True, "path": "p", "config": {
        k: v for k, v in got["config"].items() if k != app_config.RESERVED}})
    assert why == ""
    assert logic.table_for(config, PROCURVE) == 100
    assert all(logic.table_for(config, s["dpid"]) == 0 for s in switches if s["dpid"] != PROCURVE)
    assert (config["fail_mode"], config["timeout_s"], config["block_ipv4"]) == ("open", 2.0, None)
    path = logic.verdict_path("malware.testcategory.com")
    assert mercury_app.PATH.match(path) and "/../" not in path
    assert config["timeout_s"] <= mercury_app.MAX_TIMEOUT_S


def test_it_owns_the_config_contexts_dns_classes_and_no_other_apps_cookie():
    with open(os.path.join(ROOT, "docs", "LAB9_NETBOX_STEPS.md"), encoding="utf-8") as fh:
        text = fh.read()
    section = text[text.index("## 9. The protected DNS and DHCP flows"):]
    block = re.search(r"```json\n(.*?)\n\s*```", section, re.S).group(1)
    classes = json.loads(block)["mercury"]["protected_flows"]
    owned = sorted(c["name"] for c in classes if OWNER in c["owners"])
    assert owned == ["dns", "dns-ipv6"] and len(classes) == 4
    mine = load_manifest(APP).owns_flows
    assert sorted(mine.classes) == owned
    for name in sorted(os.listdir(APPS)):
        other = os.path.join(APPS, name)
        if name == "dns_blacklist" or not os.path.isfile(os.path.join(other, "manifest.yml")):
            continue
        theirs = load_manifest(other).owns_flows
        if theirs is not None:
            mask = int(mine.cookie_mask, 16) & int(theirs.cookie_mask, 16)
            assert int(mine.cookie_prefix, 16) & mask != int(theirs.cookie_prefix, 16) & mask, name


def test_the_apps_own_tests_pass_on_mercurys_python():
    """Each test file the manifest lists, read when the test runs (never at collection, so
    the file collects where the app is absent and fails there by its own asserts)."""
    listed = load_manifest(APP).tests
    assert len(listed) >= 2, listed
    for test in listed:
        tests_dir = os.path.dirname(os.path.join(APP, test))
        module = os.path.splitext(os.path.basename(test))[0]
        sys.path[:0] = [tests_dir, APP]
        try:
            for name in OWN:
                sys.modules.pop(name, None)
            mod = importlib.import_module(module)
            found = [f for n, f in sorted(vars(mod).items())
                     if n.startswith("test_") and callable(f)]
            assert len(found) >= 8, test
            for f in found:
                f()
        finally:
            sys.path.remove(tests_dir)
            sys.path.remove(APP)
            for name in OWN:
                sys.modules.pop(name, None)
