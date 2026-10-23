"""C1593: the console session stops at IOS's first refusal, never typing past it
(modules/nsot/console_session.py: `refusal`, `refused_in`, the session's `_refused`).

On s5 (2026-10-23) the kick-start typed `ip address dhcp` under `interface Vlan1`, vIOS-L2
answered "% Invalid input detected at '^' marker." with the caret under `dhcp`, and the run
typed on (`no shutdown`, `line con 0`, `exec-timeout 15 0`, `end`) and recorded "done". The
refusal's text here is IOS's real wording: s1's own (tests/fixtures/operational/
s1__show_foobar.txt, a vIOS-L2 capture) and C1593's register row; the syslog lines are s5's
own (tests/fixtures/console/s5-pnp-stopped.txt) and IOS's message shape.

The set, precisely: a line whose first character after its indent is `%`, unless the profile's
`ignore` names it a message (a syslog message, `%FACILITY-SEVERITY-MNEMONIC:`; the key
generation's informational lines). In the 0-survivor blocking set (the operator, C1593)."""

import os

import pytest

from modules.nsot import console_profiles as P
from modules.nsot import console_session as S
from tests.test_console_session import PNP, answer, plan, session

SWITCH = P.load("cisco_ios_switch")
ROUTER = P.load("cisco_ios_router")
OPERATIONAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures",
                           "operational")


def _real_invalid_input() -> str:
    """s1's real refusal of an invalid command: the caret line, then IOS's words."""
    with open(os.path.join(OPERATIONAL, "s1__show_foobar.txt"), encoding="ascii") as fh:
        return fh.read()


INVALID = "% Invalid input detected at '^' marker."
#: Every refusal form, each as IOS words it (the last two IOS's other `%` forms: refused by
#: resemblance, which is the safe side).
REFUSALS = [
    INVALID,
    "% Incomplete command.",
    "% Ambiguous command:  \"s\"",
    "% Unknown command or computer name, or unable to find computer address",
    "%Error opening tftp://192.0.2.10/edge1.cfg (Timed out)",
    "%Error opening tftp://192.0.2.10/edge1.cfg (No such file or directory)",
    "% Bad IP address or host name",
    "% 192.0.2.12 overlaps with Vlan10",
    "%Warning: an unmeasured warning",
    "%",
]
#: Lines that begin with `%` (or carry one) and are NOT refusals: syslog messages (s5's own
#: PnP line, IOS's link and configuration messages, severities 0 and 7, a facility with a digit
#: and an underscore) and the key generation's two informational lines.
MESSAGES = [
    "*Oct 22 06:09:53.182: %PNP-6-PNP_DISCOVERY_STOPPED: PnP Discovery stopped (Config Wizard)",
    "%PNP-6-PNP_DISCOVERY_STOPPED: PnP Discovery stopped (Config Wizard)",
    "%LINK-3-UPDOWN: Interface GigabitEthernet0/1, changed state to up",
    "%LINEPROTO-5-UPDOWN: Line protocol on Interface Vlan1, changed state to up",
    "%SYS-5-CONFIG_I: Configured from console by console",
    "%SYS-0-EMERG: an emergency",
    "%C4K_EBM2-7-DEBUG: a debug message",
    "% The key modulus size is 2048 bits",
    "% Generating 2048 bit RSA keys, keys will be non-exportable...",
    "% Generating 2048 bit RSA keys, keys will be non-exportable...[OK]",
    "% Generating 2048 bit RSA keys, keys will be non-exportable...[OK] (elapsed time was 39 "
    "seconds)",
]
NOT_PERCENT = ["", "Switch#", "s5(config-if)#", "ip address dhcp", "                   ^",
               "Building configuration...", "100% done"]


