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

    def test_only_the_differences_against_the_reference_chosen(self, sc):
        """C577: no default reference; the differences are against the device a person chose."""
        _r, target = _run(sc, ["show ip interface"])
        _r, html = _get(sc, target + "&show=differences")
        assert "Choose who to compare against first" in html and 'class="op-add"' not in html
        _r, html = _get(sc, target + "&show=differences&against=r3")
        assert "against r3, your choice" in html
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


#: r1's real `show ip ospf neighbor` (tests/fixtures/operational), and the same answer with only
#: its Dead Time column edited: what two reads seconds apart look like (C580).
OSPF = _cap("r1__show_ip_ospf_neighbor.txt")
OSPF_LATER = (OSPF.replace("00:00:36", "00:00:31").replace("00:00:35", "00:00:30")
              .replace("00:00:32", "00:00:37"))


@pytest.fixture
def c2(sc):
    sc["fleet"].answers["r3"]["show ip ospf neighbor"] = OSPF
    sc["fleet"].answers["r9"]["show ip ospf neighbor"] = OSPF_LATER
    sc["fleet"].answers["r3"]["show ipv6 ospf neighbor"] = _cap("r3__show_ipv6_ospf_neighbor.txt")
    sc["fleet"].answers["r9"]["show ipv6 ospf neighbor"] = ""
    return sc


def _groups_drawn(html):
    return re.findall(r'<summary><span class="badge badge-([a-z]+)">([^<]+)</span>', html)


class TestTheResultRevised:
    """Board C2 (C577 to C580), approved 2026-10-08."""

    def test_nobody_is_the_reference_until_chosen(self, c2):
        """C577: every device got "Compare with r1" because r1 was the first group."""
        _r, target = _run(c2, ["show ip interface"])
        _r, html = _get(c2, target)
        assert re.search(r'<option value="" selected>Nobody \(no reference\)</option>', html)
        assert "Compare r3 with" in html and "Compare r9 with" in html, "each group picks its pair"
        assert not re.search(r"Compare r\d with r\d<", html), "no pairing made for the person"
        assert "your choice" not in html and "the reference" not in html
        assert "differs:" not in html, "no group is described against a reference nobody chose"
        assert re.search(r'<option value="differences"[^>]*disabled>Only the differences '
                         r'\(choose who to compare against first\)', html)
        _r, html = _get(c2, target + "&against=r3")
        assert "your choice" in html and "differs:" in html, "the control: a chosen reference"

    def test_the_most_common_answer_is_offered_only_when_shared(self, c2):
        _r, target = _run(c2, ["show ip interface"])
        _r, html = _get(c2, target)
        assert "The most common answer</option>" not in html
        assert "no answer is shared by two devices" in html
        _r, target = _run(c2, ["show clock"])
        _r, html = _get(c2, target)
        assert "The most common answer</option>" in html

    def test_groups_are_neutral_without_an_expectation(self, c2):
        """C578: green for one group and amber for the others read as right and wrong."""
        _r, target = _run(c2, ["show ip interface", "show clock"])
        _r, html = _get(c2, target)
        drawn = _groups_drawn(html)
        assert len(drawn) >= 3, drawn
        assert {kind for kind, _t in drawn} == {"muted"}, drawn

    def test_an_empty_answer_says_so(self, c2):
        """C579: r6's empty answer was a blank box."""
        _r, target = _run(c2, ["show ipv6 ospf neighbor"])
        _r, html = _get(c2, target)
        assert "no output (empty answer)" in html and "No output (empty answer). r9 answered" in html
        assert "(1 empty)" in html
        assert '<pre class="ask-pre"></pre>' not in html

    def test_ticked_columns_group_again_recorded_with_the_run(self, c2):
        """C580: Dead Time ticks every second, so every device stood alone."""
        from modules.nsot import reads
        _r, target = _run(c2, ["show ip ospf neighbor"])
        _r, html = _get(c2, target)
        names = re.findall(r'name="column" value="([^"]+)"', html)
        assert names == ["Neighbor ID", "Pri", "State", "Dead Time", "Address", "Interface"]
        assert re.search(r"<strong>2</strong>: every device's answer is its own", html)
        run_id = re.search(r"/run/([^?/]+)", target).group(1)
        r = c2["client"].post(f"/v2/show-commands/run/{run_id}/ignore?list=Lab",
                              data={"command": "show ip ospf neighbor", "column": ["Dead Time"]},
                              headers={"HX-Request": "true"})
        html = html_mod.unescape(r.get_data(as_text=True))
        assert r.status_code == 200 and "2 alike" in html, html[:400]
        assert "Ignored when grouping: <span class=\"mono\">Dead Time</span>, by" in html
        assert "········" in html, "the ignored column is drawn as dots"
        record = reads.get("Lab", run_id)
        assert record["ignored"]["show ip ospf neighbor"]["columns"] == ["Dead Time"]
        assert record["ignored"]["show ip ospf neighbor"]["by"]
        assert c2["fleet"].sent.count(("r3", "show ip ospf neighbor")) == 1, "no device asked again"

    def test_a_column_the_header_does_not_name_is_refused(self, c2):
        from modules.nsot import reads
        _r, target = _run(c2, ["show ip ospf neighbor"])
        run_id = re.search(r"/run/([^?/]+)", target).group(1)
        r = c2["client"].post(f"/v2/show-commands/run/{run_id}/ignore?list=Lab",
                              data={"command": "show ip ospf neighbor", "column": ["Uptime"]})
        html = html_mod.unescape(r.get_data(as_text=True))
        assert "Not recorded:" in html and "Uptime is not a column" in html
        assert "Dead Time" in html and not reads.get("Lab", run_id).get("ignored")


