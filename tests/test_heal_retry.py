"""The retry pass (`modules/heal/retry.py`): an open incident whose fixes failed is tried again
ONCE per trigger (C3805, b001bb46; C3824, 9f62b2c7: the operator, 2026-11-16, "a failed fix is
retried once per trigger: switched on, a matching script saved, or every 24 h"). The debt pass
(2026-11-18, docs/FAST_LANE_DEBT.md's rows for b001bb46 and 9f62b2c7).

On tests/test_heal_decide.py's lab (the real incidents, decisions and policy stores under a
temporary data folder). The incident is stood on a can't-fix by the stores' own writers; the
retry is run with ``decide_now=False``, so what is held is the pass itself (who is sent back,
the key recorded on the incident's own record, what is refused), never the decision after it.
Stand-ins: the saved scripts' store (`saved_plans.scripts`, one Automatic script) and the
problem's classification (`problem.classify`, by device), each a read the pass makes.

- **Switched on:** turning self-healing to Auto starts one switched-on retry keyed by the
  confirmation's instant; confirming Auto again while in Auto starts none.
- **Who is sent back:** in Auto, a standing can't-fix is sent back for a fresh decision, its
  retry recorded on its record with its key and words; not in Auto, nothing is.
- **Never twice:** the same trigger's instance never retries it again, a new instance does; a
  key another process recorded between this pass's read and its write is honoured under the
  store's lock.
- **A script saved:** only the incidents that script matches, and only an Automatic script.
- **Daily:** only once its last try is a day old.
"""
import pytest

from modules import problem as P
from modules.heal import decisions as DS
from modules.heal import incidents as I
from modules.heal import retry
from tests.test_heal_decide import GOLDEN, lab, settle  # noqa: F401
from tests.test_heal_policy import T0, confirm
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

NET = "Default"
SCRIPT = "sp-bpdu"


def standing(device="edge-b", at=T0 - 5) -> str:
    """An open incident on *device* standing on a can't-fix, by the stores' own writers."""
    inc = settle(GOLDEN, device=device)
    d = DS.record(NET, {"incident": inc["id"], "device": device, "outcome": "cant_fix",
                        "mode": "auto", "kind": "", "tier": 3,
                        "words": f"{device}: no fix in Mercury's code"}, at)
    got = I.stand(NET, inc["id"], d, now=at)
    assert got["state"] == "standing", got
    return inc["id"]


def stand_again(iid: str, at: float) -> None:
    """The retried incident decided a can't-fix again and standing on it (as `decide.run`
    would leave it), so the next trigger finds it in the population again."""
    I.claim(NET, iid, by="the decision", now=at)
    d = DS.record(NET, {"incident": iid, "device": "edge-b", "outcome": "cant_fix",
                        "mode": "auto", "kind": "", "tier": 3, "words": "still no fix"}, at)
    I.stand(NET, iid, d, now=at)


def record_of(iid: str) -> dict:
    return next(i for i in I.read(NET)["incidents"] if i["id"] == iid)


@pytest.fixture
def world(lab, monkeypatch):  # noqa: F811
    """The lab in Auto, the retry's own thread never started (each start recorded)."""
    started = []
    monkeypatch.setattr(retry, "run_soon",
                        lambda network, trigger, **kw: started.append(dict(kw, trigger=trigger)))
    confirm(NET, now=T0 - 60, heal_mode="auto")
    return started


class TestSwitchedOn:
    def test_turning_auto_on_starts_one_retry_keyed_by_its_confirmation(
            self, lab, monkeypatch):  # noqa: F811
        started = []
        monkeypatch.setattr(retry, "run_soon",
                            lambda network, trigger, **kw: started.append(
                                dict(kw, trigger=trigger, network=network)))
        got = confirm(NET, now=T0 - 60, heal_mode="auto")
        assert [(s["network"], s["trigger"], s["instance"]) for s in started] == [
            (NET, "switched_on", got["at"])], started
        confirm(NET, now=T0 - 30, heal_mode="auto", heal_kinds_auto=["added_line"],
                reason="another change while in Auto")
        assert len(started) == 1, "a change confirmed while in Auto is no switch-on"


class TestWhoIsSentBack:
    def test_a_standing_cant_fix_is_sent_back_and_its_retry_recorded(self, world):
        iid = standing()
        got = retry.run(NET, "switched_on", instance="on-1", now=T0, decide_now=False)
        assert got["retried"] == [iid] and got["skipped"] == [], got
        inc = record_of(iid)
        assert inc["state"] in ("ready", "watching") and inc["standing"] is None, inc["state"]
        (r,) = inc["retries"]
        assert (r["key"], r["trigger"], r["state"]) == ("switched_on:on-1", "switched_on",
                                                       "deciding"), r
        assert r["from"]["outcome"] == "cant_fix"
        assert r["words"].startswith("Retried at ") and "self-healing switched on" in r["words"]
        assert inc["retry_pending"] == r["id"]

    def test_held_by_a_guard_still_holding_is_recorded_not_tried_and_once_cleared_sent_back(
            self, world, monkeypatch):
        """A standing incident held by guard 4 (`WERE_HELD`): while `decide.guard_holds` still
        finds it holding, the retry is recorded as not tried, naming the guard; held no longer,
        it is sent back."""
        from modules.heal import decide

        inc = settle(GOLDEN, device="edge-b")
        d = DS.record(NET, {"incident": inc["id"], "device": "edge-b", "outcome": "held",
                            "mode": "auto", "kind": "added_line", "tier": 1,
                            "guard": {"guard": 4, "name": "the golden", "words": "held"},
                            "words": "edge-b: held by guard 4"}, T0 - 5)
        I.stand(NET, inc["id"], d, now=T0 - 5)
        holds = {"now": {"guard": 4, "name": "the golden", "words": "its golden is not read"}}
        monkeypatch.setattr(decide, "guard_holds",
                            lambda network, incident, guard, now=None: holds["now"])
        held = retry.run(NET, "switched_on", instance="on-1", now=T0, decide_now=False)
        assert held["skipped"] == [inc["id"]] and held["retried"] == [], held
        (r,) = record_of(inc["id"])["retries"]
        assert r["state"] == "skipped" and "guard 4 still holds" in r["words"], r
        assert record_of(inc["id"])["state"] == "standing"
        holds["now"] = None
        cleared = retry.run(NET, "switched_on", instance="on-2", now=T0 + 10, decide_now=False)
        assert cleared["retried"] == [inc["id"]], cleared

    def test_not_in_auto_nothing_is_sent_back(self, world):
        iid = standing()
        confirm(NET, now=T0 - 30, heal_mode="dry_run", reason="back to watching")
        got = retry.run(NET, "switched_on", instance="on-1", now=T0, decide_now=False)
        assert got["retried"] == [] and not got["ran"], got
        assert got["words"].startswith("nothing retried: self-healing is not in Auto")
        assert record_of(iid)["state"] == "standing" and not record_of(iid).get("retries")


