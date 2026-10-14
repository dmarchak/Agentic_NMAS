"""The drift checker's one schedule (modules/drift_interval.py), moved out of the AI agent's
timers with no behaviour change: the same file and key, default and bounds, so nothing stored on
the host moves. The agent's timers (modules/agent_timers.py) left with the AI family (D15,
2026-10-14); the file they wrote is read as it stands."""
import json
import os

import pytest

from modules import drift_interval


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    return os.path.join(str(tmp_path), "agent_timers.json")


class TestTheSchedule:
    def test_its_default_and_bounds_are_the_agents(self, store):
        """The agent's timers' default and bounds for this key (measured before they left)."""
        assert drift_interval.get() == drift_interval.DEFAULT == 14400
        assert drift_interval.BOUNDS == (300, 86400)
        assert drift_interval._path() == store

    @pytest.mark.parametrize("stored, read", [(60, 300), (3600, 3600), (999999, 86400),
                                              ("not a number", 14400), (None, 14400)])
    def test_a_stored_value_is_read_within_its_bounds(self, store, stored, read):
        with open(store, "w", encoding="utf-8") as fh:
            json.dump({"drift_check_interval": stored, "user_idle_seconds": 90}, fh)
        assert drift_interval.get() == read

    def test_an_unreadable_file_is_the_default(self, store):
        with open(store, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        assert drift_interval.get() == 14400

    def test_a_save_stores_its_key_within_bounds_and_leaves_the_rest(self, store):
        with open(store, "w", encoding="utf-8") as fh:
            json.dump({"user_idle_seconds": 120, "trap_flap_window": 30}, fh)
        assert drift_interval.save(10) == 300 and drift_interval.save(7200) == 7200
        with open(store, encoding="utf-8") as fh:
            assert json.load(fh) == {"user_idle_seconds": 120, "trap_flap_window": 30,
                                     "drift_check_interval": 7200}


class TestNothingMoved:
    """The host's stored value is read as before: the file the agent's timers wrote, with its
    other keys, is the schedule's."""

    def test_what_the_agents_timers_stored_is_the_schedule(self, store):
        with open(store, "w", encoding="utf-8") as fh:
            json.dump({"drift_check_interval": 28800, "user_idle_seconds": 90,
                       "event_check_interval": 600}, fh)
        assert drift_interval.get() == 28800

    def test_the_drift_checker_reads_its_schedule_here(self, store):
        from modules.drift_check import _get_interval
        drift_interval.save(43200)
        assert _get_interval() == 43200.0
