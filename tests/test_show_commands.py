"""Show commands (C548; boards B to E, signed off 2026-10-08; NSOT_READS.md section 4).

OBSERVE › Show commands on test_device_v2's lab (r3, IOS-XE; r9, IOS), the device session faked
at the connection seam answering from real captures, so the engine, the job, the record, the
routes, the saved sets' commits and History all run for real.
"""

import html as html_mod
import os
import re

import pytest

from tests.test_device_v2 import lab  # noqa: F401 (the fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures", "operational")


def _cap(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


class Fleet:
    """Each device's session: r3 and r9 answer `show ip interface` from their own captures
    (r3's and s3's), and `show clock` alike."""

    def __init__(self):
        self.answers = {"r3": {"show ip interface": _cap("r3__show_ip_interface.txt"),
                               "show clock": "*03:20:01.123 UTC Thu Oct 8 2026"},
                        "r9": {"show ip interface": _cap("s3__show_ip_interface.txt"),
                               "show clock": "*03:20:01.123 UTC Thu Oct 8 2026"}}
        self.sent = []

    def __call__(self, dev, fn):
        host = dev["hostname"]

        class Conn:
            def answer(_self, command):
                self.sent.append((host, command))
                return self.answers[host].get(command, f"% no capture for {command}")
        return fn(Conn())


@pytest.fixture
def sc(lab, monkeypatch):  # noqa: F811
    fleet = Fleet()
    monkeypatch.setattr("modules.connection.with_temp_connection", fleet)
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, c: conn.answer(c))
    lab["fleet"] = fleet
    return lab


def _get(lab, url):  # noqa: F811
    r = lab["client"].get(url)
    return r, html_mod.unescape(r.get_data(as_text=True))


def _fingerprint(lab, query=""):  # noqa: F811
    _r, html = _get(lab, "/v2/show-commands?list=Lab" + query)
    return re.search(r'name="fingerprint" value="([0-9a-f]+)"', html).group(1)


def _run(lab, commands, fingerprint=None, **fields):  # noqa: F811
    from modules.nsot import capture_job
    data = {"list": "Lab", "command": commands, **fields,
            "fingerprint": fingerprint or _fingerprint(lab)}
    r = lab["client"].post("/v2/show-commands/run", data=data, headers={"HX-Request": "true"})
    target = r.headers.get("HX-Redirect", "")
    job = re.search(r"job=([0-9a-f]{32})", target)
    if job:
        assert capture_job.wait(job.group(1), 30)
    return r, target


class TestThePick:
    def test_the_page_is_under_the_strict_policy_with_the_sidebar_item(self, sc):
        r, html = _get(sc, "/v2/show-commands?list=Lab")
        assert r.status_code == 200 and "'unsafe-inline'" not in r.headers["Content-Security-Policy"]
        assert re.search(r'class="nav-item active"[^>]*href="/v2/show-commands"[^>]*>', html) \
            or 'aria-current="page"' in html
        assert "2 devices" in html and ">r3<" in html and ">r9<" in html
        assert "Nothing here changes a device" in html

    def test_a_filter_narrows_the_devices_and_the_fingerprint_moves(self, sc):
        _r, html = _get(sc, "/v2/show-commands/pick?list=Lab&q=r3")
        assert "1 device" in html and ">r3<" in html and ">r9<" not in html
        assert _fingerprint(sc) != _fingerprint(sc, "&q=r3")

    def test_add_and_remove_a_command_row(self, sc):
        _r, html = _get(sc, "/v2/show-commands/pick?list=Lab&command=show+clock&add=1")
        assert html.count('name="command"') == 2
        _r, html = _get(sc, "/v2/show-commands/pick?list=Lab&command=show+clock&command=x&remove=1")
        assert html.count('name="command"') == 1 and 'value="show clock"' in html

    def test_a_write_typed_says_why(self, sc):
        _r, html = _get(sc, "/v2/show-commands/check?command=reload&i=0")
        assert "refused: " in html and "Tier 3" in html and 'id="sc-check-0"' in html


