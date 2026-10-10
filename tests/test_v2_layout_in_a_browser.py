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


def _timeline(ref, f, members):
    """The History page's timeline (C369) at its widest: a denied decision's long words, a
    Save All naming nine devices, a long person, a known-wrong record."""
    nine = ["r1", "r2", "r3", "r4", "r6", "s1", "s2", "s3", "s4"]
    return {"events": [
        {"at": "2026-10-02T08:00:00Z", "kind": "decision", "what": f"Baseline {DENIED} (save_all)",
         "devices": [], "devices_words": "fleet", "marks": [], "outcome": "denied",
         "who": "a-person-with-a-long-name@example.com",
         "who_short": "a-person-with-a-long-name@example.com",
         "detail": "golden: 9 device(s) via save_all, the whole fleet read at once after the lab "
                   "redeploy, every capture compared with its intent",
         "sha": "abc0def" + "0" * 33, "record": [("Baseline", DENIED)]},
        {"at": "2026-10-02T07:59:00Z", "kind": "golden", "what": "Golden recorded (save_all)",
         "devices": nine, "devices_words": "9 devices", "marks": ["record known wrong"],
         "exception": LONG_NOTE, "outcome": "",
         "who": "a-person-with-a-long-name@example.com (host login, not verified)",
         "who_short": "a-person-with-a-long-name@example.com", "detail": "golden: 9 device(s)",
         "sha": "abc1def" + "0" * 33, "record": []}],
        "errors": [], "cut": [], "limit": 50, "total": 2, "people": [], "counts": {}}


def _history(ref, dev, limit=None):
    return {"events": [
        {"at": "2026-10-01T16:58:00Z", "kind": "restart", "what": "Restarted as planned",
         "devices": ["r2"], "devices_words": "r2",
         "marks": ["corrected", "acknowledged", "crash file"],
         "who": "a-person-with-a-long-name@example.com (host login, not a verified identity)",
         "who_short": "a-person-with-a-long-name@example.com", "correction": LONG_NOTE,
         "detail": "reason: Reload Command; planned: lab redeploy", "sha": "",
         "outcome": "planned"}], "errors": [], "cut": [], "limit": 50, "total": 1}


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
    monkeypatch.setattr(v2, "_history_timeline", _timeline)
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
            "ci": {"tip": "b" * 40, "state": "verified"},
            # The reader's shape since C436: the target is the newest commit CI passed.
            "verdicts": {"b" * 40: {"tip": "b" * 40, "state": "verified"}},
            "target": "b" * 40}}}}
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
         "/v2/device/r2?tab=intent&edit=1",
         "/v2/device/r2?tab=history", "/v2/device/r2?tab=monitoring", "/v2/device/r2?tab=logs",
         "/v2/device/r2?tab=netbox", "/v2/device/r2?tab=neighbours", "/v2/history",
         "/v2/history?tab=baselines", "/v2/history?tab=authorisations", "/v2/monitoring",
         "/v2/monitoring/coverage", "/v2/help/about", "/v2/update", "/v2/settings",
         "/v2/settings/installation", "/v2/help/records-database",
         "/v2/settings/installation?tab=server", "/v2/help/installation-settings",
         "/v2/settings/installation?tab=ai",
         "/v2/templates", "/v2/templates?bring=_common.j2", "/v2/monitoring/profile",
         "/v2/monitoring/profile?propose=1", "/v2/device/r2?tab=ask",
         "/v2/device/r2?tab=ask&command=show%20ip%20route", "/v2/show-commands"]

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


