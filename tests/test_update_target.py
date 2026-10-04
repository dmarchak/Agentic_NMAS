"""The Update operation's target is the NEWEST commit CI passed (C436; the operator, 2026-10-04).

The button considered only origin/main's tip. While commits are pushed every few minutes the
tip's CI is nearly always running, so it waited even when an older commit had passed. And the
updater refused a confirmed commit CI had passed because a later push moved the tip:
"origin/main is now bb179f7ddf, not 7992a15823 as confirmed".

Now:
- the reader asks CI newest first and stops at the first pass: that commit is the target. A
  cancelled, failed or pending commit is never a target, and nothing older than the running
  commit is in the chain at all;
- the commits beyond the target are said, counted by CI state, and never offered;
- the host steps are exactly those of the commits up to the target;
- the updater lands exactly the confirmed commit while it is still on origin/main.

The operator's four tests, driven through the real reader (`enrich` on a real repository, CI's
verdicts scripted per commit), the real plan and request, and the real updater:
- tip pending, an older commit passed: the older is offered and applied;
- the tip moving between confirm and apply: the confirmed commit is applied;
- a cancelled commit is never a target;
- nothing passed since the running commit: nothing is offered.
"""

import json
import os

import pytest

from tests.test_update_button import _g, _gate, _plan_kw, _run, repos  # noqa: F401 (fixture)


def _codes():
    from modules.readers import ci_verdict as CV
    mod = CV.deploy_script()
    return {"passed": (mod.OK, "CI passed"), "pending": (mod.CI_PENDING, "PENDING: run #2"),
            "cancelled": (mod.CI_CANCELLED, "CANCELLED: run #3"),
            "failed": (mod.CI_REFUSED, "FAILED: run #4")}


def _verdicts(states: dict, asked: list):
    """CI's verdict per commit, scripted; every ask recorded, in order."""
    codes = _codes()

    def verdict(root, sha):
        asked.append(sha)
        return codes[states.get(sha, "pending")]
    return verdict


def _read(repos, states, previous=None, wanted=""):
    from modules.readers import app_pushed as P

    asked = []
    v = P.judge(str(repos["work"]), repos["shas"][0])
    out = P.enrich(str(repos["work"]), v, previous or {}, verdict=_verdicts(states, asked),
                   jobs=lambda run: {"steps": []}, wanted=wanted)
    return out, asked


@pytest.fixture
def store(tmp_path, monkeypatch):
    from modules import update_op
    for name, rel in (("REQUEST_DIR", "requests"), ("STAGING_DIR", "staging"),
                      ("AUDIT", "audit.jsonl"), ("DEFERRED", "deferred.json"),
                      ("DEFERRED_OUTCOME", "deferred_outcome.json")):
        monkeypatch.setattr(update_op, name, str(tmp_path / rel))
    return tmp_path


def _plan(value, **kw):
    from modules import update_op
    args = _plan_kw(value=value)
    args["holder"] = ""
    args["waiting"] = {}
    args.update(kw)
    return update_op.plan(**args)


