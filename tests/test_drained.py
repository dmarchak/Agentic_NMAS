"""A device marked DRAINED by a person (the operator, 2026-10-06: the smallest form, approved
without a mockup: a badge, and a Set/Clear card in the Actions menu; `modules/drained.py`).

- The store: a mark is appended with who, when and why (masked), owner-only; a device's state
  is its newest event; it is refused, naming why and recording nothing, without a verified
  person, with a reason not the shape of one, when the device is already in that state, or
  for a network that does not exist.
- The card, through the real routes on test_persist_screen's lab (r2 in "Lab"): the Actions
  menu offers Mark drained…, its card asks for a reason and sends nothing; the confirm records
  it as the verified person; the page header and the Devices list then draw the badge with
  who, when and why on hover, and the menu offers Clear the drained mark…; a second mark and
  a short reason are refused in the card with nothing recorded; clearing takes the badge away.
- History: each mark and clear is a line on the device's timeline, by its person, with why.
- Needs attention: a Grafana alert whose every device is drained raises no row and is said
  under What was checked, naming the drain; an alert naming a device in service still does.
"""

import json
import os
import re
import stat

import pytest

from modules import drained as D
from tests.test_persist_screen import lab  # noqa: F401 (the fixture)

WHY = "moving traffic off it for the IOS patch"
BACK = "back in service after the IOS patch"


def _mark(lab, state="drained", why=WHY, device="r2", list_name="Lab"):  # noqa: F811
    return lab["client"].post(f"/v2/device/{device}/drained/confirm",
                              data={"list": list_name, "state": state, "why": why,
                                    "back": "overview"})


def _text(r):
    return r.get_data(as_text=True)


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------

