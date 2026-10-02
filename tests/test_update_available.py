"""The top bar's quiet "Update available" (the operator, 2026-10-02): an update is news,
not a problem, but it should be noticeable where a person looks, not only on Help > About.

- It is drawn only when origin/main is ahead AND CI passed for its tip, neutral in colour,
  and opens the Update page; its hover says how far behind and since when.
- It TURNS INTO the Needs attention row: when any of the row's conditions holds (CI failed
  or cancelled, behind past the measured 20 h, the fetch failed, an update asked from this
  commit that did not happen), the indicator is gone and the row is there. One decision,
  `attention.release_level()`, is read by both, so they can never show together and never
  both be absent for an installable update.
"""

import time

import pytest

from modules import attention

RUN, TIP = "a" * 40, "b" * 40


def _iso(seconds_ago):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds_ago))


def _value(**over):
    v = {"running": RUN, "tip": TIP, "state": "behind", "behind": 3, "branch": "main",
         "behind_since": _iso(600), "ci": {"tip": TIP, "state": "verified"}}
    v.update(over)
    return v


def _cached(value):
    return {"state": "ok", "doc": {"last_good": {"value": value, "value_at": _iso(30)},
                                   "stale_after_seconds": 750}}


NO_UPDATE_ASKED = {}
FAILED_UPDATE = {"outcome": "rolled_back", "from": RUN, "to": TIP, "requested_by": "op@example.com",
                 "reason": "the new version did not come up"}

#: Every case: the stored comparison, the last update's outcome, and whether the
#: indicator shows. Where it does not, the row's presence is asserted beside it.
CASES = [
    ("installable", _value(), NO_UPDATE_ASKED, True),
    ("ci_still_checking", _value(ci={"tip": TIP, "state": "pending"}), NO_UPDATE_ASKED, False),
    ("ci_never_asked", _value(ci={}), NO_UPDATE_ASKED, False),
    ("ci_for_another_tip", _value(ci={"tip": "c" * 40, "state": "verified"}), NO_UPDATE_ASKED,
     False),
    ("ci_failed", _value(ci={"tip": TIP, "state": "failed"}), NO_UPDATE_ASKED, False),
    ("ci_cancelled", _value(ci={"tip": TIP, "state": "cancelled"}), NO_UPDATE_ASKED, False),
    ("behind_too_long", _value(behind_since=_iso(21 * 3600)), NO_UPDATE_ASKED, False),
    ("fetch_failed", _value(state="behind_unfetched", behind=None, fetch_error="refused"),
     NO_UPDATE_ASKED, False),
    ("update_did_not_happen", _value(), FAILED_UPDATE, False),
    ("at_the_tip", _value(state="at_tip", tip=RUN, behind=0), NO_UPDATE_ASKED, False),
    ("not_on_the_remote", _value(state="not_on_remote", behind=None), NO_UPDATE_ASKED, False),
]


@pytest.fixture
def running(monkeypatch):
    from routes import health
    monkeypatch.setattr(health, "_COMMIT", RUN)


def _last(monkeypatch, last):
    monkeypatch.setattr("modules.update_op.outcome", lambda: {"value": last})


class TestTheDecision:
    @pytest.mark.parametrize("name,value,last,shows", CASES, ids=[c[0] for c in CASES])
    def test_shown_only_for_an_installable_update(self, name, value, last, shows):
        got = attention.update_available(value, last=last)
        assert (got is not None) is shows, (name, got)

    def test_the_hover_says_how_far_behind_and_since_when(self):
        got = attention.update_available(_value(behind_since="2026-10-02T14:05:00Z"),
                                         last=NO_UPDATE_ASKED)
        assert got["title"].startswith("3 commits behind origin/main (aaaaaaa → bbbbbbb)")
        assert "CI passed" in got["title"] and "since 2026-10-02 14:05 UTC" in got["title"]
        one = attention.update_available(_value(behind=1), last=NO_UPDATE_ASKED)
        assert one["title"].startswith("1 commit behind")

    @pytest.mark.parametrize("name,value,last,shows", CASES, ids=[c[0] for c in CASES])
    def test_it_turns_into_the_row_never_beside_it(self, monkeypatch, running, name, value, last,
                                                    shows):
        """For an update CI passed, exactly one of the two is drawn: the quiet
        indicator, or the Needs attention row. The row's own source computes the
        row, from the same stored value."""
        _last(monkeypatch, last)
        rows = attention.pushed_source(cached=_cached(value))["rows"]
        assert not (shows and rows), (name, rows)
        if name in ("ci_failed", "ci_cancelled", "behind_too_long", "fetch_failed",
                    "update_did_not_happen", "not_on_the_remote"):
            assert rows and rows[0]["level"] in ("warning", "danger"), name


class TestTheTopBar:
    def _get(self, monkeypatch, value, last=NO_UPDATE_ASKED):
        import app as A
        _last(monkeypatch, last)
        monkeypatch.setattr("modules.reader_job.read_cached",
                            lambda name: _cached(value) if name == "app-pushed" else
                            {"state": "absent", "doc": None, "why": "not in this test"})
        return A.app.test_client().get("/v2/update-available")

    def test_an_installable_update_is_a_neutral_link_to_the_update_page(self, monkeypatch,
                                                                        running):
        r = self._get(monkeypatch, _value())
        body = r.get_data(as_text=True)
        assert r.status_code == 200 and 'class="update-pill"' in body
        assert 'href="/v2/update"' in body and "Update" in body and "available" in body
        assert 'title="3 commits behind origin/main' in body
        assert "warn" not in body and "danger" not in body         # neutral, not a problem
        assert "script-src" in (r.headers.get("Content-Security-Policy") or "")

    @pytest.mark.parametrize("value,last", [
        (_value(ci={"tip": TIP, "state": "pending"}), NO_UPDATE_ASKED),
        (_value(ci={"tip": TIP, "state": "failed"}), NO_UPDATE_ASKED),
        (_value(), FAILED_UPDATE),
        (_value(state="at_tip", tip=RUN, behind=0), NO_UPDATE_ASKED)])
    def test_nothing_is_drawn_otherwise(self, monkeypatch, running, value, last):
        assert "update-pill" not in self._get(monkeypatch, value, last).get_data(as_text=True)

    def test_a_comparison_for_another_commit_draws_nothing(self, monkeypatch, running):
        body = self._get(monkeypatch, _value(running="c" * 40)).get_data(as_text=True)
        assert "update-pill" not in body

    def test_every_page_carries_the_slot_and_it_redraws_when_the_reader_runs(self):
        import app as A
        page = A.app.test_client().get("/v2/").get_data(as_text=True)
        slot = page[page.index('id="nmas-update"') - 60:page.index('id="nmas-update"') + 200]
        assert 'hx-get="/v2/update-available"' in slot
        assert "nmas:app_version from:body" in slot
