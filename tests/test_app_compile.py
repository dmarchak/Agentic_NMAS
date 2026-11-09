"""The compile step (C2760; modules/apps/app_config.py): an app's start-time config made from its
manifest's `compiled` and the expected switches' platform profiles, passed by the controller
app deploy's plan to `channel.plan`, its bytes in the plan's hash, and drawn masked in the
preview.

Cases, each planted:
- each table role is the first table of the profile's measured pipeline that takes the role's
  flows: the ProCurve's forward 100, punt 200 and meter 100 (C2601, by
  `modules/sdn/placement`), table 0 for a profile that records no tables (said so);
- a switch whose profile is not selected, a DPID that is not a whole number, a network config
  setting a compiled key, a pipeline whose forward table cannot go on to its punt table, a
  role no table takes, and a result its schema refuses are each refused by name;
- an app with nothing compiled and no config gets no file; the network's config is the base
  and the schema's defaults are filled;
- the manifest's `compiled` takes only a key its schema declares and the roles Mercury knows;
- the plan stages what was compiled, its sha256 in the request, so a profile that moves a
  table moves the plan's hash; a compile refused refuses the preview;
- the preview card draws each config masked, with what each switch's tables came from and
  whether it is new, changed or as the record last sent.
"""

import copy
import hashlib
import json

import pytest

from modules.apps import app_config, channel, deploy_op
from modules.apps.manifest import TABLE_ROLES, ManifestError, parse_manifest
from modules.platforms import profile
from tests.test_controller_deploy_op import CTL, NET, FakeSources, registry
from tests.test_sdn_connections import networks  # noqa: F401 - the fixture

PROCURVE = 56298109234905574
HP = {"name": "sw-hp", "dpid": PROCURVE,
      "selected": profile.select("hp_procurve", "K.16.02.0020")}
OVS = {"name": "sw-ovs", "dpid": 3, "selected": profile.select("ovs_linux", "3.3.4")}
EOS = {"name": "sw-eos", "dpid": 2214744208935,
       "selected": profile.select("arista_eos", "4.17.0F")}
BASE = ("name: quirky\nversion: 1.0.0\ncontrollers:\n  ryu: \">=4.34\"\n"
        "openflow_versions: [\"1.0\", \"1.3\"]\nrest:\n  prefix: /quirky\n  endpoints:\n"
        "    - path: /health\n      methods: [GET]\n")
SCHEMA = ("config_schema:\n  type: object\n  additionalProperties: false\n  properties:\n"
          "    switches: {type: object}\n    settle_s: {type: number, default: 3}\n")


def manifest(compiled="  - key: switches\n    per_switch: [forward_table, punt_table, "
                      "meter_table]\n", schema=SCHEMA):
    return parse_manifest(BASE + schema + ("compiled:\n" + compiled if compiled else ""))


# ── the roles ────────────────────────────────────────────────────────────────────────────

def test_the_roles_are_the_manifests_and_each_carries_flows():
    assert set(app_config.ROLES) == set(TABLE_ROLES) == set(app_config.ROLE_WORDS)
    assert all(app_config.ROLES[r] for r in TABLE_ROLES)


def test_the_procurves_measured_pipeline_places_forward_100_punt_200_meter_100():
    got = app_config.table_roles(HP["selected"], TABLE_ROLES)
    assert got["ok"] is True
    assert got["tables"] == {"forward_table": 100, "punt_table": 200, "meter_table": 100}
    assert got["notes"][0].startswith("from the platform profile aruba_os_switch (HP ProCurve /"
                                      " ArubaOS-Switch K.16.02 to below K.16.03)")
    assert "punt_table 200 is a software table, at 100 packets a second" in got["notes"]


