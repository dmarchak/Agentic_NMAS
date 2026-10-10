"""The device page's Capture on v2 (7.3; the mockup signed off 2026-10-02, the mockups'
"Device actions on v2" page).

On test_capture's lab: r2's REAL configuration with committed intent parsed from it, and the
host's exact break (`load-interval 30` on Gi2, OSPFv3 off). Only the device read is replaced.
Through the real routes and templates:

- the Actions menu draws Capture as the card's request, its (i) beside it; the rest open on
  today's page;
- the card starts its own read (a POST on load), then waits for the job's announcement, so
  the card that waits is the one that asked (the catch-up keys on its id);
- the preview draws what it records, what it will not do, the difference from the golden
  now and against intent, the operands (the golden now, this read, committed intent), the
  checks with the verified person, and the confirm bound to this read's hash, busy on itself;
- a device that equals its golden offers no confirm and says nothing would be recorded; a
  device another operation holds fails its check by name and offers no confirm;
- the confirm records one commit, `Source: capture`, as the verified person, through the
  same apply as `/golden/capture/apply`, and draws the result in place: the commit, who, when
  (the read timings on hover), what is still true against intent, and what next;
- a device that moved before the confirm is refused naming both captures, nothing committed;
- a write that names no list, or no read, is refused; an unknown job says so.
"""

import re
import subprocess

import pytest

from tests.test_capture import build_capture_lab
from tests.test_intent_match import _broken


@pytest.fixture
def lab(tmp_path, monkeypatch):
    cap = build_capture_lab(monkeypatch, tmp_path)
    device = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
              "platform": "cisco_iosxe", "username": "nmas"}
    # The device page finds r2 in the list's inventory, as it does on a real install.
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path: [dict(device)])
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: str(name) == "Lab")
    return cap


