"""Reload on v2 (P.14, cutover blocker 6, 2026-10-10): a gated device-page operation.

- Blast radius (`blast_radius.radius`), pure, on a planted fleet: a switch's VLAN subnets go
  down with it; a router behind another is cut; an edge device cuts nothing; unknown when no
  subnet of this host holds a device, or the device has no intent; a shut interface is no link.
- The six gates (`reload_op.judge`), on test_capture's lab (r2's REAL configuration and
  committed intent): the same running and startup pass and differing ones fail naming Persist;
  the image gate passes, fails on a missing image or boot file, and says so where the platform
  has no `show boot`; another hold fails.
- The run (`reload_op.run`) with the device-facing parts replaced: reloaded and verified (the
  window declared before the reload, six steps, the record written and read back on History);
  moved since the preview (nothing sent, no window); not back within the bound; back running
  something else; a window that cannot be recorded (nothing sent).
- The routes: the Actions menu's Reload…, the card that starts its own read, a write naming no
  network refused, a reason not shaped as one refused with nothing started, a confirm with no
  preview refused.
"""

import re

import pytest

from modules.nsot import blast_radius, reload_op
from tests.test_device_capture_v2 import lab  # noqa: F401 (the fixture)


def _hv(*ifaces):
    return {"interfaces": [dict(name=n, ipv4=a, **({"shutdown": True} if s else {}))
                           for n, a, s in ifaces]}


FLEET = {
    "s3": _hv(("Vlan99", "192.0.2.3 255.255.255.0", False),
              ("Vlan100", "198.51.100.1 255.255.255.0", False)),
    "r1": _hv(("GigabitEthernet1", "198.51.100.2 255.255.255.0", False),
              ("GigabitEthernet2", "203.0.113.1 255.255.255.252", False)),
    "r2": _hv(("GigabitEthernet1", "203.0.113.2 255.255.255.252", False),
              ("Loopback0", "203.0.113.200 255.255.255.255", False)),
}
HOST = ["192.0.2.0/24", "198.18.0.0/15"]


class TestBlastRadius:
    def test_a_switch_takes_its_vlan_subnets_and_everything_behind(self):
        got = blast_radius.radius(FLEET, HOST, "s3")
        assert got["state"] == "known" and got["cut"] == ["r1", "r2"], got

    def test_a_device_on_the_switch_s_own_vlan_is_cut_with_it(self):
        """r9 shares Mercury's own subnet, a VLAN s3 routes: s3 carries it at layer 2, so r9
        goes too. Without the VLAN rule the shared subnet would keep r9 reachable."""
        fleet = dict(FLEET, r9=_hv(("GigabitEthernet1", "192.0.2.9 255.255.255.0", False)))
        assert "r9" in blast_radius.radius(fleet, HOST, "s3")["cut"]
        assert blast_radius.radius(fleet, HOST, "r1")["cut"] == ["r2"]

    def test_a_router_cuts_what_is_behind_it(self):
        assert blast_radius.radius(FLEET, HOST, "r1")["cut"] == ["r2"]

    def test_an_edge_device_cuts_nothing(self):
        got = blast_radius.radius(FLEET, HOST, "r2")
        assert got["state"] == "known" and got["cut"] == []
        assert "layer 2" in got["why"], "the caveat is said with the answer"

    def test_unknown_when_no_subnet_of_this_host_holds_a_device(self):
        got = blast_radius.radius(FLEET, ["198.18.0.0/15"], "r1")
        assert got["state"] == "unknown" and "where Mercury attaches" in got["why"]

    def test_unknown_for_a_device_with_no_intent(self):
        assert blast_radius.radius(FLEET, HOST, "zz")["state"] == "unknown"

    def test_a_shut_interface_is_no_link(self):
        fleet = dict(FLEET, r1=_hv(("GigabitEthernet1", "198.51.100.2 255.255.255.0", False),
                                   ("GigabitEthernet2", "203.0.113.1 255.255.255.252", True)))
        # r2 is reachable through nothing now, so restarting r1 cuts nothing more.
        assert blast_radius.radius(fleet, HOST, "r1")["cut"] == []


VERSION = 'Cisco IOS XE Software\nSystem image file is "bootflash:packages.conf"\n'
DIR_OK = "Directory of bootflash:/packages.conf\n  12 -rw- 7000 packages.conf\n"


def _reads(lab, **over):  # noqa: F811
    text = lab["captured"]
    reads = {"running": text, "startup": text, "version": VERSION,
             "boot": "BOOT variable = bootflash:packages.conf,12;\n",
             "dirs": {"bootflash:packages.conf": DIR_OK}}
    reads.update(over)
    return reads


def _gate(j, key):
    return next(g for g in j["gates"] if g["key"] == key)


