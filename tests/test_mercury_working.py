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
- a script's automatic run is Self-healing's, naming who approved it at save, and History names
  its run so, never as its promoter's own press.
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
        # The fix its job's page names (C4302: every run's page names it, `&fix=`) is found by
        # its key among the saved fixes (C4310: the list names the job's own fix).
        monkeypatch.setattr(SP, "fixes", lambda network=None, **k: {SCRIPT["key"]: dict(SCRIPT)})
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
                                page=f"/v2/incident/{iid}?list={NET}&fix={SCRIPT['key']}")
        try:
            assert attached.wait(60)
            assert SP.running_on(NET, iid) == {"job": job, "step": "starting",
                                               "key": SCRIPT["key"], "by": "policy"}
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

    def test_a_persons_run_is_named_on_the_list_by_its_own_fix_not_the_automatic_match(
            self, world, monkeypatch):  # noqa: F811
        # C4310: the list named the first Automatic fix that matched (`script_for`) and said
        # "Self-healing:" though a person pressed Run on another fix.
        from modules import op_progress
        from modules.nsot import saved_plans as SP

        pressed = {"key": "bpdu-any", "name": "BPDU guard recovery (any port)"}
        monkeypatch.setattr(capture_job, "start", REAL_START)
        monkeypatch.setattr(SP, "script_for", lambda network, found: (dict(SCRIPT), None))
        monkeypatch.setattr(SP, "fixes", lambda network=None, **k: {
            SCRIPT["key"]: dict(SCRIPT), pressed["key"]: dict(pressed)})
        iid = planted()["cant_fix"]
        steps, go, attached = [], threading.Event(), threading.Event()

        def work(_job):
            op_progress.attach((("hold", "Hold"), ("send", "Send"), ("verify", "Verify")),
                               steps)
            attached.set()
            go.wait(60)
            return {"state": "done", "words": ""}
        # A person's Run, as routes/fixit_v2.py starts it: its kind and its page naming the fix.
        job = capture_job.start(NET, f"{pressed['name']} on {iid}", "op@example.com", work,
                                kind=SP.JOB_KIND,
                                page=f"/v2/incident/{iid}?list={NET}&fix={pressed['key']}")
        try:
            assert attached.wait(60)
            row = row_of(iid)
            assert row["status"] == "Running BPDU guard recovery (any port) · starting", \
                row["status"]
            assert "Self-healing" not in row["status"] and SCRIPT["name"] not in row["status"]
        finally:
            go.set()
            assert capture_job.wait(job, 60)

    def test_an_automatic_run_is_self_healings_naming_who_approved_it(self):
        from modules import display_names
        from modules.nsot import saved_plans as SP

        assert SP.actor_words(SCRIPT) == (
            f"Self-healing, saved script BPDU recover (approved by "
            f"{display_names.people('op@example.com')} at save)")
        assert SP.actor_words({"name": "BPDU recover"}) == (
            "Self-healing, saved script BPDU recover")

    def test_history_names_a_scripts_run_by_self_healing_never_its_promoters_press(
            self, world, monkeypatch):  # noqa: F811
        import types

        from modules import history_sources as HS
        from modules.nsot import privileged, reads
        from modules.nsot import saved_plans as SP

        monkeypatch.setattr(SP, "scripts", lambda network: {SCRIPT["key"]: dict(SCRIPT)})
        mine, persons = reads.new_id(), reads.new_id()
        for rid, authority in ((mine, {"script": SCRIPT["key"]}), (persons, {})):
            privileged.record(NET, {"id": rid, "device": "r3", "key": "errdisable-recover",
                                    "state": "done", "actor": SCRIPT["promoted_by"],
                                    "started_at": DETECTED, "authority": authority,
                                    "reason": "the run"})
        ctx = {"ref": types.SimpleNamespace(name=NET, data_dir=""), "device": "", "limit": 50,
               "since": None, "until": None, "members": None}
        who = {e["record"][0][1]: e["who"] for e in HS.privileged(ctx)["events"]}
        assert who[mine] == SP.actor_words(SCRIPT), who
        assert who[persons] == SCRIPT["promoted_by"], "a person's own run names them"