@pytest.mark.parametrize("switch", [OVS, EOS])
def test_a_profile_with_no_recorded_tables_compiles_table_0_and_says_so(switch):
    got = app_config.table_roles(switch["selected"], ("forward_table", "punt_table"))
    assert got["ok"] is True and got["tables"] == {"forward_table": 0, "punt_table": 0}
    assert got["notes"] == [f"table 0 for forward_table, punt_table: the platform profile "
                            f"{switch['selected']['profile']} ({switch['selected']['family']} "
                            f"{profile.range_words(switch['selected']['entry']['os'])}) records "
                            "no tables (its pipeline is discovered), so OpenFlow's first table"]


def _with_tables(tables):
    sel = copy.deepcopy(HP["selected"])
    sel["entry"]["openflow"]["tables"] = tables
    return sel


def test_a_forward_table_that_cannot_reach_the_punt_table_is_refused():
    tables = copy.deepcopy(HP["selected"]["entry"]["openflow"]["tables"])
    tables[1]["next_tables"] = [150]
    got = app_config.table_roles(_with_tables(tables), ("forward_table", "punt_table"))
    assert got["ok"] is False
    assert got["error"].startswith("the forward table 100 cannot go on to the punt table 200 on "
                                   "the platform profile aruba_os_switch")
    assert "table 100 cannot go to table 200 (its next tables: [150])" in got["error"]


def test_a_role_no_table_takes_names_every_tables_refusal():
    tables = copy.deepcopy(HP["selected"]["entry"]["openflow"]["tables"][:2])
    got = app_config.table_roles(_with_tables(tables), ("punt_table",))
    assert got["ok"] is False
    assert got["error"].startswith("no table of the platform profile aruba_os_switch")
    assert "takes the table miss, ARP and LLDP to the controller (punt_table)" in got["error"]
    assert "table 0 is reserved" in got["error"] and "table 100 takes only a match" in \
        got["error"]


def test_a_switch_whose_profile_is_not_selected_is_refused_by_name():
    sw = {"name": "sw-x", "dpid": 9, "selected": profile.select("arista_eos", "4.30.1F")}
    got = app_config.compile_config(manifest(), None, [HP, sw])
    assert got["ok"] is False and got["config"] is None
    assert got["problems"] == [f"quirky 1.0.0's switches for sw-x: {sw['selected']['error']}"]


# ── the config ───────────────────────────────────────────────────────────────────────────

def test_the_compile_keys_each_switch_by_its_dpid_and_fills_the_defaults():
    got = app_config.compile_config(manifest(), None, [HP, OVS, {"name": "sw-none",
                                                                  "dpid": None}])
    assert got["ok"] is True and got["problems"] == []
    assert got["config"] == {"settle_s": 3, "switches": {
        str(PROCURVE): {"forward_table": 100, "punt_table": 200, "meter_table": 100},
        "3": {"forward_table": 0, "punt_table": 0, "meter_table": 0}}}
    assert got["notes"][0].startswith(f"sw-hp (DPID {PROCURVE}): forward_table 100, "
                                      "punt_table 200, meter_table 100; from the platform "
                                      "profile aruba_os_switch")
    assert got["notes"][1].startswith("sw-ovs (DPID 3): forward_table 0, punt_table 0, "
                                      "meter_table 0; table 0 for")


def test_the_networks_config_is_the_base_and_a_compiled_key_it_sets_is_refused():
    got = app_config.compile_config(manifest(), {"settle_s": 1.5}, [OVS])
    assert got["ok"] is True and got["config"]["settle_s"] == 1.5
    got = app_config.compile_config(manifest(), {"switches": {"3": {}}}, [OVS])
    assert got["ok"] is False
    assert got["problems"] == ["quirky 1.0.0: the network's config sets switches, which Mercury "
                               "compiles from the platform profiles; a value set by hand would "
                               "stand in for the measured tables, so it is refused"]


def test_nothing_compiled_and_no_config_gets_no_file():
    assert app_config.compile_config(manifest(compiled=""), None, [HP]) == {
        "ok": True, "config": None, "notes": [], "problems": []}
    assert app_config.compile_config(manifest(compiled=""), {"settle_s": 2}, [HP])["config"] \
        == {"settle_s": 2}