class TestARun:
    def test_the_summary_leads_and_alike_answers_group(self, sc):
        _r, target = _run(sc, ["show clock", "show ip interface"])
        assert target.startswith("/v2/show-commands/run/")
        _r, html = _get(sc, target)
        assert "2 commands on 2 devices" in html
        rows = re.findall(r"<tr><td class=\"mono\">(show [a-z ]+)</td><td>(\d+)</td><td><strong>(\d+)",
                          html)
        assert ("show clock", "2", "1") in rows and ("show ip interface", "2", "2") in rows
        assert "2 alike" in html and sorted(sc["fleet"].sent) == sorted(
            [("r3", "show clock"), ("r3", "show ip interface"),
             ("r9", "show clock"), ("r9", "show ip interface")])

    def test_only_the_differences_against_the_largest_group(self, sc):
        _r, target = _run(sc, ["show ip interface"])
        _r, html = _get(sc, target + "&show=differences")
        assert "against r3" in html or "against r9" in html
        assert 'class="op-add"' in html and 'class="op-del"' in html

    def test_two_devices_side_by_side(self, sc):
        _r, target = _run(sc, ["show ip interface"])
        _r, html = _get(sc, target + "&left=r3&right=r9&command=show ip interface")
        assert "r3 and r9, side by side" in html and 'class="sc-only"' in html

    def test_a_write_refuses_the_run_and_asks_no_device(self, sc):
        _r, target = _run(sc, ["show clock", "write erase"])
        _r, html = _get(sc, target)
        assert "Not run:" in html and "No device was asked" in html
        assert sc["fleet"].sent == []

    def test_show_tech_is_refused_across_devices(self, sc):
        _r, target = _run(sc, ["show tech-support"])
        _r, html = _get(sc, target)
        assert "asked of one device, on its page" in html and sc["fleet"].sent == []

    def test_a_moved_device_list_refuses_naming_both(self, sc):
        r, _t = _run(sc, ["show clock"], fingerprint="0" * 16)
        html = html_mod.unescape(r.get_data(as_text=True))
        assert "Not run: the devices these filters match changed" in html
        assert "0000000000000000 then" in html and sc["fleet"].sent == []

    def test_the_run_is_a_history_row(self, sc):
        _run(sc, ["show clock"])
        from modules.history_sources import show_commands
        from modules.nsot import listref
        got = show_commands({"ref": listref.resolve("Lab"), "device": "", "limit": 50,
                             "since": None, "members": None})
        (e,) = got["events"]
        assert e["kind"] == "show_commands" and e["what"] == "Show commands: show clock"
        assert e["devices"] == ["r3", "r9"] and e["outcome"].startswith("2 answered")


@pytest.mark.parametrize("width", [1366, 390])
def test_a_finished_run_in_a_real_browser_stays_inside_its_cards(sc, width):
    """Boards C and E: a finished run's page, every group opened, at desktop and phone width:
    every cell and answer ends inside its card (or scrolls inside its own box), and the page
    itself never scrolls sideways."""
    from tests import browser
    from tests.test_v2_layout_in_a_browser import CELLS_INSIDE_JS
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    _r, target = _run(sc, ["show clock", "show ip interface"])
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": width, "height": 1000})
            b.go(srv.url(target + "&left=r3&right=r9&command=show%20ip%20interface"))
            b.wait_for("return !!window.Alpine && !document.querySelector('.htmx-request')", 15)
            b.js("document.querySelectorAll('details').forEach(function(d){d.open=true}); return 1")
            got, n = b.js(CELLS_INSIDE_JS)
            assert not got, "\n".join(got)
            assert n >= 5, n
            wide = b.js("return document.documentElement.scrollWidth - window.innerWidth")
            assert wide <= 1, f"the page scrolls sideways by {wide}px at {width}px"
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


