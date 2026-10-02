"""Verify scaled to what the program touches (the operator, 2026-10-01).

The vty standardisation sent five lines under `line vty 0 4` to r1 to r4,
and r3 and r4 each took three to four minutes: verify waited out BGP's hold
time (C178) after a change that cannot break a BGP session. A program whose
every section is management (terminal lines, logging, SNMP, NTP, banners,
users) gets a QUICK verify: a new login, every check read once, each new line
read back, and no hold-time wait. Anything else, or unrecognised, is FULL.

On r3's REAL config and session table (test_bgp_hold_watch's world), with the
real vty program and minimal edits of it."""

import re

import pytest

from modules import pipeline
from modules.nsot import verify_scope as V
from tests.test_bgp_hold_watch import R3, _summary, world  # noqa: F401  (the fixture)

VTY = ["line vty 0 4", " logging synchronous", " login local", " length 0",
       " transport input all", "exit"]
MERGED = re.sub(r"(?ms)^line vty 0\n.*?^line vty 2 4\n(?: [^\n]*\n)*",
                "line vty 0 4\n logging synchronous\n login local\n length 0\n"
                " transport input all\n", R3)


def test_the_floor_r3_holds_split_vty_stanzas_and_the_merge_replaces_them():
    assert "line vty 2 4\n" in R3 and "line vty 2 4\n" not in MERGED
    assert "line vty 0 4\n" not in R3 and "line vty 0 4\n" in MERGED


class TestTheClassification:
    def test_the_vty_standard_is_quick(self):
        v = V.classify(VTY)
        assert v["scope"] == "quick" and v["sections"] == ["line vty 0 4"]
        assert "terminal lines" in v["why"] and "hold time is not waited out" in v["why"]

    def test_the_monitoring_profile_s_families_are_quick(self):
        v = V.classify(["snmp-server community <redacted> RO", "logging host 192.0.2.10",
                        "logging trap notifications", "ntp server 192.0.2.10",
                        "username ops privilege 15 secret 0 <redacted>",
                        "banner motd ^Cauthorised use only^C"])
        assert v["scope"] == "quick"
        assert "SNMP" in v["why"] and "NTP" in v["why"] and "users" in v["why"]

    def test_a_mode_b_removal_of_a_logging_line_is_quick(self):
        assert V.classify(["no logging buffered"])["scope"] == "quick"

    @pytest.mark.parametrize("program, named", [
        (["interface GigabitEthernet2", " ip address 192.0.2.1 255.255.255.0", "exit"],
         "interface GigabitEthernet2"),
        (["router bgp 65001", " neighbor 192.0.2.9 remote-as 65002", "exit"], "router bgp 65001"),
        (["ip route 192.0.2.0 255.255.255.0 198.51.100.1"], "ip route 192.0.2.0"),
        (["ip access-list extended MGMT", " permit ip any any", "exit"], "ip access-list"),
        (["route-map RM permit 10", " set metric 10", "exit"], "route-map RM permit 10"),
        (["ip prefix-list P seq 5 permit 192.0.2.0/24"], "ip prefix-list"),
        (["vrf definition BLUE", " rd 65001:1", "exit"], "vrf definition BLUE"),
        (["no ip sla 1", "ip sla 1", " icmp-echo 192.0.2.1", "exit"], "ip sla 1"),
        (["lldp run"], "lldp run"),
    ])
    def test_anything_that_can_affect_forwarding_or_is_unnamed_is_full(self, program, named):
        v = V.classify(program)
        assert v["scope"] == "full" and any(named in f for f in v["forwarding"])

    def test_one_forwarding_line_makes_a_management_program_full_naming_only_it(self):
        v = V.classify(VTY + ["interface Loopback9", " description x", "exit"])
        assert v["scope"] == "full" and v["forwarding"] == ["interface Loopback9"]
        assert "`interface Loopback9`" in v["why"]

    def test_a_logging_line_under_an_interface_is_the_interface_s(self):
        assert V.classify(["interface GigabitEthernet2", " logging event link-status",
                           "exit"])["scope"] == "full"

    def test_nothing_sent_is_full_with_nothing_to_classify(self):
        assert V.classify([]) == {"scope": "full", "sections": [], "forwarding": [],
                                  "why": "nothing is sent, so there is nothing to classify"}


