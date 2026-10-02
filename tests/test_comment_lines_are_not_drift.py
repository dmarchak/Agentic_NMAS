"""A comment line is not drift (the operator, 2026-10-02).

r3's drift after its crash-reboot (9 lines, an approval queued at 08:52) was ONE line:
``! Call-home is enabled by Smart-Licensing.``, a comment IOS-XE writes itself by licensing
state. A comment changes nothing on a device, so drift and the capture preview set comment
lines aside (`normalize.strip_comments`) and say so in one line (`comment_note`), as they do
a regenerated self-signed certificate; the golden is recorded verbatim. A list of the
comments IOS-XE writes was the other choice: it would lag the next one, and each lag is a
false drift report, the kind that silenced the drift checker for 24 days.

On r2's REAL configuration (which carries the call-home comment, and comments inside its
call-home stanza), each case a minimal edit. A ``!`` line inside a banner is the banner's
text and still counts. Once the rule is in force, the next drift run withdraws the pending
item a comment-only difference queued.
"""

import subprocess

import pytest

from modules.nsot.normalize import COMMENTS_DIFFER, comment_note, strip_comments
from tests.test_capture import _apply, _hash, _preview, build_capture_lab
from tests.test_intent_match import R2

CALL_HOME = "! Call-home is enabled by Smart-Licensing."


def _r2():
    text = open(R2, encoding="utf-8").read()
    assert CALL_HOME in text
    return text


def _without_call_home(text):
    return text.replace(CALL_HOME + "\n", "")


class TestTheRule:
    def test_comments_are_set_aside_and_separators_kept(self):
        lines = strip_comments(_r2())
        assert CALL_HOME not in lines
        assert not [l for l in lines if l.strip().startswith("!") and l.strip() != "!"]
        assert "!" in lines and "hostname r2" in lines

    def test_a_missing_comment_is_one_line_naming_it(self):
        note = comment_note(_r2(), _without_call_home(_r2()))
        assert note.startswith(f"~ {COMMENTS_DIFFER}: no longer {CALL_HOME!r}")
        assert "recorded verbatim, not drift" in note
        assert comment_note(_r2(), _r2()) == ""

    def test_a_bang_line_inside_a_banner_is_banner_text_not_a_comment(self):
        cfg = "hostname s\nbanner motd ^C\n! Authorised use only\n^C\n!\nend\n"
        assert "! Authorised use only" in strip_comments(cfg)
        assert comment_note(cfg, cfg.replace("Authorised", "Permitted")) == ""


@pytest.fixture
def drift(monkeypatch):
    from modules import drift_check

    devices = [{"hostname": "r2", "ip": "203.0.113.12", "username": "u", "password": "p",
                "device_type": "cisco_xe"}]
    golden = {"203.0.113.12": _r2()}
    running = {"203.0.113.12": _without_call_home(_r2())}
    queued, superseded = [], []
    monkeypatch.setattr("modules.device.get_current_device_list", lambda: ("lab", "lab.csv"))
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path: list(devices))
    monkeypatch.setattr("modules.ai_assistant._golden_record",
                        lambda ip: {"text": golden.get(ip), "path": "", "commit": "",
                                    "source": "", "refused": ""})
    monkeypatch.setattr("modules.connection.get_persistent_connection",
                        lambda dev, pool, lock: dev["ip"])
    monkeypatch.setattr("modules.commands.run_device_command", lambda conn, cmd: running[conn])
    monkeypatch.setattr("modules.approval_queue.add_approval",
                        lambda **kw: queued.append(kw) or {"ok": True})
    monkeypatch.setattr("modules.approval_queue.supersede_drift",
                        lambda hosts, reason, by="": superseded.append((list(hosts), reason)))
    return {"module": drift_check, "running": running, "queued": queued,
            "superseded": superseded}


class TestDrift:
    def test_a_missing_comment_alone_is_clean_said_and_queues_nothing(self, drift):
        r = drift["module"].run_drift_check("test")
        assert r["drifted"] == 0 and r["clean"] == 1, r["summary"]
        assert drift["queued"] == []
        assert f"{COMMENTS_DIFFER[0].upper()}{COMMENTS_DIFFER[1:]}, not drift: r2." in r["summary"]

    def test_the_pending_item_it_queued_is_withdrawn_by_the_next_run(self, drift):
        drift["module"].run_drift_check("test")
        assert drift["superseded"] and drift["superseded"][0][0] == ["r2"]

    def test_real_drift_beside_it_is_drawn_with_the_comment_as_one_line(self, drift):
        drift["running"]["203.0.113.12"] = _without_call_home(_r2()).replace(
            "hostname r2\n", "hostname r2\nip domain lookup source-interface Loopback0\n")
        r = drift["module"].run_drift_check("test")
        assert r["drifted"] == 1
        diff = drift["queued"][0]["diff"].splitlines()
        assert "+ip domain lookup source-interface Loopback0" in diff
        assert any(l.startswith(f"~ {COMMENTS_DIFFER}") for l in diff)
        assert f"-{CALL_HOME}" not in diff


@pytest.fixture
def cap(tmp_path, monkeypatch):
    return build_capture_lab(monkeypatch, tmp_path)


class TestTheCapture:
    def test_the_preview_draws_one_line_and_the_golden_is_verbatim(self, cap):
        assert CALL_HOME in cap["captured"]
        cap["running"]["r2"] = _without_call_home(cap["captured"])
        d = _preview(cap)
        lines = d["preview"]["targets"][0]["program"]["lines"]
        assert any(l.startswith(f"~ {COMMENTS_DIFFER}") for l in lines), lines
        assert f"-{CALL_HOME}" not in lines
        _apply(cap, {"r2": _hash(d)})
        golden = subprocess.run(["git", "-C", cap["repo"], "show", "HEAD:golden/r2.cfg"],
                                capture_output=True, text=True).stdout
        assert CALL_HOME not in golden, "the golden records what the device runs, verbatim"
