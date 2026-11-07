"""T10 (the SDN platform design revision 6, section 15; P2a; C2601): capability records and flow
placement, on the recordings.

- **The table features read:** the Ryu driver's `table_features` on the container harness's
  recording of real Ryu 4.34 reading real Open vSwitch (tests/fixtures/sdn/harness/), every
  instruction and action by name; a property or number it cannot translate kept, never dropped;
  a 1.0 switch's 501 said as the version.
- **Placement on a real pipeline:** OVS's tables accept a MAC match in table 0, and a field none
  of its tables matches is refused naming each table.
- **Placement on the ProCurve's measured pipeline** (its platform profile, C2601): a MAC match is
  never placed in hardware table 100, an LLDP flow never in table 0 (Ryu's own LLDP rule there
  was refused with BAD_MATCH), an IPv4 or IPv6 match carrying eth_type lands in table 100, and a
  placement in software table 200 says so with its rate.

The ProCurve's own recorded `tablefeatures` answer is still to be made at the lab (the design's
section 9); until then its tables are the profile's, measured at the bring-up.
"""

import json

import pytest

from modules.platforms import profile
from modules.sdn import placement
from modules.sdn.drivers.base import OXM_FIELDS, Connection
from modules.sdn.drivers.ryu import RyuDriver, table_from_ryu
from tests.fixtures.sdn import ryu_recorded as R
from tests.sdn_fakes import Clock, Response, Session

HARNESS = R.RecordedRyu(R.HARNESS)
LLDP = {"match": {"eth_type": 0x88CC}, "actions": [{"type": "OUTPUT", "port": "CONTROLLER"}]}
MAC = {"match": {"eth_src": "02:00:00:00:00:01"}, "actions": [{"type": "OUTPUT", "port": 2}]}
IPV4 = {"match": {"eth_type": 0x0800, "ipv4_dst": "192.0.2.10"},
        "actions": [{"type": "OUTPUT", "port": 2}]}
IPV6 = {"match": {"eth_type": 0x86DD, "ipv6_dst": "2001:db8::10"},
        "actions": [{"type": "OUTPUT", "port": 2}]}


def _raw_tables() -> list:
    """The recording's tables as Ryu answered them, not through the driver."""
    return HARNESS.get("/stats/tablefeatures/3")["3"]


def _procurve():
    got = profile.select("hp_procurve", "K.16.02.0020")
    assert got["ok"], got
    return placement.from_profile(got["entry"])


# ───────────────────────────────────────────────────────────── the table features read

def test_the_driver_reads_every_recorded_table_and_names_every_id():
    got = HARNESS.driver().table_features(3)
    assert got["ok"], got
    assert [t["table_id"] for t in got["tables"]] == [t["table_id"] for t in _raw_tables()]
    first = got["tables"][0]
    assert first["instructions"] == ["GOTO_TABLE", "WRITE_METADATA", "WRITE_ACTIONS",
                                     "APPLY_ACTIONS", "CLEAR_ACTIONS", "METER"]
    assert {"OUTPUT", "SET_FIELD", "GROUP", "PUSH_VLAN", "POP_VLAN"} <= set(first["apply_actions"])
    raw = _raw_tables()[0]
    raw_match = [o["type"] for p in raw["properties"] if p["type"] == "MATCH"
                 for o in p["oxm_ids"]]
    assert first["match"] == raw_match
    assert first["max_entries"] == raw["max_entries"]
    names = [n for t in got["tables"] for k in ("instructions", "apply_actions",
                                                 "write_actions", "instructions_miss")
             for n in t[k]]
    assert names and not [n for n in names if n.startswith("UNKNOWN(")]
    assert [t["unknown_properties"] for t in got["tables"]] == [[]] * len(got["tables"])


def test_a_number_or_property_the_driver_cannot_translate_is_kept():
    table = table_from_ryu(1, {"table_id": 0, "properties": [
        {"type": "APPLY_ACTIONS", "action_ids": [{"type": 0, "len": 4}, {"type": 99, "len": 4}]},
        {"type": "INSTRUCTIONS", "instruction_ids": [{"type": 42, "len": 4}]},
        {"type": "SOMETHING_NEW"}, {"type": "EXPERIMENTER"}]})
    assert table.apply_actions == ["OUTPUT", "UNKNOWN(99)"]
    assert table.instructions == ["UNKNOWN(42)"]
    assert table.unknown_properties == ["SOMETHING_NEW"]


def _driver(*answers):
    return RyuDriver(Connection("http://127.0.0.1:8080"), session=Session(*answers),
                     clock=Clock(), sleep=lambda s: None)


def test_a_switch_whose_version_has_no_table_features_is_said_so():
    got = _driver(Response(501, "")).table_features(1)
    assert not got["ok"] and "OpenFlow version does not support" in got["error"]


