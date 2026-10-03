"""C408: a device page's card names its one device, never the fleet's words (the operator,
2026-10-04: "Every device-page card names the device in the singular. Sweep all of them, plus
a check that a device-scoped card contains no 'devices you tick', 'N of N device(s)' or 'for
each'").

The check is the suite's guard (`tests/conftest.py`, `_device_cards_are_singular`): every card
`routes/device_v2.py` answers in any test is read for the class's phrases
(`tests/singular_cards.FLEET`), so the population is every card the suite draws. Here:
- the scanner finds each phrase, in the card only, and passes the singular sentences;
- the guard is wired: the device page's response wrapper is the guard's while a test runs;
- the states no device test draws in their fleet form: a job result built by the batch's own
  `operation_result` (its "N of N device(s) deployed") and a seed result by `seed_result`
  ("N of N device(s) seeded") are drawn singular by their device cards.
"""

import pytest

from tests.singular_cards import fleet_words


def _card(text):
    return f'<nav>for each device, 3 of 9 device(s)</nav><section id="device-op"><p>{text}</p></section>'


class TestTheScanner:
    @pytest.mark.parametrize("text, phrase", [
        ("Deploy to the devices you tick, merge-only.", "devices you tick"),
        ("Re-applying stored configuration to 1 of 1 device(s) you selected.", "1 of 1 device(s)"),
        ("0 of 1 can be deployed now, and for each, exactly the program shown is sent.",
         "for each"),
        ("Read 1 device(s) at once.", "device(s)"),
    ])
    def test_each_phrase_is_found(self, text, phrase):
        assert phrase in [w for w, _ctx in fleet_words(_card(text))]

    def test_singular_sentences_and_the_page_outside_the_card_pass(self):
        assert fleet_words(_card("Deploy r2's committed intent, merge-only: exactly these 3 "
                                 "line(s) are sent, in order.")) == []
        assert fleet_words("<p>3 of 9 device(s) for each</p>") == [], "no card, nothing read"


def test_the_guard_wraps_the_device_pages_answers():
    import routes.device_v2 as dv
    assert dv._strict.__name__ == "strict" and dv._strict.__module__.endswith("conftest"), \
        "the guard is not wired: no device card in the suite would be read"


class TestStatesNoDeviceTestDrawsInFleetForm:
    def test_a_batch_shaped_job_result_is_drawn_singular(self):
        from modules import device_actions
        from modules.preview_confirm import operation_result

        result = operation_result([{"device": "r2", "outcome": "deployed"}], {}, {}, "deploy")
        assert "1 of 1 device(s)" in result["happened"]["summary"], "the batch's own words"

        class Ref:
            name = "Lab"
        got = {"state": "done", "payload": {"result": result}}
        c = device_actions.deploy_job_card(Ref(), "r2", "job1", got)
        assert c["summary"].startswith("r2: ") and "device(s)" not in c["summary"], c["summary"]

    def test_a_batch_shaped_seed_result_is_drawn_singular(self):
        from modules import device_actions
        from modules.preview_confirm import seed_result

        result = seed_result([{"device": "r2", "outcome": "seeded", "entry": {}}], {"commit": "a" * 40})
        assert "1 of 1 device(s)" in result["happened"]["summary"], "the batch's own words"

        class Ref:
            name = "Lab"
        c = device_actions.seed_result_card(Ref(), "r2", result)
        assert c["summary"] == "r2: seeded: its intent is committed.", c["summary"]
