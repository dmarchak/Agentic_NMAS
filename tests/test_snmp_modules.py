"""The routing-adjacency modules for snmp_exporter (staged run 5, 2026-09-30)
and the operator's append step, `scripts/nmas-snmp-add-modules`.

The fragment is the generator's output (prom/snmp-generator v0.29.0); these
tests pin what it walks against the tables the devices were MEASURED to
answer, and drive the append against a small exporter config in the host
file's shape (a header comment, `auths:`, then `modules:` last).
"""

import os
import subprocess
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAGMENT = os.path.join(ROOT, "deploy", "snmp_exporter", "routing-modules.yml")
SCRIPT = os.path.join(ROOT, "scripts", "nmas-snmp-add-modules")

HOST_SHAPE = """# WARNING: This file was auto-generated using snmp_exporter generator, manual changes will be lost.
auths:
  public_v2:
    community: not-the-real-one
    version: 2
modules:
  if_mib:
    walk:
    - 1.3.6.1.2.1.2
    metrics: []
  lldp:
    walk:
    - 1.0.8802.1.1.2.1.4.1.1.7
    metrics: []
"""


def _fragment():
    return yaml.safe_load("modules:\n" + open(FRAGMENT, encoding="utf-8").read())["modules"]


class TestTheFragment:
    def test_it_walks_exactly_the_measured_tables(self):
        mods = _fragment()
        assert sorted(mods) == ["cisco_bgp_peer2", "ospf", "ospfv3"]
        # C700 (2026-10-12): the OSPF walks narrowed to the state column (and the router-id
        # column its lookup reads); every label Mercury and the dashboards use is an index.
        assert mods["ospf"]["walk"] == ["1.3.6.1.2.1.14.10.1.3",             # ospfNbrRtrId
                                        "1.3.6.1.2.1.14.10.1.6"]             # ospfNbrState
        assert mods["ospfv3"]["walk"] == ["1.3.6.1.2.1.191.1.9.1.8"]         # ospfv3NbrState
        assert all(o.startswith("1.3.6.1.4.1.9.9.187.1.2.5.1.") for o in mods["cisco_bgp_peer2"]["walk"])
        assert [m["name"] for m in mods["ospf"]["metrics"]] == ["ospfNbrState"]
        assert [i["labelname"] for i in mods["ospfv3"]["metrics"][0]["indexes"]] == [
            "ospfv3NbrIfIndex", "ospfv3NbrIfInstId", "ospfv3NbrRtrId"]

    def test_each_asks_with_a_2_s_timeout_that_fits_the_scrape(self):
        """C700: a lost request waits 2 s, not the exporter's 5 s default; the worst per
        request (the first try and 3 retries) fits the routing jobs' 20 s scrape timeout."""
        for name, mod in _fragment().items():
            assert mod["timeout"] == "2s" and mod["retries"] == 3, name
            assert (mod["retries"] + 1) * 2 < 20

    def test_the_states_carry_their_names_for_the_value_mappings(self):
        mods = _fragment()
        state = next(m for m in mods["ospf"]["metrics"] if m["name"] == "ospfNbrState")
        assert state["enum_values"][4] == "twoWay" and state["enum_values"][8] == "full"
        assert [l["labelname"] for l in state["lookups"]] == ["ospfNbrRtrId"]
        bgp = next(m for m in mods["cisco_bgp_peer2"]["metrics"] if m["name"] == "cbgpPeer2State")
        assert bgp["enum_values"][6] == "established"
        assert [i["labelname"] for i in bgp["indexes"]] == ["cbgpPeer2RemoteAddr"]

    def test_it_carries_no_auth_and_no_community(self):
        text = open(FRAGMENT, encoding="utf-8").read()
        assert "auths" not in text and "community" not in text


