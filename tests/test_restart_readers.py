"""scripts/nmas-restart-readers: each restart of the app and the readers that failed after it
(C836). The lines are the host's log, 2026-10-15, captured read-only, the checkout's path
replaced by <home>."""
import importlib.machinery
import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOG = """\
2026-10-15 11:02:39,201 INFO modules.reader_job: readers started: adjacencies, dhcp, ztp-discovery [in <home>/modules/reader_job.py:693]
2026-10-15 11:02:41,880 INFO modules.reader_job: reader job-health: run 821c8914c185 on job_finished by nmas-startup-check took 7824 ms: ok [in <home>/modules/reader_job.py:538]
2026-10-15 18:40:41,402 INFO modules.reader_job: readers started: adjacencies, dhcp, ztp-discovery [in <home>/modules/reader_job.py:693]
2026-10-15 18:40:41,688 ERROR modules.reader_job: reader dhcp: the read failed (_DeadlockError: deadlock detected by _ModuleLock('modules.integrations.loki') at 140589990612336); the last good value from 2026-10-15T18:36:13Z is kept [in <home>/modules/reader_job.py:523]
2026-10-15 18:40:41,710 ERROR modules.reader_job: reader ztp-discovery: the read failed (_DeadlockError: deadlock detected by _ModuleLock('modules.integrations') at 140590270279808); the last good value from 2026-10-15T18:40:12Z is kept [in <home>/modules/reader_job.py:523]
2026-10-15 18:52:03,100 ERROR modules.reader_job: reader dhcp: the read failed (ConnectionError: refused); the last good value from 2026-10-15T18:47:13Z is kept [in <home>/modules/reader_job.py:523]
"""


def _cli():
    loader = importlib.machinery.SourceFileLoader(
        "nmas_restart_readers", os.path.join(ROOT, "scripts", "nmas-restart-readers"))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_each_restart_carries_the_failures_in_its_window_alone():
    cli = _cli()
    found = cli.restarts(LOG.splitlines(keepends=True))
    assert [str(r["at"]) for r in found] == ["2026-10-15 11:02:39", "2026-10-15 18:40:41"]
    assert found[0]["failed"] == []
    # The 18:52 failure is 11 minutes after the restart: outside the 300 s window.
    assert [name for name, _e in found[1]["failed"]] == ["dhcp", "ztp-discovery"]
    assert "_ModuleLock('modules.integrations.loki')" in found[1]["failed"][0][1]


def test_the_report_counts_the_clean_restarts_and_names_each_failure():
    cli = _cli()
    out = cli.report(cli.restarts(LOG.splitlines(keepends=True)), last=0)
    assert "2026-10-15 18:40:41 UTC: 2 reader(s) failed" in out
    assert "    ztp-discovery: _DeadlockError: deadlock detected by" in out
    assert out.splitlines()[-1] == "1 of 2 restart(s) with no reader failing"


def test_rotations_are_read_oldest_first(tmp_path):
    cli = _cli()
    log = tmp_path / "device_manager.log"
    lines = LOG.splitlines(keepends=True)
    (tmp_path / "device_manager.log.2").write_text(lines[0])
    (tmp_path / "device_manager.log.1").write_text(lines[1])
    log.write_text("".join(lines[2:]))
    found = cli.restarts(cli.lines_of(str(log)))
    assert [str(r["at"]) for r in found] == ["2026-10-15 11:02:39", "2026-10-15 18:40:41"]
