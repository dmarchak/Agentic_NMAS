"""Mode B's computation (7.3 step 2), on the REAL fleet configs.

The acceptance case is r2 as the operator left it (C70's residue): intent
lacks ` load-interval 30` under GigabitEthernet2, so every capture departs
from intent and no baseline can be earned (C184, recorded in 17239ae).
"""

import os

import pytest

from modules.nsot import removal as RM
from tests.test_intent_match import _broken

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLEET = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet")


def _cfg(name):
    return open(os.path.join(FLEET, f"{name}.cfg"), encoding="utf-8").read()


R2 = _cfg("r2")
R2_BROKEN = _broken(R2)
R3 = _cfg("r3")


def _unit(chain, line):
    return {"chain": list(chain), "line": line}


def _measure(monkeypatch, result="exact", keys=None, dialect="cisco_iosxe"):
    rows = {k: {"result": result, "device": "probe", "at": "2026-09-28T00:00:00Z",
                "detail": "" if result == "exact" else "also removed: x"}
            for k in (keys or [s.key for s in RM.SHAPES])}
    monkeypatch.setattr(RM, "measured", lambda: {"state": "ok", "by_dialect": {dialect: rows}})


@pytest.fixture(autouse=True)
def every_shape_measured_exact(request, monkeypatch):
    """Most tests are about the computation, so every shape reads measured
    and exact unless a test is about the measurement gate itself."""
    if not request.node.get_closest_marker("real_measurements"):
        _measure(monkeypatch)


def program(running, units, mgmt_ip="10.255.1.12", dialect="cisco_iosxe"):
    return RM.removal_program(running, units, mgmt_ip=mgmt_ip, dialect=dialect)


class TestTheAcceptanceCase:
    def test_the_one_candidate_is_the_line_the_host_carries(self):
        cands = RM.candidates(R2, R2_BROKEN)
        assert [(c["chain"], c["line"], c["kind"]) for c in cands] == [
            (["interface GigabitEthernet2"], " load-interval 30", "leaf")]

    def test_its_program_is_the_verbatim_negation_in_its_stanza(self):
        out = program(R2_BROKEN, [_unit(["interface GigabitEthernet2"],
                                                   " load-interval 30")],
                                 mgmt_ip="10.255.1.12")
        assert out["commands"] == ["interface GigabitEthernet2", " no load-interval 30", "exit"]
        assert out["refused"] == [] and out["secret_position"] == []

    def test_a_device_at_intent_offers_nothing(self):
        assert RM.candidates(R2, R2) == [], "the control: no residue, no candidate"


class TestShapes:
    def test_a_stanza_the_target_lacks_is_one_unit_removed_by_one_negation(self):
        running = R2 + ("event manager applet NMAS-HEARTBEAT\n"
                        " event timer watchdog time 300\n"
                        " action 1.0 syslog msg \"NMAS-HEARTBEAT\"\n")
        cands = RM.candidates(R2, running)
        (stanza,) = [c for c in cands if c["kind"] == "stanza"]
        assert stanza["line"] == "event manager applet NMAS-HEARTBEAT"
        assert len(stanza["children"]) == 2, "its children are listed, never offered alone"
        assert not [c for c in cands if c["chain"][:1] == [stanza["line"]]]
        out = program(running, [_unit([], stanza["line"])])
        assert out["commands"] == ["no event manager applet NMAS-HEARTBEAT"]

    def test_a_child_selected_with_its_stanza_is_implied(self):
        running = R2 + "event manager applet X\n event timer watchdog time 300\n"
        out = program(running, [
            _unit([], "event manager applet X"),
            _unit(["event manager applet X"], " event timer watchdog time 300")])
        assert out["commands"] == ["no event manager applet X"]

    def test_a_no_line_is_removed_by_its_positive_form(self):
        """The builder's rule. No shape covers `no ip http server` yet, so the
        gated path refuses it until one is measured (the next test)."""
        assert RM.negation_program([_unit([], "no ip http server")]) == ["ip http server"]
        out = program(R2, [_unit([], "no ip http server")])
        assert out["commands"] == [] and "no measured shape" in out["refused"][0]["reason"]

    def test_the_line_is_the_devices_own_never_rebuilt(self):
        running = R2.replace("snmp-server community public RO",
                             "snmp-server community public RO 99", 1)
        out = program(running, [_unit([], "snmp-server community public RO 99")])
        assert out["commands"] == ["no snmp-server community public RO 99"]
        assert out["secret_position"], "a community is a secret position, flagged for a reason"

    def test_a_unit_not_on_the_device_is_refused_and_sends_nothing(self):
        out = program(R2, [_unit(["interface GigabitEthernet2"], " load-interval 30")])
        assert out["commands"] == []
        assert out["refused"][0]["reason"].startswith("not on the device")


