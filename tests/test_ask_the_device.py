"""Ask the device (C547; board A, signed off 2026-10-08; NSOT_READS.md section 3).

The device page's tab on test_device_v2's lab (r3, with r2's real config as its golden). The
device session is faked at the connection seam (`connection.with_temp_connection`), answering
from real captures; the reads engine, its hold, masking, record and job, the routes and the
templates all run for real.
"""

import html as html_mod
import os
import re

import pytest

from tests.test_device_v2 import lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")


def _text(*parts):
    with open(os.path.join(FIX, *parts), encoding="utf-8") as fh:
        return fh.read()


class Device:
    """r3's session: answers by command, every command recorded."""

    def __init__(self):
        self.answers = {"show running-config": _text("configs", "fleet", "r2.cfg"),
                        "show ip interface": _text("operational", "r3__show_ip_interface.txt")}
        self.sent = []

    def __call__(self, dev, fn):
        return fn(self)

    def answer(self, command):
        self.sent.append(command)
        return self.answers.get(command, f"% no capture for {command}")


@pytest.fixture
def ask(lab, monkeypatch):  # noqa: F811
    device = Device()
    monkeypatch.setattr("modules.connection.with_temp_connection", device)
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, c: conn.answer(c))
    lab["device"] = device
    return lab


def _get(lab, url):  # noqa: F811
    r = lab["client"].get(url)
    return r, html_mod.unescape(r.get_data(as_text=True))


def _run(lab, command):  # noqa: F811
    """Run as the card does (htmx), wait for the job, and read the card as its announcement
    makes the page read it."""
    from modules.nsot import capture_job
    r = lab["client"].post("/v2/device/r3/ask", data={"list": "Lab", "command": command},
                           headers={"HX-Request": "true"})
    body = r.get_data(as_text=True)
    assert r.status_code == 200, body[:300]
    job = re.search(r"job=([0-9a-f]{32})", body)
    if job:
        assert capture_job.wait(job.group(1), 30)
        return _get(lab, f"/v2/device/r3/ask?job={job.group(1)}&command={command}")[1], body
    return html_mod.unescape(body), body


class TestTheTab:
    def test_it_is_built_and_drawn_under_the_strict_policy(self, ask):
        r, html = _get(ask, "/v2/device/r3?tab=ask")
        assert r.status_code == 200 and "'unsafe-inline'" not in r.headers["Content-Security-Policy"]
        assert 'id="ask"' in html and "Ask r3" in html
        assert "show ip interface brief" in html and "None yet." in html
        assert "Nothing here changes r3" in html
        # C588: the box is named as the policy is (Tier 1 holds send log, which writes a line).
        assert '<label class="ask-label" for="ask-command">A read or diagnostic command ' \
               '(Tier 1)</label>' in html

    def test_a_picked_command_is_filled_and_checked(self, ask):
        _r, html = _get(ask, "/v2/device/r3/ask?command=show ip route")
        assert 'value="show ip route"' in html and "read-only" in html
        assert re.search(r'<button type="submit" class="btn btn-primary" data-op="show-commands">Run',
                         html)


class TestCheckedAsTyped:
    @pytest.mark.parametrize("command, words", [
        ("reload", "Refused:"), ("write erase", "Refused:"),
        ("show running-config | redirect flash:x", "redirect"),
    ])
    def test_a_write_says_why_and_run_stays_off(self, ask, command, words):
        _r, html = _get(ask, f"/v2/device/r3/ask/check?command={command}")
        assert words in html and ("Nothing will be sent" in html or "Nothing was sent" in html)
        assert re.search(r'<button[^>]*data-op="show-commands" disabled', html), html
        assert ask["device"].sent == []

    def test_a_heavy_read_says_what_it_costs(self, ask):
        _r, html = _get(ask, "/v2/device/r3/ask/check?command=sh tech")
        assert "runs for minutes and loads the device's CPU" in html
        assert not re.search(r'data-op="show-commands" disabled', html)

    def test_a_read_says_read_only(self, ask):
        _r, html = _get(ask, "/v2/device/r3/ask/check?command=show ip route")
        assert "read-only" in html and not re.search(r'data-op="show-commands" disabled', html)


class TestRun:
    def test_the_answer_in_place_masked_and_recorded(self, ask):
        html, started = _run(ask, "show running-config")
        assert 'hx-trigger="nmas:reads from:body"' in started and 'aria-busy="true"' in started
        assert "username admin privilege 15" in html                 # the answer, in place
        assert "password 0 admin" not in html and "community public" not in html   # masked
        assert ask["device"].sent == ["show running-config"]
        assert "Recent reads on r3 (1)" in html

    def test_a_write_is_refused_in_place_and_nothing_is_sent(self, ask):
        html, _ = _run(ask, "reload")
        assert "Not run:" in html and "Nothing was sent to r3" in html
        assert ask["device"].sent == []
        from modules.nsot import reads
        (r,) = reads.runs("Lab")["runs"]
        assert r["state"] == "refused" and r["commands"] == ["reload"]

    def test_compare_with_the_last_answer(self, ask):
        _run(ask, "show ip interface")
        old = ask["device"].answers["show ip interface"]
        ask["device"].answers["show ip interface"] = old.replace(
            "GigabitEthernet1 is up, line protocol is up",
            "GigabitEthernet1 is administratively down, line protocol is down", 1)
        html, _ = _run(ask, "show ip interface")
        assert "Compare with the last answer" in html
        from modules.nsot import reads
        newest = reads.runs("Lab")["runs"][0]["id"]
        _r, cmp = _get(ask, f"/v2/device/r3/ask?run={newest}&compare=show ip interface")
        assert "- GigabitEthernet1 is up, line protocol is up" in cmp
        assert "+ GigabitEthernet1 is administratively down, line protocol is down" in cmp

    def test_a_held_device_is_not_read_and_says_who(self, ask):
        from modules.nsot import device_ops
        with device_ops.hold("Lab", "r3", "deploy", "other@example.invalid"):
            html, _ = _run(ask, "show ip interface")
        assert "Not read:" in html and "r3 is being deployed to by other@example.invalid" in html
        assert ask["device"].sent == []

    def test_without_script_the_post_opens_the_page_at_its_card(self, ask):
        r = ask["client"].post("/v2/device/r3/ask", data={"list": "Lab",
                                                          "command": "show ip interface"})
        assert r.status_code == 302 and "tab=ask" in r.headers["Location"]
        from modules.nsot import capture_job
        job = re.search(r"job=([0-9a-f]{32})", r.headers["Location"]).group(1)
        assert capture_job.wait(job, 30)          # its record is written inside this test's store

    def test_an_unknown_job_says_so(self, ask):
        _r, html = _get(ask, "/v2/device/r3/ask?job=" + "0" * 32)
        assert "This server has no record of that run" in html