def _loki_line(host, tok):
    """r1's real `send log` line as Loki received it (tests/fixtures/loki/userlog_r1.json,
    C587), as *host*'s, carrying the test's token."""
    import json
    with open(os.path.join(ROOT, "tests", "fixtures", "loki", "userlog_r1.json"),
              encoding="utf-8") as fh:
        line = json.load(fh)["line"]
    return (line.replace(" r1 3604: r1: ", f" {host} 3604: {host}: ")
            .replace("MERCURY-LOGTEST manual-check", tok))


@pytest.fixture
def lp(sc, monkeypatch):
    """Board F: Loki configured, r3's line arriving and r9's never, the window shortened."""
    import time as _time

    from modules.nsot import logging_path as LP
    monkeypatch.setattr(LP, "loki_configured", lambda: True)
    monkeypatch.setattr(LP, "WAIT_SECONDS", 1)
    monkeypatch.setattr(LP, "POLL_SECONDS", 0.1)
    monkeypatch.setattr(LP, "_ask", lambda s, e, tok, limit: (
        [(int(_time.time() * 1e9), _loki_line("r3", tok))], ""))
    monkeypatch.setattr(LP, "last_lines", lambda hosts, **kw: {h: "" for h in hosts})
    # The lab's r3 golden is an old capture trapping at critical (C587 would hold it back), and
    # these tests are about the drawing: no golden, so IOS's default, informational.
    # test_the_line_goes_at_the_level_the_goldens_forward gives them r1's real trap.
    monkeypatch.setattr(LP, "_golden", lambda list_name, host: "")

    def answering(self, dev, fn):
        host = dev["hostname"]

        class Conn:
            def answer(_self, command):
                self.sent.append((host, command))
                if command.startswith("send log "):
                    return ""
                return self.answers[host].get(command, f"% no capture for {command}")
        return fn(Conn())

    monkeypatch.setattr(sc["fleet"].__class__, "__call__", answering)
    return sc


def _test(lab, **fields):  # noqa: F811
    from modules.nsot import capture_job
    data = {"list": "Lab", "command": [""], **fields, "fingerprint": _fingerprint(lab)}
    r = lab["client"].post("/v2/show-commands/logging-path", data=data,
                           headers={"HX-Request": "true"})
    target = r.headers.get("HX-Redirect", "")
    job = re.search(r"job=([0-9a-f]{32})", target)
    if job:
        assert capture_job.wait(job.group(1), 30)
    return r, target