class TestTheFilterBarIsOneHeight:
    def test_show_is_as_tall_as_the_fields_beside_it(self, served):
        """History's filter bar (the operator, 2026-10-05: "the Show button is taller than the
        filter fields beside it"): the button and every field stand the same height, their
        bottoms aligned."""
        srv, b = served
        b.go(srv.url("/v2/history"))
        b.wait_for("return document.querySelector('form.dev-filters .btn')", 10)
        got = b.js(
            "var f=document.querySelector('form.dev-filters'), out=[];"
            "f.querySelectorAll('select, .hist-kinds-sum, input[type=search], .btn').forEach("
            "function(e){var r=e.getBoundingClientRect();"
            "out.push([e.tagName + '.' + (e.className||''), Math.round(r.height), Math.round(r.bottom)]);});"
            "return out;")
        heights = {h for _n, h, _b in got}
        bottoms = {bt for _n, _h, bt in got}
        assert len(got) >= 4, got
        assert len(heights) == 1, f"the bar's controls differ in height: {got}"
        assert max(bottoms) - min(bottoms) <= 1, f"their bottoms do not align: {got}"


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

    def test_a_long_decision_stays_one_line_with_the_whole_of_it_under_its_row(self, served):
        """The timeline's line is one line (C369): a denied decision's 80-character words run to
        the What cell's edge and no further; the whole decision opens under the row."""
        srv, b = served
        b.go(srv.url("/v2/history"))
        b.wait_for("return document.querySelector('.hist-tl .hist-sum')", 10)
        h = b.js("var s=document.querySelector('.hist-tl .hist-sum'); return [s.getBoundingClientRect()"
                 ".height, s.querySelector('.hist-what').getBoundingClientRect().height]")
        assert h[0] < 40 and h[1] < 30, h
        assert b.js("return document.querySelectorAll('.hist-tl .hist-sum')[1]"
                    ".querySelector('.hist-dev').textContent.trim()") == "9 devices"
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


#: C502 (the operator, 2026-10-05: the Templates table's first column touched the card's left
#: border). Every drawn table's first cell: its text starts at least TABLE_GAP_PX inside the
#: nearest box that draws a left border (a card, an op card, the table itself). Returns one line
#: per table that does not, and the number of tables read.
TABLE_GAP_PX = 8
FIRST_COLUMN_JS = """
var out=[], n=0;
document.querySelectorAll('table').forEach(function(t){
  if (!t.offsetParent) return;
  var row=t.querySelector('tbody tr') || t.querySelector('tr'); if (!row || !row.cells[0]) return;
  var cell=row.cells[0], box=null;
  for (var p=t; p && p!==document.body; p=p.parentElement){
    var cs=getComputedStyle(p);
    if (parseFloat(cs.borderLeftWidth)>0 && cs.borderLeftStyle!=='none'){box=p; break;}
  }
  if (!box) return;
  n++;
  var edge=box.getBoundingClientRect().left + parseFloat(getComputedStyle(box).borderLeftWidth);
  var text=cell.getBoundingClientRect().left + parseFloat(getComputedStyle(cell).paddingLeft);
  if (text - edge < %d) out.push((t.className||'table')+': its first column starts '
    + Math.round(text-edge)+' px inside '+(box.className||box.tagName));
});
return [out, n];
""" % TABLE_GAP_PX

#: C509 (the operator, 2026-10-05: the Revert card's "Commit to revert" dropdown ran past the
#: card and the page on a long commit subject). Every drawn form control and button ends inside
#: the card holding it. Returns one line per control that does not, and the number read.
CONTROLS_INSIDE_JS = """
var out=[], n=0;
document.querySelectorAll('select, textarea, input:not([type=hidden]), button, .btn').forEach(function(e){
  if (!e.offsetParent) return;
  var card=e.closest('.card, .op-card'); if (!card) return;
  n++;
  var R=card.getBoundingClientRect().right, r=e.getBoundingClientRect();
  if (r.right > R + 1) out.push(e.tagName.toLowerCase()+(e.name ? '[name='+e.name+']' : '')
    +' ends at '+Math.round(r.right)+', past its card at '+Math.round(R)
    +': '+(e.textContent||e.value||'').trim().slice(0, 40));
});
return [out, n];
"""


