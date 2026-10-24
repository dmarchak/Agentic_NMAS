"""C1646: a VLAN is read where the switch keeps it, `show vlan id <N>`, by the deploy's verify
and the out-of-band kick-start alike (modules/nsot/vlan_read.py; `verify_scope.read_back`,
`pipeline._read_vlans`; the kick-start's in tests/test_console_readback.py).

s5's Day 1 deploy (2026-10-24 00:42 UTC) landed `vlan 10` / ` name VLAN10` and verify "did not
pass" on `vlan 10 > name VLAN10`: a switch in VTP server mode keeps its VLANs in the VLAN
database and prints none in `show running-config`. The answers here are two lab vIOS-L2
switches' real `show vlan id` (tests/fixtures/console/, README.md there): one in VTP server
mode (VLAN 10 `VLAN10`), one transparent (VLAN 10 `VLAN0010`), and IOS's answer for a VLAN the
database lacks. A VLAN id is an integer, so the IPv4/IPv6 parity rule has no case here.
"""

import os

import pytest

from modules import pipeline, readonly_commands
from modules.nsot import verify_scope as V
from modules.nsot import vlan_read as R
from tests.test_bgp_hold_watch import _summary, world  # noqa: F401  (the fixture)

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "console")


def capture(switch: str, what: str) -> str:
    with open(os.path.join(HERE, f"vios_l2_{switch}_{what}.txt"), encoding="ascii") as fh:
        return fh.read()


SERVER, TRANSPARENT = "s5", "s1"          # the two captures' switches, by VTP mode
VLAN10 = ["vlan 10", " name VLAN10", "exit"]
#: A VTP-server switch's running configuration after the push: no `vlan` line at all.
RUNNING = "hostname edge\n!\ninterface GigabitEthernet0/2\n switchport access vlan 10\n!\nend\n"


def test_the_floor_the_captures_are_the_modes_they_are_named_for():
    assert "VTP Operating Mode                : Server" in capture(SERVER, "show_vtp_status")
    assert "VTP Operating Mode                : Transparent" in capture(TRANSPARENT,
                                                                       "show_vtp_status")
    assert not [ln for ln in RUNNING.splitlines() if ln.startswith("vlan")]


# ── The read itself ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("switch,vlan,name", [
    (SERVER, "10", "VLAN10"), (SERVER, "1", "default"),
    (TRANSPARENT, "10", "VLAN0010"), (TRANSPARENT, "1", "default"),
])
def test_a_vlan_in_the_database_is_present_with_its_name_and_status(switch, vlan, name):
    got = R.parse(vlan, capture(switch, f"show_vlan_id_{vlan}"))
    assert (got["state"], got["name"], got["status"]) == ("present", name, "active"), got
    assert got["row"].split()[:3] == [vlan, name, "active"], got["row"]


@pytest.mark.parametrize("switch", [SERVER, TRANSPARENT])
def test_a_vlan_the_database_lacks_is_absent_by_ios_s_own_line(switch):
    got = R.parse("999", capture(switch, "show_vlan_id_999"))
    assert got == {"state": "absent", "name": "", "status": "",
                   "row": "VLAN id 999 not found in current VLAN database",
                   "why": "VLAN 999 is not in the device's VLAN database"}


@pytest.mark.parametrize("text,why", [
    ("", "the answer is empty"),
    ("                 ^\n% Invalid input detected at '^' marker.\n",
     "the answer has no VLAN table ('^')"),
    # Another VLAN's not-found line is not this VLAN's.
    ("VLAN id 20 not found in current VLAN database\n", "the answer has no VLAN table"),
], ids=["empty", "refused", "another-vlan-s-absence"])
def test_an_answer_that_is_not_this_vlan_s_table_is_unreadable(text, why):
    got = R.parse("10", text)
    assert got["state"] == "unreadable" and got["why"].startswith(why), got


def test_a_table_showing_another_vlan_is_unreadable_naming_what_it_shows():
    got = R.parse("20", capture(SERVER, "show_vlan_id_10"))
    assert got["state"] == "unreadable"
    assert got["why"] == "the VLAN table shows ['10'], not VLAN 20 alone"


def test_a_table_with_two_rows_is_unreadable():
    two = capture(SERVER, "show_vlan_id_10").replace("\n\nVLAN Type", "\n10   VLAN10                           active    "
                                        "Gi0/1\n\nVLAN Type", 1)
    assert R.parse("10", two)["why"] == "the VLAN table shows ['10', '10'], not VLAN 10 alone"


@pytest.mark.parametrize("value", ["0", "4095", "01", "abc", "10,20", "10-12", "-1", " 10",
                                   "", None, 3.0])
