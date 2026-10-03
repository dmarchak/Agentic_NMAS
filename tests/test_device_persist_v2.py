"""The device page's Persist on v2 (7.3; the device-actions mockup signed off 2026-10-02).

On test_persist_screen's lab (r2 and s9, the device side faked at `onboard.persist_on_device`,
the ONE save of a startup config; the record captured), through the real routes and
templates:

- the Actions menu draws Persist as its card's request, its (i) beside it, after Rotate as the
  mockup orders them; without script the page draws the card;
- the preview card draws what persist sends (`write memory`) and then reads, what it will not
  do, its operands (driver and dialect apart, the account, the startup check's last reading,
  the plan hash), its checks naming the verified person, and the confirm bound to the plan's
  hash, busy on itself; drawing it contacts no device;
- a device with no driver recorded, a held device and a viewer who may not confirm each fail
  their check by name and get no confirm;
- the confirm saves once, holding the device, as the verified person, records it "via device
  page", and draws the result in place: persisted, or saved and NOT persisted (danger, with
  Preview it again), or refused when the plan moved, with nothing sent;
- a write naming no list, an unknown list, or no plan is refused with nothing sent;
- in a real browser: Actions, Persist, the confirm and Close, with no reload, and nothing past
  the screen at 390 px.
"""

import json
import re

import pytest

from tests.test_persist_screen import lab  # noqa: F401 (the fixture)


def _card(lab, device="r2", back="history"):  # noqa: F811
    r = lab["client"].get(f"/v2/device/{device}/persist?back={back}")
    assert r.status_code == 200, r.get_data(as_text=True)[:400]
    return r.get_data(as_text=True)


def _confirm(lab, html, device="r2", **over):  # noqa: F811
    vals = json.loads(re.search(r"hx-vals='([^']*)'", html[html.index("op-confirm"):]).group(1))
    return lab["client"].post(f"/v2/device/{device}/persist/confirm", data={**vals, **over})


class TestTheMenu:
    def test_persist_runs_here_after_rotate(self, lab):  # noqa: F811
        html = lab["client"].get("/v2/device/r2").get_data(as_text=True)
        menu = html[html.index('role="menu"'):html.index('class="tabs"')]
        row = menu[menu.index('data-op="persist"') - 200:menu.index('data-op="persist"') + 1500]
        assert 'hx-get="/v2/device/r2/persist?back=overview"' in row
        assert 'aria-label="How does persist work?"' in row
        assert "Capture and Persist run here" in menu
        labels = re.findall(r'role="menuitem"[^>]*>([^<]+)</a>', menu)
        assert labels.index("Rotate credential…") + 1 == labels.index("Persist")

    def test_without_script_the_page_draws_the_card(self, lab):  # noqa: F811
        html = lab["client"].get("/v2/device/r2?op=persist").get_data(as_text=True)
        body = html[html.index('id="tab-body"'):]
        assert 'id="device-op"' in body and "Persist r2" in body and "op-confirm" in body


class TestThePreview:
    def test_it_draws_every_part_and_contacts_no_device(self, lab):  # noqa: F811
        html = _card(lab)
        assert lab["sent"] == [], "drawing the preview contacts no device"
        assert "Persist r2" in html
        assert '<span class="op-add">write memory (the device&#39;s own save)</span>' in html
        assert "read the startup config back" in html
        part = html[html.index("What will not happen"):html.index("Operands")]
        assert "Its running configuration is not changed" in part
        assert "No credential is rotated" in part and "No golden is committed" in part
        ops = html[html.index("Operands"):html.index("Checks")]
        assert "cisco_xe" in ops and "cisco_iosxe" in ops and "Account" in ops
        assert "Startup config, last checked" in ops and "Plan hash" in ops
        checks = html[html.index("Checks"):html.index("op-ft")]
        assert "You are a verified person: test-person@example.invalid" in checks
        assert "badge-danger" not in checks
        foot = html[html.index("op-ft"):]
        h = re.search(r'"hash": "([0-9a-f]+)"', foot).group(1)
        assert f"Bound to plan {h}" in foot and "AS IT IS" in foot
        assert 'class="op-idle">Save and read back r2' in foot
        assert 'class="op-busy">Saving r2 and reading it back' in foot
        assert 'hx-disabled-elt="this"' in foot and '"list": "Lab"' in foot
        assert 'hx-get="/v2/device/r2/history"' in html, "Cancel puts back the tab it replaced"

    def test_a_device_with_no_driver_fails_its_check(self, lab):  # noqa: F811
        html = _card(lab, device="s9")
        checks = html[html.index("Checks"):]
        assert "badge-danger" in checks and "its platform driver is recorded" in checks
        assert "op-confirm" not in html and "Not available:" in html

    def test_a_held_device_fails_its_check_by_name(self, lab):  # noqa: F811
        from modules.nsot import device_ops
        device_ops.acquire("Lab", "r2", "deploy", "alex@example.invalid")
        try:
            html = _card(lab)
        finally:
            device_ops.release("Lab", "r2")
        assert "alex@example.invalid" in html[html.index("Checks"):]
        assert "op-confirm" not in html and "Nothing is queued" in html

    def test_a_viewer_who_may_not_confirm_gets_no_confirm(self, lab, monkeypatch):  # noqa: F811
        from modules import identity
        monkeypatch.setattr(identity, "identify",
                            lambda r: identity.Identity(peer="198.51.100.7"))
        html = _card(lab)
        assert "<strong>You are a verified person</strong>" in html
        assert "op-confirm" not in html


