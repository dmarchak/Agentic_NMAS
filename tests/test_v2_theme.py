"""The redesign's dark mode (the operator, 2026-09-30): a System/Light/Dark
choice, applied before the first paint, every colour a token with a dark
counterpart, and the charts drawn in the theme on screen.

The shipped `nmas_theme.js` and `nmas_panels.js` are executed in duktape
against stub browsers (storage that works, that throws, a system that prefers
dark), never re-implemented here.
"""

import json
import os
import re

import dukpy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = os.path.join(ROOT, "static", "css", "nmas-v2.css")


def _js(name):
    return open(os.path.join(ROOT, "static", "js", name), encoding="utf-8").read()


STUB = """
var attrs = {}, events = [];
var store = %(store)s;
var window = {
  localStorage: %(storage)s,
  matchMedia: function (q) { return {matches: %(dark)s, addEventListener: function () {}}; },
  document: {
    documentElement: {
      setAttribute: function (k, v) { attrs[k] = v; },
      removeAttribute: function (k) { delete attrs[k]; }
    },
    createEvent: function () { return {initCustomEvent: function (t, b, c, d) { this.type = t; this.detail = d; }}; },
    dispatchEvent: function (e) { events.push([e.type, e.detail.theme]); }
  }
};
"""
WORKING = "{getItem: function (k) { return store[k] === undefined ? null : store[k]; }, setItem: function (k, v) { store[k] = v; }}"
THROWING = "{getItem: function () { throw new Error('blocked'); }, setItem: function () { throw new Error('blocked'); }}"


def _run(expr, store=None, storage=WORKING, dark=False):
    src = STUB % {"store": json.dumps(store or {}), "storage": storage, "dark": "true" if dark else "false"}
    return dukpy.evaljs(src + _js("nmas_theme.js") + f"\nJSON.stringify({expr});")


class TestTheChoice:
    def test_the_effective_theme_for_each_choice(self):
        got = json.loads(_run("[window.NMAS_THEME.effective('system', false), "
                              "window.NMAS_THEME.effective('system', true), "
                              "window.NMAS_THEME.effective('light', true), "
                              "window.NMAS_THEME.effective('dark', false), "
                              "window.NMAS_THEME.effective('purple', true)]"))
        assert got == ["light", "dark", "light", "dark", "dark"]

    def test_a_saved_dark_is_on_the_page_before_anything_else_runs(self):
        assert json.loads(_run("attrs", store={"nmas.theme": "dark"})) == {"data-theme": "dark"}

    def test_system_sets_nothing_so_the_stylesheet_follows_the_device(self):
        assert json.loads(_run("attrs", store={"nmas.theme": "system"}, dark=True)) == {}
        assert json.loads(_run("window.NMAS_THEME.current()", dark=True)) == "dark"

    def test_a_saved_value_that_is_not_a_choice_is_system(self):
        assert json.loads(_run("[attrs, window.NMAS_THEME.get()]", store={"nmas.theme": "neon"})) == [{}, "system"]

    def test_blocked_storage_follows_the_system_and_a_choice_still_applies(self):
        got = json.loads(_run("[window.NMAS_THEME.get(), window.NMAS_THEME.set('dark'), attrs]",
                              storage=THROWING))
        assert got == ["system", "dark", {"data-theme": "dark"}]

    def test_a_choice_is_stored_applied_and_announced(self):
        snap = "JSON.parse(JSON.stringify(%s))"
        got = json.loads(_run("[window.NMAS_THEME.set('light'), " + ", ".join(snap % v for v in ("store", "attrs", "events"))
                              + ", window.NMAS_THEME.set('system'), " + ", ".join(snap % v for v in ("attrs", "events")) + "]",
                              dark=True))
        assert got[0] == "light" and got[1] == {"nmas.theme": "light"}
        assert got[2] == {"data-theme": "light"}
        assert got[3][0] == ["nmas:theme", "light"]
        assert got[5] == {} and got[6][-1] == ["nmas:theme", "dark"]


def _blocks():
    css = open(CSS, encoding="utf-8").read()
    light = re.search(r"^:root \{(.*?)^\}", css, re.S | re.M).group(1)
    media = re.search(r":root:not\(\[data-theme=\"light\"\]\) \{(.*?)\}", css, re.S).group(1)
    forced = re.search(r"^:root\[data-theme=\"dark\"\] \{(.*?)^\}", css, re.S | re.M).group(1)
    return css, light, media, forced