def test_a_vlan_id_of_the_wrong_shape_is_refused_before_any_command_is_built(value):
    with pytest.raises(ValueError, match="is not an integer from 1 to 4094"):
        R.command(value)


@pytest.mark.parametrize("value,cmd", [(1, "show vlan id 1"), ("4094", "show vlan id 4094")])
def test_the_read_is_one_allowed_read(value, cmd):
    assert R.command(value) == cmd and readonly_commands.refusal(cmd) == ""


@pytest.mark.parametrize("line,vlan", [
    ("vlan 10", "10"), ("vlan 4094", "4094"), ("vlan 10,20", None), ("vlan 10-12", None),
    ("vlan internal allocation policy ascending", None), ("vlan 0", None), ("vlanx 10", None),
    ("interface Vlan10", None),
])
def test_only_a_line_configuring_one_vlan_is_read_from_the_database(line, vlan):
    assert R.vlan_of(line) == vlan


# ── The deploy's verify (`verify_scope.read_back`) ────────────────────────────────────────

@pytest.mark.parametrize("switch,name", [(SERVER, "VLAN10"), (TRANSPARENT, "VLAN0010")])
def test_a_vlan_and_its_name_read_back_from_the_database_whatever_the_vtp_mode(switch, name):
    """The finding's case: the running configuration holds no `vlan 10`, and the VLAN's read
    shows it named as sent; on the transparent switch, named as IOS names it by default."""
    program = ["vlan 10", f" name {name}", "exit"]
    rb = V.read_back(program, RUNNING, {"10": capture(switch, "show_vlan_id_10")})
    assert rb == {"missing": [], "skipped": [], "checked": 1, "unread": []}


def test_a_vlan_under_another_name_is_missing_naming_both_names():
    rb = V.read_back(VLAN10, RUNNING, {"10": capture(TRANSPARENT, "show_vlan_id_10")})
    assert rb["missing"] == ["vlan 10 > name VLAN10 (`show vlan id 10` names VLAN 10 "
                             "'VLAN0010', the program 'VLAN10')"]
    assert rb["checked"] == 1 and rb["unread"] == []


def test_a_vlan_absent_from_the_database_is_missing_naming_the_read():
    absent = capture(SERVER, "show_vlan_id_999").replace("999", "10")
    rb = V.read_back(VLAN10, RUNNING, {"10": absent})
    assert rb["missing"] == ["vlan 10 > name VLAN10 (`show vlan id 10`: VLAN 10 is not in the "
                             "device's VLAN database)"]


def test_a_bare_vlan_line_needs_the_vlan_only():
    rb = V.read_back(["vlan 1"], RUNNING, {"1": capture(SERVER, "show_vlan_id_1")})
    assert rb == {"missing": [], "skipped": [], "checked": 1, "unread": []}


@pytest.mark.parametrize("vlans,why", [
    ({}, "`show vlan id 10`: it was not read"),
    ({"10": "% Invalid input detected at '^' marker.\n"},
     "`show vlan id 10`: the answer has no VLAN table"),
], ids=["not-read", "not-understood"])
def test_a_vlan_read_not_made_or_not_understood_is_unread_neither_pass_nor_miss(vlans, why):
    rb = V.read_back(VLAN10, RUNNING, vlans)
    assert rb["missing"] == [] and rb["checked"] == 0
    assert [(u["line"], u["vlan"]) for u in rb["unread"]] == [("vlan 10 > name VLAN10", "10")]
    assert rb["unread"][0]["why"].startswith(why), rb["unread"]


def test_other_lines_under_a_vlan_and_its_negations_are_read_as_before():
    """Only the VLAN and its `name` are the database's; `state` keeps its running-configuration
    rule (missing there), and `no name` is skipped: a negation under a VLAN is the database's,
    which is read for the VLAN and its name only (C1415 reads every other negation)."""
    rb = V.read_back(["vlan 10", " state suspend", " no name", "exit"], RUNNING, {})
    assert rb["missing"] == ["vlan 10 > state suspend"] and rb["unread"] == []
    assert [s["why"] for s in rb["skipped"]] == [
        "a `no` line under a VLAN is the VLAN database's, not read back"]
    assert V.vlan_reads(["vlan 10", " state suspend", " no name", "exit"]) == []


def test_the_vlans_read_are_the_program_s_each_once_in_order():
    program = ["vlan 20", "exit", "vlan 10", " name A", "exit", "vlan 20", " name B", "exit",
               "vlan 30-31", " name C", "interface Vlan40", " no shutdown"]
    assert V.vlan_reads(program) == ["20", "10"]


# ── The pipeline reads them after the push and verify judges them ─────────────────────────

class _Conn:
    pass


