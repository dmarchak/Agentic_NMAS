"""Troubleshooting › Incidents and the sidebar's Troubleshooting section (board T,
~/Documents/nmas-reports/boards/troubleshooting-nav.html; the GUI review's proposal 17 and its
finding IN9; provisional, operator review pending, the operator 2026-11-13).
`modules/incidents_list.py`, `routes/incidents_v2.py`, `templates/v2/incidents.html`,
`templates/v2/_heal_auto_chip.html`, and the sidebar and top bar in `templates/v2/base.html`.

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
  long expanded list (test_large_fleets' scan).
- **The top bar's Self-healing chip** (the operator, 2026-11-14: "a status chip in the top bar
  beside the AI chip, shown only while Auto is in force ... Nothing in the normal state"):
  nothing in dry run, off, an expired Auto or under the stop switch; in Auto, amber, "Self-
  healing: Auto until" the expiry in the viewer's zone by the clock (UTC on hover), linking to
  the network's Self-healing tab, reading itself again once at the expiry; several networks
  say how many and name the soonest; an unreadable answer is said.
- **Pressed, in Firefox** (where one runs; skipped naming why elsewhere): the sidebar's
  Troubleshooting section is above OBSERVE with the board's two entries and no chip, and each
  opens its page; on the list, Closed, a row's title, the incident page's breadcrumb back to
  its tab, and the search narrowing the rows; the Auto chip drawn beside the AI chip, before
  it (after it on a phone), at 1440, 1280 and 500 px, inside the bar, without moving it.
"""
import json
import os
import re
import time

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
    # Premise corrected (measured 2026-11-18: rolled_back() on this branch leaves its incident
    # STANDING, 7d54cf24 and C3870, so tests/fixtures/incident_page/failed.json, re-captured
    # from it for its walks test, is open): the rolled-back heal its STORE closed, which these
    # tests hold on Closed as "Closed, not confirmed" (C3876), is the capture taken before
    # C3870, kept as closed_unconfirmed.json, unchanged.
    docs = {n: _load(f) for n, f in (("healed", "healed"), ("failed", "closed_unconfirmed"),
                                     ("busy", "busy"))}
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
        """C3876 (the operator, 2026-11-16): the tabs follow the incidents store, so the
        rolled-back heal its capture holds closed (closed before C3870 kept such an incident
        open) is on Closed, "Closed, not confirmed", never Open and never Fixed."""
        p = L.page(NET, "open")
        assert [(g["key"], g["n"], g["open"]) for g in p["groups"]] == [
            ("needs_person", 1, True), ("watching", 1, True)]
        assert (p["total"], p["summary"], p["folded"]) == (2, ["1 needs a person",
                                                               "1 watching"], 1)
        closed = L.page(NET, "closed")
        assert [(g["key"], g["n"]) for g in closed["groups"]] == [("fixed_mercury", 1),
                                                                  ("closed_unconfirmed", 1)]
        (row,) = closed["groups"][0]["rows"]
        assert row["by"] == "Mercury" and row["ttr"] and row["ended"], row
        (past,) = closed["groups"][1]["rows"]
        assert past["id"] == planted["failed"]["page"], past
        assert [(t["key"], t["n"]) for t in p["tabs"]] == [("open", 2), ("closed", 2)]

    def test_search_and_the_device_filter_narrow_it(self, planted):
        """The filters narrow each tab (the failed capture is on Closed since C3876)."""
        busy = planted["busy"]
        assert list(listed(L.page(NET, "open", q=busy["related"]))) == [busy["related"]]
        p = L.page(NET, "open", device="edge-b")
        assert sorted(listed(p)) == [busy["page"]]
        assert (p["matched"], p["total"]) == (1, 2)
        assert sorted(listed(L.page(NET, "closed", device="edge-b"))) == sorted([
            planted["healed"]["page"], planted["failed"]["page"]])
        assert p["devices"] == sorted({"edge-b", "dist-c"}), p["devices"]

    def test_an_unreadable_store_is_said_never_read_as_empty(self, planted):
        tear("decisions")
        p = L.page(NET, "open")
        assert p["unreadable"] and "decisions cannot be read" in p["unreadable"][0]
        body = drawn(p)
        assert "couldn't be read" in body and "may be short" in body
        # Premise corrected (board T, 2026-11-14: the sidebar's open count removed with
        # `open_count`): the nearest live read, the rows every count was made from, says the
        # store it could not read, never a count of none.
        assert any("decisions cannot be read" in u for u in L.rows(NET)["unreadable"])


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
        for path in ("/v2/incidents", "/v2/incidents/heal-auto"):
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


