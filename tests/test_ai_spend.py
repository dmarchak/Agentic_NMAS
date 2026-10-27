"""AI spend as the toolbar chip, the spend panel and Needs attention read it (C1843; PHASE8_PLAN
18.3 rules 4, 6, 9 and 10; `modules/ai/spend.py`), and the windowed read every figure is
bounded by (`calls.rows_since`, `records_migrate.store_rows_since`).

- **The window** returns exactly the rows a whole read filtered by time returns, across block
  edges, a multi-byte character, an unparsable line, use rows and rows a lock's wait apart; and
  its WORK is the window's, not the record's: ten times the older rows parse no more lines.
- **The chip:** "AI off" with hosted AI off or no key; "AI $X today · N background on", neutral
  under 50%, amber from 50% and red from 80% of the day cap, neutral with no cap; an unreadable
  record says so in red, never $0.
- **The panel:** today, the 7- and 30-day averages over the complete days before today, month to
  date with its projection and the cap the day cap implies, the viewer's own spend, today by
  trigger kind and each evaluation run's; an unreadable record is said, never zeros.
- **Background features:** each on, its spend against its caps, a warning at 50% and 80%,
  stopped by a cap refusal recorded since its caps were set, its estimate against the average
  daily spend since it was turned on; and the Needs attention rows they raise, each naming what
  is wrong, the action and how it clears; none read while no feature is on.
"""
import datetime
import json
import types

import pytest

from modules import attention
from modules import records_migrate as R
from modules.ai import background as B
from modules.ai import calls, gateway, spend
from tests.test_ai_background import ADMIN, _on, _plant, bg  # noqa: F401 (the fixture)
from tests.test_ai_gateway import own_record  # noqa: F401 (the fixture)

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _row(at, cost=0.0, **extra):
    return dict({"id": calls.new_id(), "at": _iso(at), "feature": "connection_check",
                 "actor": "a@example.com", "verdict": "ok", "cost_usd": cost}, **extra)


def _write(rows):
    for r in rows:
        assert calls.record(r)["recorded"]


# ── the window ────────────────────────────────────────────────────────────────────────────────

def _file(tmp_path, rows, junk_at=None):
    p = tmp_path / "w.jsonl"
    with open(p, "w", encoding="utf-8") as fh:
        for i, r in enumerate(rows):
            if junk_at == i:
                fh.write('{"torn": \n')
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    return str(p)


def _whole(rows, since):
    return [r for r in rows if R._at(r) is not None and R._at(r) >= since]


def test_the_window_is_exactly_what_a_whole_read_filtered_by_time_gives(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "TAIL_BLOCK", 97)        # many block edges, inside lines
    base = NOW - datetime.timedelta(days=10)
    rows = []
    for i in range(400):
        at = base + datetime.timedelta(minutes=36 * i)
        # A row stamped a few seconds before the one written ahead of it (a lock's wait).
        if i % 7 == 3:
            at -= datetime.timedelta(seconds=40)
        rows.append({"i": i, "at": _iso(at), "note": "naïve – ünïcode"})
    rows.insert(50, {"i": "no time"})
    path = _file(tmp_path, rows, junk_at=200)
    for since in (base, NOW - datetime.timedelta(days=3, minutes=7), NOW,
                  NOW + datetime.timedelta(days=30), base - datetime.timedelta(days=1)):
        got = R.store_rows_since("ai_calls", path, since, 600.0, skip_unparsable=True)
        assert got["state"] == "ok" and got["rows"] == _whole(rows, since), since


def test_absent_and_unreadable_are_said(tmp_path):
    got = R.store_rows_since("ai_calls", str(tmp_path / "none.jsonl"), NOW, 600.0)
    assert got == {"state": "absent", "rows": [], "error": ""}
    path = _file(tmp_path, [{"at": _iso(NOW)}], junk_at=0)
    got = R.store_rows_since("ai_calls", path, NOW - datetime.timedelta(days=1), 600.0)
    assert got["state"] == "unreadable" and got["rows"] == []


