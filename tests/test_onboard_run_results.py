"""7.1: onboarding's Verify and Abandon show their result where it can be read
again.

Both were a toast (Verify's failure was drawn, until the banner reloaded).
Now each run is RECORDED (`onboarding_runs.jsonl`, beside the list's
repository), the route draws its result FROM the recorded row with the result
component, and the pending banner reads it back: each pending row's last run,
and, for a run that took its device off the list (promoted or abandoned),
"finished recently". The row cannot hold those two, and they are the results
most worth reading again.

The record is masked on the way in and created 0600; absent and unreadable
are different facts, and an unreadable record is drawn as that, never as
"no runs". A record that could not be written is part of the result.
"""

import json
import os
import stat

import pytest

from tests.js_source import read_shipped

PERSON = "test-person@example.invalid"


@pytest.fixture
def lab(monkeypatch, tmp_path):
    """A list whose data directory is a temporary one, so the record lands
    where the route derives it and nowhere else."""
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / name))
    monkeypatch.setattr("modules.config.LISTS_DIR", str(tmp_path))
    (tmp_path / "probe" / "config_repo").mkdir(parents=True)
    return tmp_path


def _client():
    import app as A

    return A.app.test_client()


def _steps(ok_upto: int, fail_detail: str = "timeout"):
    from modules.nsot.onboard import PHASE_TWO_STEPS

    out = []
    for i, st in enumerate(PHASE_TWO_STEPS):
        if i < ok_upto:
            out.append({"step": st, "ok": True, "detail": ""})
        elif i == ok_upto:
            out.append({"step": st, "ok": False, "detail": fail_detail})
        else:
            out.append({"step": st, "ok": False, "detail": "did not run"})
    return out


class TestTheRecord:
    def test_created_0600_and_masked_on_the_way_in(self, lab):
        from modules.nsot.onboard import read_runs, record_run, runs_path

        repo = str(lab / "probe" / "config_repo")
        rec = record_run(repo, "verify", "probe", "r7", PERSON, {
            "ok": False, "steps": _steps(0, "refused: snmp-server community S3cretComm RO"),
            "reason": "snmp-server community S3cretComm RO"})
        assert rec["ok"], rec
        path = runs_path(repo)
        assert path == str(lab / "probe" / "onboarding_runs.jsonl")
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        text = open(path, encoding="utf-8").read()
        assert "S3cretComm" not in text, "a reason carrying a community was stored clear"
        assert "<redacted:" in text, "floor: the slot is masked, not the line dropped"
        assert read_runs(repo)["rows"][0]["device"] == "r7"

    def test_absent_and_unreadable_are_different_facts(self, lab):
        from modules.nsot.onboard import read_runs, runs_path

        repo = str(lab / "probe" / "config_repo")
        assert read_runs(repo)["state"] == "absent"
        with open(runs_path(repo), "w", encoding="utf-8") as fh:
            fh.write("{not json\n")
        got = read_runs(repo)
        assert got["state"] == "unreadable" and got["rows"] == [] and got["error"]


class TestTheRoutesDrawFromTheRecordedRow:
    def test_a_verify_is_recorded_and_its_result_is_the_recorded_rows(self, lab, monkeypatch):
        from modules.nsot.onboard import read_runs

        monkeypatch.setattr("modules.nsot.onboard.run_phase_two",
                            lambda repo, host, lst, **k: {
                                "ok": False, "reason": "the capture timed out",
                                "mgmt_ip": "192.0.2.7", "steps": _steps(1)})
        r = _client().post("/onboard/verify/r7", json={"list_name": "probe"})
        assert r.status_code == 409
        d = r.get_json()
        rows = read_runs(str(lab / "probe" / "config_repo"))["rows"]
        assert [row["kind"] for row in rows] == ["verify"]
        assert rows[0]["actor"] == PERSON, "the VERIFIED person, never a body field"
        assert d["result"]["level"] == "partial", "verify ran then capture failed: never green"
        assert "stopped at capture" in d["result"]["happened"]["summary"]
        assert f"by {PERSON}" in d["result"]["record"]["statement"]

    def test_a_record_that_could_not_be_written_is_part_of_the_result(self, lab, monkeypatch):
        monkeypatch.setattr("modules.nsot.onboard.run_phase_two",
                            lambda repo, host, lst, **k: {"ok": False, "reason": "x",
                                                          "steps": _steps(0)})
        # A DIRECTORY where the file goes: open_secure creates missing parents,
        # so a missing directory would be written, and the test would pass
        # without the failure ever happening.
        monkeypatch.setattr("modules.nsot.onboard.runs_path",
                            lambda repo: str(lab / "probe"))
        d = _client().post("/onboard/verify/r7", json={"list_name": "probe"}).get_json()
        assert d["result"]["record"]["statement"].startswith("THE RUN RECORD WAS NOT WRITTEN")

    def test_an_abandon_is_recorded_and_a_dry_run_is_not(self, lab, monkeypatch):
        from modules.nsot.onboard import read_runs

        monkeypatch.setattr("modules.nsot.onboard.abandon_onboarding",
                            lambda repo, host, lst, **k: {
                                "ok": not k.get("dry_run") and True, "released": "r8",
                                "remaining": [],
                                "steps": [{"step": "identity", "ok": True,
                                           "detail": "released 'r8'"}]})
        c = _client()
        c.post("/onboard/abandon/r8", json={"list_name": "probe", "dry_run": True})
        repo = str(lab / "probe" / "config_repo")
        assert read_runs(repo)["state"] == "absent", "a dry run removes nothing: no record"
        d = c.post("/onboard/abandon/r8", json={"list_name": "probe"}).get_json()
        assert read_runs(repo)["rows"][0]["kind"] == "abandon"
        assert d["result"]["level"] == "success"
        assert "the name 'r8' is free" in d["result"]["happened"]["summary"]

    def test_a_partial_abandon_names_what_remains_and_is_not_green(self):
        from modules.preview_confirm import onboard_abandon_result

        r = onboard_abandon_result({
            "device": "r8", "ok": False, "error": "abandon did not finish; 1 step(s) remain",
            "steps": [{"step": "intent", "ok": True, "detail": "removed"},
                      {"step": "netbox", "ok": False, "detail": "refused"}],
            "remaining": [{"step": "netbox", "detail": "refused",
                           "how_to_finish": "run abandon again"}]})
        assert r["level"] == "partial"
        lines = r["did_not"]["items"][0]["lines"]
        assert lines == ["netbox: refused -- to finish: run abandon again"]


