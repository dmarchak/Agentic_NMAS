"""The manual (NSOT_GUI_BRIEF 10 and 10a; the operator, 2026-10-02: "a v2 screen
isn't done until its manual section and info link exist").

Every check reads the population from the program itself, with floors:
- every SIDEBAR destination (read from the rendered v2 frame) has a Screens page;
- every DEVICE-PAGE tab (``routes.device_v2.TABS``) has its section;
- every OPERATION has a How it works page, and every step its code DECLARES
  (``modules.manual.OPERATIONS``) is named on that page, read from the code;
  an operation declaring none is listed with why, and that list only shrinks;
- every INFO LINK in a v2 template names a page and section that exist;
- every v2 PAGE template carries an info link (one exemption, named);
- every page renders, every diagram is used, and the renderer cannot carry
  markup (all text escaped, unknown link forms refused).
The suite runs in CI, so a new screen or operation without its manual fails it.
"""

import os
import re

import pytest

from modules import manual

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(ROOT, "templates", "v2")
INFO_CALL = re.compile(r"info\(\s*'([a-z0-9-]+)'(?:\s*,\s*'([a-z0-9-]*)')?")
#: A v2 page that carries no info link, and why.
NO_INFO = {"not_found.html": "an error page: what it says is the whole of what there is to know"}
#: Operations whose code declares no step list yet (brief 10a's stepper work
#: adds one to each). Only shrinks.
UNDECLARED_CEILING = 5


def _client():
    import app as A
    return A.app.test_client()


def _templates():
    return {f: open(os.path.join(V2, f), encoding="utf-8").read()
            for f in sorted(os.listdir(V2)) if f.endswith(".html")}


def _info_calls(text):
    return [(m.group(1), m.group(2) or "") for m in INFO_CALL.finditer(text)
            if not text[max(0, m.start() - 8):m.start()].endswith("macro ")]


def unresolved(calls):
    """The info calls naming a page or section the manual lacks."""
    bad = []
    for slug, sec in calls:
        try:
            doc = manual.load(slug)
        except manual.ManualError:
            bad.append((slug, sec, "no such page"))
            continue
        if sec and sec not in doc["anchors"]:
            bad.append((slug, sec, "no such section"))
    return bad


class TestEveryPageRenders:
    def test_floor_and_each_renders(self):
        assert len(manual.PAGES) >= 25
        for slug, _t, _g, _f in manual.PAGES:
            doc = manual.load(slug)
            assert doc["title"] and doc["html"], slug

    def test_every_diagram_is_used_and_carries_no_style_or_script(self):
        ddir = os.path.join(manual.MANUAL_DIR, "diagrams")
        names = sorted(f[:-4] for f in os.listdir(ddir) if f.endswith(".svg"))
        assert len(names) >= 4
        used = "".join(manual.source(s) for s, _t, _g, _f in manual.PAGES)
        for n in names:
            assert f"diagrams/{n}.svg" in used, f"{n}.svg is used by no page"
            assert manual.diagram(n).startswith("<svg")

    def test_the_four_concepts_are_drawn(self):
        """The operator: diagrams where the concept is visual."""
        for page, name in (("onboard", "onboarding-flow"), ("getting-started", "baseline-contents"),
                           ("getting-started", "intent-golden-device"),
                           ("getting-started", "merge-vs-replace")):
            assert f"diagrams/{name}.svg" in manual.source(page), (page, name)


