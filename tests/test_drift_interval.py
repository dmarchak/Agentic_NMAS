"""The drift checker's one schedule (modules/drift_interval.py), moved out of the AI agent's
timers with no behaviour change: the same file and key, default and bounds, so nothing stored on
the host moves, and the two read each other's writes until the agent's page goes."""
import json
import os

import pytest

from modules import agent_timers, drift_interval


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    path = os.path.join(str(tmp_path), "agent_timers.json")
    monkeypatch.setattr(agent_timers, "_TIMERS_FILE", path)
    return path


class TestTheSchedule:
    def test_its_default_and_bounds_are_the_agents(self, store):
        assert drift_interval.get() == agent_timers.DEFAULTS["drift_check_interval"] == 14400
        assert drift_interval.BOUNDS == agent_timers.BOUNDS["drift_check_interval"]

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
    """The host's stored value is read as before, and the agent's page (until the removal)
    still reads and writes the same value."""

    def test_what_the_agents_timers_stored_is_the_schedule(self, store):
        agent_timers.save({"drift_check_interval": 28800})
        assert drift_interval.get() == 28800

    def test_what_the_schedule_stores_the_agents_timers_read(self, store):
        drift_interval.save(1800)
        assert agent_timers.get("drift_check_interval") == 1800
        assert agent_timers.load()["user_idle_seconds"] == agent_timers.DEFAULTS["user_idle_seconds"]

    def test_the_drift_checker_reads_its_schedule_here(self, store):
        from modules.drift_check import _get_interval
        drift_interval.save(43200)
        assert _get_interval() == 43200.0
