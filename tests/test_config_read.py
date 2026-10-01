"""A configuration read can be trusted before anything records or compares it
(the operator, 2026-10-01).

Save All's preview showed r2 departing from its intent by 135 lines. r2 had
not drifted: its capture held the config, then `r2#show running-config`, then
the whole config again. Measured in the host's log: the prompt-based read
raised "Pattern not detected: 'r2\\#'" at its 60 s read timeout, and
`run_device_command` retried with `send_command_timing` on the SAME session,
whose channel still carried the first command's output. And the gate said
"device read: pass".

Everything here is built from r2's REAL config and the host's exact shape.
"""
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
R2 = ROOT / "tests" / "fixtures" / "configs" / "fleet" / "r2.cfg"
FLEET = sorted((ROOT / "tests" / "fixtures" / "configs" / "fleet").glob("*.cfg"))


def _r2():
    return R2.read_text(encoding="utf-8")


def _stitched(text=None):
    """r2's capture as the host recorded it: the config, the prompt and the
    echoed command, then the config again."""
    text = text or _r2()
    return text + "r2#show running-config\n" + text


class TestTheJudgement:
    def test_every_real_config_is_one_configuration(self):
        assert len(FLEET) >= 9
        from modules import config_read
        for p in FLEET:
            text = p.read_text(encoding="utf-8")
            host = next(l.split()[1] for l in text.splitlines() if l.startswith("hostname "))
            assert config_read.problems(text, host) == [], p.name
            assert config_read.problems(text, host, previous=text) == [], p.name

    def test_the_hosts_shape_is_refused_naming_each_sign(self):
        from modules import config_read
        got = config_read.problems(_stitched(), "r2", previous=_r2())
        text = " | ".join(got)
        assert "2 `end` lines" in text and "a second configuration follows" in text
        assert "device prompt line" in text and "'r2#show running-config'" in text
        assert "echoed command" in text
        assert "2 `hostname` lines" in text
        assert "against" in text and "in the committed golden" in text

    def test_each_sign_alone_is_enough(self):
        from modules import config_read
        r2 = _r2()
        body = r2[: r2.rindex("end")]
        cases = {
            "a prompt alone": body + "r2#\nend\n",
            "an echoed command": "r2#show running-config\n" + r2,
            "no end": body,
            "another device": r2.replace("hostname r2", "hostname r3"),
            "a second end": r2 + "end\n",
        }
        for why, text in cases.items():
            assert config_read.problems(text, "r2"), why

    def test_a_real_change_in_size_is_not_refused(self):
        """Measured on the host's 73 golden blobs: the largest real step was 1.05x."""
        from modules import config_read
        r2 = _r2()
        grown = r2.replace("\nend", "\n" + "".join(f"interface Loopback{i}\n" for i in range(30))
                           + "end")
        assert config_read.problems(grown, "r2", previous=r2) == []

    def test_at_save_time_absence_is_not_evidence(self):
        """`save_golden` refuses on evidence of a stitched or foreign text,
        never on a fragment's missing `end` or hostname (the reader judged
        presence)."""
        from modules import config_read
        assert config_read.problems("interface Gi2\n load-interval 30\n", "r2",
                                    strict=False) == []
        assert config_read.problems(_stitched(), "r2", strict=False)


class _Session:
    """A Netmiko session as far as a config read uses it."""

    def __init__(self, first, timing=None):
        self.first, self.timing, self.sent = first, timing, []

    def send_command(self, command, **kw):
        self.sent.append(("send_command", command, kw.get("read_timeout")))
        if isinstance(self.first, Exception):
            raise self.first
        return self.first

    def send_command_timing(self, command, **kw):
        self.sent.append(("send_command_timing", command, kw.get("read_timeout")))
        return self.timing


class TestTheReadIsNeverRetriedOnItsSession:
    def test_a_timed_out_config_read_is_not_sent_again(self):
        """The host's case: the prompt was not seen in time. The retry is what
        stitched the capture, so a config read raises instead."""
        from modules.commands import run_device_command
        s = _Session(TimeoutError("Pattern not detected: 'r2\\#' in output."),
                     timing=_stitched())
        with pytest.raises(TimeoutError):
            run_device_command(s, "show running-config")
        assert [x[0] for x in s.sent] == ["send_command"], s.sent

    def test_it_waits_with_the_config_bound_not_60_s(self):
        from modules import config_read
        from modules.commands import run_device_command
        s = _Session(_r2())
        assert run_device_command(s, "show running-config") == _r2().lstrip("\x00")
        assert s.sent[0][2] == max(60, config_read.read_timeout()) >= 120

    def test_a_stitched_answer_raises_whoever_asked(self):
        from modules import config_read
        from modules.commands import run_device_command
        with pytest.raises(config_read.UnreliableRead) as exc:
            run_device_command(_Session(_stitched()), "show running-config")
        assert config_read.UNRELIABLE in str(exc.value)

    def test_other_commands_keep_their_fallback(self):
        """The control: only a configuration read changed."""
        from modules.commands import run_device_command
        s = _Session(TimeoutError("slow"), timing="Cisco IOS XE Software")
        assert run_device_command(s, "show version") == "Cisco IOS XE Software"
        assert [x[0] for x in s.sent] == ["send_command", "send_command_timing"]