class TestTheRendererCarriesNoMarkup:
    def test_text_is_escaped(self):
        out = manual.render("# T\n\nA <script>x</script> and **<b>bold</b>** and `<i>`\n")
        assert "<script>" not in out["html"] and "&lt;script&gt;" in out["html"]
        assert "<b>" not in out["html"] and "<i>" not in out["html"]

    @pytest.mark.parametrize("link", ["[x](https://example.com)", "[x](javascript:alert(1))",
                                      "[x](no-such-page)", "[x](../etc)"])
    def test_an_unknown_link_form_is_refused(self, link):
        with pytest.raises(manual.ManualError):
            manual.render(f"# T\n\n{link}\n")

    def test_the_link_forms_it_takes(self):
        out = manual.render("# T\n\n[a](deploy) [b](deploy#the-run-stage-by-stage) [c](#x) "
                            "[d](/v2/devices)\n")
        for href in ('href="/v2/help/deploy"', 'href="/v2/help/deploy#the-run-stage-by-stage"',
                     'href="#x"', 'href="/v2/devices"'):
            assert href in out["html"]

    def test_a_diagram_with_inline_style_or_script_is_refused(self, tmp_path, monkeypatch):
        (tmp_path / "diagrams").mkdir()
        (tmp_path / "diagrams" / "bad.svg").write_text('<svg><rect style="fill:red"></rect></svg>')
        monkeypatch.setattr(manual, "MANUAL_DIR", str(tmp_path))
        with pytest.raises(manual.ManualError):
            manual.diagram("bad")

    def test_lists_and_sections(self):
        out = manual.render("# T\n\n## One\n\n- a\n  more\n- b\n  1. c\n\n## Two\n\ntext\n")
        assert "<ul><li>a more</li><li>b<ol><li>c</li></ol></li></ul>" in out["html"]
        assert out["anchors"] == ["one", "two"]
        assert "text" not in out["sections"]["one"] and "text" in out["sections"]["two"]


class TestEverySidebarDestinationHasItsPage:
    def _sidebar(self):
        html = _client().get("/v2/help/getting-started").get_data(as_text=True)
        nav = html.split('aria-label="Main"', 1)[1].split("</nav>", 1)[0]
        return re.findall(r'class="nav-item[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span>', nav)

    def test_floor(self):
        labels = self._sidebar()
        assert len(labels) >= 11, labels

    def test_each_has_a_screens_page(self):
        for label in self._sidebar():
            assert label in manual.SCREENS, f"the sidebar's {label!r} has no manual page"
            assert manual.page(manual.SCREENS[label])["group"] == "Screens"

    def test_a_destination_without_a_page_is_found(self):
        """The control: a sidebar label the manual does not declare."""
        assert "Fleet map" not in manual.SCREENS

    def test_every_device_tab_has_its_section(self):
        from routes.device_v2 import TABS
        anchors = manual.load("device-page")["anchors"]
        assert len(TABS) >= 8
        for key, _label in TABS:
            assert key in manual.DEVICE_TABS, f"device tab {key!r} has no manual section"
            assert manual.DEVICE_TABS[key] in anchors, key


class TestEveryOperationIsExplained:
    REQUIRED = ("deploy", "capture", "restore", "removal", "rotate", "persist", "seed",
                "onboard", "adopt", "retire", "monitoring-templates", "update")

    def test_the_operator_s_list_and_a_floor(self):
        """The operator's twelve (2026-10-02), each with a How it works page."""
        assert len(self.REQUIRED) == 12
        for op in self.REQUIRED:
            assert op in manual.OPERATIONS, op
            assert manual.page(op)["group"] == "How it works", op

    def test_every_declared_step_is_named_on_its_page(self):
        checked = 0
        for op in manual.OPERATIONS:
            steps = manual.declared_steps(op)
            text = manual.source(manual.OPERATION_PAGE.get(op, op))
            for key in steps:
                assert f"`{key}`" in text, f"{op}: the code declares step {key!r}; its page " \
                                           "does not name it"
                checked += 1
        assert checked >= 60, checked

    def test_a_step_missing_from_its_page_is_found(self, monkeypatch):
        """The control: a step the code declares and the page does not name."""
        from modules import pipeline
        monkeypatch.setattr(pipeline, "STAGE_NAMES", list(pipeline.STAGE_NAMES) + ["new_stage"])
        missing = [k for k in manual.declared_steps("deploy")
                   if f"`{k}`" not in manual.source("deploy")]
        assert missing == ["new_stage"]

    def test_undeclared_operations_say_why_and_only_shrink(self):
        undeclared = sorted(op for op, ref in manual.OPERATIONS.items() if ref is None)
        assert undeclared == sorted(manual.UNDECLARED)
        assert len(undeclared) <= UNDECLARED_CEILING
        assert all(len(why) >= 20 for why in manual.UNDECLARED.values())


