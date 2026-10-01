"""UPDATE WHEN CI PASSES (the operator, 2026-09-30): the Update page offers to
wait for CI instead of telling the person to run `nmas-deploy --wait`, and
every refusal is worded for a person.

The wait is the person's confirm, recorded; the `app-pushed` reader releases it
after each read. The request it writes is the UPDATER'S OWN exact fields (its
`validate()` is the seam), dated now, so a wait longer than the updater's
staleness bound still yields a request it accepts. Every other ending (CI
failed or cancelled, a newer release, the bound, another gate) ends the wait
in words and updates nothing.
"""
import json
import os
import time

import pytest

from tests.test_update_button import _plan_kw, _updater, _value

PENDING = {"tip": "b" * 40, "state": "pending", "asked_at": "2026-09-30T10:01:00Z",
           "sentence": "PENDING: CI run #120 is still in_progress for bbbbbbbbbb: <url>. Wait, "
                       "and run nmas-deploy again when it completes, or run `nmas-deploy --wait`"}
VERIFIED = {"tip": "b" * 40, "state": "verified", "asked_at": "2026-09-30T10:05:00Z",
            "sentence": "CI passed for bbbbbbbbbb: run #120"}


@pytest.fixture
def store(tmp_path, monkeypatch):
    from modules import update_op
    for name, rel in (("REQUEST_DIR", "requests"), ("STAGING_DIR", "staging"),
                      ("AUDIT", "audit.jsonl"), ("DEFERRED", "deferred.json"),
                      ("DEFERRED_OUTCOME", "deferred_outcome.json")):
        monkeypatch.setattr(update_op, name, str(tmp_path / rel))
    return tmp_path


def _kw(ci=None, **over):
    kw = _plan_kw(value=_value(ci=dict(ci or PENDING), **over))
    kw["holder"] = ""
    return kw


def _defer(**over):
    from modules import update_op
    kw = _kw(**over)
    p = update_op.plan(waiting={}, **kw)
    return update_op.defer(p["hash"], ["c" * 40], "person@example.invalid", **kw), p


class TestTheOffer:
    def test_ci_still_checking_is_the_only_thing_in_the_way(self, store):
        from modules import update_op
        p = update_op.plan(**_kw())
        assert not p["selectable"] and p["waitable"]
        assert p["ci_words"].startswith("CI is still checking this release")
        assert "nmas-deploy" not in p["ci_words"] and "nmas-deploy" not in p["why_not"]

    def test_another_gate_failing_offers_no_wait(self, store):
        from modules import update_op
        p = update_op.plan(**_kw(checkout_changes=["M app.py"]))
        assert not p["waitable"]
        p = update_op.plan(**_kw(ci={"tip": "b" * 40, "state": "failed", "sentence": "x"}))
        assert not p["waitable"]
        assert p["ci_words"].startswith("CI failed for this release")

    def test_the_page_offers_it_in_words_with_the_cause_on_hover(self, store, monkeypatch):
        import app as A
        from modules import update_op
        real = update_op.plan
        monkeypatch.setattr(update_op, "plan", lambda **kw: real(**_kw()))
        html = A.app.test_client().get("/v2/update/panel").get_data(as_text=True)
        assert 'data-when="ci"' in html and "when CI passes</button>" in html
        assert "CI is still checking this release" in html
        assert 'title="PENDING: CI run #120' in html          # the cause, on hover
        assert 'id="update-why-not"' not in html


