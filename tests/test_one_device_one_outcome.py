"""C310 (2026-10-01): after the vty standardisation every deploy's golden and
then Save All were refused, all nine rows carrying r1's "fewer structural
sections (line 5->3) ... pass acknowledge_structural_change=True".

Three defects, each tested through the REAL capture routes on r2's REAL
config: a shrink committed intent renders is accepted and recorded; one
device's refusal is that device's row alone (the others recorded, no
baseline); a person acknowledges an unexplained shrink with a stated reason
on the preview, never a parameter. And a deploy whose golden was not recorded
is never drawn as a clean success.
"""

import re
import subprocess

import pytest

from tests.payload_render import render_preview
from tests.test_capture import _apply, _last_message, build_capture_lab, run_capture_preview

ONE_VTY = "line vty 0 4\n logging synchronous\n login local\n length 0\n transport input all\n"


def _vty_block(text):
    return re.search(r"(?ms)^line vty 0\n.*?^line vty 2 4\n(?: [^\n]*\n)*", text).group(0)


@pytest.fixture
def two(tmp_path, monkeypatch):
    """r2 (REAL, committed intent) and s9 (r2's config renamed, a golden and
    NO committed intent, so intent explains nothing about it)."""
    from modules.nsot import manifest as M
    from modules.nsot.repo import GoldenItem, save_golden

    cap = build_capture_lab(monkeypatch, tmp_path)
    s9 = cap["captured"].replace("hostname r2", "hostname s9")
    M.upsert_device(cap["repo"], "uid:s9", "s9", "203.0.113.19", platform="cisco_iosxe")
    assert save_golden("Lab", [GoldenItem("s9", s9, "203.0.113.19", platform="cisco_iosxe")],
                       source="onboarding", actor="t", allow_new=False, baseline=False)["ok"]
    devices = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
                "platform": "cisco_iosxe"},
               {"hostname": "s9", "ip": "203.0.113.19", "device_type": "cisco_xe",
                "platform": "cisco_iosxe"}]
    monkeypatch.setattr("modules.nsot.restore._devices_of", lambda ln: [dict(d) for d in devices])
    cap["running"]["s9"] = s9
    cap["s9"] = s9
    return cap


def _preview(cap, fleet=True):
    r = run_capture_preview(cap["client"], {"devices": ["r2", "s9"], "fleet": fleet})
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    return r.get_json()


def _targets(d):
    return {t["name"]: t for t in d["preview"]["targets"]}


def _hashes(d):
    return {t["name"]: t["select_data"]["hash"] for t in d["preview"]["what"]["targets"]}


def _shrink_s9(cap):
    """s9 loses its `line aux 0` stanza: line 5->4, which nothing explains."""
    assert "line aux 0\n" in cap["s9"]
    cap["running"]["s9"] = cap["s9"].replace("line aux 0\n", "")


def _grow_r2(cap):
    cap["running"]["r2"] = cap["captured"].replace(
        "hostname r2\n", "hostname r2\nip domain lookup source-interface Loopback0\n")


