"""A host job ending wakes the job-health reader at once (C283).

The operator, 2026-10-01: the startup check succeeded at 07:23 through its own
unit, `nmas-jobs` read ok at 07:25, and Needs attention showed the old Critical
row ("last success 138 min ago ... 2 consecutive failures") until the
job-health reader's next scheduled run, about 07:30. Every job unit in the
repository now names `nmas-job-finished@%N.service` in `OnSuccess=` and
`OnFailure=`; systemd starts it once the job's result is recorded (a job a
person starts by hand included), and `scripts/nmas-job-finished` posts the unit
to `/jobs/finished`, which runs the reader now, records why, and announces.
"""

import importlib.machinery
import importlib.util
import io
import json
import os
import re
import urllib.error

import pytest

from modules import job_health, reader_job
from modules.readers import job_health_reader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNITS = os.path.join(ROOT, "deploy", "systemd")


def _client():
    import app as A
    return A.app.test_client()


class TestTheRoute:
    def test_an_undeclared_unit_is_refused_naming_the_declared_jobs(self, monkeypatch):
        started = []
        monkeypatch.setattr(reader_job, "running", lambda name: True)
        monkeypatch.setattr(reader_job, "request_run", lambda *a, **k: started.append(a))
        r = _client().post("/jobs/finished", json={"unit": "sshd"})
        body = r.get_json()
        assert r.status_code == 400 and started == []
        assert body["error"].startswith("sshd is not a job this app reads")
        assert "nmas-startup-check" in body["error"]

    def test_where_the_readers_do_not_run_nothing_is_read(self, monkeypatch):
        started = []
        monkeypatch.setattr(reader_job, "request_run", lambda *a, **k: started.append(a))
        r = _client().post("/jobs/finished", json={"unit": "nmas-startup-check.service"})
        assert r.status_code == 409 and started == []
        assert "do not run in this process" in r.get_json()["error"]

    def test_a_declared_job_runs_the_reader_now_recording_why(self, monkeypatch):
        calls = []
        monkeypatch.setattr(reader_job, "running", lambda name: True)

        def request_run(reader, by, announce=None, kind="request"):
            calls.append((reader.name, by, kind, announce))
            return {"run": "abc123", "started": len(calls) == 1}
        monkeypatch.setattr(reader_job, "request_run", request_run)
        r = _client().post("/jobs/finished", json={"unit": "nmas-startup-check.service"})
        assert r.status_code == 202 and r.get_json() == {
            "ok": True, "unit": "nmas-startup-check", "started": True, "run": "abc123"}
        assert calls == [("job-health", "nmas-startup-check", "job_finished",
                          reader_job.announce_via_page)]
        again = _client().post("/jobs/finished", json={"unit": "nmas-startup-check"})
        assert again.status_code == 200 and again.get_json()["started"] is False


class TestTheRunRecordsItsCause:
    def test_a_job_finished_run_is_recorded_and_announced_unchanged(self, monkeypatch):
        """An unchanged answer is still announced: the page showing the old
        row is waiting on it (as a person's request is, C244)."""
        import dataclasses
        import time

        heard = []
        # A change-only reader announced moments ago: an unchanged scheduled
        # run would be skipped (its keepalive not due), so only the cause can
        # make this one announce.
        fake = dataclasses.replace(job_health_reader.READER, read=lambda: {"health": {"jobs": []}},
                                   announce_if=lambda old, new: False,
                                   announce_at_least_every=3600)
        monkeypatch.setattr(reader_job, "_REQUESTS", {})
        monkeypatch.setattr(reader_job, "_LAST_ANNOUNCED", {fake.name: time.time()})
        got = reader_job.request_run(fake, "nmas-startup-check", kind="job_finished",
                                     announce=lambda keys, name, ok: heard.append((tuple(keys), ok)))
        end = time.monotonic() + 10
        while not reader_job._REQUESTS[fake.name]["done"] and time.monotonic() < end:
            time.sleep(0.02)
        doc = reader_job.read_cached(fake.name)["doc"]
        want = {"kind": "job_finished", "by": "nmas-startup-check", "run": got["run"]}
        assert doc["last_attempt"]["trigger"] == want
        assert heard == [(("job_health",), True)]
        assert reader_job.trigger_words(want) == "re-read when nmas-startup-check finished"


