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

    def test_a_device_as_its_golden_and_intent_say_passes_the_drift_gate(self, lab):  # noqa: F811
        """Lab 7 (b)'s mutation sample (2026-10-17): the drift gate's `pass` side was never
        asserted, so `departs` computed as always True (the golden comparison skipped, the
        intent's state misread, `"ack" if departs or True`) survived. r2 running its
        golden and its committed intent departs from nothing."""
        j = reload_op.judge("Lab", "r2", "cisco_iosxe", _reads(lab))
        g = _gate(j, "drift")
        assert j["departs"] is False and g["state"] == "pass"
        assert g["detail"] == "it matches its golden and its committed intent"

    def test_no_golden_is_a_departure(self, lab, monkeypatch):  # noqa: F811
        """Lab 7 (b): with no golden, `drift` read as EQUAL (`{"equal": True}`), or `departs`
        needing the golden AND the intent to differ, survived: a device whose golden is gone
        would reload with no reason asked. Running what its intent says is not enough."""
        monkeypatch.setattr("modules.nsot.repo.golden_at", lambda *a, **k: None)
        j = reload_op.judge("Lab", "r2", "cisco_iosxe", _reads(lab))
        g = _gate(j, "drift")
        assert j["departs"] is True and g["state"] == "ack"
        assert g["detail"].startswith("its running configuration differs from its golden; ")

    def test_a_startup_without_mercury_s_credential_fails(self, lab):  # noqa: F811
        """Lab 7 (b): the credential gate's `"pass" if carries.get("ok") or True` survived: no
        test planted a startup config missing the running config's `username` lines, the
        lockout a reload would boot into. It fails, and is among the failing gates."""
        startup = "\n".join(l for l in lab["captured"].splitlines()
                            if not l.startswith("username "))
        assert startup != lab["captured"], "the capture holds no username line to remove"
        j = reload_op.judge("Lab", "r2", "cisco_iosxe", _reads(lab, startup=startup))
        g = _gate(j, "credential")
        assert g["state"] == "fail" and "does not carry" in g["detail"]
        assert g in j["failing"]

    def test_the_fingerprint_binds_what_the_preview_read(self, lab):  # noqa: F811
        """Lab 7 (b): the fingerprint the confirm is bound to ignoring the running config
        (`_h(None)`), the startup config, or the booted image survived every test: the run's
        "moved" test sends a made-up fingerprint, never a real one of a changed device. Each,
        changed alone, moves it; the same reads give the same one."""
        was = _fp(lab)
        assert _fp(lab) == was
        # The running config alone: a device ALREADY departing that changes again departs
        # still, so only the running config's own hash can say it moved.
        from tests.test_intent_match import _broken
        broken = _broken(lab["captured"])
        departing = _fp(lab, running=broken, startup=broken)
        assert _fp(lab, running=broken + "\nbanner motd ^changed^\n",
                   startup=broken) != departing
        assert _fp(lab, startup=lab["captured"] + "\nbanner motd ^changed^\n") != was
        other = VERSION.replace("packages.conf", "other.bin")
        assert _fp(lab, version=other,
                   dirs={"bootflash:other.bin": DIR_OK.replace("packages.conf",
                                                               "other.bin"),
                         "bootflash:packages.conf": DIR_OK}) != was


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

    def test_a_reload_that_raised_is_not_reloaded(self, run_lab):
        """Lab 7 (b)'s mutation sample (2026-10-17): the reload's exception read as SENT
        (`"ok": True` in its stand-in answer) survived, so a reload that never left would have
        waited for a return and could be recorded `reloaded`. It ends `error`, naming the
        exception, and nothing waits for a device that was not reloaded."""
        def _raises(d):
            raise OSError("the session dropped before reload was sent")
        out = reload_op.run("Lab", "r2", actor="a", fingerprint=_fp(run_lab), reason="r e a s",
                            reader=lambda d: _reads(run_lab), reloader=_raises,
                            wait=lambda ip, b: pytest.fail("waited for a reload not sent"))
        assert out["ok"] is False and out["outcome"] == "error", out
        step = out["steps"][-1]
        assert step["step"] == "reload" and step["ok"] is False
        assert "the session dropped" in step["detail"]