class TestTheWait:
    def test_a_confirmed_wait_is_recorded_and_writes_no_request(self, store):
        from modules import update_op
        got, _p = _defer()
        assert got["ok"] and got["waiting"]
        assert not (store / "requests").exists() or os.listdir(store / "requests") == []
        d = update_op.deferred()
        assert d["target"] == "b" * 40 and d["requested_by"] == "person@example.invalid"
        assert d["acknowledged_host_steps"] == ["c" * 40]
        rows = [json.loads(l) for l in open(store / "audit.jsonl")]
        assert rows[-1]["waiting_for_ci"] is True

    def test_a_wait_refuses_what_an_update_refuses(self, store):
        from modules import update_op
        kw = _kw()
        p = update_op.plan(waiting={}, **kw)
        assert not update_op.defer(p["hash"], [], "p@example.invalid", **kw)["ok"]   # host step
        assert not update_op.defer("0" * 16, ["c" * 40], "p@example.invalid", **kw)["ok"]
        assert not update_op.defer(p["hash"], ["c" * 40], "", **kw)["ok"]
        assert update_op.deferred() == {}

    def test_a_second_wait_is_refused_naming_the_first(self, store):
        from modules import update_op
        _defer()
        p = update_op.plan(**_kw())
        assert not p["waitable"]
        assert "is waiting for CI, asked by person@example.invalid" in p["why_not"]

    def test_ci_already_passed_updates_now(self, store):
        from modules import update_op
        kw = _kw(ci=VERIFIED)
        p = update_op.plan(**kw)
        got = update_op.defer(p["hash"], ["c" * 40], "p@example.invalid", **kw)
        assert got["ok"] and not got.get("waiting") and len(got["id"]) == 16

    def test_stop_waiting_updates_nothing_and_says_who(self, store):
        from modules import update_op
        _defer()
        assert update_op.stop_waiting("other@example.invalid")["ok"]
        assert update_op.deferred() == {}
        e = update_op.deferred_outcome()
        assert e["outcome"] == "stopped" and "other@example.invalid" in e["words"]
        assert not (store / "requests").exists() or os.listdir(store / "requests") == []


