"""The v2 pages as a person sees them, in a real browser (Firefox, where one runs; skipped naming
why elsewhere). The operator, 2026-10-02, after 4fe12ea was deployed:

1. History's Baseline column ran past the table's right edge: a whole decision ("denied: r2
   departs …") in a no-wrap badge. The sweep's screenshots missed it because the test lab's
   commits carried no baseline decision, so the column was empty: a fixture that could not
   reach the case. Here every one-line row is drawn with long, realistic text and every cell
   must end inside its row.
2. The "How does this work?" link beside a baseline's Re-apply opened a BLANK panel. The route
   answered with the section, but the Baselines card carries `hx-select` for its own refresh
   and htmx passed it down to every link inside, so the link selected `#hist-baselines` out
   of the manual's answer and swapped in nothing. The manual's checks resolved each link's
   page and section on the server, and the one real click was on the Update page. Here EVERY
   info and how link on every v2 page, every row opened, is clicked, and the panel must fill
   with that link's own section without leaving the page.
3. On a phone the top bar ran past the screen. geckodriver will not make a window narrower
   than 500 CSS px, so the bar is measured in a same-origin frame of each width; the strict
   policy's `frame-ancestors 'none'` is relaxed to `'self'` for this test alone, which
   changes nothing about the layout.
"""

import urllib.error

import pytest

from tests import browser
from tests.test_profile_apply import lab  # noqa: F401 (the fixture)

R2 = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
      "platform": "cisco_iosxe", "role": "router"}
R6 = {"hostname": "r6", "ip": "203.0.113.16", "device_type": "cisco_xe",
      "platform": "cisco_iosxe", "role": "router"}
DENIED = ("denied: r2 departs from its committed intent (+1 -1: load-interval 30 on "
          "GigabitEthernet2, added by hand)")[:88]
LONG_NOTE = ("the redeploy was planned on 2026-10-01 from 15:20 to 17:10 UTC; the tool could "
             "not record a window until 30c2fd4 shipped, so this is recorded late")


def _commits(ref, f):
    rows = []
    for i, (state, words) in enumerate((("denied", DENIED), ("not_taken", "not taken: 7 not targeted"),
                                        ("earned", "earned"), ("unrecorded", "not recorded"))):
        rows.append({"short": f"abc{i}def", "sha": f"abc{i}def" + "0" * 32,
                     "at": "2026-10-02T08:00:00Z",
                     "subject": "golden: 9 device(s) via save_all, the whole fleet read at once "
                                "after the lab redeploy, every capture compared with its intent",
                     "exception": "", "intent_match": "no: r2 (+1 -1)", "devices": ["r2", "r6"],
                     "files": ["golden/r2.cfg", "golden/r6.cfg"], "workflow": "save all",
                     "source": "save_all", "who": "a-person-with-a-long-name@example.com",
                     "how": "verified by Cloudflare Access",
                     "baseline": {"state": state, "words": words,
                                  "tag": "baseline/20261002T080000Z" if state == "earned" else ""}})
    return {"rows": rows, "cut": False, "limit": 100, "error": ""}


def _history(ref, dev, limit=None):
    return {"events": [
        {"at": "2026-10-01T16:58:00Z", "kind": "restart", "what": "Restarted as planned",
         "marks": ["corrected", "acknowledged", "crash file"],
         "who": "a-person-with-a-long-name@example.com (host login, not a verified identity)",
         "who_short": "a-person-with-a-long-name@example.com", "correction": LONG_NOTE,
         "detail": "reason: Reload Command; planned: lab redeploy", "sha": "",
         "outcome": "planned"}], "errors": [], "cut": [], "limit": 50}


BASELINES = {"state": "ok", "doc": {"last_good": {"value_at": "2026-10-02T09:00:00Z", "value": {
    "lists": {"Lab": {"count": 2, "usable": 1, "baselines": [
        {"tag": "baseline/20261001T165800Z", "created": "2026-10-01T16:58:00Z", "withdrawn": False,
         "decision": "denied", "decision_detail": DENIED, "usable": False, "stale": ["r1", "s1"]},
        {"tag": "baseline/20260926T080000Z", "created": "2026-09-26T08:00:00Z", "withdrawn": False,
         "decision": "earned", "usable": True, "stale": []}]}}}}}}

AUTHS = [{"device": "r3", "at": "2026-10-02T07:00:00Z", "actor": "operator@example.com",
          "reason": "Oxidized fetched r3 during the crash and kept a partial config; the next poll "
                    "replaces it", "expired": False, "expires_at": "2026-10-03T07:00:00Z"}]


