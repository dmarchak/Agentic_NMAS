"""The refresh audit's cause 7 (design/review/REFRESH_AUDIT.md section 4; C4230): a chart panel
polls its source on a timer, and every answer destroyed and rebuilt the chart, so a person's
zoom and open hover were lost every poll even when nothing had changed. An answer equal to the
one drawn now draws nothing (`NMAS_PANELS.unchanged`, static/js/nmas_panels.js); a changed one,
or a panel with no chart yet, is drawn; a theme change still redraws from the last answer."""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "static", "js", "nmas_panels.js")


def _run(js: str):
    import dukpy
    src = open(SRC, encoding="utf-8").read()
    return json.loads(dukpy.evaljs("var window = {};\n" + src + "\n" + js))


def test_an_equal_answer_draws_nothing_and_a_changed_one_draws():
    got = _run("""
        var P = window.NMAS_PANELS, s = {}, a = {series: [{name: 'in', points: [[1, 2]]}]};
        var b = {series: [{name: 'in', points: [[1, 3]]}]};
        var out = {};
        out.first = P.unchanged(s, a);            // nothing drawn yet: draw it
        s.__nmasChart = {};                       // drawn
        out.same = P.unchanged(s, a);             // the same answer: keep what is drawn
        out.copy = P.unchanged(s, JSON.parse(JSON.stringify(a)));  // equal, a new object
        out.changed = P.unchanged(s, b);          // a new value: draw it
        out.back = P.unchanged(s, b);             // then that one is the drawn one
        var t = {};
        out.noChart = (P.unchanged(t, a), P.unchanged(t, a));  // a table or stat: always drawn
        JSON.stringify(out);
    """)
    assert got == {"first": False, "same": True, "copy": True, "changed": False, "back": True,
                   "noChart": False}, got


def _body(src: str, start: str) -> str:
    i = src.index(start)
    return src[i:src.index("\n  }\n", i)]


def test_the_fetch_asks_before_it_draws_and_the_theme_still_redraws():
    src = open(SRC, encoding="utf-8").read()
    fetched = _body(src, "  function load(section) {")
    asks = fetched.index("if (unchanged(section, got.body))")
    assert asks < fetched.index("draw(section, got.body);"), "asked before the draw"
    assert re.search(r"if \(unchanged\(section, got\.body\)\) \{[^}]*return; \}", fetched)
    listener = src[src.index("addEventListener('nmas:theme'"):]
    listener = listener[:listener.index("});")]
    assert "draw(list[i], list[i].__nmasLast)" in listener and "unchanged" not in listener