CHIP = "/v2/incidents/heal-auto"


def auto_on(now=None, hours=2):
    """Auto confirmed on the lab's network by a person, from *now* for *hours* (the policy's
    own writer, tests/test_heal_policy.py's `auto`): its expiry as the policy now reads it.

    The switch-on's retry (`heal.retry.run_soon`, its own thread: the operator, 2026-11-16,
    "switched on, every open incident whose fixes failed is tried again once") is recorded,
    not started, as tests/test_heal_switch_batch.py records it: these tests hold the chip, and
    a retry thread on a planted standing incident outlived its test into the next one's store
    (measured 2026-11-18, -n 2: test_a_chip_says_a_store_it_cannot_read's teardown found
    lists/default/heal/incidents.json.lock, its setup log "Default's retry (switched_on)
    failed: Refused: no heal incident hi-… is held")."""
    from modules.heal import policy, retry
    from tests.test_heal_policy import auto

    now = time.time() if now is None else now
    retries = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(retry, "run_soon",
                   lambda network, trigger, **kw: retries.append(dict(kw, trigger=trigger)))
        auto(NET, now=now, hours=hours)
    return policy.current(NET)


def chip_of(client) -> str:  # noqa: F811
    r = client.get(f"{CHIP}?list={NET}")
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


class TestTheAutoChip:
    def test_nothing_is_drawn_in_dry_run_or_off(self, client):  # noqa: F811
        from modules.heal import policy

        # The lab is in dry run (tests/test_heal_decide.py's `lab`).
        assert policy.current(NET)["mode"] == "dry_run"
        assert chip_of(client).strip() == ""
        policy.turn_off(NET, actor="op@example.com", actor_verified="access")
        assert policy.current(NET)["mode"] == "off"
        assert chip_of(client).strip() == ""

    def test_in_auto_it_is_amber_says_until_in_local_time_and_opens_the_tab(self, client):  # noqa: F811
        cur = auto_on()
        assert cur["mode"] == "auto", cur["words"]
        body = chip_of(client)
        link = re.search(r'<a class="heal-auto-chip" href="([^"]+)"[^>]*>(.*?)</a>', body, re.S)
        assert link, body
        # C3748 (the operator, 2026-11-15): the chip opens the control strip for its network,
        # where Self-healing and AI troubleshooting are switched. Premise corrected (C3789,
        # the operator, 2026-11-15: "remove it from Needs attention; keep it only on
        # Incidents"): it opened Needs attention's strip before.
        assert link.group(1) == f"/v2/incidents?list={NET}#control-strip"
        words = link.group(2)
        assert re.sub(r"<[^>]+>", "", words).startswith("Self-healing: Auto until ")
        # The expiry is the policy's own, drawn by THE clock: its instant in `datetime`, the
        # UTC on its hover, the words in the viewer's zone.
        stamp = re.search(r'<time class="clock" datetime="([^"]+)"[^>]*title="([^"]+)"', words)
        assert stamp and stamp.group(1) == cur["until"], (stamp and stamp.group(1), cur["until"])
        assert "UTC" in stamp.group(2)
        # It reads itself again once, at the expiry.
        delay = int(re.search(r'hx-trigger="load delay:(\d+)s"', body).group(1))
        assert 2 * 3600 - 120 <= delay <= 2 * 3600 + 2, delay
        # Amber: the warn tokens, which have their dark values (tests/test_v2_theme.py).
        css = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "css",
                                "nmas-v2.css"), encoding="utf-8").read()
        rule = re.search(r"^\.heal-auto-chip \{(.*?)\}", css, re.S | re.M).group(1)
        assert "var(--warn-soft)" in rule and "var(--warn)" in rule and "var(--warn-line)" in rule

    def test_an_auto_not_in_force_draws_nothing(self, client):  # noqa: F811
        from modules.heal import policy

        expired = auto_on(now=time.time() - 3 * 3600, hours=1)
        assert (expired["mode"], expired["expired"]) == ("dry_run", True)
        assert chip_of(client).strip() == ""
        auto_on()
        assert policy.current(NET)["mode"] == "auto"
        policy.stop(actor="op@example.com", actor_verified="access", why="a test")
        assert policy.current(NET)["mode"] == "off"
        assert chip_of(client).strip() == ""

    def test_several_networks_in_auto_say_how_many_and_name_the_soonest(self, monkeypatch):
        from modules import integration_groups
        from modules.heal import policy
        from tests.test_heal_policy import iso

        now = time.time()
        held = {"A": {"mode": "auto", "until": iso(now + 7200)},
                "B": {"mode": "dry_run", "until": ""},
                "C": {"mode": "auto", "until": iso(now + 600)}}
        monkeypatch.setattr(integration_groups, "network_names", lambda: list(held))
        monkeypatch.setattr(policy, "current", lambda net, now=None, kill=None: held[net])
        got = L.heal_auto(now)
        assert (got["on"], got["network"], got["until"], got["n"], got["networks"]) == (
            True, "C", held["C"]["until"], 2, ["C", "A"])
        assert got["reread_s"] in (600, 601)
        import app as APP
        from flask import render_template
        with APP.app.test_request_context(f"{CHIP}?list={NET}"):
            body = render_template("v2/_heal_auto_chip.html", a=dict(got, error=""))
        assert "Self-healing: Auto on 2 networks until" in re.sub(r"<[^>]+>", "", body)
        # C3748: the chip opens the soonest network's control strip, on Incidents since C3789
        # (premise corrected: on Needs attention before).
        assert 'href="/v2/incidents?list=C#control-strip"' in body and "on C, A:" in body

    @staticmethod
    def _chip(monkeypatch, held, now):
        from modules import integration_groups
        from modules.heal import policy

        monkeypatch.setattr(integration_groups, "network_names", lambda: list(held))
        monkeypatch.setattr(policy, "current", lambda net, now=None, kill=None: held[net])
        got = L.heal_auto(now)
        import app as APP
        from flask import render_template
        with APP.app.test_request_context(f"{CHIP}?list={NET}"):
            return got, render_template("v2/_heal_auto_chip.html", a=dict(got, error=""))

    def test_until_off_chip_does_not_poll(self, monkeypatch):
        """The correctness review's G4-D4: an Auto with no expiry ("until turned off",
        cd0aa4cc) stores ``until`` empty; the chip read it as ending now, re-read itself every
        second in every open tab, and said "until at an unrecorded time"."""
        now = time.time()
        got, body = self._chip(monkeypatch, {"A": {"mode": "auto", "until": ""}}, now)
        assert (got["auto"], got["network"], got["reread_s"]) == (True, "A", 0), got
        assert "load delay" not in body and "hx-get" not in body, body
        words = re.sub(r"<[^>]+>", "", body)
        assert "unrecorded time" not in words and "Self-healing: Auto until turned off" in \
            words, words

    def test_an_auto_with_an_expiry_comes_before_one_until_turned_off(self, monkeypatch):
        from tests.test_heal_policy import iso

        now = time.time()
        held = {"A": {"mode": "auto", "until": ""}, "C": {"mode": "auto", "until": iso(now + 600)}}
        got, body = self._chip(monkeypatch, held, now)
        assert (got["network"], got["networks"]) == ("C", ["C", "A"]), got
        assert got["reread_s"] in (600, 601), got
        assert 'hx-trigger="load delay:60' in body, body

    def test_a_mode_that_cannot_be_read_is_said(self, client, monkeypatch):  # noqa: F811
        """The route's own answer when the read raises (called in a request, its template
        drawn): said, never drawn as nothing."""
        import app as APP
        from routes import incidents_v2

        def unreadable(now=None):
            raise OSError("the registry")
        monkeypatch.setattr(L, "heal_auto", unreadable)
        with APP.app.test_request_context(f"{CHIP}?list={NET}"):
            body = incidents_v2.heal_auto().get_data(as_text=True)
        assert "Self-healing: mode not known" in body and "could not be read (OSError)" in body


