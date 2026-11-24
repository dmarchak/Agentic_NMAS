"""C2820's survey, item 9 (rule 3: "departs (+1 -1)" read as a key): a device that differs from
its committed intent is said to DIFFER, its detail in words: a `+` line is in intent and not
on the device, a `-` line on the device and not in intent (`intent_match.said`), and an intent
state's words in a sentence that already says it differs (`intent_match.state_said`). Only
the trailer's exact shape is read: a sign inside other text (a time's offset) is never taken
for a count."""
import pytest

from modules.nsot import intent_match  # its `said`, `state_said` read in each test's body


@pytest.mark.parametrize("detail, words", [
    ("+1 -1", "1 line in intent not on the device, 1 line on the device not in intent"),
    ("-2", "2 lines on the device not in intent"),
    ("+3", "3 lines in intent not on the device"),
    ("1 reordered", "1 section in a different order"),
    ("+1 -13 2 reordered", "1 line in intent not on the device, 13 lines on the device not in "
                           "intent, 2 sections in a different order"),
])
def test_a_trailer_detail_is_said_in_words(detail, words):
    assert intent_match.said(detail) == words


@pytest.mark.parametrize("other", [
    "differs", "unknown (no committed intent)", "", "read at 2026-11-24T08:30-07:00",
    "+1 -1 at 09:00", "matches",
])
def test_any_other_shape_is_returned_as_it_is(other):
    assert intent_match.said(other) == other


def test_none_is_said_as_nothing():
    assert intent_match.said(None) == ""


@pytest.mark.parametrize("state, words", [
    ({"state": "departs", "words": "differs (+2 -2)"},
     "2 lines in intent not on the device, 2 lines on the device not in intent"),
    ({"state": "departs", "words": "differs (-1)"}, "1 line on the device not in intent"),
    ({"state": "at_intent", "words": "at intent"}, "at intent"),
    ({"state": "departs", "words": "its newest measurement does not stand (x); compared now: "
                                    "+1"},
     "its newest measurement does not stand (x); compared now: +1"),
    ({"state": "unknown"}, "unknown"),
])
def test_an_intent_state_is_said_without_saying_differs_twice(state, words):
    assert intent_match.state_said(state) == words


def test_the_devices_list_badge_is_short_and_its_hover_says_the_lines():
    from modules.device_list import _intent_of

    got = _intent_of("r4", "no: r4 (+2 -2)")
    assert got["words"] == "differs (+2 -2)" and "depart" not in got["words"]
    assert got["why"] == ("2 lines in intent not on the device, 2 lines on the device not in "
                          "intent")