class TestTheOffer:
    def test_tip_pending_and_an_older_passed_offers_the_older_and_it_is_applied(self, repos,
                                                                              store):
        c0, c1, c2 = repos["shas"]
        v, asked = _read(repos, {c2: "pending", c1: "passed"})
        assert v["target"] == c1 and v["ci"]["tip"] == c2 and v["ci"]["state"] == "pending"
        assert asked == [c2, c1], "asked out of order, or past the first pass"
        p = _plan(dict(v, running=c0), running=c0)
        assert p["selectable"], p["why_not"]
        f = p["facts"]
        assert f["target"] == c1 and [c["sha"] for c in f["commits"]] == [c1]
        assert f["beyond_words"] == "1 newer: 1 running CI"
        assert [s["sha"] for s in f["host_steps"]] == [c1]
        # Applied: the person's request, through the real updater.
        from modules import update_op
        got = update_op.request(p["hash"], [c1], "person@example.invalid",
                                **dict(_plan_kw(value=dict(v, running=c0)), running=c0,
                                       holder="", waiting={}))
        assert got["ok"], got
        doc = json.loads((store / "requests" / f"{got['id']}.json").read_text())
        assert doc["target"] == c1
        restarts = []
        _U, rec = _run(repos, doc, _gate(), restarts)
        assert rec["outcome"] == "updated"
        assert _g(repos["work"], "rev-parse", "HEAD") == c1

    def test_the_tip_moving_between_confirm_and_apply_applies_the_confirmed_commit(self, repos,
                                                                                  store):
        c0, c1, c2 = repos["shas"]
        v, _asked = _read(repos, {c2: "passed"})
        assert v["target"] == c2
        from modules import update_op
        kw = dict(_plan_kw(value=dict(v, running=c0)), running=c0, holder="", waiting={})
        p = update_op.plan(**kw)
        got = update_op.request(p["hash"], [c1], "person@example.invalid", **kw)
        doc = json.loads((store / "requests" / f"{got['id']}.json").read_text())
        # A push lands after the confirm and before the updater runs.
        (repos["work"] / "h").write_text("4")
        _g(repos["work"], "checkout", "-q", c2)
        _g(repos["work"], "add", "h")
        _g(repos["work"], "commit", "-q", "-m", "c3")
        c3 = _g(repos["work"], "rev-parse", "HEAD")
        _g(repos["work"], "push", "-q", "origin", "HEAD:main")
        _g(repos["work"], "checkout", "-q", "main")
        _g(repos["work"], "reset", "-q", "--hard", c0)
        _U, rec = _run(repos, doc, _gate(), [])
        assert rec["outcome"] == "updated"
        assert _g(repos["work"], "rev-parse", "HEAD") == c2
        assert _g(repos["work"], "rev-parse", "origin/main") == c3

    def test_a_cancelled_commit_is_never_a_target(self, repos):
        c0, c1, c2 = repos["shas"]
        v, _asked = _read(repos, {c2: "cancelled", c1: "cancelled"})
        assert v["target"] == ""
        v, _asked = _read(repos, {c2: "pending", c1: "cancelled"})
        assert v["target"] == ""
        p = _plan(dict(v, running=c0), running=c0)
        assert not p["selectable"] and p["facts"]["target"] == c2
        assert "CI passed the target" in p["why_not"]
        v, _asked = _read(repos, {c2: "cancelled", c1: "passed"})
        assert v["target"] == c1

    def test_nothing_passed_since_the_running_commit_offers_nothing(self, repos):
        c0, c1, c2 = repos["shas"]
        v, asked = _read(repos, {c2: "failed", c1: "cancelled"})
        assert v["target"] == "" and c0 not in asked, "the running commit, or older, was asked"
        p = _plan(dict(v, running=c0), running=c0)
        assert not p["selectable"] and not p["waitable"]
        assert "no commit since the running one has passed CI" in p["why_not"]

    def test_a_pending_tip_with_nothing_passed_is_the_wait(self, repos):
        c0, c1, c2 = repos["shas"]
        v, _asked = _read(repos, {c2: "pending", c1: "failed"})
        p = _plan(dict(v, running=c0), running=c0)
        assert not p["selectable"] and p["waitable"] and p["facts"]["target"] == c2


class TestTheHostSteps:
    def test_the_preview_lists_exactly_the_steps_up_to_the_target(self):
        """A step in a commit beyond the target is not this update's: not listed, not ticked,
        and not in the hash."""
        from tests.test_update_button import _value

        b, c = "b" * 40, "c" * 40
        pending = {"tip": b, "state": "pending", "sentence": "PENDING"}
        passed = {"tip": c, "state": "verified", "sentence": "CI passed"}
        v = _value(ci=pending, verdicts={b: pending, c: passed}, target=c,
                   host_steps=[{"sha": b, "step": "on the tip, beyond the target"},
                               {"sha": c, "step": "on the target"}],
                   after_steps=[{"sha": b, "step": "after, beyond", "when": "after"}],
                   updater_by_sha={b: ["deploy/update/nmas-update"]})
        p = _plan(v)
        assert p["selectable"], p["why_not"]
        assert [s["step"] for s in p["facts"]["host_steps"]] == ["on the target"]
        assert p["facts"]["after_steps"] == [] and p["facts"]["updater_changes"] == []
        assert p["facts"]["behind"] == 1


