"""An open incident is Mercury working while the AI investigates it or a saved script runs on
it (7cc49a1b, `incident_page.working_status`; the operator, 2026-11-16: "Mercury working while a
fix or an AI investigation runs; 'Needs a person' only when a plan awaits approval or nothing
Mercury has can fix it"), on each surface that draws the incident's one state: its page, its
Incidents row, and Needs attention's can't-fix row, which stays linked to it while Mercury works
(`attention.FIX_UNDER_WAY`).

Through tests/test_fixit_catch_up.py's world (the real app, the stores' own writers, no device,
no AI call). Paid for docs/FAST_LANE_DEBT.md's rows for 7cc49a1b (the badge in each state) and
2f368606 (a saved script's run: `saved_plans.running_on`, its live step and its actor), the debt
pass, 2026-11-18.

Each test holds one purpose:
- the status is unchanged while nothing works, and while the incident is resolved;
- a can't-fix incident the AI investigates is Mercury working on its page, its Incidents row
  (the Mercury working group, busy) and keeps Needs attention's row linked to it;
- the same incident with nothing working says no Mercury working on either, and Needs
  attention's can't-fix row loses its link;
- a saved script's run on the incident (its job's page the incident's) is found with what it
  is doing now, from the run's own steps, only for that incident and network and while it runs,
  and its row and page say "Self-healing: fixing with saved script <name>" with that step;
- a script's automatic run is Self-healing's, naming who approved it at save.
"""
import threading

from modules import attention as A
from modules import incident_page as IP
from modules import incidents_list
from modules.fixit import incident as F
from modules.nsot import capture_job
from tests.test_fixit_catch_up import DETECTED, inc_of, planted, world  # noqa: F401
from tests.test_fixit_section_v2 import NET
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_fixit_troubleshoot import ai  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

NEEDS = {"state": "needs_person", "why": "decided", "words": "Needs a person"}
#: The real job starter, kept before `web` stands one in that runs the work in the caller's
#: thread: a saved script's run must be running while it is read.
REAL_START = capture_job.start


def row_of(iid: str) -> dict:
    got = incidents_list.rows(NET)
    assert not got.get("unreadable"), got
    return next(r for r in got["rows"] if r["id"] == iid)


def cant_fix_row(iid: str) -> dict:
    """Needs attention's can't-fix row about *iid*, linked to its page as the heal source links
    it."""
    return {"source": "heal", "kind": "cant_fix", "id": f"heal:{iid}", "key": iid,
            "incident_page": {"id": iid, "list": NET}}


def linked(iid: str) -> str:
    """The incident Needs attention's can't-fix row about *iid* links once held to the
    Incidents list's state (`attention._incidents_agree`), "" for none."""
    out = A._incidents_agree([cant_fix_row(iid)], NET, listed=incidents_list.rows(NET))
    (r,) = [r for r in out if r.get("kind") == "cant_fix"]
    return (r.get("incident_page") or {}).get("id") or ""


def investigating(iid: str) -> None:
    F.claim_start(inc_of(iid), f"decision:{iid}", trigger="auto", state="started",
                  now=__import__("time").time())


class TestTheStatus:
    def test_nothing_working_or_resolved_leaves_the_status_as_it_was(self):
        assert IP.working_status(NEEDS, "", resolved=False) == NEEDS
        assert IP.working_status(NEEDS, "The AI is investigating", resolved=True) == NEEDS
        got = IP.working_status(NEEDS, "The AI is investigating", resolved=False)
        assert (got["state"], got["why"], got["words"]) == (
            "open", IP.MERCURY_WORKING, "Mercury working")