class TestTheChipsAndTheEmptyList:
    def test_the_chips_say_the_open_count_and_the_mode(self, planted, client):  # noqa: F811
        """Premise corrected (the operator, 2026-11-14, board T: "Remove the 'N open' chip from
        Incidents in the sidebar ... no Self-healing chip in the sidebar at all; the sidebar is
        navigation only. Instead, a status chip in the top bar"; the name predates it): the
        sidebar draws no count chip and no mode chip, whatever is open, and the top bar's chip
        says the mode, from the policy itself: nothing in dry run, "Auto until" in Auto."""
        from modules.heal import policy
        page = client.get(f"/v2/incidents?list={NET}").get_data(as_text=True)
        nav = page.split('<nav', 1)[1].split('</nav>', 1)[0]
        assert L.page(NET, "open")["total"] >= 1, "incidents are open"
        assert "nav-chip" not in nav and not re.search(r">\s*\d+ open\s*<", nav), nav
        assert policy.current(NET)["mode"] == "dry_run" and L.heal_auto()["auto"] is False
        assert chip_of(client).strip() == ""
        cur = auto_on()
        assert cur["mode"] == "auto" and L.heal_auto()["network"] == NET
        assert "Self-healing: Auto until " in re.sub(r"<[^>]+>", "", chip_of(client))

    def test_a_chip_says_a_store_it_cannot_read(self, planted, client, monkeypatch):  # noqa: F811
        """Premise corrected (board T, the operator 2026-11-14: the sidebar's chips removed;
        the name predates it): the top bar's chip, its store unreadable (the installation's
        settings, where the stop switch is kept), says so, never drawn as nothing."""
        from modules.config import SettingsUnreadable
        from modules.heal import policy

        def torn(*_a, **_k):
            raise SettingsUnreadable("user_settings.json: torn")
        monkeypatch.setattr(policy, "stopped", torn)
        with pytest.raises(SettingsUnreadable):
            L.heal_auto()
        before = {k: open(p, "rb").read() for k, p in _stores().items()}
        body = chip_of(client)
        assert {k: open(p, "rb").read() for k, p in _stores().items()} == before, \
            "the chip's read wrote nothing"
        assert "Self-healing: mode not known" in body and "could not be read" in body, body

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
                # Navigation only: each item of the section is its icon and its label (the
                # operator, 2026-11-14: no chip on either).
                kids = b.js("return Array.prototype.map.call(document.querySelectorAll("
                            "'nav.sidebar a.nav-item[href^=\"/v2/incidents\"],"
                            " nav.sidebar a.nav-item[href*=\"tab=heal\"]'), function (a) {"
                            " return Array.prototype.map.call(a.children, function (c) {"
                            " return c.tagName.toLowerCase(); }).join(' '); })")
                # Premise corrected (board T, 2026-11-14: the sidebar's "N open" chip removed):
                # the open count is the page's own Open tab's, read in the browser.
                count = b.wait_for("var t = document.querySelector('a.tab[data-tab=open]');"
                                   " return t && t.textContent.trim()")
                b.click('nav.sidebar a.nav-item[href*="tab=heal"]')
                heal = b.wait_for("return location.pathname.indexOf('/v2/settings/network/')"
                                  " === 0 && " + self.WHERE[7:])
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        heads = [s for s in before if s.isupper()]
        assert heads[:2] == ["TROUBLESHOOTING", "OBSERVE"], before
        section = before[before.index("TROUBLESHOOTING") + 1:before.index("OBSERVE")]
        # Premise corrected (measured 2026-11-18: templates/v2/base.html draws Troubleshooting ›
        # Fixes between them, C3849, board fixes-list approved by the operator 2026-11-16).
        assert section == ["Incidents", "Fixes", "Self-healing"], section
        # Premise corrected (C3876, the operator, 2026-11-16: the rolled-back heal its store
        # closed is on Closed, as TestTheRows holds: 2 open; measured 2026-11-18 in Firefox:
        # "2 open · 1 needs a person · 1 watching").
        assert landed[1] == "Incidents" and landed[2].startswith("2 open"), landed
        assert kids == ["svg span", "svg span"], kids
        assert count == "Open · 2", count
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
                # Board R5 (approved 2026-11-15): the search sits behind one "Search or
                # filter…" link, opened by a person's press before it is typed into.
                b.click("details.inc-search > summary")
                b.wait_for("return document.querySelector('details.inc-search').open")
                b.type("#inc-q", busy["related"])
                b.click(".inc-list-filter button[type=submit]")
                found = b.wait_for("return /q=/.test(location.search) &&"
                                   " Array.prototype.map.call(document.querySelectorAll("
                                   "'.inc-row'), function (r) { return r.dataset.incident; })")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        assert on_page == ["Incidents", "Closed"], on_page
        # Premise corrected (C3876, the operator, 2026-11-16: the tabs follow the store, so the
        # rolled-back heal its store closed is on Closed, "Closed, not confirmed", after the
        # heal Mercury fixed; measured 2026-11-18 in Firefox: the two rows in that order).
        assert back == [healed, planted["failed"]["page"]], back
        assert found == [busy["related"]], found


