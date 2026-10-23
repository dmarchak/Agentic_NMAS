"""The one-decision out-of-band onboarding's run, its steps (modules/nsot/oob_onboard.py,
`_phases`): what each stop compared and its exact words, what the record holds, what Create is
handed, and that an informational line the profile ignores is never read as a refusal.

Mutation run #25 (2026-10-23, at c4716675), part A: each test here fails on a survivor of
`_phases`, applied by hand. The world, its console answers and its stand-ins are
tests/test_oob_onboard.py's.
"""

from tests.test_oob_onboard import (MAC_TEXT, _echo, _prompt, answers, saved_nvram,
                                    world)  # noqa: F401 - the fixture, used by name

#: IOS's informational line while it generates a key: a `%` line the switch profile's
#: ``ignore`` names, never a refusal (console_profiles/cisco_ios_switch.json).
MODULUS = "% The key modulus size is 2048 bits"


def _at(got, prefix: bytes) -> int:
    return next(i for i, a in enumerate(got) if a.startswith(prefix))


class TestTheBlankCheck:
    def test_a_blank_check_with_no_startup_entry_says_blank_is_unknown(self, world):
        nvram = _echo("dir nvram:", "") + (b"\r\nDirectory of nvram:/\r\n\r\n  254  -rw-        "
                                           b"4096                    <no date>  private-config"
                                           b"\r\n\r\nSwitch#")
        rec = world.run(answers(nvram=nvram, upto=4))
        assert rec["outcome"] == "not_blank" and world.created == []
        assert rec["stop"]["compared"] == ("blank is unknown: no startup-config entry in "
                                           "'dir nvram:''s output, so blank is unknown")


class TestTheWake:
    def test_the_wake_s_stop_names_how_the_session_ended(self, world):
        rec = world.run([b"\r\n*** a banner and no prompt ***\r\n"])
        assert rec["outcome"] == "unexpected"
        assert rec["stop"]["compared"] == (
            "expected a prompt answering the wake; expected one of setup_dialog, press_return, "
            "user_exec, priv_exec, config (the plan's end) within 3 s, found output: "
            "'*** a banner and no prompt ***'")


class TestCreate:
    def test_create_is_handed_the_reviewed_derived_values(self, world, monkeypatch):
        handed = []
        real = world.create
        monkeypatch.setattr(world, "create", lambda l, f, d, fp, a: (handed.append(d),
                                                                      real(l, f, d, fp, a))[1])
        rec = world.run(answers())
        assert rec["outcome"] == "done", rec["reason"]
        assert handed == [world.review()["derived"]]

    def test_the_record_holds_what_create_answered(self, world):
        rec = world.run(answers())
        assert rec["created"] == {"ok": True, "completed": ["credentials", "commit", "render"],
                                  "commit": "c0ffee", "reason": ""}

    def test_create_refused_with_no_reason_says_so(self, world, monkeypatch):
        monkeypatch.setattr(world, "create", lambda *a: {"ok": False, "completed": [],
                                                         "commit": "", "reason": ""})
        rec = world.run(answers(upto=5))
        assert rec["outcome"] == "create_failed"
        assert rec["stop"]["compared"] == "Create did not complete: no reason (completed: none)"

    def test_create_that_stopped_part_way_names_what_it_completed_and_is_undone(self, world,
                                                                                monkeypatch):
        monkeypatch.setattr(world, "create", lambda *a: {
            "ok": False, "completed": ["credentials", "commit"], "commit": "c0ffee",
            "reason": "render failed"})
        rec = world.run(answers(upto=5))
        assert rec["outcome"] == "create_failed" and world.undone == ["edge1"]
        assert rec["stop"]["compared"] == ("Create did not complete: render failed (completed: "
                                           "credentials, commit)")


class TestTheBlankCheckAgain:
    def test_the_record_holds_the_blank_check_again(self, world):
        rec = world.run(answers())
        assert rec.get("recheck") == {"blank": True, "size": 0,
                                      "reason": "startup-config is 0 bytes in 'dir nvram:''s "
                                                "output"}

    def test_a_saved_configuration_found_again_names_the_size_and_the_rule(self, world):
        rec = world.run(answers(recheck=saved_nvram(99), upto=5))
        assert rec["stop"]["compared"] == ("the blank check again found startup-config is 99 "
                                           "bytes in 'dir nvram:''s output: the device holds a "
                                           "saved configuration (blank needs 0 or none)")

    def test_a_prompt_the_blank_check_again_does_not_expect_names_that_step(self, world):
        got = answers()
        got[4] = b"dir nvram:\r\nPassword: "
        rec = world.run(got[:5])
        assert rec["outcome"] == "unexpected" and world.undone == ["edge1"]
        assert rec["stop"]["compared"].startswith(
            "expected priv_exec after the blank check again; the session ended aborted: ")


class TestTheLines:
    def test_an_ignored_informational_line_is_not_a_refusal_while_typing(self, world):
        got = answers()
        at = _at(got, b"hostname edge1\r\n")
        got[at] = f"hostname edge1\r\n{MODULUS}\r\nedge1(config)#".encode()
        rec = world.run(got)
        assert rec["outcome"] == "done", rec["reason"]
        assert world.undone == []

    def test_a_refused_line_is_named_whole_whatever_its_last_letter(self, world):
        world.dev["name"] = "edgeX"
        line = "hostname edgeX"
        got = answers()
        at = _at(got, b"hostname edge1\r\n")
        got[at] = (f"{line}\r\n               ^\r\n% Invalid input detected at '^' marker."
                   f"\r\n\r\n{_prompt(line, 'edgeX')}").encode()
        rec = world.run(got[:at + 1], fields={"hostname": "edgeX"})
        assert rec["outcome"] == "refused_line"
        assert rec["stop"]["compared"] == ("'hostname edgeX' was refused: \"% Invalid input "
                                           "detected at '^' marker.\". Stopped there")


class TestTheReadBack:
    def test_an_ignored_informational_line_is_not_a_refusal_in_a_read_back(self, world):
        rec = world.run(answers(reads={"show running-config | section line con 0":
                                       f"{MODULUS}\r\nline con 0\r\n exec-timeout 15 0\r\n"}))
        assert rec["outcome"] == "done", rec["reason"]
        assert world.undone == []

    def test_a_prompt_a_read_back_does_not_expect_names_the_read(self, world):
        got = answers()
        at = _at(got, b"show running-config interface GigabitEthernet0/1\r\n")
        got[at] = b"show running-config interface GigabitEthernet0/1\r\nPassword: "
        rec = world.run(got[:at + 1])
        assert rec["outcome"] == "unexpected" and world.undone == ["edge1"]
        assert rec["stop"]["compared"].startswith(
            "expected priv_exec after 'show running-config interface GigabitEthernet0/1'; the "
            "session ended aborted: ")

    def test_the_record_holds_the_read_back_s_verdict(self, world):
        rec = world.run(answers())
        assert rec["read_back"] == {"ok": True, "differs": [],
                                    "mac_why": f"the MAC in use, from {MAC_TEXT}"}
