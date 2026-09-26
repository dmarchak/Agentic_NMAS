"""The drift routes, EXERCISED — not inspected.

`DriftChecker.set_disabled()` is the method the panel's toggle reaches.
Stage 3.3c added `actor` to the module-level `set_disabled()` and left the
method alone, so every toggle raised

    TypeError: DriftChecker.set_disabled() got an unexpected keyword
    argument 'actor'

before touching the state file. Seventeen tests in
`test_drift_scheduling.py` passed throughout, because every one of them
called the module function directly. **The path the operator uses was the one
path nothing ran.** Same shape as the `write_committed()` crash in the 1.4
repair.

Worse than the crash was how it presented. `@app.errorhandler(Exception)`
redirected everything to the index, so the POST returned **302** -- a
success as far as `fetch` is concerned -- the panel refetched
`/drift/status`, read the unchanged `disabled: true`, and the toggle flicked
back with nothing on screen. The error existed only in the log.

These tests go through the HTTP client. A test that asserts the shape of a
call cannot see a signature that does not exist.
"""

import json
import os

import pytest


@pytest.fixture
def client(tmp_path, monkeypatch):
    (tmp_path / "lab").mkdir()
    monkeypatch.setattr("modules.config.get_list_data_dir",
                        lambda name: str(tmp_path / "lab"))
    monkeypatch.setattr("modules.config.get_current_list_name", lambda: "lab")
    monkeypatch.setattr("modules.config.DATA_DIR", str(tmp_path))
    monkeypatch.setattr("modules.agent_timers.save", lambda d: None)

    import app as nmas

    nmas.app.config["TESTING"] = False        # keep the error handlers live
    return nmas.app.test_client()


class TestTheToggleActuallyToggles:
    """Through the route, end to end, because that is where it broke."""

    def test_enabling_is_persisted(self, client):
        client.post("/drift/settings", json={"disabled": True})
        r = client.post("/drift/settings", json={"disabled": False})
        assert r.status_code == 200, r.get_data(as_text=True)
        assert client.get("/drift/status").get_json()["disabled"] is False

    def test_disabling_is_persisted(self, client):
        r = client.post("/drift/settings", json={"disabled": True})
        assert r.status_code == 200, r.get_data(as_text=True)
        assert client.get("/drift/status").get_json()["disabled"] is True

    def test_the_response_reports_what_was_stored(self, client):
        """Not what was asked for. Echoing the request is how a save that did
        nothing reports success and the control reverts on the next poll."""
        body = client.post("/drift/settings", json={"disabled": True}).get_json()
        assert body["ok"] is True
        assert body["disabled"] is client.get("/drift/status").get_json()["disabled"]

    def test_the_status_state_follows_the_toggle(self, client):
        client.post("/drift/settings", json={"disabled": True})
        assert client.get("/drift/status").get_json()["state"] == "disabled"
        client.post("/drift/settings", json={"disabled": False})
        assert client.get("/drift/status").get_json()["state"] == "idle"

    def test_the_interval_still_saves(self, client):
        body = client.post("/drift/settings", json={"interval_s": 7200}).get_json()
        assert body["ok"] is True and body["interval_s"] == 7200

    def test_disabling_records_who_and_when(self, client, tmp_path):
        client.post("/drift/settings", json={"disabled": True})
        state = json.loads((tmp_path / "lab" / "drift_state.json").read_text())
        assert state["disabled"] is True
        assert state["disabled_at"]