class TestRefusals:
    def _why(self, running, chain, line, mgmt_ip="10.255.1.12"):
        out = program(running, [_unit(chain, line)], mgmt_ip=mgmt_ip)
        assert out["commands"] == [], out
        return out["refused"][0]["reason"]

    def test_the_management_interface(self):
        assert "management path" in self._why(R2, ["interface Loopback0"],
                                              " ip address 10.255.1.12 255.255.255.255")
        assert "management path" in self._why(R2, [], "interface Loopback0")

    def test_another_interfaces_line_is_not_the_management_path(self):
        """The control: the refusal is keyed on the address, not on 'interface'."""
        out = program(R2_BROKEN, [_unit(["interface GigabitEthernet2"],
                                                   " load-interval 30")])
        assert out["commands"]

    def test_the_vty_lines_and_ssh(self):
        vty = [(line, chain) for line, chain in RM._chains(R2) if chain[:1] == ("line vty 0",)]
        assert vty, "the fixture has vty children"
        assert "vty" in self._why(R2, ["line vty 0"], vty[0][0])
        assert "line stanza" in self._why(R2, [], "line vty 0")

    def test_a_static_route(self):
        assert "path to the manager" in self._why(
            R2, [], "ip route vrf clab-mgmt 0.0.0.0 0.0.0.0 10.0.0.2")

    def test_an_account(self):
        assert "account" in self._why(R2, [], "username admin privilege 15 password 0 admin")

    def test_a_physical_interface_and_the_hostname(self):
        assert "default interface" in self._why(R2, [], "interface GigabitEthernet2")
        assert "hostname" in self._why(R2, [], "hostname r2")

    def test_a_numbered_access_list_entry(self):
        running = R2 + "access-list 10 permit 192.0.2.1\naccess-list 10 permit 192.0.2.2\n"
        assert "WHOLE numbered access-list" in self._why(running, [], "access-list 10 permit 192.0.2.1")

    def test_a_prefix_list_a_neighbour_uses_names_the_neighbour(self):
        why = self._why(R3, [], "ip prefix-list NO-PRIVATE seq 20 permit 0.0.0.0/0 le 32",
                        mgmt_ip="")
        assert "NO-PRIVATE is still used by" in why and "prefix-list NO-PRIVATE out" in why

    def test_a_vrf_its_interfaces_sit_in(self):
        why = self._why(R3, [], "vrf definition clab-mgmt", mgmt_ip="")
        assert "vrf forwarding clab-mgmt" in why

    def test_an_unreferenced_named_object_is_removable(self):
        """The control for the reference check: the same shape with no user."""
        running = R3 + "ip prefix-list UNUSED seq 5 permit 192.0.2.0/24\n"
        out = program(running, [_unit([], "ip prefix-list UNUSED seq 5 permit "
                                                     "192.0.2.0/24")])
        assert out["commands"] == ["no ip prefix-list UNUSED seq 5 permit 192.0.2.0/24"]


class TestTheFleet:
    def test_every_device_offers_nothing_against_itself(self):
        """Floors: the whole real fleet, and a candidate list that CAN be
        non-empty (the acceptance case) is empty on a device at itself."""
        names = [f[:-4] for f in sorted(os.listdir(FLEET)) if f.endswith(".cfg")]
        assert len(names) >= 9
        for name in names:
            text = _cfg(name)
            assert RM.candidates(text, text) == [], name