@pytest.fixture
def page(sc):
    """The pick page in a real browser, its parts loaded."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1366, "height": 1000})
            b.go(srv.url("/v2/show-commands?list=Lab"))
            b.wait_for("return !!window.Alpine && !document.querySelector('.htmx-request')", 15)
            yield b
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


SETTLED = "!document.querySelector('.htmx-request, .htmx-settling, .htmx-swapping')"


class TestTypedInARealBrowser:
    """The operator's walk, 2026-10-08: typing `*` in the name filter lost the field (a paste
    worked), and Run stayed off with a valid command typed until Add a command was pressed."""

    def test_typing_a_pattern_keeps_the_field_and_filters(self, page):
        page.click("input[name=q]")
        for ch in "r9*":                             # r9 alone; the operator typed `r*`
            page.type("input[name=q]", ch)
            page.wait_for("return " + SETTLED, 10)
            import time
            time.sleep(0.6)                          # past the filter's 400 ms pause
            page.wait_for("return " + SETTLED, 10)
            focused = page.js("var a = document.activeElement; return a && a.name || a.tagName")
            assert focused == "q", f"after typing {ch!r} the focus is on {focused!r}"
        assert page.js("return document.querySelector('input[name=q]').value") == "r9*"
        assert "1 device" in page.js("return document.querySelector('.sc-count').textContent")

    def test_a_typed_valid_command_enables_run_at_once(self, page):
        run = "document.querySelector('#sc-form button[type=submit][data-op]')"
        assert page.js(f"return {run}.disabled") is True, "no command yet: Run is off"
        page.click("input[name=command]")
        page.type("input[name=command]", "show clock")
        page.wait_for(f"return !{run}.disabled && " + SETTLED, 10)
        page.type("input[name=command]", " | redirect flash:x")
        page.wait_for(f"return {run}.disabled && " + SETTLED, 10)


class TestSavedSets:
    def test_a_set_is_committed_and_offered(self, sc):
        r = sc["client"].post("/v2/show-commands/sets", data={
            "list": "Lab", "command": ["show clock", "show ip interface"],
            "set_name": "Time and interfaces", "set_description": "the overnight check"})
        html = html_mod.unescape(r.get_data(as_text=True))
        assert "Saved as 'Time and interfaces', committed" in html
        import subprocess
        log = subprocess.run(["git", "-C", sc["repo"], "log", "-1", "--format=%s%n%b"],
                             capture_output=True, text=True).stdout
        assert log.startswith("command set: Time and interfaces") and "Actor:" in log
        _r, html = _get(sc, "/v2/show-commands?list=Lab")
        assert "Time and interfaces" in html and "show clock; show ip interface" in html
        _r, used = _get(sc, "/v2/show-commands?list=Lab&set=time-and-interfaces")
        assert 'value="show clock"' in used and 'value="show ip interface"' in used
        # Ask the device offers it too, opening Show commands on that one device (board A).
        _r, ask = _get(sc, "/v2/device/r3/ask")
        assert "Time and interfaces (2)" in ask
        assert "/v2/show-commands?set=time-and-interfaces&amp;q=r3" in ask.replace("&", "&amp;") \
            or "/v2/show-commands?set=time-and-interfaces&q=r3" in ask

    def test_a_write_or_a_taken_name_is_refused(self, sc):
        r = sc["client"].post("/v2/show-commands/sets", data={
            "list": "Lab", "command": ["reload"], "set_name": "Bad"})
        assert "Not saved:" in html_mod.unescape(r.get_data(as_text=True))
        for _ in range(2):
            r = sc["client"].post("/v2/show-commands/sets", data={
                "list": "Lab", "command": ["show clock"], "set_name": "Clock"})
        assert "already has a set named 'Clock'" in html_mod.unescape(r.get_data(as_text=True))