class TestACrashIsNotARedirect:
    """An unhandled exception presented as a successful redirect is the
    failure mode this project calls the dominant one, wired in at the
    framework level and applying to every JSON route at once."""

    def test_a_failing_save_returns_500_not_302(self, client, monkeypatch):
        monkeypatch.setattr("modules.drift_check.set_disabled",
                            lambda *a, **kw: (_ for _ in ()).throw(
                                TypeError("unexpected keyword argument")))
        r = client.post("/drift/settings", json={"disabled": True})
        assert r.status_code == 500
        assert r.get_json()["ok"] is False

    def test_the_reason_reaches_the_caller(self, client, monkeypatch):
        monkeypatch.setattr("modules.drift_check.set_disabled",
                            lambda *a, **kw: (_ for _ in ()).throw(
                                RuntimeError("disk on fire")))
        body = client.post("/drift/settings", json={"disabled": True}).get_json()
        assert "disk on fire" in body["error"]

    def test_an_unhandled_exception_anywhere_answers_json(self, client,
                                                          monkeypatch):
        """The global handler, not this route's own try/except."""
        monkeypatch.setattr("modules.drift_check.get_checker",
                            lambda: (_ for _ in ()).throw(
                                RuntimeError("no checker")))
        r = client.post("/drift/settings", json={"disabled": True})
        assert r.status_code == 500
        assert r.headers["Content-Type"].startswith("application/json")
        assert r.get_json()["ok"] is False

    def test_a_browser_navigation_still_redirects(self, client, monkeypatch):
        """The redirect is right for a page load and wrong for a fetch. Only
        the literal Accept header separates them: `*/*` from fetch cannot be
        told from `*/*` by any quality comparison."""
        r = client.get("/no-such-page",
                       headers={"Accept": "text/html,application/xhtml+xml"})
        assert r.status_code == 302

    def test_a_fetch_gets_json_for_a_404(self, client):
        r = client.get("/no-such-page", headers={"Accept": "*/*"})
        assert r.status_code == 404
        assert r.get_json()["ok"] is False


class TestTheRunReportsItsCoverageEveryTime:
    """"All 9 device(s) clean" reads identically for 9 of 9 and 9 of 10."""

    @pytest.fixture
    def nine_clean(self, monkeypatch):
        from modules import drift_check

        devices = [{"hostname": f"r{i}", "ip": f"203.0.113.{i}",
                    "username": "u", "password": "p",
                    "device_type": "cisco_ios"} for i in range(1, 10)]
        monkeypatch.setattr("modules.device.get_current_device_list",
                            lambda: ("lab", "lab.csv"))
        monkeypatch.setattr("modules.device.load_saved_devices",
                            lambda p: list(devices))
        monkeypatch.setattr("modules.ai_assistant._load_golden_config_file",
                            lambda ip: "hostname x\n!\nend\n")
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda d, p, l: d["ip"])
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda c, cmd: "hostname x\n!\nend\n")
        return drift_check

    def test_a_fully_clean_run_still_states_the_coverage(self, nine_clean):
        r = nine_clean.run_drift_check("test")
        assert r["clean"] == 9
        assert "checked 9 of 9" in r["summary"], r["summary"]

    def test_the_accounting_is_in_the_fields_not_only_the_sentence(self,
                                                                  nine_clean):
        """The panel renders from these; a sentence is not a place to keep
        numbers."""
        r = nine_clean.run_drift_check("test")
        assert r["inventory"] == 9 and r["checked"] == 9
        assert r["skipped"] == [] and r["errors"] == []


class TestTheWrapperCannotDriftFromWhatItWraps:
    """The general shape, not just this instance.

    `DriftChecker.set_disabled` shadows the module-level `set_disabled` by
    name and delegates to it. Adding a parameter to one and not the other
    produces a `TypeError` reachable only by calling the method -- and the
    shared name is what makes it easy to believe both were edited.

    Checked with `inspect.signature`, so a future parameter added to either
    side fails here rather than at the first click.
    """

    def _pair(self, name):
        import inspect

        from modules import drift_check

        method = getattr(drift_check.DriftChecker, name)
        function = getattr(drift_check, name)
        return inspect.signature(method), inspect.signature(function)

    def test_set_disabled_accepts_everything_the_function_does(self):
        msig, fsig = self._pair("set_disabled")
        method_params = set(msig.parameters) - {"self"}
        missing = set(fsig.parameters) - method_params
        assert not missing, (
            f"DriftChecker.set_disabled cannot pass {sorted(missing)} through; "
            "the route calls the METHOD")

    def test_the_method_actually_forwards_them(self):
        """Accepting a parameter and dropping it is the same defect wearing a
        signature that type-checks."""
        from modules import drift_check
        from tests.astcheck import code_of

        source = code_of(drift_check.DriftChecker.set_disabled)
        assert "actor=actor" in source, source
