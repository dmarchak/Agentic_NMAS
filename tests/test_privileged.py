"""Tier 2, "Run a privileged command…" (modules/nsot/privileged.py, routes/privileged_v2.py;
boards T2-A to T2-D, approved 2026-10-08; NSOT_TIER2_PRIVILEGED.md).

Built from the probe's measurements on r2 and s1: the reads its verify judges are those
captures (`tests/fixtures/operational/`, the README's Tier 2 section), the prompts it answers
are the ones the devices asked (`tests/fixtures/tier2/`). Where a test needs a state no capture
holds (a debug on, a buffer with lines), it is the capture with one line added, said so.
The device session is faked at the connection seam; the engine, the hold, the record, the
routes and History run for real.
"""

import html as html_mod
import os
import re

import pytest

from modules.nsot import privileged as P
from tests.test_device_v2 import lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPS = os.path.join(ROOT, "tests", "fixtures", "operational")
T2 = os.path.join(ROOT, "tests", "fixtures", "tier2")
R2_CFG = os.path.join(ROOT, "tests", "fixtures", "configs", "fleet", "r2.cfg")


def _cap(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


class TestTheMeasuredPrompts:
    def test_the_prompts_are_what_the_devices_asked(self):
        assert _cap(T2, "r2__clear_counters_Loopback0.txt").strip().splitlines()[-1] == \
            P.COUNTERS_PROMPT
        assert _cap(T2, "r2__clear_logging.txt").strip().splitlines()[-1] == P.LOGGING_PROMPT
        assert P.COMMANDS["clear-arp"]["prompt"] is None
        assert P.COMMANDS["undebug-all"]["prompt"] is None


class TestVerifyOnTheRealReads:
    @pytest.mark.parametrize("host, seconds", [("r2", 5), ("s1", 2)])
    def test_counters_cleared_just_now(self, host, seconds):
        before = _cap(OPS, f"{host}__show_interfaces_Loopback0.txt")
        after = _cap(OPS, f"{host}__show_interfaces_Loopback0__after_clear_counters.txt")
        assert P.verify("clear-counters", before, after) == {
            "ok": True, "words": f'cleared {seconds} s ago (Last clearing of "show interface" '
                                 'counters)'}
        got = P.verify("clear-counters", before, before)
        assert got["ok"] is False and "reads never" in got["words"], got

    def test_counters_with_no_clearing_line_decide_nothing(self):
        assert P.verify("clear-counters", "", "Loopback0 is up")["ok"] is None

    @pytest.mark.parametrize("host", ["r2", "s1"])
    def test_logging_emptied(self, host):
        after = _cap(OPS, f"{host}__show_logging__after_clear_logging.txt")
        # A buffer with a line: the capture with one line added after its header.
        before = after.rstrip("\n") + "\n*Oct  8 17:40:01.000: %SYS-5-CONFIG_I: Configured\n"
        assert P.verify("clear-logging", before, after)["ok"] is True
        assert P.verify("clear-logging", before, before)["ok"] is False
        assert P.verify("clear-logging", before, "Syslog logging: enabled")["ok"] is None

    @pytest.mark.parametrize("host", ["r2", "s1"])
    def test_nothing_on_is_the_measured_form_exactly(self, host):
        text = _cap(OPS, f"{host}__show_debugging.txt")
        assert P.nothing_on(text)
        on = text + "\nIP routing:\n  IP routing debugging is on\n"   # the capture, one debug added
        assert not P.nothing_on(on)
        assert P.verify("undebug-all", on, on)["ok"] is None, "never claimed by resemblance"

    def test_arp_back(self):
        row = "Internet  198.51.100.{n}   1   5254.0000.000{n}  ARPA   GigabitEthernet3\n"
        two = row.format(n=1) + row.format(n=2)
        assert P.verify("clear-arp", two, two)["ok"] is True
        assert P.verify("clear-arp", two, row.format(n=1))["ok"] is False


def _loopback_address():
    """r2's real config (the lab fixture's committed golden for r3): Loopback0's address."""
    text = _cap(R2_CFG)
    block = re.search(r"^interface Loopback0\n((?: .*\n)+)", text, re.M).group(1)
    return re.search(r"ip address (\S+)", block).group(1)


@pytest.fixture
def t2(lab, monkeypatch):  # noqa: F811
    """The lab, r3 reached on its golden's Loopback0 address (as this lab's devices are), its
    session faked: reads answered from the captures, sends recorded."""
    import modules.device as D
    real = D.load_saved_devices
    loop = _loopback_address()

    def devices(path):
        out = real(path)
        for d in out:
            if d.get("hostname") == "r3":
                d["ip"] = loop
        return out

    monkeypatch.setattr("modules.device.load_saved_devices", devices)
    session = Session()
    monkeypatch.setattr("modules.connection.with_temp_connection", session)
    monkeypatch.setattr("modules.commands.run_device_command",
                        lambda conn, cmd, **kw: conn.read(cmd))
    monkeypatch.setattr("time.sleep", lambda s: None)
    lab["session"], lab["loop"] = session, loop
    return lab


class Session:
    """r3 at the connection seam: each read answered in turn from *reads*, each send's answer
    from *sends*; everything sent recorded."""

    def __init__(self):
        self.reads, self.sends, self.sent, self.calls = {}, {}, [], {}

    def __call__(self, dev, fn):
        return fn(self)

    def read(self, cmd):
        seq = self.reads.get(cmd, f"% no capture for {cmd}")
        self.calls[cmd] = self.calls.get(cmd, 0) + 1
        return seq[min(self.calls[cmd], len(seq)) - 1] if isinstance(seq, list) else seq

    def send_command_timing(self, text, **kw):
        self.sent.append(text)
        return self.sends.get(text, "r3#")


COUNTERS_BEFORE = _cap(OPS, "r2__show_interfaces_Loopback0.txt").replace("Loopback0", "GigabitEthernet2")
COUNTERS_AFTER = _cap(OPS, "r2__show_interfaces_Loopback0__after_clear_counters.txt").replace(
    "Loopback0", "GigabitEthernet2")


class TestThePlan:
    def test_the_choices_are_the_devices_own_and_never_the_management_one(self, t2):
        p = P.plan("Lab", "r3", "", "")
        assert p["management"] == "Loopback0"
        assert "GigabitEthernet2" in p["interfaces"] and "Loopback0" not in p["interfaces"]
        assert [c["key"] for c in p["commands"]] == ["clear-counters", "clear-arp",
                                                     "clear-logging", "undebug-all"]
        assert "clear-bgp-soft" in p["not_measured"]

    @pytest.mark.parametrize("key, arg, words", [
        ("clear-counters", "Loopback0", "the address Mercury reaches r3 on"),
        ("clear-arp", "Loopback0", "Tier 2 never clears it"),
        ("clear-counters", "GigabitEthernet99", "is not an interface of r3"),
        ("clear-counters", "", "choose an interface"),
        ("clear-logging", "GigabitEthernet2", "takes no argument"),
        ("clear-bgp-soft", "", "not measured yet"),
        ("reload", "", "is not a Tier 2 command here"),
    ])
    def test_refused_before_anything_is_read(self, t2, key, arg, words):
        p = P.plan("Lab", "r3", key, arg)
        assert not p["ok"] and words in " ".join(p["refusals"]), p["refusals"]

    def test_the_hash_binds_the_device_and_the_command(self, t2):
        a = P.plan("Lab", "r3", "clear-counters", "GigabitEthernet2")
        assert a["ok"] and a["hash"] == P.plan("Lab", "r3", "clear-counters", "GigabitEthernet2")["hash"]
        assert a["hash"] != P.plan("Lab", "r3", "clear-counters", "GigabitEthernet3")["hash"]
        assert a["command"] == "clear counters GigabitEthernet2" and a["prompt"] == P.COUNTERS_PROMPT


REASON = "baseline before watching CRC errors"


class TestApply:
    def _apply(self, t2, key="clear-counters", arg="GigabitEthernet2", reason=REASON, **kw):
        h = P.plan("Lab", "r3", key, arg)["hash"]
        return P.apply("Lab", "r3", key, arg, actor="op@example.invalid",
                       confirmed_hash=kw.get("hash", h), reason=reason)

    def test_the_measured_prompt_answered_once_before_kept_verified_recorded(self, t2):
        s = t2["session"]
        s.reads["show interfaces GigabitEthernet2"] = [COUNTERS_BEFORE, COUNTERS_AFTER]
        s.sends["clear counters GigabitEthernet2"] = _cap(T2, "r2__clear_counters_Loopback0.txt")
        rec = self._apply(t2)
        assert rec["state"] == "done", rec
        assert s.sent == ["clear counters GigabitEthernet2", "\n"], s.sent
        assert rec["answered"] == P.COUNTERS_PROMPT
        assert "403 packets output" in rec["before"], "the evidence kept first (T2-4)"
        assert rec["verify"]["ok"] and rec["reason"] == REASON
        assert P.get("Lab", rec["id"])["state"] == "done"

    def test_any_other_question_is_not_answered(self, t2):
        s = t2["session"]
        s.reads["show interfaces GigabitEthernet2"] = COUNTERS_BEFORE
        s.sends["clear counters GigabitEthernet2"] = "Proceed? [yes/no]:"
        rec = self._apply(t2)
        assert rec["state"] == "refused" and "not the measured prompt" in rec["why"], rec
        assert "\n" not in s.sent

    def test_a_short_reason_or_a_moved_plan_sends_nothing(self, t2):
        with pytest.raises(P.Refused, match="3 words or more"):
            self._apply(t2, reason="because")
        with pytest.raises(P.Refused, match="the plan changed"):
            self._apply(t2, hash="0" * 16)
        assert t2["session"].sent == []

    def test_undebug_with_nothing_on_says_it_changed_nothing(self, t2):
        s = t2["session"]
        s.reads["show debugging"] = _cap(OPS, "r2__show_debugging.txt")
        s.sends["undebug all"] = _cap(T2, "r2__undebug_all.txt")
        rec = self._apply(t2, key="undebug-all", arg="")
        assert rec["state"] == "done" and rec["changed_nothing"] is True, rec
        assert s.sent == ["undebug all"], "no prompt, so nothing answered"

    def test_a_device_error_is_a_failure(self, t2):
        s = t2["session"]
        s.reads["show ip arp GigabitEthernet2"] = ""
        s.sends["clear arp-cache interface GigabitEthernet2"] = (
            "% Invalid input detected at '^' marker.\nr3#")
        rec = self._apply(t2, key="clear-arp")
        assert rec["state"] == "failed" and rec["why"].startswith("% Invalid input"), rec


class TestTheCard:
    def _get(self, t2, url):
        r = t2["client"].get(url)
        return html_mod.unescape(r.get_data(as_text=True))

    def test_the_menu_row_and_the_choose_card(self, t2):
        page = self._get(t2, "/v2/device/r3/actions")
        assert re.search(r'data-op="privileged"[^>]*>Run a privileged command…</a>', page)
        html = self._get(t2, "/v2/device/r3/privileged?list=Lab")
        assert "Run a privileged command on r3" in html
        assert "<option>GigabitEthernet2</option>" in html
        assert "<option>Loopback0</option>" not in html
        assert "Loopback0 carries the address Mercury reaches it on, and is never offered" in html
        assert re.search(r'value="clear-bgp-soft" disabled', html)

    def test_preview_then_confirm_then_the_result(self, t2):
        from modules.nsot import capture_job
        s = t2["session"]
        s.reads["show interfaces GigabitEthernet2"] = [COUNTERS_BEFORE, COUNTERS_BEFORE,
                                                       COUNTERS_AFTER]
        s.sends["clear counters GigabitEthernet2"] = _cap(T2, "r2__clear_counters_Loopback0.txt")
        r = t2["client"].post("/v2/device/r3/privileged/preview",
                              data={"list": "Lab", "key": "clear-counters",
                                    "arg": "GigabitEthernet2"}, headers={"HX-Request": "true"})
        html = html_mod.unescape(r.get_data(as_text=True))
        job = re.search(r"job=([0-9a-f]{32})", html)
        run = re.search(r"(?:run=|name=\"run\" value=\")([0-9TZ]+-[0-9a-f]{32})", html).group(1)
        if job:                                   # still reading when the card was drawn
            assert capture_job.wait(job.group(1), 30)
        html = self._get(t2, f"/v2/device/r3/privileged?list=Lab&key=clear-counters"
                             f"&arg=GigabitEthernet2&run={run}")
        assert "403 packets output" in html and P.COUNTERS_PROMPT in html
        assert "Does not apply: cleared counters cannot be put back" in html
        h = re.search(r'name="hash" value="([0-9a-f]{16})"', html).group(1)
        r = t2["client"].post("/v2/device/r3/privileged/confirm", headers={"HX-Request": "true"},
                              data={"list": "Lab", "key": "clear-counters",
                                    "arg": "GigabitEthernet2", "hash": h, "reason": "too short"})
        assert "Refused:" in html_mod.unescape(r.get_data(as_text=True))
        r = t2["client"].post("/v2/device/r3/privileged/confirm", headers={"HX-Request": "true"},
                              data={"list": "Lab", "key": "clear-counters",
                                    "arg": "GigabitEthernet2", "hash": h, "reason": REASON})
        html = html_mod.unescape(r.get_data(as_text=True))
        job = re.search(r"job=([0-9a-f]{32})", html).group(1)
        result = re.search(r"result=([0-9TZ-]+[0-9a-f]{32})", html).group(1)
        assert capture_job.wait(job, 30)
        html = self._get(t2, f"/v2/device/r3/privileged?list=Lab&key=clear-counters"
                             f"&arg=GigabitEthernet2&result={result}")
        assert "done, verified" in html and REASON in html, html[:300]
        assert "cleared 5 s ago" in html

    def test_history_shows_the_run(self, t2):
        s = t2["session"]
        s.reads["show interfaces GigabitEthernet2"] = [COUNTERS_BEFORE, COUNTERS_AFTER]
        s.sends["clear counters GigabitEthernet2"] = P.COUNTERS_PROMPT
        h = P.plan("Lab", "r3", "clear-counters", "GigabitEthernet2")["hash"]
        P.apply("Lab", "r3", "clear-counters", "GigabitEthernet2", actor="op@example.invalid",
                confirmed_hash=h, reason=REASON)
        from modules.history_sources import privileged
        from modules.nsot import listref
        got = privileged({"ref": listref.resolve("Lab"), "device": "", "limit": 50,
                          "since": None, "members": None})
        (e,) = got["events"]
        assert e["what"] == "Privileged: clear counters GigabitEthernet2"
        assert e["outcome"] == "done, verified" and e["detail"] == REASON


@pytest.mark.parametrize("width", [1366, 390])
@pytest.mark.parametrize("state", ["choose", "confirm", "result"])
def test_the_card_in_a_real_browser_stays_inside_itself(t2, width, state):
    """Boards T2-A to T2-C and T2 phone: every cell ends inside its card; no sideways scroll."""
    from tests import browser
    from tests.test_v2_layout_in_a_browser import CELLS_INSIDE_JS
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    from modules.nsot import reads
    s = t2["session"]
    s.reads["show interfaces GigabitEthernet2"] = [COUNTERS_BEFORE, COUNTERS_BEFORE, COUNTERS_AFTER]
    s.sends["clear counters GigabitEthernet2"] = P.COUNTERS_PROMPT
    query = "op=privileged&list=Lab"
    if state in ("confirm", "result"):
        run = reads.run("Lab", ["r3"], ["show interfaces GigabitEthernet2"], "op@example.invalid",
                        session=s)["id"]
        query += f"&key=clear-counters&arg=GigabitEthernet2&run={run}"
    if state == "result":
        h = P.plan("Lab", "r3", "clear-counters", "GigabitEthernet2")["hash"]
        rec = P.apply("Lab", "r3", "clear-counters", "GigabitEthernet2",
                      actor="op@example.invalid", confirmed_hash=h, reason=REASON)
        query += f"&result={rec['id']}"
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": width, "height": 1000})
            b.go(srv.url(f"/v2/device/r3?{query}"))
            b.wait_for("return !!window.Alpine && !document.querySelector('.htmx-request')", 15)
            assert b.js("return !!document.getElementById('device-op')")
            got, n = b.js(CELLS_INSIDE_JS)
            assert not got, "\n".join(got)
            wide = b.js("return document.documentElement.scrollWidth - window.innerWidth")
            assert wide <= 1, f"the page scrolls sideways by {wide}px at {width}px"
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def test_the_agent_has_no_way_to_it():
    """T2-3: the agent never RUNS Tier 2; no module the agent's tools import reaches it."""
    src = open(os.path.join(ROOT, "modules", "ai_assistant.py"), encoding="utf-8").read()
    assert "privileged" not in src
