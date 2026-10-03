"""The operator's first real use of restore on v2 (2026-10-03), and Mode B's entry point:
C399 to C403.

- C399, a dead first click. A cold page whose deferred scripts are slow (Alpine held back by
  the served app, the browser's cache off, navigation returning at once as a person sees the
  page): the Actions button is clicked BEFORE Alpine has run, three times on fresh loads, and
  the menu must open each time (the early click is kept and replayed, `nmas_early.js`). The
  test proves it is early: Alpine is absent when it clicks. Then "Restore from…", its answer
  held back: the menu stays open with the row busy on itself until the card arrives, then
  closes. And the chooser checks the credentials of only the moments it draws.
- C400, the busy words. At rest the Preview button shows no busy words (they showed always:
  the rule was keyed on the confirm's class); while its request runs they show, and they go
  when it ends. Another request replacing it (a moment ticked while the preview is held back)
  aborts it: no busy button is left, and no late preview lands over the newer card.
- C401 and C402, the card's words: a moment the device already matches says "nothing to
  send, so nothing to confirm", once, never "read back at apply"; the summary names the
  device and the moment, never the fleet's "N of M device(s) you selected".
- C403, "Remove lines (Mode B)…": with lines removable it opens THE deploy card at "Left on
  the device", highlighted, with its one line, and the menu closes; with none it opens
  nothing and the row says so, the menu still open; the card's own re-plans keep the focus.
"""

import html as html_mod
import re
import time

import pytest

from tests.test_device_restore_v2 import history  # noqa: F401 (the fixture)
from tests.test_device_deploy_v2 import deploy  # noqa: F401 (the fixture)
from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

#: How long the served app holds Alpine back: long enough that a click lands before it runs.
ALPINE_DELAY = 2.0
BUTTON = ".page-actions button[aria-haspopup=menu]"
MENU = ("var m = document.querySelector('.page-actions [role=menu]');"
        "return !!(m && m.offsetParent !== null)")
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
CARD = "document.querySelector('#device-op')"
NO_CACHE = {"browser.cache.disk.enable": False, "browser.cache.memory.enable": False}


def _browser_or_skip():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    return browser


def _slow_alpine(monkeypatch):
    import app as A
    real = A.app.view_functions["static"]

    def slow(**kw):
        if kw.get("filename", "").endswith("alpinejs-csp/cdn.min.js"):
            time.sleep(ALPINE_DELAY)
        return real(**kw)
    monkeypatch.setitem(A.app.view_functions, "static", slow)


def _hold(monkeypatch, target, seconds):
    """Hold *target* (a dotted name) back by *seconds*, as the host's 6 s chooser was."""
    import importlib
    mod_name, attr = target.rsplit(".", 1)
    mod = importlib.import_module(mod_name)
    real = getattr(mod, attr)

    def slow(*a, **k):
        time.sleep(seconds)
        return real(*a, **k)
    monkeypatch.setattr(mod, attr, slow)


class TestC399:
    def test_a_click_before_the_scripts_run_opens_the_menu_every_time(self, history,  # noqa: F811
                                                                      monkeypatch):
        browser = _browser_or_skip()
        import app as A
        _slow_alpine(monkeypatch)
        with browser.Served(A.app) as srv, browser.Browser(prefs=NO_CACHE,
                                                           page_load="none") as b:
            try:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": 1280, "height": 1000})
                for attempt in range(3):
                    b.go("about:blank")
                    b.go(srv.url(f"/v2/device/r2?cold={attempt}"))
                    b.wait_for(f"return !!document.querySelector('{BUTTON}')", 10)
                    assert b.js("return !window.Alpine"), "the click must land before Alpine"
                    b.click(BUTTON)
                    # Open BY THE CLICK, once Alpine runs: Alpine started (the page's scripts
                    # loaded at all), the button says it is expanded, and the menu shows.
                    b.wait_for("return !!window.Alpine && document.querySelector('"
                               + BUTTON + "').getAttribute('aria-expanded') === 'true' && "
                               "(function () { " + MENU + " })()", ALPINE_DELAY + 8)
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()

    def test_the_row_stays_open_and_busy_until_its_card_arrives(self, history,  # noqa: F811
                                                                monkeypatch):
        browser = _browser_or_skip()
        import app as A
        _hold(monkeypatch, "routes.golden.restore_points_for", 2.0)
        with browser.Served(A.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url("/v2/device/r2"))
                b.wait_for("return !!window.Alpine && " + SETTLED, 15)
                b.click(BUTTON)
                b.wait_for(MENU, 10)
                b.click('.page-actions a[data-op="restore"]')
                b.wait_for("var r = document.querySelector('.page-actions a[data-op=restore]');"
                           "return r && r.classList.contains('htmx-request')", 2)
                assert b.js(MENU), "the menu stays open while the row is busy"
                b.wait_for(f"return {CARD} && {CARD}.querySelector('input[name=chosen]')", 15)
                b.wait_for("var m = document.querySelector('.page-actions [role=menu]');"
                           "return m && m.offsetParent === null", 5)
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()

    def test_the_chooser_checks_only_the_moments_it_draws(self, history,  # noqa: F811
                                                          monkeypatch):
        from modules.nsot import restore as RS
        seen = []
        real = RS.baseline_credential_gaps
        monkeypatch.setattr(RS, "baseline_credential_gaps",
                            lambda repo, ref, *a, **k: seen.append(ref) or real(repo, ref, *a, **k))
        from routes.golden import restore_points_for
        points = restore_points_for("Lab", "r2", checked=1)
        assert len(points) >= 2 and len(seen) <= 1, (len(points), seen)
        assert {p["credential"] for p in points[1:]} == {"unchecked"}
        seen.clear()
        whole = restore_points_for("Lab", "r2")
        assert "unchecked" not in {p["credential"] for p in whole}, "unbounded checks every one"
        assert len(seen) == len([p for p in whole if p["kind"] != "head"])


