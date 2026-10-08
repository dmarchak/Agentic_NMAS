"""The reads engine (modules/nsot/reads.py; NSOT_READS.md section 2, signed off 2026-10-08).

Each property the design names, on real answers: r2's sanitized running configuration
(`tests/fixtures/configs/fleet/r2.cfg`, its credentials the capture's fakes) and real
`show ip interface` captures (`tests/fixtures/operational/`). The session is faked at the
engine's one seam (`session=`), so the hold, the masking, the cap, the concurrency bound and
the record all run for real.
"""

import os
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
DEVICES = [{"hostname": h, "ip": f"192.0.2.{n}", "device_type": "cisco_xe"}
           for h, n in (("r1", 11), ("r2", 12), ("r3", 13), ("s1", 21))]


def _text(*parts):
    with open(os.path.join(FIX, *parts), encoding="utf-8") as fh:
        return fh.read()


ANSWERS = {"show running-config": _text("configs", "fleet", "r2.cfg"),
           "show ip interface": _text("operational", "r1__show_ip_interface.txt")}


class Session:
    """A device session at the engine's seam: answers from the captures, every command
    recorded, the most sessions open at once measured."""

    def __init__(self, delay=0.0, fail=(), answers=None):
        self.sent, self.open_now, self.peak = [], 0, 0
        self.delay, self.fail, self.answers = delay, set(fail), answers or ANSWERS
        self.mu = threading.Lock()

    def __call__(self, dev, fn):
        if dev["hostname"] in self.fail:
            raise OSError(f"TCP connection to device failed ({dev['ip']}:22)")
        with self.mu:
            self.open_now += 1
            self.peak = max(self.peak, self.open_now)
        try:
            time.sleep(self.delay)
            return fn(self)
        finally:
            with self.mu:
                self.open_now -= 1

    # the engine reads through commands.run_device_command(conn, command)
    def answer(self, command):
        with self.mu:
            self.sent.append(command)
        return self.answers.get(command, f"% no capture for {command}")


@pytest.fixture
def lab(monkeypatch, tmp_path):
    monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(tmp_path / name))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path: [dict(d) for d in DEVICES])
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, c: conn.answer(c))
    settings = {}
    monkeypatch.setattr("modules.list_settings.value",
                        lambda ln, key, default=None: settings.get(key, default))
    return {"settings": settings, "tmp": tmp_path}


def _run(hosts, commands, session=None, **kw):
    from modules.nsot import reads
    session = session or Session()
    return reads.run("Lab", hosts, commands, "op@example.invalid", session=session, **kw), session


class TestRefusedFirst:
    @pytest.mark.parametrize("command", ["reload", "write erase", "configure terminal",
                                         "show running-config | redirect flash:x",
                                         "show clock\nreload"])
    def test_a_write_asks_no_device_and_is_recorded(self, lab, command):
        from modules.nsot import reads
        s = Session()
        with pytest.raises(reads.Refused) as e:
            reads.run("Lab", ["r1", "r2"], ["show version", command], "op@example.invalid",
                      session=s)
        assert "REFUSED" in str(e.value) and s.sent == []
        (r,) = reads.runs("Lab")["runs"]
        assert r["state"] == "refused" and r["refused"] == str(e.value) and r["results"] == {}

    def test_show_tech_is_refused_across_devices_and_allowed_on_one(self, lab):
        from modules.nsot import reads
        for spelling in ("show tech-support", "sh tech", "show tech-support | include Gi"):
            assert "asked of one device, on its page" in reads.refusal([spelling], 2), spelling
            assert reads.refusal([spelling], 1) == ""
        assert reads.warnings(["sh tech"])[0]["why"].startswith("runs for minutes")
        assert reads.warnings(["show ip route"]) == []

    def test_no_command_and_too_many(self, lab):
        from modules.nsot import reads
        assert reads.refusal([], 1).startswith("Refused: no command")
        assert "at most 10" in reads.refusal(["show clock"] * 11, 1)