class TestNeverTwice:
    def test_the_same_instance_never_again_and_a_new_one_once(self, world):
        iid = standing()
        assert retry.run(NET, "switched_on", instance="on-1", now=T0,
                         decide_now=False)["retried"] == [iid]
        stand_again(iid, T0 + 10)
        again = retry.run(NET, "switched_on", instance="on-1", now=T0 + 20, decide_now=False)
        assert again["retried"] == [] and again["words"] == "nothing to retry", again
        assert record_of(iid)["state"] == "standing"
        new = retry.run(NET, "switched_on", instance="on-2", now=T0 + 30, decide_now=False)
        assert new["retried"] == [iid], new
        assert [r["key"] for r in record_of(iid)["retries"]] == ["switched_on:on-1",
                                                                "switched_on:on-2"]

    def test_a_key_another_process_wrote_after_the_read_is_honoured(self, world, monkeypatch):
        """The pass reads the store, then writes under its lock: a retry of the same key that
        another worker recorded in between is found there, and this pass sends nothing back."""
        iid = standing()
        real = I._mutate

        def other_process_first(network, fn):
            # Only before the pass's own write (`run`'s ``change``), after its read: the
            # switch-on's wake of watching incidents comes before the read and is left alone.
            def theirs(doc):
                inc = next(i for i in doc["incidents"] if i["id"] == iid)
                inc["retries"] = [{"id": "rt-other", "key": "switched_on:on-1",
                                   "trigger": "switched_on", "epoch": T0}]
            if fn.__name__ == "change":
                real(network, theirs)
            return real(network, fn)
        monkeypatch.setattr(I, "_mutate", other_process_first)
        got = retry.run(NET, "switched_on", instance="on-1", now=T0, decide_now=False)
        assert got["retried"] == [], got
        inc = record_of(iid)
        assert inc["state"] == "standing" and [r["id"] for r in inc["retries"]] == ["rt-other"]


class TestAScriptSaved:
    @pytest.fixture
    def scripts(self, world, monkeypatch):
        """One Automatic script matching an err-disabled port, and the problem each device's
        incident classifies as: edge-b's matches it, edge-c's is another condition."""
        from modules.nsot import saved_plans

        held = {SCRIPT: {"key": SCRIPT, "name": "BPDU recovery", "mode": "auto",
                         "network": NET, "match": {"condition": "err_disabled"},
                         "track": []}}
        monkeypatch.setattr(saved_plans, "scripts", lambda network: held)
        conditions = {"edge-b": "err_disabled", "edge-c": "down"}
        monkeypatch.setattr(P, "classify", lambda page: P.Problem(
            device=page["device"], object="Gi1/0", condition=conditions[page["device"]]))
        monkeypatch.setattr("modules.incident_page.resolve",
                            lambda network, iid: {"device": record_of(iid)["device"]})
        return held

    def test_only_the_incidents_it_matches(self, scripts):
        mine, other = standing("edge-b"), standing("edge-c")
        got = retry.run(NET, "script_saved", script=SCRIPT, instance=f"{SCRIPT}:t1",
                        now=T0, decide_now=False)
        assert got["retried"] == [mine], got
        assert record_of(other)["state"] == "standing" and not record_of(other).get("retries")
        (r,) = record_of(mine)["retries"]
        assert r["script"] == SCRIPT and "BPDU recovery" in r["trigger_words"]

    def test_a_script_not_automatic_retries_nothing(self, scripts):
        iid = standing("edge-b")
        scripts[SCRIPT]["mode"] = "dry_run"
        got = retry.run(NET, "script_saved", script=SCRIPT, instance=f"{SCRIPT}:t1",
                        now=T0, decide_now=False)
        assert got["retried"] == [] and "is no Automatic script" in got["words"], got
        assert record_of(iid)["state"] == "standing"


class TestDaily:
    def test_only_once_its_last_try_is_a_day_old(self, world):
        iid = standing(at=T0 - 5)
        soon = retry.run(NET, "daily", instance="d1", now=T0 + retry.DAY_S - 60,
                         decide_now=False)
        assert soon["retried"] == [], soon
        due = retry.run(NET, "daily", instance="d1", now=T0 + retry.DAY_S, decide_now=False)
        assert due["retried"] == [iid], due