class TestTheAppend:
    def _run(self, config, *extra):
        return subprocess.run([sys.executable, SCRIPT, "--config", str(config), *extra],
                              capture_output=True, text=True, timeout=60)

    def test_the_dry_run_writes_nothing(self, tmp_path):
        cfg = tmp_path / "snmp.yml"
        cfg.write_text(HOST_SHAPE)
        r = self._run(cfg)
        assert r.returncode == 0 and "dry run: nothing written" in r.stdout
        assert cfg.read_text() == HOST_SHAPE and len(list(tmp_path.iterdir())) == 1

    def test_apply_appends_backs_up_and_proves_the_rest_unchanged(self, tmp_path):
        cfg = tmp_path / "snmp.yml"
        cfg.write_text(HOST_SHAPE)
        os.chmod(cfg, 0o644)
        r = self._run(cfg, "--apply")
        assert r.returncode == 0, r.stderr
        assert "appended and proven: 5 module(s), the 2 before unchanged" in r.stdout
        text = cfg.read_text()
        assert text.startswith(HOST_SHAPE)                                   # a pure append
        got = yaml.safe_load(text)
        assert got["auths"] == yaml.safe_load(HOST_SHAPE)["auths"]
        assert sorted(got["modules"]) == ["cisco_bgp_peer2", "if_mib", "lldp", "ospf", "ospfv3"]
        backups = [p for p in tmp_path.iterdir() if p.name.startswith("snmp.yml.bak-routing-")]
        assert len(backups) == 1 and backups[0].read_text() == HOST_SHAPE
        assert "not-the-real-one" not in r.stdout + r.stderr

    def test_a_second_apply_is_refused_naming_the_modules(self, tmp_path):
        cfg = tmp_path / "snmp.yml"
        cfg.write_text(HOST_SHAPE)
        assert self._run(cfg, "--apply").returncode == 0
        once = cfg.read_text()
        r = self._run(cfg, "--apply")
        assert r.returncode == 1 and "already has module(s)" in r.stderr and cfg.read_text() == once

    def test_replace_swaps_the_routing_modules_in_place_and_proves_the_rest(self, tmp_path):
        """C700: the regenerated modules replace the ones the host holds, in place; every other
        module and key keeps its bytes."""
        cfg = tmp_path / "snmp.yml"
        old = {"ospf": {"walk": ["1.3.6.1.2.1.14.10"], "metrics": []},
               "ospfv3": {"walk": ["1.3.6.1.2.1.191.1.9"], "metrics": []},
               "cisco_bgp_peer2": {"walk": ["1.3.6.1.4.1.9.9.187.1.2.5.1.3"], "metrics": []}}
        # The host's shape: the old modules as entries of `modules:`, after the others.
        cfg.write_text(HOST_SHAPE + "".join(
            f"  {line}\n" for line in yaml.safe_dump(old, sort_keys=True).splitlines()))
        before = yaml.safe_load(cfg.read_text())
        assert sorted(before["modules"]) == ["cisco_bgp_peer2", "if_mib", "lldp", "ospf",
                                             "ospfv3"], "the floor: the old modules are there"
        dry = self._run(cfg, "--replace")
        assert dry.returncode == 0 and "would replace" in dry.stdout
        assert yaml.safe_load(cfg.read_text()) == before
        r = self._run(cfg, "--replace", "--apply")
        assert r.returncode == 0, r.stderr
        assert "replaced and proven" in r.stdout
        text = cfg.read_text()
        after = yaml.safe_load(text)
        # In place: each module once in the text, and every byte before them kept.
        for name in ("ospf", "ospfv3", "cisco_bgp_peer2"):
            assert text.count(f"\n  {name}:\n") == 1, name
        assert text.startswith(HOST_SHAPE)
        assert after["auths"] == before["auths"]
        assert after["modules"]["if_mib"] == before["modules"]["if_mib"]
        assert after["modules"]["lldp"] == before["modules"]["lldp"]
        for k, v in _fragment().items():
            assert after["modules"][k] == v
        assert "not-the-real-one" not in r.stdout + r.stderr

    def test_replace_refuses_a_module_the_config_lacks(self, tmp_path):
        cfg = tmp_path / "snmp.yml"
        cfg.write_text(HOST_SHAPE)
        r = self._run(cfg, "--replace", "--apply")
        assert r.returncode == 1 and "has no module(s)" in r.stderr
        assert cfg.read_text() == HOST_SHAPE

    def test_modules_not_last_is_refused(self, tmp_path):
        cfg = tmp_path / "snmp.yml"
        shape = HOST_SHAPE.replace("auths:", "tmp_auths:").replace("modules:\n", "modules:\n", 1)
        cfg.write_text(shape + "trailer:\n  x: 1\n")
        r = self._run(cfg, "--apply")
        assert r.returncode == 1 and "is not the last top-level key" in r.stderr
        assert cfg.read_text() == shape + "trailer:\n  x: 1\n"
