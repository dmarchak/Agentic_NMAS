"""The one-decision out-of-band onboarding's run, step by step (modules/nsot/oob_onboard.py,
`_phases`): what each step leaves on the record and the exact words of each stop, on the same
loopback world as tests/test_oob_onboard.py (its `world` fixture and console answers).

Each test holds one behaviour mutation run #25 showed no test held:

- the wake: a console found signed in is named with the states blank needs;
- the prelude: a session that does not end at the privileged prompt names that phase;
- the blank check: its verdict, size and reason on the record;
- the read-back: its verdict on the record, every difference joined in the stop;
- the MAC: recorded for the list, the device and the actor, a failure to record it kept;
- the copy: its bound is the run's own, its verdict read with the device's profile, and its
  stop names the rule it applied and, only when the session did not end done, how it ended.
"""

from modules.nsot import oob_steps
from tests import oob_fake_steps as S
from tests.test_console_ztp import ACTOR, LIST
from tests.test_oob_onboard import ADDRESS, FAST, MAC_TEXT, MASK, answers, world  # noqa: F401

MAC = "0c:00:08:75:80:01"
COPY = "copy tftp://192.0.2.10/edge1.cfg running-config"


class TestTheWake:
    def test_a_signed_in_console_is_named_with_the_states_blank_needs(self, world):
        rec = world.run([b"\r\nSwitch#"])
        assert rec["stop"]["compared"] == ("the console answered at priv_exec (blank needs the "
                                           "setup dialog, Press RETURN or the user prompt)")


class TestThePrelude:
    def test_a_prelude_that_does_not_reach_the_privileged_prompt_names_the_phase(self, world):
        rec = world.run([b"\r\nSwitch>", b"enable\r\nPassword: "])
        assert rec["outcome"] == "unexpected" and world.created == []
        assert rec["stop"]["compared"].startswith(
            "expected priv_exec after the prelude and the blank check; the session ended ")


class TestTheBlankCheck:
    def test_the_blank_verdict_size_and_reason_are_recorded(self, world):
        rec = world.run(answers())
        assert rec.get("blank") == {"blank": True, "size": 0,
                                    "reason": "startup-config is 0 bytes in 'dir nvram:''s output"}


class TestTheReadBack:
    def test_a_read_back_that_agrees_is_recorded_with_the_mac_s_source(self, world):
        rec = world.run(answers())
        assert rec.get("read_back") == {"ok": True, "differs": [],
                                        "mac_why": f"the MAC in use, from {MAC_TEXT}"}

    def test_every_difference_is_recorded_and_joined_in_the_stop(self, world):
        rec = world.run(answers(reads={"show running-config interface Vlan1":
                                       "interface Vlan1\r\n shutdown\r\nend\r\n"}))
        whys = [f"typed 'ip address {ADDRESS} {MASK}'; 'show running-config interface Vlan1' "
                "does not show it",
                "typed 'no shutdown'; 'show running-config interface Vlan1' does not show it"]
        assert rec["outcome"] == "read_back"
        assert (rec.get("read_back") or {}).get("differs") == whys
        assert rec["stop"]["compared"] == "; ".join(whys)


class TestTheMac:
    def test_the_mac_is_recorded_for_the_list_the_device_and_the_actor(self, world,
                                                                       monkeypatch):
        calls = []
        monkeypatch.setattr(world, "record_mac", lambda *a: (calls.append(a), "")[1])
        world.run(answers())
        assert calls == [(LIST, "edge1", MAC, ACTOR)]

    def test_a_mac_that_could_not_be_recorded_is_kept_on_the_record(self, world, monkeypatch):
        monkeypatch.setattr(world, "record_mac",
                            lambda *a: "the manifest commit failed: index locked")
        rec = world.run(answers())
        assert rec["mac"] == MAC
        assert rec.get("mac_record_error") == "the manifest commit failed: index locked"


class TestTheCopy:
    def test_the_copy_is_bounded_by_the_run_s_own_copy_timeout(self, world, monkeypatch):
        bounds = []

        def then(console, steps, final, timeout_s):
            bounds.append(timeout_s)
            return S.then_with_timeout(console, steps, final, timeout_s)
        monkeypatch.setattr(oob_steps, "then_with_timeout", then)
        assert FAST.copy_timeout_s != oob_steps.copy_timeout_s(), "the two bounds differ"
        world.run(answers())
        assert bounds == [FAST.copy_timeout_s]

    def test_the_key_s_generation_messages_are_not_a_refusal_of_the_copy(self, world):
        copy = ("Accessing tftp://192.0.2.10/edge1.cfg...\r\n"
                "Loading edge1.cfg from 192.0.2.10 (via Vlan1): !\r\n[OK - 2048 bytes]\r\n"
                "% The key modulus size is 2048 bits\r\n"
                "% Generating 2048 bit RSA keys, keys will be non-exportable...\r\n"
                "2048 bytes copied in 1.2 secs\r\n")
        rec = world.run(answers(copy=copy))
        assert rec["copy"] == {"ok": True, "bytes": 2048, "refused": "",
                               "why": "the copy printed '[OK - 2048 bytes]'"}
        assert rec["outcome"] == "done", rec["reason"]

    def test_a_copy_refused_in_a_done_session_names_its_rule_and_nothing_more(self, world):
        rec = world.run(answers(copy="Accessing tftp://192.0.2.10/edge1.cfg...\r\n"
                                     "[OK - 0 bytes]\r\n"))
        assert rec["stop"]["compared"] == (
            f"{COPY!r}: the copy printed '[OK - 0 bytes]': it must move more than 0 bytes "
            "(needs one [OK - N bytes], N over 0, and no refusal)")

    def test_a_copy_whose_session_did_not_end_done_says_how_it_ended(self, world):
        got = answers()
        got[-1] = f"{COPY}\r\nAccessing tftp://192.0.2.10/edge1.cfg...\r\nPassword: ".encode()
        rec = world.run(got)
        assert rec["outcome"] == "copy_failed"
        assert "(needs one [OK - N bytes], N over 0, and no refusal); the session ended " \
            in rec["stop"]["compared"]