class TestTheRelease:
    def test_still_pending_keeps_waiting(self, store):
        from modules import update_op
        _defer()
        assert update_op.release_deferred(**_kw()) is None
        assert update_op.deferred()["target"] == "b" * 40

    def test_ci_passing_writes_the_persons_request_the_updater_accepts(self, store):
        from modules import update_op
        _defer()
        ended = update_op.release_deferred(**_kw(ci=VERIFIED))
        assert ended["outcome"] == "requested" and len(ended["request_id"]) == 16
        (name,) = os.listdir(store / "requests")
        doc = json.loads((store / "requests" / name).read_text())
        assert doc["requested_by"] == "person@example.invalid"
        assert doc["id"] == ended["request_id"] and doc["acknowledged_host_steps"] == ["c" * 40]
        assert _updater().validate(doc, time.time()) == doc       # the SEAM
        assert update_op.deferred() == {}

    def test_a_request_dated_at_release_not_at_the_confirm(self, store, monkeypatch):
        """The updater refuses a request older than its staleness bound; a wait
        can be longer, so the request is dated when it is written."""
        from modules import update_op
        _defer()
        d = json.loads((store / "deferred.json").read_text())
        d["requested_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 900))
        (store / "deferred.json").write_text(json.dumps(d))
        update_op.release_deferred(**_kw(ci=VERIFIED))
        (name,) = os.listdir(store / "requests")
        doc = json.loads((store / "requests" / name).read_text())
        assert _updater().validate(doc, time.time()) == doc

    @pytest.mark.parametrize("state,words", [("failed", "CI failed for this release"),
                                             ("cancelled", "CI's check of this release was stopped")])
    def test_ci_that_will_never_pass_ends_the_wait_in_words(self, store, state, words):
        from modules import update_op
        _defer()
        ended = update_op.release_deferred(**_kw(ci={"tip": "b" * 40, "state": state,
                                                     "sentence": "x"}))
        assert ended["outcome"] == f"ci_{state}" and words in ended["words"]
        assert "nothing was updated" in ended["words"]
        assert not (store / "requests").exists() or os.listdir(store / "requests") == []

    def test_a_newer_release_is_never_installed_in_its_place(self, store):
        from modules import update_op
        _defer()
        newer = dict(VERIFIED, tip="d" * 40)
        ended = update_op.release_deferred(**_kw(ci=newer, tip="d" * 40))
        assert ended["outcome"] == "superseded" and "dddddddddd" in ended["words"]
        assert not (store / "requests").exists() or os.listdir(store / "requests") == []

    def test_past_the_bound_it_gives_up(self, store):
        from modules import update_op
        _defer()
        later = time.time() + update_op.DEFER_BOUND_S + 5
        ended = update_op.release_deferred(clock=lambda: later, **_kw())
        assert ended["outcome"] == "gave_up" and "nothing was updated" in ended["words"]

    def test_another_gate_failing_at_release_updates_nothing(self, store):
        from modules import update_op
        _defer()
        ended = update_op.release_deferred(**_kw(ci=VERIFIED, checkout_changes=["M app.py"]))
        assert ended["outcome"] == "refused" and "M app.py" in ended["words"]

    def test_the_ending_is_drawn_on_the_page_until_an_update_supersedes_it(self, store):
        from modules import update_op
        _defer()
        update_op.release_deferred(**_kw(ci={"tip": "b" * 40, "state": "failed", "sentence": "x"}))
        p = update_op.plan(**_kw())
        assert p["wait_ended"]["outcome"] == "ci_failed"
        later = dict(_kw(), now_outcome={"state": "ok", "value": {
            "outcome": "updated", "ended_at": "2999-01-01T00:00:00Z"}})
        assert update_op.plan(**later)["wait_ended"] == {}


class TestTheReaderReleasesIt:
    def test_the_app_pushed_reader_runs_the_release_after_storing(self, store, monkeypatch):
        from modules import reader_job, update_op
        from modules.readers import app_pushed
        called = []
        monkeypatch.setattr(update_op, "release_deferred", lambda: called.append(1) or {"x": 1})
        assert app_pushed.READER.after_store() == {"x": 1} and called == [1]

    def test_a_reader_that_acted_announces_and_one_that_raised_still_stores(self, store):
        from modules import reader_job
        heard = []
        r = reader_job.Reader(name="t-after", what="w", endpoints=("e",), interval_seconds=60,
                              interval_basis="b", read=lambda: {"v": 1}, invalidates=("app_version",),
                              announce_if=lambda a, b: False, announce_at_least_every=10 ** 9,
                              after_store=lambda: {"acted": True})
        reader_job._LAST_ANNOUNCED[r.name] = time.time()
        reader_job.run_once(r, announce=lambda *a: heard.append(a))
        assert heard                                   # acted: announced though unchanged
        boom = reader_job.Reader(**{**r.__dict__, "name": "t-after-2",
                                    "after_store": lambda: 1 / 0})
        reader_job._LAST_ANNOUNCED[boom.name] = time.time()
        doc = reader_job.run_once(boom, announce=lambda *a: None)
        assert doc["last_attempt"]["ok"] is True


class TestTheRoute:
    def test_wait_and_stop_through_the_route(self, store, monkeypatch):
        import app as A
        from modules import identity, update_op
        monkeypatch.setattr(identity, "request_actor", lambda: "person@example.invalid")
        real = update_op.plan
        monkeypatch.setattr(update_op, "plan", lambda **kw: real(**{**_kw(), **kw}))
        h = real(**_kw())["hash"]
        c = A.app.test_client()
        r = c.post("/update/apply", json={"hash": h, "acknowledged": ["c" * 40], "when": "ci"})
        assert r.status_code == 202 and r.get_json()["waiting"] is True
        assert "starts when CI passes" in r.get_json()["message"]
        r = c.post("/update/apply", json={"when": "stop"})
        assert r.status_code == 200 and update_op.deferred() == {}
        r = c.post("/update/apply", json={"when": "stop"})
        assert r.status_code == 409 and "nothing is waiting" in r.get_json()["error"]


class TestTheShippedClient:
    def _js(self):
        import dukpy  # noqa: F401
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent / "static/js/nmas_update.js").read_text()

    def _call(self, status, target):
        import dukpy
        return dukpy.evaljs([self._js(), "NMAS_UPDATE.waitOutcome(dukpy.s, dukpy.t)"],
                            s=status, t=target)

    def test_the_page_follows_the_wait_to_its_end(self):
        t = "b" * 40
        assert self._call({"waiting": {"target": t}}, t)["state"] == "waiting"
        r = self._call({"waiting": {}, "wait_ended": {"target": t, "outcome": "requested",
                                                      "request_id": "0123456789abcdef"}}, t)
        assert r == {"state": "requested", "id": "0123456789abcdef", "words": ""}
        r = self._call({"waiting": {}, "wait_ended": {"target": t, "outcome": "ci_failed",
                                                      "words": "CI found a problem"}}, t)
        assert r["state"] == "ended" and "CI found a problem" in r["words"]
        assert self._call(None, t)["state"] == "unknown"     # a failed read decides nothing

    def test_the_click_sends_when_and_the_component_has_a_stop(self):
        js = self._js()
        assert "when: el.getAttribute('data-when') || ''" in js
        assert "body: JSON.stringify({when: 'stop'})" in js
        assert "addEventListener('nmas:app_version', heard)" in js