class TestTheConfirm:
    def test_persisted_saves_once_holding_the_device_and_draws_the_result(self, lab):  # noqa: F811
        out = _confirm(lab, _card(lab)).get_data(as_text=True)
        assert lab["sent"] == [{"ip": "192.0.2.12", "held": True, "type": "cisco_xe",
                                "password_ok": True}]
        assert lab["records"] == [{"device": "r2", "state": "persisted",
                                   "actor": "test-person@example.invalid", "via": "device page"}]
        assert "op-card op-ok" in out and "Persisted" in out and "r2 is persisted" in out
        assert "test-person@example.invalid" in out[out.index("Recorded"):]
        assert "hourly startup check" in out[out.index("Still true"):]
        assert "Preview it again" not in out
        assert 'hx-get="/v2/device/r2/history"' in out, "Close puts back the tab it replaced"

    def test_saved_and_not_persisted_is_danger_and_offers_another_preview(self, lab):  # noqa: F811
        lab["state"]["answer"] = {"ok": False, "state": "not_persisted",
                                  "detail": "the startup config lacks the username line"}
        out = _confirm(lab, _card(lab)).get_data(as_text=True)
        assert "op-card op-danger" in out and "Saved, NOT persisted" in out
        assert "the startup config lacks the username line" in out and "Preview it again" in out

    def test_a_plan_that_moved_is_refused_with_nothing_sent(self, lab):  # noqa: F811
        out = _confirm(lab, _card(lab), hash="0000000000000000").get_data(as_text=True)
        assert lab["sent"] == [] and "op-card op-warn" in out
        assert "Refused: nothing was sent" in out and "the plan changed since the preview" in out

    @pytest.mark.parametrize("body,words", [
        ({"hash": "abc"}, "names no list"),
        ({"list": "Elsewhere", "hash": "abc"}, "names no list"),
        ({"list": "Lab"}, "no plan to be bound to"),
    ])
    def test_a_write_naming_no_list_or_no_plan_is_refused(self, lab, body, words):  # noqa: F811
        r = lab["client"].post("/v2/device/r2/persist/confirm", data=body)
        assert r.status_code == 400 and words in r.get_data(as_text=True)
        assert lab["sent"] == []


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
def served(lab, live_browser):  # noqa: F811
    browser, srv, b = live_browser
    yield {"b": b, "srv": srv, "lab": lab}
    try:
        b.go("about:blank")
    finally:
        browser.close_socketio_sessions()


CARD = "document.getElementById('device-op')"
#: htmx binds a swapped-in control while it settles: click only once nothing settles
#: (tests/test_device_capture_v2.py measured it).
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


class TestInARealBrowser:
    def test_the_menu_the_preview_and_the_confirm_as_a_person_clicks_them(self, served):
        b, lab = served["b"], served["lab"]  # noqa: F811
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
        b.go(served["srv"].url("/v2/device/r2"))
        b.wait_for("return !!window.Alpine && " + SETTLED, 15)
        b.js("window.__notReloaded = 1; return 1")
        b.click('button[aria-haspopup="menu"]')
        b.wait_for("var m=document.querySelector('.page-actions [role=menu]'); "
                   "return m && m.offsetParent", 5)
        b.click('a[role="menuitem"][data-op="persist"]')
        b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
        assert lab["sent"] == []
        b.click("#device-op .op-confirm")
        b.wait_for(f"return {CARD} && {CARD}.className.indexOf('op-ok') >= 0 && {SETTLED}", 15)
        assert "Persisted" in b.js(f"return {CARD}.textContent")
        assert b.js("return window.__notReloaded") == 1 and len(lab["sent"]) == 1
        b.click("#device-op .op-hd-actions button")
        b.wait_for(f"return !{CARD} && document.querySelector('#tab-body .card')", 10)

    def test_at_phone_width_nothing_runs_past_the_screen(self, served, monkeypatch):
        from modules import csp
        # For the frame the page is measured in, and nothing else (as the layout test does).
        monkeypatch.setattr(csp, "STRICT_POLICY", csp.STRICT_POLICY.replace(
            "frame-ancestors 'none'", "frame-ancestors 'self'"))
        b = served["b"]
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1200, "height": 900})
        b.go(served["srv"].url("/v2/devices"))
        b.wait_for("return !!window.Alpine", 10)
        b.js("var f=document.createElement('iframe'); f.id='phone'; f.width='390';"
             "f.height='800'; f.style.position='fixed'; f.style.left='0'; f.style.top='0';"
             "f.style.border='0'; f.style.zIndex='9999';"
             "f.src=location.origin + '/v2/device/r2?op=persist';"
             "document.documentElement.appendChild(f); return 1")
        b.wait_for("var d=document.getElementById('phone').contentDocument;"
                   "return d && d.querySelector('#device-op .op-confirm')", 15)
        got = b.js("var w=document.getElementById('phone').contentWindow, d=w.document;"
                   "var btn=d.querySelector('#device-op .op-confirm').getBoundingClientRect();"
                   "return {inner: w.innerWidth, scroll: d.documentElement.scrollWidth,"
                   " button: Math.round(btn.right)};")
        assert got["inner"] == 390 and got["scroll"] <= 390 and got["button"] <= 390, got