class TestARun:
    def test_every_device_answers_masked_and_recorded(self, lab):
        r, s = _run(["r1", "r2"], ["show running-config", "show ip interface"])
        assert r["state"] == "done" and sorted(r["results"]) == ["r1", "r2"]
        a = r["results"]["r2"]["answers"][0]
        assert a["state"] == "answered" and not a["cut"]
        assert "password 0 admin" not in a["answer"] and "community public" not in a["answer"]
        assert "username admin privilege 15" in a["answer"]          # masked, not dropped
        from modules.nsot import reads
        again = reads.get("Lab", r["id"])
        assert again["results"]["r2"]["answers"][0]["sha256"] == a["sha256"]
        assert again["actor"] == "op@example.invalid" and reads.actor_words(again) == \
            "op@example.invalid"

    def test_the_summary_groups_alike_answers(self, lab):
        answers = dict(ANSWERS, **{"show clock": "*02:20:01.123 UTC Thu Oct 8 2026"})
        s = Session(answers=answers)
        r, _ = _run(["r1", "r2", "r3"], ["show clock", "show ip interface"], session=s)
        per = {c["command"]: c for c in r["summary"]["commands"]}
        assert per["show clock"]["distinct"] == 1 and per["show clock"]["answered"] == 3
        assert per["show clock"]["groups"] == [["r1", "r2", "r3"]]

    def test_an_answer_past_the_cap_is_cut_and_says_so(self, lab):
        lab["settings"]["reads_answer_cap_kib"] = 1
        r, _ = _run(["r2"], ["show running-config"])
        a = r["results"]["r2"]["answers"][0]
        assert a["cut"] and len(a["answer"].encode()) <= 1024 and a["bytes"] > 1024
        import hashlib

        from modules.redact import redact_text
        assert a["sha256"] == hashlib.sha256(
            redact_text(ANSWERS["show running-config"]).encode()).hexdigest()

    def test_the_concurrency_bound_holds(self, lab):
        lab["settings"]["reads_max_workers"] = 2
        s = Session(delay=0.2)
        _run(["r1", "r2", "r3", "s1"], ["show ip interface"], session=s)
        assert s.peak == 2, s.peak
        lab["settings"]["reads_max_workers"] = 4
        s = Session(delay=0.2)
        _run(["r1", "r2", "r3", "s1"], ["show ip interface"], session=s)
        assert s.peak == 4, s.peak                  # the control: the bound is the setting

    def test_a_failed_device_is_named_and_the_others_answer(self, lab):
        r, _ = _run(["r1", "s1"], ["show ip interface"], session=Session(fail={"s1"}))
        assert r["results"]["r1"]["state"] == "answered"
        assert r["results"]["s1"]["state"] == "failed"
        assert "TCP connection to device failed" in r["results"]["s1"]["why"]
        assert "answers" not in r["results"]["s1"]

    def test_an_unknown_device_is_named(self, lab):
        r, _ = _run(["r9"], ["show clock"])
        assert r["results"]["r9"] == {"state": "unknown", "why": "r9 is not a device of Lab"}

    def test_the_agent_reads_for_a_person(self, lab):
        from modules.nsot import reads
        r, _ = _run(["r1"], ["show ip interface"], by="agent", purpose="evidence")
        assert reads.actor_words(r) == "the agent, for op@example.invalid"


class TestTheHold:
    def test_a_device_held_by_another_operation_is_skipped_by_name(self, lab):
        from modules.nsot import device_ops
        with device_ops.hold("Lab", "r2", "deploy", "other@example.invalid"):
            r, s = _run(["r1", "r2"], ["show ip interface"])
        assert r["results"]["r1"]["state"] == "answered"
        assert r["results"]["r2"]["state"] == "skipped"
        assert "r2 is being deployed to by other@example.invalid" in r["results"]["r2"]["why"]
        assert s.sent == ["show ip interface"]                    # r1 only

    def test_a_deploy_is_refused_while_a_read_holds_the_device(self, lab):
        from modules.nsot import device_ops
        seen = {}

        class Slow(Session):
            def __call__(self, dev, fn):
                def deploy():                 # another thread, as a deploy's request is
                    try:
                        with device_ops.hold("Lab", dev["hostname"], "deploy",
                                             "other@example.invalid"):
                            seen["why"] = "the deploy took the device"
                    except device_ops.DeviceBusy as exc:
                        seen["why"] = str(exc)
                t = threading.Thread(target=deploy)
                t.start()
                t.join(10)
                return super().__call__(dev, fn)
        _run(["r1"], ["show ip interface"], session=Slow())
        assert "r1 is being read (show commands) by op@example.invalid" in seen["why"], seen


class TestRetention:
    def _old_run(self, lab):
        from modules.nsot import reads
        r, _ = _run(["r1"], ["show ip interface"])
        r["finished_at"] -= 31 * 86400
        reads._write("Lab", r)
        return r

    def test_old_answers_move_to_the_archive_and_who_when_what_stay(self, lab):
        from modules.nsot import reads
        r = self._old_run(lab)
        put = {}
        got = reads.expire("Lab", archive=lambda key, data: put.__setitem__(key, data))
        assert got == {"moved": 1, "kept": 0, "why": ""}
        assert list(put) == [f"reads/Lab/{r['id']}.json"] and b"GigabitEthernet1" in put[
            f"reads/Lab/{r['id']}.json"]
        after = reads.get("Lab", r["id"])
        a = after["results"]["r1"]["answers"][0]
        assert "answer" not in a and a["sha256"] and a["bytes"]
        assert after["retention"]["archived"]["key"] == f"reads/Lab/{r['id']}.json"
        assert after["actor"] == "op@example.invalid" and after["commands"]

    def test_with_no_archive_the_answers_stay_and_it_says_why(self, lab, monkeypatch):
        from modules.nsot import reads
        r = self._old_run(lab)
        monkeypatch.setattr("modules.integrations.s3_archive.S3ArchiveIntegration.is_configured",
                            lambda self: False)
        got = reads.expire("Lab")
        assert got["moved"] == 0 and got["kept"] == 1 and "no S3/MinIO archive" in got["why"]
        assert reads.get("Lab", r["id"])["results"]["r1"]["answers"][0]["answer"]

    def test_a_recent_run_is_not_due(self, lab):
        from modules.nsot import reads
        _run(["r1"], ["show ip interface"])
        assert reads.expire("Lab", archive=lambda k, d: None) == {"moved": 0, "kept": 0, "why": ""}