class TestTheReadBack:
    def test_every_new_vty_line_reads_back_from_the_merged_config(self):
        rb = V.read_back(VTY, MERGED)
        assert rb == {"missing": [], "skipped": [], "checked": 4}

    def test_a_line_the_device_does_not_show_is_named_under_its_section(self):
        rb = V.read_back(VTY, R3)
        assert rb["missing"] == ["line vty 0 4 > logging synchronous",
                                 "line vty 0 4 > login local", "line vty 0 4 > length 0",
                                 "line vty 0 4 > transport input all"]

    def test_negations_secrets_and_banners_are_skipped_with_why(self):
        rb = V.read_back(["no logging console", "username ops privilege 15 secret 0 Zq7value",
                          "banner motd ^Cx^C"], R3)
        assert rb["checked"] == 0 and rb["missing"] == []
        assert [s["why"] for s in rb["skipped"]] == [
            "a `no` line reads back as an absence", "a secret the device stores in another form",
            "a banner reads back in the device's own delimiter"]
        assert "Zq7value" not in str(rb)


class TestThePipelineRunsTheScopedVerify:
    def test_a_quick_program_does_not_wait_out_bgp_s_hold_time(self, world):
        ctx, clock = world(_summary(), config=MERGED)
        ctx.rendered_commands = {"x": VTY}
        pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert clock.slept == [] and v["bgp_watch"] is None
        assert v["verify_scope"]["scope"] == "quick" and v["ok"] is True
        assert v["read_back"] == {"missing": [], "skipped": [], "checked": 4}

    def test_a_full_program_still_watches_bgp_to_its_hold_time(self, world):
        ctx, clock = world(_summary(), config=MERGED)
        ctx.rendered_commands = {"x": ["interface Loopback9", " description x", "exit"]}
        pipeline._stage_verify(ctx)
        v = ctx.verify_result["x"]
        assert clock.slept == [170.0] and v["bgp_watch"]["state"] == "converged"
        assert v["verify_scope"]["scope"] == "full" and v["read_back"] is None

    def test_a_quick_line_that_did_not_read_back_fails_verify_and_rolls_nothing_back(self, world):
        ctx, clock = world(_summary(), config=R3)
        ctx.rendered_commands = {"x": VTY}
        pipeline._stage_verify(ctx)                      # no PipelineStageError: no rollback
        v = ctx.verify_result["x"]
        assert v["ok"] is False and v["issues"] == []
        assert "line vty 0 4 > length 0" in v["read_back"]["missing"]

    def test_a_quick_verify_still_catches_a_neighbour_lost(self, world, monkeypatch):
        ctx, clock = world(_summary("Idle"), config=MERGED)
        ctx.rendered_commands = {"x": VTY}
        lost = pipeline._detect_routing_neighbors(None)
        ctx.post_snapshots["x"]["routing_neighbors"] = lost
        with pytest.raises(pipeline.PipelineStageError):
            pipeline._stage_verify(ctx)


class TestTheRecordAndTheScreens:
    def test_the_receipt_keeps_the_scope_and_the_read_back(self):
        from modules.nsot.receipts import _checks
        checks = _checks({"commands": VTY, "verify": {
            "ok": True, "pre": {}, "post": {},
            "verify_scope": {"scope": "quick", "why": "w"},
            "read_back": {"missing": [], "skipped": [], "checked": 4}}})
        assert checks["verify_scope"] == {"scope": "quick", "why": "w"}
        assert checks["read_back"]["checked"] == 4

    def test_the_deploy_preview_says_which_verify_runs(self):
        from modules.preview_confirm import verify_note
        n = verify_note(VTY)
        assert n["title"].startswith("Verify after the push: QUICK, because every line is "
                                     "management (terminal lines)")
        assert n["lines"] == ["line vty 0 4"]
        f = verify_note(["interface GigabitEthernet2", " shutdown", "exit"])
        assert f["title"].startswith("Verify after the push: FULL") and \
            f["lines"] == ["interface GigabitEthernet2"]
        assert verify_note([]) is None