class TestOnlyWhatWasMeasured:
    """The operator (2026-09-28): ask the platform rather than reason about
    it, because this is where being wrong destroys configuration."""

    LOAD = [_unit(["interface GigabitEthernet2"], " load-interval 30")]

    @pytest.mark.real_measurements
    def test_the_committed_record_allows_nothing_unmeasured(self):
        rec = RM.measured()
        assert rec["state"] in ("absent", "ok")
        rows = rec["by_dialect"].get("cisco_iosxe") or {}
        if (rows.get("interface.load-interval") or {}).get("result") != "exact":
            out = program(R2_BROKEN, self.LOAD)
            assert out["commands"] == []
            assert "scripts/nmas-removal-probe --shape interface.load-interval" in \
                out["refused"][0]["reason"]

    def test_not_measured_on_this_platform_is_refused_naming_the_probe(self, monkeypatch):
        _measure(monkeypatch, dialect="cisco_ios")
        out = program(R2_BROKEN, self.LOAD, dialect="cisco_iosxe")
        assert out["commands"] == []
        assert "has not been measured on cisco_iosxe" in out["refused"][0]["reason"]

    def test_a_shape_measured_broader_is_refused_with_what_was_measured(self, monkeypatch):
        _measure(monkeypatch, result="broader")
        out = program(R2_BROKEN, self.LOAD)
        why = out["refused"][0]["reason"]
        assert "removes MORE than that line" in why and "also removed: x" in why

    def test_a_line_no_shape_covers_is_refused(self):
        running = R2 + "service tcp-keepalives-in\n"
        out = program(running, [_unit([], "service tcp-keepalives-in")])
        assert out["commands"] == []
        assert out["refused"][0]["reason"].startswith("no measured shape covers this line")

    def test_no_platform_is_refused(self):
        out = program(R2_BROKEN, self.LOAD, dialect="")
        assert "platform is not known" in out["refused"][0]["reason"]

    @pytest.mark.real_measurements
    def test_an_unreadable_record_allows_nothing(self, tmp_path, monkeypatch):
        bad = tmp_path / "m.json"
        bad.write_text("{not json")
        monkeypatch.setattr(RM, "MEASURED_FILE", str(bad))
        assert RM.measured()["state"] == "unreadable"
        out = program(R2_BROKEN, self.LOAD)
        assert "could not be read" in out["refused"][0]["reason"]

    def test_the_suspected_shapes_are_in_the_table(self):
        """Measured so the record shows WHY they are refused, never assumed."""
        keys = {s.key for s in RM.SHAPES}
        assert {"global.numbered-acl-entry", "bgp.neighbor-remote-as",
                "global.route-map-sequence", "named-acl.entry",
                "global.snmp-server-community"} <= keys



S4 = _cfg("s4")