class TestOneDeviceOneOutcome:
    def test_the_preview_asks_for_a_reason_for_the_unexplained_shrink_only(self, two):
        _shrink_s9(two)
        _grow_r2(two)
        t = _targets(_preview(two))
        s9 = {g["name"]: g for g in t["s9"]["gates"]}
        gate = s9["structure: no section lost that intent does not explain"]
        assert gate["state"] == "fail" and "line 5->4, not explained" in gate["detail"]
        assert "say why" in t["s9"]["acknowledge"]["prompt"]
        assert "acknowledge" not in t["r2"]
        assert not any(g["name"].startswith("structure") for g in t["r2"]["gates"])
        html = render_preview(_preview(two)["preview"])
        assert 'data-ack-device="s9"' in html and 'data-ack-device="r2"' not in html

    def test_without_a_reason_only_s9_is_refused_and_r2_is_recorded(self, two):
        _shrink_s9(two)
        _grow_r2(two)
        d = _preview(two)
        out = _apply(two, _hashes(d), fleet=True)
        rows = {t["name"]: t for t in out["result"]["happened"]["targets"]}
        assert rows["r2"]["outcome"] == "captured"
        assert rows["s9"]["outcome"] == "not_recorded"
        not_done = {i["target"]: i["text"] for i in out["result"]["did_not"]["items"]
                    if i["kind"] == "not_recorded"}
        assert list(not_done) == ["s9"]
        assert "s9: the capture has fewer structural sections" in not_done["s9"]
        assert "acknowledge_structural_change" not in not_done["s9"]
        summary = out["result"]["happened"]["summary"]
        assert summary.startswith("s9 was not recorded: s9:")
        assert "A baseline needs every device." in summary
        golden_r2 = subprocess.run(["git", "-C", two["repo"], "show", "HEAD:golden/r2.cfg"],
                                   capture_output=True, text=True).stdout
        assert "ip domain lookup source-interface Loopback0" in golden_r2

    def test_a_stated_reason_records_it_on_the_commit(self, two):
        _shrink_s9(two)
        d = _preview(two, fleet=False)
        r = two["client"].post("/golden/capture/apply", json={
            "confirmations": {"s9": _hashes(d)["s9"]}, "fleet": False,
            "acknowledge": {"s9": "the aux line was removed on purpose today"}})
        assert r.status_code == 200, r.get_data(as_text=True)[:300]
        rows = {t["name"]: t for t in r.get_json()["result"]["happened"]["targets"]}
        assert rows["s9"]["outcome"] == "captured"
        assert ("Structural-Change: s9 line 5->4, acknowledged: the aux line was removed on "
                "purpose today") in _last_message(two["repo"])

    def test_a_reason_without_the_shape_of_one_is_refused(self, two):
        _shrink_s9(two)
        d = _preview(two, fleet=False)
        r = two["client"].post("/golden/capture/apply", json={
            "confirmations": {"s9": _hashes(d)["s9"]}, "fleet": False, "acknowledge": {"s9": "ok"}})
        assert r.status_code == 400 and "too short to be a reason" in r.get_json()["error"]


class TestIntentExplainsIt:
    def test_r2_s_vty_lines_merged_by_committed_intent_are_recorded(self, two):
        """The operator's case: intent now renders one `line vty 0 4` stanza
        (committed), the device shows it, and line 5->3 is explained."""
        from modules.nsot import hostvars
        from modules.nsot.parsers import get_parser
        from modules.nsot.repo import save_host_vars

        merged = two["captured"].replace(_vty_block(two["captured"]), ONE_VTY)
        hostvars.write_committed(two["repo"], get_parser("cisco_iosxe").parse(merged))
        assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
        two["running"]["r2"] = merged
        r = run_capture_preview(two["client"], {"devices": ["r2"]})
        d = r.get_json()
        t = _targets(d)["r2"]
        gate = next(g for g in t["gates"] if g["name"].startswith("structure"))
        assert gate["state"] == "pass"
        assert gate["detail"] == "line 5->3, which is what committed intent renders"
        assert "acknowledge" not in t
        out = _apply(two, {"r2": _hashes(d)["r2"]})
        assert {x["name"]: x["outcome"] for x in out["result"]["happened"]["targets"]} == \
            {"r2": "captured"}
        assert ("Structural-Change: r2 line 5->3, which is what committed intent renders"
                in _last_message(two["repo"]))


class TestADeployWhoseGoldenWasNotRecorded:
    ROW = {"device": "r1", "outcome": "deployed", "sent": True, "matches_confirmed": True,
           "program": ["line vty 0 4", " length 0", "exit"], "program_hash": "a",
           "confirmed_hash": "a", "checks": {"ran": True, "ok": True}, "rollback": {}}

    def _result(self, golden):
        from modules.preview_confirm import operation_result
        return operation_result([dict(self.ROW)], {"golden": golden},
                                {"ok": True, "written": 1}, "deploy")

    def test_is_never_a_clean_success(self):
        res = self._result({"ok": False, "devices": ["r1"], "error": "r1: the capture has fewer "
                            "structural sections than the golden it would replace (line 5->3)"})
        assert res["level"] == "partial"
        text = str(res)
        assert "GOLDEN NOT RECORDED for r1" in text
        assert "its golden was NOT recorded: r1: the capture has fewer" in text

    def test_a_recorded_golden_is_still_a_success(self):
        res = self._result({"ok": True, "commit": "abcdef1234567", "devices": ["r1"],
                            "refused": []})
        assert res["level"] == "success"
        assert "GOLDEN NOT RECORDED" not in str(res)
