"""The top bar's quiet "Update available" (the operator, 2026-10-02): an update is news,
not a problem, but it should be noticeable where a person looks, not only on Help > About.

- It is drawn only when origin/main is ahead AND CI passed a commit since the running one
  (the Update operation's target, C436), neutral in colour, and opens the Update page; its
  hover says how many commits it installs and since when.
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
    """The reader's value (C436 shape): its target is the tip exactly when the tip's verdict
    is a pass, unless the case names ``verdicts`` or ``target``."""
    v = {"running": RUN, "tip": TIP, "state": "behind", "behind": 3, "branch": "main",
         "behind_since": _iso(600), "ci": {"tip": TIP, "state": "verified"}}
    v.update(over)
    ci = v.get("ci") or {}
    v.setdefault("verdicts", {ci["tip"]: ci} if ci.get("tip") else {})
    v.setdefault("target", v["tip"] if ci.get("tip") == v["tip"] and ci.get("state") == "verified"
                 else "")
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
        # Judged against a stated clock an hour after the date it prints: on the real clock
        # the 20 h "behind too long" rule hid the pill from 2026-10-03T10:05Z (C353's survey).
        import calendar
        now = calendar.timegm(time.strptime("2026-10-02T15:05:00Z", "%Y-%m-%dT%H:%M:%SZ"))
        got = attention.update_available(_value(behind_since="2026-10-02T14:05:00Z"),
                                         last=NO_UPDATE_ASKED, now=now)
        assert got["title"].startswith("3 commits to install from origin/main (aaaaaaa → bbbbbbb)")
        assert "CI passed" in got["title"] and "since 2026-10-02 14:05 UTC" in got["title"]
        one = attention.update_available(_value(behind=1), last=NO_UPDATE_ASKED)
        assert one["title"].startswith("1 commit to install")

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

    def _offerable(self, monkeypatch, gates=None, loops=()):
        """The in-app path's own gates (C2337): the installed updater's, and the SDN loops."""
        from modules import update_op as U
        monkeypatch.setattr(U, "updater_gates", lambda install=None: set(
            U.SAFE_DEPLOY_GATES if gates is None else gates))
        monkeypatch.setattr(U, "sdn_loops_running", lambda: list(loops))

    def test_an_installable_update_is_a_neutral_link_to_the_update_page(self, monkeypatch,
                                                                        running):
        self._offerable(monkeypatch)
        r = self._get(monkeypatch, _value())
        body = r.get_data(as_text=True)
        assert r.status_code == 200 and 'class="update-pill"' in body
        assert 'href="/v2/update"' in body and "Update" in body and "available" in body
        assert 'title="3 commits to install from origin/main' in body
        assert "warn" not in body and "danger" not in body         # neutral, not a problem
        assert "script-src" in (r.headers.get("Content-Security-Policy") or "")

    @pytest.mark.parametrize("gates,loops,words", [
        ((), (), "the in-app update does not yet run the refusal while an SDN loop runs, the page "
                 "smoke after the restart (rolling back on a failure) (deploy through the "
                 "safe-deploy script)"),
        (None, ("sdn_lab",), "an SDN loop runs on sdn_lab")])
    def test_held_it_names_the_commit_and_why(self, monkeypatch, running, gates, loops, words):
        """C2337 (the operator, 2026-11-03): until the in-app update runs the safe-deploy
        script's gates, the pill names the commit it would install and is drawn held, saying
        why; it still opens the Update page, whose gates refuse its Confirm."""
        import html as _h
        self._offerable(monkeypatch, gates=gates, loops=loops)
        body = _h.unescape(self._get(monkeypatch, _value()).get_data(as_text=True))
        assert 'class="update-pill update-pill-held"' in body and 'href="/v2/update"' in body
        assert f"Update to {TIP[:7]}: not offered: {words}" in body, body[:900]
        assert f" to {TIP[:7]} (held)" in body

    def test_on_a_laptop_kit_it_is_held_saying_a_kit_updates_by_repin(self, monkeypatch,
                                                                      running):
        """A laptop kit is moved only by `kit repin <sha>` (docs/LAB9_LAPTOP_RUN.md): the pill
        is drawn held with that alone, never offering the update, even with every in-app
        gate passing; the safe-deploy script's advice is the host's, not the kit's."""
        import html as _h

        from modules import installation_kind as K
        self._offerable(monkeypatch)
        monkeypatch.setattr(K, "kind", lambda: K.LAPTOP_KIT)
        body = _h.unescape(self._get(monkeypatch, _value()).get_data(as_text=True))
        assert 'class="update-pill update-pill-held"' in body, body[:900]
        assert (f"Update to {TIP[:7]}: not offered: a laptop kit updates by `kit repin <sha>`, "
                "docs/LAB9_LAPTOP_RUN.md\"") in body, body[:900]
        assert "safe-deploy" not in body and f" to {TIP[:7]} (held)" in body
        # Pressed: the pill's link opens the Update page, which says how a kit updates and
        # whose every Update button is disabled.
        import re

        import app as A
        href = re.search(r'<a class="update-pill update-pill-held" href="([^"]+)"', body).group(1)
        page = _h.unescape(A.app.test_client().get(href).get_data(as_text=True))
        assert "a laptop kit updates by `kit repin <sha>`" in page, page[:900]
        posts = re.findall(r'<button[^>]*id="update-confirm"[^>]*hx-post="/update/apply"[^>]*>',
                           page)
        assert posts and all(re.search(r"\sdisabled[\s>]", b) for b in posts), posts
        # And what that button would send, sent anyway, is refused naming the kind.
        sent = re.search(r"hx-vals='(\{[^']*\})'", posts[0]).group(1)
        import json

        from modules import update_op
        before = update_op.pending()
        r = A.app.test_client().post("/update/apply", data=json.loads(sent))
        assert r.status_code == 409, r.get_data(as_text=True)[:600]
        assert "this installation's kind is laptop_kit" in _h.unescape(r.get_data(as_text=True))
        assert update_op.pending() == before, "a kit's refused update left a request behind"

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
