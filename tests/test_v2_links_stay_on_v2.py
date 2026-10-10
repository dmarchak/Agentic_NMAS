"""C569: a v2 page or result never sends a person to today's (v1) pages, except a labelled
"today's page" link that names its cutover gap (tests/todays_page_links.py).

The operator's walk, 2026-10-08: after a deploy, the result's "Back to Coverage" and the
Coverage tab opened today's page. Both links were right; the Coverage page raised, and the
app's error handler redirected every failed navigation to today's index. So there are three
checks: the links in every v2 template (results and parts included, rendered or not), the
links on every rendered v2 page in a real browser, and a failing v2 request answered on v2.

A NAVIGATION is an `<a href>` or a `<form>`'s action (a request a page makes for its own data
is `test_page_requests_resolve`'s). A target is v1 when it resolves to a route outside `/v2/`
and is not a static file; an external URL (Grafana, a documentation link) is neither.
"""

import os
import re

import pytest

from tests.source_index import tracked

from tests import todays_page_links as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAG = re.compile(r"<(a|form)\b([^>]*)>", re.S)
TARGET = re.compile(r"""\b(?:href|action)="([^"]*)\"""")
URL_FOR = re.compile(r"""url_for\(\s*'([^']+)'""")
GAP = re.compile(r"""\bdata-todays-page="([^"]*)\"""")


def _rules():
    import app as A
    return {r.endpoint: r.rule for r in A.app.url_map.iter_rules()}


def _is_v1(target: str, rules: dict) -> bool:
    m = URL_FOR.search(target)
    if m:
        rule = rules.get(m.group(1), "")
        return bool(rule) and not rule.startswith("/v2") and not rule.startswith("/static")
    return (target.startswith("/") and not target.startswith("//")
            and not target.startswith("/v2") and not target.startswith("/static"))


def _element_text(text: str, start: int, kind: str) -> str:
    """The words a person reads for the element opening at *start*: an `<a>`'s content, or a
    form's submit button."""
    if kind == "a":
        end = text.find("</a>", start)
        return re.sub(r"<[^>]+>|\{[{%#].*?[}%#]\}", " ", text[start:end])
    end = text.find("</form>", start)
    body = text[start:end if end > 0 else len(text)]
    buttons = re.findall(r"<button[^>]*type=\"submit\"[^>]*>(.*?)</button>", body, re.S)
    return " ".join(buttons)


def scan(text: str, rules: dict, path: str = "") -> list:
    """``[(path, line, problem)]`` for every v1 navigation in *text* not labelled as a gap."""
    out = []
    for m in TAG.finditer(text):
        kind, attrs = m.group(1), m.group(2)
        t = TARGET.search(attrs)
        if not t or not _is_v1(t.group(1), rules):
            continue
        line = text.count("\n", 0, m.start()) + 1
        gap = GAP.search(attrs)
        if not gap:
            out.append((path, line, f"<{kind}> to {t.group(1)!r} is a v1 route with no "
                                    "data-todays-page naming its cutover gap"))
        elif gap.group(1) not in T.GAPS:
            out.append((path, line, f"data-todays-page={gap.group(1)!r} is no listed gap"))
        elif "today's" not in _element_text(text, m.end(), kind):
            out.append((path, line, f"<{kind}> to {t.group(1)!r} does not say \"today's\" "
                                    "in the words a person reads"))
    return out


def _templates():
    return tracked("templates/v2", suffix=".html")