class TestTheShippedScreensDrawIt:
    def _html(self, verify):
        from modules.nsot import receipts
        from modules.preview_confirm import operation_result
        from tests.payload_render import render_result
        rows = receipts.rows_for({"results": [{
            "device": "r3", "outcome": "deployed", "commands": VTY, "authorised": [],
            "verify": {"issues": [], "checked_protocols": ["bgp"], "pre": {}, "post": {},
                       **verify}}]},
            list_name="Lab", action="deploy", actor="op", actor_kind="person")
        return render_result(operation_result(rows, {"results": []}, {"ok": True, "path": "x"},
                                              "deploy"))

    def test_the_result_says_quick_and_how_many_lines_read_back(self):
        html = self._html({"ok": True, "verify_scope": V.classify(VTY),
                           "read_back": V.read_back(VTY + ["no logging console"], MERGED)})
        assert 'data-pr-verify-scope="quick"' in html and "quick verify: every line is" in html
        assert ("new lines read back: 4 of 4 (1 not checked: a `no` line reads back as an "
                "absence)") in html

    def test_a_line_not_read_back_is_drawn_and_says_nothing_was_rolled_back(self):
        html = self._html({"ok": False, "verify_scope": V.classify(VTY),
                           "read_back": V.read_back(VTY, R3)})
        assert "not read back after the change: line vty 0 4 &gt; length 0" in html
        assert "nothing was rolled back for it" in html

    def test_the_preview_draws_the_note(self):
        from tests.payload_render import render_preview
        from modules.preview_confirm import build, confirm_part, verify_note, gate
        from types import SimpleNamespace
        p = build(action="deploy", summary="s", targets=[{
            "name": "r3", "state": "deployable", "selectable": True, "select_data": {},
            "program": {"lines": VTY, "verify": verify_note(VTY), "none": ""},
            "operands": [{"name": "o", "value": "v"}], "gates": [gate("g", "pass", "")]}],
            what_not=[], nothing_left_out="Nothing.",
            confirm=confirm_part(SimpleNamespace(headers={}, environ={}, remote_addr="")))
        html = render_preview(p)
        assert "Verify after the push: QUICK, because every line is management" in html
        assert "Sections: line vty 0 4" in html

    def test_the_real_deploy_plan_carries_it(self, tmp_path, monkeypatch):
        """Through the REAL /deploy/plan on r2's real config (the capture lab):
        an intent edit to the vty lines plans a quick verify."""
        from modules.nsot import hostvars
        from modules.nsot.parsers import get_parser
        from modules.nsot.repo import save_host_vars
        from tests.test_capture import build_capture_lab
        from modules.nsot import approval
        cap = build_capture_lab(monkeypatch, tmp_path)
        monkeypatch.setattr(approval, "is_approved", lambda repo, t: True)
        hv = get_parser("cisco_iosxe").parse(cap["captured"].replace(
            "line vty 2 4\n", "line vty 2 4\n exec-timeout 30 0\n", 1))
        hostvars.write_committed(cap["repo"], hv)
        assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
        r = cap["client"].post("/deploy/plan", json={"devices": ["r2"], "list_name": "Lab"})
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        t = r.get_json()["preview"]["targets"][0]
        assert "exec-timeout 30 0" in "\n".join(t["program"]["lines"]), (t["program"]["none"],
                                                                    t.get("gates"))
        assert t["program"]["verify"]["title"].startswith("Verify after the push: QUICK")