class TestC400:
    def test_busy_words_show_only_while_the_request_runs(self, history,  # noqa: F811
                                                         monkeypatch):
        browser = _browser_or_skip()
        import app as A
        _hold(monkeypatch, "routes.golden.restore_plan", 1.5)
        with browser.Served(A.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url("/v2/device/r2?op=restore"))
                b.wait_for("return !!window.Alpine && !!document.querySelector('#restore-preview')"
                           " && " + SETTLED, 15)
                busy = ("var s = document.querySelector('#restore-preview .op-busy');"
                        "return !!(s && s.offsetParent !== null)")
                assert not b.js(busy), "no busy words at rest"
                b.click("#restore-preview")
                b.wait_for(busy, 2)
                b.wait_for(f"return !document.querySelector('#restore-preview') && {SETTLED}", 15)
                assert not b.js("return !!document.querySelector('.htmx-request')")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()

    def test_a_tick_replaces_a_preview_in_flight_and_nothing_lands_late(self, history,  # noqa: F811
                                                                        monkeypatch):
        browser = _browser_or_skip()
        import app as A
        _hold(monkeypatch, "routes.golden.restore_plan", 2.0)
        with browser.Served(A.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url("/v2/device/r2?op=restore"))
                b.wait_for("return !!window.Alpine && !!document.querySelector('#restore-preview')"
                           " && " + SETTLED, 15)
                b.click("#restore-preview")
                b.wait_for("return document.querySelector('#restore-preview')"
                           ".classList.contains('htmx-request')", 2)
                b.js("var h = document.querySelector('input[name=chosen][value=HEAD]');"
                     "h.checked = true; h.dispatchEvent(new Event('change', {bubbles: true}));"
                     "return 1")
                b.wait_for("var b = document.querySelector('#restore-preview');"
                           "return b && /Preview golden now/.test(b.textContent) && "
                           "!b.classList.contains('htmx-request') && !b.disabled && " + SETTLED, 10)
                time.sleep(3.0)          # past the held preview's answer
                assert b.js("var b = document.querySelector('#restore-preview');"
                            "return !!b && /Preview golden now/.test(b.textContent)"), \
                    "the older preview landed over the newer card"
                assert not b.js("var s = document.querySelector('#restore-preview .op-busy');"
                                "return !!(s && s.offsetParent !== null)")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()


    def test_two_ticks_in_a_row_the_older_answer_never_lands_last(self, history,  # noqa: F811
                                                                  monkeypatch):
        """The case the card's request sync guards (an answer whose element has left the page
        is already dropped by htmx): a tick whose re-read is slow, then another whose re-read
        is fast. The newer card must stay; the older, slower answer is aborted."""
        browser = _browser_or_skip()
        import app as A
        from routes import golden as G
        real, calls = G.restore_points_for, []

        def held(*a, **k):
            calls.append(1)
            if len(calls) == 2:          # the first tick's re-read (the page's own is first)
                time.sleep(2.0)
            return real(*a, **k)
        monkeypatch.setattr(G, "restore_points_for", held)
        with browser.Served(A.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url("/v2/device/r2?op=restore"))
                b.wait_for("return !!window.Alpine && !!document.querySelector('#restore-preview')"
                           " && " + SETTLED, 15)
                tick = ("var h = document.querySelector('input[name=chosen][value=\"' + arguments[0]"
                        " + '\"]'); h.checked = true;"
                        "h.dispatchEvent(new Event('change', {bubbles: true})); return 1")
                b.js(tick, history["middle"])
                b.js(tick, "HEAD")
                b.wait_for("var b = document.querySelector('#restore-preview');"
                           "return b && /Preview golden now/.test(b.textContent) && " + SETTLED, 10)
                time.sleep(3.0)          # past the first tick's held answer
                assert b.js("var b = document.querySelector('#restore-preview');"
                            "return !!b && /Preview golden now/.test(b.textContent)"), \
                    "the older tick's answer landed over the newer card"
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()


