"""`scripts/nmas-scheduled-failures` (the operator, 2026-11-05; C2552: a red weekly mutation run
went unflagged for ten days). A failed scheduled job is listed; one the register does not name
is printed as a ready row, or written with --write after the newest open row; a dispatched run
and a success are never failures. Its sources are faked (no API, no host)."""
import importlib.machinery
import importlib.util
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def sf(tmp_path, monkeypatch):
    path = os.path.join(ROOT, "scripts", "nmas-scheduled-failures")
    loader = importlib.machinery.SourceFileLoader("nmas_scheduled_failures", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    reg = tmp_path / "OPEN_FINDINGS.md"
    reg.write_text("## C. Tooling\n\n| # | Finding | Kind | Where recorded |\n|---|---|---|---|\n"
                   "| C10 | **an old row** | **[C: x]** | x |\n"
                   "| C12 | **the newest row** | **[C: x]** | x |\n\n## Closed\n\n"
                   "| C99 | **closed** | 2026-01-01 | fixed |\n")
    monkeypatch.setattr(mod, "REGISTER", str(reg))
    return mod, reg


def _run(n, event, conclusion, day="2026-11-01"):
    return {"run_number": n, "event": event, "status": "completed", "conclusion": conclusion,
            "created_at": f"{day}T18:39:24Z", "html_url": f"https://example.invalid/runs/{n}"}


def _runs(table):
    return lambda wf: table.get(wf, [])


OK_HOST = "Result=success\nExecMainExitTimestamp=Wed 2026-11-04 09:00:00 UTC\n"


class TestWhatCountsAsAFailure:
    def test_the_newest_scheduled_run_failing_is_one(self, sf):
        mod, _ = sf
        got = mod.workflow_failures(_runs({"mutation-nightly.yml": [
            _run(67, "schedule", "failure"), _run(68, "schedule", "failure"),
            _run(70, "workflow_dispatch", "failure")]}))
        assert [f["key"] for f in got] == ["mutation-nightly #68"]

    def test_a_scheduled_success_and_dispatches_are_not(self, sf):
        mod, _ = sf
        got = mod.workflow_failures(_runs({"coverage-nightly.yml": [
            _run(40, "schedule", "failure"), _run(41, "schedule", "success"),
            _run(42, "workflow_dispatch", "failure")]}))
        assert got == []

    def test_a_host_unit_that_did_not_end_in_success(self, sf):
        mod, _ = sf
        texts = {"nmas-netbox-backup": "Result=exit-code\n"
                                       "ExecMainExitTimestamp=Wed 2026-11-04 09:00:00 UTC\n"}
        got = mod.host_failures(lambda unit: texts.get(unit, OK_HOST))
        assert [f["key"] for f in got] == ["nmas-netbox-backup failed 2026-11-04"]


class TestRaisedOrNot:
    def test_an_unraised_failure_is_printed_as_a_ready_row_exit_3(self, sf, capsys):
        mod, reg = sf
        before = reg.read_text()
        code = mod.main(["--no-host"], get_runs=_runs({"mutation-nightly.yml": [
            _run(68, "schedule", "failure")]}), today="2026-11-05")
        out = capsys.readouterr().out
        assert code == 3 and reg.read_text() == before
        assert "| C100 | **A scheduled job failed:" in out  # above every id, closed ones included and "(mutation-nightly #68)" in out

    def test_write_inserts_it_after_the_newest_open_row_exit_1(self, sf, capsys):
        mod, reg = sf
        code = mod.main(["--no-host", "--write"], get_runs=_runs({"mutation-nightly.yml": [
            _run(68, "schedule", "failure")]}), today="2026-11-05")
        lines = reg.read_text().splitlines()
        assert code == 1
        at = next(i for i, ln in enumerate(lines) if ln.startswith("| C12 "))
        assert lines[at + 1].startswith("| C100 | **A scheduled job failed:")
        assert "now raised as C100" in capsys.readouterr().out

    def test_a_raised_failure_is_said_and_not_written_again(self, sf, capsys):
        mod, reg = sf
        reg.write_text(reg.read_text().replace("**the newest row**",
                                               "**mutation-nightly #68 failed**"))
        before = reg.read_text()
        code = mod.main(["--no-host", "--write"], get_runs=_runs({"mutation-nightly.yml": [
            _run(68, "schedule", "failure")]}), today="2026-11-05")
        assert code == 1 and reg.read_text() == before
        assert "each raised in the register" in capsys.readouterr().out

    def test_nothing_failing_exit_0(self, sf, capsys):
        mod, _ = sf
        assert mod.main([], get_runs=_runs({}), show=lambda u: OK_HOST) == 0
        assert "none failing" in capsys.readouterr().out

    def test_a_source_that_cannot_be_asked_exit_2_never_a_pass(self, sf, capsys):
        mod, _ = sf

        def boom(wf):
            raise RuntimeError("the API could not be asked")
        assert mod.main(["--no-host"], get_runs=boom) == 2
        assert "could not be asked" in capsys.readouterr().err