class TestEveryInfoLinkResolves:
    def test_every_call_in_the_templates(self):
        calls = [c for text in _templates().values() for c in _info_calls(text)]
        assert len(calls) >= 18, len(calls)
        assert unresolved(calls) == []

    def test_a_link_to_a_missing_section_is_found(self):
        assert unresolved([("deploy", "no-such-section"), ("no-such-page", "")]) == [
            ("deploy", "no-such-section", "no such section"),
            ("no-such-page", "", "no such page")]

    def test_every_v2_page_carries_one(self):
        pages = {f: t for f, t in _templates().items() if 'extends "v2/base.html"' in t}
        assert len(pages) >= 12
        for f, text in pages.items():
            if f in NO_INFO:
                continue
            assert _info_calls(text), f"{f} has no info link (a v2 screen is not done without one)"
        assert set(NO_INFO) <= set(pages), "an exemption names a page that does not exist"

    def test_every_device_tab_fragment_links_its_section(self):
        texts = _templates()
        for frag, anchor in (("_overview.html", "overview"), ("_intent.html", "intent"),
                             ("_history.html", "history-tab"), ("_monitoring.html", "monitoring-tab"),
                             ("_logs.html", "logs-tab"), ("_netbox.html", "netbox-tab"),
                             ("_neighbours.html", "neighbours")):
            assert ("device-page", anchor) in _info_calls(texts[frag]), frag


class TestTheRoutes:
    def test_every_page_is_served_under_the_strict_policy(self):
        from modules import csp
        c = _client()
        for slug, title, _g, _f in manual.PAGES:
            r = c.get(f"/v2/help/{slug}")
            assert r.status_code == 200, slug
            assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
            html = r.get_data(as_text=True)
            assert f'aria-current="page">{title}</a>' in html.replace("&#39;", "'"), slug
            assert not re.search(r"<script(?! defer src)|\son[a-z]+=", html.split("<main", 1)[1])

    def test_an_unknown_page_is_404(self):
        assert _client().get("/v2/help/no-such-page").status_code == 404

    def test_the_panel_draws_the_section_alone(self):
        r = _client().get("/v2/help/deploy/panel?section=the-run-stage-by-stage")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and "ci_gate" in html
        assert "Many devices at once" not in html and "Before the deploy" not in html
        assert 'href="/v2/help/deploy#the-run-stage-by-stage">Open in Help' in html

    def test_an_unknown_section_is_404_saying_so(self):
        r = _client().get("/v2/help/deploy/panel?section=nope")
        assert r.status_code == 404 and "defect to report" in r.get_data(as_text=True)

    def test_an_info_link_opens_the_panel_and_falls_back_to_the_page(self):
        html = _client().get("/v2/update").get_data(as_text=True)
        link = re.search(r'<a class="info-link"[^>]*>', html).group(0)
        assert 'href="/v2/help/update"' in link and 'hx-get="/v2/help/update/panel"' in link
        assert 'hx-target="#help-panel-body"' in link and 'x-on:click="openHelp"' in link
        assert 'id="help-panel-body"' in html

    def test_the_sidebar_help_opens_the_manual(self):
        html = _client().get("/v2/").get_data(as_text=True)
        assert 'href="/v2/help/getting-started"' in html


class TestTheInfoLinkInARealBrowser:
    """The click, in Firefox (where one runs; skipped naming why elsewhere):
    the info link on the Update page opens the side panel with the Update
    page's How it works, without leaving the page, and Escape closes it."""

    def test_the_panel_opens_with_the_section_and_closes(self):
        from tests import browser
        ok, why = browser.available()
        if not ok:
            pytest.skip(f"no real browser here ({why}); the wiring checks above still run")
        import app as A
        with browser.Served(A.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url("/v2/update"))
                b.wait_for("return !!(window.Alpine && document.querySelector('a.info-link'))")
                assert b.js("var p = document.querySelector('aside.help-panel');"
                            "return p && getComputedStyle(p).display;") == "none"
                b.click("h1 a.info-link")
                b.wait_for("return document.querySelector('#help-panel-body').textContent"
                           ".indexOf('The steps, in order') >= 0")
                assert b.js("return getComputedStyle(document.querySelector("
                            "'aside.help-panel')).display;") != "none"
                assert b.js("return location.pathname;") == "/v2/update"
                b.js("document.body.dispatchEvent(new KeyboardEvent('keydown', "
                     "{key: 'Escape', bubbles: true}));")
                b.wait_for("return getComputedStyle(document.querySelector("
                           "'aside.help-panel')).display === 'none'")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