class TestC401C402:
    def test_a_moment_already_matched_says_one_thing_and_names_the_device(self, matched):
        r = matched["client"].get("/v2/device/r2/restore/preview?moment=HEAD&back=overview")
        card = html_mod.unescape(r.get_data(as_text=True))
        assert "r2 already holds every line of golden now: nothing to send." in card, re.sub(r"<[^>]+>", " ", card)[:900]
        assert "Nothing to send, so nothing to confirm: r2 already matches golden now." in card
        assert "read back at apply" not in card
        assert "you selected" not in card and "of 1 device(s)" not in card
        assert "op-confirm" not in card


def _hx_get(lab, url, target=None):
    headers = {"HX-Request": "true"}
    if target:
        headers["HX-Target"] = target
    r = lab["client"].get(url, headers=headers)
    return r, r.get_data(as_text=True)


@pytest.fixture
def matched(lab, monkeypatch):  # noqa: F811
    """r2 whose golden holds nothing its committed intent lacks."""
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    devices = [{"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
                "platform": "cisco_iosxe", "username": "admin"}]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(d) for d in devices])
    # The restore asks the inventory whether a device is stale, and the inventory modules hold
    # their own name for the list's folder (as test_device_restore_v2's history does).
    from modules import config
    for mod in ("modules.inventory", "modules.inventory.source_config"):
        monkeypatch.setattr(mod + ".get_list_data_dir", config.get_list_data_dir)
    return lab


class TestC403:
    URL = "/v2/device/r2/deploy?back=overview&focus=removal"

    def test_with_lines_to_remove_the_row_opens_the_deploy_at_them(self, deploy):  # noqa: F811
        r, card = _hx_get(deploy, self.URL)
        assert r.headers.get("HX-Retarget") == "#tab-body"
        assert r.headers.get("HX-Reswap") == "innerHTML show:#removal:top"
        assert r.headers.get("HX-Trigger") == "nmas-close-menu"
        part = card[card.index('id="removal"') - 60:card.index('id="removal"') + 600]
        assert "op-focus" in part and "Left on the device" in part
        assert ("Removals are made as part of a deploy: tick the lines to remove here; "
                "anything intent adds is sent with them.") in part
        assert 'name="focus" value="removal"' in card, "re-plans keep the focus"

    def test_a_re_plan_from_the_card_keeps_the_focus_and_is_only_redrawn(self, deploy):  # noqa: F811
        r, card = _hx_get(deploy, self.URL, target="device-op")
        assert "HX-Retarget" not in r.headers and "op-focus" in card

    def test_with_nothing_removable_the_row_says_so_and_opens_nothing(self, matched):
        r, row = _hx_get(matched, self.URL)
        assert "HX-Retarget" not in r.headers and 'id="device-op"' not in row
        assert 'aria-disabled="true"' in row
        assert "Nothing to remove: r2 holds no line its committed intent lacks." in row

    def test_the_page_without_script_draws_the_focused_card(self, deploy):  # noqa: F811
        _r, page = _hx_get(deploy, "/v2/device/r2?op=deploy&focus=removal")
        assert "op-focus" in page and 'id="removal"' in page

    def test_in_a_real_browser_the_row_opens_the_card_at_the_lines(self, deploy):  # noqa: F811
        browser = _browser_or_skip()
        import app as A
        with browser.Served(A.app) as srv, browser.Browser() as b:
            try:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": 1280, "height": 700})
                b.go(srv.url("/v2/device/r2"))
                b.wait_for("return !!window.Alpine && " + SETTLED, 15)
                b.click(BUTTON)
                b.wait_for(MENU, 10)
                b.click('.page-actions a[data-op="removal"]')
                b.wait_for("var p = document.querySelector('#removal.op-focus');"
                           "return !!p && " + SETTLED, 15)
                top = b.js("return document.querySelector('#removal').getBoundingClientRect().top")
                assert -2 <= top < 200, f"scrolled to the lines on the device ({top}; sub-pixel rounding allowed)"
                assert not b.js(MENU), "the menu closed"
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