class TestEveryV2Template:
    def test_no_unlabelled_link_to_today_s_pages(self):
        rules, problems, links = _rules(), [], 0
        for f in _templates():
            text = open(f, encoding="utf-8").read()
            rel = os.path.relpath(f, ROOT)
            problems += [f"{p}:{n}: {why}" for p, n, why in scan(text, rules, rel)]
            links += len(TAG.findall(text))
        assert links >= 150, links          # a floor; measured 2026-10-08: 182
        assert not problems, "\n".join(problems)

    def test_every_listed_gap_is_used_and_the_list_only_shrinks(self):
        used = set()
        for f in _templates():
            used |= set(GAP.findall(open(f, encoding="utf-8").read()))
        assert used == set(T.GAPS), (sorted(set(T.GAPS) - used), sorted(used - set(T.GAPS)))
        assert len(T.GAPS) <= T.CEILING
        # Tight, never slack: a closed gap lowers the ceiling in the same change (C629).
        assert len(T.GAPS) == T.CEILING, f"a gap closed: lower CEILING to {len(T.GAPS)}"

    def test_the_scan_names_each_planted_case(self, monkeypatch):
        """The control: an unlabelled v1 link, a label naming no gap, a labelled link whose
        words do not say so, and a form to a v1 route; a v2 link and a static file pass. The
        list is empty now, so the listed gap is planted too."""
        monkeypatch.setitem(T.GAPS, "planted", "a planted gap")
        rules = _rules()
        planted = ("<a href=\"{{ url_for('index') }}\">Logs</a>\n"
                   "<a data-todays-page=\"nope\" href=\"/\">x today's</a>\n"
                   "<a data-todays-page=\"planted\" href=\"{{ url_for('index') }}\">Logs</a>\n"
                   "<form method=\"get\" action=\"{{ url_for('index') }}\">"
                   "<button type=\"submit\">Go</button></form>\n"
                   "<a href=\"{{ url_for('v2.coverage') }}\">Coverage</a>\n"
                   "<a href=\"/static/x.css\">x</a>\n"
                   "<a data-todays-page=\"planted\" href=\"{{ url_for('index') }}\">Logs "
                   "<small>today's page</small></a>\n")
        got = [(n, why) for _p, n, why in scan(planted, rules)]
        assert [n for n, _w in got] == [1, 2, 3, 4], got
        assert "no data-todays-page" in got[0][1] and "is no listed gap" in got[1][1]
        assert "does not say" in got[2][1] and "<form>" in got[3][1]


def test_the_sidebar_s_logs_and_dhcp_say_what_is_there():
    """C633: today's page had neither screen. C652 (the operator, 2026-10-10): Logs opens the
    queryable logs, the network's syslog by device, never Mercury's own log (that stays in
    Settings › Installation › Diagnostics); DHCP is not built and says so, going nowhere."""
    import app as A
    html = A.app.test_client().get("/v2/monitoring").get_data(as_text=True)
    side = html[html.index('<nav class="sidebar"'):html.index("</nav>", html.index("sidebar"))]
    logs = re.search(r'<a class="nav-item" href="([^"]+)"[^>]*>(?:(?!</a>).)*<span>Logs</span>'
                     r'</a>', side, re.S)
    assert logs and logs.group(1) == "/v2/logs"
    assert "diag-log" not in side and "the app&#39;s own" not in side
    dhcp = re.search(r'<span class="nav-item nav-off" aria-disabled="true"[^>]*>.*?<span>DHCP'
                     r'</span><small class="nav-todays">not built yet</small></span>', side, re.S)
    assert dhcp, "DHCP is drawn as a link, or without saying it is not built"
    assert "today's page" not in side and "today&#39;s page" not in side


