"""The echo of the line just sent, still arriving, is never a prompt (s5's retry take on deploy
2c, 2026-10-23, run 20261023T220926977356Z: real-hardware catch #11, C1638).

Every line was accepted, the read-back agreed and the MAC in use was read; then the copy was
sent and the switch echoed it only up to its source URL (`copy tftp://10.255.0.10/s5.cfg`) and
printed nothing more for over 5 s. `console_session.read_state` read that unterminated line as
an unknown prompt, and once the 5 s quiet interval passed the run stopped, safely, before IOS's
`Destination filename [running-config]?`. IOS did take the whole line: the reset's RETURN
afterwards answered that question ("Accessing tftp://10.255.0.10/s5.cfg..."). The take's
transcript keeps no time per event, so the pause is known only to be over 5 s; the copy's own
step bound (`console_ztp.Timings.copy_timeout_s`, 150 s) now bounds it. This file drives the
session with the take's REAL answers (tests/fixtures/console/s5-kickstart-take-copy-echo.txt).
What IOS prints after the pause is its documented wording, not captured (the take stopped)."""

import codecs
import os
import re

from modules.nsot import console_profiles as P
from modules.nsot import console_session as S
from tests.test_console_session import SETTLE, answer, plan, session

SWITCH = P.load("cisco_ios_switch")
FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "console",
                       "s5-kickstart-take-copy-echo.txt")
COPY = b"copy tftp://10.255.0.10/s5.cfg running-config\r"
PARTIAL = "copy tftp://10.255.0.10/s5.cfg"
QUIET = 5.0
BOUND = 150.0


def take():
    """The take's sends and the console's answer to each, in order."""
    with open(FIXTURE, encoding="ascii") as fh:
        text = fh.read()
    parts = re.split(r"^>>> send '(.*)'\n", text, flags=re.M)
    sends = [codecs.decode(s, "unicode_escape").encode("ascii") for s in parts[1::2]]
    answers = [a[:-1] if a.endswith("\n") else a for a in parts[2::2]]
    return sends, [a.encode("ascii") for a in answers]


def copy_session():
    """The copy's two steps from the take's last prompt, under the copy's own bound."""
    return session(plan((P.PRIV_EXEC, COPY), (P.COPY_DESTINATION, b"\r")),
                   profile=SWITCH, quiet=QUIET, timeout=BOUND)


class TestTheTakeWaitsOutTheEchoPause:
    def test_the_fixture_is_the_take_ending_in_the_partial_echo(self):
        sends, answers = take()
        assert sends[-1] == COPY and len(sends) == 25, sends
        assert answers[-1] == PARTIAL.encode(), "the take's real last answer, unterminated"
        assert answers[-2].endswith(b"s5#"), "the copy was sent at the privileged prompt"

    def test_the_partial_echo_is_waited_on_past_the_quiet_interval(self):
        """The take's stop: the partial echo, then quiet past 5 s. It is a wait now (the take
        aborted here), and stays one up to the copy's bound."""
        _sends, answers = take()
        s = copy_session()
        d = answer(s, answers[-2], 1.0)                   # show interfaces' answer: s5#
        assert (d.action, d.data) == ("send", COPY)
        d = s.feed(answers[-1], 2.0)
        for t in (2.0 + SETTLE, 2.0 + QUIET, 2.0 + QUIET + 1.0, 1.0 + BOUND - 1.0):
            d = s.tick(t)
            assert d.action == "wait", (t, d)
        assert s.state != P.COPY_DESTINATION

    def test_the_rest_of_the_echo_and_ios_question_are_answered_with_return(self):
        """IOS's documented continuation after the pause (not captured: the take stopped)."""
        _sends, answers = take()
        s = copy_session()
        answer(s, answers[-2], 1.0)
        s.feed(answers[-1], 2.0)
        s.tick(2.0 + QUIET + 1.0)
        d = answer(s, b" running-config\r\nDestination filename [running-config]? ", 30.0)
        assert (d.action, d.data) == ("send", b"\r")

    def test_the_copy_s_bound_still_ends_an_echo_that_never_finishes(self):
        """Bounded from the copy's send, which is the prompt's settle after it arrived."""
        _sends, answers = take()
        s = copy_session()
        d = answer(s, answers[-2], 1.0)
        assert (d.action, d.data) == ("send", COPY)
        sent_at = 1.0 + SETTLE
        s.feed(answers[-1], 2.0)
        assert s.tick(sent_at + BOUND - 0.01).action == "wait"
        d = s.tick(sent_at + BOUND)
        assert d.action == "abort"
        assert d.reason.startswith(f"expected {P.COPY_DESTINATION} (step 2 of 2) within "
                                   f"{BOUND:g} s"), d.reason


class TestReadState:
    def test_the_partial_echo_decides_nothing(self):
        assert S.read_state(PARTIAL, SWITCH, COPY[:-1].decode()) == ("", PARTIAL, True)

    def test_each_prefix_of_the_echo_decides_nothing(self):
        echo = COPY[:-1].decode()
        for n in range(1, len(echo) + 1):
            assert S.read_state(echo[:n], SWITCH, echo)[0] == "", echo[:n]

    def test_a_line_that_is_not_the_echo_s_start_is_still_an_unknown_prompt(self):
        """Controls: a line the echo does not begin with, and the same partial line with no
        echo to compare (a bare RETURN's step), read as an unknown prompt as before."""
        echo = COPY[:-1].decode()
        assert S.read_state("copy tftp://10.255.0.10/s6.cfg", SWITCH, echo)[0] == S.UNKNOWN
        assert S.read_state(PARTIAL + "x", SWITCH, echo)[0] == S.UNKNOWN
        assert S.read_state(PARTIAL, SWITCH, "")[0] == S.UNKNOWN

    def test_a_prompt_after_the_echo_still_decides(self):
        echo = COPY[:-1].decode()
        text = f"{echo}\r\nDestination filename [running-config]? "
        assert S.read_state(text, SWITCH, echo) == (
            P.COPY_DESTINATION, "Destination filename [running-config]?", True)