class TestTheCommittedRecord:
    """The first real measurement (s4, cisco_ios, 2026-09-29) is load-bearing:
    what it measured exact is removable on that platform, and on no other."""

    GI01 = "interface GigabitEthernet0/1"

    def _s4_with(self, line):
        return S4.replace(self.GI01 + "\n", f"{self.GI01}\n{line}\n", 1)

    @pytest.mark.real_measurements
    def test_a_measured_shape_is_removable_on_its_platform_and_not_elsewhere(self):
        """A numbered ACL entry in LIST form: exact on cisco_iosxe (r3), the form it
        displays; never measured on cisco_ios, which displays numbered ACLs at the top
        and measured THAT form destructive. (load-interval, then the named-ACL entry,
        were this test's example until each was measured on both platforms.)"""
        acl = "ip access-list standard 97"
        running = S4 + f"{acl}\n 10 permit 192.0.2.1\n 20 permit 192.0.2.2\n"
        unit = [_unit([acl], " 10 permit 192.0.2.1")]
        xe = program(running, unit, mgmt_ip="10.255.1.24", dialect="cisco_iosxe")
        assert xe["commands"] == [acl, " no 10 permit 192.0.2.1", "exit"], xe
        ios = program(running, unit, mgmt_ip="10.255.1.24", dialect="cisco_ios")
        assert ios["commands"] == [] and "not been measured on cisco_ios" in \
            ios["refused"][0]["reason"]

    @pytest.mark.real_measurements
    def test_the_community_removal_c139_needs_is_measured_on_ios(self):
        out = program(S4, [_unit([], next(l for l in S4.splitlines()
                                          if l.startswith("snmp-server community")))],
                      mgmt_ip="10.255.1.24", dialect="cisco_ios")
        assert out["commands"] and out["commands"][0].startswith("no snmp-server community")
        assert out["secret_position"], "still needs a stated reason"

    @pytest.mark.real_measurements
    def test_logging_buffered_is_refused_by_name_citing_s4(self):
        running = S4 + "logging buffered 16001\n"
        out = program(running, [_unit([], "logging buffered 16001")], mgmt_ip="10.255.1.24",
                      dialect="cisco_ios")
        assert out["commands"] == []
        assert "measured on cisco_ios (s4, 2026-09-29)" in out["refused"][0]["reason"]
        assert "logging-buffered" not in {s.key for s in RM.SHAPES}, "retired from the probe"

    @pytest.mark.real_measurements
    def test_of_three_list_entry_shapes_only_the_numbered_acl_is_refused_on_ios(self):
        """Resemblance would have refused all three; measurement refused one."""
        running = S4 + ("access-list 97 permit 192.0.2.1\naccess-list 97 permit 192.0.2.2\n"
                        "ip prefix-list SCRATCH seq 5 permit 192.0.2.0/24\n"
                        "ip access-list extended SCRATCH\n permit ip host 192.0.2.1 any\n"
                        "route-map SCRATCH permit 10\n set metric 10\n")
        acl = program(running, [_unit([], "access-list 97 permit 192.0.2.1")],
                      mgmt_ip="10.255.1.24", dialect="cisco_ios")
        assert acl["commands"] == [] and "measured on cisco_ios, s4" in acl["refused"][0]["reason"]
        ok = program(running, [
            _unit([], "ip prefix-list SCRATCH seq 5 permit 192.0.2.0/24"),
            _unit(["ip access-list extended SCRATCH"], " permit ip host 192.0.2.1 any"),
            _unit([], "route-map SCRATCH permit 10")],
            mgmt_ip="10.255.1.24", dialect="cisco_ios")
        assert ok["refused"] == [], ok["refused"]
        assert ok["commands"] == ["no ip prefix-list SCRATCH seq 5 permit 192.0.2.0/24",
                                  "ip access-list extended SCRATCH",
                                  " no permit ip host 192.0.2.1 any", "exit",
                                  "no route-map SCRATCH permit 10"]

    @pytest.mark.real_measurements
    def test_the_record_holds_only_what_no_did(self):
        import json
        rec = json.load(open(RM.MEASURED_FILE, encoding="utf-8"))
        rows = rec["by_dialect"]["cisco_ios"]
        assert {k for k, v in rows.items() if v["result"] == "exact"} == {
            "interface.load-interval", "interface.description",
            "global.snmp-server-community", "global.logging-host",
            "global.route-map-sequence", "global.event-manager-applet",
            "global.ip-prefix-list-entry", "named-acl.entry",
            # C531 part 1, s1, 2026-10-07 (the operator's run):
            "global.ip-route", "global.ipv6-route", "interface.ipv6-rip-default-originate",
            "interface.shutdown", "interface.ospf-cost"}
        # vIOS-L2 rejects the IPv6 forms themselves: a fact about the platform, recorded.
        assert rows["interface.ipv6-ospf-cost"]["result"] == "unsupported"
        assert rows["ospfv3.max-metric"]["result"] == "unsupported"
        # Redefined after `no <line>` measured DIFFERENT: not a platform fact until re-measured.
        assert "ospf.max-metric" not in rows
        assert "REDEFINED" in rec["unmeasured"]["cisco_ios"]["ospf.max-metric"]["reason"]
        assert rows["global.numbered-acl-entry"]["result"] == "broader"
        assert "access-list 97 permit 192.0.2.2" in rows["global.numbered-acl-entry"]["detail"]
        assert rows["global.logging-buffered"]["result"] == "overrides_default"
        assert all(v["result"] not in ("unmeasured", "failed") for v in rows.values())



class TestWhyAShapeIsUnmeasured:
    @pytest.mark.real_measurements
    def test_the_refusal_says_why_the_run_could_not_measure_it(self):
        running = R3 + "access-list 97 permit 192.0.2.1\n"
        out = program(running, [_unit([], "access-list 97 permit 192.0.2.1")],
                      mgmt_ip="", dialect="cisco_iosxe")
        why = out["refused"][0]["reason"]
        # The named refusal (IOS measured it destructive) speaks first; the
        # record's reason for IOS-XE is checked at the gate itself.
        assert "WHOLE numbered access-list" in why
        gate = RM._unmeasured([], "access-list 97 permit 192.0.2.1", "leaf", "cisco_iosxe")
        assert "(r3," in gate and "never DISPLAYS this form" in gate

    @pytest.mark.real_measurements
    def test_r2s_residue_shape_is_measured_exact_on_iosxe(self):
        """Mode B's acceptance, unlocked in the record: r2's program is allowed."""
        out = program(R2_BROKEN, [_unit(["interface GigabitEthernet2"], " load-interval 30")],
                      mgmt_ip="10.255.1.12", dialect="cisco_iosxe")
        assert out["commands"] == ["interface GigabitEthernet2", " no load-interval 30", "exit"]
        assert out["refused"] == []


