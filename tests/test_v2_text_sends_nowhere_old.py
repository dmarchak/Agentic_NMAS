"""No visible v2 text sends a person to today's (v1) pages (Phase 7's burn-down, P7-19's
findings, 2026-10-15). tests/test_v2_links_stay_on_v2.py holds the LINKS; this holds the WORDS:
three v2 sentences still said a task lived on today's page after v2 carried it (the Devices
page's deploy, the device NetBox tab's import and removal, History's diff reveal), and once today's
pages leave such a sentence points nowhere. Jinja comments are the code's own notes and are
skipped; Help's "today's app" label is drawn only for a page `manual.ON_TODAYS_APP` marks (empty
since P7-19), so it is the one place the phrase may stand.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V2 = os.path.join(ROOT, "templates", "v2")

#: A sentence that places a task on today's pages.
SENDS_TO_TODAY = re.compile(r"today's (?:page|pages|screen|screens|[A-Z][A-Za-z ]{0,20} tab)\b")
#: The one template that may name today's app: Help's nav, for a page manual.ON_TODAYS_APP marks.
EXCUSED = {"_helpnav.html"}
COMMENT = re.compile(r"\{#.*?#\}", re.S)


def offenders(text: str) -> list:
    return SENDS_TO_TODAY.findall(COMMENT.sub("", text))


def scan() -> dict:
    found = {}
    for name in sorted(os.listdir(V2)):
        if not name.endswith(".html") or name in EXCUSED:
            continue
        with open(os.path.join(V2, name), encoding="utf-8") as fh:
            hits = offenders(fh.read())
        if hits:
            found[name] = hits
    return found


def test_no_v2_text_places_a_task_on_todays_pages():
    templates = [n for n in os.listdir(V2) if n.endswith(".html")]
    assert len(templates) >= 150, len(templates)        # 2026-10-15: the v2 templates
    assert scan() == {}, ("v2 text that sends a person to today's pages, which cutover "
                          "removes; name the v2 home instead: " + repr(scan()))


def test_the_scan_finds_a_planted_sentence_and_skips_a_comment():
    assert offenders("<p>A deploy is planned on today's page until the redesign.</p>") == \
        ["today's page"]
    assert offenders("<p>Importing stays on today's NetBox tab.</p>") == ["today's NetBox tab"]
    assert offenders("{# today's page drew this until 7.8 #}<p>Plan a deploy…</p>") == []