def _tokens(block):
    return dict(re.findall(r"(--[\w-]+):\s*([^;]+);", block))


class TestTheTokens:
    def test_every_colour_token_has_a_dark_value_in_both_dark_blocks(self):
        _, light, media, forced = _blocks()
        lt = {k for k, v in _tokens(light).items() if re.match(r"#|rgba?\(", v.strip())}
        assert len(lt) >= 30, sorted(lt)                                  # the floor
        assert lt <= set(_tokens(media)), sorted(lt - set(_tokens(media)))
        assert _tokens(media) == _tokens(forced)
        assert set(_tokens(media)) <= set(_tokens(light))                 # no dark-only ghost

    def test_the_dark_values_differ_where_the_ground_is_drawn(self):
        _, light, media, _ = _blocks()
        L, D = _tokens(light), _tokens(media)
        for k in ("--ground", "--surface", "--ink", "--line", "--accent", "--series-0"):
            assert L[k] != D[k], k

    def test_system_dark_yields_to_a_chosen_light(self):
        css, *_ = _blocks()
        assert "@media (prefers-color-scheme: dark)" in css
        assert ':root:not([data-theme="light"])' in css

    def test_no_colour_outside_the_token_blocks_except_on_the_always_dark_sidebar(self):
        css, light, media, forced = _blocks()
        rest = css
        for b in (light, media, forced):
            rest = rest.replace(b, "")
        found = []
        for line in rest.splitlines():
            if re.search(r"#[0-9A-Fa-f]{3,6}\b|rgba?\(", line):
                found.append(line.strip())
        # White text on --side, which is dark in both themes: the sidebar and
        # the phone's top bar.
        allowed = (".brand-name", ".nav-item:hover", ".nav-item.active", ".topbar {", ".net {", ".jump input")
        assert found and all(line.startswith(allowed) or "  .topbar" in line for line in found), found


class TestThePage:
    def test_the_theme_script_is_in_the_head_before_the_stylesheet_and_not_deferred(self):
        base = open(os.path.join(ROOT, "templates", "v2", "base.html"), encoding="utf-8").read()
        head = base[:base.index("</head>")]
        tag = "<script src=\"{{ url_for('static', filename='js/nmas_theme.js') }}\"></script>"
        assert tag in head and head.index(tag) < head.index("css/nmas-v2.css")
        assert '<meta name="color-scheme" content="light dark">' in head

    def test_the_menu_offers_three_choices_and_says_where_it_is_kept(self, client_v2=None):
        from app import app

        with app.test_client() as c:
            html = c.get("/v2/help/about").get_data(as_text=True)
        assert html.count('role="menuitemradio"') == 3
        for words in ("System", "Light", "Dark", "Kept in this browser only."):
            assert words in html
        assert 'x-data="theme"' in html

    def test_the_component_is_registered(self):
        src = _js("nmas_v2.js")
        assert "A.data('theme'" in src
        for m in ("chooseSystem", "chooseLight", "chooseDark"):
            assert m in src


class TestTheCharts:
    PANEL_STUB = """
var window = {
  getComputedStyle: function () { return {getPropertyValue: function (n) { return %(vals)s[n] || ''; }}; },
  document: {documentElement: {}}
};
"""

    def _palette(self, vals):
        src = self.PANEL_STUB % {"vals": json.dumps(vals)} + _js("nmas_panels.js")
        return json.loads(dukpy.evaljs(src + "\nJSON.stringify(window.NMAS_PANELS.palette());"))

    def test_the_charts_take_the_theme_tokens(self):
        dark = {"--series-0": " #5AA2D8", "--ink-2": "#A9B3BE", "--line-2": "#232C35", "--line": "#2E3843"}
        p = self._palette(dark)
        assert p["series"][0] == "#5AA2D8" and p["axis"] == "#A9B3BE" and p["grid"] == "#232C35"

    def test_with_no_stylesheet_the_light_constants_draw(self):
        p = self._palette({})
        assert p["series"][:2] == ["#1E5E8C", "#D97706"] and p["axis"] == "#4A5260"

    def test_a_theme_change_redraws_from_the_last_answer_and_fetches_nothing(self):
        src = _js("nmas_panels.js")
        listener = src[src.index("addEventListener('nmas:theme'"):]
        listener = listener[:listener.index("});")]
        assert "draw(list[i], list[i].__nmasLast)" in listener and "fetch" not in listener
        assert "'#4A5260', grid: {stroke: '#EEF0EC'}" not in src      # the old hard-coded axes