def _head(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()


def _preview_card(lab):
    """The card as a person meets it: the menu's request, the card's own start, then the
    job's card once it has announced."""
    from modules.nsot import capture_job

    c = lab["client"]
    start = c.get("/v2/device/r2/capture?back=history").get_data(as_text=True)
    assert 'hx-trigger="load"' in start and 'hx-post="/v2/device/r2/capture/start?list=Lab"' in start
    vals = re.search(r"hx-vals='([^']*)'", start).group(1)
    assert '"list": "Lab"' in vals and '"back": "history"' in vals
    reading = c.post("/v2/device/r2/capture/start", data={"list": "Lab", "back": "history"})
    assert reading.status_code == 200, reading.get_data(as_text=True)[:400]
    html = reading.get_data(as_text=True)
    assert 'id="device-op"' in html and 'hx-trigger="nmas:capture_preview from:body"' in html
    job = re.search(r"/capture/job/([0-9a-f]+)", html).group(1)
    assert capture_job.wait(job, 60)
    return c.get(f"/v2/device/r2/capture/job/{job}?back=history").get_data(as_text=True)


def _confirm(lab, html, **over):
    vals = re.search(r"hx-vals='([^']*)'", html[html.index("op-confirm"):]).group(1)
    import json
    body = {**json.loads(vals), **over}
    return lab["client"].post("/v2/device/r2/capture/confirm", data=body)


class TestTheMenu:
    def test_capture_runs_here_and_the_others_open_on_today_s_page(self, lab):
        html = lab["client"].get("/v2/device/r2").get_data(as_text=True)
        menu = html[html.index('role="menu"'):html.index('class="tabs"')]
        row = menu[menu.index('data-op="capture"') - 200:menu.index('data-op="capture"') + 1500]
        assert 'hx-get="/v2/device/r2/capture?back=overview&amp;list=Lab"' in row and 'hx-target="#tab-body"' in row
        assert 'aria-label="How does capture work?"' in row
        assert "Every action runs here." in menu and "today's device page" not in menu
        labels = re.findall(r'role="menuitem"[^>]*>([^<]+)</a>', menu)
        assert labels == ["Plan a deploy…", "Capture", "Seed intent…", "Restore from…",
                          "Remove lines (Mode B)…",
                          "Rotate credential…", "Persist", "Run a privileged command…",
                          "Reload…", "Retire…"], labels

    def test_without_script_the_row_opens_the_page_with_the_card(self, lab):
        html = lab["client"].get("/v2/device/r2?op=capture").get_data(as_text=True)
        body = html[html.index('id="tab-body"'):]
        assert 'id="device-op"' in body and 'hx-post="/v2/device/r2/capture/start?list=Lab"' in body


class TestThePreview:
    def test_it_draws_every_part_the_mockup_drew(self, lab):
        lab["running"]["r2"] = _broken(lab["captured"])
        html = _preview_card(lab)
        assert "Capture r2 as its golden" in html
        assert "<span class=\"mono\">Source: capture</span>, as you" in html
        # The read timings on hover (the faked read records no connect phase).
        assert re.search(r'<time class="stamp" datetime="[^"]+" title="[^"]+ · read in [0-9.]+ s', html)
        assert "Nothing is sent to r2." in html and "No baseline is taken" in html
        assert "still departs from its committed intent" in html
        diff = html[html.index("The difference"):html.index("Operands")]
        assert '<span class="op-add">+ load-interval 30</span>' in diff
        assert "Against committed intent, r2 departs" in diff
        ops = html[html.index("Operands"):html.index("Checks")]
        assert re.search(r"Golden now</dt><dd class=\"mono\">[0-9a-f]{7,}", ops)
        assert re.search(r"This read</dt><dd class=\"mono\">capture [0-9a-f]+", ops)
        assert re.search(r"host_vars/r2.yml at [0-9a-f]{7,}", ops)
        checks = html[html.index("Checks"):html.index("op-ft")]
        assert "You are a verified person: test-person@example.invalid" in checks
        assert "badge-danger" not in checks
        assert "device read" in checks
        foot = html[html.index("op-ft"):]
        h = re.search(r"This read</dt><dd class=\"mono\">capture ([0-9a-f]+)", ops).group(1)
        assert f"Bound to capture {h}" in foot
        assert 'class="op-idle">Record r2' in foot and 'class="op-busy">Reading r2 again' in foot
        assert 'hx-disabled-elt="this"' in foot and f'"hash": "{h}"' in foot
        assert 'hx-get="/v2/device/r2/history?list=Lab"' in html, "Cancel puts back the tab it replaced"

    def test_a_device_equal_to_its_golden_offers_no_confirm(self, lab):
        html = _preview_card(lab)
        assert "None: r2's running configuration equals its golden" in html
        assert "op-confirm" not in html
        assert "Nothing to confirm: r2 matches its golden" in html

    def test_a_viewer_who_may_not_confirm_fails_the_check_and_gets_no_confirm(self, lab,
                                                                              monkeypatch):
        """The read is started by the person; the card is then drawn for a viewer the
        access proxy did not verify (a tab left open after the session ended)."""
        from modules import identity

        lab["running"]["r2"] = _broken(lab["captured"])
        real = identity.identify
        state = {"anon": False}
        monkeypatch.setattr(identity, "identify", lambda r: identity.Identity(
            peer="198.51.100.7") if state["anon"] else real(r))
        from modules.nsot import capture_job
        c = lab["client"]
        html = c.post("/v2/device/r2/capture/start", data={"list": "Lab"}).get_data(as_text=True)
        job = re.search(r"/capture/job/([0-9a-f]+)", html).group(1)
        assert capture_job.wait(job, 60)
        state["anon"] = True
        html = c.get(f"/v2/device/r2/capture/job/{job}").get_data(as_text=True)
        checks = html[html.index("Checks"):]
        assert "badge-danger" in checks and "<strong>You are a verified person</strong>" in checks
        assert "op-confirm" not in html and "Not available:" in html

    def test_a_held_device_fails_its_check_by_name(self, lab):
        from modules.nsot import device_ops

        lab["running"]["r2"] = _broken(lab["captured"])
        device_ops.acquire("Lab", "r2", "deploy", "alex@example.invalid")
        try:
            html = _preview_card(lab)
        finally:
            device_ops.release("Lab", "r2")
        checks = html[html.index("Checks"):]
        assert "badge-danger" in checks and "alex@example.invalid" in checks
        assert "op-confirm" not in html and "Not available:" in html and "Nothing is queued" in html


class TestTheConfirm:
    def test_it_records_one_commit_as_the_person_and_draws_the_result(self, lab):
        lab["running"]["r2"] = _broken(lab["captured"])
        html = _preview_card(lab)
        before = _head(lab["repo"])
        r = _confirm(lab, html)
        assert r.status_code == 200
        out = r.get_data(as_text=True)
        after = _head(lab["repo"])
        assert after != before
        msg = subprocess.run(["git", "-C", lab["repo"], "log", "-1", "--format=%B"],
                             capture_output=True, text=True).stdout
        assert "Source: capture" in msg and "Actor: test-person@example.invalid" in msg
        assert "op-card op-ok" in out and "Captured" in out and "badge-ok" in out
        assert f">{after[:10]}</a>" in out and "test-person@example.invalid (verified)" in out
        assert re.search(r'title="[^"]*read again at confirm: capture [0-9a-f]+, unchanged since '
                         r'the preview; [^"]+"', out)
        still = out[out.index("Still true"):]
        assert "r2 departs" in still and "the next deploy would send intent" in still
        assert "Edit intent…</a>" in out and "on its Intent tab's editor, which this opens" in out
        assert 'data-op="removal"' in out
        assert 'href="/v2/device/r2?tab=history&amp;list=Lab"' in out and "Open in History" in out
        assert 'hx-get="/v2/device/r2/history?list=Lab"' in out, "Close puts back the tab it replaced"

    def test_a_device_that_moved_is_refused_naming_both_reads(self, lab):
        lab["running"]["r2"] = _broken(lab["captured"])
        html = _preview_card(lab)
        confirmed = re.search(r'"hash": "([0-9a-f]+)"', html).group(1)
        before = _head(lab["repo"])
        # Moved by another valid change, as the device would be.
        lab["running"]["r2"] = _broken(lab["captured"]).replace("load-interval 30", "load-interval 60")
        out = _confirm(lab, html).get_data(as_text=True)
        assert _head(lab["repo"]) == before, "nothing committed"
        assert "op-card op-warn" in out and "Not recorded" in out
        current = re.search(r"the read at confirm is capture ([0-9a-f]+)", out).group(1)
        assert current != confirmed and f"you confirmed {confirmed}" in out
        assert "Preview it again" in out and "Nothing was committed" in out

    @pytest.mark.parametrize("body,code,words", [
        ({"hash": "abc"}, 400, "names no list"),
        ({"list": "Elsewhere", "hash": "abc"}, 400, "names no list"),
        ({"list": "Lab"}, 400, "no read to be bound to"),
    ])
    def test_a_write_naming_no_list_or_no_read_is_refused(self, lab, body, code, words):
        before = _head(lab["repo"])
        r = lab["client"].post("/v2/device/r2/capture/confirm", data=body)
        assert r.status_code == code and words in r.get_data(as_text=True)
        assert _head(lab["repo"]) == before

    def test_an_unknown_job_says_so(self, lab):
        out = lab["client"].get("/v2/device/r2/capture/job/0123abcd").get_data(as_text=True)
        assert "This server has no record of that read" in out and "Preview it again" in out


def _shrunk(text):
    """r2 with its last interface section gone: a shrink committed intent does not explain."""
    lines = text.splitlines()
    starts = [i for i, l in enumerate(lines) if l.startswith("interface ")]
    assert len(starts) >= 2, "the fixture has too few interfaces to lose one"
    i = starts[-1]
    j = next((k for k in range(i + 1, len(lines)) if not lines[k].startswith(" ")), len(lines))
    return "\n".join(lines[:i] + lines[j:]) + "\n"


class TestTheReasonForAShrink:
    """C486, cutover blocker 4: a shrink committed intent does not explain is recorded only
    with the person's reason, taken on v2's card (today's device page held the only field)."""

    def test_the_card_takes_the_reason_beside_its_confirm(self, lab):
        lab["running"]["r2"] = _shrunk(lab["captured"])
        html = _preview_card(lab)
        assert '<input id="capture-reason" name="reason"' in html
        assert 'hx-include="#capture-reason"' in html, "the confirm does not carry the reason"
        assert "not explained by committed intent" in html and "op-confirm" in html
        assert "today&#39;s device page" not in html and 'data-todays-page' not in html

    def test_without_a_reason_the_save_refuses_and_nothing_is_committed(self, lab):
        lab["running"]["r2"] = _shrunk(lab["captured"])
        html = _preview_card(lab)
        before = _head(lab["repo"])
        out = _confirm(lab, html).get_data(as_text=True)
        assert _head(lab["repo"]) == before
        assert "Not recorded" in out and "the save refused it" in out

    def test_a_reason_not_shaped_as_one_is_refused_naming_why(self, lab):
        lab["running"]["r2"] = _shrunk(lab["captured"])
        html = _preview_card(lab)
        before = _head(lab["repo"])
        r = _confirm(lab, html, reason="ok")
        out = r.get_data(as_text=True)
        assert r.status_code == 400 and _head(lab["repo"]) == before
        assert "Refused: the reason was not taken" in out and "too short to be a reason" in out

    def test_with_a_reason_it_is_recorded_on_the_commit_as_the_person_s(self, lab):
        lab["running"]["r2"] = _shrunk(lab["captured"])
        html = _preview_card(lab)
        why = "the interface was removed with its circuit last week"
        r = _confirm(lab, html, reason=why)
        out = r.get_data(as_text=True)
        assert r.status_code == 200 and "Captured" in out, out[:600]
        msg = subprocess.run(["git", "-C", lab["repo"], "log", "-1", "--format=%B"],
                             capture_output=True, text=True).stdout
        assert f"acknowledged: {why}" in msg and "Structural-Change: r2" in msg
        assert "your reason is recorded on the commit" in out and why in out


class TestWhatNextFollowsTheDirection:
    """C486: lines the device lacks are sent by a deploy or put back by a restore; lines the
    device holds and intent does not are taken off by Mode B. Edit intent fits either way."""

    def _next(self, lab, running):
        lab["running"]["r2"] = running
        html = _preview_card(lab)
        out = _confirm(lab, html, reason="the interface was removed with its circuit").get_data(
            as_text=True)
        assert "What next" in out, out[:600]
        return out[out.index("What next"):]

    def test_a_device_lacking_intent_s_lines_is_offered_deploy_and_restore(self, lab):
        nxt = self._next(lab, _shrunk(lab["captured"]))
        assert "Deploy intent…" in nxt and "Restore from…" in nxt and "Edit intent…" in nxt
        assert "Remove lines (Mode B)…" not in nxt
        assert 'href="/v2/device/r2?tab=overview&amp;op=restore&amp;list=Lab"' in nxt

    def test_a_device_holding_extra_lines_is_offered_mode_b(self, lab):
        extra = lab["captured"].replace("\ninterface ", "\nip domain lookup source-interface "
                                        "Loopback99\ninterface ", 1)
        nxt = self._next(lab, extra)
        assert "Remove lines (Mode B)…" in nxt and "Edit intent…" in nxt
        assert "Deploy intent…" not in nxt and "Restore from…" not in nxt

    def test_a_reason_the_commit_does_not_carry_is_not_drawn_as_recorded(self, lab):
        """Nothing shrank here, so the reason sent is not on the commit: the card says
        nothing of it (a reason drawn as recorded where it is not is a wrong thing that
        looks right)."""
        lab["running"]["r2"] = _broken(lab["captured"])
        html = _preview_card(lab)
        out = _confirm(lab, html, reason="the interface was removed with its circuit")
        out = out.get_data(as_text=True)
        assert "Captured" in out and "your reason is recorded" not in out


# ------------------------------------------------ clicking what ships, where Firefox runs

@pytest.fixture(scope="module")
def live_browser():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        yield browser, srv, b


@pytest.fixture
def served(lab, live_browser):
    browser, srv, b = live_browser
    yield {"b": b, "srv": srv, "lab": lab}
    try:
        b.go("about:blank")
    finally:
        browser.close_socketio_sessions()


CARD = "document.getElementById('device-op')"
#: htmx binds a swapped-in control during its settle (about 20 ms): a click before that
#: issues nothing (measured 2026-10-02: 3 of 12 cold runs clicked an unbound button). A
#: test clicks only once nothing is swapping, settling or requesting.
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


class TestInARealBrowser:
    def test_the_menu_the_preview_and_the_confirm_as_a_person_clicks_them(self, served):
        """Actions, Capture: the card reads r2 and draws the preview when the job announces
        (the card that asked is the one that waits); Record: the result in place, the page
        never reloaded, one commit made."""
        b, lab = served["b"], served["lab"]
        lab["running"]["r2"] = _broken(lab["captured"])
        before = _head(lab["repo"])
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
        b.go(served["srv"].url("/v2/device/r2"))
        b.wait_for("return !!window.Alpine && window.NMAS && NMAS.live().state === 'connected'", 15)
        b.js("window.__notReloaded = 1; return 1")
        b.click('button[aria-haspopup="menu"]')
        b.wait_for("var m=document.querySelector('.page-actions [role=menu]'); return m && m.offsetParent", 5)
        b.click('a[role="menuitem"][data-op="capture"]')
        b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 20)
        assert "+ load-interval 30" in b.js(f"return {CARD}.textContent")
        b.click("#device-op .op-confirm")
        b.wait_for(f"return {CARD} && {CARD}.className.indexOf('op-ok') >= 0 && {SETTLED}", 20)
        text = b.js(f"return {CARD}.textContent")
        assert "Captured" in text and "Still true" in text, text[:400]
        assert b.js("return window.__notReloaded") == 1
        assert _head(lab["repo"]) != before
        b.click("#device-op .op-hd-actions button")                     # Close
        b.wait_for(f"return !{CARD} && document.querySelector('#tab-body .card')", 10)

    def test_at_phone_width_nothing_runs_past_the_screen(self, served, monkeypatch):
        """The preview at 390 px, in a frame that wide (geckodriver will not make a window
        narrower than about 500 px): no horizontal scroll, the confirm on the screen."""
        from modules import csp
        # For the frame the page is measured in, and nothing else (as the layout test does).
        monkeypatch.setattr(csp, "STRICT_POLICY", csp.STRICT_POLICY.replace(
            "frame-ancestors 'none'", "frame-ancestors 'self'"))
        b, lab = served["b"], served["lab"]
        lab["running"]["r2"] = _broken(lab["captured"])
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1200, "height": 900})
        b.go(served["srv"].url("/v2/devices"))           # a page with nothing to start
        b.wait_for("return !!window.Alpine", 10)
        b.js("var f=document.createElement('iframe'); f.id='phone'; f.width='390';"
             "f.height='800'; f.style.position='fixed'; f.style.left='0'; f.style.top='0';"
             "f.style.border='0'; f.style.zIndex='9999';"
             "f.src=location.origin + '/v2/device/r2?op=capture';"
             "document.documentElement.appendChild(f); return 1")
        b.wait_for("var d=document.getElementById('phone').contentDocument;"
                   "return d && d.querySelector('#device-op .op-confirm')", 20)
        got = b.js("var w=document.getElementById('phone').contentWindow, d=w.document;"
                   "var btn=d.querySelector('#device-op .op-confirm').getBoundingClientRect();"
                   "return {inner: w.innerWidth, scroll: d.documentElement.scrollWidth,"
                   " button: Math.round(btn.right)};")
        assert got["inner"] == 390, got
        assert got["scroll"] <= 390, ("the page scrolls sideways at phone width", got)
        assert got["button"] <= 390, ("the confirm runs past the screen", got)
