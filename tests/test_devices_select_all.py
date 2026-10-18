"""The Devices list's select-all (the operator's walk, 2026-10-18, B; C902's agreed design, R1).

A tri-state box in the table's head ticks every row SHOWN under the current search and
filters, labelled "Select the <n> shown"; a pending onboarding has no tick, so it is never one
of the n. Some ticked, the box is indeterminate; Clear selection unticks it with the rows.

The list has no pages (it draws every device that matches; paging is C450's revised board), so
with every shown row ticked the selection is ALL MATCHING, and the bar says so ("All 412
matching selected"; "All 900 selected" with no search or filter). The form then carries it as
``match=1`` with the search and filters, never as the names: each action (Plan a deploy, Save,
Change a setting) resolves the devices ITSELF from the same `device_list.listing` the page drew
(`device_list.matching`), and a ``device`` sent beside ``match`` is ignored. So a selection of
900 never travels as 900 names, and nothing the page sends widens or narrows it.

Three halves: the server's resolution at test_scale's 900 devices, each action's entry reached
with ``match`` (expectations read from the fleet itself, a path independent of `listing`); the
drawn controls; and a real browser that ticks the head box, unticks a row, clears, and opens
Save with every shown row ticked.
"""

import json
import os
import re

import pytest

from tests.test_devices_v2 import R2, R6, inv  # noqa: F401 (the fixture)
from tests.test_large_fleets import FLEET, fleet  # noqa: F401 (the fixture)
from tests.test_profile_apply import lab  # noqa: F401 (the fixture)
from tests.test_save_v2 import lab as save_lab  # noqa: F401 (Save's lab, by its own name)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIDDEN_DEVICES = re.compile(r'<input type="hidden" name="device" value="([^"]+)">')


def _names(q="", platform=""):
    """The fleet's devices a search and a platform match, read from the fleet itself."""
    q = q.lower()
    return sorted(d["hostname"] for d in FLEET
                  if (not q or q in d["hostname"].lower() or q in d["ip"].lower())
                  and (not platform or d["platform"] == platform))


@pytest.fixture
def scale(fleet, monkeypatch):  # noqa: F811
    """test_scale's 900 devices as the network Lab, whose name the action routes accept."""
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: str(name) == "Lab")
    return fleet


# ------------------------------------------------ the server resolves "all matching" itself

class TestTheServerResolvesAllMatching:
    def test_the_expectations_are_a_subset_of_more_than_a_page(self):
        """The cases below are a true subset of the fleet, each more than the large-fleets
        rule's page of 50, so neither the page nor the whole fleet could pass for them."""
        assert 50 < len(_names(q="edg")) < len(FLEET)
        assert 50 < len(_names(platform="cisco_iosxe")) < len(FLEET)
        assert 0 < len(_names(q="cor01")) < 50

    def test_matching_is_none_without_match_and_the_listing_s_rows_with_it(self, scale):
        from werkzeug.datastructures import MultiDict

        from modules import device_list
        from modules.nsot import listref
        ref = listref.resolve("Lab")
        assert device_list.matching(ref, MultiDict([("device", "cor0000")])) is None
        got = device_list.matching(ref, MultiDict([("match", "1"), ("q", "EDG")]))
        assert sorted(got) == _names(q="edg")

    def test_a_pending_onboarding_is_never_matched(self, inv, monkeypatch):  # noqa: F811
        from werkzeug.datastructures import MultiDict

        from modules import device_list
        from modules.nsot import listref
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [{
            "name": "r7", "mgmt_ip": "", "reserved_address": "203.0.113.17",
            "state": "in_flight"}])
        got = device_list.matching(listref.resolve("Lab"), MultiDict([("match", "1")]))
        assert got == ["r2", "r6"]

    def test_save_plans_exactly_the_matching_devices_never_the_names_sent(self, scale):
        """Save with ``match``: its plan (whose confirm carries each device) names exactly the
        devices the search matches, at 900; the names sent beside it are ignored."""
        client = scale["client"]
        sent = "".join(f"&device={n}" for n in ("cor0000", "acc0002", "dis0003"))
        html = client.get(f"/v2/devices/save?list=Lab&match=1&q=edg{sent}").get_data(as_text=True)
        assert sorted(HIDDEN_DEVICES.findall(html)) == _names(q="edg")

    def test_save_with_no_search_or_filter_is_the_network_s_devices(self, scale):
        html = scale["client"].get("/v2/devices/save?list=Lab&match=1").get_data(as_text=True)
        assert sorted(HIDDEN_DEVICES.findall(html)) == sorted(d["hostname"] for d in FLEET)

    def test_plan_a_deploy_orders_exactly_the_matching_devices(self, scale, monkeypatch):
        seen = {}

        def plan(list_name, order, remove=None, authorise=None, scope="x"):
            seen["order"] = list(order)
            return [{"device": d, "deployable": False, "blocking_reasons": ["planted"],
                     "to_add": [], "removal_warnings": []} for d in order]
        monkeypatch.setattr("routes.deploy.plan_devices", plan)
        r = scale["client"].get("/v2/devices/deploy?list=Lab&match=1&q=cor01"
                                "&device=edg0001&device=cor0000")
        assert r.status_code == 200
        assert sorted(seen["order"]) == _names(q="cor01")

    def test_change_a_setting_names_exactly_the_matching_devices(self, scale):
        html = scale["client"].get("/v2/devices/change?list=Lab&match=1&platform=cisco_iosxe"
                                   "&device=edg0001").get_data(as_text=True)
        assert sorted(HIDDEN_DEVICES.findall(html)) == _names(platform="cisco_iosxe")

    def test_without_match_the_ticked_names_are_the_selection(self, scale):
        r = scale["client"].get("/v2/devices/save?list=Lab&q=edg&device=cor0000"
                                "&device=acc0002")
        html = r.get_data(as_text=True)
        assert r.status_code == 200, html[html.find("<main"):][:1500]
        assert sorted(HIDDEN_DEVICES.findall(html)) == ["acc0002", "cor0000"]