class TestAFailedReleaseReadsAsAFailure:
    """The operator, 2026-10-01: run #241 failed and the page said "could_not_ask".
    A definite failure is said as one, naming the run, and ends a wait."""

    FAILED = {"tip": "b" * 40, "state": "failed", "asked_at": "2026-10-01T09:00:00Z",
              "sentence": "FAILED: bbbbbbbbbb has no run of its own (its paths are ones CI "
                          "skips), and the nearest ancestor with one, aaaaaaaaaa, failed: run "
                          "#241 concluded failure."}

    def test_the_words_name_the_run(self):
        from modules import update_op
        words = update_op.person_ci(self.FAILED, "b" * 40)
        assert words == ("CI failed for this release (run #241): it will not be installed. "
                         "A fix needs a new release")

    def test_without_a_run_number_it_still_says_failed(self):
        from modules import update_op
        words = update_op.person_ci({"tip": "b" * 40, "state": "failed", "sentence": "x"})
        assert words == "CI failed for this release: it will not be installed. A fix needs a new release"
        # The tool never promises what it cannot know (the operator, 2026-10-01).
        from modules.update_op import CI_PERSON
        assert not any("next release" in w for w in CI_PERSON.values())

    def test_a_wait_ends_on_it(self, store):
        from modules import update_op
        _defer()
        out = update_op.release_deferred(**_kw(ci=self.FAILED))
        assert out.get("outcome") == "ci_failed" and update_op.deferred() == {}
        assert out["words"].startswith("CI failed for this release (run #241)")

    def test_the_badge_is_words_never_the_key(self, store, monkeypatch):
        import app as A
        from modules import update_op
        real = update_op.plan
        for ci, word in ((self.FAILED, ">failed<"),
                         ({"tip": "b" * 40, "state": "could_not_ask", "sentence": "x"},
                          ">not asked<")):
            monkeypatch.setattr(update_op, "plan", lambda ci=ci, **kw: real(**_kw(ci=ci)))
            html = A.app.test_client().get("/v2/update/panel").get_data(as_text=True)
            assert word in html
            assert "could_not_ask" not in html.replace('data-', '')


class TestTheLastUpdateByEitherRoute:
    """The operator, 2026-10-01: the panel showed the button's e7b80c7 -> 771bead and
    not the terminal deploy 771bead -> 1954ce7 after it."""

    BUTTON = {"state": "ok", "value": {"outcome": "updated", "from": "e7b80c7" + "0" * 33,
                                       "to": "771bead" + "0" * 33, "step": "confirmed",
                                       "requested_by": "person@example.invalid",
                                       "ended_at": "2026-09-30T20:00:00Z"}}

    def _audit(self, tmp_path, *rows):
        path = tmp_path / "deploy_audit.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return str(path)

    def test_a_newer_terminal_deploy_is_the_last_update(self, tmp_path):
        from modules import update_op
        path = self._audit(tmp_path,
                           {"user": "op", "exit": 0, "from": "771bead" + "0" * 33,
                            "to": "1954ce7" + "0" * 33, "ended_at": "2026-09-30T21:00:00.123Z"},
                           {"user": "op", "exit": 1, "verdict": "FAILED", "ended_at":
                            "2026-09-30T22:00:00.000Z"},                    # refused: not one
                           {"user": "op", "exit": 0, "from": "1954ce7" + "0" * 33,
                            "to": "1954ce7" + "0" * 33, "ended_at": "2026-09-30T23:00:00.000Z"})
        got = update_op.last_update(self.BUTTON, update_op.terminal_deploy(path))
        v = got["value"]
        assert v["route"] == "terminal" and v["to"].startswith("1954ce7")
        assert v["from"].startswith("771bead") and v["requested_by"] == "op"

    def test_an_older_terminal_deploy_leaves_the_button_shown(self, tmp_path):
        from modules import update_op
        path = self._audit(tmp_path, {"user": "op", "exit": 0, "from": "a" * 40, "to": "b" * 40,
                                      "ended_at": "2026-09-30T19:00:00.000Z"})
        assert update_op.last_update(self.BUTTON, update_op.terminal_deploy(path)) == self.BUTTON

    def test_no_record_or_an_unreadable_one_is_none(self, tmp_path):
        from modules import update_op
        assert update_op.terminal_deploy(str(tmp_path / "absent.jsonl")) == {}
        assert update_op.last_update(self.BUTTON, {}) == self.BUTTON

    def test_the_panel_draws_it_with_how_and_no_raw_step(self, store, monkeypatch, tmp_path):
        import app as A
        from modules import update_op
        monkeypatch.setattr(update_op, "DEPLOY_AUDIT", self._audit(
            tmp_path, {"user": "op", "exit": 0, "from": "771bead" + "0" * 33,
                       "to": "1954ce7" + "0" * 33, "ended_at": "2026-09-30T21:00:00.123Z"}))
        real = update_op.plan
        monkeypatch.setattr(update_op, "plan",
                            lambda **kw: real(**{**_kw(), "now_outcome": self.BUTTON}))
        html = A.app.test_client().get("/v2/update/panel").get_data(as_text=True)
        last = html[html.index('id="update-last"'):]
        last = last[:last.index("</section>")]
        assert "1954ce7" in last and "a terminal deploy (nmas-deploy) by op" in last
        assert "updated: " not in last and ": wait" not in last


