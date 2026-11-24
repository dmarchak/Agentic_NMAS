"""The Incidents page's fleet view (the GUI redesign brief §4.2, 2026-11-18;
modules/incidents_board.py, templates/v2/_incidents_board.html): an incident's category from its
own triggers (a symptom before a change), each row's autonomy from how it was or is being fixed,
the period's outcome strip counted from the rows' groups (the brief's four always drawn, a
closed-without-a-fix count beside them), each category's tile with its open count and its
detections per day, and the partial drawing every part with the categories the store holds none
of saying what they need."""

from modules import incidents_board as B

NOW = 1794960000.0          # 2026-11-18T00:00:00Z
DAY = 86400


def _at(days_ago):
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - days_ago * DAY))


def _row(group, days_ago=1, category="interfaces", resolved=True, ai=None):
    return {"group": group, "since": _at(days_ago), "category": category,
            "resolved": resolved, "ai": ai}


def test_the_category_is_its_first_symptoms_kind():
    assert B.category({"triggers": [{"kind": "config_change"}, {"kind": "errdisable"}]}) == \
        "interfaces"
    assert B.category({"triggers": [{"kind": "drift"}]}) == "drift"
    assert B.category({"triggers": [{"kind": "adjacency_log"}]}) == "routing"
    assert B.category({"triggers": [{"kind": "alert"}]}) == "alerts"
    assert B.category(None) == "other" and B.category({"triggers": [{"kind": "x"}]}) == "other"


def test_the_autonomy_is_how_it_was_or_is_being_fixed():
    assert [B.autonomy(_row(g)) for g in ("fixed_mercury", "fixed_script", "fixed_ai",
                                          "fixed_person", "cleared")] == \
        [B.SELF, B.SELF, B.AI, B.MANUAL, ""]
    assert B.autonomy(_row("needs_person", resolved=False, ai={"state": "ended"})) == B.AI
    assert B.autonomy(_row("needs_person", resolved=False)) == B.MANUAL
    assert B.autonomy(_row("working", resolved=False)) == B.SELF


def test_the_strip_counts_the_period_by_outcome():
    rows = ([_row("fixed_mercury")] * 3 + [_row("fixed_script")] + [_row("fixed_ai")] * 2
            + [_row("needs_person", resolved=False)] + [_row("cleared"), _row("cancelled")]
            + [_row("fixed_person", days_ago=31)])
    got = {o["key"]: o["n"] for o in B.board(rows, NOW)["outcomes"]}
    assert got == {"self_healed": 4, "ai_fixed": 2, "person_fixed": 0, "open": 1,
                   "closed_unfixed": 2}


def test_the_strips_open_counts_every_open_incident_as_the_tiles_do():
    """C4033: an incident still open though detected before the window is open on the strip,
    so the strip never reads "0 open" beside the tab's "Open · 1" and the tile's "1 open"."""
    rows = [_row("needs_person", days_ago=40, resolved=False), _row("fixed_person", days_ago=45),
            _row("working", days_ago=2, category="routing", resolved=False)]
    got = B.board(rows, NOW)
    strip = {o["key"]: o["n"] for o in got["outcomes"]}
    assert strip["open"] == 2 == sum(t["open"] for t in got["tiles"])
    assert strip.get("person_fixed", 0) == 0, "the window still bounds the closed counts"


def test_each_tile_counts_its_open_and_its_detections_per_day():
    rows = [_row("fixed_mercury", days_ago=0.5), _row("fixed_mercury", days_ago=0.6),
            _row("needs_person", days_ago=40, resolved=False),
            _row("fixed_ai", days_ago=10, category="routing")]
    tiles = {t["key"]: t for t in B.board(rows, NOW)["tiles"]}
    assert set(tiles) == {"interfaces", "routing"}
    assert tiles["interfaces"]["open"] == 1 and tiles["interfaces"]["total"] == 2
    assert tiles["interfaces"]["trend"][-1] == 2 and tiles["interfaces"]["peak"] == 2
    assert len(tiles["routing"]["trend"]) == B.WINDOW_DAYS and tiles["routing"]["trend"][20] == 1


def test_the_partial_draws_every_part_and_its_needs():
    from flask import render_template
    from markupsafe import escape

    from app import app
    board = B.board([_row("fixed_ai"), _row("needs_person", resolved=False)], NOW)
    with app.test_request_context("/"):
        html = render_template("v2/_incidents_board.html", p={"network": "Lab", "board": board})
    for key in B.ALWAYS:
        assert f'data-outcome="{key}"' in html
    assert '<strong>1</strong> AI-fixed (approved)' in html
    assert 'data-category="interfaces"' in html and html.count("<rect ") == 1
    for name, need in B.NEEDS.items():
        assert f'data-category="{name}"' in html and "needs: " + str(escape(need)) in html