class TestTheLoggingPath:
    """Board F, approved 2026-10-08: from Show commands' card, a line sent, Loki watched."""

    def test_the_button_is_off_and_says_why_without_loki(self, sc):
        _r, html = _get(sc, "/v2/show-commands?list=Lab")
        assert re.search(r'<button type="submit" class="btn" data-op="logging-path"[^>]* disabled '
                         r'title="Loki is not configured[^"]*">Test the logging path on 2 '
                         r'devices</button>', html), html[:200]

    def test_on_with_loki_on_the_card_s_devices(self, lp):
        _r, html = _get(lp, "/v2/show-commands?list=Lab")
        assert re.search(r'data-op="logging-path"[^>]*>Test the logging path on 2 devices</button>',
                         html)
        assert not re.search(r'data-op="logging-path"[^>]* disabled', html)

    def test_sent_watched_and_drawn_act_first(self, lp):
        from modules.nsot import logging_path as LP
        from modules.nsot import reads
        _r, target = _test(lp)
        assert target.startswith("/v2/show-commands/run/"), target
        sent = sorted(c for _h, c in lp["fleet"].sent)
        assert len(sent) == 2 and all(c.startswith("send log 6 MERCURY-LOGTEST ") for c in sent)
        _r, html = _get(lp, target)
        assert "Logging path on 2 devices" in html
        assert html.index("1 not received within 1 s") < html.index("1 received"), \
            "what to act on first"
        assert "r9</strong>: not received within 1 s" in html
        assert "Open r9's Logs" in html and "Test r9 again" in html
        assert "Loki holds no line from r9 in the last 24 hours" in html
        assert ("r9 forwards informational (6) and above (IOS's default: it has no committed "
                "golden); this line was level 6, so its own filter passed it.") in html, (
            "C587: the device's own filter is said first")
        run_id = re.search(r"/run/([^?/]+)", target).group(1)
        lp_rec = reads.get("Lab", run_id)["logging_path"]
        assert lp_rec["counts"] == {"received": 1, "not received": 1}
        assert lp_rec["token"] == LP.token(run_id)

    def test_the_history_row_says_what_to_act_on(self, lp):
        _test(lp)
        from modules.history_sources import show_commands
        from modules.nsot import listref
        got = show_commands({"ref": listref.resolve("Lab"), "device": "", "limit": 50,
                             "since": None, "members": None})
        (e,) = got["events"]
        assert e["what"] == "Logging path on 2 devices"
        assert e["outcome"] == "1 not received, 1 received"

    def test_the_line_goes_at_the_level_the_goldens_forward(self, lp, monkeypatch):
        """C587, through the page: goldens carrying r1's real `logging trap notifications`
        make the line level 5, and the result says so."""
        from tests.test_logging_path import NOTIFICATIONS
        from modules.nsot import logging_path as LP
        monkeypatch.setattr(LP, "_golden", lambda list_name, host: NOTIFICATIONS)
        _r, target = _test(lp)
        sent = sorted(c for _h, c in lp["fleet"].sent)
        assert len(sent) == 2 and all(c.startswith("send log 5 MERCURY-LOGTEST ") for c in sent)
        _r, html = _get(lp, target)
        assert "send log 5 MERCURY-LOGTEST" in html
        assert "r9 forwards notifications (5) and above (its golden); this line was level 5" in html

    def test_again_on_one_device_and_never_a_stranger(self, lp):
        _r, target = _test(lp)
        run_id = re.search(r"/run/([^?/]+)", target).group(1)
        lp["fleet"].sent.clear()
        r = lp["client"].post(f"/v2/show-commands/logging-path?list=Lab&again={run_id}&host=r9",
                              headers={"HX-Request": "true"})
        from modules.nsot import capture_job
        capture_job.wait(re.search(r"job=([0-9a-f]{32})", r.headers["HX-Redirect"]).group(1), 30)
        assert [h for h, _c in lp["fleet"].sent] == ["r9"]
        lp["fleet"].sent.clear()
        r = lp["client"].post(f"/v2/show-commands/logging-path?list=Lab&again={run_id}&host=r1",
                              headers={"HX-Request": "true"})
        html = html_mod.unescape(r.get_data(as_text=True))
        assert "Not run:" in html and "r1 was not tested in" in html and lp["fleet"].sent == []


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


