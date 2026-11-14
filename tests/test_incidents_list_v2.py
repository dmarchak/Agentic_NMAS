"""Troubleshooting › Incidents and the sidebar's Troubleshooting section (board T,
~/Documents/nmas-reports/boards/troubleshooting-nav.html; the GUI review's proposal 17 and its
finding IN9; provisional, operator review pending, the operator 2026-11-13).
`modules/incidents_list.py`, `routes/incidents_v2.py`, `templates/v2/incidents.html`,
`templates/v2/_incidents_chip.html`, and the sidebar in `templates/v2/base.html`.

On the heal's lab (tests/test_incident_page.py's `client`), every incident planted from
tests/fixtures/incident_page/ (the stores as the heal modules' own writers left them: a heal
done with no human, a heal rolled back, a can't-fix that took another device's incident in with
a related one watching). No device, no network.

- **Each row is its incident page's:** the list's model gives each incident the state and the
  title its own page draws (THE state function, THE title builder) and THE incident address;
  the expectations are read through the incident page, never through the list's code. Open
  groups by what each waits for, Closed by how each ended; a folded incident is not a row and
  is counted; search and the device filter narrow it.
- **Page speed:** one read of each heal store whatever the count; the routes write nothing and
  carry the strict policy; the page draws the viewer through `identity.viewer()`.
- **Drawn:** the template, rendered from the model, says an unreadable store and an empty
  network; 900 incidents draw a summary and closed groups, at most `SHOWN` rows a group, no
  long expanded list (test_large_fleets' scan). The chips say the open count, the mode, and a
  store they cannot read.
- **Pressed, in Firefox** (where one runs; skipped naming why elsewhere): the sidebar's
  Troubleshooting section is above OBSERVE with the board's two entries, and each opens its
  page; on the list, Closed, a row's title, the incident page's breadcrumb back to its tab,
  and the search narrowing the rows.
"""
import json
import os
import re

import pytest

from modules import incident_page as IP
from modules import incidents_list as L
from tests.test_heal_decide import lab  # noqa: F401  (the fixture `client` builds on)
from tests.test_incident_page import NET, client  # noqa: F401  (the fixture)
from tests.test_large_fleets import LIMIT, expanded_devices
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "incident_page")