class TestTheGates:
    def test_the_same_running_and_startup_pass(self, lab):  # noqa: F811
        j = reload_op.judge("Lab", "r2", "cisco_iosxe", _reads(lab))
        assert _gate(j, "unsaved")["state"] == "pass"
        assert _gate(j, "image")["state"] == "pass"
        assert re.fullmatch(r"[0-9a-f]{16}", j["fingerprint"])

    def test_unsaved_changes_fail_naming_persist(self, lab):  # noqa: F811
        j = reload_op.judge("Lab", "r2", "cisco_iosxe",
                            _reads(lab, startup=lab["captured"].replace("hostname r2",
                                                                        "hostname r2-old")))
        g = _gate(j, "unsaved")
        assert g["state"] == "fail" and "Persist" in g["detail"]
        assert g in j["failing"]

    def test_a_missing_image_fails(self, lab):  # noqa: F811
        j = reload_op.judge("Lab", "r2", "cisco_iosxe",
                            _reads(lab, boot="", dirs={"bootflash:packages.conf":
                                                       "%Error opening"}))
        g = _gate(j, "image")
        assert g["state"] == "fail" and "does not show it" in g["detail"]
        assert "boot variable" not in g["detail"], "failed on the boot variable, not the image"

    def test_a_boot_variable_naming_a_missing_file_fails(self, lab):  # noqa: F811
        j = reload_op.judge("Lab", "r2", "cisco_iosxe", _reads(
            lab, boot="BOOT variable = bootflash:other.bin,12;\n",
            dirs={"bootflash:packages.conf": DIR_OK, "bootflash:other.bin": "%Error"}))
        g = _gate(j, "image")
        assert g["state"] == "fail" and "other.bin" in g["detail"]

    def test_a_platform_without_show_boot_is_said(self, lab):  # noqa: F811
        j = reload_op.judge("Lab", "r2", "cisco_ios", _reads(lab, boot=""))
        g = _gate(j, "image")
        assert g["state"] == "pass" and "no `show boot`" in g["detail"]
        assert "placeholder" in j["bound_words"]

    def test_another_hold_fails(self, lab, monkeypatch):  # noqa: F811
        monkeypatch.setattr("modules.nsot.device_ops.busy_text",
                            lambda *a: "held by a deploy (ana, 20 s)")
        j = reload_op.judge("Lab", "r2", "cisco_iosxe", _reads(lab))
        assert _gate(j, "busy")["state"] == "fail"

    def test_a_departure_needs_the_reason(self, lab):  # noqa: F811
        from tests.test_intent_match import _broken
        broken = _broken(lab["captured"])
        j = reload_op.judge("Lab", "r2", "cisco_iosxe",
                            _reads(lab, running=broken, startup=broken))
        assert _gate(j, "drift")["state"] == "ack" and j["departs"] is True
        assert not j["failing"], "a departure is acknowledged by the reason, never a refusal"


@pytest.fixture
def run_lab(lab, monkeypatch):  # noqa: F811
    """The run with the device-facing parts replaced: what was sent is recorded."""
    sent = []
    monkeypatch.setattr(reload_op, "_device", lambda l, h: {"hostname": "r2",
                                                            "ip": "203.0.113.12",
                                                            "platform": "cisco_iosxe"})
    return {**lab, "sent": sent,
            "reloader": lambda d: sent.append("reload") or {"ok": True, "outcome": "reloading",
                                                            "detail": "dropped after 2 s"},
            "back": lambda ip, bound: {"ok": True, "after_s": 300, "attempts": 30}}


def _fp(lab, **over):  # noqa: F811
    return reload_op.judge("Lab", "r2", "cisco_iosxe", _reads(lab, **over))["fingerprint"]


