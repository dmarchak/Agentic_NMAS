"""The Incidents row's status says why a person is needed as the incident's own status line
does (20e0a401: "It is the incident's status line, the Incidents row's status (now read for
every incident that needs a person ...)"; C4086, the operator, 2026-11-18: "give the Incidents
row, Needs attention and the incident page one shared source for 'why a person is needed'. The
kept failing test becomes the regression test"). Written failing by the skip-mode debt pass
(debt-tests-3, 2026-11-18) and kept uncommitted until the fix; Needs attention's row takes the
Incidents row's status (`attention`, `incidents_list.rows`).

Before the fix, measured in tests/test_fixit_section_v2.py's world: a lost stream nothing has tried reads, on
its page, "Mercury has no fix it runs by itself for a lost stream; ... The AI can investigate",
and on its row "Waiting for a person: its fix changes the configuration, so a person approves
it" (the row reads the section only when `state_of` is "needs_person" or a troubleshooting record
exists; a lost stream's `state_of` is neither); a plan Mercury refuses reads, on its page,
"Mercury refuses its fix as it stands: ...", and on its row "The AI's plan is ready: needs your
approval" (the row takes `why_person` for every needs-person state, past the section's own
overrides).
"""
from modules import incident_page as IP
from modules import incidents_list
from tests.test_fixit_section_v2 import NET, plant, proposed
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)


def both(iid: str) -> tuple:
    row = next(r for r in incidents_list.rows(NET)["rows"] if r["id"] == iid)
    pg = IP.page(NET, iid, attention={})
    assert row["state"] == pg["state"] == "needs_person", (row["state"], pg["state"])
    return row["status"], pg["fixit"]["status"]


def test_a_lost_stream_nothing_tried_says_the_same_reason_on_its_row(web):  # noqa: F811
    row, page = both(plant())
    assert row == page


def test_a_refused_plan_is_never_ready_for_approval_on_its_row(web, tmp_path):  # noqa: F811
    iid = plant()
    proposed(web, iid, tmp_path)
    row, page = both(iid)
    assert page.startswith("Mercury refuses its fix as it stands"), page
    # "plan is ready", not "ready": the page's refusal says "it already failed".
    assert "plan is ready" not in row and row == page, row
