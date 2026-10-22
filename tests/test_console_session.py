"""The console session's state machine (modules/nsot/console_session.py; docs/LAB9_PLAN.md section
8, O1): driven by real console text, it sends exactly the plan's bytes and zero beyond, and
aborts on any unexpected state, naming the expected and the found.

The fixtures (tests/fixtures/console/, README.md there) are real captures, unchanged: a
switch's boot log to the boot loader's release, its console reader's lines up to "Press RETURN
to get started.", and a diagnostic session's transcript (`>>> send '...'` lines are what that
session sent; the text between them is what the console answered)."""

import codecs
import os
import re

import pytest

from modules.nsot import console_profiles as P
from modules.nsot import console_session as S

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "console")
SWITCH = P.load("cisco_ios_switch")
ROUTER = P.load("cisco_ios_router")
NO_VALUES = {}
SETTLE = 0.5


def fixture(name: str) -> bytes:
    with open(os.path.join(FIXTURES, name), "rb") as fh:
        return fh.read()


BOOT = fixture("s5-boot-to-release.txt")
PNP = fixture("s5-pnp-stopped.txt")


def session_fixture():
    """The diagnostic session's sends and the console's answer to each, in order."""
    text = fixture("s5-session-enable-dir-nvram.txt").decode("ascii")
    parts = re.split(r"^>>> send '(.*)'\n", text, flags=re.M)
    sends = [codecs.decode(s, "unicode_escape").encode("ascii") for s in parts[1::2]]
    # The transcript writes a line break of its own before each `>>> send` line.
    answers = [a[:-1] if a.endswith("\n") else a for a in parts[2::2]]
    return sends, [a.encode("ascii") for a in answers]


def plan(*steps, final=(P.PRIV_EXEC,)):
    return S.Plan(steps=tuple(S.Step(e, d) for e, d in steps), final=tuple(final))


def session(the_plan, profile=SWITCH, settle=SETTLE, quiet=5.0, timeout=600.0):
    return S.ConsoleSession(profile, the_plan, start=0.0, settle_s=settle, quiet_s=quiet,
                            step_timeout_s=timeout, values=NO_VALUES)


def answer(s, data: bytes, t: float):
    """The console prints *data* at *t* and then stays quiet for the settle interval: the
    decision once it has settled."""
    first = s.feed(data, t)
    if first.action != "wait":
        return first
    return s.tick(t + SETTLE)


SURVEY = plan((P.PRESS_RETURN, b"\r"), (P.USER_EXEC, b"enable\r"),
              (P.PRIV_EXEC, b"dir nvram:\r"))


# ── Real text ─────────────────────────────────────────────────────────────────────────────

def test_the_real_boot_text_reaches_press_return_and_sends_the_one_cr():
    s = session(plan((P.PRESS_RETURN, b"\r"), final=(P.USER_EXEC,)))
    during = answer(s, BOOT, 1.0)
    assert during.action == "wait" and during.data == b""
    d = s.feed(PNP, 2.0)
    assert (d.state, d.action, d.data) == (P.PRESS_RETURN, "send", b"\r")
    assert s.sent() == b"\r"


def test_the_real_boot_text_in_small_chunks_reaches_the_same_state():
    """Every 7-byte chunk arrives at once (no settle between them): nothing decides until the
    whole "Press RETURN" line has arrived. Before the settle rule, a chunk ending inside an
    output line (`<redacted>` before its `.`) read as a `>` prompt and aborted here."""
    s = session(plan(final=(P.PRESS_RETURN,)))
    text = BOOT + PNP
    decisions = [s.feed(text[i:i + 7], 1.0) for i in range(0, len(text), 7)]
    assert [d.action for d in decisions[:-1]] == ["wait"] * (len(decisions) - 1)
    assert (decisions[-1].action, s.attach_state) == ("done", P.PRESS_RETURN)


def test_the_boot_text_settling_at_every_chunk_never_reads_as_a_prompt():
    """The boot log split at every line, each piece left to settle: no piece is a prompt."""
    s = session(plan(final=(P.PRESS_RETURN,)))
    t = 1.0
    states = set()
    for piece in BOOT.split(b"\n"):
        states.add(answer(s, piece + b"\n", t).state)
        t += 1.0
    assert states <= {S.OUTPUT, P.BOOT}, states
    assert s.sent() == b""


