"""C3886 (the operator's ruling of 2026-11-23: measure, fix, review): the heal confirm's save
check reads through the reads engine (`heal.act._saved_read`), recorded and masked, in this
thread on the act's own hold, as self-healing's reads; never a session of its own. Each case
plants the engine's answer (`reads.run`) and reads the verdict.

Measured first (2026-11-23, offline, r1's and s1's real captures in tests/fixtures/transcripts):
a planted extra line fails the verdict masked as raw, and the configurations are 5.5 to 9.3 KB
against the engine's 32 KiB answer cap. Those captures are already masked, so that measurement
could not see a difference only in a secret's value (C4204, its device-write review): masked
with one placeholder per label, such a pair compared equal. The engine's placeholders now carry
a keyed fingerprint of the value (`redact.KEYED_PLACEHOLDER`, the operator's ruling of
2026-11-23), and `TestASecretOnlyDifference` masks real values through the engine's own mask.
"""
import os
import re

import pytest

from modules.heal import act
from modules.nsot import reads

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(ROOT, "tests", "fixtures", "transcripts")
#: s1's real running configuration, read back as its own startup (a save that held), as the
#: engine answers it: the transcript ends with the device's prompt (`s1#`), which the engine's
#: `send_command` strips (`strip_prompt=True`, modules/commands.py), so the answer ends `end`.
CONFIG = re.sub(r"\n\S+#\s*\Z", "\n",
                open(os.path.join(T, "s1", "show_running-config.txt"), encoding="utf-8").read())
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
    assert one["by"] == "heal" and one["inline"] is True and one["keyed"] is True, one


def test_a_running_line_startup_lacks_fails(engine):
    # The line planted inside the configuration, before its `end`, as a device draws it.
    running = re.sub(r"\nend\n\s*\Z", "\nlogging host 192.0.2.99\nend\n", CONFIG)
    assert running != CONFIG
    engine["answers"].update({"show running-config": running, "show startup-config": CONFIG})
    got = act._saved_read("Lab", {}, "s1")
    assert got["state"] == "fail" and "1 running line(s) not in startup" in got["words"], got


def test_the_real_capture_passes_with_its_own_hostname(engine):
    """C4239: the strict read's hostname is the device's own (`dev["hostname"]`), as Reload's."""
    engine["answers"].update({"show running-config": CONFIG, "show startup-config": CONFIG})
    assert act._saved_read("Lab", {"hostname": "s1"}, "s1")["state"] == "pass"


def test_two_identical_refusals_are_unread_never_a_save_that_held(engine):
    """C4239 (the final review's MEDIUM 3, its probe): both reads refused the same way compare
    equal, so the save check judges only configurations: unread, naming why."""
    refusal = "% Invalid input detected at '^' marker.\n"
    engine["answers"].update({"show running-config": refusal, "show startup-config": refusal})
    got = act._saved_read("Lab", {"hostname": "s1"}, "s1")
    assert got["state"] == "unread" and "did not arrive whole" in got["words"], got


def test_another_device_s_configuration_is_unread(engine):
    engine["answers"].update({"show running-config": CONFIG, "show startup-config": CONFIG})
    got = act._saved_read("Lab", {"hostname": "r9"}, "r9")
    assert got["state"] == "unread" and "its hostname is 's1', not 'r9'" in got["words"], got


def test_no_startup_configuration_is_a_save_that_did_not_hold(engine):
    """IOS answers `show startup-config` on a device that never saved with its own words."""
    engine["answers"].update({"show running-config": CONFIG,
                              "show startup-config": "startup-config is not present\n"})
    got = act._saved_read("Lab", {"hostname": "s1"}, "s1")
    assert got["state"] == "fail" and "no startup configuration" in got["words"], got