class TestThePendingBannerReadsItBack:
    def _banner(self, data):
        import dukpy

        from tests.test_concepts_are_taught import lift

        src = read_shipped("static/js/gen/partials__onboard_pending.1.js")
        return dukpy.evaljs("var window = {};\n" + read_shipped("static/js/nmas_preview_confirm.js")
                            + "\nvar previewConfirmResultHtml = window.previewConfirmResultHtml;\n"
                            + "\n".join(lift(src, n) for n in ("pendingAgeText",
                                                               "pendingBannerHtml"))
                            + f"\npendingBannerHtml({json.dumps(data)})")

    def test_a_pending_rows_last_run_and_a_finished_run_are_drawn(self, monkeypatch, tmp_path):
        from tests import payload_providers as P

        data = P.onboard_pending(monkeypatch, tmp_path)
        r7 = next(r for r in data["pending"] if r["name"] == "r7")
        assert r7["last_run"]["kind"] == "verify"
        assert {f["device"] for f in data["runs"]["finished"]} == {"r8", "r9"}, \
            "the runs that took their device off the list are read back"
        html = self._banner(data)
        assert 'data-onboard-run="verify"' in html and 'data-onboard-finished' in html
        assert "r7 did not answer" in html
        assert "r9 is onboarded" in html and "r8 is abandoned" in html

    def test_nothing_pending_still_shows_what_finished(self):
        from modules.preview_confirm import onboard_abandon_result

        row = {"at": "t", "kind": "abandon", "device": "r8", "actor": PERSON, "ok": True,
               "released": "r8", "steps": [{"step": "identity", "ok": True, "detail": ""}]}
        html = self._banner({"ok": True, "list": "probe", "pending": [], "runs": {
            "state": "ok", "finished": [{"at": "t", "kind": "abandon", "by": PERSON,
                                         "device": "r8",
                                         "result": onboard_abandon_result(row)}]}})
        assert "r8 is abandoned" in html

    def test_an_unreadable_record_is_drawn_as_that(self):
        html = self._banner({"ok": True, "list": "probe", "pending": [],
                             "runs": {"state": "unreadable", "error": "bad json",
                                      "finished": []}})
        assert "data-onboard-runs-unreadable" in html and "not the same as none" in html

    def test_nothing_pending_and_nothing_recorded_draws_nothing(self):
        """The floor: an empty banner stays empty."""
        assert self._banner({"ok": True, "list": "probe", "pending": [],
                             "runs": {"state": "absent", "finished": []}}) == ""


class TestAPromotedDeviceIsNeverDrawnAsPending:
    """R1, 2026-09-28: probe-r1a's Verify ran all eight steps and promoted
    it, and the result's record read "The device's pending row shows it until
    the next run", because this run made no golden commit of its own (the
    rotation had made it first, C147). The row below is the host's recorded
    row, reduced to what the result reads."""

    ROW = {"at": "2026-09-28T07:02:50Z", "kind": "verify", "list": "probe-r1",
           "device": "probe-r1a", "actor": "p@example.invalid", "ok": True,
           "reason": "", "error": "", "remaining": [], "released": "",
           "mgmt_ip": "10.255.0.33", "promoted": True,
           "steps": [{"step": s, "ok": True, "detail": d} for s, d in (
               ("verify", "answered"), ("capture", "264 lines"),
               ("rotate", "rotated and recorded"), ("remove_rw", "0 removed, 0 kept"),
               ("persist", "the startup config carries it"),
               ("golden", "re-read after the removal"), ("netbox", "8 object(s)"),
               ("promote", ""))],
           "verify": {"state": "answered", "error": "", "credential_source": "override",
                      "causes": [], "recovery": {"available": False, "note": "", "command": ""}}}

    def _statement(self, row):
        from modules.preview_confirm import onboard_verify_result
        return onboard_verify_result(row, {"ok": True})["record"]["statement"]

    def test_no_commit_of_its_own_is_said_as_that(self):
        text = self._statement({**self.ROW, "golden_commit": ""})
        assert "pending row" not in text, text
        assert "already held" in text and "in the inventory" in text, text

    def test_a_commit_is_named_and_a_failure_is_still_pending(self):
        """The floors: the commit case names the commit, and a run that
        stopped still points at the pending row."""
        assert "abcdef123456" in self._statement({**self.ROW, "golden_commit": "abcdef1234567890"})
        stopped = {**self.ROW, "ok": False, "promoted": False, "golden_commit": ""}
        assert "pending row" in self._statement(stopped)