class TestAFailedV2RequestStaysOnV2:
    """The shape that sent the walk to today's page: a v2 page that raises."""

    @pytest.fixture
    def failing(self, monkeypatch):
        import app as A
        from routes import v2

        def boom():
            raise ValueError("no reporting rule for 'planted'")
        monkeypatch.setattr(v2, "_coverage", boom)
        A.app.config["PROPAGATE_EXCEPTIONS"] = False
        return A.app.test_client()

    def test_a_navigation_is_answered_on_v2_with_its_status(self, failing):
        r = failing.get("/v2/monitoring/coverage", headers={"Accept": "text/html"})
        html = r.get_data(as_text=True)
        assert r.status_code == 500, (r.status_code, r.headers.get("Location"))
        assert "Location" not in r.headers
        assert "Couldn't load: GET /v2/monitoring/coverage failed with an unexpected " \
               "error: ValueError: no reporting rule for &#x27;planted&#x27;" in html, html
        assert 'href="/v2/"' in html
        assert "'unsafe-inline'" not in r.headers["Content-Security-Policy"]

    def test_an_htmx_part_gets_the_notice_alone(self, failing):
        r = failing.get("/v2/monitoring/coverage/table",
                        headers={"Accept": "text/html", "HX-Request": "true"})
        html = r.get_data(as_text=True)
        assert r.status_code == 500 and html.startswith('<div class="notice notice-danger"')

    def test_today_s_pages_keep_their_redirect(self, failing, monkeypatch):
        """A v1 navigation that fails is unchanged (today's pages draw the flash)."""
        import app as A

        def boom(*a, **k):
            raise ValueError("planted")
        monkeypatch.setitem(A.app.view_functions, "monitoring_config", boom)
        r = failing.get("/monitoring/config", headers={"Accept": "text/html"})
        assert r.status_code == 302


LINKS_JS = """
var out = [];
document.querySelectorAll('a[href], form[action]').forEach(function (e) {
  var raw = e.getAttribute(e.tagName === 'A' ? 'href' : 'action');
  var u;
  try { u = new URL(raw, location.href); } catch (x) { return; }
  if (u.origin !== location.origin) return;
  var p = u.pathname;
  if (p.indexOf('/v2/') === 0 || p === '/v2' || p.indexOf('/static/') === 0) return;
  var gap = e.getAttribute('data-todays-page');
  var words = e.tagName === 'A' ? e.textContent
      : Array.prototype.map.call(e.querySelectorAll('button[type=submit]'),
                                 function (b) { return b.textContent; }).join(' ');
  if (!gap || words.indexOf("today's") < 0)
    out.push(e.tagName.toLowerCase() + ' to ' + p + ' (' + words.trim().slice(0, 60) + ')'
             + (gap ? ' says nothing of today' : ' has no data-todays-page'));
  else out.push('GAP ' + gap);
});
return out;
"""


def test_every_rendered_v2_page_in_a_real_browser(served):  # noqa: F811
    """The crawl: every page the layout test draws, with its parts loaded."""
    from tests.test_v2_layout_in_a_browser import PAGES
    srv, b = served
    problems, gaps = [], set()
    for page in PAGES:
        b.go(srv.url(page))
        b.wait_for("return !!window.Alpine && !document.querySelector('.htmx-request')", 10)
        for line in b.js(LINKS_JS):
            if line.startswith("GAP "):
                gaps.add(line[4:])
            else:
                problems.append(f"{page}: {line}")
    assert not problems, "\n".join(problems)
    assert gaps <= set(T.GAPS), gaps - set(T.GAPS)
    # No page links to today's pages at all since C633 (2026-10-10): the sidebar's Logs and
    # DHCP, on every page, say what is there.
    assert not gaps, gaps
    # The planted case, on a real page: an unlabelled link to today's index is named.
    b.js("var a=document.createElement('a'); a.href='/'; a.textContent='Planted';"
         "document.body.appendChild(a); return 1")
    assert any("to / (Planted) has no data-todays-page" in p for p in b.js(LINKS_JS))


def test_capture_s_edit_intent_opens_the_v2_editor(served):  # noqa: F811
    """Capture's "Edit intent…" opened today's intent editor; it opens v2's, as its link
    loads it (with r2's intent committed, as on the layout lab)."""
    from tests.test_next_steps_act import OPENERS
    srv, b = served
    b.go(srv.url("/v2/device/r2?tab=intent&edit=1"))
    b.wait_for(f"return !!({OPENERS['intent_edit']})", 15)


from tests.test_profile_apply import lab  # noqa: E402,F401 (the fixture)
from tests.test_v2_layout_in_a_browser import served  # noqa: E402,F401 (the fixture)
