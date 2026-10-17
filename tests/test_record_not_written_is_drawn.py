"""C1221, C1222: a result whose own record was not written says so where it is drawn, and is
never drawn as done.

Onboarding's Verify and Abandon (`routes.onboard._recorded_run`) and NetBox's Remove and Stop
tracking (`netbox_jobs.remove`, `netbox_jobs.forget`) each record their run, then draw the result
from the recorded row; when the record cannot be written, the result's record statement says
"THE RUN RECORD WAS NOT WRITTEN" or "THE REMOVAL RECORD WAS NOT WRITTEN". The v2 cards draw those
results through the shared `result_parts` macro (templates/v2/_preview_parts.html), which drew the
level, the summary and what did not happen, and never the record: the statement was drawn
nowhere, the card stayed a success, and the pending card's own line read `record_error`, which
nothing sets.

Each test makes the REAL recorder fail: a directory where its file goes (open_secure creates
missing parents, so a missing directory would be written and nothing would fail), through the
real route; the device and NetBox are the fakes the per-card tests use
(tests/test_onboard_run_results.py's phase-two stand-in, tests/test_netbox_v2.py's `tracked`
FakeNetBox). The controls: the same run with the record written draws no such sentence and stays
a success.
"""

import re

import pytest

from tests.test_netbox_v2 import _post, nb, tracked  # noqa: F401 (fixtures)
from tests.test_settings_v2 import networks  # noqa: F401 (the fixture: a temporary store)


def _flat(html):
    return re.sub(r"\s+", " ", html).replace("&#39;", "'")


def _result_notice(html):
    """The result component's notice: its colour class and its text."""
    m = re.search(r'<div class="notice notice-(\w+) set-result" role="status">(.*?)</div></div>',
                  html)
    assert m, "floor: the result component is drawn, so this proves something"
    return m.group(1), m.group(2)


# ── onboarding's Verify and Abandon (C1221) ─────────────────────────────────

@pytest.fixture
def lab(monkeypatch, tmp_path):
    """tests/test_onboard_run_results.py's list: its data directory a temporary one, so the
    run record lands where the route derives it."""
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / name))
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    (tmp_path / "probe" / "config_repo").mkdir(parents=True)
    return tmp_path


def _client():
    import app as A

    return A.app.test_client()


def _all_steps_ok():
    from modules.nsot.onboard import PHASE_TWO_STEPS

    return [{"step": st, "ok": True, "detail": ""} for st in PHASE_TWO_STEPS]


def _unwritable_runs(monkeypatch, lab):
    monkeypatch.setattr("modules.nsot.onboard.runs_path", lambda repo: str(lab / "probe"))


def _verify(monkeypatch):
    monkeypatch.setattr("modules.nsot.onboard.run_phase_two",
                        lambda repo, host, lst, **k: {
                            "ok": True, "promoted": True, "mgmt_ip": "192.0.2.7",
                            "golden": {"ok": True, "commit": ""}, "steps": _all_steps_ok()})
    r = _client().post("/v2/onboard/r7/verify", data={"list_name": "probe", "fingerprint": "f"},
                       headers={"HX-Request": "true"})
    return r.status_code, _flat(r.get_data(as_text=True))


def _abandon(monkeypatch):
    monkeypatch.setattr("modules.nsot.onboard.abandon_onboarding",
                        lambda repo, host, lst, **k: {
                            "ok": True, "released": "r8", "remaining": [],
                            "steps": [{"step": "identity", "ok": True,
                                       "detail": "released 'r8'"}]})
    r = _client().post("/v2/onboard/r8/abandon", data={"list_name": "probe", "fingerprint": "f"},
                       headers={"HX-Request": "true"})
    return r.status_code, _flat(r.get_data(as_text=True))


class TestOnboardingSaysItsRunRecordWasNotWritten:
    @pytest.mark.parametrize("run", [_verify, _abandon], ids=["verify", "abandon"])
    def test_the_card_says_so_and_is_not_a_success(self, lab, monkeypatch, run):
        _unwritable_runs(monkeypatch, lab)
        status, html = run(monkeypatch)
        assert status == 200, html
        level, text = _result_notice(html)
        assert "THE RUN RECORD WAS NOT WRITTEN" in text, text
        assert "Is a directory" in text, "the recorder's own reason is drawn"
        assert level == "warn", f"a run whose record failed is drawn as notice-{level}"

    @pytest.mark.parametrize("run", [_verify, _abandon], ids=["verify", "abandon"])
    def test_the_control_a_written_record_draws_a_success(self, lab, monkeypatch, run):
        status, html = run(monkeypatch)
        assert status == 200, html
        level, text = _result_notice(html)
        assert "WAS NOT WRITTEN" not in html
        assert level == "muted", "a run recorded and done is drawn as done"


# ── NetBox's Remove and Stop tracking (C1222) ───────────────────────────────

def _unwritable_removals(monkeypatch, tmp_path):
    from modules import netbox_guard

    where = tmp_path / "removals-are-a-directory"
    where.mkdir()
    monkeypatch.setattr(netbox_guard, "_REMOVALS_FILE", str(where))


def _confirm(networks, operation):
    from modules import netbox_jobs
    import os

    _r, card = _post(networks, "/v2/netbox/preview", {"operation": operation, "list": "Branch"})
    jobs = [n[:-5] for n in os.listdir(netbox_jobs._dir())
            if netbox_jobs.read(n[:-5]).get("operation") == operation]
    job = max(jobs, key=lambda j: os.path.getmtime(netbox_jobs._path(j)))
    r, html = _post(networks, f"/v2/netbox/job/{job}/confirm")
    return r.status_code, _flat(html)


class TestNetBoxSaysItsRemovalRecordWasNotWritten:
    @pytest.mark.parametrize("operation", ["remove", "forget"])
    def test_the_card_says_so_and_is_not_a_success(self, networks, nb, tracked, monkeypatch,
                                                   tmp_path, operation):
        nb["switch"]["on"] = True
        _unwritable_removals(monkeypatch, tmp_path)
        status, html = _confirm(networks, operation)
        assert status == 200, html
        level, text = _result_notice(html)
        assert ("deleted from NetBox for Branch" in text if operation == "remove"
                else "Mercury forgot 3 object(s)" in text), "floor: the operation ran"
        assert "THE REMOVAL RECORD WAS NOT WRITTEN" in text, text
        assert level == "warn", f"a removal whose record failed is drawn as notice-{level}"

    @pytest.mark.parametrize("operation", ["remove", "forget"])
    def test_the_control_a_written_record_draws_a_success(self, networks, nb, tracked,
                                                          operation):
        nb["switch"]["on"] = True
        status, html = _confirm(networks, operation)
        assert status == 200, html
        level, _text = _result_notice(html)
        assert "WAS NOT WRITTEN" not in html
        assert level == "muted"


class TestTheLevelFallsWithTheRecord:
    """`build_result` itself: a record not written lowers success and nothing to partial, and
    leaves a failure a failure."""

    def _result(self, level, written):
        from modules.preview_confirm import build_result

        return build_result(
            action="probe", level=level, summary="it ran", targets=[], did_not=[],
            nothing_left_out="Nothing.", not_watched="nothing",
            record={"statement": "THE RUN RECORD WAS NOT WRITTEN: x", "written": written})

    @pytest.mark.parametrize("level,written,expect", [
        ("success", False, "partial"), ("nothing", False, "partial"),
        ("failed", False, "failed"), ("success", True, "success"),
        ("nothing", True, "nothing")])
    def test_each_level(self, level, written, expect):
        assert self._result(level, written)["level"] == expect