def test_the_real_session_drives_user_exec_to_priv_exec_with_exactly_its_sends():
    sends, answers = session_fixture()
    assert sends == [b"\r", b"enable\r", b"dir nvram:\r"]
    s = session(SURVEY)
    out = [s.feed(PNP, 1.0)]
    for t, text in enumerate(answers, 2):
        out.append(answer(s, text, float(t)))
    assert [(d.state, d.action) for d in out] == [
        (P.PRESS_RETURN, "send"), (P.USER_EXEC, "send"), (P.PRIV_EXEC, "send"),
        (S.DONE, "done")]
    assert [d.data for d in out if d.action == "send"] == sends
    # The end's reason (the mutation run of 2026-10-22: it made None survived).
    assert out[-1].reason == "ended in priv_exec"
    assert s.sent() == b"".join(sends)
    assert s.attach_state == P.PRESS_RETURN
    assert "startup-config" in s.received_since_send()


# ── Exactly the plan's bytes ──────────────────────────────────────────────────────────────

def test_the_machine_sends_exactly_the_plans_bytes_and_zero_beyond():
    _sends, answers = session_fixture()
    s = session(SURVEY)
    s.feed(PNP, 1.0)
    for t, text in enumerate(answers, 2):
        answer(s, text, float(t))
    # The prompts again, and time passing: still nothing more.
    for t in range(10, 20):
        answer(s, b"\r\nSwitch#", float(t))
    planned = sum(len(step.send) for step in SURVEY.steps)
    assert len(s.sent()) == planned == 19
    assert s.sent() == b"\renable\rdir nvram:\r"


def test_a_step_is_sent_once_even_when_asked_again_before_an_answer():
    s = session(SURVEY)
    assert s.feed(PNP, 1.0).action == "send"
    for t in (1.5, 2.0, 2.5):
        d = s.tick(t)
        assert (d.action, d.data) == ("wait", b"")
    assert s.sent() == b"\r"


def test_the_prompt_a_step_answered_does_not_answer_the_next_step():
    s = session(plan((P.USER_EXEC, b"enable\r"), (P.PRIV_EXEC, b"dir nvram:\r")))
    assert answer(s, b"Switch>", 1.0).data == b"enable\r"
    assert s.tick(2.0).action == "wait"
    assert s.sent() == b"enable\r"


def test_a_reprinted_prompt_after_a_send_aborts_and_is_never_answered_again():
    s = session(plan((P.USER_EXEC, b"enable\r"), (P.PRIV_EXEC, b"dir nvram:\r")))
    answer(s, b"Switch>", 1.0)
    d = answer(s, b"enable\r\n% Bad secrets\r\n\r\nSwitch>", 2.0)
    assert (d.state, d.action) == (S.ABORTED, "abort")
    assert d.reason == ("expected priv_exec (step 2 of 2), found user_exec: 'Switch>' (out of "
                        "the plan's order)")
    assert s.sent() == b"enable\r"


# ── The settle rule ───────────────────────────────────────────────────────────────────────

def test_a_prompt_is_acted_on_only_once_it_has_settled():
    """Until then it reads as waiting, the session's state too (the mutation run of 2026-10-22:
    that state made None, and the session's recorded state made None, survived)."""
    s = session(plan((P.USER_EXEC, b"enable\r")))
    assert s.feed(b"\r\nSwitch>", 1.0) == S.Decision(S.WAITING, "wait")
    assert s.state == S.WAITING
    assert s.tick(1.0 + SETTLE - 0.01) == S.Decision(S.WAITING, "wait")
    assert s.tick(1.0 + SETTLE).data == b"enable\r"


def test_the_sessions_state_is_what_the_console_last_read_as():
    s = session(SURVEY, quiet=5.0)
    s.feed(b"Initializing flash...\r\n", 1.0)
    assert s.state == S.OUTPUT
    s.feed(b"Booting `IOSv'\r\n", 2.0)
    assert s.state == P.BOOT
    s.tick(7.0)
    assert s.state == P.BOOT
    s.feed(PNP, 8.0)
    assert s.state == P.PRESS_RETURN


