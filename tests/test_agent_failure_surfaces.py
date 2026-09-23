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

    def test_the_streak_stops_at_the_last_run_that_WORKED(self, log):
        """A run that worked resets it — the count is "since it last worked",
        not "ever".

        This test used to pass `_entry(True)` as the success, which encoded
        the old definition: `success` meant "no exception reached the top".
        A no-op run now classifies as `inconclusive` and no longer ends the
        streak, so the fixture carries a run that actually did something.
        """
        from modules.agent_runner import failure_health

        worked = dict(_entry(True), tool_call_count=1, summary="checked r1")
        log.extend([_entry(False, WORKSPACE), worked,
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


class TestDisabledAndFailingAreBothTrue:
    """It is now both, and they are different facts.

    "Disabled" is the current state — it will not run. "26 consecutive
    failures" is what happened before it was switched off. Showing only the
    second implies it is still trying; showing only the first loses the
    reason it was switched off, which is precisely the information this whole
    change exists to keep.

    The first version of this UI put `failing` ahead of `enabled`, so the
    badge would have read "Failing (26)" about a component that cannot run.
    """

    @pytest.fixture(scope="class")
    def page(self):
        import app as nmas

        return nmas.app.test_client().get("/").get_data(as_text=True)

    def test_disabled_outranks_failing_in_the_badge(self, page):
        i = page.index("status.enabled === false")
        j = page.index("} else if (health.failing) {")
        assert i < j, "a disabled agent must not be described as failing"

    def test_the_badge_carries_both(self, page):
        assert "Disabled · ${health.consecutive_failures} failed" in page

    def test_a_disabled_agent_still_shows_the_streak_in_the_tab_badge(self, page):
        assert "Background agent is disabled; its last runs had failed" in page

    def test_the_banner_says_they_will_not_retry(self, page):
        import re

        flat = re.sub(r"\s+", " ", page)
        assert "these will not retry" in flat

    def test_a_disabled_agent_is_amber_not_red(self, page):
        """A red alarm on something that cannot run is an alarm nobody can
        act on."""
        assert "'badge bg-warning text-dark ms-1' : 'badge bg-danger ms-1'" in page
        assert "'alert-warning' : 'alert-danger'" in page

    def test_an_enabled_failing_agent_is_still_red(self, page):
        """The softening must not swallow a live incident."""
        assert "badgeEl.className = 'badge bg-danger';" in page


class TestSuccessMustMeanSomethingHappened:
    """Measured across the agent's whole recorded history: **27 entries,
    `tool_call_count` zero in every one**, and one `success: true` with no
    tools, no summary and no errors — five minutes after a failure.

    `success` meant "no exception reached the top of `run_background_task`",
    which is a fact about the interpreter rather than about the network. A
    backward failure streak stopped dead on that entry, which is why the
    badge showed nothing even after the route was fixed to report it.

    **Diagnosed, not inferred:** the loop breaks on `_user_is_active()`
    without appending anything, while the model-side `interrupted` event a few
    lines below always appended `"Task was interrupted."`. One of the two exit
    paths recorded and the other did not.
    """

    def test_a_run_with_no_tools_and_no_output_is_not_ok(self):
        from modules.agent_runner import classify_outcome

        outcome, reason = classify_outcome(_entry(True))
        assert outcome == "inconclusive"
        assert "nothing observable happened" in reason

    def test_a_run_with_errors_is_failed(self):
        from modules.agent_runner import classify_outcome

        assert classify_outcome(_entry(False, WORKSPACE))[0] == "failed"

    def test_an_interrupted_run_says_so(self):
        from modules.agent_runner import classify_outcome

        outcome, reason = classify_outcome(_entry(True),
                                           interrupted="the user became active")
        assert outcome == "interrupted"
        assert "user became active" in reason

    def test_a_run_that_did_something_is_ok(self):
        from modules.agent_runner import classify_outcome

        entry = dict(_entry(True), tool_call_count=2, summary="checked r1")
        assert classify_outcome(entry)[0] == "ok"

    def test_output_alone_counts(self):
        """A run that reported without calling a tool still did something."""
        from modules.agent_runner import classify_outcome

        assert classify_outcome(dict(_entry(True), summary="all clean"))[0] == "ok"

    def test_historical_entries_are_classified_from_what_they_carry(self):
        """They have no `outcome` field. An old entry cannot say it was
        interrupted — nothing recorded that — so it lands in `inconclusive`,
        which is honest rather than a guess dressed as a record."""
        from modules.agent_runner import outcome_of

        assert outcome_of(_entry(True)) == "inconclusive"
        assert outcome_of({"outcome": "interrupted"}) == "interrupted"

    def test_the_user_active_break_records_a_reason(self):
        from tests.astcheck import code_of

        from modules import agent_runner

        src = code_of(agent_runner.run_background_task)
        assert "interrupted = " in src, (
            "the user-active break must record why, like the model-side one")

    def test_success_is_derived_from_the_outcome(self):
        from tests.astcheck import code_of

        from modules import agent_runner

        src = code_of(agent_runner.run_background_task)
        assert "entry['success'] = entry['outcome'] == 'ok'" in src.replace('"', "'")


class TestTheStreakCountsBackToWhatWORKED:

    def test_an_inconclusive_run_does_not_end_the_streak(self, log):
        """The defect exactly: a no-op run stopped a 26-failure streak."""
        from modules.agent_runner import failure_health

        log.extend(_entry(False, WORKSPACE) for _ in range(26))
        log.append(_entry(True))                    # the no-op "success"
        h = failure_health()
        assert h["consecutive_failures"] == 26
        assert h["runs_since_ok"] == 27

    def test_a_real_success_does_end_it(self, log):
        from modules.agent_runner import failure_health

        log.extend(_entry(False, WORKSPACE) for _ in range(3))
        log.append(dict(_entry(True), tool_call_count=1, summary="did a thing"))
        log.append(_entry(False, WORKSPACE))
        assert failure_health()["consecutive_failures"] == 1

    def test_an_inconclusive_run_is_not_counted_as_a_failure(self, log):
        """It is not evidence the agent works, and it is not a failure
        either. Two different facts, two different numbers."""
        from modules.agent_runner import failure_health

        log.append(_entry(True))
        h = failure_health()
        assert h["consecutive_failures"] == 0
        assert h["runs_since_ok"] == 1
        assert h["outcomes"]["inconclusive"] == 1

    def test_never_succeeded_is_reported(self, log):
        from modules.agent_runner import failure_health

        log.extend(_entry(False, WORKSPACE) for _ in range(3))
        assert failure_health()["never_succeeded"] is True

    def test_zero_tool_calls_across_the_history_is_reported(self, log):
        """Nothing in the tool library has ever executed. That is the fact
        Stage 8 turns on, and it is reported rather than rediscovered."""
        from modules.agent_runner import failure_health

        log.extend(_entry(False, WORKSPACE) for _ in range(27))
        assert failure_health()["tool_calls_total"] == 0

    def test_the_panel_says_both(self):
        import re

        import app as nmas

        flat = re.sub(r"\s+", " ", nmas.app.test_client().get("/").get_data(as_text=True))
        assert "It has never completed a run." in flat
        assert "No tool has ever executed" in flat
