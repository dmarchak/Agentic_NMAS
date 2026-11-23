"""C3886 (the operator's ruling of 2026-11-23: measure, fix, review): the heal confirm's save
check reads through the reads engine (`heal.act._saved_read`), recorded and masked, in this
thread on the act's own hold, as self-healing's reads; never a session of its own. Each case
plants the engine's answer (`reads.run`) and reads the verdict.

Measured first (2026-11-23, offline, r1's and s1's real captures in tests/fixtures/transcripts):
`roundtrip.startup_is_running` gives the same verdict and the same differing lines on the
engine's masked text as on raw text, a planted extra line fails both, and the configurations
are 5.5 to 9.3 KB against the engine's 32 KiB answer cap.
"""
import os

import pytest

from modules.heal import act
from modules.nsot import reads

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(ROOT, "tests", "fixtures", "transcripts")
#: s1's real running configuration, read back as its own startup (a save that held).
CONFIG = open(os.path.join(T, "s1", "show_running-config.txt"), encoding="utf-8").read()
#: r1's real startup, which keeps its certificates as files in nvram:.
R1_STARTUP = open(os.path.join(T, "r1", "show_startup-config.txt"), encoding="utf-8").read()


@pytest.fixture
def engine(monkeypatch):
    """The reads engine stood in: each run's arguments kept, its answers what the test sets."""
    asked, answers = [], {}

    def run(network, hosts, commands, actor, **kw):
        asked.append({"network": network, "hosts": hosts, "commands": list(commands), **kw})
        if answers.get("refused"):
            raise reads.Refused(answers["refused"])
        return {"id": "run-1", "results": {hosts[0]: {"answers": [
            dict({"command": c, "state": reads.ANSWERED, "answer": answers.get(c, "")},
                 **answers.get(("meta", c), {})) for c in commands]}}}
    monkeypatch.setattr(reads, "run", run)
    return {"asked": asked, "answers": answers}


def test_startup_holding_what_runs_passes_through_one_engine_run(engine):
    engine["answers"].update({"show running-config": CONFIG, "show startup-config": CONFIG})
    got = act._saved_read("Lab", {"ip": "192.0.2.11"}, "s1")
    assert got["state"] == "pass", got
    (one,) = engine["asked"]
    assert one["commands"] == list(act.SAVED_READS) and one["hosts"] == ["s1"]
    assert one["by"] == "heal" and one["inline"] is True, one


def test_a_running_line_startup_lacks_fails(engine):
    engine["answers"].update({"show running-config": CONFIG + "logging host 192.0.2.99\n",
                              "show startup-config": CONFIG})
    got = act._saved_read("Lab", {}, "s1")
    assert got["state"] == "fail" and "1 running line(s) not in startup" in got["words"], got


def test_a_cut_answer_is_never_judged(engine):
    engine["answers"].update({"show running-config": CONFIG, "show startup-config": CONFIG,
                              ("meta", "show startup-config"): {"cut": True}})
    got = act._saved_read("Lab", {}, "s1")
    assert got["state"] == "unread" and "not answered whole" in got["words"], got


def test_a_refused_run_is_unread(engine):
    engine["answers"]["refused"] = "Refused: s1 is held by deploy"
    got = act._saved_read("Lab", {}, "s1")
    assert got["state"] == "unread" and "held by deploy" in got["words"], got


def test_a_certificate_in_nvram_asks_dir_nvram_as_a_second_engine_read(engine):
    engine["answers"].update({"show running-config": CONFIG,
                              "show startup-config": R1_STARTUP, "dir nvram:": ""})
    act._saved_read("Lab", {}, "s1")
    assert [a["commands"] for a in engine["asked"]] == [list(act.SAVED_READS), ["dir nvram:"]]


def test_the_act_opens_no_session_for_it():
    import inspect
    src = inspect.getsource(act._saved_read) + inspect.getsource(act._engine_answers)
    assert "with_temp_connection" not in src and "send_command" not in src
