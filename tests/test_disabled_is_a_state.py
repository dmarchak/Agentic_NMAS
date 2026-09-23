""""Disabled" is a state to report, not a reason to withhold.

`GET /ai/agent_log?limit=2` returned `{"entries": [], "status": {}}` with a
503 the moment AI was switched off. So disabling the agent **suppressed the
26 recorded failures and the workspace-id error that were the reason for
disabling it.** The health surface built so a dead component could not look
quiet went silent exactly when its history mattered most, and an operator
finding it disabled next month would have learned nothing.

The mechanism is worth naming, because the route was not carelessly written:
**the guard was correct for an older payload.** When `/ai/agent_log` returned
only a log, "AI is disabled" plausibly meant "nothing to say". Adding
`health` to it changed what the route carries and nobody revisited the
guard. A guard ages against its own payload.

**A read reports; an action refuses.** `/ai/agent_run`, `/ai/agent_pause`,
`/ai/agent_resume` and the timer POST still return 503 — a disabled agent
must not be made to act. Fifteen of the eighteen short-circuiting routes are
actions and are right as they stand.
"""

import ast
import io
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: Every **GET** route whose body returns something mentioning a disabled or
#: unconfigured state, classified. The default is not "fine" — a route that
#: shows up in the AST scan and is missing here fails the test below.
#:
#: The scan is deliberately broader than "refuses": it finds every GET that
#: *says something* about a degraded state, because from the AST a healthy
#: report and a refusal look alike. Deciding which it is, is the point.
#:
#: `/ai/agent_log` and `/ai/agent_timers` are deliberately **absent**: they
#: no longer mention a degraded state in a return at all, having been
#: corrected to carry the status through. `TestTheAgentLogSurvivesBeingDisabled`
#: covers them behaviourally, which is stronger than a classification.
#:
#: ``reports``  — carries status or accumulated history. It must survive the
#:                degraded state, because the state is *what the operator
#:                needs to see*.
#: ``fetches``  — returns a resource that genuinely does not exist when the
#:                feature is off. Refusing is correct; the refusal must still
#:                say what to do about it.
CLASSIFIED = {
    "/drift/settings":     "reports",
    "/<name>":             "reports",   # monitoring_stack: one card per tool
    "/svg":                "fetches",   # topology_view: no SVG without a URL
}

_STATE = re.compile(r"disabled|not configured|not_configured|unconfigured|"
                    r"no api key|not enabled", re.I)


def _gets_mentioning_a_degraded_state():
    """GET routes that return something naming a disabled/unconfigured state."""
    found = []
    paths = [os.path.join(ROOT, "app.py")]
    routes_dir = os.path.join(ROOT, "routes")
    paths += [os.path.join(routes_dir, f) for f in sorted(os.listdir(routes_dir))
              if f.endswith(".py")]

    for path in paths:
        tree = ast.parse(io.open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            rule, methods = "", set()
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "route":
                    if dec.args and isinstance(dec.args[0], ast.Constant):
                        rule = dec.args[0].value
                    for kw in dec.keywords:
                        if kw.arg == "methods":
                            methods = {e.value for e in kw.value.elts}
            if not rule or (methods and methods != {"GET"}):
                continue
            for sub in ast.walk(node):
                if isinstance(sub, ast.Return) and sub.value is not None:
                    if _STATE.search(ast.unparse(sub.value)):
                        found.append(rule)
                        break
    return sorted(set(found))


class TestEveryDegradedReadIsClassified:
    """The list must not grow silently, which is the only way this stays a
    check rather than a snapshot of one afternoon."""

    def test_the_scan_finds_something(self):
        """A scan that returns nothing would make the test below vacuous —
        and this project has found five controls that could not fail."""
        assert len(_gets_mentioning_a_degraded_state()) >= 3

    def test_every_one_is_classified(self):
        unclassified = [r for r in _gets_mentioning_a_degraded_state() if r not in CLASSIFIED]
        assert not unclassified, (
            "a GET route names a disabled/unconfigured state in a return and "
            "is not classified in CLASSIFIED: " + str(unclassified) +
            " — decide whether it REPORTS the state or FETCHES a resource")

    def test_the_classification_names_no_ghosts(self):
        """An entry for a route that no longer short-circuits is a decision
        about nothing, and it hides the day the route changes back."""
        live = set(_gets_mentioning_a_degraded_state())
        ghosts = [r for r in CLASSIFIED if r not in live]
        assert not ghosts, (
            f"classified but no longer naming a degraded state: {ghosts} — "
            "either it was fixed (drop the entry; a behavioural test is "
            "stronger) or it was deleted")


class TestTheAgentLogSurvivesBeingDisabled:
    """The instance. Both switches off, and the history still arrives."""

    @pytest.fixture
    def disabled(self, monkeypatch):
        from modules import agent_runner

        entries = [{"id": "x", "started_at": "2026-08-28 23:26", "task": "t",
                    "trigger": "missing_golden_configs", "tools_used": [],
                    "tool_call_count": 0, "success": False,
                    "errors": ["anthropic-workspace-id is required when "
                               "authenticating with an identity-linked API key"],
                    "cost_usd": 0.0, "summary": ""} for _ in range(26)]
        monkeypatch.setattr(agent_runner, "_activity_log", entries)
        monkeypatch.setattr("modules.config.load_user_settings",
                            lambda: {"ai_enabled": False,
                                     "background_agent_enabled": False})

        import app as nmas

        return nmas.app.test_client()

    def test_it_answers_200_not_503(self, disabled):
        assert disabled.get("/ai/agent_log?limit=2").status_code == 200

    def test_the_entries_are_still_returned(self, disabled):
        assert len(disabled.get("/ai/agent_log?limit=2").get_json()["entries"]) == 2

    def test_the_streak_survives(self, disabled):
        h = disabled.get("/ai/agent_log").get_json()["status"]["health"]
        assert h["consecutive_failures"] == 26

    def test_the_error_that_explains_it_survives(self, disabled):
        h = disabled.get("/ai/agent_log").get_json()["status"]["health"]
        assert "anthropic-workspace-id" in h["last_error"]

    def test_same_error_survives(self, disabled):
        h = disabled.get("/ai/agent_log").get_json()["status"]["health"]
        assert h["same_error"] is True

    def test_both_switches_are_reported_separately(self, disabled):
        """"Not running" has a different fix for each, and an operator who
        turns the wrong one back on has learned nothing from the panel."""
        status = disabled.get("/ai/agent_log").get_json()["status"]
        assert status["ai_enabled"] is False
        assert status["enabled"] is False

    def test_the_status_is_produced_once(self):
        """`get_status()` reports both switches; the route must not compute a
        second copy that can disagree with it."""
        from tests.astcheck import code_of

        import app as nmas

        src = code_of(nmas.ai_agent_log)
        assert src.count("_ai_enabled()") == 0


class TestActionsStillRefuse:
    """A read reports. An action refuses — a disabled agent must not be made
    to act, and loosening that would be the opposite mistake."""

    @pytest.fixture
    def disabled(self, monkeypatch):
        monkeypatch.setattr("modules.config.load_user_settings",
                            lambda: {"ai_enabled": False})

        import app as nmas

        return nmas.app.test_client()

    @pytest.mark.parametrize("route", ["/ai/agent_run", "/ai/agent_pause",
                                       "/ai/agent_resume", "/ai/agent_timers"])
    def test_the_action_routes_still_return_503(self, disabled, route):
        assert disabled.post(route, json={}).status_code == 503