@pytest.fixture
def served(lab, monkeypatch):  # noqa: F811
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why})")
    from modules import csp, device_page, reader_job
    from routes import v2
    rows = [dict(R2), dict(R6)]
    monkeypatch.setattr("modules.device.load_saved_devices",
                        lambda path=None: [dict(r) for r in rows])
    monkeypatch.setattr(device_page, "history", _history)
    monkeypatch.setattr(v2, "_history_commits", _commits)
    real = reader_job.read_cached
    # An installable update, so the top bar is measured carrying its "Update available"
    # (the widest the bar gets in ordinary use).
    from routes import health
    monkeypatch.setattr(health, "_COMMIT", "a" * 40)
    monkeypatch.setattr("modules.update_op.outcome", lambda: {"value": {}})
    # Its times are NOW's: behind for longer than attention.BEHIND_TOO_LONG_S (20 h) turns the
    # quiet pill into a Needs attention row, and fixed dates made this test pass until
    # 2026-10-03T04:00Z and fail everywhere after (CI #333's runs, measured 2026-10-03).
    import time as _time
    def _iso(ago_s):
        return _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(_time.time() - ago_s))
    pushed = {"state": "ok", "doc": {"stale_after_seconds": 750, "last_good": {
        "value_at": _iso(60), "value": {
            "running": "a" * 40, "tip": "b" * 40, "state": "behind", "behind": 3,
            "branch": "main", "behind_since": _iso(3600),
            "ci": {"tip": "b" * 40, "state": "verified"}}}}}
    stored = {"baseline-usability": BASELINES, "app-pushed": pushed}
    monkeypatch.setattr(reader_job, "read_cached",
                        lambda name: stored[name] if name in stored else real(name))
    monkeypatch.setattr("modules.nsot.freshness.authorisations",
                        lambda ln, include_expired=False: [dict(a) for a in AUTHS])
    # For the frame the top bar is measured in, and nothing else (the module docstring).
    monkeypatch.setattr(csp, "STRICT_POLICY", csp.STRICT_POLICY.replace(
        "frame-ancestors 'none'", "frame-ancestors 'self'"))
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        try:
            yield srv, b
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()


PAGES = ["/v2/", "/v2/devices", "/v2/device/r2", "/v2/device/r2?tab=intent",
         "/v2/device/r2?tab=history", "/v2/device/r2?tab=monitoring", "/v2/device/r2?tab=logs",
         "/v2/device/r2?tab=netbox", "/v2/device/r2?tab=neighbours", "/v2/history",
         "/v2/history?tab=baselines", "/v2/history?tab=authorisations", "/v2/monitoring",
         "/v2/monitoring/coverage", "/v2/help/about", "/v2/update"]

LINKS = "a.info-link, a.how-link"


class TestEveryHelpLinkRenders:
    def test_every_info_and_how_link_fills_the_panel_with_its_own_section(self, served):
        srv, b = served
        clicked, failed = [], []
        for page in PAGES:
            b.go(srv.url(page))
            b.wait_for("return !!(window.Alpine && document.querySelector('#help-panel-body'))")
            b.wait_for("return !document.querySelector('.htmx-request')", 10)
            n = b.js("document.querySelectorAll('details').forEach(function(d){d.open=true});"
                     f"var l=document.querySelectorAll({LINKS!r});"
                     "l.forEach(function(a,i){a.setAttribute('data-sweep', i)}); return l.length")
            for i in range(n):
                want = b.js(f"var a=document.querySelector('[data-sweep=\"{i}\"]');"
                            "if (!a || !a.offsetParent) return null;"
                            "document.querySelector('#help-panel-body').innerHTML='';"
                            "a.scrollIntoView({block: 'center'}); return a.getAttribute('data-manual')")
                if want is None:
                    continue                      # not drawn on this page's state
                try:
                    b.click(f'[data-sweep="{i}"]')
                except urllib.error.HTTPError as e:     # WebDriver's refusal: a person could not either
                    failed.append(f"{page}: {want}: not clickable: {e.read()[:200]!r}")
                    continue
                slug, _h, section = want.partition("#")
                href = f"/v2/help/{slug}" + (f"#{section}" if section else "")
                try:
                    b.wait_for("var p=document.querySelector('#help-panel-body');"
                               "var o=p && p.querySelector('.help-panel-page a');"
                               f"return o && o.getAttribute('href') === {href!r}"
                               " && p.innerText.trim().length > 60", 6)
                except AssertionError:
                    failed.append(f"{page}: {want}")
                assert b.js("return location.pathname + location.search") == page, page
                clicked.append(f"{page}: {want}")
                b.click('.help-panel-head button[aria-label="Close the help"]')   # as a person would
                b.wait_for("return !document.querySelector('.help-panel').offsetParent", 3)
        assert not failed, "help links whose panel stayed empty or showed another section:\n" + \
            "\n".join(failed)
        assert len(clicked) >= 30, clicked          # the measured count is the floor's basis
        assert any("restore" in c and "baselines" in c for c in clicked), \
            "the link this test was written for was not reached"


