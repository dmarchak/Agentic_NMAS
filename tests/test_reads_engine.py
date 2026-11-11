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

    def __init__(self, delay=0.0, fail=(), answers=None, gather=0):
        """*gather*: each session stays open until that many are open at once, or *delay*
        passes, so the most open at once is reached by waiting for it, never by how fast a
        loaded machine starts threads (CI #735 saw 3 of 4 with a 0.2 s sleep)."""
        self.sent, self.open_now, self.peak = [], 0, 0
        self.delay, self.fail, self.answers = delay, set(fail), answers or ANSWERS
        self.gather = gather
        self.mu = threading.Condition()

    def __call__(self, dev, fn):
        if dev["hostname"] in self.fail:
            raise OSError(f"TCP connection to device failed ({dev['ip']}:22)")
        with self.mu:
            self.open_now += 1
            self.peak = max(self.peak, self.open_now)
            self.mu.notify_all()
            if self.gather and self.peak < self.gather:
                # Once that many were open together, no later session waits for it again.
                self.mu.wait_for(lambda: self.peak >= self.gather, timeout=self.delay)
        try:
            if not self.gather:
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

    def test_a_long_failure_reason_says_it_was_cut_and_how_much(self, lab):
        """A failed read's reason was cut at 400 characters and said nothing. It says in
        place that it was cut and how much, as a capped answer does (C2990), for a device's
        failure and for a command's; a short reason is kept whole."""
        long = "the session ended: " + "x" * 981                    # 1000 characters

        class Conn:
            def answer(self, command):
                raise RuntimeError(long if command == "show clock" else "no answer")

        def session(dev, fn):
            if dev["hostname"] == "r1":
                raise OSError(long)
            return fn(Conn())
        r, _ = _run(["r1", "r2"], ["show clock", "show version"], session=session)
        device, (cut, short) = r["results"]["r1"], r["results"]["r2"]["answers"]
        assert device["state"] == "failed" and device["why"] == (
            ("OSError: " + long)[:400] + " [cut: the first 400 of this reason's 1009 "
            "characters are kept and the last 609 were cut]")
        assert cut["state"] == "failed" and cut["why"] == (
            ("RuntimeError: " + long)[:400] + " [cut: the first 400 of this reason's 1014 "
            "characters are kept and the last 614 were cut]")
        assert short["why"] == "RuntimeError: no answer"

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
        # Each session waits for a third to open (0.5 s at most): under a bound of 2 none does.
        lab["settings"]["reads_max_workers"] = 2
        s = Session(delay=0.5, gather=3)
        _run(["r1", "r2", "r3", "s1"], ["show ip interface"], session=s)
        assert s.peak == 2, s.peak
        # Each waits for all four (10 s at most; they open within milliseconds when allowed).
        lab["settings"]["reads_max_workers"] = 4
        s = Session(delay=10, gather=4)
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


# ── A read that is part of a run (the operator, 2026-11-11) ─────────────────────────────────

RUN_OF = ("telemetry re-subscribe", "20261111T163825000000Z-" + "a" * 32, "verify", "privileged")