#: C566 (the operator, 2026-10-07: board B's "What changes" ran past the table's right edge).
#: Every drawn table cell and `pre` ends inside the card holding it, or inside a scroller
#: (overflow-x auto or scroll) that itself ends inside the card: long template and config lines
#: wrap or scroll in place, never past the card. Returns one line per element that does not,
#: and the number read.
CELLS_INSIDE_JS = """
var out=[], n=0;
document.querySelectorAll('td, th, pre').forEach(function(e){
  if (!e.offsetParent) return;
  var card=e.closest('.card, .op-card'); if (!card) return;
  n++;
  // A card that scrolls its own content (`.tpl-card`) keeps a wide table inside it, in place.
  var cx=getComputedStyle(card).overflowX;
  if (cx === 'auto' || cx === 'scroll') return;
  var m=e, p=e.parentElement;
  while (p && p !== card) {
    var ox=getComputedStyle(p).overflowX;
    if (ox === 'auto' || ox === 'scroll' || ox === 'hidden') { m=p; break; }
    p=p.parentElement;
  }
  // The CONTENT's extent, not the box's: a pre's box stays inside the card while its text runs
  // past it. A scroller ends at its own edge; anything else at its left plus its scroll width.
  var R=card.getBoundingClientRect().right, r=m.getBoundingClientRect();
  var own=getComputedStyle(e).overflowX;
  var right=(m !== e || own === 'auto' || own === 'scroll') ? r.right : r.left + e.scrollWidth;
  if (right > R + 1) out.push(e.tagName.toLowerCase()+(m !== e ? ' (in its scroller)' : '')
    +' ends at '+Math.round(right)+', past its card at '+Math.round(R)
    +': '+(e.textContent||'').trim().replace(/\\s+/g, ' ').slice(0, 40));
});
return [out, n];
"""


#: C505 and the operator's check (2026-10-05): every DRAWN "How does this work?" sits right after
#: the control it documents (the nearest drawn element before it carries data-op naming the
#: link's page), and no control has two (a drawn help link before it is a second one). A control
#: hidden until some state (Update's Stop waiting) leaves its link beside whatever is drawn.
#: Returns one line per link that breaks it, and the number read.
HELP_BESIDE_JS = """
var out=[], n=0;
function shown(e){ return e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden'; }
function name(e){ return e.tagName.toLowerCase() + (e.id ? '#'+e.id : '')
  + ' "' + (e.textContent||'').trim().replace(/\\s+/g, ' ').slice(0, 30) + '"'; }
document.querySelectorAll('a.how-link').forEach(function(a){
  if (!shown(a)) return;
  n++;
  var slug=(a.getAttribute('data-manual')||'').split('#')[0], p=a.previousElementSibling;
  while (p && !shown(p)) p=p.previousElementSibling;
  var words=a.getAttribute('aria-label') || (a.textContent||'').trim();
  // Beside a HEADING (an op card's or a card's head row): it documents the card, not a control.
  var head=a.closest('.op-hd, .card-head');
  if (!p && head && head.querySelector('h1, h2, h3')) return;
  if (!p) out.push(words+' ('+slug+'): no control is drawn before it');
  else if (p.matches('a.how-link, a.info-link')) out.push(words+' ('+slug+'): a second help '
    + 'link beside the same control, after '+((p.getAttribute('aria-label')||p.textContent||'').trim()));
  else if (p.getAttribute('data-op') !== slug) out.push(words+' ('+slug+'): beside '+name(p)
    + ', which documents '+(p.getAttribute('data-op') || 'nothing'));
});
return [out, n];
"""


#: C503's rule (the operator, 2026-10-06; NSOT_GUI_BRIEF 10b): "How does this work?" in words
#: ONCE per context. A card (`.card`, `.op-card`) that draws any such link draws exactly one in
#: words (beside its heading, or its one standalone button), the rest the (i) alone; a menu's
#: rows the (i) alone; a standalone button outside any card or menu the words. Links in a card
#: nested inside another card belong to the inner one. Returns one line per context or link
#: that breaks it, and the number of contexts read.
HELP_CONTEXT_JS = """
var out=[], cards=new Map(), n=0;
function shown(e){ return e.getClientRects().length > 0 && getComputedStyle(e).visibility !== 'hidden'; }
function label(e){ var h=e.querySelector('h1, h2, h3');
  return (e.id ? '#'+e.id+' ' : '') + '"' + ((h ? h.textContent : e.className)||'').trim()
    .replace(/\\s+/g, ' ').slice(0, 40) + '"'; }
document.querySelectorAll('a.how-link').forEach(function(a){
  if (!shown(a)) return;
  var words=!a.classList.contains('compact'), slug=(a.getAttribute('data-manual')||'').split('#')[0];
  var menu=a.closest('[role=menu]'), card=a.closest('.op-card, .card');
  if (menu && (!card || card.contains(menu))) {
    if (words) out.push('a menu row carries the words ('+slug+')');
    return;
  }
  if (!card) {
    if (!words) out.push('a standalone (i) outside any card or menu ('+slug+')');
    return;
  }
  var c=cards.get(card) || {words: 0, icons: 0}; c[words ? 'words' : 'icons']++; cards.set(card, c);
});
cards.forEach(function(c, card){
  n++;
  if (c.words === 0) out.push(label(card)+': no "How does this work?" in words, '+c.icons+' (i) alone');
  else if (c.words > 1) out.push(label(card)+': "How does this work?" in words '+c.words+' times');
});
return [out, n];
"""