def test_a_table_without_an_id_is_refused():
    body = json.dumps({"1": [{"name": "t", "properties": []}]})
    got = _driver(Response(200, body)).table_features(1)
    assert not got["ok"] and "is not a table id" in got["error"]


# ───────────────────────────────────────────────────────────── placement on OVS's own tables

def test_ovs_takes_a_mac_match_and_lldp_in_its_first_table():
    tables = placement.from_features(HARNESS.driver().table_features(3))
    for flow in (MAC, LLDP, IPV4, IPV6):
        got = placement.place(flow, tables)
        assert got["ok"] and got["table_id"] == 0 and got["notes"] == [], (flow, got)


def test_a_field_no_ovs_table_matches_is_refused_naming_each_table():
    tables = placement.from_features(HARNESS.driver().table_features(3))
    unmatched = sorted(OXM_FIELDS - set(tables[0].match))
    assert "pbb_isid" in unmatched                 # what the recording says OVS lacks
    got = placement.place({"match": {"pbb_isid": 5}, "actions": []}, tables)
    assert not got["ok"]
    assert [f"table {t.table_id} matches no pbb_isid" for t in tables] == got["passed"]


# ───────────────────────────────────────────────────────────── the ProCurve's measured pipeline

def test_the_procurve_profile_holds_c2601s_pipeline():
    by_id = {t.table_id: t for t in _procurve()}
    assert sorted(by_id) == [0, 100, 200]
    assert by_id[0].reserved and by_id[0].instructions == ["GOTO_TABLE"]
    assert (by_id[100].hardware, by_id[100].max_entries) == (True, 1000)
    assert (by_id[200].hardware, by_id[200].max_entries, by_id[200].software_pps) == \
        (False, 65536, 100)


def test_a_mac_match_is_never_placed_in_the_hardware_table():
    got = placement.place(MAC, _procurve())
    assert got["ok"] and got["table_id"] == 200
    assert "table 100 matches no eth_src" in got["passed"][1]
    assert got["notes"] == ["table 200 is a software table, at 100 packets a second (the "
                            "platform profile)"]


def test_lldp_is_never_placed_in_table_zero_and_goes_to_software():
    got = placement.place(LLDP, _procurve())
    assert got["ok"] and got["table_id"] == 200
    assert got["passed"][0].startswith("table 0 is reserved: the pipeline's single "
                                       "goto-table-100 entry")
    assert "takes eth_type 0x800, 0x86dd, not 0x88cc" in got["passed"][1]


@pytest.mark.parametrize("flow", [IPV4, IPV6], ids=["ipv4", "ipv6"])
def test_an_ip_match_carrying_eth_type_lands_in_hardware(flow):
    got = placement.place(flow, _procurve())
    assert got["ok"] and got["table_id"] == 100 and got["notes"] == [], got


def test_an_ip_match_without_eth_type_is_refused_by_hardware_naming_it():
    flow = {"match": {"ipv4_dst": "192.0.2.10"}, "actions": [{"type": "OUTPUT", "port": 2}]}
    got = placement.place(flow, _procurve())
    assert got["table_id"] == 200
    assert "table 100 takes only a match carrying eth_type" in got["passed"][1]


def test_a_set_field_the_hardware_table_cannot_set_goes_to_software():
    flow = dict(IPV4, actions=[{"type": "SET_FIELD", "field": "eth_dst",
                                "value": "02:00:00:00:00:02"}, {"type": "OUTPUT", "port": 2}])
    got = placement.place(flow, _procurve())
    assert got["table_id"] == 200 and "table 100 sets no eth_dst field" in got["passed"][1]
    remark = dict(IPV4, actions=[{"type": "SET_FIELD", "field": "ip_dscp", "value": 46},
                                 {"type": "METER", "meter_id": 1}, {"type": "OUTPUT", "port": 2}])
    assert placement.place(remark, _procurve())["table_id"] == 100


def test_a_goto_outside_the_next_tables_is_refused():
    flow = dict(IPV4, actions=[{"type": "GOTO_TABLE", "table_id": 5}])
    got = placement.place(flow, _procurve())
    assert "table 100 cannot go to table 5" in got["passed"][1]


def test_a_flow_no_table_takes_names_every_table():
    tables = [t for t in _procurve() if t.table_id != 200]
    got = placement.place(MAC, tables)
    assert not got["ok"] and got["error"].startswith("no table accepts this flow: table 0 is "
                                                     "reserved")
    assert "table 100 matches no eth_src" in got["error"]


def test_tables_from_an_unread_answer_or_an_unmeasured_profile_are_refused():
    with pytest.raises(ValueError, match="were not read: HTTP 501"):
        placement.from_features({"ok": False, "error": "HTTP 501"})
    eos = profile.select("arista_eos", "4.17.0F (Indigo-2 OpenFlow)")
    with pytest.raises(ValueError, match="records no tables"):
        placement.from_profile(eos["entry"])