class TestTheAutoChipInARealBrowser:
    """In Firefox: in Auto the chip is drawn in the top bar just before the AI chip, inside the
    bar and the screen, amber, at 1440, 1280 and 500 px (its words above 1366 px, "Auto" alone
    up to it), and the AI chip is where it is without it (the bar read once nothing in it is
    still changing)."""

    #: The boxes read: the chip's, the AI chip's, the bar's, the screen's width and the words
    #: the chip shows (its visible part).
    BOXES = ("var w = window, d = document, c = d.querySelector('#nmas-heal-auto .heal-auto-chip'),"
             " ai = d.getElementById('nmas-ai'), bar = d.querySelector('header.topbar');"
             " if (!c || !ai || /reading/.test(ai.textContent)) return null;"
             " function box(e) { var r = e.getBoundingClientRect();"
             " return [r.left, r.right, r.top, r.bottom]; }"
             " var shown = Array.prototype.filter.call(c.children, function (k) {"
             " return k.getBoundingClientRect().width > 1; }).map(function (k) {"
             " return k.textContent.trim(); });"
             " return {chip: box(c), ai: box(ai), bar: box(bar), width: w.innerWidth,"
             " shown: shown, bg: getComputedStyle(c).backgroundColor,"
             " warn: (function () { var p = d.createElement('span');"
             " p.style.background = 'var(--warn-soft)'; d.body.appendChild(p);"
             " var v = getComputedStyle(p).backgroundColor; p.remove(); return v; })()};")
    #: The bar once nothing in it is still changing: every item's box and the Live word, read
    #: twice 0.3 s apart and equal (Live's word and the strip's arrive on their own).
    BAR = ("return JSON.stringify([Array.prototype.map.call(document.querySelectorAll("
           "'header.topbar > *'), function (e) { var r = e.getBoundingClientRect();"
           " return [r.left, r.right]; }), document.querySelector('.live-word').textContent])")
    REMOVE = "document.getElementById('nmas-heal-auto').innerHTML = ''; return 1"
    AI = ("var r = document.getElementById('nmas-ai').getBoundingClientRect();"
          " return [r.left, r.right, r.top, r.bottom];")

    def settled(self, b, bound=10.0):
        """The bar (`BAR`) once two reads 0.3 s apart agree; fails naming the reads."""
        reads, deadline = [b.js(self.BAR)], time.monotonic() + bound
        while True:
            time.sleep(0.3)
            reads.append(b.js(self.BAR))
            if reads[-1] == reads[-2]:
                return reads[-1]
            if time.monotonic() > deadline:
                raise AssertionError(f"the top bar did not settle within {bound} s: {reads}")

    #: A desktop, a laptop (the bar full: 5 px free at 1280, measured 2026-11-14) and a phone
    #: (500 px, the narrowest window geckodriver makes; tests/browser.py).
    @pytest.mark.parametrize("width", [1440, 1280, 500])
    def test_it_is_before_the_ai_chip_inside_the_bar_and_moves_nothing(self, client, width):  # noqa: F811
        browser = _browser()
        import app as APP

        cur = auto_on()
        assert cur["mode"] == "auto"
        with browser.Served(APP.app) as srv, browser.Browser() as b:
            try:
                b._call("POST", f"/session/{b.session}/window/rect",
                        {"width": width, "height": 900})
                b.go(srv.url(f"/v2/devices?list={NET}"))
                b.wait_for(self.BOXES, 15)
                bar_with = self.settled(b)
                got = b.js(self.BOXES)
                b.js(self.REMOVE)
                bar_without = self.settled(b)
                without = b.js(self.AI)
                got["items"] = (bar_with, bar_without)
                # Pressed, it opens the control strip for the network. Premise
                # corrected (C3748, the operator, 2026-11-15: "a top-bar status chip only while
                # Auto or the AI toggle is on, opening the strip"): it opened Settings ›
                # Self-healing before the strip. Premise corrected again (C3789, the operator,
                # 2026-11-15: "keep it only on Incidents"): Troubleshoot › Incidents' strip,
                # its Self-healing switch on it, where Needs attention's was before.
                b.go(srv.url(f"/v2/devices?list={NET}"))
                b.wait_for("return !!document.querySelector('#nmas-heal-auto .heal-auto-chip')",
                           15)
                b.click("#nmas-heal-auto a.heal-auto-chip")
                opened = b.wait_for("return location.pathname === '/v2/incidents' && "
                                    "!!document.querySelector('#control-strip [data-ctl=heal]')"
                                    " && location.pathname + location.search + location.hash",
                                    15)
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
        assert opened == f"/v2/incidents?list={NET}#control-strip", opened
        auto, ai, bar = got["chip"], got["ai"], got["bar"]
        assert got["width"] == width, got
        if width > 640:
            # Just before the AI chip, the bar's gap between them.
            assert auto[1] <= ai[0] <= auto[1] + 17, f"the chip is not before the AI chip: {got}"
        else:
            # A phone's bar is packed from the left: just after it, so it never moves it.
            assert ai[1] <= auto[0] <= ai[1] + 17, f"the chip is not after the AI chip: {got}"
        assert bar[0] <= auto[0] and auto[1] <= got["width"], f"outside the bar: {got}"
        assert bar[2] <= auto[2] and auto[3] <= bar[3], f"outside the bar's height: {got}"
        assert all(abs(a - b) < 0.5 for a, b in zip(ai, without)), (
            f"the AI chip moved: {ai} with the chip, {without} without; the bar's items "
            f"(left, right) with and without: {got['items']}")
        # Nothing in the bar runs past the screen with the chip drawn.
        boxes = [x for x in __import__("json").loads(got["items"][0])[0] if x[1] > x[0]]
        assert max(r for _l, r in boxes) <= got["width"], got["items"][0]
        assert got["bg"] == got["warn"], f"not amber: {got['bg']} against {got['warn']}"
        if width > 1366:
            assert len(got["shown"]) == 1 and got["shown"][0].startswith(
                "Self-healing: Auto until "), got["shown"]
        else:
            # Up to 1366 px "Auto" alone, as Update says "Update" (its words on hover).
            assert got["shown"] == ["Auto"], got["shown"]
