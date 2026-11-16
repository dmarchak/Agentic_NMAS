"""The incident page draws What to do in every state it can be in (the operator, 2026-11-16:
7cc49a1b's "Mercury working" state raised KeyError on GET /v2/incident/<id> while the AI
investigated): `incident_page._todo` answers for each of `incident_page.WHYS`, the one list of
whys `status` gives, so a state added without its words fails here, never on the page.
"""
import pytest

from modules import incident_page as IP


def _todo(why: str, state: str, item_state: str = "") -> dict:
    st = {"state": state, "why": why, "words": why}
    tl = {"decided": {"words": "declined by someone"}}
    # An item as `item_of` gives one: its row, its state and its first action (none here).
    item = {"row": {}, "state": item_state, "first": "", "level": ""}
    return IP._todo(st, "s1", tl, {"stop": {"n": 1}}, item)


@pytest.mark.parametrize("why", sorted(set(IP.WHYS)))
def test_every_why_draws_what_to_do(why):
    got = _todo(why, "needs_person" if why not in IP.RESOLVED else why)
    assert isinstance(got, dict) and str(got.get("words") or "").strip(), (why, got)


def test_mercury_working_is_a_state_and_draws():
    st = IP.working_status({"state": "needs_person", "why": "decided", "words": "x"},
                           "The AI is investigating", resolved=False)
    assert st["why"] == IP.MERCURY_WORKING and st["why"] in IP.WHYS
    assert "Mercury is working on it" in _todo(st["why"], st["state"])["words"]