def test_a_complete_line_that_looks_like_a_prompt_is_output():
    """A boot's progress line of `#` or an output line ending in `>` is a line, not a prompt."""
    s = session(SURVEY)
    for t, text in enumerate((b"##########\r\n", b"Switch>\r\n", b"Password:\r\n",
                              b"--More--\r\n"), 1):
        d = answer(s, text, float(t))
        assert (d.state, d.action) == (S.OUTPUT, "wait")
    assert s.sent() == b""


def test_a_partial_line_completed_before_it_settles_is_not_a_prompt():
    s = session(SURVEY)
    assert s.feed(b"contact <redacted>", 1.0).action == "wait"
    assert s.feed(b".\r\nPress RETURN to get started.\r\n", 1.1).data == b"\r"


def test_the_settle_interval_counts_from_the_last_text_heard():
    s = session(plan((P.USER_EXEC, b"enable\r")))
    s.feed(b"\r\nSwi", 1.0)
    s.feed(b"tch>", 1.4)
    assert s.tick(1.0 + SETTLE).action == "wait"
    assert s.tick(1.4 + SETTLE).data == b"enable\r"


# ── Aborts ────────────────────────────────────────────────────────────────────────────────

def test_a_password_prompt_aborts_with_nothing_sent_after_it():
    s = session(SURVEY)
    s.feed(PNP, 1.0)
    d = answer(s, b"\r\n\r\nUser Access Verification\r\n\r\nPassword: ", 2.0)
    assert (d.state, d.action) == (S.ABORTED, "abort")
    assert d.reason == "expected user_exec (step 2 of 3), found login_password: 'Password:'"
    for t in (3.0, 4.0):
        assert answer(s, b"\r\nSwitch>", t) == d
        assert s.tick(t + 100) == d
    assert s.sent() == b"\r"


def test_an_aborted_session_answers_every_later_input_with_the_same_abort():
    """Its state and its reason, unchanged (the mutation run of 2026-10-22: the later decision's
    state or reason made None survived a check of its action alone)."""
    s = session(SURVEY)
    d = answer(s, b"\r\nUsername: ", 1.0)
    assert s.feed(b"x", 2.0) == S.Decision(S.ABORTED, "abort", reason=d.reason)
    assert s.state == S.ABORTED


def test_a_username_prompt_aborts():
    s = session(SURVEY)
    s.feed(PNP, 1.0)
    d = answer(s, b"\r\nUsername: ", 2.0)
    assert d.action == "abort"
    assert "found login_user: 'Username:'" in d.reason
    assert s.sent() == b"\r"


def test_a_password_prompt_aborts_even_where_the_plan_waits_for_its_end():
    s = session(plan((P.USER_EXEC, b"enable\r")))
    answer(s, b"Switch>", 1.0)
    d = answer(s, b"enable\r\nPassword: ", 2.0)
    assert d.action == "abort"
    assert d.reason == ("expected one of priv_exec (the plan's end), found login_password: "
                        "'Password:'")
    assert s.sent() == b"enable\r"


def test_a_pager_aborts():
    s = session(plan((P.PRIV_EXEC, b"dir nvram:\r")))
    answer(s, b"Switch#", 1.0)
    d = answer(s, b"dir nvram:\r\nDirectory of nvram:/\r\n  254  -rw-  0  <no date>  "
                  b"startup-config\r\n --More-- ", 2.0)
    assert (d.state, d.action) == (S.ABORTED, "abort")
    assert "found more: '--More--'" in d.reason
    assert s.sent() == b"dir nvram:\r"


def test_a_state_out_of_the_plans_order_aborts_naming_both():
    s = session(SURVEY)
    d = answer(s, b"\r\nSwitch#", 1.0)
    assert (d.state, d.action) == (S.ABORTED, "abort")
    assert d.reason == ("expected press_return (step 1 of 3), found priv_exec: 'Switch#' (out of "
                        "the plan's order)")
    assert s.sent() == b""


def test_a_setup_dialog_the_plan_does_not_name_aborts():
    s = session(SURVEY)
    d = answer(s, b"Would you like to enter the initial configuration dialog? [yes/no]: ", 1.0)
    assert d.action == "abort"
    assert "found setup_dialog" in d.reason


