"""Who fixed an incident closed on a run verified on its device, and how long it took
(2f368606, `incident_page.fixed_how`; the operator, 2026-11-15: the closed list says "Fixed by
AI" (an AI plan approved by <person> at <instant>), "Fixed by Mercury: saved script" (<name>,
learned from an AI fix on <device>, approved by <person> when saved), or "Fixed by Mercury";
"lasted …; the fix took …"; no ", fixed and verified" on the title).

Through tests/test_fixit_catch_up.py's world: an incident planted by the incidents store's own
writer, its run's record written by `privileged.record`, closed by `incidents.close` with the
run as its ``fixed``. A saved script's entry is stood in for `saved_plans.scripts` (its store's
save path is the saved-fix tests'). Paid for docs/FAST_LANE_DEBT.md's row for 2f368606 ("Running
state and the closed list"), the debt pass, 2026-11-18.

Each test holds one purpose:
- a close on an AI plan's verified run is Fixed by AI, by the run's person at its start, on the
  row with how long it lasted and how long the fix took, its title with nothing appended;
- a close on a saved script's run is Fixed by Mercury: saved script, with where it was learned
  and who approved it;
- a close with no run is none of them.
"""
import time

from modules import display_names
from modules import incident_page as IP
from modules import incidents_list
from modules.heal import incidents
from modules.nsot import privileged, saved_plans
from tests.test_fixit_catch_up import DETECTED, planted, world  # noqa: F401
from tests.test_fixit_section_v2 import NET
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_fixit_troubleshoot import ai  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

RUN = "20261115T010203000000Z-" + "a" * 32
LEARNED = "20261114T010203000000Z-" + "b" * 32
PERSON = "op@example.com"


def closed_on_run(fixed_more: dict = None, actor: str = PERSON) -> str:
    """The can't-fix incident, its run started 100 s and verified 160 s after it was detected,
    closed with that run as its ``fixed``: its id."""
    iid = planted()["cant_fix"]
    privileged.record(NET, {"id": RUN, "device": "r3", "started_at": DETECTED + 100,
                            "finished_at": DETECTED + 160, "actor": actor})
    incidents.close(NET, iid, "its fix verified", now=DETECTED + 170,
                    fixed=dict({"run": RUN}, **(fixed_more or {})))
    return iid


def row_of(iid: str) -> dict:
    return next(r for r in incidents_list.rows(NET)["rows"] if r["id"] == iid)


def test_an_ai_plans_verified_run_is_fixed_by_ai_with_how_long(world):  # noqa: F811
    iid = closed_on_run()
    at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(DETECTED + 100))
    words = f"AI plan approved by {display_names.people(PERSON)} at {at}"
    how = IP.fixed_how(NET, IP.resolve(NET, iid)["incident"])
    assert (how["kind"], how["group"], how["label"], how["words"]) == (
        "ai", "fixed_ai", "Fixed by AI", words), how
    row = row_of(iid)
    assert (row["state"], row["group"], row["fixed_words"]) == ("fixed", "fixed_ai", words), row
    assert row["ttr"] == "lasted 2 min 40 s; the fix took 1 min", row["ttr"]
    assert not row["title"].endswith(", fixed and verified"), row["title"]
    assert "fixed and verified" not in IP.page(NET, iid, attention={})["title"]


def test_an_ai_plans_run_with_no_person_recorded_is_an_ai_plan(world):  # noqa: F811
    iid = closed_on_run(actor="")
    assert IP.fixed_how(NET, IP.resolve(NET, iid)["incident"])["words"] == "an AI plan"


def test_a_saved_scripts_verified_run_says_where_it_was_learned_and_who_approved_it(
        world, monkeypatch):  # noqa: F811
    privileged.record(NET, {"id": LEARNED, "device": "s2", "started_at": DETECTED - 900,
                            "finished_at": DETECTED - 840, "actor": PERSON})
    entry = {"key": "bpdu-recover", "name": "BPDU recover", "promoted_by": PERSON,
             "from_run": {"run": LEARNED}}
    monkeypatch.setattr(saved_plans, "scripts", lambda network: {"bpdu-recover": entry})
    iid = closed_on_run({"script": "bpdu-recover"})
    words = (f"BPDU recover, learned from an AI fix on s2, approved by "
             f"{display_names.people(PERSON)} when saved")
    how = IP.fixed_how(NET, IP.resolve(NET, iid)["incident"])
    assert (how["kind"], how["group"], how["label"], how["words"]) == (
        "script", "fixed_script", "Fixed by Mercury: saved script", words), how
    row = row_of(iid)
    assert (row["group"], row["fixed_words"]) == ("fixed_script", words), row


def test_a_close_with_no_run_is_none_of_them(world):  # noqa: F811
    iid = planted()["cant_fix"]
    incidents.close(NET, iid, "its symptom cleared", now=DETECTED + 170)
    assert IP.fixed_how(NET, IP.resolve(NET, iid)["incident"]) == {}
    row = row_of(iid)
    assert row["group"] not in ("fixed_ai", "fixed_script") and not row["fixed_words"], row