class TestARedrawAfterTheReleaseKeepsTheStepper:
    """The wait no longer holds the panel (2026-10-01), so a redraw can land
    between the release and the page hearing of it: the server then draws the
    request to follow, while its update has not finished."""

    NOW = 1_790_000_000.0
    AT = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - 60))
    ENDED = {"outcome": "requested", "request_id": "r1", "target": "b" * 40, "ended_at": AT}

    def _f(self, ended=None, last=None, running="a" * 40, now=None):
        from modules import update_op
        return update_op.following(self.ENDED if ended is None else ended,
                                   last or {"state": "absent"}, running,
                                   clock=lambda: now or self.NOW)

    def test_a_released_request_not_finished_is_followed(self):
        assert self._f() == "r1"
        assert self._f(last={"state": "ok", "value": {"id": "r1", "outcome": "running"}}) == "r1"

    def test_finished_running_its_target_or_past_the_limit_is_not(self):
        from modules import update_op
        for outcome in update_op.FINISHED:
            assert self._f(last={"state": "ok", "value": {"id": "r1", "outcome": outcome}}) == ""
        assert self._f(running="b" * 40) == ""               # the app runs it: no reload loop
        assert self._f(now=self.NOW + update_op.UPDATER_TIMEOUT_S + 1) == ""
        assert self._f(ended=dict(self.ENDED, outcome="ci_failed")) == ""
        assert self._f(ended={}) == ""

    def test_the_panel_draws_it(self, store, monkeypatch):
        import app as A
        from modules import update_op
        real = update_op.plan
        monkeypatch.setattr(update_op, "plan", lambda **kw: dict(real(**_kw()), following="r1"))
        html = A.app.test_client().get("/v2/update/panel").get_data(as_text=True)
        assert 'data-follow-id="r1"' in html
        monkeypatch.setattr(update_op, "plan", lambda **kw: real(**_kw()))
        assert "data-follow-id" not in A.app.test_client().get("/v2/update/panel").get_data(as_text=True)


class TestAnEndedWaitForAnotherReleaseIsHistory:
    """The operator, 2026-10-01: above "Update to 8f1676c02d" the page still
    said "The wait for CI ended 35 min ago: CI failed for this release ...
    (asked for 9fd781bcbf)", a wait for an OLDER release after a newer one had
    passed. Above the button only while it concerns the release offered."""

    def _ended_for_b(self):
        from modules import update_op
        _defer()
        update_op.release_deferred(**_kw(ci={"tip": "b" * 40, "state": "failed",
                                             "sentence": "FAILED: run #245"}))

    def test_about_the_release_offered_it_stays_above_the_button(self, store):
        from modules import update_op
        self._ended_for_b()
        p = update_op.plan(**_kw())
        assert p["wait_ended"]["outcome"] == "ci_failed" and p["wait_ended_earlier"] == {}

    def test_about_another_release_it_moves_to_earlier_updates(self, store, monkeypatch):
        import app as A
        from modules import update_op
        self._ended_for_b()
        newer = {"tip": "e" * 40, "state": "verified", "sentence": "CI passed"}
        p = update_op.plan(**_kw(ci=newer, tip="e" * 40))
        assert p["wait_ended"] == {}
        assert p["wait_ended_earlier"]["target"] == "b" * 40
        real = update_op.plan
        monkeypatch.setattr(update_op, "plan",
                            lambda **kw: real(**_kw(ci=newer, tip="e" * 40)))
        html = A.app.test_client().get("/v2/update/panel").get_data(as_text=True)
        assert 'id="update-wait-ended"' not in html
        earlier = html[html.index('id="update-history"'):]
        assert 'id="update-wait-ended-earlier"' in earlier and "bbbbbbbbbb" in earlier
        assert "CI failed for this release" in earlier