@pytest.mark.parametrize("profile", [SWITCH, ROUTER], ids=["switch", "router"])
@pytest.mark.parametrize("line", REFUSALS)
def test_each_refusal_form_is_a_refusal_and_its_words_are_ios_s(profile, line):
    assert S.refusal(line, profile) == line
    assert S.refusal(f"  {line}  ", profile) == line, "the indent and trailing space dropped"


@pytest.mark.parametrize("profile", [SWITCH, ROUTER], ids=["switch", "router"])
@pytest.mark.parametrize("line", MESSAGES + NOT_PERCENT)
def test_a_message_or_a_line_without_a_leading_percent_is_not(profile, line):
    assert S.refusal(line, profile) == ""


def test_the_real_capture_s_refusal_is_found_with_the_line_before_it():
    text = "show foobar\n" + _real_invalid_input().replace("\r\n", "\n") + "\ns1#"
    assert S.refused_in(text, SWITCH) == (INVALID, "show foobar")


def test_the_first_refusal_is_named_and_the_caret_and_blank_lines_are_skipped():
    text = ("ip address dhcp\n                   ^\n\n" + INVALID + "\n% Incomplete command.\n"
            "s5(config-if)#")
    assert S.refused_in(text, SWITCH) == (INVALID, "ip address dhcp")


def test_a_refusal_with_nothing_before_it_names_no_line():
    assert S.refused_in("\n  ^\n" + INVALID + "\n", SWITCH) == (INVALID, "")


def test_a_refusal_on_the_line_still_arriving_is_found():
    """The capture as IOS left it, its refusal the last line with no break after it yet (the
    hand mutation of 2026-10-23: reading only complete lines survived)."""
    text = "show foobar\n" + _real_invalid_input().replace("\r\n", "\n")
    assert not text.endswith("\n")
    assert S.refused_in(text, SWITCH) == (INVALID, "show foobar")


@pytest.mark.parametrize("text", ["", "hostname s5\ns5(config)#",
                                  "\n".join(MESSAGES) + "\ns5#"])
def test_no_refusal_is_none(text):
    assert S.refused_in(text, SWITCH) == ("", "")


# ── The session stops at it ───────────────────────────────────────────────────────────────

def _typing(*lines, final=(P.PRIV_EXEC,)):
    """A session typing *lines* at the config prompt, its first already answered."""
    s = session(plan(*[(P.CONFIG, f"{line}\r".encode()) for line in lines], final=final))
    first = answer(s, b"s5(config-if)#", 1.0)
    assert first.action == "send" and first.data == f"{lines[0]}\r".encode()
    return s


def c1593_answer(line: str) -> bytes:
    """vIOS-L2's answer to *line* refused, as s5 printed it: the echo, the caret, IOS's words,
    a blank line, the prompt again."""
    return (f"{line}\r\n                   ^\r\n{INVALID}\r\n\r\ns5(config-if)#").encode()


def test_the_c1593_refusal_stops_the_session_with_nothing_more_typed():
    s = _typing(" ip address dhcp", " no shutdown")
    d = answer(s, c1593_answer(" ip address dhcp"), 2.0)
    assert (d.state, d.action, d.data) == (S.ABORTED, "abort", b"")
    assert d.reason == f"'ip address dhcp' was refused: {INVALID!r}"
    assert s.refused == {"line": "ip address dhcp", "words": INVALID,
                         "before": "ip address dhcp"}
    assert s.sent() == b" ip address dhcp\r"
    assert s.tick(9.0).action == "abort", "aborted is terminal"
    assert s.sent() == b" ip address dhcp\r"


def test_a_console_that_does_not_echo_names_no_line_before_the_refusal():
    """No echo, nothing before IOS's words: the reason names the line sent and stops there
    (the hand mutation of 2026-10-23: "(after '')" survived)."""
    s = _typing(" ip address dhcp", " no shutdown")
    d = answer(s, f"\r\n{INVALID}\r\ns5(config-if)#".encode(), 2.0)
    assert d.reason == f"'ip address dhcp' was refused: {INVALID!r}"
    assert s.refused == {"line": "ip address dhcp", "words": INVALID, "before": ""}