class TestTheCaptureRefusesIt:
    """Through the real capture preview and apply, the real reader, a session
    answering r2's stitched text."""

    @pytest.fixture
    def cap(self, monkeypatch, tmp_path):
        import routes.golden as G
        from tests.test_capture import build_capture_lab
        from tests.test_capture_reads_concurrently import _REAL_READ_RUNNING
        lab = build_capture_lab(monkeypatch, tmp_path)
        monkeypatch.setattr(G, "_read_running", _REAL_READ_RUNNING)
        lab["answer"] = _stitched()
        monkeypatch.setattr("modules.connection.with_temp_connection",
                            lambda dev, func: func(_Session(lab["answer"])))
        return lab

    def test_the_preview_says_it_could_not_be_read_and_offers_nothing(self, cap):
        from tests.test_capture import run_capture_preview
        d = run_capture_preview(cap["client"], {"devices": ["r2"]}).get_json()
        assert "the device's output could not be read reliably" in str(d)
        # The gate the operator saw read "pass" over this text.
        gates = {g["name"]: g["state"] for g in d["preview"]["targets"][0]["gates"]}
        assert gates["device read"] == "fail", gates
        (t,) = d["preview"]["what"]["targets"]
        assert not (t.get("select_data") or {}).get("hash"), t

    def test_a_good_read_is_still_offered(self, cap):
        """The control: r2's real config, once."""
        from tests.test_capture import run_capture_preview
        cap["answer"] = _r2()
        d = run_capture_preview(cap["client"], {"devices": ["r2"]}).get_json()
        (t,) = d["preview"]["what"]["targets"]
        assert t["select_data"]["hash"]


class TestNothingRecordsIt:
    def test_save_golden_refuses_and_writes_nothing(self, monkeypatch, tmp_path):
        """The backstop: a path that skipped its read's check is refused where
        every golden is recorded."""
        import subprocess
        from tests.test_capture import build_capture_lab
        from modules.nsot.repo import GoldenItem, save_golden
        lab = build_capture_lab(monkeypatch, tmp_path)
        head = subprocess.run(["git", "-C", lab["repo"], "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout
        before = open(os.path.join(lab["repo"], "golden", "r2.cfg"), encoding="utf-8").read()
        got = save_golden("Lab", [GoldenItem("r2", _stitched(), "203.0.113.12",
                                             platform="cisco_iosxe")],
                          source="capture", actor="t", baseline=False)
        assert got["ok"] is False
        assert "could not be read reliably" in got["error"] and "Nothing was recorded" in got["error"]
        assert subprocess.run(["git", "-C", lab["repo"], "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout == head
        assert open(os.path.join(lab["repo"], "golden", "r2.cfg"),
                    encoding="utf-8").read() == before

    def test_drift_names_it_and_drops_the_pooled_session(self, monkeypatch):
        from modules import drift_check
        dev = {"hostname": "r2", "ip": "203.0.113.12", "username": "u", "password": "p",
               "device_type": "cisco_xe"}
        monkeypatch.setattr("modules.device.get_current_device_list", lambda: ("lab", "x.csv"))
        monkeypatch.setattr("modules.device.load_saved_devices", lambda p: [dict(dev)])
        monkeypatch.setattr("modules.ai_assistant._golden_record",
                            lambda ip: {"text": _r2(), "path": "", "commit": "",
                                        "source": "", "refused": ""})
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda d, p, l: _Session(_stitched()))
        closed = []
        monkeypatch.setattr("modules.connection.close_persistent_connection",
                            lambda ip, p, l: closed.append(ip))
        monkeypatch.setattr("modules.approval_queue.add_approval", lambda **kw: {"ok": True})
        r = drift_check.run_drift_check("test")
        assert [e["hostname"] for e in r["errors"]] == ["r2"]
        assert "could not be read reliably" in r["errors"][0]["reason"]
        assert not r.get("drifted") and closed == ["203.0.113.12"]
