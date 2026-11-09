"""quirks_logic over plain data: the config, the pipeline flows each switch should hold,
reconcile and /health. Python 3.5 and Mercury's alike. The switches are the five Ryu recorded at
the bring-up (2026-11-06); the ProCurve's tables are its measured pipeline's (C2601: forward
100, punt 200, meter 100), the others' table 0 (their profiles record no tables).
"""

try:
    from mercury_app.testing import covers
except ImportError:                     # run with no SDK on the path (the app gate reads the import)
    def covers(*_names):
        return lambda test: test

import quirks_logic as L

S3, S4 = 3, 4
ARISTA_A, ARISTA_C, PROCURVE = 2214744208935, 2843895626628, 56298109234905574
OF10, OF13 = 0x01, 0x04
PROCURVE_TABLES = {"forward_table": 100, "punt_table": 200, "meter_table": 100}
TABLE_0 = {"forward_table": 0, "punt_table": 0, "meter_table": 0}
CONFIG = L.parse_config({"switches": {str(PROCURVE): PROCURVE_TABLES, str(S3): TABLE_0,
                                      str(ARISTA_A): TABLE_0}})[0]
OURS_GOTO = 0x5351000000000001
OURS_LLDP = 0x5351000000000002
FOREIGN = 0x99


@covers("the ProCurve's hardware table misses to its software table and LLDP reaches the "
        "controller")
def test_the_procurve_gets_the_miss_goto_and_lldp_and_nothing_in_table_0():
    flows, problems = L.desired_flows(L.tables_for(CONFIG, PROCURVE), OF13)
    assert problems == []
    assert flows == {(100, 0, ()): ((("GOTO", 200),), OURS_GOTO),
                     (200, 65535, (("eth_type", 0x88cc),)): ((("CONTROLLER",),), OURS_LLDP)}
    assert not [k for k in flows if k[0] == 0]


@covers("a switch on table 0 for every role gets no flow")
def test_open_vswitch_and_an_arista_on_table_0_get_no_flow():
    for dpid in (S3, ARISTA_A):
        assert L.desired_flows(L.tables_for(CONFIG, dpid), OF13) == ({}, [])


@covers("reconcile changes only the app's own flows")
def test_reconcile_removes_the_stale_leaves_the_other_owner_and_resends_nothing_right():
    desired, _problems = L.desired_flows(PROCURVE_TABLES, OF13)
    current = [
        (100, 0, (), (("GOTO", 200),), OURS_GOTO),                       # already right
        (200, 65535, (("eth_type", 0x88cc),), (("OUTPUT", 1),), FOREIGN),  # another owner's
        (200, 5, (("eth_type", 0x0806),), (("CONTROLLER",),), OURS_LLDP),  # stale, the app's
    ]
    diff = L.difference(desired, current)
    assert diff["add"] == []
    assert diff["delete"] == [((200, 5, (("eth_type", 0x0806),)), OURS_LLDP)]
    assert diff["conflicts"] == ["table 200 priority 65535 {'eth_type': 35020} is held by "
                                 "another owner (cookie 0x99): left as it is"]


def test_a_missing_flow_is_added_and_a_changed_one_sent_again():
    desired, _problems = L.desired_flows(PROCURVE_TABLES, OF13)
    current = [(100, 0, (), (("GOTO", 100),), OURS_GOTO)]
    diff = L.difference(desired, current)
    assert diff["add"] == [((100, 0, ()), (("GOTO", 200),), OURS_GOTO),
                           ((200, 65535, (("eth_type", 0x88cc),)), (("CONTROLLER",),),
                            OURS_LLDP)]
    assert diff["delete"] == [] and diff["conflicts"] == []


def test_openflow_1_0_takes_table_0_only():
    assert L.desired_flows(TABLE_0, OF10) == ({}, [])
    flows, problems = L.desired_flows(PROCURVE_TABLES, OF10)
    assert flows == {}
    assert problems == ["it speaks OpenFlow 1.0, which has one table, and the config names "
                        "table 100, 200"]


def test_the_config_refuses_each_field_by_name():
    config, problems = L.parse_config({"switches": {"x": {}, "4": {"forward_table": 300,
                                                                    "punt_table": 0,
                                                                    "meter_table": 0}},
                                       "other": 1})
    assert config is None
    assert problems == ["the config takes switches, not 'other'",
                        "switches.4.forward_table is a table id, 0 to 254, not 300",
                        "switches: 'x' is not a datapath id in decimal"]
    config, problems = L.parse_config({"switches": {"5": {"forward_table": 0,
                                                          "punt_table": 0}}})
    assert config is None
    assert problems == ["switches.5.meter_table is a table id, 0 to 254, not None"]


def test_the_start_time_config_is_taken_and_one_not_read_is_named():
    config, why = L.from_start_config({"ok": True, "path": "/a/1.0.0.config.json",
                                       "config": {"switches": {str(PROCURVE): PROCURVE_TABLES}}})
    assert why == "" and L.tables_for(config, PROCURVE) == PROCURVE_TABLES
    assert L.from_start_config(None) == (None, L.NO_SDK)
    config, why = L.from_start_config({"ok": False, "error": "no start-time config at /a"})
    assert config is None
    assert why == "its start-time config was not read: no start-time config at /a"
    config, why = L.from_start_config({"ok": True, "path": "/a", "config": []})
    assert config is None
    assert why == "its start-time config /a is refused: the config is a JSON object, not []"


def test_health_is_ok_only_with_the_config_every_switch_served_and_reconciled():
    switches = [S3, PROCURVE]
    got = L.health(CONFIG, "", switches, set(switches), {}, {})
    assert got == {"ok": True, "configured": True, "switches": 2, "served": 2, "problems": []}
    got = L.health(None, "its start-time config was not read: absent", switches, set(), {}, {})
    assert got["ok"] is False
    assert got["problems"] == ["its start-time config was not read: absent: no switch is "
                               "served"]
    got = L.health(CONFIG, "", [S3, S4, PROCURVE], set([S3]), {PROCURVE: ["a conflict"]},
                   {S3: ["type 4 code 9"]})
    assert got["ok"] is False and got["served"] == 2
    assert got["problems"] == [
        "switch 4 is connected and the config names no tables for it: not served",
        "switch 56298109234905574: its flows are not read and reconciled yet",
        "switch 56298109234905574: a conflict",
        "switch 3 refused: type 4 code 9"]


def test_the_tables_view_names_each_switch_by_its_dpid():
    assert L.tables_view(None) == {"configured": False, "switches": {}}
    view = L.tables_view(CONFIG)
    assert view["configured"] is True
    assert view["switches"][str(PROCURVE)] == PROCURVE_TABLES
    assert sorted(view["switches"]) == sorted([str(S3), str(ARISTA_A), str(PROCURVE)])