# ------------------------------------------------ the drawn controls

def _head_box(html):
    thead = re.search(r"<thead>(.*?)</thead>", html, re.S).group(1)
    return re.search(r"<input [^>]*>", thead)


def _carried(html):
    """The form's all-matching fields: {name: (value, disabled)}."""
    form = re.search(r'<form method="get" action="[^"]*" class="dev-form".*?</form>', html, re.S)
    out = {}
    for tag in re.findall(r'<input type="hidden" name="(?:match|q|state|platform)"[^>]*>',
                          form.group(0)):
        name = re.search(r'name="(\w+)"', tag).group(1)
        out[name] = (re.search(r'value="([^"]*)"', tag).group(1), bool(re.search(r"\sdisabled\b", tag)))
    return out


class TestTheDrawnControls:
    def test_the_head_box_names_the_rows_shown_and_ticks_them(self, inv):  # noqa: F811
        html = inv["client"].get("/v2/devices").get_data(as_text=True)
        box = _head_box(html)
        assert box, "no select-all box in the table's head"
        assert 'type="checkbox"' in box.group(0) and 'name=' not in box.group(0)
        assert 'x-ref="all"' in box.group(0) and 'x-on:change="pickAll"' in box.group(0)
        assert 'aria-label="Select the 2 shown"' in box.group(0)
        html = inv["client"].get("/v2/devices/table?q=r6").get_data(as_text=True)
        assert 'aria-label="Select the 1 shown"' in _head_box(html).group(0)

    def test_a_pending_row_is_not_one_of_the_shown(self, inv, monkeypatch):  # noqa: F811
        monkeypatch.setattr("modules.nsot.manifest.pending_devices", lambda repo: [{
            "name": "r7", "mgmt_ip": "", "reserved_address": "203.0.113.17",
            "state": "in_flight"}])
        html = inv["client"].get("/v2/devices").get_data(as_text=True)
        assert 'aria-label="Select the 2 shown"' in _head_box(html).group(0)

    def test_the_form_carries_the_search_and_filters_only_when_all_are_ticked(self, inv):  # noqa: F811
        html = inv["client"].get("/v2/devices").get_data(as_text=True)
        assert _carried(html) == {"match": ("1", True), "q": ("", True), "state": ("", True),
                                  "platform": ("", True)}
        assert re.search(r'<strong x-text="summary">0 selected</strong>', html)
        html = inv["client"].get("/v2/devices/table?device=r2&device=r6").get_data(as_text=True)
        assert _carried(html)["match"] == ("1", False)
        assert re.search(r'<strong x-text="summary">All 2 selected</strong>', html)
        html = inv["client"].get("/v2/devices/table?q=R6&device=r6").get_data(as_text=True)
        assert _carried(html) == {"match": ("1", False), "q": ("r6", False),
                                  "state": ("", False), "platform": ("", False)}
        assert re.search(r'<strong x-text="summary">All 1 matching selected</strong>', html)
        html = inv["client"].get("/v2/devices/table?device=r6").get_data(as_text=True)
        assert _carried(html)["match"] == ("1", True)

    @pytest.mark.parametrize("names, whole, summary", [
        (["r2", "r3"], "", "2 selected"),
        (["r2", "r3"], "every", "All 2 selected"),
        (["r2", "r3"], "matching", "All 2 matching selected"),
    ])
    def test_the_bar_s_words_as_the_browser_computes_them(self, names, whole, summary):
        import dukpy
        src = open(os.path.join(ROOT, "static", "js", "nmas_apply.js"), encoding="utf-8").read()
        got = dukpy.evaljs("var window = {};\n" + src + "\nwindow.NMAS_APPLY.deviceWords("
                           f"{json.dumps(names)}, {json.dumps(whole)})")
        assert (got["summary"], got["count"]) == (summary, f"({len(names)})")