def test_a_startup_with_no_end_is_unread(engine):
    startup = re.sub(r"\nend\n\s*\Z", "\n", CONFIG)
    assert "\nend" not in startup[-10:]
    engine["answers"].update({"show running-config": CONFIG, "show startup-config": startup})
    got = act._saved_read("Lab", {"hostname": "s1"}, "s1")
    assert got["state"] == "unread" and "no `end` line" in got["words"], got


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


def test_a_cut_answer_names_its_size_and_the_cap(engine):
    engine["answers"].update({"show running-config": CONFIG, "show startup-config": CONFIG,
                              ("meta", "show running-config"): {"cut": True, "bytes": 48000}})
    got = act._saved_read("Lab", {}, "s1")
    assert got["state"] == "unread", got
    assert "48000 bytes" in got["words"] and f"{act.SAVE_CHECK_CAP_KIB * 1024} bytes" in got["words"], got


def test_the_save_check_reads_with_its_own_cap_never_the_engines(engine):
    """C4210: the engine's cap for a person's reads (32 KiB) made every production-sized
    configuration unread here; the save check asks its own, a whole configuration's."""
    engine["answers"].update({"show running-config": CONFIG, "show startup-config": CONFIG})
    act._saved_read("Lab", {"hostname": "s1"}, "s1")
    (one,) = engine["asked"]
    assert one["cap_kib"] == act.SAVE_CHECK_CAP_KIB and act.SAVE_CHECK_CAP_KIB * 1024 > 2 ** 20


def _with_values(community: str, hashed: str) -> str:
    """s1's capture with real-looking values put back where it was masked."""
    return (CONFIG.replace("<redacted:snmp_community>", community)
            .replace("<redacted:user_password>", hashed))


HASH_A = "$9$abcdefghijklmn$opqrstuvwxyz0123456789ABCDEFGHIJ"
HASH_B = "$9$zyxwvutsrqponm$opqrstuvwxyz0123456789ABCDEFGHIJ"


class TestASecretOnlyDifference:
    """C4204: running and startup differing only in a secret's value, each masked by the
    engine's own mask (`discovery.masked`), are judged different; the same values, the same."""

    @staticmethod
    def _engine_masked(engine, running_raw, startup_raw):
        from modules.discovery import masked
        # The save check's run is keyed (`reads.run`'s *keyed*, asked by `_engine_answers`),
        # salted as the engine salts one device's answers in one run (C4237): its id and host.
        salt = "run-1\x00s1"
        engine["answers"].update({
            "show running-config": masked(running_raw, {}, "cisco_ios", keyed=salt),
            "show startup-config": masked(startup_raw, {}, "cisco_ios", keyed=salt)})

    def test_the_same_secrets_pass(self, engine):
        raw = _with_values("Comm2Ready", HASH_A)
        self._engine_masked(engine, raw, raw)
        assert act._saved_read("Lab", {}, "s1")["state"] == "pass"

    @pytest.mark.parametrize("running,startup", [
        (("Comm2Ready", HASH_A), ("Comm2Drift", HASH_A)),
        (("Comm2Ready", HASH_A), ("Comm2Ready", HASH_B)),
    ], ids=["the community", "a secret 9 hash"])
    def test_a_changed_secret_fails(self, engine, running, startup):
        self._engine_masked(engine, _with_values(*running), _with_values(*startup))
        got = act._saved_read("Lab", {}, "s1")
        assert got["state"] == "fail", got

    def test_no_value_reaches_the_answers(self, engine):
        self._engine_masked(engine, _with_values("Comm2Ready", HASH_A),
                            _with_values("Comm2Drift", HASH_B))
        text = engine["answers"]["show running-config"] + engine["answers"]["show startup-config"]
        assert "Comm2Ready" not in text and "Comm2Drift" not in text and "$9$" not in text


def test_the_act_opens_no_session_for_it():
    import inspect
    src = inspect.getsource(act._saved_read) + inspect.getsource(act._engine_answers)
    assert "with_temp_connection" not in src and "send_command" not in src