def _parses(tmp_path, monkeypatch, older: int) -> int:
    """How many lines the window of the last day parses, with *older* rows before it."""
    rows = [{"at": _iso(NOW - datetime.timedelta(days=5, seconds=i))} for i in range(older)]
    rows.reverse()
    rows += [{"at": _iso(NOW - datetime.timedelta(hours=h))} for h in range(20, 0, -1)]
    path = _file(tmp_path, rows)
    counted = []
    real = json.loads
    monkeypatch.setattr(R, "json", types.SimpleNamespace(
        loads=lambda s, *a, **k: counted.append(1) or real(s, *a, **k), dumps=json.dumps))
    got = R.store_rows_since("ai_calls", path, NOW - datetime.timedelta(days=1), 600.0)
    assert len(got["rows"]) == 20
    return len(counted)


def test_the_windows_work_is_the_windows_not_the_records(tmp_path, monkeypatch):
    small = _parses(tmp_path, monkeypatch, 500)
    large = _parses(tmp_path, monkeypatch, 5000)
    assert small == large == 21, "the window's 20 rows and the first older one, whatever came before"


@pytest.mark.parametrize("day,first,before", [
    # Havana skips midnight on 2026-03-08 (00:00 -05 becomes 01:00 -04): the day's first
    # minute is 05:00 UTC.
    ("2026-03-08", "2026-03-08T05:00:30Z", "2026-03-08T04:59:30Z"),
    # And repeats an hour on 2026-11-01 (01:00 -04 becomes 00:00 -05): the day begins at its
    # first midnight, 04:00 UTC.
    ("2026-11-01", "2026-11-01T04:10:00Z", "2026-11-01T03:59:00Z"),
], ids=["midnight-skipped", "hour-repeated"])
def test_a_days_window_holds_its_first_minutes_across_daylight_saving(day, first, before):
    _write([{"id": "b", "at": before, "cost_usd": 0.01, "actor": "a"},
            {"id": "f", "at": first, "cost_usd": 0.20, "actor": "a"}])
    got = calls.spent_usd(day, zone="America/Havana")
    assert got == {"state": "ok", "usd": 0.20, "calls": 1, "error": ""}


def _stamps_its_own_time(call) -> bool:
    """Whether a `calls.record(...)` call hands in a time of its own (an `"at"` key in a dict
    literal, or `at=` in a `dict(...)`)."""
    import ast
    for arg in call.args:
        for node in ast.walk(arg):
            if isinstance(node, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == "at"
                                                  for k in node.keys):
                return True
            if isinstance(node, ast.Call) and any(k.arg == "at" for k in node.keywords):
                return True
    return False


