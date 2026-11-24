"""Settings' words name no register row or plan section (C2820's survey, items 32 and 34;
MERCURY_CHARTER, "Human-facing means human-readable", rules 2 and 3).

- **The property:** the text a person reads on every Settings screen (Installation's tabs,
  Default's and each network's tabs, Self-healing's policy among them, and the cards and forms
  they load; `test_settings_descriptions._pages`) holds no register code ("(C380)", "C2839"),
  no plan or design code ("(N8)", "(H20)", "PHASE8_PLAN 17.7", "Section 13's") and no
  "production-readiness gate", the plan's name for what a person reads as Mercury being
  cleared for production use. A code's place is the record and the source, never the screen;
  what a hover or a comment holds is not read here.
- **Visible text:** each page with its scripts, styles, comments and tags removed, the
  entities unescaped; attribute values (a hover) are not text.

Through the real app, routes and templates, on `test_settings_v2`'s temporary store.
"""

import html
import re

from tests.test_settings_descriptions import _pages
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

#: A register or plan code as prose quotes one: "(C380)", "(N8)", "(H20)", ", C2839)", a bare
#: "C2839", "PHASE8_PLAN", "Section 13's"; never a platform's name ("C8000v").
CODE = re.compile(r"\((?:C\d{2,5}|[NH]\d{1,2})\b[^)]*\)|\bC\d{3,5}\b|PHASE8_PLAN"
                  r"|\bSection \d+'s\b|production-readiness gate")
_HIDDEN = re.compile(r"<(script|style)\b.*?</\1>|<!--.*?-->", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def visible(page: str) -> str:
    """*page*'s text as a person reads it: no script, style, comment or tag; entities read."""
    return html.unescape(_TAG.sub(" ", _HIDDEN.sub(" ", page)))


def test_the_pattern_finds_each_kind_of_code_and_not_a_platform_name():
    for planted in ("declared (C380)", "keeps it, C2839", "at most 7 days (N8)",
                    "the actions H20 built (H20)", "the gate (PHASE8_PLAN 17.7)",
                    "Section 13's never list", "the AUTO production-readiness gate"):
        assert CODE.search(planted), planted
    for plain in ("a C8000v router", "Catalyst 9300", "at most 7 days", "IOS-XE 17.9"):
        assert not CODE.search(plain), plain


def test_visible_reads_text_and_leaves_hovers_and_scripts_out():
    page = ('<p title="the token (C380)">Token expires</p><script>x="(N8)"</script>'
            "<!-- C2839 --><span>Lab &amp; pilot</span>")
    assert visible(page).split() == ["Token", "expires", "Lab", "&", "pilot"]


def test_no_settings_screen_names_a_register_row_or_a_plan_section(networks):  # noqa: F811
    pages = _pages(networks["client"])
    found = {}
    for path, page in pages.items():
        text = visible(page)
        for m in CODE.finditer(text):
            found.setdefault(path, []).append(text[max(0, m.start() - 50):m.end() + 10])
    assert len(pages) > 20, f"the floor: {len(pages)} Settings screens read"
    assert not found, "codes a person reads: " + "; ".join(
        f"{p}: {', '.join(repr(s) for s in hits)}" for p, hits in found.items())
