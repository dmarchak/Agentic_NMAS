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
