"""A correct install clears its job-health row at the next read of the page (C439; 2026-10-04).

The operator installed this release's Oxidized helper, and minutes later Needs attention still
said "helper:oxidized-cred differs from this release's copy (installed d03532c08b0a, this
release 355818515ba5)". Measured on the host the same day: the installed copy matched, and the
job-health reader's next read (every 300 s) cleared the row. The row's promise, "job health
re-reads every minute", was false, the row did not say when it was read, and the host-step
check of the same helper is asked live: two owners of one fact, minutes apart.

Now a stored job-health row about a root-installed file (`host_helpers.INSTALL_UNITS`) that
reads not-ok is asked again at the read of the page, so an install clears it at once and never
shows the reading from before it. A stored ok row is not asked again: the Oxidized row's check
runs `sudo -n -l`, which would be a sudo query per page view, and the rotation preflight asks
the helper itself live (`credential_rotation.preflight`), so a correct install is never
refused on a stored value. Every job-health row says when its reading was taken.

The helper's real comparison runs (this release's `scripts/nmas-oxidized-cred` against a copy in
a temporary folder); only root ownership, the pin and sudo are stood in for, since a test can
make none of them.
"""

import os
import shutil

import pytest

from modules import attention as A
from modules import config
from modules import reader_job as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(ROOT, "scripts", "nmas-oxidized-cred")
T0 = 1_790_000_000.0
ROW = "job_health:helper:oxidized-cred"


@pytest.fixture
def helper(tmp_path, monkeypatch):
    """A drifted installed copy, read as root-owned, pinned and runnable by sudo."""
    from modules.nsot import credential_rotation as cr

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    installed = tmp_path / "nmas-oxidized-cred"
    installed.write_bytes(open(HELPER, "rb").read() + b"# an older release\n")
    os.chmod(installed, 0o755)
    real = os.stat

    def stat(p, *a, **k):
        st = real(p, *a, **k)
        if str(p) != str(installed):
            return st
        fields = list(st)
        fields[4] = 0                                   # st_uid: root's
        return os.stat_result(fields)
    monkeypatch.setattr(os, "stat", stat)
    monkeypatch.setattr(cr, "HELPER_INSTALLED", str(installed))
    monkeypatch.setattr(cr, "helper_pin_status", lambda **kw: {"ok": True})
    monkeypatch.setattr(cr, "helper_sudo_status", lambda **kw: {"ok": True, "reason": ""})
    return installed


def _store_a_reading(monkeypatch):
    """The job-health reader's real run, its value the helper's real row at that moment."""
    from modules import host_helpers
    from modules import job_health as J
    from modules.readers import job_health_reader as JHR

    monkeypatch.setattr(J, "health", lambda **kw: {"jobs": [host_helpers.oxidized_row()]})
    return R.run_once(JHR.READER, clock=lambda: T0)


def _install(installed):
    """The operator's install, `install -m 0755` of this release's copy."""
    shutil.copy(HELPER, installed)
    os.chmod(installed, 0o755)


def _rows(res):
    return {r["id"]: r for r in res["rows"]}


def test_a_correct_install_clears_the_row_at_the_next_read_of_the_page(helper, monkeypatch):
    _store_a_reading(monkeypatch)
    before = _rows(A.job_health_source(readers_now=[]))
    assert ROW in before, "the drifted helper drew no row"
    assert "differs" in before[ROW]["what"] or "differs" in before[ROW]["cause"], before[ROW]
    _install(helper)
    after = _rows(A.job_health_source(readers_now=[]))
    assert ROW not in after, ("a correct install still drawn as wrong, from the stored "
                              f"reading: {after.get(ROW)}")


def test_a_still_wrong_install_is_drawn_from_a_reading_taken_now(helper, monkeypatch):
    import time

    _store_a_reading(monkeypatch)
    started = time.time()
    row = _rows(A.job_health_source(readers_now=[]))[ROW]
    assert row["read_at"] >= A._iso(started), row["read_at"]


def test_a_stored_ok_row_is_not_asked_again(helper, monkeypatch):
    from modules import host_helpers

    _install(helper)
    _store_a_reading(monkeypatch)
    calls = []
    real = host_helpers.oxidized_row
    monkeypatch.setattr(host_helpers, "oxidized_row", lambda: calls.append(1) or real())
    res = A.job_health_source(readers_now=[])
    assert ROW not in _rows(res) and calls == [], "an ok row asked sudo again on a page view"


def test_every_stored_row_says_when_its_reading_was_taken(monkeypatch, tmp_path):
    from modules import job_health as J
    from modules.readers import job_health_reader as JHR

    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(J, "health", lambda **kw: {"jobs": [
        {"unit": "nmas-backup", "state": "failed", "what": "the backup", "detail": "exit 1",
         "max_age_minutes": 0}]})
    R.run_once(JHR.READER, clock=lambda: T0)
    row = _rows(A.job_health_source(readers_now=[]))["job_health:nmas-backup"]
    assert row["read_at"] == A._iso(T0), row


def test_the_row_draws_its_reading_time():
    from flask import render_template

    import app as APP

    row = A.row(source="job_health", kind="job", key="u", what="u failed", cause="c",
                action={"label": "Run it again"}, level="warning", read_at=T0)
    with APP.app.test_request_context("/v2/"):
        html = render_template("v2/_attention.html", a={
            "ok": True, "rows": [row], "sources": [], "headline": "1", "counts": {},
            "badge": {"n": 1, "level": "warning"}})
    meta = html.split('class="att-meta"')[1].split("</p>")[0]
    assert "read at" in meta and A._iso(T0) in meta, meta


def test_the_clearing_words_state_the_readers_real_interval():
    """The row promised "every minute" against a 300 s reader: the words must match the
    reader's interval, keep the host job's finish (`POST /jobs/finished` reads job health at
    once), and say when an install row is asked again."""
    import ast

    from modules.readers import job_health_reader as JHR

    when = A.CLEARS[("job_health", "job")][1]
    assert f"every {JHR.INTERVAL_SECONDS // 60} minutes" in when, when
    assert "every minute" not in when, when
    src = open(os.path.join(ROOT, "routes", "jobs.py"), encoding="utf-8").read()
    finished = next(n for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.FunctionDef) and n.name == "job_finished")
    assert "request_run(job_health_reader.READER" in ast.unparse(finished)
    assert "as soon as a host job finishes" in when, when
    assert "at the next read of this page" in when, when


def test_every_installed_file_s_row_is_asked_again():
    """The registry of root-installed files and the units asked again are one set, so a helper
    added to the registry cannot keep a stale row."""
    from modules import host_helpers

    assert set(host_helpers.INSTALL_UNITS) == {h["unit"] for h in host_helpers.registry()}
