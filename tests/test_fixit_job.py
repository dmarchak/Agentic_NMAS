"""AI troubleshooting's investigation as a job (the operator, 2026-11-14: "AI start returns at once,
runs as a job, pushes progress"; `modules/troubleshoot_job.py`, routes/fixit_v2.py `_ask`), through
tests/test_fixit_troubleshoot.py's world with the REAL job starter and the REAL gateway, only the
provider replaced by one that blocks until the test releases it. No device, no network, no live
AI call.

- The press returns before the model's call completes, the card in its running state.
- A reload while it runs draws the running state from the record, never a fresh button.
- A second press while it runs is refused naming the running one: one job, one paid call.
- Its end is announced (the invalidation path), and the card then draws the plan.
- A failure in the job is drawn in place: "Couldn't troubleshoot: <why>".
"""
import threading

import pytest

from modules.fixit import incident as F
from modules.nsot import capture_job
from tests.test_fixit_section_v2 import NET, attempt, incident, page, plant, post, section_of
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_fixit_troubleshoot import answer, fix
from tests.test_fixit_troubleshoot import ai  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)

#: The job starter as the app runs it (`web` replaces it with an inline one).
REAL_START = capture_job.start


@pytest.fixture
def blocked(ai, monkeypatch):
    """`ai` with the real job starter, and a provider that blocks each request until
    ``blocked.release`` is set; ``blocked.announced`` the announcements made."""
    from modules import invalidation
    from modules.ai import gateway

    monkeypatch.setattr("modules.nsot.capture_job.start", REAL_START)
    release, entered = threading.Event(), threading.Event()
    inner = gateway.anthropic_adapter.send

    def send(body, key):
        entered.set()
        assert release.wait(30), "the test never released the provider"
        return inner(body, key)
    monkeypatch.setattr(gateway.anthropic_adapter, "send", send)
    announced = []
    real_announce = invalidation.announce
    monkeypatch.setattr(invalidation, "announce",
                        lambda keys, by="", **kw: announced.append((tuple(keys), by))
                        or real_announce(keys, by=by, **kw))
    ai.release, ai.entered, ai.announced = release, entered, announced
    return ai


def jobs_of_kind():
    from modules import troubleshoot_job
    with capture_job._lock:
        return [j for j in capture_job._jobs.values() if j.get("kind") == troubleshoot_job.KIND]


def wait_all():
    for j in jobs_of_kind():
        assert capture_job.wait(j["job"], 30)


class TestTheJob:
    def test_the_press_returns_before_the_call_completes_and_a_reload_draws_it_running(
            self, blocked):
        iid = plant()
        attempt(blocked.client, subs=("101",))
        blocked.answer = answer(fix())
        before = len(jobs_of_kind())
        try:
            r = post(blocked.client, iid, "start", text="")
            assert r.status_code == 202, r.get_data(as_text=True)
            assert "The AI is investigating" in r.get_data(as_text=True)
            assert blocked.entered.wait(10), "the job reached the provider"
            assert blocked.sent == [], "the call has not completed: the provider is blocked"
            assert len(jobs_of_kind()) == before + 1, "one job for the press"
            _r, html = page(blocked.client, iid)
            sec = section_of(html)
            assert 'data-state="investigating"' in sec
            assert "The AI is investigating (started" in sec
            # The start as an instant the screen draws in the viewer's zone, never a count of
            # seconds that stays where it was drawn (C3801: "started 0 s ago", nine minutes on).
            assert "The AI is investigating (started at <time" in sec, sec[:800]
            assert " s ago)" not in sec
            assert "/fixit/start" not in sec, "never a fresh button while it runs"
            # A second press while it runs: refused, naming the running one; no second job.
            again = post(blocked.client, iid, "ask_again", text="")
            assert again.status_code == 409
            assert "already investigating" in again.get_data(as_text=True)
            assert len(jobs_of_kind()) == before + 1
        finally:
            blocked.release.set()
            wait_all()
        assert len(blocked.sent) == 1, "one paid call for the press"
        assert any("drift" in keys for keys, by in blocked.announced
                   if by == "fixit-investigation"), blocked.announced
        _r, html = page(blocked.client, iid)
        assert 'data-state="proposed"' in section_of(html)

    def test_a_failure_in_the_job_is_drawn_in_place(self, blocked, monkeypatch):
        from modules.ai import fixit_troubleshoot as AIT
        iid = plant()
        attempt(blocked.client, subs=("101",))

        def boom(*a, **kw):
            raise RuntimeError("the provider's answer could not be read")
        monkeypatch.setattr(AIT, "troubleshoot", boom)
        r = post(blocked.client, iid, "start", text="")
        assert r.status_code in (200, 202)
        wait_all()
        _r, html = page(blocked.client, iid)
        sec = section_of(html)
        assert "Couldn&#39;t troubleshoot: RuntimeError: the provider&#39;s answer could not be read" \
            in sec or "Couldn't troubleshoot: RuntimeError: the provider's answer could not be read" \
            in sec, sec[:600]
        lines = F.starts(incident(iid))["starts"]
        assert [ln["state"] for ln in lines] == ["started", "failed"]
        # And the AI may be asked again.
        assert "/fixit/ask_again" in sec


