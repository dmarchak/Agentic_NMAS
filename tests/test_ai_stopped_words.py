"""An investigation the AI loop stopped while its kept answer still asked for reads says so in
Mercury's words (93120b2f, `fixit_troubleshoot.stopped_words`; the operator, 2026-11-16: "The AI
stopped after N round(s) of reads: <why>; what it found so far: ...", never pass 1's "reading
first"). Paid for docs/FAST_LANE_DEBT.md's row for 93120b2f, the debt pass, 2026-11-18.

Each test holds one purpose:
- the words name the rounds, the reason and the hypotheses' claims, never the answer's own
  rationale, one round said in the singular;
- with no hypothesis it says none yet, with no reason recorded it says so, and with nothing
  stopped it says nothing.
"""
import types

from modules.ai import fixit_troubleshoot as FT


def answer(*claims, rationale="I am reading first: show telemetry connection all"):
    return types.SimpleNamespace(rationale=rationale, hypotheses=[
        types.SimpleNamespace(claim=c) for c in claims])


def test_it_names_the_rounds_the_reason_and_what_was_found_never_reading_first():
    got = FT.stopped_words({"rounds": 2, "why": "its reads reached their bound"},
                           answer("The collector holds r7's old session",
                                  "The  stream   restarted at 04:53"))
    assert got == ("The AI stopped after 2 rounds of reads: its reads reached their bound; "
                   "what it found so far: The collector holds r7's old session; The stream "
                   "restarted at 04:53."), got
    assert "reading first" not in got
    one = FT.stopped_words({"rounds": 1, "why": "the pass was refused"}, answer("A claim."))
    assert one.startswith("The AI stopped after 1 round of reads: the pass was refused;")


def test_none_found_no_reason_and_nothing_stopped():
    assert FT.stopped_words({"rounds": 3}, answer()) == (
        "The AI stopped after 3 rounds of reads: no reason recorded; what it found so far: "
        "no hypothesis yet.")
    assert FT.stopped_words({}, answer("A claim.")) == ""
    assert FT.stopped_words(None, answer("A claim.")) == ""
