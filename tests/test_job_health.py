"""A failing timer must be visible (modules/job_health.py). The shapes below
are what systemd and the journal return, measured on the NMAS host."""

import pytest

from modules import job_health as J

NOW = 1790370000.0
JOB = {"unit": "clab-sync", "max_age_minutes": 90, "what": "sync"}


def _runner(show: str, journal: str, show_rc=0, journal_rc=0):
    def run(cmd):
        if cmd[0] == "systemctl":
            return show_rc, show
        return journal_rc, journal
    return run


LOADED = "LoadState=loaded\nActiveState=failed\nResult=exit-code\nExecMainStatus=2\n"


def _line(ts, text):
    return f"{ts:.6f} nmas {text}"


def _fail(ts, why="REFUSED - the NMAS could not be asked where configs belong."):
    return "\n".join([
        _line(ts - 2, "systemd[1]: Starting clab-sync.service - Sync Oxidized configs..."),
        _line(ts - 1, "clab-sync[1]: ./oxidized-to-config.sh: line 137: nmas-clab-targets: command not found"),
        _line(ts - 0.5, f"clab-sync[1]: {why}"),
        _line(ts - 0.4, "clab-sync[1]: config boots from writes one device's credentials into another lab."),
        _line(ts, "systemd[1]: clab-sync.service: Main process exited, code=exited, status=2/INVALIDARGUMENT"),
        _line(ts, "systemd[1]: clab-sync.service: Failed with result 'exit-code'."),
    ])


def _ok(ts):
    return _line(ts, "systemd[1]: clab-sync.service: Deactivated successfully.")


def test_the_measured_shape_is_failing_with_its_own_reason():
    """The live state: one success, then 72 failures every 30 minutes."""
    journal = "\n".join([_ok(NOW - 73 * 1800)] +
                        [_fail(NOW - k * 1800) for k in range(72, 0, -1)])
    s = J.job_status(JOB, NOW, _runner(LOADED, journal))
    assert s["state"] == "failing"
    assert s["consecutive_failures"] == 72
    # The CAUSE, which comes first; not the refusal's continuation line.
    assert s["last_error"].endswith("nmas-clab-targets: command not found"), s["last_error"]


def test_a_unit_that_does_not_exist_is_never_ok():
    """Measured: systemd reports Result=success for a not-found unit."""
    show = "LoadState=not-found\nActiveState=inactive\nResult=success\nExecMainStatus=0\n"
    s = J.job_status(JOB, NOW, _runner(show, ""))
    assert s["state"] == "not_installed" and "Result=success" in s["detail"]


def test_quiet_and_old_is_stale_not_ok():
    s = J.job_status(JOB, NOW, _runner(LOADED, _ok(NOW - 5 * 3600)))
    assert s["state"] == "stale"


def test_recent_success_is_ok():
    s = J.job_status(JOB, NOW, _runner(LOADED, _ok(NOW - 600)))
    assert s["state"] == "ok" and s["consecutive_failures"] == 0


def test_failures_and_no_success_is_never_succeeded():
    s = J.job_status(JOB, NOW, _runner(LOADED, _fail(NOW - 60)))
    assert s["state"] == "never_succeeded"


@pytest.mark.parametrize("show_rc,journal_rc", [(1, 0), (0, 1)])
def test_could_not_ask_is_unknown_not_ok(show_rc, journal_rc):
    s = J.job_status(JOB, NOW, _runner(LOADED, _ok(NOW - 60), show_rc, journal_rc))
    assert s["state"] == "unknown"


def test_a_recovery_clears_the_streak():
    journal = "\n".join([_fail(NOW - 1200), _fail(NOW - 900), _ok(NOW - 300)])
    s = J.job_status(JOB, NOW, _runner(LOADED, journal))
    assert s["state"] == "ok" and s["last_error"] == ""


def test_the_headline_counts_and_names():
    journal = _ok(NOW - 60)
    h = J.health(NOW, _runner(LOADED, journal))
    assert h["headline"] == f"{len(J.JOBS)} of {len(J.JOBS)} job(s) ok"
    h = J.health(NOW, _runner(LOADED, _fail(NOW - 60)))
    assert h["headline"].startswith("0 of") and "clab-sync" in h["headline"]


def test_the_route_reports_rather_than_withholds(monkeypatch):
    import app as nmas
    monkeypatch.setattr(J, "_run", _runner(LOADED, _fail(NOW - 60)))
    body = nmas.app.test_client().get("/jobs/health").get_json()
    assert body["ok"] is True and "clab-sync" in body["not_ok"]
    # The STATE, not just "not ok": a route asking the real systemd of a
    # machine without the unit would say not_installed and also be "not ok".
    clab = next(j for j in body["jobs"] if j["unit"] == "clab-sync")
    assert clab["state"] == "never_succeeded", clab
