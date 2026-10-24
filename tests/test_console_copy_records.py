"""The static kick-start's COPY (C1594): what its verification says and what a failed copy
records (mutation run #30's survivors, `console_kickstart.verify_copy` and
`console_ztp._copy`).

- `verify_copy`'s words: a refusal with no line before it says only IOS's words, one with a
  line before it names that line; an answer with no ``[OK - N bytes]`` line shows its last
  three LINES whole (never its last three words);
- what a failed copy records, which the card and History read later: what was sent, its byte
  count, the console's transcript and the state it was found in; and a known secret planted
  in the copy's refusal masked in every field the copy writes (``copied``'s refusal and why,
  the session's ``refused``, the reason) and nowhere in the stored record;
- a kick-start whose program has no copy (a DHCP profile, no out-of-band onboarding) ends done
  with nothing sent after its read-back.

Over the fake console of tests/test_console_ztp.py (`World`); documentation addresses
(RFC 5737) throughout."""

import json
import socket

import pytest

from modules.nsot import console_kickstart as K
from modules.nsot import console_profiles as P
from modules.nsot import console_ztp as Z
from tests.test_console_session import PNP
from tests.test_console_ztp import (COPY, LIST, PARAMS, PLANNED, World, _recorded_as_sent,
                                    blank_answers, kick_answers)

SWITCH = P.load("cisco_ios_switch")
SERVER = "192.0.2.10"
URL = f"tftp://{SERVER}/edge1.cfg"
ERR = f"%Error opening {URL} (Timed out)"
#: A known secret (`redact_text`'s values) planted where the copy's refusal echoes it: IOS's
#: ``% Ambiguous command:`` names the copied file's line it refused, whole. Masking is by
#: token (`redact._TOKEN_CHAR`: a letter, a digit or `_` continues one), so the secret stands
#: as a token of its own there.
SECRET = "Hush8Token9"
PLANTED = {SECRET: "planted"}
AMBIGUOUS = f'% Ambiguous command:  "snmp-server location {SECRET}"'
MASKED_AMBIGUOUS = '% Ambiguous command:  "snmp-server location <redacted:planted>"'
OK_LINE = "[OK - 1203 bytes]"


@pytest.fixture
def world(tmp_path, monkeypatch):
    w = World(tmp_path, monkeypatch, socket.AF_INET)
    yield w
    w.server.close()


def _lines():
    from modules.nsot import console_survey as V
    return V.render_kickstart(SWITCH, dict(PARAMS, **PLANNED))


