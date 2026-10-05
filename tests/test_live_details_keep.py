"""C472: a `<details>` a live region draws stays open through its region's redraw.

R27's survey (2026-10-05) found the open `<details>` a person was reading closed by every
live redraw: Needs attention's evidence, History's rows, an apply's evidence, the device
Monitoring tab's folded panels, seed's whole document. One mechanism now covers the class
(`nmas_v2.js`, `rememberOpen` and `reopenKept`): a `<details data-keep="…">` open before a
swap of its region is opened again after it. tests/test_live_redraw_keeps_form.py shows it in
a real browser.

This holds the SHAPE: every `<details>` in a template that redraws live (an `hx-trigger` on
`nmas:` announcements, or Needs attention's built trigger), or in a template such a template
includes or imports, carries `data-keep`, or is named here with why it is not in a live region.
The population has a floor, and a planted template is found.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(ROOT, "templates", "v2")
LIVE = re.compile(r"from:body|attention_trigger")
USES = re.compile(r"""{%-?\s*(?:include|from)\s+["']v2/([^"']+)["']""")
DETAILS = re.compile(r"<details\b[^>]*>")

#: (template, the tag's class or "" ) -> why it is outside every live region.
NOT_LIVE = {
    ("history.html", "hist-kinds"): "the Kind filter, in History's filter form, which no "
                                    "announcement redraws",
    ("history.html", "hist-row"): "the authorisations' rows (#hist-auth), a section with no live "
                                  "trigger; the baselines' rows carry their key",
}


def live_templates() -> dict:
    """{template: text} for every v2 template that redraws live, and those it uses."""
    texts = {f: open(os.path.join(V2, f), encoding="utf-8").read()
             for f in os.listdir(V2) if f.endswith(".html")}
    todo = sorted(f for f, t in texts.items() if LIVE.search(t))
    seen = {}
    while todo:
        f = todo.pop()
        if f in seen or f not in texts:
            continue
        seen[f] = texts[f]
        todo += USES.findall(texts[f])
    return seen


def unkept(templates: dict) -> list:
    out = []
    for f, text in sorted(templates.items()):
        for tag in DETAILS.findall(text):
            if "data-keep" in tag:
                continue
            cls = (re.search(r'class="([^"]*)"', tag) or [None, ""])[1].split(" ")[0]
            if (f, cls) not in NOT_LIVE:
                out.append(f"{f}: {tag}")
    return out


def test_the_population_has_its_floor():
    t = live_templates()
    assert len(t) >= 25, sorted(t)
    assert sum(len(DETAILS.findall(x)) for x in t.values()) >= 8


def test_every_live_details_carries_its_key():
    assert unkept(live_templates()) == [], (
        "a <details> in a live region closes on every redraw unless it carries data-keep "
        "(C472); give it a stable key, or name here why it is not in a live region")


def test_a_planted_details_is_found():
    planted = {"_planted.html": '<div hx-trigger="nmas:goldens from:body"><details class="x">'
                                "<summary>s</summary></details></div>"}
    assert unkept(planted) == ['_planted.html: <details class="x">']


def test_every_exception_still_names_a_tag():
    t = live_templates()
    found = {(f, (re.search(r'class="([^"]*)"', tag) or [None, ""])[1].split(" ")[0])
             for f, text in t.items() for tag in DETAILS.findall(text)
             if "data-keep" not in tag}
    assert set(NOT_LIVE) <= found, set(NOT_LIVE) - found
