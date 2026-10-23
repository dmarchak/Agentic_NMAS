"""A prompt followed by the device's own syslog is still the prompt (s5's first recorded take on
deploy 2, 2026-10-23, run 20261023T203440850197Z: real-hardware catch #10).

After Vlan1's `no shutdown` the switch printed `s5(config-if)#` and then three syslog lines
(`%LINEPROTO-5-UPDOWN`, `%LINK-3-UPDOWN`) and no new prompt. `console_session.read_state` let
only the unterminated last line read as a prompt, so the prompt was read as output and the run
waited out its 120 s step and stopped, safely, with `ip default-gateway`, `line con 0`,
`exec-timeout 15 0` and `end` never sent. Every fake console before answered with its prompt
last (C1626's shape); this file drives the session with the take's REAL answers
(tests/fixtures/console/s5-kickstart-take-syslog.txt)."""

import codecs
import os
import re

from modules.nsot import console_profiles as P
from modules.nsot import console_session as S
from tests.test_console_session import SETTLE, answer, plan, session

SWITCH = P.load("cisco_ios_switch")
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "console",
                       "s5-kickstart-take-syslog.txt")
SYSLOG = ("*Oct 23 20:27:43.622: %LINEPROTO-5-UPDOWN: Line protocol on Interface Vlan1, changed "
          "state to down")
LINK = "*Oct 23 20:27:46.260: %LINK-3-UPDOWN: Interface Vlan1, changed state to up"


def take():
    """The take's sends and the console's answer to each, in order."""
    with open(FIXTURE, encoding="ascii") as fh:
        text = fh.read()
    parts = re.split(r"^>>> send '(.*)'\n", text, flags=re.M)
    sends = [codecs.decode(s, "unicode_escape").encode("ascii") for s in parts[1::2]]
    answers = [a[:-1] if a.endswith("\n") else a for a in parts[2::2]]
    return sends, [a.encode("ascii") for a in answers]


class TestTheTakeContinuesPastTheSyslog:
    def test_the_real_answers_reach_the_line_after_no_shutdown(self):
        """From `configure terminal` on, each real answer is answered with the next line; the
        answer to Vlan1's `no shutdown`, its prompt followed by three syslog lines, is answered
        with `ip default-gateway` (where the take stopped)."""
        sends, answers = take()
        start = sends.index(b"configure terminal\r")
        assert sends[-1] == b" no shutdown\r" and len(sends) == 15, sends
        typed = sends[start:] + [b"ip default-gateway 10.255.4.13\r"]
        steps = [(P.PRIV_EXEC, typed[0])] + [(P.CONFIG, t) for t in typed[1:]]
        s = session(plan(*steps, final=(P.PRIV_EXEC,)), profile=SWITCH)
        t = 1.0
        d = answer(s, answers[start - 1], t)              # dir nvram:'s answer: Switch#
        assert (d.action, d.data) == ("send", typed[0])
        for i, reply in enumerate(answers[start:], 1):
            t += 1.0
            d = answer(s, reply, t)
            assert (d.action, d.data) == ("send", typed[i]), (i, d)
        assert s.sent() == b"".join(typed)
        assert SYSLOG.encode() in answers[-1], "the fixture is the take's real answer"

    def test_no_answer_in_the_take_reads_as_a_refusal(self):
        """The syslog lines (`*timestamp: %FACILITY-SEV-MNEMONIC:`) are never a `%` refusal."""
        _sends, answers = take()
        assert [S.refused_in(a.decode(), SWITCH) for a in answers] == [("", "")] * len(answers)


class TestAPromptBeforeLogs:
    def test_a_prompt_followed_only_by_syslog_is_the_prompt(self):
        text = f" no shutdown\r\ns5(config-if)#\r\n{SYSLOG}\r\n{LINK}\r\n"
        assert S.read_state(text, SWITCH, " no shutdown") == (P.CONFIG, "s5(config-if)#", False)

    def test_a_prompt_followed_by_a_bare_line_break_is_still_output(self):
        """The control: only the unterminated line may read as a prompt (the settle rule);
        a syslog line after it is what lets a terminated one."""
        assert S.read_state("s5(config-if)#\r\n", SWITCH, "")[0] == S.OUTPUT

    def test_output_after_the_syslog_is_what_decides(self):
        text = f"s5(config-if)#\r\n{LINK}\r\nsomething the device printed\r\n"
        assert S.read_state(text, SWITCH, "") == (S.OUTPUT, "something the device printed",
                                                  False)

    def test_syslog_interleaved_with_the_echo_still_reaches_the_prompt(self):
        """Without `logging synchronous` IOS prints a message in the middle of an echo; the
        echo's pieces and the message never hide the prompt after them."""
        text = f" no shut\r\n{LINK}\r\ndown\r\ns5(config-if)#"
        assert S.read_state(text, SWITCH, " no shutdown") == (P.CONFIG, "s5(config-if)#", True)
        assert S.refused_in(text, SWITCH) == ("", "")

    def test_a_session_waits_out_the_settle_then_answers_the_prompt_before_logs(self):
        s = session(plan((P.CONFIG, b"ip default-gateway 192.0.2.1\r")), profile=SWITCH)
        d = s.feed(f"s5(config-if)#\r\n{SYSLOG}\r\n".encode(), 1.0)
        if d.action != "send":
            d = s.tick(1.0 + SETTLE)
        assert (d.action, d.data) == ("send", b"ip default-gateway 192.0.2.1\r")
