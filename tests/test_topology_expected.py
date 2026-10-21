"""A network's expected islands (`modules/topology_expected.py`; the operator, 2026-10-10): a
person declares a device cabled apart on purpose, with why, and the topology reader draws its
island as expected instead of warning.

- absent and unreadable are different states;
- a declaration needs a reason of a few words, and records who and when;
- withdrawing one that is not declared is refused naming it;
- an unreadable store refuses a write and is left as it was.
"""

import pytest

from modules import topology_expected as E


@pytest.fixture
def lst(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr("modules.nsot.listref.resolve",
                        lambda name: SimpleNamespace(name=name, data_dir=str(tmp_path)))
    return tmp_path


def test_absent_then_declared_then_withdrawn(lst):
    assert E.read("Lab") == {"state": "absent", "islands": {}, "error": ""}
    assert E.declare("Lab", "r6", "its own containerlab lab, cabled apart", "p@example.invalid")["ok"]
    got = E.read("Lab")
    assert got["state"] == "ok"
    assert got["islands"]["r6"]["reason"] == "its own containerlab lab, cabled apart"
    assert got["islands"]["r6"]["by"] == "p@example.invalid" and got["islands"]["r6"]["at"]
    assert E.withdraw("Lab", "r6", "p@example.invalid")["ok"]
    assert E.read("Lab")["islands"] == {}


def test_a_reason_of_a_few_words_is_required(lst):
    got = E.declare("Lab", "r6", "lab", "p@example.invalid")
    assert not got["ok"] and "say why r6 is apart on purpose" in got["error"]
    assert E.read("Lab")["state"] == "absent"


def test_withdrawing_what_is_not_declared_is_refused(lst):
    got = E.withdraw("Lab", "s1", "p@example.invalid")
    assert not got["ok"] and "s1 is not declared expected" in got["error"]


def test_a_weak_point_is_keyed_and_holds_what_it_cut_off(lst):
    """C1487: an accepted SPOF or only link is a declaration keyed by the weak point, holding
    what it cut off when accepted; Retire withdraws every declaration naming the device."""
    assert E.key_for("spof", "r4") == "spof:r4"
    assert E.key_for("bridge", a="r6", b="r4") == "bridge:r4~r6", "the ends sorted"
    assert E.declare("Lab", "bridge:r4~r6", "the course topology: one link to area 10",
                     "p@example.invalid", holds=["r7", "r6"])["ok"]
    assert E.read("Lab")["islands"]["bridge:r4~r6"]["holds"] == ["r6", "r7"]
    table = {"r6": {}, "spof:r6": {}, "bridge:r4~r6": {}, "bridge:r4~r60": {}, "spof:r60": {}}
    assert E.keys_naming(table, "r6") == ["bridge:r4~r6", "r6", "spof:r6"]
    assert E.words_for("bridge:r4~r6") == "the only link r4 ↔ r6"


def test_an_unreadable_store_refuses_a_write_and_keeps_its_bytes(lst):
    (lst / E.STORE).write_text("{not json")
    assert E.read("Lab")["state"] == "unreadable"
    got = E.declare("Lab", "r6", "its own containerlab lab", "p@example.invalid")
    assert not got["ok"] and "nothing was written" in got["error"]
    assert (lst / E.STORE).read_text() == "{not json"