# ── In progress's finished row, and the card's push (the operator, 2026-11-15) ──────────────
#: "The status popover: one line per item ("Failed: request rejected. Details on the card"),
#: never overflowing. When a job ends, the incident card updates by push without a reload,
#: and the reason is stored and drawn after any refresh."

LONG = ("The AI was not asked: the press could not be tied to a verified person (a host "
        "script under the operator's grant, refused by the gateway); nothing was sent")


def finished_row(html: str) -> str:
    """The In progress list's finished row for AI troubleshooting."""
    import re
    rows = re.findall(r'<div class="ip-row">.*?</div>', html, re.S)
    got = [r for r in rows if "<strong>AI troubleshooting</strong>" in r]
    assert len(got) == 1, rows
    return got[0]


class TestTheFinishedRow:
    def test_a_failed_job_is_one_line_its_reason_kept_and_its_end_pushed(self, blocked,
                                                                         monkeypatch):
        from html import unescape

        from modules.ai import fixit_troubleshoot as AIT
        iid = plant()
        attempt(blocked.client, subs=("101",))

        def refused(*a, **kw):
            raise AIT.Refused(LONG)
        monkeypatch.setattr(AIT, "troubleshoot", refused)
        post(blocked.client, iid, "start", text="")
        wait_all()
        # Its end is announced on the incident pages' key, so the open card re-fetches.
        assert any("drift" in keys for keys, by in blocked.announced
                   if by == "fixit-investigation"), blocked.announced
        bar = blocked.client.get("/operations/in_flight", headers={"HX-Request": "true"})
        row = unescape(finished_row(bar.get_data(as_text=True)))
        assert "badge-danger" in row and ">failed<" in row
        line = row.split('class="ip-line">', 1)[1].split("</span>\n", 1)[0]
        assert "The AI was not asked. Details on the card" in line, line
        assert "the press could not be tied" not in line, \
            "one line: the whole reason is on its hover, never in the line"
        assert f'title="Failed: {LONG}"' in row, row
        # The reason is the record's, so a refresh draws it from the store, not this job.
        gone = [j["job"] for j in jobs_of_kind()]
        with capture_job._lock:
            for job_id in gone:
                capture_job._jobs.pop(job_id, None)
        _r, html = page(blocked.client, iid)
        assert "the press could not be tied to a verified person" in unescape(section_of(html))

    def test_a_plan_is_done_never_failed(self):
        from modules import troubleshoot_job as TJ
        o = TJ.outcome({"state": "done", "payload": {"state": "proposed", "words": "A plan"}})
        assert (o["level"], o["badge"]) == ("ok", "plan proposed"), o
        o = TJ.outcome({"state": "done", "payload": {"state": "gap", "words": "No operation"}})
        assert o["level"] == "warn", "an answer with no plan is partial, never green or red"
        o = TJ.outcome({"state": "failed", "error": "RuntimeError: the answer could not be "
                        "read because the provider sent half of it and then closed"})
        assert o["level"] == "danger"
        assert o["line"] == "The answer could not be read because the… Details on the card", \
            o["line"]
        assert o["full"].startswith("Failed: the answer could not be read"), \
            "the exception's type is left out of the hover too"

    def test_each_line_is_cut_with_an_ellipsis_by_the_stylesheet(self):
        import os
        import re
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "static", "css", "nmas-v2.css"), encoding="utf-8") as fh:
            css = fh.read()
        rule = re.search(r"\.ip-what \.ip-line, \.ip-what > small \{([^}]*)\}", css)
        assert rule, "the one-line rule"
        for decl in ("white-space: nowrap", "overflow: hidden", "text-overflow: ellipsis"):
            assert decl in rule.group(1), decl