class TestUndoAndReadBack:
    """2b's pure half: a removal is undone by re-adding the device's OWN lines
    from the pre-change snapshot, and a read-back names what did not go."""

    LOAD = [_unit(["interface GigabitEthernet2"], " load-interval 30")]

    def test_the_undo_is_the_removed_line_verbatim_in_its_stanza(self):
        assert RM.restore_program(self.LOAD, R2_BROKEN, R2) == [
            "interface GigabitEthernet2", " load-interval 30", "exit"]

    def test_a_stanza_comes_back_with_every_line_it_held(self):
        before = R2 + 'event manager applet X\n event timer watchdog time 300\n action 1.0 syslog msg "x"\n'
        assert RM.restore_program([_unit([], "event manager applet X")], before, R2) == [
            "event manager applet X", " event timer watchdog time 300",
            ' action 1.0 syslog msg "x"', "exit"]

    def test_only_what_is_missing_now_is_sent(self):
        assert RM.restore_program(self.LOAD, R2_BROKEN, R2_BROKEN) == [], \
            "the removal never took: nothing to put back"

    def test_the_undo_never_sends_a_line_the_snapshot_did_not_hold(self, monkeypatch):
        from modules.nsot import deploy
        monkeypatch.setattr(deploy, "merge_commands",
                            lambda fragment, now: ["interface GigabitEthernet2",
                                                   " load-interval 31", "exit"])
        with pytest.raises(RuntimeError, match="never held"):
            RM.restore_program(self.LOAD, R2_BROKEN, R2)

    def test_the_read_back_names_what_did_not_go(self):
        assert RM.still_present(self.LOAD, R2_BROKEN) == self.LOAD
        assert RM.still_present(self.LOAD, R2) == []


class TestTheCdpRunFlag:
    """r6 carries `cdp run` its effective intent no longer has (the operator,
    2026-09-30): the profile pushed it, then dropped CDP on IOS-XE because the
    line runs nothing there (C254). Its removal is a shape of its own, and,
    like every shape, refused until measured on the platform."""

    # r2's real config carries `cdp run` (r1 to r4 do); intent without it is r6's.
    R6_LIKE = R2
    INTENT = "".join(l for l in R2.splitlines(True) if l.strip() != "cdp run")

    @pytest.mark.real_measurements
    def test_refused_until_measured_naming_the_probe(self, monkeypatch):
        rows = {"interface.load-interval": {"result": "exact", "device": "r2", "at": "x", "detail": ""}}
        monkeypatch.setattr(RM, "measured", lambda: {"state": "ok", "by_dialect": {"cisco_iosxe": rows}})
        cands = RM.candidates(self.INTENT, self.R6_LIKE)
        assert [(c["chain"], c["line"]) for c in cands] == [([], "cdp run")]
        out = program(self.R6_LIKE, [_unit([], "cdp run")])
        assert out["commands"] == []
        assert "scripts/nmas-removal-probe --shape global.cdp-run" in out["refused"][0]["reason"]

    def test_removable_once_measured_exact(self):
        out = program(self.R6_LIKE, [_unit([], "cdp run")])
        assert out["commands"] == ["no cdp run"], out

    @pytest.mark.real_measurements
    def test_the_committed_record_removes_it_on_ios_xe_and_nowhere_else(self):
        """Staged run 8 (2026-10-01): `global.cdp-run` measured EXACT on r2, so
        the COMMITTED record lets r6 drop the line (C262); IOS was never asked,
        so it is still refused there, naming the probe."""
        rows = RM.measured()["by_dialect"]
        assert rows["cisco_iosxe"]["global.cdp-run"]["result"] == "exact"
        assert rows["cisco_iosxe"]["global.cdp-run"]["device"] == "r2"
        xe = program(self.R6_LIKE, [_unit([], "cdp run")])
        assert xe["commands"] == ["no cdp run"] and not xe["refused"], xe
        ios = program(self.R6_LIKE, [_unit([], "cdp run")], dialect="cisco_ios")
        assert ios["commands"] == []
        assert "scripts/nmas-removal-probe --shape global.cdp-run" in ios["refused"][0]["reason"]
