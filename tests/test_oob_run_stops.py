"""The out-of-band onboarding's stops (modules/nsot/oob_onboard.py: `_finish_stop`, `_then`,
`_console_phases`), on the fake console world of tests/test_oob_onboard.py.

Each stop leaves a record a person reads on the run's card and in History: its rule, the
comparison with both operands, what was sent (masked), what the undo undid and left, and
whether an undo ran at all; the reason in words is built from the same. Every stop once
Create has begun undoes it, with the list, the device and the person who confirmed, and the
device's hold says so while it runs (another operation refused meanwhile reads it). A phase
that ends anywhere but its prompt, with no refusal from the device, is the `unexpected` stop
naming what it expected and how the session ended. A secret the installation holds, printed
back by the device, is masked in the stop's words and in the record at rest.
"""

import json

import pytest

from modules.nsot import oob_onboard as O
from tests.test_console_ztp import ACTOR, LIST, _real
from tests.test_oob_onboard import (ADDRESS, FAST, FIELDS, MASK, _echo, answers, saved_nvram,
                                    world)  # noqa: F401 - the world fixture, shared

#: A secret the installation holds (``{value: label}``, `redact.redact_text`'s table); the
#: device prints it back in a refusal.
SECRET = "Pl4ntedS3cretValue"
VALUES = {SECRET: "enable secret"}
BLANK_SENT = ["enable", "terminal length 0", "dir nvram:"]


def run_with(world, got, *, values=None, undo=None):
    """One run on *got* (the console's answers), reviewed and confirmed with *values* as the
    installation's secrets, with *undo* as Create's undo when given: its record. A run that
    raises instead of recording its stop fails here, naming what it raised."""
    values = {} if values is None else values
    p = O.preview(LIST, dict(FIELDS), values=values, **world.nbk())
    assert p["ok"], p["refusals"]
    world.consoles.append((b"", list(got)))
    try:
        return O.run(LIST, dict(FIELDS), confirmed_hash=p["hash"], actor=ACTOR,
                     actor_verified="access", reason="a new access switch", timings=FAST,
                     wall=world.wall, sleep=world.sleep, values=values, probe=world.probe,
                     create=world.create, undo=undo or world.undo,
                     record_mac=world.record_mac, **world.nbk())
    except O.Refused:
        raise
    except Exception as exc:                          # noqa: BLE001 - the test says it
        pytest.fail(f"the run raised {type(exc).__name__}: {exc} instead of recording its "
                    "stop")


class TestTheStopRecord:
    def test_a_stop_before_create_records_rule_comparison_sent_and_no_undo(self, world):
        rec = run_with(world, answers(nvram=saved_nvram(), upto=4))
        assert rec["outcome"] == "not_blank" and world.undone == []
        assert rec["stop"] == {
            "rule": "not_blank",
            "compared": ("nvram holds a startup configuration of 1234 bytes (blank needs 0 or "
                         "none): startup-config is 1234 bytes in 'dir nvram:''s output: the "
                         "device holds a saved configuration"),
            "sent": BLANK_SENT, "undone": [], "remaining": [], "undo_ran": False}

    def test_a_stop_before_create_says_what_was_sent_and_that_nothing_was_created(self,
                                                                                  world):
        rec = run_with(world, answers(nvram=saved_nvram(), upto=4))
        assert rec["reason"] == (
            "nvram holds a startup configuration of 1234 bytes (blank needs 0 or none): "
            "startup-config is 1234 bytes in 'dir nvram:''s output: the device holds a saved "
            "configuration. Sent: enable; terminal length 0; dir nvram:. Nothing was created.")

    def test_a_stop_keeps_the_console_s_sent_bytes_and_transcript_on_the_record(self, world):
        rec = run_with(world, answers(nvram=saved_nvram(), upto=4))
        want = "\r".join(["", *BLANK_SENT, ""])
        assert (rec.get("sent"), rec.get("bytes_written")) == (want, len(want))
        assert "startup-config" in (rec.get("transcript") or "")
        assert rec.get("attach_state") == "user_exec"

    def test_a_stop_after_create_records_what_the_undo_undid_and_left(self, world):
        def undo(list_name, hostname, actor):
            world.undone.append(hostname)
            return {"ok": False, "undone": ["intent: removed host_vars/edge1.yml"],
                    "remaining": ["identity: the manifest entry is kept"]}
        line = f"ip address {ADDRESS} {MASK}"
        rec = run_with(world, answers(refuse_at=line), undo=undo)
        assert rec["outcome"] == "refused_line" and world.undone == ["edge1"]
        sent = rec["stop"].pop("sent")
        assert sent[:3] == BLANK_SENT and sent[-1] == " " + line
        assert rec["stop"] == {
            "rule": "refused_line",
            "compared": (f"'{line}' was refused: \"% Invalid input detected at '^' marker.\". "
                         "Stopped there"),
            "undone": ["intent: removed host_vars/edge1.yml"],
            "remaining": ["identity: the manifest entry is kept"], "undo_ran": True}
        assert ("Undone: intent: removed host_vars/edge1.yml. Not undone: identity: the "
                "manifest entry is kept. Nothing was saved on the device") in rec["reason"]


class TestTheUndo:
    def test_the_undo_is_given_the_list_the_device_and_the_person(self, world):
        calls = []

        def undo(list_name, hostname, actor):
            calls.append((list_name, hostname, actor))
            return {"ok": True, "undone": [], "remaining": []}
        rec = run_with(world, answers(recheck=saved_nvram(99), upto=5), undo=undo)
        assert rec["outcome"] == "not_blank"
        assert calls == [(LIST, "edge1", ACTOR)]
        assert rec["stop"]["undo_ran"] is True and "Nothing needed undoing." in rec["reason"]

    def test_the_device_s_hold_says_undo_while_the_undo_runs(self, world):
        from modules.nsot import device_ops
        seen = []

        def undo(list_name, hostname, actor):
            seen.append(device_ops.busy_text(list_name, hostname))
            return {"ok": True, "undone": [], "remaining": []}
        run_with(world, answers(recheck=saved_nvram(99), upto=5), undo=undo)
        assert len(seen) == 1 and "last progress: onboard: undo, " in seen[0]


class TestAPhaseThatDidNotEnd:
    def test_a_blank_check_ending_at_another_prompt_is_the_unexpected_stop(self, world):
        _wake, enable, _blank = _real()
        got = [b"\r\nSwitch>", enable, _echo("terminal length 0", "Switch#"),
               b"dir nvram:\r\nPassword: "]
        rec = run_with(world, got)
        assert rec["outcome"] == "unexpected" and world.created == [] and world.undone == []
        assert rec["stop"]["compared"] == (
            "expected priv_exec after the prelude and the blank check; the session ended "
            "aborted: expected one of priv_exec (the plan's end), found login_password: "
            "'Password:'")


class TestSecretsInTheStop:
    def test_a_secret_the_device_prints_in_a_refusal_is_masked_in_the_record(self, world):
        line = f"ip address {ADDRESS} {MASK}"
        got = answers()
        at = next(i for i, a in enumerate(got) if a.startswith(f"{line}\r\n".encode())
                  or a.startswith(f" {line}\r\n".encode()))
        got[at] = (f" {line}\r\n% Bad secret {SECRET} refused\r\n\r\nedge1(config-if)#"
                   .encode())
        rec = run_with(world, got, values=VALUES)
        assert rec["outcome"] == "refused_line"
        assert "% Bad secret <redacted:enable secret> refused" in rec["reason"]
        assert SECRET not in json.dumps(rec)