# ── The bound (the operator, 2026-11-15: "Every AI job enforces its declared bound (240 s plus
# margin): past it, it ends itself, records why ("stopped: waited N s for <thing>"), releases
# anything it holds, and the card says so. Test: a job blocked on a fake read past the bound
# ends with that record.") ────────────────────────────────────────────────────────────────────

def _until(cond, bound_s=10.0):
    """Wait, bounded, for *cond*; whether it held (an Event's wait, never a sleep loop)."""
    pause = threading.Event()
    for _ in range(int(bound_s / 0.05)):
        if cond():
            return True
        pause.wait(0.05)
    return cond()


class TestTheBound:
    def test_a_job_blocked_past_its_bound_ends_itself_with_why_and_its_late_answer_is_dropped(
            self, blocked, monkeypatch):
        from html import unescape

        from modules import troubleshoot_job as TJ
        monkeypatch.setattr(TJ, "bound_s", lambda: 0.3)
        iid = plant()
        attempt(blocked.client, subs=("101",))
        blocked.answer = answer(fix())
        try:
            r = post(blocked.client, iid, "start", text="")
            assert r.status_code == 202, r.get_data(as_text=True)
            assert blocked.entered.wait(10), "the job reached its blocked step"
            job = max(jobs_of_kind(), key=lambda j: j["started_at"])["job"]
            assert _until(lambda: (capture_job.get(job) or {}).get("state") == "failed"), \
                "past its bound, the job ended itself while its step was still blocked"
            got = capture_job.get(job)
            assert got["error"].startswith("stopped: waited "), got["error"]
            assert "past its bound of 0 s" in got["error"], got["error"]
            assert "for asking the model (call 1" in got["error"], \
                "the record names the step it was waiting on: " + got["error"]
            lines = F.starts(incident(iid))["starts"]
            assert [ln["state"] for ln in lines] == ["started", "failed"], lines
            assert lines[-1]["words"].startswith("stopped: waited "), lines[-1]
            _r, html = page(blocked.client, iid)
            sec = unescape(section_of(html))
            assert "Couldn't troubleshoot: stopped: waited " in sec, sec[:800]
            assert "/fixit/ask_again" in sec, "and the AI may be asked again"
        finally:
            blocked.release.set()
            wait_all()
        # Released late, its answer changes nothing: the record and the card stay stopped.
        assert [ln["state"] for ln in F.starts(incident(iid))["starts"]] == ["started", "failed"]
        assert capture_job.get(job)["state"] == "failed"
        _r, html = page(blocked.client, iid)
        assert 'data-state="proposed"' not in section_of(html)

    def test_a_job_that_ends_within_its_bound_is_left_alone(self):
        from modules import troubleshoot_job as TJ
        job = capture_job.start("net", "x", "someone", lambda job_id: {"state": "gap"},
                                kind=TJ.KIND)
        assert capture_job.wait(job, 10)
        assert TJ._watch(job, "net", "inc-0", "person:1", "person",
                         wait=lambda s: None, bound=1) is False
        assert capture_job.get(job)["state"] == "done"
        assert not TJ.was_stopped(job)
