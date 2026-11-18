"""Delete… and Restore… on a saved fix's page (a61bb071, C3849 pieces 2 to 4; the operator,
2026-11-16: a deleted fix is kept, never removed, recorded in History): `saved_plans.retire`
takes the right changing the fix takes (`change_right`) and a reason of `authorisation`'s
shape, refuses the AI, keeps the entry with ``retired`` and its ``retirements``, and every
reader leaves a deleted fix out (offered, fired, proposed, promoted or run on its standing
approval); saving onto a deleted fix is refused saying how to restore it.

The store through tests/test_saved_plans.py's `store` fixture. Paid for docs/FAST_LANE_DEBT.md's
row for a61bb071 ("C3849 pieces 2 to 4"), the debt pass, 2026-11-18.

Each test holds one purpose:
- deleted, the fix is kept but out of every reader, and Restore brings it back;
- the reason has authorisation's shape, or nothing is written;
- the AI deletes nothing, and a person without the fix's right is refused;
- a fix of another network, one deleted twice and one restored that is not deleted are refused;
- a deleted fix is never promoted, its standing approval stands for nothing, and it is never
  saved onto again;
- History draws each deletion and restore with who, the fix and the reason.
"""
import types

import pytest

from modules import history_sources as HS
from modules import identity
from modules.nsot import authorisation
from modules.nsot import saved_plans as S
from tests.test_saved_plans import NET, OTHER, PERSON, WHO, script, store  # noqa: F401

REASON = "taken back by its author"


def stored(key: str) -> dict:
    return S.read()["plans"][key]


def delete(e: dict, reason: str = REASON, **kw) -> dict:
    return S.retire(e["key"], network=NET, reason=reason, **dict(WHO, **kw))


def restore(e: dict, reason: str = "brought back after review", **kw) -> dict:
    return S.retire(e["key"], network=NET, reason=reason, restore=True, **dict(WHO, **kw))


def every_reader(key: str) -> dict:
    return {"fixes": key in S.fixes(NET), "scripts": key in S.scripts(NET),
            "actions": key in S.actions(NET), "deleted filter": key in S.fixes(NET, deleted=True)}


def test_deleted_it_is_kept_out_of_every_reader_and_restore_brings_it_back(store):  # noqa: F811
    e = script(store)
    assert every_reader(e["key"]) == {"fixes": True, "scripts": True, "actions": True,
                                      "deleted filter": True}
    delete(e)
    raw = stored(e["key"])
    assert (raw["retired"]["by"], raw["retired"]["reason"]) == (PERSON, REASON)
    assert [r["action"] for r in raw["retirements"]] == ["deleted"]
    assert raw["template"] and raw["track"] == [], "its record stays"
    assert every_reader(e["key"]) == {"fixes": False, "scripts": False, "actions": False,
                                      "deleted filter": True}
    restore(e)
    raw = stored(e["key"])
    assert "retired" not in raw
    assert [r["action"] for r in raw["retirements"]] == ["deleted", "restored"]
    assert every_reader(e["key"])["scripts"] is True


@pytest.mark.parametrize("reason", ["", "gone", "no more"])
def test_a_reason_of_too_few_words_or_characters_writes_nothing(store, reason):  # noqa: F811
    e = script(store)
    with pytest.raises(S.Refused) as got:
        delete(e, reason=reason)
    assert f"a reason is at least {authorisation.MIN_WORDS} words and " \
           f"{authorisation.MIN_CHARS} characters" in str(got.value)
    assert "retired" not in stored(e["key"]) and not stored(e["key"]).get("retirements")


def test_the_ai_deletes_nothing_and_a_person_needs_the_fixs_right(store):  # noqa: F811
    e = script(store)
    with identity.as_ai("assistant"), pytest.raises(S.Refused) as got:
        delete(e)
    assert "may not delete or restore a saved fix" in str(got.value)
    # A fix with a match takes the self-healing right (`change_right`).
    store["rights"].update(self_healing=[OTHER], admin=[PERSON])
    with pytest.raises(S.Refused):
        delete(e)
    assert "retired" not in stored(e["key"])
    store["rights"].update(self_healing=[PERSON])
    delete(e)
    assert stored(e["key"])["retired"]


def test_another_network_twice_and_a_restore_of_a_kept_fix_are_refused(store):  # noqa: F811
    e = script(store)
    with pytest.raises(S.Refused) as got:
        S.retire(e["key"], network="Branch", reason=REASON, **WHO)
    assert f"is a saved fix of {NET}, not of Branch" in str(got.value)
    with pytest.raises(S.Refused) as got:
        restore(e)
    assert "is not deleted: nothing to restore" in str(got.value)
    delete(e)
    with pytest.raises(S.Refused) as got:
        delete(e)
    assert f"is deleted already, by {PERSON}" in str(got.value)


def test_a_deleted_fix_is_never_promoted_run_on_its_approval_or_saved_onto(store):  # noqa: F811
    e = script(store, dry_run=True)
    delete(e)
    with pytest.raises(S.Refused) as got:
        S.promote(e["key"], **WHO)
    assert "it is deleted: Restore… on its page brings it back" in str(got.value)
    why = S.authority_refusal(e["key"], {"script": e["key"]}, NET)
    assert why.startswith(f"{e['name']} was deleted by {PERSON} at "), why
    with pytest.raises(S.Refused) as got:
        script(store, name=e["name"])
    assert "is saved already and deleted; Restore… on its page brings it back" in str(
        got.value)


def test_history_draws_each_deletion_and_restore(store):  # noqa: F811
    e = script(store)
    delete(e)
    restore(e)
    ctx = {"ref": types.SimpleNamespace(name=NET), "device": "", "limit": 50, "since": None,
           "until": None}
    rows = [r for r in HS.saved_fixes(ctx)["events"] if r["what"].endswith(("deleted",
                                                                             "restored"))]
    # Both in the same second here: History's order between them is by instant alone.
    assert sorted(r["what"] for r in rows) == [f"Saved fix “{e['name']}” deleted",
                                               f"Saved fix “{e['name']}” restored"]
    deleted = next(r for r in rows if r["what"].endswith("deleted"))
    assert (deleted["who"], deleted["detail"]) == (PERSON, REASON)
    assert HS.saved_fixes(dict(ctx, device="s1"))["events"] == [], "no device's History"