def test_a_setup_dialog_the_plan_names_is_answered():
    s = session(plan((P.SETUP_DIALOG, b"no\r"), (P.PRESS_RETURN, b"\r"), final=(P.USER_EXEC,)))
    assert answer(s, b"\r\nWould you like to enter the initial configuration dialog? "
                     b"[yes/no]: ", 1.0).data == b"no\r"
    assert s.feed(b"no\r\n\r\nPress RETURN to get started!\r\n", 2.0).data == b"\r"
    assert answer(s, b"\r\nSwitch>", 3.0).action == "done"


def test_an_end_state_the_plan_does_not_name_aborts():
    s = session(plan((P.USER_EXEC, b"enable\r")))
    answer(s, b"Switch>", 1.0)
    d = answer(s, b"enable\r\nSwitch(config)#", 2.0)
    assert d.action == "abort"
    assert d.reason == "expected one of priv_exec (the plan's end), found config: 'Switch(config)#'"


def test_an_unknown_prompt_aborts_only_after_the_quiet_period():
    s = session(SURVEY, quiet=5.0)
    assert answer(s, b"\r\nrommon 1 > ", 1.0).action == "wait"
    assert s.tick(5.9).state == S.UNKNOWN
    assert s.tick(5.9).action == "wait"
    d = s.tick(6.0)
    assert (d.state, d.action) == (S.ABORTED, "abort")
    assert d.reason == ("expected press_return (step 1 of 3), found an unknown prompt "
                        "'rommon 1 >' after 5 s quiet")
    assert s.sent() == b""


def test_an_unrecognised_complete_line_is_output_and_waits_past_the_quiet_period():
    s = session(SURVEY, quiet=5.0)
    d = s.feed(b"Initializing flash...\r\n", 1.0)
    assert (d.state, d.action) == (S.OUTPUT, "wait")
    assert s.tick(100.0).action == "wait"


def test_the_step_bound_aborts_naming_what_it_waited_for():
    s = session(SURVEY, quiet=5.0, timeout=60.0)
    s.feed(b"Initializing flash...\r\n", 1.0)
    assert s.tick(59.9).action == "wait"
    d = s.tick(60.0)
    assert d.action == "abort"
    assert d.reason == ("expected press_return (step 1 of 3) within 60 s, found output: "
                        "'Initializing flash...'")


def test_the_step_bound_with_nothing_heard_names_the_idle_console():
    s = session(SURVEY, quiet=5.0, timeout=60.0)
    d = s.tick(60.0)
    assert d.reason == "expected press_return (step 1 of 3) within 60 s, found idle"


def test_the_step_bound_counts_from_the_last_send():
    s = session(SURVEY, quiet=5.0, timeout=60.0)
    s.feed(PNP, 50.0)
    assert s.tick(109.9).action == "wait"
    assert s.tick(110.0).action == "abort"


def test_an_unknown_prompt_still_arriving_is_not_judged_until_quiet():
    """A prompt split across chunks reads as unknown for a moment; the next chunk completes it."""
    s = session(plan((P.USER_EXEC, b"enable\r")))
    assert s.feed(b"\r\nSwi", 1.0).action == "wait"
    assert s.tick(3.0).action == "wait"
    d = answer(s, b"tch>", 4.0)
    assert (d.action, d.data) == ("send", b"enable\r")


# ── Reading the console ───────────────────────────────────────────────────────────────────

def test_a_message_split_across_chunks_is_joined():
    s = session(plan((P.PRESS_RETURN, b"\r"), final=(P.USER_EXEC,)))
    sent = [s.feed(piece, 1.0).data for piece in (b"Press RET", b"URN to get st", b"arted.\r",
                                                  b"\n")]
    assert sent == [b"", b"", b"\r", b""]


def test_iac_and_nul_bytes_are_stripped_before_the_prompt_is_read():
    s = session(plan((P.USER_EXEC, b"enable\r")))
    d = answer(s, b"\xff\xfb\x01\xff\xfb\x03\xff\xfd\x18\r\n\x00Sw\x00itch>", 1.0)
    assert (d.state, d.data) == (P.USER_EXEC, b"enable\r")