#: The contexts that broke C503's rule when it was written (2026-10-06), kept on screen as they
#: are until the operator decides (register C522): each a lone (i) in a card with no words.
#: Matched on the problem's text; the list may only shrink (`test_the_known_gaps_only_shrink`).
C503_KNOWN_GAPS = (
    '#intent "Editing',                     # the intent editor's card (_intent_edit.html)
    '#hist-baselines ',                     # History's baselines card (history.html:83)
    '#installation "About this installation"',   # _installation.html:27
    '#card-',                               # each Settings card (_settings_card.html:59)
    'a standalone (i) outside any card or menu (settings-switch)',   # the switch's choice
    '#update-owed "Still to do on the host"',    # _update.html:136
    '#update-preview "Update from',         # Update while waiting: its worded link hides
    '"card tpl-card"',                      # the Templates table (_templates_table.html)
)
C503_GAPS_CEILING = 8


def measure_help_links(b, page_label):
    """``(problems, links)`` for the page *b* shows, every <details> open: each drawn help link
    beside its control (C505) and the words once per context (C503), less its known gaps."""
    b.js("document.querySelectorAll('details').forEach(function(d){d.open=true}); return 1")
    got, n = b.js(HELP_BESIDE_JS)
    ctx, _contexts = b.js(HELP_CONTEXT_JS)
    ctx = [p for p in ctx if not any(g in p for g in C503_KNOWN_GAPS)]
    return [f"{page_label}: {p}" for p in got + ctx], n


def test_the_known_gaps_only_shrink():
    assert len(C503_KNOWN_GAPS) <= C503_GAPS_CEILING


def test_the_context_rule_fails_each_way_on_a_planted_page(served):
    """The rule's three failures and its passes, planted in a page the browser draws: a card
    with no words, a card with words twice, a menu row with words, a standalone (i)."""
    srv, b = served
    b.go(srv.url("/v2/help/about"))
    b.wait_for("return !!window.Alpine", 10)
    w = '<a class="how-link" data-manual="deploy" href="#"><span>How does this work?</span></a>'
    i = '<a class="how-link compact" data-manual="deploy" href="#"></a>'
    b.js("var m=document.createElement('div'); m.id='planted'; m.innerHTML=arguments[0];"
         "document.querySelector('main').appendChild(m); return 1",
         f'<section class="card" id="p-none"><h2>None</h2><button>Go</button>{i}</section>'
         f'<section class="card" id="p-twice"><h2>Twice</h2>{w}<button>Go</button>{w}</section>'
         f'<section class="card" id="p-once"><h2>Once</h2>{w}<button>Go</button>{i}</section>'
         f'<div role="menu"><a role="menuitem">Row</a>{w}</div>'
         f'<p><button>Alone</button>{i}</p>')
    got, _n = b.js(HELP_CONTEXT_JS)
    planted = [p for p in got if "#p-" in p or "menu row" in p or "standalone (i)" in p]
    assert any('#p-none' in p and "no " in p for p in planted), got
    assert any('#p-twice' in p and "2 times" in p for p in planted), got
    assert not any('#p-once' in p for p in planted), got
    assert any("a menu row carries the words" in p for p in planted), got
    assert any("a standalone (i) outside any card or menu (deploy)" in p for p in planted), got


