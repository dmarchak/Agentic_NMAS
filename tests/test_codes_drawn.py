"""No screen names a register row or a plan section (C4234; C2820's survey, items 32 and 34;
MERCURY_CHARTER, "Human-facing means human-readable", rules 2 and 3).

- **The property:** the text a person reads in every HTML response the v2 walk reads (every
  page, fragment and provider on test_device_v2's lab, `tests/v2_context.measure`) holds no
  register code ("(C1915)", "C1793"), no plan or design code ("(N8)", "PHASE8_PLAN 17.1",
  "Section 7's") and no "production-readiness gate": tests/test_settings_words_name_no_codes.py's
  `CODE` and `visible` (a hover, a script or a comment is not read), so Settings' check and this
  one are one rule. A code's place is the record and the source, never the screen.
- **The manual is inside the population** (C4234's remainder, 2026-11-24): its pages
  (`v2/help.html` and its panel) said their gaps by register row, 38 codes in 18 pages, and now
  say them in words ("a known gap, registered to be built"); the source keeps the row.

Measured 2026-11-24 before the fix: 17 distinct codes in 11 templates' words, and the manual's
67 passages on the 2 help routes the walk reaches (C4234's row).
"""

from flask import Flask

from tests import v2_context as V2


def test_the_walk_reads_its_responses_and_the_scan_finds_a_planted_code():
    walked = V2.measure()
    # 2015 HTML responses read on 2026-11-24 (C4234's measurement): a walk that stopped
    # reading most of them would fall below this.
    assert walked["bodies"] >= 1500, walked["bodies"]
    # The planted case, through the walk's own recorder: one response whose words name a row
    # and a plan section, and one that names them only on hover and in a script (not read).
    app = Flask(__name__)
    app.add_url_rule("/planted", "planted", lambda: (
        "<p>registered for later, C1915, as PHASE8_PLAN 17.1 says</p>"))
    app.add_url_rule("/hidden", "hidden", lambda: (
        '<p title="C1915">in words</p><script>var row = "C1915";</script>'))
    recorder = V2._Recorder(app)
    with app.test_client() as client:
        for path in ("/planted", "/hidden"):
            recorder._people(client.get(path))
    found = {words for hits in recorder.codes.values() for words in hits}
    assert recorder.bodies == 2, recorder.bodies
    assert len(recorder.codes) == 1 and any("C1915" in w for w in found), recorder.codes
    assert all("/planted" in route for (route, _t) in recorder.codes), recorder.codes


def test_no_screen_names_a_register_row_or_a_plan_section():
    walked = V2.measure()
    found = sorted(f"{route} [{templates}]: “{words}”"
                   for (route, templates), hits in walked["codes"].items()
                   for words in hits)
    assert found == [], (
        f"{len(found)} place(s) show a person a register or plan code. Say what the code stands "
        "for in words, or leave it to the record and the source:\n" + "\n".join(found))