def test_a_dpid_that_is_not_a_whole_number_and_a_schema_refusal_are_named():
    got = app_config.compile_config(manifest(), None, [dict(OVS, dpid="0x3")])
    assert got["problems"] == ["quirky 1.0.0's switches: sw-ovs's DPID '0x3' is not a whole "
                               "number, so it cannot be keyed"]
    strict = SCHEMA.replace("switches: {type: object}",
                            "switches: {type: object, maxProperties: 1}")
    got = app_config.compile_config(manifest(schema=strict), None, [HP, OVS])
    assert got["ok"] is False
    assert got["problems"] == ["quirky 1.0.0's compiled config fails its config_schema: "
                               "switches: {'56298109234905574': {'forward_table': 100, "
                               "'punt_table': 200, 'meter_table': 100}, '3': {'forward_table': "
                               "0, 'punt_table': 0, 'meter_table': 0}} has too many properties"]


@pytest.mark.parametrize("compiled, words", [
    ("  - key: tables\n    per_switch: [punt_table]\n",
     "compiled tables: not a key config_schema declares through properties"),
    ("  - key: switches\n    per_switch: [punt_table, egress_table]\n",
     "'egress_table' is not a table role Mercury compiles"),
    ("  - key: switches\n    per_switch: []\n", "per_switch names at least one table role"),
    ("  - key: switches\n    per_switch: [punt_table]\n  - key: switches\n"
     "    per_switch: [forward_table]\n", "compiled keys"),
    ("  - key: switches.x\n    per_switch: [punt_table]\n", "a top-level config key"),
])
def test_the_manifest_takes_only_a_declared_key_and_known_roles(compiled, words):
    with pytest.raises(ManifestError) as raised:
        manifest(compiled=compiled)
    assert words in " | ".join(raised.value.problems), raised.value.problems


# ── the plan and the preview ─────────────────────────────────────────────────────────────

class CompiledSources(FakeSources):
    """FakeSources whose one registered app compiles its tables, over *switches*."""

    def __init__(self, tmp_path, switches):
        super().__init__(tmp_path)
        self.reg = registry(tmp_path, name="quirky", versions=("1.0.0",))
        self.reg["apps"][0]["versions"][0]["manifest"] = manifest()
        self.switches = switches

    def expected(self, network, controller):
        return {"state": "ok", "error": "", "switches": list(self.switches), "links": []}


def test_the_plan_stages_the_compiled_config_and_its_hash_rides_in_the_request(tmp_path):
    plan = deploy_op.preview(NET, CTL, {"quirky": "1.0.0"}, src=CompiledSources(tmp_path,
                                                                                [HP, OVS]))
    assert plan["ok"] is True, plan["refusals"]
    want = {"settle_s": 3, "switches": {
        str(PROCURVE): {"forward_table": 100, "meter_table": 100, "punt_table": 200},
        "3": {"forward_table": 0, "meter_table": 0, "punt_table": 0}}}
    text = plan["configs"]["quirky"]
    assert json.loads(text) == want and text == channel.config_bytes(want).decode("ascii")
    assert plan["request"]["apps"][0]["config_sha256"] == \
        hashlib.sha256(text.encode("ascii")).hexdigest()
    assert plan["config_notes"]["quirky"][0].startswith(f"sw-hp (DPID {PROCURVE})")


def test_a_profile_that_moves_a_table_moves_the_plans_hash(tmp_path):
    first = deploy_op.preview(NET, CTL, {"quirky": "1.0.0"},
                              src=CompiledSources(tmp_path / "a", [HP, OVS]))
    tables = copy.deepcopy(HP["selected"]["entry"]["openflow"]["tables"])
    tables[2]["table_id"] = 201
    tables[1]["next_tables"] = [201]
    moved = dict(HP, selected=_with_tables(tables))
    second = deploy_op.preview(NET, CTL, {"quirky": "1.0.0"},
                               src=CompiledSources(tmp_path / "b", [moved, OVS]))
    assert first["ok"] and second["ok"]
    assert json.loads(second["configs"]["quirky"])["switches"][str(PROCURVE)]["punt_table"] == 201
    assert first["request"]["apps"][0]["sha256"] == second["request"]["apps"][0]["sha256"]
    assert first["plan_sha256"] != second["plan_sha256"]
    assert first["parts"]["the request"] != second["parts"]["the request"]