def _load(name: str) -> dict:
    with open(os.path.join(FIXTURES, f"{name}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _stores():
    from modules.heal import decisions as HD
    from modules.heal import incidents as HI
    from modules.heal import steplog as SL

    return {"incidents": HI.path(NET), "decisions": HD.path(NET), "steps": SL._path(NET)}


def plant(docs: list) -> None:
    """Write the network's three heal stores from fixture documents, as they were captured."""
    from modules.heal import incidents as HI

    paths = _stores()
    for p in paths.values():
        os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(paths["incidents"], "w", encoding="utf-8") as fh:
        json.dump({"version": HI.VERSION,
                   "incidents": [i for d in docs for i in d["incidents"]]}, fh)
    for key in ("decisions", "steps"):
        with open(paths[key], "w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(row) + "\n" for d in docs for row in d[key])


def tear(key: str) -> None:
    with open(_stores()[key], "w", encoding="utf-8") as fh:
        fh.write("{torn\n")


@pytest.fixture
def planted(client):  # noqa: F811
    docs = {n: _load(n) for n in ("healed", "failed", "busy")}
    plant(list(docs.values()))
    return docs


def drawn(p: dict, **context) -> str:
    """The list's template rendered from the model *p*, in a request for its page."""
    import app as APP
    from flask import render_template

    from routes.device_v2 import _who

    with APP.app.test_request_context(f"/v2/incidents?list={NET}"):
        return render_template("v2/incidents.html", p=p, who=_who(), active_nav="incidents",
                               **context)


def chip(**context) -> str:
    import app as APP
    from flask import render_template

    with APP.app.test_request_context(f"/v2/incidents/count?list={NET}"):
        return render_template("v2/_incidents_chip.html", **context)


def listed(p: dict) -> dict:
    """The model's rows: {incident id: row}."""
    return {r["id"]: r for g in p["groups"] for r in g["rows"]}


class TestTheRows:
    def test_each_row_is_its_incident_pages_state_title_and_address(self, planted):
        from modules.heal import incidents as HI

        rows = {**listed(L.page(NET, "open")), **listed(L.page(NET, "closed"))}
        busy = planted["busy"]
        expected = [planted["healed"]["page"], planted["failed"]["page"], busy["page"],
                    busy["related"]]
        assert sorted(rows) == sorted(expected), sorted(rows)
        for iid in expected:
            pg = IP.page(NET, iid, attention={})
            r = rows[iid]
            assert (r["state"], r["title"], r["device"]) == (pg["state"], pg["title"],
                                                             pg["device"]), iid
            assert r["href"] == HI.incident_href(NET, iid, device=pg["device"]), iid
        assert busy["folded"] not in rows

    def test_open_groups_by_what_each_waits_for_and_closed_by_how_it_ended(self, planted):
        p = L.page(NET, "open")
        assert [(g["key"], g["n"], g["open"]) for g in p["groups"]] == [
            ("needs_person", 2, True), ("watching", 1, True)]
        assert (p["total"], p["summary"], p["folded"]) == (3, ["2 needs a person",
                                                               "1 watching"], 1)
        closed = L.page(NET, "closed")
        assert [(g["key"], g["n"]) for g in closed["groups"]] == [("fixed_mercury", 1)]
        (row,) = closed["groups"][0]["rows"]
        assert row["by"] == "Mercury" and row["ttr"] and row["ended"], row
        assert [(t["key"], t["n"]) for t in p["tabs"]] == [("open", 3), ("closed", 1)]

    def test_search_and_the_device_filter_narrow_it(self, planted):
        busy = planted["busy"]
        assert list(listed(L.page(NET, "open", q=busy["related"]))) == [busy["related"]]
        p = L.page(NET, "open", device="edge-b")
        assert sorted(listed(p)) == sorted([planted["failed"]["page"], busy["page"]])
        assert (p["matched"], p["total"]) == (2, 3)
        assert p["devices"] == sorted({"edge-b", "dist-c"}), p["devices"]

    def test_an_unreadable_store_is_said_never_read_as_empty(self, planted):
        tear("decisions")
        p = L.page(NET, "open")
        assert p["unreadable"] and "decisions cannot be read" in p["unreadable"][0]
        body = drawn(p)
        assert "couldn't be read" in body and "may be short" in body
        assert L.open_count(NET)["ok"] is False


class TestPageSpeedAndReads:
    N = 900

    @pytest.fixture
    def fleet(self, client):  # noqa: F811
        """900 incidents, each the healed fixture's records with its ids (the incident's, its
        decisions' and its steps') and its device renamed (a minimal edit of a real capture),
        on 900 devices the fleet scan recognises."""
        text = json.dumps(_load("healed"))
        iid = _load("healed")["page"]
        docs = []
        for n in range(self.N):
            one = re.sub(r"\b(h[ds])-[0-9a-f]{4}([0-9a-f]{8})\b",
                         lambda m, n=n: f"{m.group(1)}-{n:04x}{m.group(2)}", text)
            docs.append(json.loads(one.replace(iid, f"hi-{n:012x}")
                                   .replace("edge-b", f"edg{n:04d}")))
        plant(docs)
        return docs

    def test_900_draw_a_summary_and_closed_groups_and_no_long_list(self, fleet):
        p = L.page(NET, "closed")
        assert (p["total"], [(g["key"], g["n"], g["open"], len(g["rows"]), g["more"])
                             for g in p["groups"]]) == (
            self.N, [("fixed_mercury", self.N, False, L.SHOWN, self.N - L.SHOWN)])
        body = drawn(p)
        assert re.findall(r'<details class="inc-group card" data-group="([a-z_]+)" '
                          r'data-keep="inc-group-\1"( open)?>', body) == [("fixed_mercury", "")]
        assert body.count('class="inc-row"') == L.SHOWN
        assert f"{self.N - L.SHOWN} more: search, or choose a device" in body
        assert len(expanded_devices(body)) <= LIMIT

    def test_one_read_of_each_store_whatever_the_count(self, fleet, monkeypatch):
        from modules.heal import decisions as HD
        from modules.heal import incidents as HI
        from modules.heal import steplog as SL

        calls = {"incidents": 0, "steps": 0, "decisions": 0}
        for key, mod in (("incidents", HI), ("steps", SL), ("decisions", HD)):
            real = mod.read

            def counted(network, _real=real, _key=key):
                calls[_key] += 1
                return _real(network)
            monkeypatch.setattr(mod, "read", counted)
        L.page(NET, "closed")
        assert calls == {"incidents": 1, "steps": 1, "decisions": 1}, calls

    def test_the_routes_are_strict_draw_the_viewer_and_write_nothing(self, planted, client,  # noqa: F811
                                                                     monkeypatch):
        from modules import csp, identity

        before = {p: open(p, "rb").read() for p in _stores().values()}
        for path in ("/v2/incidents", "/v2/incidents/count", "/v2/incidents/heal-mode"):
            r = client.get(f"{path}?list={NET}")
            assert r.status_code == 200, path
            assert r.headers["Content-Security-Policy"] == csp.STRICT_POLICY, path
        assert {p: open(p, "rb").read() for p in _stores().values()} == before
        other = identity.Identity(actor="second@example.invalid", email="second@example.invalid",
                                  kind="person", verified=True, outcome="ok",
                                  peer="198.51.100.7", peer_trusted=True, header_present=True)
        monkeypatch.setattr(identity, "viewer", lambda: other)
        body = client.get(f"/v2/incidents?list={NET}").get_data(as_text=True)
        assert ">second<" in body and "second@example.invalid" not in body
        assert identity.viewer() is other


class TestTheChipsAndTheEmptyList:
    def test_the_chips_say_the_open_count_and_the_mode(self, planted, client):  # noqa: F811
        # Expected through the incident page: the incidents whose page is not resolved.
        ids = [planted["healed"]["page"], planted["failed"]["page"], planted["busy"]["page"],
               planted["busy"]["related"]]
        n = sum(1 for i in ids if not IP.page(NET, i, attention={})["resolved"])
        assert n == 3 and L.open_count(NET) == {"n": n, "ok": True}
        count = client.get(f"/v2/incidents/count?list={NET}").get_data(as_text=True)
        assert re.search(rf">\s*{n} open\s*<", count), count
        # The lab is in dry run (tests/test_heal_decide.py's `lab`): what runs is said.
        from modules.heal import policy
        assert policy.current(NET)["mode"] == "dry_run"
        mode = client.get(f"/v2/incidents/heal-mode?list={NET}").get_data(as_text=True)
        assert re.search(r">\s*Dry run\s*<", mode) and 'title="Self-healing: dry run' in mode

    def test_a_chip_says_a_store_it_cannot_read(self, planted):
        tear("incidents")
        c = L.open_count(NET)
        assert c["ok"] is False
        body = chip(chip="count", c=c, list_name=NET)
        assert "nav-chip-unread" in body and re.search(r">\s*\?\s*<", body)

    def test_an_empty_network_says_so(self, client):  # noqa: F811
        p = L.page(NET, "open")
        assert (p["total"], p["groups"], p["unreadable"]) == (0, [], [])
        body = drawn(p)
        assert f"No incident is open on {NET}." in body and 'class="inc-row"' not in body


def _browser():
    from tests import browser

    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the model's and the template's checks "
                    "above still run")
    return browser


class TestPressedInARealBrowser:
    #: The sidebar as the browser drew it: its headings and its items, in order.
    SIDEBAR = ("return Array.prototype.map.call(document.querySelectorAll("
               "'nav.sidebar .nav-head, nav.sidebar .nav-item > span:first-of-type'),"
               " function (e) { return e.textContent.trim(); })")
    WHERE = "return location.pathname + location.search"

    def test_the_sidebars_troubleshooting_section_opens_its_pages(self, planted):
        browser = _browser()
        import app as APP

        with browser.Served(APP.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url(f"/v2/devices?list={NET}"))
                before = b.wait_for(self.SIDEBAR)
                b.click('nav.sidebar a.nav-item[href^="/v2/incidents"]')
                landed = b.wait_for("return location.pathname === '/v2/incidents' &&"
                                    " document.querySelector('.inc-list-sum') &&"
                                    " [location.search, document.querySelector("
                                    "'nav.sidebar a.nav-item.active span').textContent,"
                                    " document.querySelector('.inc-list-sum').textContent"
                                    ".trim()]")
                count = b.wait_for("var c = document.getElementById('incidents-count');"
                                   " return c && /open/.test(c.textContent)"
                                   " && c.textContent.trim()")
                b.click('nav.sidebar a.nav-item[href*="tab=heal"]')
                heal = b.wait_for("return location.pathname.indexOf('/v2/settings/network/')"
                                  " === 0 && " + self.WHERE[7:])
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        heads = [s for s in before if s.isupper()]
        assert heads[:2] == ["TROUBLESHOOTING", "OBSERVE"], before
        section = before[before.index("TROUBLESHOOTING") + 1:before.index("OBSERVE")]
        assert section == ["Incidents", "Self-healing"], section
        assert landed[1] == "Incidents" and landed[2].startswith("3 open"), landed
        assert count == "3 open"
        assert heal == f"/v2/settings/network/{NET}?tab=heal", heal

    def test_a_row_opens_its_incident_whose_breadcrumb_leads_back_and_search_narrows(
            self, planted):
        browser = _browser()
        import app as APP

        healed, busy = planted["healed"]["page"], planted["busy"]
        with browser.Served(APP.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url(f"/v2/incidents?list={NET}"))
                b.wait_for("return document.querySelector('.inc-list-sum')")
                b.click('nav.tabs a[data-tab="closed"]')
                b.wait_for("return /tab=closed/.test(location.search) &&"
                           " document.querySelector('.inc-row')")
                b.click(f'li[data-incident="{healed}"] a.inc-row-title')
                on_page = b.wait_for(
                    f"return location.pathname === '/v2/incident/{healed}' &&"
                    " Array.prototype.map.call(document.querySelectorAll("
                    "'nav.crumbs a'), function (a) { return a.textContent.trim(); })")
                b.click('nav.crumbs a[href*="tab=closed"]')
                back = b.wait_for("return location.pathname === '/v2/incidents' &&"
                                  " Array.prototype.map.call(document.querySelectorAll("
                                  "'.inc-row'), function (r) { return r.dataset.incident; })")
                b.go(srv.url(f"/v2/incidents?list={NET}"))
                b.wait_for("return document.getElementById('inc-q')")
                b.type("#inc-q", busy["related"])
                b.click(".inc-list-filter button[type=submit]")
                found = b.wait_for("return /q=/.test(location.search) &&"
                                   " Array.prototype.map.call(document.querySelectorAll("
                                   "'.inc-row'), function (r) { return r.dataset.incident; })")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        assert on_page == ["Incidents", "Closed"], on_page
        assert back == [healed], back
        assert found == [busy["related"]], found
