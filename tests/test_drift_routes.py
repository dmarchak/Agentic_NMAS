"""The drift switch, EXERCISED — not inspected.

`DriftChecker.set_disabled()` is the method a network's switch reaches.
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
success as far as `fetch` is concerned -- the panel refetched its status,
read the unchanged `disabled: true`, and the toggle flicked back with nothing
on screen. The error existed only in the log.

These tests go through the HTTP client. A test that asserts the shape of a
call cannot see a signature that does not exist. Today's drift routes
(`/drift/settings`, `/drift/status`) left with today's Drift tab at 7.8
(2026-10-15); the path the operator uses now is Settings › Installation ›
Diagnostics, the Drift checks card's Turn off and Turn on
(`routes/settings_v2.diag_drift_switch`), so that is the path exercised.
"""

import re

import pytest

from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)

SWITCH = "/v2/settings/installation/diagnostics/drift/Branch/{to}"


def _post(n, path, accept="*/*"):
    """As htmx sends it: a fetch, whose Accept is `*/*` unless it names one."""
    r = n["client"].post(path, headers={"HX-Request": "true", "Accept": accept})
    return r, r.get_data(as_text=True)


def _branch_row(html):
    """The Drift checks card's Branch row, its text without tags."""
    card = re.search(r'id="diag-drift".*?</section>', html, re.S).group(0)
    row = re.search(r"<tr>\s*<td>Branch</td>.*?</tr>", card, re.S)
    assert row, card[:400]
    return " ".join(re.sub(r"<[^>]+>", " ", row.group(0)).split())


@pytest.fixture
def live(networks, monkeypatch):  # noqa: F811
    """The temporary store, with the app's error handlers live (TESTING off)."""
    import app as nmas
    monkeypatch.setitem(nmas.app.config, "TESTING", False)
    return networks


class TestTheToggleActuallyToggles:
    """Through the route, end to end, because that is where it broke."""

    def test_enabling_is_persisted(self, live):
        from modules.drift_check import _is_disabled
        _post(live, SWITCH.format(to="off"))
        assert _is_disabled("Branch") is True, "the precondition: it was off"
        r, _html = _post(live, SWITCH.format(to="on"))
        assert r.status_code == 200, _html[:300]
        assert _is_disabled("Branch") is False

    def test_disabling_is_persisted(self, live):
        from modules.drift_check import _is_disabled
        r, html = _post(live, SWITCH.format(to="off"))
        assert r.status_code == 200, html[:300]
        assert _is_disabled("Branch") is True

    def test_the_response_draws_what_was_stored(self, live):
        """Not what was asked for: the card is drawn from the state file after the write, so a
        save that did nothing could not draw the row as off."""
        _r, html = _post(live, SWITCH.format(to="off"))
        assert "off" in _branch_row(html).split() and "Turn on" in _branch_row(html)
        _r, html = _post(live, SWITCH.format(to="on"))
        assert "Turn off" in _branch_row(html) and "Turn on" not in _branch_row(html)

    def test_the_status_state_follows_the_toggle(self, live):
        from modules.drift_check import get_checker
        _post(live, SWITCH.format(to="off"))
        assert get_checker().status("Branch")["state"] == "disabled"
        _post(live, SWITCH.format(to="on"))
        assert get_checker().status("Branch")["state"] == "idle"

    def test_disabling_records_when(self, live):
        from modules.drift_check import _load_state
        _post(live, SWITCH.format(to="off"))
        state = _load_state("Branch")
        assert state["disabled"] is True
        assert state["disabled_at"]


class TestACrashIsNotARedirect:
    """An unhandled exception presented as a successful redirect is the
    failure mode this project calls the dominant one, wired in at the
    framework level and applying to every route at once. The v2 switch has no
    try/except of its own beyond a refusal, so a crash in its core reaches the
    global handler, which is what these hold."""

    def test_a_failing_save_returns_500_not_302(self, live, monkeypatch):
        monkeypatch.setattr("modules.drift_check.set_disabled",
                            lambda *a, **kw: (_ for _ in ()).throw(
                                TypeError("unexpected keyword argument")))
        r, _html = _post(live, SWITCH.format(to="off"))
        assert r.status_code == 500
        assert r.get_json()["ok"] is False

    def test_the_reason_reaches_the_caller(self, live, monkeypatch):
        monkeypatch.setattr("modules.drift_check.set_disabled",
                            lambda *a, **kw: (_ for _ in ()).throw(
                                RuntimeError("disk on fire")))
        r, _html = _post(live, SWITCH.format(to="off"))
        assert "disk on fire" in r.get_json()["error"]

    def test_an_unhandled_exception_anywhere_answers_json(self, live, monkeypatch):
        """The global handler, not this route's own try/except."""
        monkeypatch.setattr("modules.drift_check.get_checker",
                            lambda: (_ for _ in ()).throw(
                                RuntimeError("no checker")))
        r, _html = _post(live, SWITCH.format(to="off"))
        assert r.status_code == 500
        assert r.headers["Content-Type"].startswith("application/json")
        assert r.get_json()["ok"] is False

    def test_a_v2_navigation_says_couldn_t_load_in_place(self, live, monkeypatch):
        """A request that wants HTML on a v2 path is answered on v2 with the failure and its
        status, never redirected to today's index (C569)."""
        monkeypatch.setattr("modules.drift_check.set_disabled",
                            lambda *a, **kw: (_ for _ in ()).throw(
                                RuntimeError("disk on fire")))
        r, html = _post(live, SWITCH.format(to="off"), accept="text/html")
        assert r.status_code == 500 and "Couldn't load" in html and "disk on fire" in html

    def test_a_browser_navigation_still_redirects(self, live):
        """The redirect is right for a page load and wrong for a fetch. Only
        the literal Accept header separates them: `*/*` from fetch cannot be
        told from `*/*` by any quality comparison."""
        r = live["client"].get("/no-such-page",
                               headers={"Accept": "text/html,application/xhtml+xml"})
        assert r.status_code == 302

    def test_a_fetch_gets_json_for_a_404(self, live):
        r = live["client"].get("/no-such-page", headers={"Accept": "*/*"})
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
        # Drift reads the golden through _golden_record (C104: as committed,
        # with a refusal distinct from "no golden").
        monkeypatch.setattr("modules.goldens._golden_record",
                            lambda ip, list_name="": {"text": f"hostname r{ip.split(chr(46))[-1]}\n!\nend\n",
                                        "path": "", "commit": "",
                                        "source": "", "refused": ""})
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda d, p, l: d["ip"])
        monkeypatch.setattr("modules.commands.run_device_command",
                            # Each answers with its own hostname, as a real
                            # device does (modules/config_read.py).
                            lambda c, cmd: f"hostname r{c.split(chr(46))[-1]}\n!\nend\n")
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
            "the switch (installation_diagnostics.set_drift_off) calls the METHOD")

    def test_the_method_actually_forwards_them(self):
        """Accepting a parameter and dropping it is the same defect wearing a
        signature that type-checks."""
        from modules import drift_check
        from tests.astcheck import code_of

        source = code_of(drift_check.DriftChecker.set_disabled)
        assert "actor=actor" in source, source