def test_a_compile_refused_refuses_the_preview_naming_the_switch(tmp_path):
    sw = {"name": "sw-x", "dpid": 9, "selected": profile.select("arista_eos", "4.30.1F")}
    plan = deploy_op.preview(NET, CTL, {"quirky": "1.0.0"},
                             src=CompiledSources(tmp_path, [HP, sw]))
    assert plan["ok"] is False
    assert plan["refusals"] == [f"quirky 1.0.0's switches for sw-x: {sw['selected']['error']}"]


def test_the_preview_draws_the_compiled_config_and_its_confirm_stages_those_bytes(  # noqa: F811
        networks, tmp_path, monkeypatch):
    from tests.test_sdn_apps_v2 import confirm

    src = CompiledSources(tmp_path / "src", [HP, OVS])
    monkeypatch.setattr(deploy_op, "SOURCES", src)
    import app as A

    client = A.app.test_client()
    r = client.post("/v2/sdn/apps/preview", data={
        "list": "Default", "controller": CTL, "set": "quirky=1.0.0"})
    html = r.get_data(as_text=True)
    assert r.status_code == 200, html
    assert "quirky 1.0.0's start-time config, staged to <span class=\"mono\">" \
           "/opt/ryu-apps/quirky/1.0.0.config.json</span>" in html
    assert "punt_table&#34;: 200" in html and "its config file (new)" in html
    assert f"sw-hp (DPID {PROCURVE}): forward_table 100, punt_table 200, meter_table 100" in html
    # The post-check's read: both switches back and the app's /health ok.
    src.reads = [{"switches": {"ok": True, "switches": [{"dpid": PROCURVE}, {"dpid": 3}]},
                  "links": {"ok": True, "links": []}, "health": {"quirky": {"ok": True}}}]
    _r, done = confirm(client, html)
    assert "Deployed" in done
    [sent] = src.sent
    staged = json.loads(sent["configs"]["quirky"])
    assert staged["switches"][str(PROCURVE)] == {"forward_table": 100, "meter_table": 100,
                                                 "punt_table": 200}
    assert sent["request"]["apps"][0]["config_sha256"] == hashlib.sha256(
        sent["configs"]["quirky"].encode("ascii")).hexdigest()


def test_the_preview_card_draws_each_config_masked_with_its_basis_and_state():
    from modules import sdn_apps_page

    s = channel.script()
    planted = {"note": "snmp-server community plantedvalue9 RO", "switches": {}}
    text = channel.config_bytes(planted).decode("ascii")
    same = channel.config_bytes({"switches": {}}).decode("ascii")
    plan = {"request": {"apps": [{"name": "a", "version": "1.0.0", "config_sha256": "f" * 64},
                                 {"name": "b", "version": "2.0.0", "config_sha256": "e" * 64},
                                 {"name": "c", "version": "1.0.0", "sha256": "d" * 64}]},
            "configs": {"a": text, "b": same}, "record_configs": {"b": same},
            "config_notes": {"a": ["sw-hp (DPID 1): punt_table 200; from the platform profile"]}}
    cards = sdn_apps_page.config_cards(plan, s)
    assert [(c["app"], c["state"]) for c in cards] == [("a", "new"), ("b", "same")]
    assert cards[0]["path"] == "/opt/ryu-apps/a/1.0.0.config.json"
    assert "plantedvalue9" not in cards[0]["text"] and '"note"' in cards[0]["text"]
    assert cards[0]["notes"] == ["sw-hp (DPID 1): punt_table 200; from the platform profile"]
    plan["record_configs"] = {"a": same}
    assert sdn_apps_page.config_cards(plan, s)[0]["state"] == "changed"