def test_an_iac_sequence_split_across_chunks_is_held_and_dropped():
    s = session(plan((P.USER_EXEC, b"enable\r")))
    assert s.feed(b"\r\nSwitch\xff", 1.0).action == "wait"
    assert s.feed(b"\xfb", 1.1).action == "wait"
    d = answer(s, b"\x01>", 1.2)
    assert d.data == b"enable\r"


@pytest.mark.parametrize("chunks,text", [
    ([b"a\r\nb"], "a\nb"),
    ([b"a\rb"], "a\nb"),
    ([b"a\nb"], "a\nb"),
    ([b"a\r", b"\nb"], "a\nb"),
    ([b"a\r\r\nb"], "a\n\nb"),
    ([b"a\n\nb"], "a\n\nb"),
    ([b"a\r\x00\nb"], "a\n\nb"),
    ([b"a\x00b\x07c\x1bd\x7fe\tf"], "abcde\tf"),
    ([b"a\xe9b"], "a?b"),
    ([b"\xff\xfb\x01a\xff\xfe\x22b"], "ab"),
    ([b"a\xff\xffb"], "a?b"),
    ([b"a\xff\xfa\x18\x01\xff\xf0b"], "ab"),
    ([b"a\xff\xfa\x18", b"\x01\xff", b"\xf0b"], "ab"),
    ([b"a\xff", b"\xfd", b"\x01b"], "ab"),
    ([b"a\xff\xf1b\xff\xf9c"], "abc"),
    ([b" ~"], " ~"),
], ids=["crlf", "lone-cr", "lf", "crlf-split", "cr-crlf", "lf-lf", "cr-nul-lf", "controls",
        "non-ascii", "will-wont", "escaped-ff", "subnegotiation", "subnegotiation-split",
        "option-split", "nop-ga", "printable-ends"])
def test_the_cleaner_turns_console_bytes_into_text(chunks, text):
    c = S.Cleaner()
    assert "".join(c.feed(ch) for ch in chunks) == text


def test_an_escaped_ff_ending_a_chunk_is_text_at_once():
    """IAC IAC is a data byte, complete in this chunk: never held back for the next (the
    mutation run of 2026-10-22: the end-of-data checks moved by one survived)."""
    assert S.Cleaner().feed(b"a\xff\xff") == "a?"


def test_an_option_whose_byte_has_not_arrived_holds_until_it_does():
    """IAC DO, its option byte (0x22, printable) in the next chunk: the byte is dropped, never
    shown as text (the mutation run of 2026-10-22: the option's end check never true, or `>`
    for `>=`, survived)."""
    c = S.Cleaner()
    assert c.feed(b"a\xff\xfd") == "a"
    assert c.feed(b"\x22b") == "b"


def test_two_subnegotiations_in_one_chunk_each_end_at_their_own_iac_se():
    """The second's search starts after its own start (the mutation run of 2026-10-22: from the
    chunk's start, or the LAST IAC SE, survived)."""
    sb = b"\xff\xfa\x18\x00VT100\xff\xf0"
    assert S.Cleaner().feed(b"a" + sb + b"b" + sb + b"c") == "abc"


def test_a_subnegotiations_payload_is_never_text():
    """Printable payload bytes (a terminal type) are dropped with the sequence (the mutation run
    of 2026-10-22: resuming two bytes before the IAC SE survived on a control-byte payload)."""
    assert S.Cleaner().feed(b"a\xff\xfa\x18\x00VT100\xff\xf0b") == "ab"


def test_an_empty_subnegotiation_ends_at_its_iac_se():
    assert S.Cleaner().feed(b"a\xff\xfa\xff\xf0b") == "ab"


def test_the_first_byte_outside_ascii_is_shown_as_a_mark():
    """0x80, the boundary (the mutation run of 2026-10-22: `>` for `>=` survived on 0xE9)."""
    assert S.Cleaner().feed(b"a\x80b\x7fc") == "a?bc"


@pytest.mark.parametrize("data,end", [
    (b"\xff", None), (b"\xff\xff", 2), (b"\xff\xf1", 2), (b"\xff\xfb", 3), (b"\xff\xfb\x01", 3),
    (b"\xff\xfa\x18", None), (b"\xff\xfa\x18\x01\xff\xf0", 6), (b"x\xff\xf9", 3),
])
def test_sequence_end_says_where_each_telnet_command_ends(data, end):
    i = data.index(b"\xff")
    assert S.sequence_end(data, i) == end


