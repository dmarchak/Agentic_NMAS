"""Troubleshooting › Fixes and a fix's page (a61bb071, C3849 pieces 2 to 4; the operator,
2026-11-16): the list's filters and counts (`fix_page.listing`: a deleted fix only under its
filter, a search by name), and what each check of a fix reads and cannot prove on a down port,
from its own module's declaration (`errdisable.SAYS` through `fix_page._check`).

The store through tests/test_saved_plans.py's `store` fixture (a verified run saved as a fix by
its own writer). Paid for docs/FAST_LANE_DEBT.md's row for a61bb071 ("C3849 pieces 2 to 4"),
the debt pass, 2026-11-18.

Each test holds one purpose:
- the list counts the saved and built-in fixes, shows a deleted one only under the Deleted
  filter and counts it, and a search keeps the fixes it names;
- a check says what its module declares for the fix's own cause, every cause labelled for a fix
  that takes more than one, and a check its module declares nothing of says its own read.
"""
from modules import fix_page as FP
from modules.heal import errdisable as ED
from modules.nsot import command_plan as CP
from modules.nsot import saved_plans as S
from tests.test_saved_plans import NET, WHO, script, store  # noqa: F401

CLEARED = {"name": "The cause has cleared", "expect": "errdisable.cause_cleared"}


def keys(listing: dict) -> set:
    return {r["key"] for r in listing["rows"]}


def test_the_list_counts_and_filters_and_a_deleted_fix_shows_only_under_its_filter(
        store):  # noqa: F811
    kept = script(store)
    gone = script(store, run_id=store["run"](), name="Port security recovery")
    S.retire(gone["key"], network=NET, reason="replaced by the BPDU fix", **WHO)
    every = FP.listing(NET)
    assert (every["saved"], every["deleted"]) == (1, 1), every
    assert every["total"] == every["saved"] + every["built"] and every["built"] >= 1
    assert kept["key"] in keys(every) and gone["key"] not in keys(every)
    # The groups are not carried since 67b90db3; ``shown`` is their count: the default list
    # holds the saved and the built-in fixes, never the deleted.
    assert every["shown"] == every["saved"] + every["built"], every["shown"]
    deleted = FP.listing(NET, kind="deleted")
    assert keys(deleted) == {gone["key"]}
    assert deleted["shown"] == 1, deleted["shown"]
    saved = FP.listing(NET, kind="saved")
    assert keys(saved) == {kept["key"]}
    found = FP.listing(NET, q="bpdu GUARD")
    assert kept["key"] in keys(found) and gone["key"] not in keys(found)
    assert FP.listing(NET, q="no fix is named this")["rows"] == []


def test_a_check_says_what_its_module_declares_for_the_fixs_own_cause(store):  # noqa: F811
    e = script(store)
    f = S.fixes(NET)[e["key"]]
    t = CP.parse(S.read()["plans"][e["key"]]["template"])
    said = ED.SAYS["check_cause_cleared"]["bpduguard"]
    got = FP._check(f, t, CLEARED)
    assert got == {"name": CLEARED["name"], "reads": said["reads"],
                   "limits": [{"label": "", "words": said["limit"]}]}, got


def test_a_fix_for_either_cause_labels_each_and_an_undeclared_check_says_its_read(
        store):  # noqa: F811
    e = script(store)
    t = CP.parse(S.read()["plans"][e["key"]]["template"])
    got = FP._check({}, t, CLEARED)
    labels = [x["label"] for x in got["limits"]]
    assert labels == [ED.CAUSES["bpduguard"], ED.CAUSES["psecure-violation"]], labels
    assert got["reads"].startswith(f"{ED.CAUSES['bpduguard']}: ")
    assert f"; {ED.CAUSES['psecure-violation']}: " in got["reads"]
    plain = {"name": "The port reads connected", "read": "show interfaces status",
             "expect": "errdisable.port_connected"}
    assert FP._check({}, t, plain) == {"name": plain["name"], "reads": "show interfaces status",
                                       "limits": []}
    recovery = {"name": "The switch does not recover the cause itself",
                "read": "show errdisable recovery", "expect": "errdisable.not_recovering_itself"}
    assert FP._check({}, t, recovery)["reads"] == ED.SAYS["check_no_recovery"]["reads"]
