"""What a later AI troubleshoot call would be sent of an incident's record, with stable labels
(modules/fixit/payload.py; the operator's order of 2026-11-12, overnight item 6: "payloads use
stable labels"). No call is made: the parts are built and read here.

**No payload built here carries an "@" or a display name:** the planted actor is an email
address with a display name set (and its default name, the part before the "@"), and the run's
own words are planted to hold both, the one edit to a real run's record, written by the
operations' own writer (`carry`'s way). Each person is `display_names.label` of their identity
instead, the same label in every part and every request. On real records: the attempt is a
real Re-subscribe run whose verify reads no data.
"""
import json
import re

import pytest

from modules import display_names
from modules.fixit import payload as PL
from modules.heal import catalog
from tests.test_fixit_catalogue import inc
from tests.test_fixit_incident import LATER, T0, a_run
from tests.test_heal_resubscribe import ACTOR, NET, lab  # noqa: F401 (the fixture)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

NAME = "Riley Tester"
SECRET = "Wq9xZr7Lp2"


def words_of(text: str, word: str) -> bool:
    return re.search(r"(?<![\w.@-])" + re.escape(word) + r"(?![\w@-])", text) is not None


def plant_words(rec, words):
    """The one edit: the run's own words hold *words*, through the operations' own writer."""
    from modules.nsot import privileged
    got = privileged.get(NET, rec["id"])
    got["why"] = words
    privileged.record(NET, got)


@pytest.fixture
def named(lab):  # noqa: F811
    display_names.set_name(ACTOR, NAME, by=ACTOR, actor_verified="access")
    return lab


class TestStableLabels:
    def test_no_part_carries_an_at_sign_a_display_name_or_a_default_name(self, named):
        rec = a_run(T0, ok=False, subs=("101", "102"))
        plant_words(rec, f"re-subscribed; the stream did not come back; asked by {ACTOR}, "
                         f"whom {NAME} called back; snmp-server community {SECRET} RO")
        got = PL.pack(inc(), now=LATER)
        assert got["state"] == "ok"
        blob = json.dumps(got)
        assert "@" not in blob
        assert NAME not in blob and not words_of(blob, display_names.default(ACTOR))
        assert SECRET not in blob
        mark = display_names.label(ACTOR)
        assert re.fullmatch(r"person-[0-9a-f]{6}", mark)
        part = got["parts"]["tried:1"]
        assert part["approved_by"] == mark
        assert part["words"].startswith(f"re-subscribed; the stream did not come back; asked "
                                        f"by {mark}, whom {mark} called back; snmp-server "
                                        "community ")
        assert (part["operation"], part["outcome"], part["passed"], part["proposed_by"]) == (
            "telemetry-resubscribe", "not_back", False, "no proposal recorded")
        assert part["params"] == {"subs": ["101", "102"], "collector_step": False}

    def test_the_label_is_the_same_in_every_request_and_differs_by_person(self, named):
        a_run(T0, ok=False, subs=("101",))
        one = PL.pack(inc(), now=LATER)["parts"]["tried:1"]["approved_by"]
        two = PL.pack(inc(), now=LATER)["parts"]["tried:1"]["approved_by"]
        assert one == two == display_names.label(ACTOR.upper())
        assert display_names.label("other@example.invalid") != one

    def test_the_planted_words_are_found_without_the_labels(self, named):
        """The control: the same run read without `unnamed` holds the identity and the name,
        so the test above would see them."""
        from modules.fixit import incident as F
        rec = a_run(T0, ok=False, subs=("101",))
        plant_words(rec, f"asked by {ACTOR}, whom {NAME} called back")
        raw = json.dumps(F.attempts(inc(), now=LATER))
        assert ACTOR in raw and NAME in raw

    def test_an_attempt_by_no_one_carries_no_label(self, lab):  # noqa: F811
        assert PL.unnamed("nobody asked", ["", None]) == "nobody asked"


class TestTheCataloguePart:
    def test_it_is_the_catalog_each_operation_with_its_parameters_shapes(self, lab):  # noqa
        part = PL.pack(inc(), now=LATER)["parts"]["catalogue"]
        assert [p["operation"] for p in part] == sorted(catalog.CATALOG)
        for p in part:
            op = catalog.CATALOG[p["operation"]]
            assert p["words"] == op.words
            assert p["params"] == [{"name": x.name, "takes": x.takes} for x in op.params]
        assert "@" not in json.dumps(part)
