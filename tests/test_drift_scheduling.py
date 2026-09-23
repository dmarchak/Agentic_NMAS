"""Drift scheduling state: per list, merged, and legible.

The cause of "Disabled" on the deployed instance was a **setting**, not a
defect: it was switched off on 2026-08-30, three minutes after a run that
flagged all nine devices, during Lab 1 -- when goldens were saved ad hoc and
the comparison ran against stale files. Noise then, and switching it off was
right.

What the three defects here did was make that decision unrecoverable. The
state file was the only record the checker had ever been on; it recorded
nothing about who switched it off or when; it was installation-wide while
everything it governs is per list; and the scheduler's own save would have
dropped the flag had it ever run while disabled. Six months later the reason
had been fixed for weeks with nothing anywhere to prompt a re-evaluation.

**That is what a silenced check looks like.** The fix is not to refuse to
silence checks -- it is to make the silence say when it started, who started
it, and what the last thing it saw was.
"""

import json
import os

import pytest


@pytest.fixture
def lists(tmp_path, monkeypatch):
    """Two lists, so 'per list' is testable rather than assumed."""
    from modules import drift_check

    for name in ("alpha", "beta"):
        (tmp_path / name).mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(tmp_path / name))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "alpha")
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    return {"root": tmp_path, "module": drift_check}


class TestStateIsPerList:
    """One switch governing several networks tells you nothing about the one
    you are looking at."""

    def test_disabling_one_list_does_not_disable_the_other(self, lists):
        d = lists["module"]
        d.set_disabled(True)
        assert d._is_disabled() is True
        assert bool(d._load_state("beta").get("disabled")) is False

    def test_the_file_lands_in_the_list_directory(self, lists):
        d = lists["module"]
        d.set_disabled(True)
        assert os.path.exists(lists["root"] / "alpha" / "drift_state.json")
        assert not os.path.exists(lists["root"] / "beta" / "drift_state.json")

    def test_each_list_keeps_its_own_last_run(self, lists):
        d = lists["module"]
        d._save_state({"last_result": {"summary": "alpha ran"}}, "alpha")
        d._save_state({"last_result": {"summary": "beta ran"}}, "beta")
        assert d._load_state("alpha")["last_result"]["summary"] == "alpha ran"
        assert d._load_state("beta")["last_result"]["summary"] == "beta ran"


class TestTheOldFileIsAdoptedNotDiscarded:
    """It is the only record that drift was ever switched on."""

    def test_the_installation_wide_state_is_adopted(self, lists):
        d = lists["module"]
        (lists["root"] / "drift_state.json").write_text(json.dumps({
            "disabled": True,
            "last_result": {"summary": "drift on all nine"}}), encoding="utf-8")
        state = d._load_state("alpha")
        assert state["disabled"] is True
        assert state["last_result"]["summary"] == "drift on all nine"

    def test_the_old_file_is_left_in_place(self, lists):
        d = lists["module"]
        legacy = lists["root"] / "drift_state.json"
        legacy.write_text(json.dumps({"disabled": True}), encoding="utf-8")
        d._load_state("alpha")
        assert legacy.exists(), "copied, not moved"

    def test_adoption_records_where_it_came_from(self, lists):
        d = lists["module"]
        (lists["root"] / "drift_state.json").write_text(
            json.dumps({"disabled": True}), encoding="utf-8")
        assert "migrated_from" in d._load_state("alpha")

    def test_adopting_does_not_recurse(self, lists):
        """`_save_state` merges by loading, and loading is what adopts."""
        d = lists["module"]
        (lists["root"] / "drift_state.json").write_text(
            json.dumps({"disabled": True}), encoding="utf-8")
        assert d._load_state("alpha")["disabled"] is True   # no RecursionError


class TestSavingMergesRatherThanReplaces:

    def test_a_completed_run_does_not_drop_the_disabled_flag(self, lists):
        """The scheduler's `finally` handed `json.dump` a fresh three-key dict.

        Unreachable while disabled, so it never fired -- but a switch a
        completed run can silently flip is one bug away from switching itself
        back on, with no record either way.
        """
        d = lists["module"]
        d.set_disabled(True)
        d._save_state({"last_check_ts": 123.0, "last_result": {"summary": "x"}})
        assert d._is_disabled() is True

    def test_unrelated_keys_survive(self, lists):
        d = lists["module"]
        d._save_state({"something_a_later_version_added": 1})
        d._save_state({"last_check_ts": 5.0})
        assert d._load_state()["something_a_later_version_added"] == 1


class TestSilenceSaysWhenAndWhoAndWhat:

    def test_disabling_records_the_time(self, lists):
        d = lists["module"]
        d.set_disabled(True)
        assert d._load_state()["disabled_at"]

    def test_disabling_records_the_actor(self, lists):
        d = lists["module"]
        d.set_disabled(True, actor="dustin@example.com")
        assert d._load_state()["disabled_by"] == "dustin@example.com"

    def test_re_enabling_clears_the_note(self, lists):
        d = lists["module"]
        d.set_disabled(True, actor="someone")
        d.set_disabled(False)
        state = d._load_state()
        assert state["disabled"] is False
        assert state["disabled_at"] is None

    def test_the_last_run_survives_being_switched_off(self, lists):
        """What was silenced must stay visible, or nothing prompts a
        re-evaluation when the reason stops holding."""
        d = lists["module"]
        d._save_state({"last_result": {"summary": "drift on all nine"}})
        d.set_disabled(True)
        assert d._load_state()["last_result"]["summary"] == "drift on all nine"


class TestStatusDistinguishesOffFromIdle:
    """A scheduler that is alive and waiting looked exactly like one switched
    off: both showed a null `next_at` and nothing else."""

    def test_disabled_says_disabled(self, lists):
        d = lists["module"]
        d.set_disabled(True)
        assert d.DriftChecker().status()["state"] == "disabled"

    def test_enabled_and_waiting_says_idle(self, lists):
        d = lists["module"]
        d.set_disabled(False)
        assert d.DriftChecker().status()["state"] == "idle"

    def test_the_status_names_the_list_it_describes(self, lists):
        d = lists["module"]
        assert d.DriftChecker().status()["list"] == "alpha"

    def test_the_status_carries_the_disabling_note(self, lists):
        d = lists["module"]
        d.set_disabled(True, actor="dustin@example.com")
        s = d.DriftChecker().status()
        assert s["disabled_by"] == "dustin@example.com"
        assert s["disabled_at"]