def test_a_syslog_line_after_the_message_does_not_hide_it():
    s = session(plan((P.PRESS_RETURN, b"\r"), final=(P.USER_EXEC,)))
    d = s.feed(PNP + b"*Oct 22 06:10:01.123: %LINK-3-UPDOWN: Interface GigabitEthernet0/1, "
                     b"changed state to up\r\n%SYS-5-CONFIG_I: Configured from console\r\n", 1.0)
    assert d.data == b"\r"


def test_the_echo_of_what_was_sent_does_not_decide_the_state():
    s = session(plan((P.USER_EXEC, b"enable\r")), quiet=5.0)
    answer(s, b"Switch>", 1.0)
    d = answer(s, b"enable\r\n", 2.0)
    assert (d.state, d.action) == (S.WAITING, "wait")
    d = s.tick(7.0)
    assert (d.state, d.action) == (S.IDLE, "wait")


@pytest.mark.parametrize("line,state", [
    ("Switch>", P.USER_EXEC), ("Switch#", P.PRIV_EXEC), ("Switch(config)#", P.CONFIG),
    ("Switch(config-if)#", P.CONFIG), ("Switch(config-vlan)# ", P.CONFIG),
    ("Password:", P.LOGIN_PASSWORD), ("Username: ", P.LOGIN_USER), (" --More-- ", P.MORE),
    ("Press RETURN to get started.", P.PRESS_RETURN),
    ("Would you like to enter the initial configuration dialog? [yes/no]:", P.SETUP_DIALOG),
    ("Booting `IOSv'", P.BOOT), ("Directory of nvram:/", ""),
])
def test_classify_reads_each_state_and_a_config_prompt_before_the_privileged_one(line, state):
    assert S.classify(line, SWITCH) == state


@pytest.mark.parametrize("line,state", [
    ("Press RETURN to get started.", P.PRESS_RETURN), ("Booting `IOSv'", P.BOOT),
    ("Switch>", ""), ("Switch#", ""), ("Password:", ""), ("--More--", ""),
])
def test_a_complete_line_classifies_only_as_a_message(line, state):
    assert S.classify(line, SWITCH, S.LINE_STATES) == state


@pytest.mark.parametrize("text,expected", [
    ("a\nSwitch>", (P.USER_EXEC, "Switch>", True)),
    ("Switch>\n", (S.OUTPUT, "Switch>", False)),
    ("Press RETURN to get started.\n\n", (P.PRESS_RETURN, "Press RETURN to get started.",
                                          False)),
    ("x\nenable\n", (S.OUTPUT, "x", False)),
    ("enable\n  \n", ("", "", False)),
    ("weird$ ", (S.UNKNOWN, "weird$", True)),
    ("", ("", "", False)),
], ids=["prompt", "prompt-as-line", "message-then-blank", "echo-skipped", "echo-only",
        "unknown", "empty"])
def test_read_state_names_the_deciding_line_and_whether_it_is_still_arriving(text, expected):
    assert S.read_state(text, SWITCH, "enable") == expected


def test_the_router_profile_reads_the_same_prompts():
    s = session(plan((P.PRESS_RETURN, b"\r"), (P.USER_EXEC, b"enable\r"), final=(P.PRIV_EXEC,)),
                profile=ROUTER)
    assert s.feed(b"Press RETURN to get started!\r\n", 1.0).data == b"\r"
    assert answer(s, b"\r\nRouter>", 2.0).data == b"enable\r"
    assert answer(s, b"enable\r\nRouter#", 3.0).action == "done"


# ── Idle, attach and the next plan ────────────────────────────────────────────────────────

def test_an_idle_console_is_woken_only_when_the_plan_names_idle():
    s = session(plan((S.IDLE, b"\r"), final=(P.PRIV_EXEC, P.USER_EXEC)), quiet=5.0)
    assert s.tick(4.9).state == S.WAITING
    d = s.tick(5.0)
    assert (d.state, d.action, d.data) == (S.IDLE, "send", b"\r")
    d = answer(s, b"\r\nSwitch#", 6.0)
    assert (d.action, s.attach_state) == ("done", P.PRIV_EXEC)