def test_the_same_answer_without_the_refusal_types_the_next_line():
    """Control: the prompt alone (a line taken) sends the next step."""
    s = _typing(" ip address 192.0.2.14 255.255.255.252", " no shutdown")
    d = answer(s, b" ip address 192.0.2.14 255.255.255.252\r\ns5(config-if)#", 2.0)
    assert (d.action, d.data) == ("send", b" no shutdown\r") and s.refused is None


@pytest.mark.parametrize("message", MESSAGES[1:7])
def test_a_syslog_line_in_the_answer_does_not_stop_it(message):
    s = _typing(" no shutdown", " exec-timeout 15 0")
    d = answer(s, f" no shutdown\r\n{message}\r\ns5(config-if)#".encode(), 2.0)
    assert (d.action, d.data) == ("send", b" exec-timeout 15 0\r")


def test_a_refusal_on_the_last_line_is_never_done():
    s = _typing(" ip address dhcp", final=(P.CONFIG,))
    d = answer(s, c1593_answer(" ip address dhcp"), 2.0)
    assert (d.state, d.action) == (S.ABORTED, "abort") and "was refused" in d.reason
    assert s.state == S.ABORTED


def test_a_refusal_followed_by_more_output_still_stops_it():
    s = _typing("ip default-gateway 192.0.2.13", "end")
    d = answer(s, ("ip default-gateway 192.0.2.13\r\n% Incomplete command.\r\nmore output\r\n"
                   "s5(config)#").encode(), 2.0)
    assert d.action == "abort"
    assert d.reason == "'ip default-gateway 192.0.2.13' was refused: '% Incomplete command.'"


def test_a_refusal_after_a_bare_return_names_the_line_before_it():
    """The copy's RETURN types nothing, so the refusal is named with what IOS printed before
    it (a line of the copied file, or its error)."""
    s = session(plan((P.COPY_DESTINATION, b"\r")))
    assert answer(s, b"Destination filename [running-config]? ", 1.0).data == b"\r"
    d = answer(s, ("\r\nAccessing tftp://192.0.2.10/edge1.cfg...\r\n%Error opening "
                   "tftp://192.0.2.10/edge1.cfg (Timed out)\r\ns5#").encode(), 2.0)
    assert d.action == "abort"
    assert d.reason == ("the console answered the last send with a refusal: '%Error opening "
                        "tftp://192.0.2.10/edge1.cfg (Timed out)' (after 'Accessing "
                        "tftp://192.0.2.10/edge1.cfg...')")
    assert s.refused["line"] == ""


def test_the_refusal_is_in_the_masked_transcript():
    s = _typing(" ip address dhcp", " no shutdown")
    answer(s, c1593_answer(" ip address dhcp"), 2.0)
    assert f">>> aborted: 'ip address dhcp' was refused: {INVALID!r}" in s.transcript()


def test_the_real_boot_text_holds_no_refusal():
    """The wake reads s5's real boot release: none of its lines is a refusal (a false stop
    there would end every survey)."""
    assert S.refused_in(PNP.decode("ascii").replace("\r\n", "\n"), SWITCH) == ("", "")


# ── No profile may hide a refusal ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("pattern", ["^%", "Invalid input", "^% ", "%Error", "Incomplete",
                                     "^%[A-Za-z]"])
def test_an_ignore_pattern_that_hides_a_refusal_is_refused(pattern):
    import copy
    data = copy.deepcopy(SWITCH.data)
    data["ignore"].append(pattern)
    with pytest.raises(P.ProfileError, match="matches IOS's refusal"):
        P.validate(data)


def test_the_shipped_profiles_hide_none():
    for name in P.shipped():
        prof = P.load(name)
        assert [r for r in P.REFUSAL_EXAMPLES if S.refusal(r, prof) != r] == []