def test_every_product_row_is_stamped_when_it_is_written():
    """The window's premise (`calls.rows_since`): the record is in time order to within a
    lock's wait, because `calls.record` stamps each row as it writes it. So no product writer
    hands in a time of its own; a planted one is found."""
    import ast
    import os
    from tests.source_index import tracked
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    found, seen = [], 0
    for p in tracked("modules", suffix=".py") + tracked("routes", suffix=".py"):
        with open(p, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            f = getattr(node, "func", None)
            if (isinstance(node, ast.Call) and isinstance(f, ast.Attribute)
                    and f.attr == "record" and getattr(f.value, "id", "") == "calls"):
                seen += 1
                if _stamps_its_own_time(node):
                    found.append(f"{os.path.relpath(p, root)}:{node.lineno}")
    assert seen >= 3, "the scan's floor: the gateway's record calls"
    assert found == []
    planted = ast.parse('calls.record(dict(row, at="2026-01-01T00:00:00Z"))\n'
                        'calls.record({"id": 1, "at": "x"})\ncalls.record(dict(row, v=1))\n')
    assert [_stamps_its_own_time(n.value) for n in planted.body] == [True, True, False]


def test_rows_since_leaves_use_rows_out(tmp_path):
    _write([_row(NOW, 0.01)])
    calls.record_use("ai-x", "shown", actor="a")
    got = calls.rows_since(NOW - datetime.timedelta(days=400))
    assert [r.get("use_of") for r in got["rows"]] == [None]


def test_rows_since_skips_a_torn_line_as_the_whole_read_does(tmp_path):
    # A line torn by a crash mid-append is no call (`read` skips it); it never makes every
    # spend figure, and so every cap, unreadable.
    _write([_row(NOW - datetime.timedelta(hours=2), 0.01)])
    with open(calls._path(), "a", encoding="utf-8") as fh:
        fh.write('{"torn": \n')
    _write([_row(NOW - datetime.timedelta(hours=1), 0.02)])
    got = calls.rows_since(NOW - datetime.timedelta(days=1))
    assert got["state"] == "ok" and [r["cost_usd"] for r in got["rows"]] == [0.01, 0.02]
    assert [r["cost_usd"] for r in calls.read()["rows"]] == [0.02, 0.01]


def test_rows_since_reads_the_records_database_once_the_record_moved_there(tmp_path,
                                                                           monkeypatch):
    # Moved, the file left behind is never read: the database is asked, and its failure said.
    from modules import records_db
    _write([_row(NOW, 0.01)])
    monkeypatch.setattr(records_db, "backend", lambda store: (
        records_db.POSTGRES if store == calls.STORE else records_db.FILE))

    def no_database():
        raise records_db.Unavailable("no records database (planted)")
    monkeypatch.setattr(records_db, "pooled", no_database)
    got = calls.rows_since(NOW - datetime.timedelta(days=1))
    assert got["state"] == "unreadable" and got["rows"] == []
    assert got["error"] == "the records database: Unavailable: no records database (planted)"


def test_an_unreadable_record_is_said_and_logged_once(tmp_path, caplog):
    import os
    os.makedirs(calls._path())              # a folder where the file should be: unreadable
    with caplog.at_level("ERROR", logger=calls.__name__):
        got = calls.rows_since(NOW - datetime.timedelta(days=1))
    assert got["state"] == "unreadable" and got["rows"] == []
    assert got["error"].startswith("IsADirectoryError: ")
    said = [r.getMessage() for r in caplog.records if r.name == calls.__name__]
    assert said == [f"ai_calls: unreadable ({got['error']})"]


def test_a_days_rows_are_read_in_the_zone_asked(tmp_path):
    # Asia/Tokyo's 15 January begins at 15:00 UTC on the 14th, hours before UTC's: the window
    # opens at the zone's midnight, never the boundary setting's (UTC here).
    early = _row(datetime.datetime(2026, 1, 14, 14, 0, tzinfo=UTC), 0.01)   # Tokyo's 14th
    first = _row(datetime.datetime(2026, 1, 14, 20, 0, tzinfo=UTC), 0.02)   # Tokyo's 15th
    late = _row(datetime.datetime(2026, 1, 15, 16, 0, tzinfo=UTC), 0.04)    # Tokyo's 16th
    _write([early, first, late])
    assert calls.boundary() == "UTC"
    assert [r["id"] for r in calls.day_rows("2026-01-15", "Asia/Tokyo")["rows"]] == [first["id"]]


@pytest.mark.parametrize("day", ["2026-13-40", "", None], ids=["no-such-date", "empty", "none"])
def test_a_day_that_is_no_date_holds_no_row(tmp_path, day):
    _write([_row(NOW, 0.01)])
    assert calls.day_rows(day) == {"state": "ok", "rows": [], "error": ""}
    assert calls.spent_usd(day) == {"state": "ok", "usd": 0, "calls": 0, "error": ""}


# ── the chip ──────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def chip_world(bg, monkeypatch):
    from modules import secrets_store
    monkeypatch.setattr(secrets_store, "is_set", lambda key: key == "anthropic_api_key")
    return bg


def test_the_chip_says_ai_off_with_hosted_ai_off_or_no_key(chip_world, monkeypatch):
    from modules import secrets_store
    from modules.settings_schema import write_settings
    monkeypatch.setattr(secrets_store, "is_set", lambda key: False)
    assert spend.chip()["words"] == "AI off" and spend.chip()["state"] == "off"
    monkeypatch.setattr(secrets_store, "is_set", lambda key: True)
    assert write_settings({"ai_hosted": {}})["ok"]
    got = spend.chip()
    assert got["words"] == "AI off" and got["level"] == "neutral" and got["usd_today"] is None


@pytest.mark.parametrize("usd,level", [(0.0, "neutral"), (0.74, "neutral"), (0.75, "amber"),
                                       (1.19, "amber"), (1.20, "red"), (1.6, "red")])
def test_the_chips_colour_is_its_fraction_of_the_day_cap(chip_world, usd, level):
    _write([_row(datetime.datetime.now(UTC), usd)])
    got = spend.chip()
    assert got["state"] == "on" and got["level"] == level
    assert got["words"] == f"AI ${usd:.2f} today · 0 background on"


def test_the_chip_counts_the_background_features_on(chip_world):
    _on("Lab")
    _on("Branch")
    assert spend.chip()["words"] == "AI $0.00 today · 2 background on"


def test_with_no_cap_the_chip_is_neutral_and_says_so(chip_world):
    from modules.settings_schema import write_settings
    assert write_settings({"ai_cap_usd_per_day": None})["ok"]
    _write([_row(datetime.datetime.now(UTC), 50.0)])
    got = spend.chip()
    assert got["level"] == "neutral" and got["no_cap"] is True and got["day_cap"] is None


def test_an_unreadable_record_is_said_on_the_chip_never_zero(chip_world, monkeypatch):
    monkeypatch.setattr(calls, "rows_since", lambda start: {"state": "unreadable", "rows": [],
                                                            "error": "a torn line"})
    got = spend.chip()
    assert got["state"] == "unreadable" and got["level"] == "red" and got["usd_today"] is None
    assert got["words"] == "AI spend unknown: the record of AI calls cannot be read"


# ── the panel ─────────────────────────────────────────────────────────────────────────────────

def _days(n):
    return NOW - datetime.timedelta(days=n)


def test_the_panels_figures(bg):
    _write([
        _row(_days(40), 9.0),                                      # outside every window
        _row(_days(19).replace(hour=1), 0.30),                     # the 1st: the month, the 30
        _row(_days(8), 0.70),                                      # in the 30, not the 7
        _row(_days(3), 0.14),
        _row(_days(1), 0.07, actor="evaluation:run-1",
             trigger={"kind": "evaluation", "run": "run-1"}),
        _row(NOW.replace(hour=1), 0.20, actor="viewer@example.com",
             trigger={"kind": "person", "by": "viewer@example.com"}),
        _row(NOW.replace(hour=2), 0.05, actor="evaluation:run-2",
             trigger={"kind": "evaluation", "run": "run-2"}),
        _row(NOW.replace(hour=3), 0.01, actor="job:j1",
             trigger={"kind": "background", "feature": "fake_loop", "job": "j1",
                      "network": "lab", "finding": {"kind": "detection", "id": "d"}}),
        # A press that joined another's call (C1854): no call made, nothing spent.
        _row(NOW.replace(hour=4), 0.0, actor="viewer@example.com", verdict=calls.JOINED,
             joined="ai-0000000000000001",
             trigger={"kind": "person", "by": "viewer@example.com"}),
    ])
    got = spend.panel("viewer@example.com", now=NOW)
    assert got["state"] == "ok" and got["today"] == "2026-10-20"
    assert got["usd_today"] == pytest.approx(0.26) and got["calls_today"] == 3, \
        "a join is no call"
    assert got["average"][7] == pytest.approx((0.14 + 0.07) / 7)
    assert got["average"][30] == pytest.approx((0.30 + 0.70 + 0.14 + 0.07) / 30)
    month = got["month"]
    assert month["usd"] == pytest.approx(0.30 + 0.70 + 0.14 + 0.07 + 0.26)
    elapsed = 19.5
    assert month["elapsed_days"] == elapsed and month["days"] == 31
    assert month["projection"] == pytest.approx(month["usd"] / elapsed * 31)
    assert month["cap"] == pytest.approx(1.5 * 31)
    assert month["cap_basis"] == "the day cap $1.50 times the month's 31 days"
    assert got["mine_today"] == pytest.approx(0.20)
    assert got["by_kind_today"] == pytest.approx({"person": 0.20, "evaluation": 0.05,
                                                  "background": 0.01})
    assert got["runs_today"] == pytest.approx({"run-2": 0.05})
    assert got["resets"]["at"] == "2026-10-21T00:00:00Z"


def test_a_row_from_before_triggers_is_read_as_a_person_or_an_evaluation():
    assert spend.trigger_of({"actor": "a@example.com"}) == {"kind": "person",
                                                           "by": "a@example.com",
                                                           "derived": True}
    assert spend.trigger_of({"actor": "evaluation:r"}) == {"kind": "evaluation", "run": "r",
                                                          "derived": True}


def test_with_no_day_cap_no_month_cap_is_implied(bg):
    from modules.settings_schema import write_settings
    assert write_settings({"ai_cap_usd_per_day": None})["ok"]
    got = spend.panel("", now=NOW)
    assert got["month"]["cap"] is None and got["no_cap"] is True
    assert got["month"]["cap_basis"] == "no day cap is set, so no month cap"


def test_an_unreadable_record_is_said_on_the_panel(bg, monkeypatch):
    monkeypatch.setattr(calls, "rows_since", lambda start: {"state": "unreadable", "rows": [],
                                                            "error": "a torn line"})
    assert spend.panel("", now=NOW) == {"state": "unreadable", "error": "a torn line",
                                        "today": "2026-10-20"}


def test_the_panel_reads_one_window_of_at_most_31_days(bg, monkeypatch):
    asked = []
    real = calls.rows_since
    monkeypatch.setattr(calls, "rows_since", lambda start: asked.append(start) or real(start))
    spend.panel("", now=NOW)
    (start,) = asked
    assert NOW - start <= datetime.timedelta(days=31, hours=12, minutes=11)


# ── background features and Needs attention ───────────────────────────────────────────────────

def _summary():
    zone = calls.boundary()
    today = calls.today(zone=zone)
    rows = calls.rows_since(spend.month_start(today, zone))["rows"]
    (f,) = spend.feature_summaries(rows, today, zone)
    return f


@pytest.mark.parametrize("spent,warning", [(0.24, ""), (0.25, "50"), (0.39, "50"),
                                           (0.40, "80")])
def test_a_features_warning_is_its_nearer_caps_fraction(bg, spent, warning):
    _on(day=0.50, month=100.0)
    _plant(spent)
    f = _summary()
    assert f["warning"] == warning and f["fractions"]["day"] == pytest.approx(spent / 0.5)
    assert f["stopped"] == {"day": False, "month": False}


def _fixed_summary():
    rows = calls.rows_since(spend.month_start("2026-10-20", "UTC"))["rows"]
    (f,) = spend.feature_summaries(rows, "2026-10-20", "UTC", NOW)
    return f


def test_a_feature_is_stopped_by_a_cap_refusal_since_its_caps_were_set(bg, monkeypatch):
    monkeypatch.setattr(B, "_now", lambda: (NOW - datetime.timedelta(hours=2)).timestamp())
    _on(day=0.50, month=100.0)
    _plant(0.0, verdict="feature_cap", cap_kind="day",
           at=_iso(NOW - datetime.timedelta(hours=1)))
    assert _fixed_summary()["stopped"] == {"day": True, "month": False}
    assert _fixed_summary()["stopped_at"]["day"] == _iso(NOW - datetime.timedelta(hours=1))
    # The caps set again after it: a refusal recorded before then no longer stops it.
    monkeypatch.setattr(B, "_now", lambda: NOW.timestamp())
    B.set_caps("Lab", "fake_loop", day_cap_usd=1.0, month_cap_usd=100.0, actor=ADMIN,
               verified="access")
    assert _fixed_summary()["stopped"] == {"day": False, "month": False}


def test_a_month_cap_refusal_stops_it_for_the_month_a_day_one_for_its_day(bg, monkeypatch):
    monkeypatch.setattr(B, "_now", lambda: (NOW - datetime.timedelta(days=5)).timestamp())
    _on(day=0.50, month=100.0)
    _plant(0.0, verdict="feature_cap", cap_kind="day", at=_iso(NOW - datetime.timedelta(days=2)))
    _plant(0.0, verdict="feature_cap", cap_kind="month",
           at=_iso(NOW - datetime.timedelta(days=3)))
    assert _fixed_summary()["stopped"] == {"day": False, "month": True}


def test_the_estimate_stands_beside_the_actual_daily_average(monkeypatch):
    zone = "UTC"
    today = "2026-10-20"
    entry = {"on": True, "at": "2026-10-16T08:00:00Z", "day_cap_usd": 1.0, "month_cap_usd": 9.0,
             "estimate": {"usd_per_day": 0.10}}
    trig = {"kind": "background", "feature": "fake_loop", "job": "j", "network": "lab",
            "finding": {"kind": "detection", "id": "d"}}
    rows = [_row(datetime.datetime(2026, 10, d, 9, tzinfo=UTC), c, trigger=trig)
            for d, c in ((16, 0.05), (17, 0.10), (19, 0.15), (20, 0.40))]
    monkeypatch.setattr(B, "enabled", lambda: [("lab", "fake_loop", entry)])
    (f,) = spend.feature_summaries(rows, today, zone, NOW)
    # The complete days since it was turned on: the 16th to the 19th.
    assert f["actual_days"] == 4
    assert f["actual_usd_per_day"] == pytest.approx((0.05 + 0.10 + 0.15) / 4)
    assert f["ratio"] == pytest.approx((0.30 / 4) / 0.10)
    assert f["spent"]["day_usd"] == pytest.approx(0.40)


def test_needs_attention_reads_nothing_while_no_feature_is_on(bg, monkeypatch):
    monkeypatch.setattr(calls, "rows_since", lambda start: pytest.fail("read the record"))
    got = attention.ai_spend_source()
    assert got["state"] == "read" and got["rows"] == []
    assert got["checked"] == "no background AI feature is on for any network, so no spend " \
                             "was read"


def test_a_warning_row_names_what_is_wrong_the_action_and_how_it_clears(bg):
    _on(day=0.50, month=100.0)
    _plant(0.42)
    (row,) = attention.ai_spend_source()["rows"]
    assert row["kind"] == "warning" and row["level"] == "danger"
    assert row["what"] == "The fake loop on lab has spent 84% of its day cap"
    assert "spent $0.4200 on lab today, 84% of its day cap $0.5000 (warned at 80%)" in \
        row["cause"]
    assert row["action"]["label"] == ("Read The fake loop's spend on lab; leave it, turn it "
                                      "off, or change its day cap in Settings › AI")
    assert row["action"]["href"] == attention.AI_SETTINGS_HREF
    assert row["clears"]["ways"] == ["resolves", "time"]
    tomorrow = calls.resets_at().strftime("%Y-%m-%dT%H:%M:%SZ")
    assert row["clears_at"] == tomorrow


def test_a_stopped_row_is_danger_and_clears_when_its_period_ends(bg):
    _on(day=0.50, month=100.0)
    _plant(0.499999)
    _plant(0.0, verdict="feature_cap", cap_kind="day")
    (row,) = attention.ai_spend_source()["rows"]
    assert row["kind"] == "stopped" and row["level"] == "danger"
    assert row["what"] == "The fake loop on lab stopped: it reached its day cap"
    assert row["action"]["label"] == ("Leave The fake loop stopped until the day ends, raise "
                                      "its day cap, or turn it off for lab in Settings › AI")
    assert row["operands"]["cap"] == "day" and row["operands"]["cap_usd"] == 0.5


def test_under_half_its_caps_a_feature_raises_no_row(bg):
    _on(day=0.50, month=100.0)
    _plant(0.10)
    got = attention.ai_spend_source()
    assert got["rows"] == [] and "1 background feature switch(es) on" in got["checked"]


def test_an_unreadable_record_is_a_row_of_its_own(bg, monkeypatch):
    _on()
    monkeypatch.setattr(calls, "rows_since", lambda start: {"state": "unreadable", "rows": [],
                                                            "error": "a torn line"})
    got = attention.ai_spend_source()
    assert got["state"] == "unreadable" and got["rows"][0]["kind"] == "unreadable"
    assert "a torn line" in got["rows"][0]["cause"]


def test_the_attention_source_is_registered_with_its_keys():
    assert attention.ai_spend_source in attention.SOURCES
    assert attention.SOURCE_KEYS["ai_spend_source"] == ("ai_calls", "settings")


def test_gateway_day_cap_is_the_panels(bg):
    assert spend.panel("", now=NOW)["day_cap"] == gateway.day_cap() == 1.5