class TestTheAsks:
    def test_a_final_verdict_is_asked_once_and_a_pending_one_again(self, repos):
        c0, c1, c2 = repos["shas"]
        first, asked = _read(repos, {c2: "pending", c1: "passed"})
        assert asked == [c2, c1]
        again, asked = _read(repos, {c2: "pending", c1: "passed"}, previous=first)
        assert asked == [c2] and again["target"] == c1

    def test_the_commit_a_wait_is_for_is_asked_past_the_target(self, repos):
        c0, c1, c2 = repos["shas"]
        v, asked = _read(repos, {c2: "passed", c1: "pending"}, wanted=c1)
        assert v["target"] == c2 and asked == [c2, c1]
        assert v["verdicts"][c1]["state"] == "pending"

    def test_one_read_asks_at_most_its_bound(self, monkeypatch):
        from modules.readers import app_pushed as P

        monkeypatch.setattr(P, "ASKS_PER_READ", 3)
        chain = [f"{i:x}" * 40 for i in range(1, 9)]
        asked = []
        got = P._target("/nonexistent", [c[:40] for c in chain], {}, 0.0,
                        verdict=_verdicts({}, asked))
        assert len(asked) == 3 and got["target"] == "" and got["asks_cut"] is True


class TestTheWords:
    @pytest.mark.parametrize("states,words", [
        ([], ""),
        (["pending"], "1 newer: 1 running CI"),
        (["pending", "cancelled", "cancelled"], "3 newer: 1 running CI, 2 cancelled"),
        (["failed", None], "2 newer: 1 failed, 1 not asked yet")])
    def test_what_lies_beyond_is_counted_by_state(self, states, words):
        from modules.readers import app_pushed as P
        assert P.beyond_words([{"sha": str(i), "state": s} for i, s in enumerate(states)]) == words

    def test_a_failed_tip_with_an_older_pass_never_says_there_is_nothing_to_update(self):
        from modules import attention
        from tests.test_update_button import _value

        b, c = "b" * 40, "c" * 40
        failed = {"tip": b, "state": "failed", "sentence": "FAILED: run #4"}
        passed = {"tip": c, "state": "verified", "sentence": "CI passed"}
        v = _value(ci=failed, verdicts={b: failed, c: passed}, target=c)
        what, action = attention.ci_refused_words(v)
        assert what.startswith("CI failed on the newest commit, bbbbbbb")
        assert "nothing to update" not in action["label"]
        assert "meanwhile ccccccc, which CI passed, can be installed" in action["label"]
        assert attention.update_words(v) == "Update available — aaaaaaa → ccccccc (1 new commit)"
        alone = _value(ci=failed)
        assert "nothing to update until CI passes" in attention.ci_refused_words(alone)[1]["label"]

    def test_the_page_draws_it_and_offers_none_of_them(self, repos, store):
        import app as A
        from modules import update_op

        c0, c1, c2 = repos["shas"]
        v, _asked = _read(repos, {c2: "pending", c1: "passed"})
        real = update_op.plan
        kw = dict(_plan_kw(value=dict(v, running=c0)), running=c0, holder="", waiting={})
        import unittest.mock as M
        with M.patch.object(update_op, "plan", lambda **k: real(**kw)):
            html = A.app.test_client().get("/v2/update/panel").get_data(as_text=True)
        assert "1 newer: 1 running CI" in html and f"Update to {c1[:10]}" in html
        assert f"Update to {c2[:10]}" not in html
