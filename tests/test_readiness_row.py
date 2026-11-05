"""C2514: the Needs attention row for a deployed release that runs and is not ready.

The operator, 2026-11-05: "Approved: C2514, deploy and Update wait for ready (100 s); a timeout
or failed step reports FAILED with a critical row and offers rollback, no automatic rollback."
The row reads the newest record of a release put running by either route
(`update_op.last_deployed`: the updater's history, `nmas-deploy`'s audit), and clears when the
running process's /health says ready, or when another release runs (a rollback landed).
Built against C2465's /health contract with stand-ins (`ready`, `warming`, `not_ready`).
"""

import json

from modules import attention, update_op

TO, FROM, OTHER = "b" * 40, "a" * 40, "c" * 40
WARMING = {"ready": False, "warming": [], "not_ready": "warming: ai-calls running for 3 s"}
READY = {"ready": True, "warming": [], "not_ready": ""}


def _updater_rec(outcome="not_ready", state="failed", **over):
    rec = {"id": "0123456789abcdef", "outcome": outcome, "from": FROM, "to": TO,
           "requested_by": "person@example.invalid", "step": "ready",
           "ended_at": "2026-11-05T10:00:00Z",
           "ready": {"state": state, "step": "ai-calls", "bound_s": 100, "seconds": 0.5,
                     "error": "OSError: the record could not be read" if state == "failed"
                     else "", "not_ready": ""}}
    rec.update(over)
    return rec


def _audit_row(code, ended, to=TO, frm=FROM, ready=None):
    return {"exit": code, "from": frm, "to": to, "user": "operator",
            "restart_issued_at": ended, "ended_at": ended, "verdict": "the verdict",
            "ready": ready or {}}


def _rows(deployed, ready_now=WARMING, running=TO):
    return attention.readiness_source(deployed=deployed, ready_now=ready_now,
                                      running=running)["rows"]


class TestTheRowIsRaised:
    def test_a_failed_step_raises_one_danger_row_naming_the_step_and_its_error(self):
        rows = _rows(dict(_updater_rec(), route="updater"))
        assert len(rows) == 1
        r = rows[0]
        assert r["level"] == "danger" and r["kind"] == "not_ready"
        assert r["what"] == (f"The deployed release {TO[:10]} is not ready: ai-calls failed: "
                             "OSError: the record could not be read")
        assert f"scripts/nmas-rollback {FROM[:10]} --push" in r["action"]["label"]
        assert r["action"]["label"].startswith(f"Roll back to the previous deployed release, "
                                               f"{FROM[:10]}")
        assert "the Update button by person@example.invalid" in r["cause"]
        assert "not rolled back" in r["cause"]
        assert r["operands"]["previous"] == FROM and r["operands"]["route"] == "updater"

    def test_still_warming_at_the_bound_says_so_and_offers_the_wait_too(self):
        rec = dict(_updater_rec(state="warming"), route="updater")
        r = _rows(rec)[0]
        assert r["what"] == (f"The deployed release {TO[:10]} is not ready: ai-calls still "
                             "warming after 100 s")
        assert "or wait, while it may still finish warming" in r["action"]["label"]
        assert "warming: ai-calls running for 3 s" in r["cause"]      # what /health says now

    def test_a_failed_terminal_deploy_raises_it_from_the_deploy_audit(self, tmp_path,
                                                                      monkeypatch):
        audit = tmp_path / "deploy_audit.jsonl"
        audit.write_text(json.dumps(_audit_row(11, "2026-11-05T10:00:00.123Z", ready={
            "state": "warming", "step": "needs-attention", "bound_s": 100})) + "\n")
        monkeypatch.setattr(update_op, "DEPLOY_AUDIT", str(audit))
        rec = update_op.last_deployed(updater_rows=[])
        assert rec["route"] == "terminal" and rec["outcome"] == "not_ready"
        r = _rows(rec)[0]
        assert "needs-attention still warming after 100 s" in r["what"]
        assert "a terminal nmas-deploy by operator" in r["cause"]

    def test_the_kind_says_how_it_clears_and_is_in_the_page(self):
        assert attention.CLEARS[("readiness", "not_ready")][0] == ("resolves",)
        assert attention.readiness_source in attention.SOURCES
        assert attention.SOURCE_KEYS["readiness_source"] == ("app_version",)


class TestTheRowClears:
    def test_when_the_running_process_says_ready(self):
        assert _rows(dict(_updater_rec(), route="updater"), ready_now=READY) == []

    def test_when_a_rollback_landed_and_another_release_runs(self):
        assert _rows(dict(_updater_rec(), route="updater"), running=FROM) == []

    def test_when_a_later_deploy_by_the_other_route_ended_ready(self):
        """The newest record of either route is the deployed release: a terminal deploy after
        the Update (here the same commit again, ready) supersedes its not-ready record."""
        rec = update_op.last_deployed(
            updater_rows=[_updater_rec()],
            audit_rows=[_audit_row(0, "2026-11-05T10:05:00.000Z", frm=TO, ready={
                "state": "ready"})])
        assert rec["route"] == "terminal" and rec["outcome"] == "updated"
        assert _rows(rec) == []

    def test_a_refused_request_after_it_does_not_hide_it(self):
        """A refusal moved nothing, so the release it was refused over is still the deployed
        one: the updater's history is read past it."""
        refused = {"outcome": "refused", "from": TO, "to": OTHER,
                   "ended_at": "2026-11-05T10:06:00Z"}
        rec = update_op.last_deployed(updater_rows=[refused, _updater_rec()], audit_rows=[])
        assert rec["outcome"] == "not_ready" and len(_rows(rec)) == 1

    def test_a_process_that_cannot_say_ready_does_not_clear_it(self, monkeypatch):
        """No warm-up in this process (`_ready_now` None) is never read as ready."""
        monkeypatch.setattr(attention, "_ready_now", lambda: None)
        rows = attention.readiness_source(deployed=dict(_updater_rec(), route="updater"),
                                          running=TO)["rows"]
        assert len(rows) == 1 and "cannot say whether it is ready" in rows[0]["cause"]


class TestNoRowWhenNothingIsWrong:
    def test_an_updated_release_and_no_record_make_none(self):
        assert _rows(dict(_updater_rec(outcome="updated", state="ready"), route="updater")) == []
        res = attention.readiness_source(deployed={}, ready_now=WARMING, running=TO)
        assert res["rows"] == [] and res["checked"] == "no deploy by either route is recorded"
