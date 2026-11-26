"""Every setting has a home, and Settings finds it (Stage 5 step 2: "a test that every setting is
still reachable"; the operator's GUI pick of 2026-11-25, C: "one searchable document").

- Every setting a person may set (`settings_index.settable`: the network's and the host's keys
  in `settings_scope.SCOPES`, a floor on how many) has exactly one home, a page, a tab and a
  section, or is declared set by no screen with why (`NO_SCREEN`, each declaration used).
- Each home's page, fetched for a network, draws the section its home names: the link a search
  gives lands on the setting.
- The search finds a setting by its words and links its home; it matches every word, finds
  nothing for nothing typed, and counts what it does not draw.
- In a real browser: typed into the box, the matches arrive under it, and pressing one opens
  the page at the section, below the sticky bar.

Through the real app, routes and templates, on tests/test_settings_v2.py's store.
"""
import re

from tests.test_settings_v2 import _get, live_browser, networks, served  # noqa: F401 (fixtures)

def _index():
    """The index, imported by each test (so a tree without it fails each test, red)."""
    from modules import settings_index
    return settings_index


def test_every_setting_has_one_home_or_says_why_none():
    X = _index()
    keys = X.settable()
    assert len(keys) >= 200, len(keys)          # 210 on 2026-11-25: 108 a network's, 102 the host's
    none, groups_none = [], set()
    for k in keys:
        h = X.home(k)
        if "none" in h:
            assert h["none"], f"{k}: set by no screen and no why"
            none.append(k)
            groups_none.add(h["group"])
        else:
            assert h["page"] in (X.NETWORK, X.INSTALLATION, X.SDN, X.CREDENTIALS), (k, h)
            assert h["tab"] and h["section"], (k, h)
    assert groups_none == set(X.NO_SCREEN), "every group declared set by no screen is one"
    # The gaps, named exactly (C4266): a setting a person cannot set in Mercury joins this
    # test's own words, never the index's alone. The others are set by no screen by design.
    gaps = {g for g, why in X.NO_SCREEN.items() if why.startswith("C")}
    assert gaps == {"ai_read_account", "no_change_windows"}, gaps
    assert len(none) <= 8, none


def test_each_home_draws_its_section(networks):  # noqa: F811
    X = _index()
    from modules.settings_scope import scope_of
    import app as A
    with A.app.test_request_context("/"):
        homes = {}
        for k in X.settable():
            h = X.home(k)
            if "none" not in h:
                homes.setdefault(X.href(h, "Branch"), []).append(k)
    assert len(homes) >= 40, len(homes)
    pages = {}
    for href, keys in sorted(homes.items()):
        path, section = href.split("#")
        if path not in pages:
            assert path.startswith("/v2/"), path
            r, pages[path] = _get(networks, f"/v2/{path[4:]}")
            assert r.status_code == 200, (path, r.status_code)
        assert re.search(rf'\bid="{re.escape(section)}"', pages[path]), \
            (f"{href} draws no section {section!r} for", keys, [scope_of(k) for k in keys])


def test_find_matches_every_word_and_links_the_home(networks):  # noqa: F811
    X = _index()
    _r, html = _get(networks, "/v2/settings/find?q=deploy+workers&at=Branch")
    assert '"deploy workers" matches 1 setting: 1 in Settings › Branch › Network.' in html
    want = X.home("deploy_max_workers")
    assert want["section"] == "card-deploy_max_workers"
    assert ('<a href="/v2/settings/network/Branch?tab=network#card-deploy_max_workers" '
            'title="deploy_max_workers">Deploy max workers</a>') in html
    import app as A
    with A.app.test_request_context("/"):
        heal = X.find("heal", "Branch")
    assert heal["count"] >= 20, heal["count"]                 # 30 on 2026-11-25
    _r, html = _get(networks, "/v2/settings/find?q=heal&at=Branch")
    assert f'"heal" matches {heal["count"]} settings' in html
    assert 'href="/v2/settings/network/Branch?tab=heal#heal-guards"' in html
    _r, html = _get(networks, "/v2/settings/find?q=&at=Branch")
    assert html.strip() == "", "nothing typed, nothing drawn"
    _r, html = _get(networks, "/v2/settings/find?q=zzqx+nothing&at=Branch")
    assert 'No setting matches "zzqx nothing"' in html


def test_a_setting_no_screen_sets_is_found_saying_so(networks):  # noqa: F811
    X = _index()
    _r, html = _get(networks, "/v2/settings/find?q=no+change+windows&at=Branch")
    why = X.home("no_change_windows")["none"]
    assert why.startswith("C4266"), "the gap names its register row"
    row = re.search(r"<li>(.*?)</li>", html, re.S).group(1)
    assert "set by no screen" in row and f'<span class="set-origin">{why}</span>' in row
    assert "href=" not in row, "a setting no screen sets links nowhere"


def test_a_long_answer_is_counted_never_drawn_whole(networks):  # noqa: F811
    X = _index()
    import app as A
    _r, html = _get(networks, "/v2/settings/find?q=e&at=Branch")
    with A.app.test_request_context("/"):
        everything = X.find("e", "Branch")
    assert everything["count"] > X.MOST and everything["shown"] == X.MOST
    assert html.count("<li>") == everything["shown"]
    assert (f'"e" matches {everything["count"]} settings' in html
            and f"The first {everything['shown']} are below; add a word to narrow it." in html)


def test_in_a_browser_a_typed_word_finds_the_setting_and_its_link_opens_it(served):  # noqa: F811
    """A person types into Find a setting on Branch's Integrations tab: the matches arrive under
    the box, and pressing Deploy max workers opens the Network tab at its section, its top
    below the sticky top bar."""
    b, srv = served["b"], served["srv"]
    b._call("POST", f"/session/{b.session}/window/rect", {"width": 1366, "height": 900})
    b.go(srv.url("/v2/settings/network/Branch?tab=integrations"))
    b.wait_for("return !!window.Alpine && !!window.htmx", 15)
    b.type("#set-find-q", "deploy workers")
    b.wait_for("return !!document.querySelector('#set-found .set-found a')", 15)
    got = b.js("return Array.from(document.querySelectorAll('#set-found .set-found a'))"
               ".map(function(a){return [a.textContent, a.getAttribute('href')];})")
    assert got == [["Deploy max workers",
                    "/v2/settings/network/Branch?tab=network#card-deploy_max_workers"]], got
    b.click("#set-found .set-found a")
    b.wait_for("return location.search.indexOf('tab=network') >= 0 && "
               "!!document.getElementById('card-deploy_max_workers')", 15)
    where = b.js("var s=document.getElementById('card-deploy_max_workers').getBoundingClientRect(),"
                 " t=document.querySelector('.topbar').getBoundingClientRect();"
                 " return {hash: location.hash, top: s.top, bar: t.bottom, inner: innerHeight};")
    assert where["hash"] == "#card-deploy_max_workers", where
    assert where["bar"] <= where["top"] < where["inner"], ("in view, below the bar", where)