@pytest.mark.parametrize("width", [1366, 390])
@pytest.mark.parametrize("which", ["c2", "f"])
def test_boards_c2_and_f_in_a_real_browser_stay_inside_their_cards(lp, width, which):
    """Board G: C2 (columns to tick, an empty answer, groups open) and F (a logging-path
    result) at desktop and phone width: every cell ends inside its card, no sideways scroll."""
    from tests import browser
    from tests.test_v2_layout_in_a_browser import CELLS_INSIDE_JS
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    if which == "c2":
        lp["fleet"].answers["r3"]["show ip ospf neighbor"] = OSPF
        lp["fleet"].answers["r9"]["show ip ospf neighbor"] = ""
        _r, target = _run(lp, ["show ip ospf neighbor", "show ip interface"])
    else:
        _r, target = _test(lp)
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": width, "height": 1000})
            b.go(srv.url(target))
            b.wait_for("return !!window.Alpine && !document.querySelector('.htmx-request')", 15)
            b.js("document.querySelectorAll('details').forEach(function(d){d.open=true}); return 1")
            got, n = b.js(CELLS_INSIDE_JS)
            assert not got, "\n".join(got)
            assert n >= 3, n
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
        run = "document.querySelector('#sc-form button[type=submit][data-op=show-commands]')"
        assert page.js(f"return {run}.disabled") is True, "no command yet: Run is off"
        page.click("input[name=command]")
        page.type("input[name=command]", "show clock")
        page.wait_for(f"return !{run}.disabled && " + SETTLED, 10)
        page.type("input[name=command]", " | redirect flash:x")
        page.wait_for(f"return {run}.disabled && " + SETTLED, 10)

    def test_a_level_2_line_brings_the_reason_field_and_typing_it_keeps_it(self, page):
        """Board C582: the field appears as the line is typed; typing the reason, a character
        at a time, keeps the focus in it, and Run comes on at three words."""
        import time
        run = "document.querySelector('#sc-form button[type=submit][data-op=show-commands]')"
        page.click("input[name=command]")
        page.type("input[name=command]", "send log 2 MERCURY TEST alert rule check")
        page.wait_for("return !!document.querySelector('#sc-reason-in') && " + SETTLED, 10)
        assert page.js(f"return {run}.disabled") is True
        page.click("#sc-reason-in")
        for ch in "prove the rule fires":
            page.type("#sc-reason-in", ch)
            time.sleep(0.05)
        time.sleep(0.5)                              # past the field's 300 ms pause
        page.wait_for("return " + SETTLED, 10)
        assert page.js("return document.activeElement.id") == "sc-reason-in"
        assert page.js("return document.querySelector('#sc-reason-in').value") \
            == "prove the rule fires"
        page.wait_for(f"return !{run}.disabled", 10)
        assert "allowed, with your reason" in page.js(
            "return document.querySelector('#sc-check-0').textContent")


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


URGENT = "send log 2 MERCURY TEST alert rule check"
REASON = "prove the critical alert rule fires after the Grafana change"


