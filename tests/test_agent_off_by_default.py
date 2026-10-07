"""C497: the background agent is OFF until Stage 8 (MERCURY_CHARTER: the agent proposes, never
confirms), as ARCHITECTURE.md and CLAUDE.md always said, where a fresh install once started it.

- An install with no stored value does not start the agent, and its status says enabled False.
- A switch that cannot be read does not start it, reports it off, and runs no task: it fails
  closed, where an exception once fell through to starting it.
- Every read takes its fallback from the one declared default (`settings_schema.DEFAULTS`).

The thread class is replaced by a recorder, so no test (and no failing control) ever starts a
real agent loop.
"""

import threading

import pytest

from modules import agent_runner as AR


@pytest.fixture
def no_real_thread(monkeypatch):
    started = []

    class Recorder:
        def __init__(self, *a, **k):
            self.name = k.get("name", "")

        def start(self):
            started.append(self.name or "agent")

        def is_alive(self):
            return bool(started)

    monkeypatch.setattr(AR.threading, "Thread", Recorder)
    monkeypatch.setattr(AR, "_processor_thread", None)
    monkeypatch.setattr(AR, "_load_persisted_log", lambda: None)
    return started


def _setting(monkeypatch, fn):
    monkeypatch.setattr("modules.config.get_user_setting", fn)


class TestOffUntilStage8:
    def test_the_declared_default_is_off(self):
        from modules.settings_schema import DEFAULTS
        assert DEFAULTS["background_agent_enabled"] is False
        assert AR._agent_default() is False

    def test_an_install_with_no_stored_value_does_not_start_it(self, monkeypatch, no_real_thread):
        _setting(monkeypatch, lambda key, default=None: default)
        AR.start_agent_loop(lambda: [], {}, {}, threading.Lock())
        assert no_real_thread == []
        assert AR.get_status()["enabled"] is False

    def test_the_control_switched_on_it_starts(self, monkeypatch, no_real_thread):
        _setting(monkeypatch, lambda key, default=None:
                 True if key == "background_agent_enabled" else default)
        AR.start_agent_loop(lambda: [], {}, {}, threading.Lock())
        assert no_real_thread, "switched on, the loop is started"


class TestFailsClosed:
    @staticmethod
    def _broken(key, default=None):
        raise OSError("settings unreadable")

    def test_an_unreadable_switch_does_not_start_it(self, monkeypatch, no_real_thread):
        _setting(monkeypatch, self._broken)
        AR.start_agent_loop(lambda: [], {}, {}, threading.Lock())
        assert no_real_thread == []
        assert AR.get_status()["enabled"] is False

    def test_an_unreadable_switch_runs_no_task(self, monkeypatch):
        _setting(monkeypatch, self._broken)
        out = AR.run_background_task("check r2")
        assert out["error"] == "the AI switches could not be read"