# ------------------------------------------------ clicking what ships, where Firefox runs

BOXES = ("return Array.prototype.map.call(document.querySelectorAll("
         "'#devices input[name=device]'), function (x) { return [x.value, x.checked]; })")
HEAD = ("var h = document.getElementById('dev-all');"
        "return h && [h.checked, h.indeterminate]")
BAR = "return document.querySelector('#dev-bar strong').textContent"
SETTLED = "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')"


@pytest.fixture
def served(request, monkeypatch):
    """Save's lab (r2, r3, r4 and s9) in a real browser; skipped where none runs."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    lab_ = request.getfixturevalue("save_lab")
    import app as A
    from modules.nsot import listref
    monkeypatch.setattr(listref, "active", lambda: listref.resolve("Lab"))
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            yield {"b": b, "srv": srv, "lab": lab_}
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


def _open(served, path):
    b = served["b"]
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
    b.go(served["srv"].url(path))
    b.wait_for("return !!window.Alpine && !!document.getElementById('dev-all') && " + SETTLED, 15)
    return b


class TestInARealBrowser:
    def test_the_head_box_ticks_the_shown_rows_then_is_indeterminate_then_clears(self, served):
        """Searched for "r", the list shows r2, r3 and r4 (s9 is hidden): the head box ticks
        those three and only those, the bar says all matching; one unticked leaves the head
        indeterminate and the names carried; Clear selection unticks everything."""
        b = _open(served, "/v2/devices?q=r")
        assert dict(b.js(BOXES)) == {"r2": False, "r3": False, "r4": False}
        assert b.js(HEAD) == [False, False]
        b.click("#dev-all")
        b.wait_for(BAR + " === 'All 3 matching selected'", 5)
        assert dict(b.js(BOXES)) == {"r2": True, "r3": True, "r4": True}
        assert b.js(HEAD) == [True, False]
        assert b.js("return document.querySelector('.dev-form input[name=match]').disabled") is False
        b.click("#dev-r3")
        b.wait_for(BAR + " === '2 selected'", 5)
        assert b.js(HEAD) == [False, True]
        assert b.js("return document.querySelector('.dev-form input[name=match]').disabled") is True
        b.click("#dev-all")
        b.wait_for(BAR + " === 'All 3 matching selected'", 5)
        b.click("#dev-bar .dev-bar-acts > button.btn")
        b.wait_for(BAR + " === '0 selected'", 5)
        assert dict(b.js(BOXES)) == {"r2": False, "r3": False, "r4": False}
        assert b.js(HEAD) == [False, False]

    def test_save_on_all_matching_carries_the_search_and_plans_the_matching(self, served):
        """Every shown row ticked, Actions › Save opens the plan with ``match`` and the search
        in its address and no device names, and the plan names exactly r2, r3 and r4."""
        b = _open(served, "/v2/devices?q=r")
        b.click("#dev-all")
        b.wait_for(BAR + " === 'All 3 matching selected'", 5)
        b.click('#dev-bar button[aria-haspopup="menu"]')
        b.wait_for("var m=document.querySelector('#dev-bar [role=menu]'); return m && m.offsetParent", 5)
        b.click("#dev-bar button[data-op=save]")
        b.wait_for("return location.pathname === '/v2/devices/save' && "
                   "!!document.querySelector('#save-op .op-confirm') && " + SETTLED, 15)
        query = b.js("return location.search")
        assert "match=1" in query and "q=r" in query and "device=" not in query, query
        got = b.js("return Array.prototype.map.call(document.querySelectorAll("
                   "'#save-op input[name=device]'), function (x) { return x.value; })")
        assert sorted(got) == ["r2", "r3", "r4"], got