def test_the_post_snapshot_reads_each_vlan_and_names_a_read_that_raised(monkeypatch):
    sent = []

    def run(conn, cmd, **_k):
        sent.append(cmd)
        if cmd == "show vlan id 20":
            raise OSError("the session closed")
        return capture(SERVER, "show_vlan_id_10")

    monkeypatch.setattr("modules.connection.get_persistent_connection", lambda *a, **k: _Conn())
    monkeypatch.setattr("modules.commands.run_device_command", run)
    ctx = pipeline.PipelineContext(
        config_type="template", device_ips=["x"], params={}, ip_params_map={},
        selected_devices=[{"ip": "x", "hostname": "edge"}], connections_pool={},
        pool_lock=None, config_id="t")
    ctx.rendered_commands = {"x": VLAN10 + ["vlan 20", "exit"]}
    snap = {}
    pipeline._read_vlans(ctx, ctx.selected_devices[0], snap)
    assert sent == ["show vlan id 10", "show vlan id 20"]
    assert snap["vlans"] == {"10": capture(SERVER, "show_vlan_id_10")}
    assert snap["vlan_errors"] == {"20": "OSError: the session closed"}


def test_the_post_change_snapshot_carries_the_vlan_reads(monkeypatch):
    """Stage 7 reads them, on its new session, beside the running configuration."""
    sent = []

    def run(conn, cmd, **_k):
        sent.append(cmd)
        return RUNNING if cmd == "show running-config" else capture(SERVER, "show_vlan_id_10")

    monkeypatch.setattr("modules.connection.close_persistent_connection", lambda *a, **k: None)
    monkeypatch.setattr("modules.connection.get_persistent_connection", lambda *a, **k: _Conn())
    monkeypatch.setattr("modules.commands.run_device_command", run)
    monkeypatch.setattr(pipeline, "_session_for", lambda ctx, dev: _Conn())
    monkeypatch.setattr(pipeline, "_capture_operational_snapshot", lambda *a: {})
    ctx = pipeline.PipelineContext(
        config_type="template", device_ips=["x"], params={}, ip_params_map={},
        selected_devices=[{"ip": "x", "hostname": "edge"}], connections_pool={},
        pool_lock=None, config_id="t")
    ctx.rendered_commands = {"x": VLAN10}
    pipeline._stage_post_snapshot(ctx)
    assert sent == ["show running-config", "show vlan id 10"]
    snap = ctx.post_snapshots["x"]
    assert snap["vlans"] == {"10": capture(SERVER, "show_vlan_id_10")}
    assert snap["vlan_errors"] == {} and snap["running_config"] == RUNNING


def test_a_program_with_no_vlan_reads_none(monkeypatch):
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda *a, **k: pytest.fail("read a VLAN"))
    ctx = pipeline.PipelineContext(
        config_type="template", device_ips=["x"], params={}, ip_params_map={},
        selected_devices=[{"ip": "x", "hostname": "edge"}], connections_pool={},
        pool_lock=None, config_id="t")
    ctx.rendered_commands = {"x": ["interface Loopback9", " description x", "exit"]}
    snap = {}
    pipeline._read_vlans(ctx, ctx.selected_devices[0], snap)
    assert snap == {"vlans": {}, "vlan_errors": {}}


class TestVerifyJudgesTheVlanRead:
    def _verify(self, world, vlans, errors=None):  # noqa: F811 - the fixture
        ctx, _clock = world(_summary(), config=RUNNING)
        ctx.rendered_commands = {"x": VLAN10}
        ctx.post_snapshots["x"].update(vlans=vlans, vlan_errors=errors or {})
        pipeline._stage_verify(ctx)
        return ctx.verify_result["x"]

    def test_a_vlan_the_database_holds_passes_with_none_in_the_running_config(self, world):
        v = self._verify(world, {"10": capture(SERVER, "show_vlan_id_10")})
        assert v["read_back"] == {"missing": [], "skipped": [], "checked": 1, "unread": []}
        assert v["unreadable"] == [] and v["ok"] is True, v

    def test_a_vlan_read_that_failed_is_unreadable_naming_why_and_does_not_pass(self, world):
        v = self._verify(world, {}, {"10": "OSError: the session closed"})
        assert v["read_back"]["missing"] == [] and v["ok"] is False
        assert v["unreadable"] == ["new lines: vlan 10 > name VLAN10: `show vlan id 10`: it was "
                                   "not read (OSError: the session closed)"]

    def test_a_vlan_under_another_name_does_not_pass(self, world):
        v = self._verify(world, {"10": capture(TRANSPARENT, "show_vlan_id_10")})
        assert v["ok"] is False and v["unreadable"] == []
        assert v["read_back"]["missing"] == [
            "vlan 10 > name VLAN10 (`show vlan id 10` names VLAN 10 'VLAN0010', the program "
            "'VLAN10')"]
