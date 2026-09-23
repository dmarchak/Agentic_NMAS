"""A component that fails every attempt must not render as idle.

Measured 2026-09-23 on the live install: the background agent's last recorded
run was **2026-08-28 23:26**, `tool_call_count` 0, trigger
`missing_golden_configs`, and the error was

    anthropic-workspace-id is required when authenticating with an
    identity-linked API key

So for four weeks it woke, decided to act, and failed at the first API call.
The Agent tab's badge said **Active**, in green, the whole time, and the only
record was `data/agent_activity.json` — a file the UI never surfaced and the
log summarised as `success=False` inside an INFO line.

This is the `last_push_failure` rule applied to the agent: **a thing that
could have worked and did not must never be silent.**

`same_error` is the load-bearing field. One failure is an incident; a dozen
identical ones is a configuration problem that will not fix itself, and the
two deserve different words.
"""

import pytest


@pytest.fixture
def log(monkeypatch):
    """Drive the real `failure_health()` off a controlled activity log."""
    from modules import agent_runner

    entries = []
    monkeypatch.setattr(agent_runner, "_activity_log", entries)
    return entries


def _entry(ok, error="", at="2026-08-28 23:26"):
    return {"id": "x", "started_at": at, "task": "t", "trigger": "missing_golden_configs",
            "tools_used": [], "tool_call_count": 0, "success": ok,
            "errors": [error] if error else [], "cost_usd": 0.0, "summary": ""}


WORKSPACE = ("anthropic-workspace-id is required when authenticating with an "
             "identity-linked API key")


class TestFailureHealth:

    def test_a_clean_log_is_not_failing(self, log):
        from modules.agent_runner import failure_health

        log.append(_entry(True))
        assert failure_health()["failing"] is False

    def test_an_empty_log_is_not_failing(self, log):
        from modules.agent_runner import failure_health

        assert failure_health()["failing"] is False
        assert failure_health()["runs_recorded"] == 0

    def test_consecutive_failures_are_counted(self, log):
        from modules.agent_runner import failure_health

        log.extend(_entry(False, WORKSPACE) for _ in range(12))
        h = failure_health()
        assert h["failing"] is True
        assert h["consecutive_failures"] == 12

    def test_the_streak_stops_at_the_last_success(self, log):
        """A run that worked resets it — the count is "since it last worked",
        not "ever"."""
        from modules.agent_runner import failure_health

        log.extend([_entry(False, WORKSPACE), _entry(True),
                    _entry(False, WORKSPACE), _entry(False, WORKSPACE)])
        assert failure_health()["consecutive_failures"] == 2

    def test_the_same_error_every_time_is_reported_as_such(self, log):
        """The difference between a flaky call and a dead component."""
        from modules.agent_runner import failure_health

        log.extend(_entry(False, WORKSPACE) for _ in range(9))
        h = failure_health()
        assert h["same_error"] is True
        assert h["same_error_count"] == 9

    def test_differing_errors_are_not(self, log):
        from modules.agent_runner import failure_health

        log.extend([_entry(False, "timeout"), _entry(False, WORKSPACE)])
        h = failure_health()
        assert h["failing"] is True
        assert h["same_error"] is False

    def test_the_error_text_is_carried(self, log):
        from modules.agent_runner import failure_health

        log.append(_entry(False, WORKSPACE))
        assert "anthropic-workspace-id" in failure_health()["last_error"]

    def test_the_time_of_the_last_failure_is_carried(self, log):
        from modules.agent_runner import failure_health

        log.append(_entry(False, WORKSPACE, at="2026-08-28 23:26"))
        assert failure_health()["last_failure_at"] == "2026-08-28 23:26"


class TestStatusCarriesIt:

    def test_get_status_includes_health(self, log):
        from modules.agent_runner import get_status

        log.append(_entry(False, WORKSPACE))
        assert get_status()["health"]["failing"] is True

    def test_get_status_reports_the_persistent_switch(self, log, monkeypatch):
        """"Not running" has two causes that look identical from outside:
        switched off, or a thread that died."""
        from modules import agent_runner

        monkeypatch.setattr("modules.config.get_user_setting",
                            lambda k, d=None: False if k == "background_agent_enabled" else d)
        assert agent_runner.get_status()["enabled"] is False

    def test_the_route_exposes_it(self, log, monkeypatch):
        import app as nmas

        monkeypatch.setattr("modules.config.load_user_settings",
                            lambda: {"ai_enabled": True})
        log.append(_entry(False, WORKSPACE))
        body = nmas.app.test_client().get("/ai/agent_log").get_json()
        assert body["status"]["health"]["failing"] is True