class TestNoOneLineRowOverflows:
    @pytest.mark.parametrize("width", [1366, 500])
    def test_every_cell_ends_inside_its_row(self, served, width):
        srv, b = served
        b._call("POST", f"/session/{b.session}/window/rect", {"width": width, "height": 1000})
        problems = []
        for page in ("/v2/history", "/v2/history?tab=baselines", "/v2/history?tab=authorisations",
                     "/v2/device/r2?tab=history"):
            b.go(srv.url(page))
            b.wait_for("return document.querySelector('.hist-sum, .tl-sum')", 10)
            got = b.js(
                "var out=[]; document.querySelectorAll('.hist-sum, .tl-sum').forEach(function(s){"
                "var R=s.getBoundingClientRect().right;"
                # Anything DRAWN past the row: a descendant whose box runs on is not drawn there
                # when something between it and the row clips it (a cell's ellipsis).
                "function clipped(e){for (var p=e.parentElement; p && p!==s; p=p.parentElement)"
                " if (getComputedStyle(p).overflowX!=='visible') return true; return false;}"
                "s.querySelectorAll('*').forEach(function(e){if (clipped(e)) return;"
                "var r=e.getBoundingClientRect();"
                "if (r.width && r.right > R + 1) out.push((e.className||e.tagName)+' '+"
                "Math.round(r.right)+'>'+Math.round(R)+': '+(e.textContent||'').slice(0,40));});});"
                "return out;")
            problems += [f"{page} at {width}: {p}" for p in got]
        assert not problems, "\n".join(problems)

    def test_the_baseline_column_is_one_word_with_the_decision_under_its_row(self, served):
        srv, b = served
        b.go(srv.url("/v2/history"))
        b.wait_for("return document.querySelector('.hist-base .badge')", 10)
        assert b.js("return Array.from(document.querySelectorAll('.hist-base .badge'))"
                    ".map(function(e){return e.textContent})") == [
            "denied", "not taken", "earned", "not recorded"]
        assert b.js("return document.querySelector('.hist-base .badge').title") == DENIED
        assert DENIED in b.js("return document.querySelector('.hist-row .hist-detail').textContent")


class TestTheTopBarFits:
    @pytest.mark.parametrize("width", [320, 360, 390, 430, 500, 768, 1024, 1280])
    def test_every_item_on_the_screen_and_the_avatar_shown(self, served, width):
        srv, b = served
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1200, "height": 900})
        b.go(srv.url("/v2/devices"))
        b.wait_for("return !!window.Alpine", 10)
        b.js(f"var f=document.createElement('iframe'); f.id='phone'; f.width='{width}';"
             "f.height='700'; f.style.position='fixed'; f.style.left='0'; f.style.top='0';"
             "f.style.maxWidth='none'; f.style.border='0'; f.style.zIndex='9999';"
             "f.src=location.href; document.documentElement.appendChild(f);")
        b.wait_for("var d=document.getElementById('phone').contentDocument;"
                   "return d && d.querySelector('.topbar #nmas-strip .strip-item')"
                   " && d.querySelector('.topbar .update-pill')", 15)
        got = b.js(
            "var w=document.getElementById('phone').contentWindow, d=w.document;"
            "var bar=d.querySelector('.topbar'), W=w.innerWidth, out=[];"
            "Array.from(bar.children).forEach(function(e){var r=e.getBoundingClientRect();"
            "if (w.getComputedStyle(e).display!=='none' && r.right > W + 0.5)"
            " out.push((e.className||e.tagName)+' ends at '+Math.round(r.right)+' of '+W);});"
            "var who=d.getElementById('nmas-who').getBoundingClientRect();"
            "var jump=d.querySelector('.jump').getBoundingClientRect();"
            "var pill=d.querySelector('.update-pill').getBoundingClientRect();"
            "return {inner: W, over: out, scroll: d.documentElement.scrollWidth,"
            " who: [Math.round(who.left), Math.round(who.right), who.width],"
            " jump: Math.round(jump.width), pill: [Math.round(pill.right), pill.width]};")
        assert got["inner"] == width, got
        assert not got["over"], got
        assert got["who"][2] > 0 and got["who"][1] <= width, ("the avatar is not on the screen", got)
        assert got["jump"] >= 60, ("the search box gave way to nothing usable", got)
        assert got["pill"][1] > 0 and got["pill"][0] <= width, ("Update available not shown", got)