def test_an_idle_console_is_not_woken_by_a_plan_that_waits_for_a_prompt():
    s = session(SURVEY, quiet=5.0)
    for t in (5.0, 50.0, 500.0):
        d = s.tick(t)
        assert (d.state, d.action) == (S.IDLE, "wait")
    assert s.sent() == b""


def test_the_state_at_attach_is_not_recorded_after_a_line_was_typed():
    s = session(plan((S.IDLE, b"terminal length 0\r")), quiet=5.0)
    s.tick(5.0)
    assert answer(s, b"terminal length 0\r\nSwitch#", 6.0).action == "done"
    assert s.attach_state is None


def test_the_state_at_attach_is_the_first_prompt_and_stays_it():
    s = session(SURVEY)
    s.feed(PNP, 1.0)
    answer(s, b"\r\nSwitch>", 2.0)
    answer(s, b"enable\r\nSwitch#", 3.0)
    assert s.attach_state == P.PRESS_RETURN


def test_a_prompt_still_arriving_is_not_recorded_as_the_state_at_attach():
    s = session(plan((S.IDLE, b"\r"), final=(P.USER_EXEC, P.PRIV_EXEC)), quiet=5.0)
    s.tick(5.0)
    s.feed(b"\r\nSwitch>", 6.0)
    assert s.attach_state is None
    s.tick(6.0 + SETTLE)
    assert s.attach_state == P.USER_EXEC


def test_a_login_prompt_at_attach_is_recorded_before_the_abort():
    s = session(plan((S.IDLE, b"\r")), quiet=5.0)
    s.tick(5.0)
    answer(s, b"\r\nPassword: ", 6.0)
    assert (s.state, s.attach_state) == (S.ABORTED, P.LOGIN_PASSWORD)


def test_continue_with_answers_the_prompt_the_last_plan_ended_on():
    s = session(plan((S.IDLE, b"\r"), final=(P.USER_EXEC, P.PRIV_EXEC)), quiet=5.0)
    s.tick(5.0)
    assert answer(s, b"\r\nSwitch>", 6.0).action == "done"
    d = s.continue_with(plan((P.USER_EXEC, b"enable\r")), 7.0)
    assert d.data == b"enable\r"
    assert answer(s, b"enable\r\nSwitch#", 8.0).action == "done"
    assert s.sent() == b"\renable\r"


def test_continue_with_bounds_the_new_wait_from_now():
    s = session(plan((S.IDLE, b"\r"), final=(P.USER_EXEC,)), quiet=5.0, timeout=60.0)
    s.tick(5.0)
    answer(s, b"\r\nSwitch>", 6.0)
    s.continue_with(plan((P.PRIV_EXEC, b"dir nvram:\r")), 100.0)
    assert s.tick(159.9).action == "abort"
    s = session(plan((S.IDLE, b"\r"), final=(P.USER_EXEC,)), quiet=5.0, timeout=60.0)
    s.tick(5.0)
    answer(s, b"\r\nSwitch>", 6.0)
    s.continue_with(plan((P.USER_EXEC, b"enable\r"), final=(P.PRIV_EXEC,)), 100.0)
    assert s.tick(159.9).action == "wait"
    assert s.tick(160.0).reason.startswith("expected one of priv_exec (the plan's end) within "
                                           "60 s")


def test_continue_with_is_refused_unless_done():
    s = session(SURVEY)
    with pytest.raises(ValueError, match="continue_with needs state 'done'; the session is "
                                         "'waiting'"):
        s.continue_with(SURVEY, 1.0)


def test_a_done_session_stays_done_and_sends_nothing():
    s = session(plan(final=(P.USER_EXEC,)))
    assert answer(s, b"Switch>", 1.0).action == "done"
    d = answer(s, b"\r\nSwitch#", 2.0)
    assert (d.state, d.action, d.reason) == (S.DONE, "done", "ended in user_exec")
    assert s.sent() == b""


