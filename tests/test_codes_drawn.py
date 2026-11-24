"""No screen names a register row or a plan section (C4234; C2820's survey, items 32 and 34;
MERCURY_CHARTER, "Human-facing means human-readable", rules 2 and 3).

- **The property:** the text a person reads in every HTML response the v2 walk reads (every
  page, fragment and provider on test_device_v2's lab, `tests/v2_context.measure`) holds no
  register code ("(C1915)", "C1793"), no plan or design code ("(N8)", "PHASE8_PLAN 17.1",
  "Section 7's") and no "production-readiness gate": tests/test_settings_words_name_no_codes.py's
  `CODE` and `visible` (a hover, a script or a comment is not read), so Settings' check and this
  one are one rule. A code's place is the record and the source, never the screen.
- **The manual is outside this population, stated:** its pages (`v2/help.html` and its panel)
  quote register rows as their sources, 38 codes in 18 pages on 2026-11-24; putting them into
  words is C4234's remainder, its own pass over docs/manual.

Measured 2026-11-24 before the fix: 17 distinct codes in 11 templates' words (C4234's row).
"""

from tests import v2_context as V2

#: The manual's templates: outside the population, as the docstring says.
MANUAL = frozenset({"v2/help.html", "v2/_help_panel.html"})


def _is_manual(templates: str) -> bool:
    return bool(set(templates.split(", ")) & MANUAL)


def test_the_walk_reads_its_responses_and_the_scan_finds_a_planted_code():
    walked = V2.measure()
    # 2015 HTML responses read on 2026-11-24 (C4234's measurement): a walk that stopped
    # reading most of them would fall below this.
    assert walked["bodies"] >= 1500, walked["bodies"]
    # The manual quotes codes (C4234's remainder), so the scan reached it and found them: a
    # scan that stopped finding codes would find none there either.
    assert any(_is_manual(t) for (_r, t) in walked["codes"]), "the scan found no code at all"


def test_no_screen_names_a_register_row_or_a_plan_section():
    walked = V2.measure()
    found = sorted(f"{route} [{templates}]: “{words}”"
                   for (route, templates), hits in walked["codes"].items()
                   if not _is_manual(templates) for words in hits)
    assert found == [], (
        f"{len(found)} place(s) show a person a register or plan code. Say what the code stands "
        "for in words, or leave it to the record and the source:\n" + "\n".join(found))