class TestTheRunJudgesAgain:
    def test_a_gate_failing_at_the_run_refuses_with_nothing_sent(self, run_lab, monkeypatch):
        """Lab 7 (b): the run's own "a gate fails now" refusal was reached by no test, so
        every mutant of it survived (the join of the failing gates, its outcome, its step's
        `ok`). The boot image is not in the fingerprint (`dir` is not), so an image deleted
        between the preview and the run reaches exactly this gate: the run refuses, sends
        nothing, declares no window, and its read step is not drawn as passed."""
        from modules import restarts
        monkeypatch.setattr(restarts, "record_planned",
                            lambda *a, **k: pytest.fail("a window for a reload not sent"))
        fp = _fp(run_lab)
        gone = _reads(run_lab, dirs={"bootflash:packages.conf": "%Error opening"})
        assert reload_op.judge("Lab", "r2", "cisco_iosxe", gone)["fingerprint"] == fp
        out = reload_op.run("Lab", "r2", actor="a", fingerprint=fp, reason="r e a s",
                            reader=lambda d: gone, reloader=run_lab["reloader"],
                            wait=run_lab["back"])
        assert out["ok"] is False and out["outcome"] == "refused", out
        assert run_lab["sent"] == []
        (step,) = out["steps"]
        assert step["step"] == "read" and step["ok"] is False
        assert step["detail"].startswith("a gate fails now: the boot image: it booted "
                                         "bootflash:packages.conf")

    def test_a_refusal_s_steps_are_never_drawn_as_passed(self, run_lab, monkeypatch):
        """Lab 7 (b): the moved run's and the unrecorded window's step `ok` read as True
        survived (the tests checked the outcome, not the step): a refusal drawn with a green
        step is a wrong thing that looks right."""
        from modules import restarts
        out = reload_op.run("Lab", "r2", actor="a", fingerprint="0" * 16, reason="r e a s",
                            reader=lambda d: _reads(run_lab), reloader=run_lab["reloader"],
                            wait=run_lab["back"])
        assert [(s["step"], s["ok"]) for s in out["steps"]] == [("read", False)]
        monkeypatch.setattr(restarts, "record_planned",
                            lambda *a, **k: {"ok": False, "error": "unreadable"})
        out = reload_op.run("Lab", "r2", actor="a", fingerprint=_fp(run_lab),
                            reason="r e a s", reader=lambda d: _reads(run_lab),
                            reloader=run_lab["reloader"], wait=run_lab["back"])
        assert [(s["step"], s["ok"]) for s in out["steps"]] == [("read", True),
                                                               ("window", False)]
        assert out["steps"][1]["detail"] == "unreadable: nothing was sent"

    def test_a_held_device_is_not_reloaded_and_not_ok(self, run_lab):
        """Lab 7 (b): the run's answer starting `"ok": True` survived, and a device held by
        another operation returns that answer before any `finish`: a refusal that said ok."""
        import threading

        from modules.nsot import device_ops
        held, done = threading.Event(), threading.Event()

        def _other():
            with device_ops.hold("Lab", "r2", "deploy", "someone@example.com"):
                held.set()
                done.wait(10)
        worker = threading.Thread(target=_other)
        worker.start()
        try:
            assert held.wait(10)
            out = reload_op.run("Lab", "r2", actor="a", fingerprint=_fp(run_lab),
                                reason="r e a s", reader=lambda d: _reads(run_lab),
                                reloader=run_lab["reloader"], wait=run_lab["back"])
        finally:
            done.set()
            worker.join(10)
        assert out["ok"] is False and out["outcome"] == "busy", out
        assert "someone@example.com" in out["error"] and run_lab["sent"] == []


class TestTheConfirmStartsTheBoundRun:
    def test_the_job_runs_what_was_confirmed_as_the_person(self, monkeypatch):
        """Lab 7 (b): every argument of the job's own call to `run` (the fingerprint, the
        list, the device, the actor, the reason), the identity it carries, and the masking of
        its answer survived: the route tests stop at the job's start. The job runs the run
        bound to the confirmed fingerprint, as the verified person, and its answer leaves
        masked."""
        from modules import identity
        from modules.nsot import capture_job

        started, ran = {}, {}
        monkeypatch.setattr(capture_job, "start", lambda *a, **k: started.update(
            work=a[3], list=a[0], actor=a[2], kw=k) or "job-1")
        ident = object()

        def fake_run(list_name, host, *, actor, fingerprint, reason, **kw):
            ran.update(list=list_name, host=host, actor=actor, fingerprint=fingerprint,
                       reason=reason, carried=identity._CARRIED.ident)
            return {"ok": True, "steps": [{"detail": "snmp-server community Planted-Comm-7 RO"}]}
        monkeypatch.setattr(reload_op, "run", fake_run)
        got = reload_op.confirm_and_start("Lab", "r2", "ab" * 8,
                                          "  a line card   swap needs a cold start ",
                                          actor="ana@example.invalid", ident=ident)
        assert got == {"job": "job-1"}
        assert started["list"] == "Lab" and started["actor"] == "ana@example.invalid"
        assert started["kw"]["device"] == "r2" and started["kw"]["card"] == "reload"
        answer = started["work"]("job-1")
        assert ran == {"list": "Lab", "host": "r2", "actor": "ana@example.invalid",
                       "fingerprint": "ab" * 8,
                       "reason": "a line card swap needs a cold start", "carried": ident}
        assert "Planted-Comm-7" not in repr(answer)
        assert answer["ok"] is True


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
