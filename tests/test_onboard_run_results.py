"""7.1: onboarding's Verify and Abandon show their result where it can be read
again.

Both were a toast (Verify's failure was drawn, until the banner reloaded).
Now each run is RECORDED (`onboarding_runs.jsonl`, beside the list's
repository), the route draws its result FROM the recorded row with the result
component, and it is read back: each pending device's page draws its last run,
and every run, one that took its device off the list (promoted or abandoned)
included, is a row of the network's History (today's pending banner read both
back until it left at 7.8, 2026-10-17, P7-25). The row cannot hold those two,
and they are the results most worth reading again.

The record is masked on the way in and created 0600; absent and unreadable
are different facts, and an unreadable record is drawn as that, never as
"no runs". A record that could not be written is part of the result.
"""

import os
import stat

import pytest

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
    """v2's pending page's Verify and Abandon (today's /onboard/verify and /onboard/abandon,
    which these drove, left at 7.8 on 2026-10-17, P7-25): the record is written by the route,
    as the verified person; the result is the core's, drawn from the recorded row."""

    def test_a_verify_is_recorded_and_its_result_is_the_recorded_rows(self, lab, monkeypatch):
        import types

        from modules.nsot.onboard import read_runs
        from routes.onboard import verify_run

        monkeypatch.setattr("modules.nsot.onboard.run_phase_two",
                            lambda repo, host, lst, **k: {
                                "ok": False, "reason": "the capture timed out",
                                "mgmt_ip": "192.0.2.7", "steps": _steps(1)})
        r = _client().post("/v2/onboard/r7/verify",
                           data={"list_name": "probe", "fingerprint": "f", "actor": "forged"})
        assert r.status_code == 409
        repo = str(lab / "probe" / "config_repo")
        rows = read_runs(repo)["rows"]
        assert [row["kind"] for row in rows] == ["verify"]
        assert rows[0]["actor"] == PERSON, "the VERIFIED person, never a body field"
        d, status = verify_run("r7", {"list_name": "probe", "fingerprint": "f"},
                               types.SimpleNamespace(actor=PERSON, kind="person"))
        assert status == 409
        assert d["result"]["level"] == "partial", "verify ran then capture failed: never green"
        assert "stopped at capture" in d["result"]["happened"]["summary"]
        assert f"by {PERSON}" in d["result"]["record"]["statement"]

    def test_a_record_that_could_not_be_written_is_part_of_the_result(self, lab, monkeypatch):
        import types

        from routes.onboard import verify_run

        monkeypatch.setattr("modules.nsot.onboard.run_phase_two",
                            lambda repo, host, lst, **k: {"ok": False, "reason": "x",
                                                          "steps": _steps(0)})
        # A DIRECTORY where the file goes: open_secure creates missing parents,
        # so a missing directory would be written, and the test would pass
        # without the failure ever happening.
        monkeypatch.setattr("modules.nsot.onboard.runs_path",
                            lambda repo: str(lab / "probe"))
        d, _status = verify_run("r7", {"list_name": "probe", "fingerprint": "f"},
                                types.SimpleNamespace(actor=PERSON, kind="person"))
        assert d["result"]["record"]["statement"].startswith("THE RUN RECORD WAS NOT WRITTEN")

    def test_an_abandon_is_recorded_and_a_dry_run_is_not(self, lab, monkeypatch):
        from modules.nsot.onboard import read_runs
        from routes.onboard import abandon_run

        monkeypatch.setattr("modules.nsot.onboard.abandon_onboarding",
                            lambda repo, host, lst, **k: {
                                "ok": not k.get("dry_run") and True, "released": "r8",
                                "remaining": [],
                                "steps": [{"step": "identity", "ok": True,
                                           "detail": "released 'r8'"}]})
        c = _client()
        c.post("/v2/onboard/r8/abandon/preview", data={"list_name": "probe"})
        repo = str(lab / "probe" / "config_repo")
        assert read_runs(repo)["state"] == "absent", "a dry run removes nothing: no record"
        c.post("/v2/onboard/r8/abandon", data={"list_name": "probe", "fingerprint": "f"})
        assert read_runs(repo)["rows"][0]["kind"] == "abandon"
        d, _status = abandon_run("r8", {"list_name": "probe"}, PERSON, confirmed="f")
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


class TestTheRunsAreReadBack:
    """Today's pending banner read the runs back (each pending row's last run, and the runs
    that took their device off the list) until it left at 7.8 (2026-10-17, P7-25). On v2 a
    pending device's page draws its last run, and an unreadable record as that
    (tests/test_onboard_v2.py, `test_the_page_draws_today_s_banner_facts`); every run, the
    finished ones included, is a row of the network's History (`history_sources.onboarding`),
    held here against the real record."""

    def _history(self, repo):
        import types

        from modules import history_sources

        return history_sources.onboarding({"ref": types.SimpleNamespace(repo_dir=repo),
                                           "limit": 50, "device": "", "members": None})

    def test_every_run_the_finished_ones_included_is_a_history_row(self, lab):
        from modules.nsot.onboard import PHASE_TWO_STEPS, record_run

        repo = str(lab / "probe" / "config_repo")
        record_run(repo, "verify", "probe", "r7", PERSON, {
            "ok": False, "reason": "did not answer", "steps": _steps(0, "did_not_answer")})
        record_run(repo, "verify", "probe", "r9", PERSON, {
            "ok": True, "promoted": True, "golden": {"ok": True, "commit": "0123456789abcdef"},
            "steps": [{"step": st, "ok": True, "detail": ""} for st in PHASE_TWO_STEPS]})
        record_run(repo, "abandon", "probe", "r8", PERSON, {
            "ok": True, "released": "r8", "remaining": [],
            "steps": [{"step": "identity", "ok": True, "detail": "released 'r8'"}]})
        got = self._history(repo)
        assert got["errors"] == []
        by = {e["devices"][0]: e for e in got["events"]}
        assert set(by) == {"r7", "r8", "r9"}, by
        assert by["r7"]["what"] == "Onboarding verify: stopped" and by["r7"]["outcome"] == \
            "failed"
        assert by["r9"]["what"] == "Onboarding verify: done" and by["r8"]["what"] == \
            "Onboarding abandon: done"
        assert all(e["who"] == PERSON for e in got["events"])

    def test_an_unreadable_record_is_said_never_none(self, lab):
        from modules.nsot.onboard import runs_path

        repo = str(lab / "probe" / "config_repo")
        with open(runs_path(repo), "w", encoding="utf-8") as fh:
            fh.write("{not json\n")
        got = self._history(repo)
        assert got["events"] == [] and got["errors"]
        assert got["errors"][0].startswith("the onboarding runs could not be read")

    def test_nothing_recorded_is_nothing_and_no_error(self, lab):
        """The floor: an absent record draws no row and no failure."""
        got = self._history(str(lab / "probe" / "config_repo"))
        assert got["events"] == [] and got["errors"] == []


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