# ── Plans and bounds refused ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("steps,final,match", [
    ([(P.LOGIN_PASSWORD, b"x\r")], (P.PRIV_EXEC,), "step 1 sends in 'login_password'"),
    ([(P.MORE, b" \r")], (P.PRIV_EXEC,), "step 1 sends in 'more'"),
    ([(P.BOOT, b"\r")], (P.PRIV_EXEC,), "step 1 sends in 'boot'"),
    ([(P.USER_EXEC, b"enable")], (P.PRIV_EXEC,), "one line ended by CR"),
    ([(P.USER_EXEC, "enable\r")], (P.PRIV_EXEC,), "one line ended by CR"),
    ([(P.USER_EXEC, b"en\nable\r")], (P.PRIV_EXEC,), "printable ASCII only"),
    ([(P.USER_EXEC, b"en\x7fable\r")], (P.PRIV_EXEC,), "printable ASCII only"),
    ([(P.USER_EXEC, b"en\x1fable\r")], (P.PRIV_EXEC,), "printable ASCII only"),
    ([(P.USER_EXEC, b"\xe9\r")], (P.PRIV_EXEC,), "printable ASCII only"),
    ([(P.USER_EXEC, b"\r\r")], (P.PRIV_EXEC,), "printable ASCII only"),
    ([(S.IDLE, b"\r"), (P.CONFIG, b"x")], (P.PRIV_EXEC,), "step 2 sends b'x'"),
    ([], (), "at least one state"),
    ([], (P.LOGIN_USER,), "may not end in 'login_user'"),
    ([], (S.IDLE,), "may not end in 'idle'"),
    ([], (P.PRIV_EXEC, P.MORE), "may not end in 'more'"),
], ids=["password", "more", "boot", "no-cr", "str", "newline", "del", "unit-separator",
        "non-ascii", "two-crs", "second-step", "no-final", "final-login", "final-idle",
        "second-final"])
def test_a_plan_that_could_send_outside_its_shape_is_refused(steps, final, match):
    with pytest.raises(ValueError, match=re.escape(match)):
        plan(*steps, final=final)


def test_a_plan_with_printable_lines_and_a_bare_cr_is_accepted():
    p = plan((S.IDLE, b"\r"), (P.USER_EXEC, b" ~\r"), final=(P.USER_EXEC,))
    assert len(p.steps) == 2


@pytest.mark.parametrize("settle,quiet,timeout", [
    (0, 5, 10), (-1, 5, 10), (5, 5, 10), (6, 5, 10), (1, 10, 10), (1, 11, 10)])
def test_the_bounds_must_rise_from_settle_to_quiet_to_the_step_bound(settle, quiet, timeout):
    with pytest.raises(ValueError, match="the bounds must rise"):
        session(SURVEY, settle=settle, quiet=quiet, timeout=timeout)


# ── The transcript ────────────────────────────────────────────────────────────────────────

def test_the_transcript_is_received_and_sent_in_order_and_masked():
    s = S.ConsoleSession(SWITCH, plan((P.USER_EXEC, b"enable\r")), start=0.0,
                         values={"Hunter2Hunter2": "enable"})
    answer(s, b"banner Hunter2Hunter2\r\nenable secret 5 $1$abcd$efgh\r\nSwitch>", 1.0)
    answer(s, b"enable\r\nPassword: ", 2.0)
    t = s.transcript()
    assert "Hunter2Hunter2" not in t and "<redacted:enable>" in t
    assert "$1$abcd$efgh" not in t
    assert t.index("Switch>") < t.index(">>> sent 'enable\\r'") < t.index("Password:") \
        < t.index(">>> aborted: expected one of priv_exec")


def test_the_transcript_is_exactly_the_text_and_the_marks_in_order():
    """Nothing between the pieces (the mutation sample of 2026-10-22: a separator joined between
    them survived the order check)."""
    s = session(plan((P.USER_EXEC, b"enable\r")))
    answer(s, b"Switch>", 1.0)
    answer(s, b"enable\r\nSwitch#", 2.0)
    assert s.transcript() == "Switch>\n>>> sent 'enable\\r'\nenable\nSwitch#"


def test_the_transcript_masks_with_the_installations_values_by_default(monkeypatch):
    monkeypatch.setattr(S.redact, "known_secret_values", lambda: {"Hunter2Hunter2": "x"})
    s = S.ConsoleSession(SWITCH, SURVEY, start=0.0)
    s.feed(b"Hunter2Hunter2\r\n", 1.0)
    assert "Hunter2Hunter2" not in s.transcript()