class TestAReadThatIsPartOfARun:
    def test_within_a_run_the_read_names_it_and_is_never_a_persons(self, lab):
        from modules.nsot import reads
        with reads.within(*RUN_OF) as mine:
            r, _ = _run(["r2"], ["show ip interface"], inline=True)
            mine["step"] = "before"
            again, _ = _run(["r2"], ["show ip interface"], inline=True)
        after, _ = _run(["r2"], ["show ip interface"])
        kind, run_id, _step, record = RUN_OF
        assert reads.get("Lab", r["id"])["part_of"] == {"kind": kind, "id": run_id,
                                                         "step": "verify", "record": record}
        assert again["part_of"]["step"] == "before", "the step moves with the operation"
        assert r["by"] == reads.OPERATION and r["actor"] == "op@example.invalid"
        assert reads.actor_words(r) == f"{kind}'s own reads, for op@example.invalid"
        assert after["by"] == "person" and "part_of" not in after, "the block is over"

    def test_a_heals_read_keeps_its_own_kind_and_a_fleet_read_is_the_runs_too(self, lab):
        """Only a person's kind is replaced: self-healing's reads stay ``heal``. A run of
        several devices, read in the engine's own threads, is the run's as well."""
        from modules.nsot import reads
        with reads.within("port bounce", "hi-1", "fresh", "heal steps"):
            r, _ = _run(["r1", "r2"], ["show ip interface"], by="heal")
        assert r["by"] == "heal" and r["part_of"]["id"] == "hi-1"
        assert sorted(r["results"]) == ["r1", "r2"] and r["summary"]["words"] == "2 answered"
        assert reads.actor_words(r) == "self-healing's action reads, for op@example.invalid"

    def test_a_block_that_raises_leaves_the_thread_outside_it(self, lab):
        from modules.nsot import reads
        with pytest.raises(RuntimeError):
            with reads.within(*RUN_OF):
                raise RuntimeError("the operation failed")
        r, _ = _run(["r2"], ["show ip interface"])
        assert r["by"] == "person" and "part_of" not in r

    def test_only_a_persons_runs_are_listed_and_never_crowded_out(self, lab):
        """History, Show commands' recent runs and Ask the device ask for the runs that are no
        operation's (`part=False`); the filter comes before the newest-N cut."""
        from modules.nsot import reads
        mine, _ = _run(["r2"], ["show ip interface"])
        with reads.within(*RUN_OF):
            theirs = [_run(["r2"], ["show ip interface"], inline=True)[0]["id"]
                      for _ in range(5)]
        assert [r["id"] for r in reads.runs("Lab", part=False, limit=3)["runs"]] == [mine["id"]]
        assert [r["id"] for r in reads.runs("Lab", part=True)["runs"]] == theirs[::-1]
        assert len(reads.runs("Lab")["runs"]) == 6, "retention and lookups still see every run"

    def test_its_answer_is_masked_capped_and_kept_as_any_other(self, lab):
        from modules.nsot import reads
        person, _ = _run(["r2"], ["show running-config"])
        with reads.within(*RUN_OF):
            theirs, _ = _run(["r2"], ["show running-config"], inline=True)
        a, b = (reads.get("Lab", x["id"])["results"]["r2"]["answers"][0] for x in (person, theirs))
        assert "password 0 admin" not in b["answer"] and "community public" not in b["answer"]
        assert a["answer"] == b["answer"] and a["sha256"] == b["sha256"] and not b["cut"]
        assert theirs["retention"] == person["retention"]

    @pytest.mark.parametrize("command", ["reload", "configure terminal", "terminal length 0",
                                         "send log 6 a test line"])
    def test_it_is_refused_off_the_allowlist_and_has_no_persons_extras(self, lab, command):
        """An operation's read is judged by the allowlist whole, and by a smaller one than a
        person's: Tier 1's extras (a session setting, a log line) are a person's to send."""
        from modules.nsot import reads
        s = Session()
        with reads.within(*RUN_OF), pytest.raises(reads.Refused) as e:
            reads.run("Lab", ["r2"], [command], "op@example.invalid", session=s, inline=True)
        assert "REFUSED" in str(e.value) and s.sent == []
        (r,) = reads.runs("Lab")["runs"]
        assert r["state"] == "refused" and r["by"] == reads.OPERATION and r["part_of"]["id"]
        assert reads.EXTRAS[reads.OPERATION] == () and reads.EXTRAS["heal"] == ()

    def test_old_answers_of_a_runs_reads_expire_as_any_other(self, lab):
        from modules.nsot import reads
        with reads.within(*RUN_OF):
            r, _ = _run(["r1"], ["show ip interface"], inline=True)
        r["finished_at"] -= 31 * 86400
        reads._write("Lab", r)
        put = {}
        got = reads.expire("Lab", archive=lambda key, data: put.__setitem__(key, data))
        assert got == {"moved": 1, "kept": 0, "why": ""} and list(put) == [
            f"reads/Lab/{r['id']}.json"]
        assert reads.get("Lab", r["id"])["part_of"]["id"] == RUN_OF[1]


class TestARunsRecordOfItsReads:
    def _entry(self, n, result="fail", words="Connecting"):
        from modules.nsot import reads
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(1_794_250_000 + 13 * n))
        return reads.read_entry("show telemetry ietf subscription 102 receiver", result, words,
                                at=at, read_id=f"id-{n}")

    def test_an_entry_is_short_and_says_when_what_and_how_it_went(self):
        from modules.nsot import reads
        e = self._entry(0)
        assert e == {"at": "2026-11-09T18:46:40Z", "result": "fail", "words": "Connecting",
                     "command": "show telemetry ietf subscription 102 receiver",
                     "read_id": "id-0"}
        long = reads.read_entry("show clock", "pass", "x" * 500, at=e["at"])
        assert len(long["words"]) == reads.ENTRY_WORDS_MAX and long["words"].endswith("…")
        assert long["read_id"] == ""
        with pytest.raises(ValueError):
            reads.read_entry("show clock", "ok", "", at=e["at"])

    def test_a_steps_reads_are_bounded_keeping_the_first_and_the_newest(self):
        from modules.nsot import reads
        step = {"step": "verify"}
        for n in range(reads.STEP_READS_MAX + 10):
            reads.keep_read(step, self._entry(n))
        ids = [e["read_id"] for e in step["reads"]]
        assert len(ids) == reads.STEP_READS_MAX == 120 and step["reads_dropped"] == 10
        assert ids[0] == "id-0" and ids[1] == "id-11" and ids[-1] == "id-129"

    def test_the_reads_are_said_in_one_line(self):
        from modules.nsot import reads
        step = {"step": "verify"}
        for n in range(25):
            reads.keep_read(step, self._entry(n))
        reads.keep_read(step, self._entry(25, "pass", "Connected on connection 985"))
        assert reads.reads_words(step) == (
            "26 reads of `show telemetry ietf subscription 102 receiver`, about 13 s apart: "
            "1 pass, 25 fail; the last: Connected on connection 985")
        assert reads.reads_words({"step": "hold"}) == ""
        # Two reads in one second are counted, and no interval is made up for them.
        same = {"reads": [self._entry(0, "pass", "read"), self._entry(0, "pass", "read")]}
        assert reads.reads_words(same) == (
            "2 reads of `show telemetry ietf subscription 102 receiver`: 2 pass; the last: read")
        # A diagnosis's step lists its reads' references, which are not entries.
        assert reads.reads_words({"reads": ["read:x:r2:show clock"]}) == ""