def _strings(node):
    """Every string in a parsed JSON document, keys included."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


# ── verify_copy's words ────────────────────────────────────────────────────────────────────

class TestWhatTheCopysVerificationSays:
    def test_a_refusal_with_no_line_before_it_says_only_ios_s_words(self):
        v = K.verify_copy(f"\r\n{ERR}\r\nedge1#", SWITCH)
        assert v == {"ok": False, "bytes": None, "refused": ERR,
                     "why": f"the copy's answer holds a refusal: {ERR!r}"}

    def test_a_refusal_after_a_line_names_that_line(self):
        v = K.verify_copy(f"\r\nAccessing {URL}...\r\n{ERR}\r\nedge1#", SWITCH)
        assert v["why"] == (f"the copy's answer holds a refusal: {ERR!r} "
                            f"(after 'Accessing {URL}...')")

    def test_an_answer_with_no_ok_line_shows_its_last_three_lines_whole(self):
        text = (f"\r\nAccessing {URL}...\r\nLoading edge1.cfg from {SERVER} (via Vlan10): !"
                "\r\n\r\nedge1#")
        v = K.verify_copy(text, SWITCH)
        shown = f"Accessing {URL}... / Loading edge1.cfg from {SERVER} (via Vlan10): ! / edge1#"
        assert v == {"ok": False, "bytes": None, "refused": "",
                     "why": f"the copy answered {shown!r}: it must print one '[OK - N bytes]' "
                            "line, and printed 0"}


# ── What a failed copy records ────────────────────────────────────────────────────────────

def _failed_copy(world, transfer: str, values=None):
    """A kick-start whose copy IOS answers, after the RETURN, with *transfer* and the prompt."""
    world.survey(greeting=PNP, answers=blank_answers())
    answers = kick_answers(_lines())
    answers[-1] = f"\r\n{transfer}\r\nedge1#".encode()
    rec = world.kick(answers, values=values)
    assert rec["outcome"] == "copy_failed", rec["reason"]
    return rec


def _secret_refused(world):
    """A copy that moved the file and whose IOS refused one of its lines, echoing the planted
    secret in its words."""
    return _failed_copy(world, f"Accessing {URL}...\r\n{OK_LINE}\r\n{AMBIGUOUS}",
                        values=PLANTED)


class TestWhatAFailedCopyRecords:
    def test_a_failed_copy_records_what_it_sent_and_saw(self, world):
        """The partial record is the evidence (`_finish` with the console)."""
        rec = _failed_copy(world, f"Accessing {URL}...\r\n{ERR}")
        assert {"sent", "bytes_written", "transcript", "attach_state"} <= set(rec), sorted(rec)
        assert world.received(1).endswith(f"{COPY}\r\r".encode())
        _recorded_as_sent(rec, world.received(1), ERR, P.USER_EXEC)

    def test_a_secret_in_the_copy_s_refusal_is_masked_in_copied_refused(self, world):
        rec = _secret_refused(world)
        assert rec["copied"]["refused"] == MASKED_AMBIGUOUS

    def test_a_secret_in_the_copy_s_refusal_is_masked_in_copied_why(self, world):
        rec = _secret_refused(world)
        assert rec["copied"]["why"] == (f"the copy's answer holds a refusal: "
                                        f"{MASKED_AMBIGUOUS!r} (after {OK_LINE!r})")

    def test_a_secret_in_the_copy_s_refusal_is_masked_in_the_session_s_refused(self, world):
        rec = _secret_refused(world)
        assert rec["refused"] == {"line": "", "words": MASKED_AMBIGUOUS, "before": OK_LINE}

    def test_a_secret_in_the_copy_s_refusal_is_masked_in_the_reason(self, world):
        rec = _secret_refused(world)
        assert SECRET not in rec["reason"] and MASKED_AMBIGUOUS in rec["reason"], rec["reason"]

    def test_a_secret_in_the_copy_s_refusal_is_nowhere_in_the_stored_record(self, world):
        rec = _secret_refused(world)
        stored = Z.get_run(LIST, rec["id"])
        assert stored["copied"]["refused"] == MASKED_AMBIGUOUS
        leaked = sorted(s for s in _strings(stored) if SECRET in s)
        assert leaked == [], leaked
        assert SECRET not in json.dumps(stored)


# ── A program with no copy ─────────────────────────────────────────────────────────────────

ROUTER_PARAMS = {"hostname": "edge1", "interface": "GigabitEthernet1"}


class TestAKickStartWithNoCopy:
    def test_a_dhcp_kick_start_with_no_onboarding_ends_done_with_no_copy_sent(self, world,
                                                                               monkeypatch):
        monkeypatch.setattr(Z, "_onboarding", lambda *a, **k: K._absent("none for the test"))
        world.survey(greeting=PNP, answers=blank_answers(), profile="cisco_ios_router")
        p = world.kick_preview(ROUTER_PARAMS)
        assert p["ok"] and p["copy"] == "", p
        answers = kick_answers(p["lines"])[:-2]          # the read-back's answers, no copy's
        rec = world.kick(answers, params=ROUTER_PARAMS)
        assert rec["outcome"] == "done", rec["reason"]
        assert "copied" not in rec
        reads = K.readback_plan(p["lines"])["reads"]
        assert world.received(1).endswith(f"{reads[-1]}\r".encode())
        assert b"copy " not in world.received(1)
