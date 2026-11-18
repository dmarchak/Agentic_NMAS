"""The Fixes page is one list in Mode order, Automatic first, then Last run newest first, a
deleted fix last, and its Source says who a fix came from (cf4018c2, the operator, 2026-11-17;
`modules/fix_page.py` `_sorted`, `_source_of`, `SOURCE_WORDS`). The debt pass, 2026-11-18
(docs/FAST_LANE_DEBT.md's row for cf4018c2).

The rows are planted as `listing` hands them to `_sorted` (``name``, ``how``, ``record``'s
``last``, ``deleted``); a written fix's Source is the person's with nothing read. The header's
sort kept in the browser is the page's script, not held here.
"""
from modules import fix_page as FP


def row(name, how, last="", deleted=False):
    return {"name": name, "how": how, "record": {"last": last}, "deleted": deleted}


def test_mode_order_then_last_run_newest_first_then_name_and_a_deleted_fix_last():
    rows = [row("bounce", "manual", "2026-11-17T09:00:00Z"),
            row("Old recovery", "automatic", "2026-11-17T12:00:00Z", deleted=True),
            row("Clear session", "matched", "2026-11-16T10:00:00Z"),
            row("BPDU recovery", "automatic", "2026-11-15T08:00:00Z"),
            row("re-add", "automatic", "2026-11-17T11:00:00Z"),
            row("audit", "matched", ""),
            row("apply ACL", "matched", "2026-11-16T10:00:00Z")]
    assert [r["name"] for r in FP._sorted(rows)] == [
        "re-add", "BPDU recovery",                # Automatic, newest run first
        "apply ACL", "Clear session", "audit",    # Matched: a tie by name, unrun last
        "bounce",                                 # Manual
        "Old recovery"]                           # deleted, whatever its mode


def test_a_written_fix_is_a_persons_and_the_three_sources_are_said():
    assert FP._source_of("Default", {"key": "fx-1", "written": True}) == "person"
    assert FP.SOURCE_WORDS == {"builtin": "Mercury built-in", "ai": "AI", "person": "Person"}