class TestEachSurface:
    def test_the_ai_investigating_is_mercury_working_on_the_page_the_row_and_attention(
            self, world):  # noqa: F811
        iid = planted()["cant_fix"]
        investigating(iid)
        page = IP.page(NET, iid, attention={})
        assert (page["state"], page["state_words"]) == ("open", "Mercury working"), page["state"]
        row = row_of(iid)
        assert (row["state"], row["why"], row["state_words"]) == (
            "open", IP.MERCURY_WORKING, "Mercury working"), row
        assert row["group"] == "working" and row["busy"], row
        assert linked(iid) == iid

    def test_with_nothing_working_none_says_mercury_working_and_the_row_is_unlinked(
            self, world):  # noqa: F811
        iid = planted()["cant_fix"]
        page = IP.page(NET, iid, attention={})
        assert page["state_words"] != "Mercury working", page["state_words"]
        row = row_of(iid)
        assert row["why"] != IP.MERCURY_WORKING and row["state"] == "open", row
        assert (row["group"], row["busy"]) == ("watching", False), row
        # Open with nobody needed and no fix under way: the can't-fix row loses its link.
        assert linked(iid) == ""


SCRIPT = {"key": "bpdu-recover", "name": "BPDU recover", "promoted_by": "op@example.com"}


class TestASavedScriptsRun:
    """A run as `saved_plans._run_as_job` starts one (a `capture_job` of `JOB_KIND`, its page
    the incident's), its steps recorded through `op_progress.attach` as the runner records
    them; the matching script stood in for `saved_plans.script_for` (the match is the saved-fix
    tests'; the card names the script from its own offer, `fix_offers`, not stood in here)."""

    def test_it_is_found_with_its_live_step_and_said_on_the_row_and_the_page(
            self, world, monkeypatch):  # noqa: F811
        from modules import op_progress
        from modules.nsot import saved_plans as SP

        monkeypatch.setattr(capture_job, "start", REAL_START)
        monkeypatch.setattr(SP, "script_for", lambda network, found: (dict(SCRIPT), None))
        iid = planted()["cant_fix"]
        steps, go, attached = [], threading.Event(), threading.Event()

        def work(_job):
            op_progress.attach((("hold", "Hold"), ("send", "Send"), ("verify", "Verify")),
                               steps)
            attached.set()
            go.wait(60)
            return {"state": "done", "words": ""}
        job = capture_job.start(NET, SP.actor_words(SCRIPT), SCRIPT["promoted_by"], work,
                                kind=SP.JOB_KIND, actor_kind="policy",
                                page=f"/v2/incident/{iid}?list={NET}")
        try:
            assert attached.wait(60)
            assert SP.running_on(NET, iid) == {"job": job, "step": "starting"}
            steps.append({"step": "hold", "result": "ok"})
            assert SP.running_on(NET, iid)["step"] == "checking preconditions"
            steps.append({"step": "send", "result": "ok"})
            assert SP.running_on(NET, iid)["step"] == "verifying"
            assert SP.running_on(NET, "hi-000000000000") == {}
            assert SP.running_on("Another", iid) == {}
            row = row_of(iid)
            assert row["status"] == ("Self-healing: fixing with saved script BPDU recover · "
                                     "verifying"), row["status"]
            assert (row["group"], row["busy"]) == ("working", True), row
            page = IP.page(NET, iid, attention={})
            assert page["state_words"] == "Mercury working", page["state_words"]
            assert page["fixit"]["working"].startswith("Self-healing: fixing with saved script")
            assert page["fixit"]["working_step"] == "verifying"
        finally:
            go.set()
            assert capture_job.wait(job, 60)
        assert SP.running_on(NET, iid) == {}, "a run that ended is no longer running"

    def test_an_automatic_run_is_self_healings_naming_who_approved_it(self):
        from modules import display_names
        from modules.nsot import saved_plans as SP

        assert SP.actor_words(SCRIPT) == (
            f"Self-healing, saved script BPDU recover (approved by "
            f"{display_names.people('op@example.com')} at save)")
        assert SP.actor_words({"name": "BPDU recover"}) == (
            "Self-healing, saved script BPDU recover")