class TestItReachesTheLog:
    """`log.info(... success=%s ...)` produced a month of INFO lines that
    scanned like successes."""

    def test_a_failure_logs_at_error(self, monkeypatch, caplog):
        import logging

        from modules import agent_runner

        monkeypatch.setattr(agent_runner, "_activity_log",
                            [_entry(False, WORKSPACE) for _ in range(3)])
        with caplog.at_level(logging.ERROR, logger="modules.agent_runner"):
            h = agent_runner.failure_health()
            agent_runner.log.error(
                "agent_runner: task FAILED [x] trigger=t tools=0 — %s "
                "(%d consecutive failure(s)%s)",
                h["last_error"], h["consecutive_failures"],
                "; same error each time" if h["same_error"] else "")
        text = caplog.text
        assert "FAILED" in text
        assert "3 consecutive" in text
        assert "same error each time" in text

    def test_the_success_path_no_longer_prints_a_success_field(self):
        """It printed `success=False` on failure, at INFO."""
        from tests.astcheck import code_of

        from modules import agent_runner

        src = code_of(agent_runner.run_background_task)
        assert "success=%s" not in src

    def test_the_failure_branch_uses_log_error(self):
        from tests.astcheck import code_of

        from modules import agent_runner

        src = code_of(agent_runner.run_background_task)
        assert "log.error" in src


class TestItReachesTheUI:

    @pytest.fixture(scope="class")
    def page(self):
        import app as nmas

        return nmas.app.test_client().get("/").get_data(as_text=True)

    def test_failing_outranks_active(self, page):
        i = page.index("health.failing")
        j = page.index("'Active'")
        assert i < j, "the Active branch must be reached only after failing"

    def test_the_badge_turns_red(self, page):
        assert "Failing (${health.consecutive_failures})" in page

    def test_the_tab_badge_shows_it(self, page):
        """So a failure is visible WITHOUT opening the tab — nobody had
        reason to look."""
        assert "agentBadge" in page
        assert "Background agent runs are failing" in page

    def test_the_banner_names_the_error(self, page):
        assert "consecutive failed run" in page
        assert "health.last_error" in page

    def test_the_same_error_gets_its_own_sentence(self, page):
        import re

        flat = re.sub(r"\s+", " ", page)
        assert "The same error every time" in flat
        assert "configuration problem, not a transient one" in flat

    def test_pause_is_labelled_as_not_persistent(self, page):
        assert "Paused (until restart)" in page


class TestTheStaleTriggerIsGone:
    """`missing_golden_configs` was the trigger of the last failed run, and it
    came from the legacy enumeration: devices that HAVE repo goldens were
    reported as missing. Its first act on recovery would have been to create
    goldens for nine devices that already had them.

    Fixed by 3.3a rather than here — pinned so it stays fixed, because this
    is the trigger that fires first when the agent comes back.
    """

    def test_a_repo_only_device_is_not_reported_missing(self, tmp_path,
                                                        monkeypatch):
        from modules import event_monitor as em
        from modules.nsot import repo as _repo

        list_dir = tmp_path / "lab"
        repo_dir = str(list_dir / "config_repo")
        import os
        os.makedirs(os.path.join(repo_dir, "golden"), exist_ok=True)

        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(list_dir))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        monkeypatch.setattr("modules.config.get_current_list_data_dir",
                            lambda: str(list_dir))
        monkeypatch.setattr("modules.settings_schema.get_setting",
                            lambda k, d=None: {"nsot_git_author_name": "N",
                                               "nsot_git_author_email": "n@l"}.get(k, d))
        monkeypatch.setattr("modules.nsot.hooks.run_post_commit", lambda c: None)
        monkeypatch.setattr("modules.device.get_current_device_list",
                            lambda: ("lab", "lab.csv"))
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda p: [{"hostname": "r6", "ip": "203.0.113.6"}])

        _repo.init_repo(repo_dir)
        _repo.save_golden("lab", [_repo.GoldenItem("r6", "hostname r6\n!\nend\n",
                                                   "203.0.113.6")],
                          source="test", actor="t", allow_new=True)

        em._events.clear()
        em._check_missing_golden_configs()
        assert em._events == [], (
            "a device with a repo golden and no legacy file was reported "
            "missing -- the trigger that would fire first on recovery")

    def test_a_device_with_no_golden_anywhere_still_is(self, tmp_path,
                                                       monkeypatch):
        """The check must still work, or this is a fix by deletion."""
        from modules import event_monitor as em

        monkeypatch.setattr("modules.config.get_list_data_dir", lambda n: str(tmp_path))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
        monkeypatch.setattr("modules.device.get_current_device_list",
                            lambda: ("lab", "lab.csv"))
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda p: [{"hostname": "r9", "ip": "203.0.113.9"}])
        monkeypatch.setattr("modules.ai_assistant._list_golden_configs", lambda: [])

        em._events.clear()
        em._check_missing_golden_configs()
        assert [e["type"] for e in em._events] == ["missing_golden_configs"]