class TestTheRun:
    def test_it_reloads_verifies_and_records(self, run_lab, monkeypatch):
        from modules import restarts

        declared = []
        real = restarts.record_planned

        def spy(*a, **k):
            declared.append(list(run_lab["sent"]))       # what had been sent at that moment
            return real(*a, **k)
        monkeypatch.setattr(restarts, "record_planned", spy)
        out = reload_op.run("Lab", "r2", actor="ana@example.invalid", fingerprint=_fp(run_lab),
                            reason="a line card swap needs a cold start",
                            reader=lambda d: _reads(run_lab), reloader=run_lab["reloader"],
                            wait=run_lab["back"])
        assert out["ok"] is True and out["outcome"] == "reloaded", out
        assert [s["step"] for s in out["steps"]] == ["read", "window", "reload", "wait",
                                                     "verify"]
        assert declared == [[]], "the window was declared after something was sent"
        assert out["record"]["ok"] is True
        rows = reload_op.read_records(reload_op._repo("Lab"))["rows"]
        assert rows[0]["outcome"] == "reloaded" and rows[0]["by"] == "ana@example.invalid"

    def test_moved_since_the_preview_sends_nothing(self, run_lab, monkeypatch):
        from modules import restarts
        monkeypatch.setattr(restarts, "record_planned",
                            lambda *a, **k: pytest.fail("a window for a reload not sent"))
        out = reload_op.run("Lab", "r2", actor="a", fingerprint="0" * 16, reason="x y z w",
                            reader=lambda d: _reads(run_lab), reloader=run_lab["reloader"],
                            wait=run_lab["back"])
        assert out["outcome"] == "moved" and run_lab["sent"] == []
        assert "previewed 0000000000000000" in out["steps"][0]["detail"]

    def test_not_back_within_the_bound(self, run_lab):
        out = reload_op.run("Lab", "r2", actor="a", fingerprint=_fp(run_lab), reason="r e a s",
                            reader=lambda d: _reads(run_lab), reloader=run_lab["reloader"],
                            wait=lambda ip, b: {"ok": False, "after_s": b, "attempts": 9,
                                                "detail": f"it did not answer within {b} s"})
        assert out["outcome"] == "not_back" and out["ok"] is False
        assert run_lab["sent"] == ["reload"]

    def test_back_running_something_else(self, run_lab):
        reads = iter([_reads(run_lab), _reads(run_lab, running="hostname r2\nend\n")])
        out = reload_op.run("Lab", "r2", actor="a", fingerprint=_fp(run_lab), reason="r e a s",
                            reader=lambda d: next(reads), reloader=run_lab["reloader"],
                            wait=run_lab["back"])
        assert out["outcome"] == "differs" and "line(s) gone" in out["steps"][-1]["detail"]

    def test_a_window_that_cannot_be_recorded_sends_nothing(self, run_lab, monkeypatch):
        from modules import restarts
        monkeypatch.setattr(restarts, "record_planned",
                            lambda *a, **k: {"ok": False, "error": "the restart record could "
                                                                   "not be read"})
        out = reload_op.run("Lab", "r2", actor="a", fingerprint=_fp(run_lab), reason="r e a s",
                            reader=lambda d: _reads(run_lab), reloader=run_lab["reloader"],
                            wait=run_lab["back"])
        assert out["outcome"] == "no_window" and run_lab["sent"] == []


def test_the_wait_asks_until_it_answers_within_the_bound():
    clock = iter([0, 0, 10, 20, 30])
    tries = {"n": 0}

    def connect():
        tries["n"] += 1
        if tries["n"] < 3:
            raise OSError("refused")
    got = reload_op._wait_for_ssh("192.0.2.9", 100, clock=lambda: next(clock),
                                  sleep=lambda s: None, connect=connect)
    assert got["ok"] is True and got["attempts"] == 3
    assert reload_op._wait_for_ssh("", 100)["ok"] is False


class TestTheRoutes:
    def test_the_menu_offers_reload_and_the_card_starts_its_own_read(self, lab):  # noqa: F811
        html = lab["client"].get("/v2/device/r2/actions").get_data(as_text=True)
        assert 'hx-get="/v2/device/r2/reload' in html and "Reload…" in html
        card = lab["client"].get("/v2/device/r2/reload").get_data(as_text=True)
        assert 'hx-post="/v2/device/r2/reload/start' in card and 'hx-trigger="load"' in card

    def test_a_write_naming_no_network_is_refused(self, lab):  # noqa: F811
        r = lab["client"].post("/v2/device/r2/reload/start", data={})
        assert r.status_code == 400

    @pytest.mark.parametrize("body,words", [
        ({"list": "Lab", "fingerprint": "abc", "reason": "ok"}, "too short to be a reason"),
        ({"list": "Lab", "reason": "a line card swap needs a cold start"},
         "carried no preview"),
    ])
    def test_a_confirm_without_a_reason_or_a_preview_starts_nothing(self, lab, body, words,  # noqa: F811
                                                                     monkeypatch):
        from modules.nsot import capture_job
        monkeypatch.setattr(capture_job, "start", lambda *a, **k: pytest.fail("started"))
        r = lab["client"].post("/v2/device/r2/reload/confirm", data=body)
        assert r.status_code == 400 and words in r.get_data(as_text=True)

    def test_the_preview_card_draws_the_gates_and_the_radius(self, lab, monkeypatch):  # noqa: F811
        from modules.nsot import capture_job
        monkeypatch.setattr(reload_op, "read_device", lambda d: _reads(lab))
        monkeypatch.setattr(blast_radius, "for_device", lambda repo, host: {
            "state": "known", "cut": ["s1", "s2"], "attached": [], "why": blast_radius.CAVEAT})
        html = lab["client"].post("/v2/device/r2/reload/start", data={"list": "Lab"}) \
            .get_data(as_text=True)
        job = re.search(r"/reload/job/([0-9a-f]+)", html).group(1)
        assert capture_job.wait(job, 30)
        card = lab["client"].get(f"/v2/device/r2/reload/job/{job}").get_data(as_text=True)
        assert "Mercury loses reach to 2 other devices" in card
        for words in ("running against startup", "its golden and its intent",
                      "startup carries Mercury", "the boot image", "no other operation holds"):
            assert words in card, words
        assert 'name="fingerprint"' in card and 'name="reason"' in card
        assert "Reload r2 (up to 17 minutes out)" in card