class TestEveryHelpLinkSitsBesideItsControl:
    def test_the_nearest_drawn_control_is_the_one_its_page_documents(self, served):
        srv, b = served
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1366, "height": 1000})
        problems, links = [], 0
        for page in PAGES:
            b.go(srv.url(page))
            b.wait_for("return !!window.Alpine && !document.querySelector('.htmx-request')", 10)
            got, n = measure_help_links(b, page)
            problems += got
            links += n
        assert not problems, "\n".join(problems)
        assert links >= 5, links


def measure_layout(b, page_label):
    """Both measurements on the page *b* shows, every <details> open: ``(problems, tables,
    controls)``."""
    b.js("document.querySelectorAll('details').forEach(function(d){d.open=true}); return 1")
    tables, n_tables = b.js(FIRST_COLUMN_JS)
    controls, n_controls = b.js(CONTROLS_INSIDE_JS)
    cells, _n_cells = b.js(CELLS_INSIDE_JS)          # C566: every cell and pre inside its card
    return ([f"{page_label}: {p}" for p in tables + controls + cells], n_tables, n_controls)


class TestTablesAndControlsSitInsideTheirCards:
    @pytest.mark.parametrize("width", [1366, 500])
    def test_every_first_column_is_padded_and_every_control_ends_inside(self, served, width):
        srv, b = served
        b._call("POST", f"/session/{b.session}/window/rect", {"width": width, "height": 1000})
        problems, tables, controls = [], 0, 0
        for page in PAGES:
            b.go(srv.url(page))
            b.wait_for("return !!window.Alpine && !document.querySelector('.htmx-request')", 10)
            got, t, c = measure_layout(b, f"{page} at {width}")
            problems += got
            tables += t
            controls += c
        assert not problems, "\n".join(problems)
        # Floors: the population read, so a page that drew nothing cannot pass by emptiness.
        assert tables >= 3 and controls >= 14, (tables, controls)   # measured 2026-10-06: 3, 14


class TestCellsSitInsideTheirCards:
    """C566 (the operator, 2026-10-07): long template and config lines in a table cell or a
    `pre` wrap, or scroll inside their own scroller, and never run past the card."""

    def test_every_cell_and_pre_ends_inside_its_card(self, served):
        srv, b = served
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1366, "height": 1000})
        problems, cells = [], 0
        for page in PAGES:
            b.go(srv.url(page))
            b.wait_for("return !!window.Alpine && !document.querySelector('.htmx-request')", 10)
            b.js("document.querySelectorAll('details').forEach(function(d){d.open=true}); "
                 "return 1")
            got, n = b.js(CELLS_INSIDE_JS)
            problems += [f"{page}: {p}" for p in got]
            cells += n
        assert not problems, "\n".join(problems)
        assert cells >= 70, cells            # a floor; measured 2026-10-07: 77

    def test_the_check_finds_a_planted_overflow(self, served):
        """The planted case: a `pre` with one long unbreakable line, put in a card with no
        wrapping and no scroller, is named; the same `pre` in a scroller is not."""
        srv, b = served
        b._call("POST", f"/session/{b.session}/window/rect", {"width": 1366, "height": 1000})
        b.go(srv.url("/v2/monitoring/coverage"))
        b.wait_for("return !!window.Alpine && !document.querySelector('.htmx-request')", 10)
        b.js("var c=document.querySelector('.card'); var p=document.createElement('pre');"
             "p.id='planted'; p.style.whiteSpace='pre'; p.style.overflow='visible';"
             "p.textContent='x'.repeat(600); c.appendChild(p); return 1")
        got, _n = b.js(CELLS_INSIDE_JS)
        assert any("pre ends at" in g and "xxxx" in g for g in got), got
        b.js("var p=document.getElementById('planted'); var w=document.createElement('div');"
             "w.style.overflowX='auto'; p.parentNode.insertBefore(w, p); w.appendChild(p); "
             "return 1")
        got, _n = b.js(CELLS_INSIDE_JS)
        assert not any("xxxx" in g for g in got), got