def _load_script():
    path = os.path.join(ROOT, "scripts", "nmas-job-finished")
    loader = importlib.machinery.SourceFileLoader("nmas_job_finished", path)
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
    loader.exec_module(mod)
    return mod


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestTheSender:
    def test_it_posts_the_unit_and_nothing_else(self, monkeypatch, capsys):
        mod = _load_script()
        sent = []

        def urlopen(req, timeout):
            sent.append((req.full_url, req.get_method(), json.loads(req.data), timeout))
            return _Answer(b'{"ok": true, "started": true, "run": "r1"}')
        monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
        monkeypatch.setenv("NMAS_URL", "http://127.0.0.1:5999/")
        assert mod.main(["nmas-startup-check"]) == 0
        assert sent == [("http://127.0.0.1:5999/jobs/finished", "POST",
                         {"unit": "nmas-startup-check"}, mod.TIMEOUT_S)]
        assert "job health is being read now (run r1)" in capsys.readouterr().out

    def test_a_refusal_is_exit_1_with_the_apps_reason(self, monkeypatch, capsys):
        mod = _load_script()

        def urlopen(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 409, "Conflict", {},
                                         io.BytesIO(b'{"error": "the reader jobs do not run"}'))
        monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
        assert mod.main(["nmas-startup-check"]) == 1
        assert "HTTP 409): the reader jobs do not run" in capsys.readouterr().err

    def test_an_app_that_cannot_be_asked_is_exit_2_saying_what_follows(self, monkeypatch, capsys):
        mod = _load_script()

        def urlopen(req, timeout):
            raise urllib.error.URLError("Connection refused")
        monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
        assert mod.main(["nmas-startup-check"]) == 2
        assert "read at the reader's next run instead" in capsys.readouterr().err


def _unit(name):
    with open(os.path.join(UNITS, name), encoding="utf-8") as f:
        return f.read()


class TestEveryJobUnitWakesTheReader:
    def test_every_declared_job_with_a_unit_here_names_the_sender_both_ways(self):
        declared = {j["unit"] for j in job_health.JOBS}
        here = {n[:-len(".service")] for n in os.listdir(UNITS)
                if n.endswith(".service") and "@" not in n}
        jobs_here = sorted(declared & here)
        assert len(jobs_here) >= 4, jobs_here               # the floor: the scan finds them
        for u in jobs_here:
            text = _unit(u + ".service")
            unit_section = text.split("[Service]")[0]
            assert re.search(r"^OnSuccess=nmas-job-finished@%N\.service$", unit_section, re.M), u
            assert re.search(r"^OnFailure=nmas-job-finished@%N\.service$", unit_section, re.M), u
        # Named, so the gap is a decision: clab-sync's unit lives on the host,
        # outside this repository, and is read at the reader's schedule.
        assert sorted(declared - here) == ["clab-sync"]

    def test_the_sender_unit_runs_the_script_with_the_instance(self):
        text = _unit("nmas-job-finished@.service")
        assert re.search(r"^ExecStart=@NMAS_CHECKOUT@/scripts/nmas-job-finished %i$", text, re.M)
        assert re.search(r"^Type=oneshot$", text, re.M)
        assert re.search(r"^User=@NMAS_USER@$", text, re.M)
        # Never wakes itself (anchored: the comment above the unit names both).
        assert not re.search(r"^On(Success|Failure)=", text, re.M)


@pytest.mark.parametrize("removed", ["OnSuccess", "OnFailure"])
def test_the_rule_finds_a_unit_missing_either_half(removed, tmp_path, monkeypatch):
    """The control: a unit that names only one half is found."""
    for n in os.listdir(UNITS):
        text = _unit(n)
        if n == "nmas-startup-check.service":
            text = re.sub(rf"^{removed}=.*\n", "", text, flags=re.M)
        (tmp_path / n).write_text(text)
    monkeypatch.setattr(__import__(__name__), "UNITS", str(tmp_path))
    with pytest.raises(AssertionError):
        TestEveryJobUnitWakesTheReader().test_every_declared_job_with_a_unit_here_names_the_sender_both_ways()


def test_the_sender_never_reads_systemds_monitor_variables():
    """The operator's install, 2026-10-01: two runs of the startup check ended
    before one sender started, and systemd logged "multiple trigger source
    candidates for exit status propagation ... skipping", setting no
    MONITOR_SERVICE_RESULT or other MONITOR_* variable. The sender takes the
    unit from its argument and reads one environment variable, NMAS_URL."""
    import ast
    src = open(os.path.join(ROOT, "scripts", "nmas-job-finished"), encoding="utf-8").read()
    assert "MONITOR_" not in src
    reads = set()
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("get", "getenv")
                and ast.unparse(node.func.value) in ("os.environ", "os")):
            reads.add(node.args[0].value)
        if isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
            reads.add(ast.unparse(node.slice))
    assert reads == {"NMAS_URL"}, reads
    unit = _unit("nmas-job-finished@.service")
    assert re.search(r"^ExecStart=\S+nmas-job-finished %i$", unit, re.M)
