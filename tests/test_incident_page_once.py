"""The incident page says each fact once and draws a hold as what it is (the operator's review of
r7's page after Part A, 2026-11-15; R2, MERCURY_CHARTER "Two standing rules": "A guard or hold
working as designed is a plain line in the details, never a failure"; docs/UI_RULES.md, "Each
fact appears once").

- **C3728, a hold is never a red failure:** an incident whose decision a guard held (guard 4:
  its golden departs from intent) draws What Mercury has done's chip neutral
  (``data-outcome-level="hold"``, ``badge-neutral``), the hold's plain line (`bluf.hold_line`)
  on its hover; a heal that failed (rolled back) keeps its red chip: red only for what failed.
- **C3729, the evidence drawn once:** every planted page has at most one evidence home, under
  the bottom line (``#inc-evidence``), and none below What Mercury has done; an incident with
  members names them there.

Through the real app on the heal's lab (tests/test_incident_page.py's planted incidents and the
real decision held by guard 4, tests/test_heal_decide.py's `Fake` with its golden departing).
No device, no network.
"""
import re
from html import unescape

import pytest

from tests import test_incident_page as T
from tests import test_incident_titles as TT
from tests.test_heal_decide import GOLDEN, ROUTE4, Fake, settle
from tests.test_heal_decide import lab  # noqa: F401  (the fixture `client` builds on)
from tests.test_heal_policy import T0
from tests.test_heal_propose import measured  # noqa: F401  (a fixture)
from tests.test_incident_page import client, no_host_addresses  # noqa: F401  (fixtures)
from tests.test_sdn_connections import networks  # noqa: F401  (the fixture `lab` builds on)

NET = T.NET


def held():
    """A real decision held by guard 4: edge-b's golden departs from its intent."""
    from modules.heal import decide as DC

    settle(GOLDEN + ROUTE4, triggers=[T.CFG], claim=False)
    (d,) = DC.run(NET, now=T0, sources=Fake(GOLDEN + ROUTE4, state="departs"))["decided"]
    assert d["outcome"] == "held", d
    from modules.heal import decisions
    (kept,) = [x for x in decisions.decisions(NET) if x.get("incident") == d["incident"]]
    assert (kept.get("guard") or {}).get("guard") == 4, kept
    return d["incident"]


def chip(body: str) -> str:
    """What Mercury has done's outcome chip, as drawn in its summary (its entities read)."""
    done = body.split('id="inc-done"', 1)[1].split("</summary>", 1)[0]
    m = re.search(r'<span data-outcome-level="[^"]*">.*?</span></span>', done, re.S)
    return unescape(m.group(0)) if m else ""


def faults(c: str, *, hold: bool) -> list:
    """What is wrong with chip *c*: a hold drawn red, or without its plain line; a failure not
    drawn red."""
    out = []
    if hold and ("badge-danger" in c or 'data-outcome-level="hold"' not in c):
        out.append("a hold drawn as a failure")
    if hold and "won't write" not in c:
        out.append("a hold without its plain line on the hover")
    if not hold and "badge-danger" not in c:
        out.append("a failure not drawn red")
    return out


class TestAHoldIsNeverARedFailure:
    def test_guard_4_s_hold_is_neutral_with_its_plain_line(self, client):  # noqa: F811
        c = chip(T.page(client, held()))
        assert c and "Self-healing (dry run): held" in c, c
        assert "badge-neutral" in c and faults(c, hold=True) == [], c
        assert "Self-healing won't write to edge-b until its saved config matches intent" in c

    def test_a_heal_that_failed_keeps_its_red(self, client):  # noqa: F811
        c = chip(T.page(client, T.rolled_back()))
        assert c and faults(c, hold=False) == [], c

    def test_the_check_finds_a_hold_drawn_red(self):
        """The floor: the chip the review measured on r7's page."""
        red = ('<span data-outcome-level="danger"><span class="badge badge-danger">'
               "Self-healing (dry run): held</span></span>")
        assert faults(red, hold=True) == ["a hold drawn as a failure",
                                          "a hold without its plain line on the hover"]


def evidence_homes(body: str) -> list:
    """Every place the page draws its evidence: each element whose summary or heading is
    Evidence."""
    live = body.split('id="incident-live"', 1)[1]
    return re.findall(r"<(?:summary|h2)[^>]*>\s*Evidence\b", live)


class TestTheEvidenceIsDrawnOnce:
    @pytest.mark.parametrize("name", sorted(TT.PLANTS))
    def test_at_most_one_home_and_it_is_under_the_bottom_line(self, client, measured, name):  # noqa: F811
        body = T.page(client, TT.PLANTS[name]())
        homes = evidence_homes(body)
        assert len(homes) <= 1, (name, homes)
        if homes:
            live = body.split('id="incident-live"', 1)[1]
            assert live.index('id="inc-bluf"') < live.index('id="inc-evidence"') < \
                live.index('id="inc-done"'), name

    def test_members_are_named_in_the_one_home(self, client):  # noqa: F811
        iid, _old, _other = T.busy()
        body = T.page(client, iid)
        assert len(evidence_homes(body)) == 1
        ev = body.split('id="inc-evidence"', 1)[1].split("</details>", 1)[0]
        assert ">core-a</a>" in ev and "is the far end of its link" in ev

    def test_the_scan_finds_a_second_home(self):
        planted = ('<div id="incident-live"><details><summary>Evidence (2)</summary></details>'
                   '<details class="card inc-evidence"><summary>Evidence</summary></details>')
        assert len(evidence_homes(planted)) == 2