class TestTheStore:
    def test_a_mark_is_recorded_with_who_when_and_why_owner_only(self, lab):  # noqa: F811
        e = D.mark("Lab", "r2", D.DRAINED, why=WHY, by="test-person@example.invalid",
                   verified="access")
        assert e["by"] == "test-person@example.invalid" and e["why"] == WHY
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", e["at"])
        assert D.state_of("Lab", "r2")["at"] == e["at"]
        assert D.state_of("Lab", "s9") is None
        path = D._path("Lab")
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        D.mark("Lab", "r2", D.CLEARED, why=BACK, by="test-person@example.invalid",
               verified="access")
        assert D.current("Lab") == {}
        assert [x["state"] for x in D.events("Lab", "r2")] == ["drained", "cleared"]

    def test_a_reason_is_masked_at_rest(self, lab):  # noqa: F811
        D.mark("Lab", "r2", D.DRAINED, why="patching it; old line was username admin secret 9 0822455D0A16",
               by="p@example.invalid", verified="access")
        with open(D._path("Lab"), encoding="utf-8") as fh:
            assert "0822455D0A16" not in fh.read()

    @pytest.mark.parametrize("kw,words", [
        ({"by": ""}, "no verified person"),
        ({"why": "patch"}, "too short to be a reason"),
        ({"why": ""}, "has no reason"),
        ({"state": "paused"}, "is not drained or cleared"),
        ({"list_name": "Nowhere"}, "no network is named 'Nowhere'"),
    ])
    def test_each_refusal_names_why_and_records_nothing(self, lab, kw, words):  # noqa: F811
        args = {"list_name": "Lab", "device": "r2", "state": D.DRAINED, "why": WHY,
                "by": "p@example.invalid", "verified": "access", **kw}
        with pytest.raises(D.Refused, match=re.escape(words)):
            D.mark(args.pop("list_name"), args.pop("device"), args.pop("state"), **args)
        assert D.events("Lab") == []

    def test_twice_drained_or_clearing_what_is_not_drained_is_refused(self, lab):  # noqa: F811
        with pytest.raises(D.Refused, match="r2 is not drained"):
            D.mark("Lab", "r2", D.CLEARED, why=BACK, by="p@example.invalid", verified="access")
        D.mark("Lab", "r2", D.DRAINED, why=WHY, by="p@example.invalid", verified="access")
        with pytest.raises(D.Refused, match=r"r2 is already drained \(by p@example.invalid"):
            D.mark("Lab", "r2", D.DRAINED, why=WHY, by="q@example.invalid", verified="access")
        assert len(D.events("Lab")) == 1

    def test_an_unreadable_line_is_skipped_never_a_guessed_state(self, lab):  # noqa: F811
        D.mark("Lab", "r2", D.DRAINED, why=WHY, by="p@example.invalid", verified="access")
        with open(D._path("Lab"), "a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        assert list(D.current("Lab")) == ["r2"]


# ---------------------------------------------------------------------------
# The card, the badge and the menu, through the real routes
# ---------------------------------------------------------------------------

class TestTheCard:
    def test_the_menu_offers_it_and_its_card_asks_for_a_reason(self, lab):  # noqa: F811
        html = _text(lab["client"].get("/v2/device/r2"))
        menu = html[html.index('role="menu"'):html.index('class="tabs"')]
        row = menu[menu.index('data-op="drained"') - 300:menu.index('data-op="drained"') + 600]
        assert "Mark drained…" in row and 'aria-label="How does drained work?"' in row
        assert 'hx-get="/v2/device/r2/drained?back=overview' in row
        assert 'id="drained-badge"' in html and "badge-warn" not in html[
            html.index('id="drained-badge"'):html.index('id="drained-badge"') + 300]
        card = _text(lab["client"].get("/v2/device/r2/drained?back=overview"))
        assert "Mark r2 drained" in card and "Not drained." in card
        assert 'name="why"' in card and "required" in card
        assert 'name="state" value="drained"' in card and 'name="list" value="Lab"' in card
        assert 'class="op-busy">Recording' in card and 'hx-disabled-elt="find button"' in card
        assert "Nothing is sent to the device" in card
        assert lab["sent"] == [] and D.events("Lab") == []

    def test_the_confirm_records_it_and_every_screen_draws_the_badge(self, lab):  # noqa: F811
        r = _mark(lab)
        assert r.status_code == 200, _text(r)[:400]
        assert r.headers.get("X-NMAS-Invalidates") and "inventory" in r.headers[
            "X-NMAS-Invalidates"]
        out = _text(r)
        assert "Drained by test-person@example.invalid at" in out and WHY in out
        (e,) = D.events("Lab", "r2")
        assert e["by"] == "test-person@example.invalid" and e["verified"] == "access"
        assert lab["sent"] == [], "marking a device drained sends nothing"
        page = _text(lab["client"].get("/v2/device/r2"))
        head = page[page.index('class="title-row"'):page.index('class="sub"')]
        assert ">Drained<" in head and f"drained by test-person@example.invalid at {e['at']}: {WHY}" in head
        assert "Clear the drained mark…" in page
        badge = _text(lab["client"].get("/v2/device/r2/drained/badge"))
        assert ">Drained<" in badge and 'hx-trigger="nmas:inventory from:body"' in badge
        listing = _text(lab["client"].get("/v2/devices"))
        r2 = listing[listing.index(">r2<"):listing.index(">r2<") + 600]
        assert ">Drained<" in r2 and WHY in r2
        s9 = listing[listing.index(">s9<"):listing.index(">s9<") + 400]
        assert ">Drained<" not in s9

    def test_a_refusal_is_drawn_in_the_card_and_records_nothing(self, lab):  # noqa: F811
        r = _mark(lab, why="patch")
        assert r.status_code == 409 and "too short to be a reason" in _text(r)
        assert "Nothing was recorded." in _text(r) and 'value="patch"' in _text(r)
        assert D.events("Lab") == []
        _mark(lab)
        again = _mark(lab)
        assert again.status_code == 409 and "r2 is already drained" in _text(again)
        assert len(D.events("Lab")) == 1

    def test_clearing_takes_the_badge_away(self, lab):  # noqa: F811
        _mark(lab)
        card = _text(lab["client"].get("/v2/device/r2/drained?back=overview"))
        assert "Clear the drained mark on r2" in card and 'name="state" value="cleared"' in card
        r = _mark(lab, state="cleared", why=BACK)
        assert r.status_code == 200 and "Back in service" in _text(r)
        page = _text(lab["client"].get("/v2/device/r2"))
        assert ">Drained<" not in page[page.index('class="title-row"'):page.index('class="sub"')]
        assert "Mark drained…" in page

    def test_a_write_naming_no_network_is_refused(self, lab):  # noqa: F811
        r = _mark(lab, list_name="")
        assert r.status_code == 400 and "names no list" in _text(r)
        assert D.events("Lab") == []


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class TestHistory:
    def test_each_mark_and_clear_is_on_the_device_s_timeline(self, lab):  # noqa: F811
        before = _text(lab["client"].get("/v2/device/r2/history"))
        assert "Marked drained" not in before
        _mark(lab)
        _mark(lab, state="cleared", why=BACK)
        html = _text(lab["client"].get("/v2/device/r2/history"))
        assert "Marked drained" in html and "Drained mark cleared" in html
        assert WHY in html and BACK in html and "test-person@example.invalid" in html
        assert "Marked drained" not in _text(lab["client"].get("/v2/device/s9/history"))


# ---------------------------------------------------------------------------
# Needs attention
# ---------------------------------------------------------------------------

class TestNeedsAttention:
    @pytest.fixture
    def alert_on_r1(self, monkeypatch):
        from modules import attention as A
        from tests.test_grafana_reader import INVENTORY, cached, load, parse, rule
        from modules import device
        monkeypatch.setattr(device, "load_saved_devices", lambda *a, **k: list(INVENTORY))
        monkeypatch.setattr(device, "get_device_lists", lambda: [{"name": "Lab", "filename": "lab"}])
        view = load("rules_view")
        inst = next(a for a in rule(view, "Device unreachable (SNMP)")["alerts"]
                    if a["labels"]["instance"] == "10.255.1.11")
        inst["state"], inst["activeAt"] = "Alerting", "2026-09-28T20:20:00Z"
        return lambda: A.grafana_source(cached=cached(parse(view)))

    def test_an_alert_on_a_drained_device_is_said_under_checked_not_raised(
            self, alert_on_r1, monkeypatch):
        drained = {"r1": {"device": "r1", "state": "drained", "by": "p@example.invalid",
                          "at": "2026-10-06T15:00:00Z", "why": WHY}}
        monkeypatch.setattr(D, "current", lambda name: drained if name == "Lab" else {})
        res = alert_on_r1()
        assert res["rows"] == []
        assert ("1 alert(s) on drained devices, not raised: Device unreachable (SNMP) on r1 "
                f"(drained by p@example.invalid at 2026-10-06T15:00:00Z: {WHY})") in res["checked"]

    def test_the_control_the_same_alert_undrained_is_a_row(self, alert_on_r1, monkeypatch):
        monkeypatch.setattr(D, "current", lambda name: {})
        (row,) = alert_on_r1()["rows"]
        assert row["devices"] == ["r1"]

    def test_another_device_drained_holds_nothing_back(self, alert_on_r1, monkeypatch):
        monkeypatch.setattr(D, "current", lambda name: {"r2": {"state": "drained"}})
        (row,) = alert_on_r1()["rows"]
        assert row["devices"] == ["r1"]

    def test_an_unreadable_record_holds_nothing_back_and_says_so(self, alert_on_r1, monkeypatch):
        def broken(name):
            raise OSError("unreadable")
        monkeypatch.setattr(D, "current", broken)
        res = alert_on_r1()
        assert len(res["rows"]) == 1
        assert "the drained record could not be read (OSError)" in res["checked"]


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
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"
BADGE = "document.querySelector('#drained-badge .badge')"


class TestInARealBrowser:
    def test_the_menu_the_reason_and_the_badge_in_place(self, served):
        b, lab = served["b"], served["lab"]  # noqa: F811
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
        b.go(served["srv"].url("/v2/device/r2"))
        b.wait_for("return !!window.Alpine && " + SETTLED, 15)
        b.js("window.__notReloaded = 1; return 1")
        assert b.js(f"return !{BADGE}")
        b.click('button[aria-haspopup="menu"]')
        b.wait_for("var m=document.querySelector('.page-actions [role=menu]'); "
                   "return m && m.offsetParent", 5)
        b.click('a[role="menuitem"][data-op="drained"]')
        b.wait_for(f"return {CARD} && {CARD}.querySelector('.op-confirm') && {SETTLED}", 15)
        b.js(f"document.getElementById('drained-why').value = {WHY!r}; return 1")
        b.click("#device-op .op-confirm")
        b.wait_for(f"return {CARD} && {CARD}.className.indexOf('op-ok') >= 0 && {SETTLED}", 15)
        # The header redraws on the confirm's announcement, with no reload.
        b.wait_for(f"return {BADGE} && {SETTLED}", 10)
        assert WHY in b.js(f"return {BADGE}.getAttribute('title')")
        assert b.js("return window.__notReloaded") == 1 and lab["sent"] == []
        assert [e["state"] for e in D.events("Lab", "r2")] == ["drained"]

    def test_at_phone_width_nothing_runs_past_the_screen(self, served, monkeypatch):
        from modules import csp
        monkeypatch.setattr(csp, "STRICT_POLICY", csp.STRICT_POLICY.replace(
            "frame-ancestors 'none'", "frame-ancestors 'self'"))
        b = served["b"]
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1200, "height": 900})
        b.go(served["srv"].url("/v2/devices"))
        b.wait_for("return !!window.Alpine", 10)
        b.js("var f=document.createElement('iframe'); f.id='phone'; f.width='390';"
             "f.height='800'; f.style.position='fixed'; f.style.left='0'; f.style.top='0';"
             "f.style.border='0'; f.style.zIndex='9999';"
             "f.src=location.origin + '/v2/device/r2?op=drained';"
             "document.documentElement.appendChild(f); return 1")
        b.wait_for("var d=document.getElementById('phone').contentDocument;"
                   "return d && d.querySelector('#device-op .op-confirm')", 15)
        got = b.js("var w=document.getElementById('phone').contentWindow, d=w.document;"
                   "var btn=d.querySelector('#device-op .op-confirm').getBoundingClientRect();"
                   "var inp=d.getElementById('drained-why').getBoundingClientRect();"
                   "return {inner: w.innerWidth, scroll: d.documentElement.scrollWidth,"
                   " button: Math.round(btn.right), input: Math.round(inp.right)};")
        assert got["inner"] == 390 and got["scroll"] <= 390, got
        assert got["button"] <= 390 and got["input"] <= 390, got
