"""7.5's identity line on History (board HistoryIdentity, canvas version 112; C70's final step):
the commits in the window the filters draw, counted by their ``Actor-Verified:`` trailer, and a
filter keeping only those not signed in through the access proxy.

- each commit event carries its trailer's value ("" before the trailer existed);
- the count: verified, host login, not verified (an unknown value too), before verification;
- the page's four states: some not verified (with "Show only these"), all verified, a filter
  narrowing the window (said), no commit at all (never "0 of 0");
- the filter keeps the commits not verified, survives Show, and is undone by one link.
"""

import html as _h
import re

from modules import history_sources as HS
from tests.test_device_v2 import _get, lab  # noqa: F401 (the fixture)
from tests.test_history_one_timeline import _commit


def _text(page):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _h.unescape(page)))


def _plant(repo):
    """Five of the fleet's own commits (each touches a file, as History's read needs), one per
    Actor-Verified value, the last with none (before the trailer existed)."""
    import os
    os.makedirs(os.path.join(repo, "profile"), exist_ok=True)
    for i, how in enumerate(("access", "access", "host-shell", "none", "")):
        path = os.path.join("profile", f"identity-{i}.yml")
        with open(os.path.join(repo, path), "w", encoding="utf-8") as fh:
            fh.write(f"n: {i}\n")
        trailer = f"\nActor-Verified: {how}" if how else ""
        actor = f"\nActor: p{i}@example.com" if how else ""
        _commit(repo, f"intent: change {i}\n\nSource: intent{actor}{trailer}",
                path)


def test_each_value_is_counted_under_its_words():
    events = [{"verified": v} for v in ("access", "access", "host-shell", "none", "", "odd")] + \
        [{"kind": "restart"}]
    got = HS.identity(events)
    assert got["commits"] == 6 and got["verified"] == 2 and got["unverified"] == 4
    assert got["others"] == [("host login", 1), ("not verified", 2),
                             ("before verification was recorded", 1)]


def test_a_commit_drawn_as_two_events_is_counted_once():
    """A Save All's commit is a measurement and a baseline decision, one sha (the host's
    history, 2026-10-11: three such commits were counted as six)."""
    events = [{"verified": "none", "sha": "a" * 40, "kind": "measured"},
              {"verified": "none", "sha": "a" * 40, "kind": "decision"},
              {"verified": "access", "sha": "b" * 40, "kind": "intent"}]
    got = HS.identity(events)
    assert (got["commits"], got["verified"], got["unverified"]) == (2, 1, 1)


def test_a_commit_event_carries_its_trailer(lab):  # noqa: F811
    _plant(lab["repo"])
    from modules.nsot import listref
    h = HS.timeline(listref.resolve("Lab"), kinds=["commits"])
    mine = {e["what"]: e["verified"] for e in h["events"] if e["what"].startswith("intent: change")}
    assert mine == {"intent: change 0": "access", "intent: change 1": "access",
                    "intent: change 2": "host-shell", "intent: change 3": "none",
                    "intent: change 4": ""}, mine


def test_the_line_counts_the_window_and_offers_the_others(lab):  # noqa: F811
    _plant(lab["repo"])
    _r, page = _get(lab, "/v2/history")
    text = _text(page)
    m = re.search(r"(\d+) of (\d+) commits in this window carry a verified identity", text)
    assert m, text[:2000]
    assert int(m.group(1)) >= 2 and int(m.group(2)) >= 5
    assert "1 host login" in text
    assert "Show only these" in text
    assert "identity=unverified" in _h.unescape(page)


def test_the_filter_keeps_the_others_survives_show_and_is_undone(lab):  # noqa: F811
    _plant(lab["repo"])
    _r, page = _get(lab, "/v2/history?identity=unverified")
    text = _text(page)
    assert "intent: change 2" in text and "intent: change 3" in text and "intent: change 4" in text
    assert "intent: change 0" not in text and "intent: change 1" not in text
    assert re.search(r"\d+ commits in this window are not verified \(", text)
    assert '<input type="hidden" name="identity" value="unverified">' in page
    assert "Show every identity" in text


def test_a_narrowed_window_says_so_and_none_is_never_zero_of_zero(lab):  # noqa: F811
    _plant(lab["repo"])
    _r, page = _get(lab, "/v2/history?person=p0@example.com")
    assert "The one commit shown (person: p0@example.com) carries a verified identity." in \
        _text(page)
    _r, page = _get(lab, "/v2/history?person=nobody")
    text = _text(page)
    assert "No commit shown (person: nobody), so no identity to count." in text
    assert "0 of 0" not in text