class TestAReasonForLevelsZeroToThree:
    """Board C582 (approved 2026-10-08): a send log at 0 to 3 needs a stated reason, three
    words or more, recorded with the run; the field appears under the commands, one per run."""

    def test_typed_without_a_reason_it_asks_for_one_and_run_is_off(self, sc):
        _r, html = _get(sc, f"/v2/show-commands/check?list=Lab&i=0&command={URGENT}")
        assert ">needs a reason</span>" in html and "refused" not in html
        assert 'id="sc-reason" hx-swap-oob="true"' in html, "the field follows the command"
        assert "Why send at level 2? Recorded with the run, at least three words" in html
        assert "Level 2 is <strong>critical (2)</strong>" in html
        assert "The line says TEST, which it must." in html
        assert re.search(r'data-op="show-commands" disabled', html), "Run stays off"

    def test_typing_the_reason_redraws_the_verdicts_and_run_never_the_field(self, sc):
        _r, html = _get(sc, f"/v2/show-commands/reason?list=Lab&command={URGENT}"
                            f"&reason={REASON}")
        assert 'id="sc-check-0" aria-live="polite" hx-swap-oob="true"' in html
        assert ">allowed, with your reason</span>" in html
        assert 'id="sc-reason"' not in html, "the field being typed in is never replaced (C573)"
        assert not re.search(r'data-op="show-commands" disabled', html), "Run is on"

    def test_two_words_are_not_a_reason(self, sc):
        _r, html = _get(sc, f"/v2/show-commands/reason?list=Lab&command={URGENT}"
                            "&reason=just testing")
        assert ">needs a reason</span>" in html
        assert re.search(r'data-op="show-commands" disabled', html)

    def test_a_line_without_test_is_said_not_a_test(self, sc):
        _r, html = _get(sc, "/v2/show-commands/reason?list=Lab&command=send log 2 MERCURY "
                            f"alert rule check&reason={REASON}")
        assert ">not a test: " in html
        assert "send log at level 2 must mark its line as a test" in html

    def test_levels_4_to_7_never_show_the_field(self, sc):
        _r, html = _get(sc, "/v2/show-commands/check?list=Lab&i=0&command=send log 5 hello")
        assert "Why send at level" not in html and ">needs a reason<" not in html

    def test_the_run_sends_with_the_reason_and_records_it(self, sc):
        _r, target = _run(sc, [URGENT], reason=REASON)
        assert sorted(sc["fleet"].sent) == [("r3", URGENT), ("r9", URGENT)]
        _r, html = _get(sc, target)
        assert f"Level critical (2), allowed by the reason. Why: {REASON}." in html
        from modules.history_sources import show_commands
        from modules.nsot import listref
        got = show_commands({"ref": listref.resolve("Lab"), "device": "", "limit": 50,
                             "since": None, "members": None})
        assert got["events"][0]["detail"] == f"Why: {REASON}"

    def test_without_a_reason_the_run_is_refused_and_asks_no_device(self, sc):
        _r, target = _run(sc, [URGENT], reason="because")
        _r, html = _get(sc, target)
        assert "Not run:" in html and "needs a stated reason of three words" in html
        assert sc["fleet"].sent == []

    def test_ask_the_device_takes_the_same_reason(self, sc):
        _r, html = _get(sc, f"/v2/device/r3/ask/check?command={URGENT}")
        assert "needs a reason of three words or more, below; Run stays off" in html
        assert 'id="ask-reason" hx-swap-oob="true"' in html
        assert "Why send at level 2? Recorded with the read, at least three words" in html
        _r, html = _get(sc, f"/v2/device/r3/ask/check?command={URGENT}&reason={REASON}"
                            "&part=run")
        assert 'id="ask-reason"' not in html, "its own typing never redraws it"
        assert "disabled" not in html.split('id="ask-check"', 1)[1].split("</button>", 1)[0]
        from modules.nsot import capture_job
        r = sc["client"].post("/v2/device/r3/ask", data={"list": "Lab", "command": URGENT,
                                                          "reason": REASON},
                              headers={"HX-Request": "true"})
        # The card draws the job in whatever state it is in (routes/reads_v2.ask_run): still
        # running, it carries the job's link; already answered (the stand-in fleet answers at
        # once), it draws the answer and the reason it was recorded with (C611: this asserted
        # the link only, and failed whenever the job won the race).
        body = r.get_data(as_text=True)
        job = re.search(r"job=([0-9a-f]{32})", body)
        if job:
            assert capture_job.wait(job.group(1), 30)
        else:
            assert "answered" in body and "Why: prove the critical alert rule" in body, body[-800:]
        assert sc["fleet"].sent == [("r3", URGENT)]
