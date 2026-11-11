"""A run that ended always shows its outcome (the operator, 2026-11-11, after a re-subscribe
of r7 that "disappeared from 'running' with NO outcome shown, the row unchanged, and nothing
under 'Finished, not opened yet'"): on its card, the outcome first and never green over a
partial or a failure, with the steps taken under it; and one entry under Finished for the
person who started it, until they open it. Through the real app, on the re-subscribe's lab
(tests/test_heal_resubscribe.py: r2's real configuration on a box, its real intent) and the
heal's (tests/test_heal_act.py: the real decision and the real act over its fakes). No device,
no network.

- **The steps taken** (`run_stepper.from_record`): a run's own recorded steps against the ones
  it declared: a failed step leads and nothing after it is drawn done; a result nobody named
  is amber, never green; a step never recorded is pending while the run goes on, and not
  reached or not needed once it ended; a step's reads are drawn from its ``reads`` where it
  carries them and from its ``checks`` where it does not.
- **A re-subscribe:** its job names its device and its card, so the chip lists its outcome and
  the device's page reopens its card; with the job forgotten (Mercury restarted) the RECORD
  lists it for the person who started it, the page reopens it from the record, and the card on
  the lost stream's row leads with it.
- **A heal:** the same for a run the policy started: its outcome and steps on the device's
  page and under Finished, for every person until each opens it.
- **A can't-fix** is a decision, not a run: its steps taken are on its Needs attention row and
  in its notice.
"""
import re

import pytest

import modules.heal.resubscribe  # noqa: F401  (the operation the cards are about)
from tests.conftest import TEST_PERSON
from tests.test_heal_act import SETTER, FakeAct, decided
from tests.test_heal_decide import GOLDEN, ROUTE4
from tests.test_heal_decide import lab as heal_lab  # noqa: F401
from tests.test_heal_resubscribe import ABSENT, NET, Box, Src, seq
from tests.test_heal_resubscribe import lab as resub_lab  # noqa: F401
from tests.test_heal_resubscribe_v2 import BASE, HX, card, press
from tests.test_heal_policy import T0
from tests.test_sdn_connections import networks  # noqa: F401 (the labs build on it)

DECLARED = (("plan", "Plan"), ("send", "Send"), ("wait", "Wait"), ("verify", "Verify"),
            ("rollback", "Roll back"), ("record", "Record"))


def step(key, result, words="", at="2026-11-11T16:38:00Z", **more):
    return dict({"step": key, "result": result, "words": words, "at": at}, **more)


def states(got):
    return {s["key"]: s["state"] for s in got["steps"]}


class TestTheStepsTaken:
    """`run_stepper.from_record`: what a run recorded, against what it declared."""

    def test_a_failed_step_leads_and_nothing_past_it_is_done(self):
        from modules import run_stepper as RS
        got = RS.from_record(DECLARED, [
            step("plan", "ok"), step("send", "ok"), step("wait", "ok"),
            step("verify", "failed", "the stream did not come back"),
            step("record", "ok", "recorded")], ended=True, conditional=("rollback",))
        assert states(got) == {"plan": "done", "send": "done", "wait": "done",
                               "verify": "failed", "rollback": "skipped", "record": "done"}
        assert (got["lead"]["key"], got["lead"]["why"]) == (
            "verify", ["the stream did not come back"])
        c = RS.record_card("r2", "Steps", [got], ended=True, level="danger")
        assert c["rows"][0]["group"] == "failed", "the row is never green over a failure"
        assert [t["state_words"] for t in c["trail"]] == [
            "done", "done", "done", "failed", "done"], "every step as it was recorded"

    def test_a_good_outcome_s_level_still_caps_the_row(self):
        from modules import run_stepper as RS
        got = RS.from_record(DECLARED, [step("plan", "ok"), step("record", "ok")], ended=True)
        assert RS.record_card("r2", "Steps", [got], ended=True, level="warn")["rows"][0][
            "group"] == "partial", "an amber outcome is never a green row"
        assert RS.record_card("r2", "Steps", [got], ended=True, level="ok")["rows"][0][
            "group"] == "done"

    def test_a_result_nobody_named_is_amber_never_green(self):
        from modules import run_stepper as RS
        got = RS.from_record(DECLARED, [step("plan", "looks-fine")], ended=True)
        assert states(got)["plan"] == "partial"
        assert RS.result_state("healed") == "partial", "an operation's word, unnamed"
        assert RS.result_state("healed", good=("healed",)) == "done"
        assert RS.result_state("cant_fix", bad=("cant_fix",)) == "failed"

    def test_a_step_never_recorded_is_pending_then_not_reached(self):
        from modules import run_stepper as RS
        steps = [step("plan", "ok"), step("send", "refused", "the session did not open")]
        going = RS.from_record(DECLARED, steps[:1], ended=False)
        assert states(going) == {"plan": "done", "send": "waiting", "wait": "waiting",
                                 "verify": "waiting", "rollback": "waiting",
                                 "record": "waiting"}
        assert going["steps"][1]["state_words"] == "pending"
        ended = RS.from_record(DECLARED, steps + [step("record", "ok")], ended=True,
                               conditional=("rollback",))
        assert states(ended) == {"plan": "done", "send": "failed", "wait": "not_reached",
                                 "verify": "not_reached", "rollback": "skipped",
                                 "record": "done"}

    def test_a_run_that_ended_inside_a_step_failed_there(self):
        from modules import run_stepper as RS
        got = RS.from_record(DECLARED, [step("plan", "ok"), step("send", "running", "sending")],
                             ended=True)
        assert states(got)["send"] == "failed"
        assert got["lead"]["why"] == ["sending. The run ended in this step"]

    def test_a_step_s_reads_are_drawn_where_it_carries_them_and_its_checks_where_not(self):
        from modules import run_stepper as RS
        checks = {"device": {"state": "pass", "words": "Connected on a new connection"},
                  "stream": {"state": "fail", "words": "no series"},
                  "collector": {"state": "cant_tell", "words": "not read"}}
        old = RS.from_record(DECLARED, [step("verify", "failed", "no series", checks=checks)],
                             ended=True)
        # An ended step that did not pass: the lead says why, once; what it read sits under
        # that step in the list (the operator, 2026-11-11: "its checks only under the failed
        # step, collapsed").
        assert old["lead"]["why"] == ["no series"] and old["lead"]["lines"] == []
        (took,) = old["trail"]
        assert [(ln["what"], ln["state_words"]) for ln in took["checks"]] == [
            ("device", "pass"), ("stream", "fail"), ("collector", "unreadable")]
        assert took["said"] == "", "the lead says it: it is not said again in the list"
        reads = [{"at": "2026-11-11T16:40:00Z", "command": "show telemetry ietf subscription "
                  "101 receiver", "result": "fail", "words": "Connecting", "read_id": "r-1"},
                 {"at": "2026-11-11T16:40:10Z", "command": "show telemetry ietf subscription "
                  "101 receiver", "result": "pass", "words": "Connected", "read_id": "r-2"}]
        new = RS.from_record(DECLARED, [step("verify", "running", reads=reads, checks=checks)],
                             ended=False)
        # While it runs: the NEWEST read of each command, then one line saying its reads;
        # every read is one level down, newest first (tests/test_run_progress.py holds the
        # compact drawing of a 32- and a 90-read verify).
        assert [(ln["state_words"], ln["words"], ln["at"]) for ln in new["lead"]["lines"]] == [
            ("pass", "Connected", "2026-11-11T16:40:10Z"),
            ("", "2 reads of `show telemetry ietf subscription 101 receiver`, about 10 s "
                 "apart: 1 pass, 1 fail; the last: Connected", "")]
        (more,) = new["lead"]["more"]
        assert more["title"] == "The 2 reads"
        assert [r["words"] for r in more["reads"]] == ["Connected", "Connecting"], \
            "each read as it was appended, newest first"

    def test_a_wait_carries_its_declared_length_and_when_it_began(self):
        from modules import run_stepper as RS
        got = RS.from_record(DECLARED, [step("plan", "ok"), step(
            "wait", "running", "after the last removal", began="2026-11-11T16:38:10Z",
            wait_s=10)], ended=False, now=RS._epoch("2026-11-11T16:38:14Z"))
        assert got["lead"]["wait"] == {"began": "2026-11-11T16:38:10Z", "length_s": 10,
                                       "bound": False, "words": "6 s left of 10 s"}
        assert RS.current_words(DECLARED, [step("plan", "ok"), step("wait", "running")]) == (
            "Wait · step 3 of 6")


# ── A re-subscribe ──────────────────────────────────────────────────────────────────────────

@pytest.fixture
def resub(resub_lab, monkeypatch):  # noqa: F811
    """The real app's client over the re-subscribe's lab, the REAL job starter, one network,
    and a person looking whom the test names (the one who confirms, unless it says)."""
    import app as A
    from modules.nsot import capture_job

    state = {"src": Src(), "jobs": [], "viewer": TEST_PERSON}
    monkeypatch.setattr("modules.heal.resubscribe.Sources", lambda net, **kw: state["src"])
    real = capture_job.start

    def start(*a, **kw):
        state["jobs"].append(real(*a, **kw))
        return state["jobs"][-1]
    monkeypatch.setattr("modules.nsot.capture_job.start", start)
    monkeypatch.setattr("modules.integration_groups.network_names", lambda: [NET])
    monkeypatch.setattr("routes.operations.viewer_key", lambda: state["viewer"])
    monkeypatch.setattr(capture_job, "_jobs", {})
    A.app.config["TESTING"] = True
    c = A.app.test_client()
    c.state = state
    yield c
    for job in state["jobs"]:                         # one a test forgot has ended already
        assert capture_job.get(job) is None or capture_job.wait(job, 30), \
            f"job {job} did not end within 30 s"


def run_one(c, src, subs=("101",)):
    """One re-subscribe confirmed on the card and run to its end by the real job: its id."""
    from modules.nsot import capture_job
    c.state["src"] = src
    _r, html = card(c, subs=",".join(subs))
    r = press(c, html, subs=subs)
    assert r.status_code == 200, r.get_data(as_text=True)
    job = c.state["jobs"][-1]
    assert capture_job.wait(job, 30)
    return job


def bar(c):
    r = c.get("/operations/in_flight", headers=HX)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def page(c, device="r2", network=NET):
    html = c.get(f"/v2/device/{device}?list={network}").get_data(as_text=True)
    return html[html.index('id="tab-body"'):]


def restarted(monkeypatch):
    """Mercury restarted: no job is held (and each test's run is its own, so nothing of it
    was remembered as opened before)."""
    from modules.nsot import capture_job
    monkeypatch.setattr(capture_job, "_jobs", {})


def not_back():
    return Src(series=seq([ABSENT]))


class TestAReSubscribesOutcome:
    def test_a_failed_run_is_listed_under_finished_and_reopened_with_its_steps(self, resub):
        from modules.nsot import privileged
        run_one(resub, not_back())
        rec = privileged.runs(NET)["runs"][0]
        assert (rec["state"], rec["outcome"]) == ("failed", "not_back")
        html = bar(resub)
        assert 'class="ip-chip ip-danger"' in html and "In progress: 1 failed" in html
        assert "Finished, not opened yet · 1" in html
        assert "<strong>r2</strong> · Re-subscribe telemetry" in html
        assert "re-subscribed; the stream did not come back" in html
        assert f"{len(rec['steps'])} steps recorded" in html and "Open the result" in html
        assert "Running now" not in html, "and it is no longer running"
        body = page(resub)
        assert "op-card op-danger" in body and "Finished at" in body
        assert "Re-subscribed; the stream did not come back:" in body
        assert "notice-danger" in body and "notice-muted" not in body
        assert f"The steps taken · {len(rec['steps'])}" in body
        assert 'run-lead run-lead-failed" data-lead="verify"' in body, "the failed step leads"
        assert "run-row-failed" in body and "run-row-done" not in body, "nothing green"
        assert "Preview a re-subscribe again…" in body, "the next action"
        assert "ip-chip" not in bar(resub), "opened: the chip lets it go"

    def test_two_subscriptions_not_back_each_verify_leads_with_its_own_reads(self, resub):
        """The operator's run of 2026-11-11 (two subscriptions, neither stream back): twelve
        steps, two verifies failed, each with its own three checks. His words on its card,
        the same day: "Say the failure once. The red summary box and 'Failed at' carry it;
        the steps list shows each step's one-line outcome, with its checks only under the
        failed step, collapsed.\""""
        from markupsafe import escape
        from modules.nsot import privileged
        run_one(resub, not_back(), subs=("101", "102"))
        rec = privileged.runs(NET)["runs"][0]
        assert [s["step"] for s in rec["steps"]] == [
            "plan", "hash", "hold", "started", "before", "remove", "remove", "wait", "re-add",
            "verify", "verify", "record"]
        assert (rec["state"], rec["outcome"]) == ("failed", "not_back")
        body = page(resub)
        assert "The steps taken · 12" in body and 'data-lead="verify"' in body
        lead = body[body.index('data-lead="verify"'):body.index('class="run-trail"')]
        taken = body[body.index('class="run-trail"'):]
        # "Failed at" names the step, by its short label; the red box above it says why.
        assert ">Failed at: Verify 101, 102</strong>" in lead
        assert "run-line" not in lead and "run-lead-said" not in lead, \
            "no checks and no second telling of the failure in the lead"
        # The failure is said ONCE on the card: the record's own summary, in the red box.
        assert body.count(str(escape(rec["why"]))) == 1
        for failed in (s for s in rec["steps"] if s["step"] == "verify"):
            assert body.count(str(escape(failed["words"]))) == 0, \
                "a failed step's own sentence is not said again under the summary"
        # Each step is one line; a failed step's checks sit under it alone, closed.
        assert taken.count('data-took="') == 12
        assert taken.count('<details class="run-checks"') == 2
        assert '<details class="run-checks" open' not in taken
        assert taken.count("<strong>stream</strong> (fail)") == 2, "each verify's own checks"
        passed = taken[taken.index('data-took="re-add"'):taken.index('data-took="verify"')]
        assert "run-checks" not in passed and "back; the running configuration" in passed, \
            "a step that passed: its one-line outcome, no checks"

    def test_a_run_still_going_is_one_entry_and_its_page_reopens_its_card(self, resub):
        """The operator's run showed twice ("r7 · telemetry re-subscribe" and "re-subscribe
        r7's telemetry subscriptions 101 and 102"): its hold and its job are one run, one
        entry, named for the run; the device's page reopens the run, never a fresh offer."""
        import threading

        from modules.nsot import capture_job, privileged
        src, entered, gate = Src(), threading.Event(), threading.Event()
        waited = src.sleep

        def held(seconds):
            """The run's own wait, held open by the test (never a sleep)."""
            entered.set()
            assert gate.wait(30), "the test never let the run go on"
            waited(seconds)
        src.sleep = held
        resub.state["src"] = src
        _r, html = card(resub, subs="101")
        try:
            assert press(resub, html, subs=("101",)).status_code == 200
            assert entered.wait(30), "the run never reached its wait"
            html = bar(resub)
            assert "Running now · 1" in html and html.count('class="ip-row"') == 1, html
            assert "<strong>r2</strong> · Re-subscribe telemetry" in html
            assert "Open its card" in html
            body = page(resub)
            assert "Re-subscribing on r2." in body and "Reopened: started by you" in body
            assert "Afterwards:" not in body, "the run, never a fresh offer"
        finally:
            gate.set()
        assert capture_job.wait(resub.state["jobs"][-1], 30)
        assert privileged.runs(NET)["runs"][0]["outcome"] == "resubscribed"
        assert "Running now" not in bar(resub), "ended: it leaves the running list"

    def test_one_run_is_one_finished_entry(self, resub):
        run_one(resub, not_back())
        assert bar(resub).count("Open the result") == 1, "the job's row, never the record's too"

    def test_a_record_alone_lists_it_for_the_person_who_started_it(self, resub, monkeypatch):
        from modules.nsot import privileged
        run_one(resub, not_back())
        rec = privileged.runs(NET)["runs"][0]
        restarted(monkeypatch)
        html = bar(resub)
        assert 'class="ip-chip ip-danger"' in html and "Finished, not opened yet · 1" in html
        assert "re-subscribed; the stream did not come back" in html and " · you · " in html
        assert f"{len(rec['steps'])} steps recorded" in html
        resub.state["viewer"] = "someone-else@example.invalid"
        assert "ip-chip" not in bar(resub), "only the person who started it"
        resub.state["viewer"] = TEST_PERSON
        body = page(resub)
        assert "op-card op-danger" in body and "started by you" in body
        assert 'data-lead="verify"' in body and f"The steps taken · {len(rec['steps'])}" in body
        assert "ip-chip" not in bar(resub), "opened from the record: not listed again"
        assert "op-card op-danger" not in page(resub), "an opened result is not reopened"

    def test_a_later_job_on_the_device_does_not_hide_a_run_known_by_its_record(
            self, resub, monkeypatch):
        """A newer job on the device that this person has opened (a diagnosis, another run)
        must not stop the page reopening an older run they have not."""
        from modules.nsot import capture_job
        run_one(resub, not_back())
        restarted(monkeypatch)
        later = capture_job.start(NET, "reading r2", TEST_PERSON, lambda _job: {},
                                  device="r2", card="diagnose")
        assert capture_job.wait(later, 30)
        capture_job.mark_opened(later, TEST_PERSON)
        body = page(resub)
        assert "op-card op-danger" in body and "Re-subscribed; the stream did not come back:" \
            in body, "the unopened run is reopened from its record"

    def test_the_row_s_card_leads_with_the_last_run_and_still_offers_the_next(
            self, resub, monkeypatch):
        from modules.nsot import privileged
        run_one(resub, not_back())
        rec = privileged.runs(NET)["runs"][0]
        restarted(monkeypatch)
        _r, html = card(resub, subs="101")
        # ONE line, closed until a person opens it (the operator, 2026-11-11: "The last run,
        # 3 h ago: re-subscribed; the stream did not come back · 12 steps · Show").
        assert (f'<details class="resub-last resub-last-danger" data-last-run="{rec["id"]}" '
                'data-keep="resub-r2-last">') in html, "closed, and in the failure's colour"
        assert html.index("The last run,") < html.index("Afterwards:"), "the outcome first"
        line = html[html.index("<summary><strong>The last run,"):html.index("</summary>")]
        assert re.search(r"The last run, <time [^>]*>[^<]+</time>: re-subscribed; the stream "
                         rf"did not come back</strong> · {len(rec['steps'])} steps · "
                         r'<span class="resub-show">Show</span>$', line), line
        assert "notice-danger" not in html.split("Afterwards:")[0], "no second red box"
        assert f"The steps taken · {len(rec['steps'])}" in html and 'data-lead="verify"' in html
        assert "Re-subscribe r2&#39;s telemetry (101)" in html or \
            "Re-subscribe r2's telemetry (101)" in html, "the offer stays under it"
        assert "ip-chip" not in bar(resub), "read on the row: the chip lets it go"

    def test_a_clean_run_is_green_and_only_then(self, resub):
        run_one(resub, Src(), subs=("101", "102"))
        html = bar(resub)
        assert 'class="ip-chip ip-ok"' in html and "In progress: 1 done" in html
        body = page(resub)
        assert "op-card op-ok" in body and "notice-muted" in body
        assert "run-lead" not in body, "nothing to lead with: every step is done"
        assert "run-step-failed" not in body and "run-row-done" in body

    def test_a_receiver_left_removed_names_the_next_action(self, resub):
        run_one(resub, Src(box=Box(readd_fails=2)))
        html = bar(resub)
        assert 'class="ip-chip ip-danger"' in html and "THE RECEIVER IS REMOVED" in html
        body = page(resub)
        assert "op-card op-danger" in body and "Re-add the receiver for 101…" in body
        # Its effect: pressed, the card is drawn again and leads with the one-step re-add.
        url = re.search(r'hx-get="([^"]+)"[^>]*>\s*<span class="op-idle">Re-add the receiver '
                        r'for 101…', body).group(1).replace("&amp;", "&")
        again = resub.get(url, headers=HX).get_data(as_text=True)
        assert "r2's receiver for 101 is removed." in again
        assert "resubscribe/readd" in again, "Re-add the receiver is offered"


# ── A heal ──────────────────────────────────────────────────────────────────────────────────

EDGE = {"hostname": "edge-b", "ip": "192.0.2.6", "device_type": "cisco_xe"}


@pytest.fixture
def heal(heal_lab, monkeypatch):  # noqa: F811
    """The heal's lab with edge-b on its network's page, one network, the real job starter."""
    import app as A
    from modules.nsot import capture_job

    state = {"jobs": [], "viewer": TEST_PERSON}
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])
    monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [dict(EDGE)])
    monkeypatch.setattr("modules.integration_groups.network_names", lambda: ["Default"])
    monkeypatch.setattr("routes.operations.viewer_key", lambda: state["viewer"])
    monkeypatch.setattr(capture_job, "_jobs", {})
    A.app.config["TESTING"] = True
    c = A.app.test_client()
    c.state = state
    yield c
    for job in state["jobs"]:
        assert capture_job.wait(job, 30), f"job {job} did not end within 30 s"


def heal_one(c, running=GOLDEN + ROUTE4, **kw):
    """One heal decided by the real decision and run by the real runner as its own job, over
    the act's fakes: ``(job, sources)``."""
    from modules.heal import act, policy
    from modules.nsot import capture_job

    # The job reads the mode at the wall clock; the lab's AUTO was confirmed at T0.
    kw.setdefault("mode", lambda got: policy.current("Default", T0 + 5))
    src = FakeAct(running, **kw)
    d = decided(running)
    got = act.run("Default", now=T0 + 5,
                  starter=lambda network, taken: act.start(network, taken, sources=src))
    assert got["started"] and not got["failed"], got
    job = got["started"][0]["job"]
    c.state["jobs"].append(job)
    assert capture_job.wait(job, 30)
    return job, src, d


def recorded(decision):
    """The heal's outcome as Mercury's own record keeps it (`decisions.applied`)."""
    from modules.heal import decisions
    return (decisions.find("Default", decision["id"]).get("applied") or {}).get("outcome")


class TestAHealsOutcome:
    def test_a_healed_run_is_listed_and_its_card_shows_the_steps_taken(self, heal):
        job, src, d = heal_one(heal)
        html = bar(heal)
        # The effect the card is about: the program applied as the policy, recorded healed.
        assert recorded(d) == "healed" and src.apply_kw["actor"] == SETTER
        assert 'class="ip-chip ip-ok"' in html and "In progress: 1 done" in html
        assert "<strong>edge-b</strong> · Self-healing" in html and "healed" in html
        assert "steps recorded" in html and SETTER in html, "started by the policy's setter"
        body = page(heal, "edge-b", "Default")
        assert "op-card op-ok" in body and "Self-healing on edge-b" in body
        assert 'data-outcome="healed"' in body and "The steps taken" in body
        for key in ("take", "stops", "read", "plan", "authorise", "apply", "intent", "saved",
                    "golden", "record"):
            assert f'data-took="{key}"' in body, f"the {key} step is among the steps taken"
        assert "run-step-failed" not in body and "run-lead" not in body
        assert "ip-chip" not in bar(heal), "opened: the chip lets it go"
        again = heal.get(f"/v2/device/edge-b/heal/job/{job}?list=Default", headers=HX)
        assert again.status_code == 200 and 'data-outcome="healed"' in again.get_data(
            as_text=True), "its own route draws the same card"

    def test_a_rolled_back_heal_is_red_and_its_failed_step_leads(self, heal):
        # The read after the change still holds the route: the heal did not land, and what
        # landed was undone.
        _job, _src, d = heal_one(heal, post=GOLDEN + ROUTE4)
        html = bar(heal)
        assert recorded(d) == "rolled_back", "the card says what the record holds"
        assert 'class="ip-chip ip-danger"' in html and "In progress: 1 failed" in html
        assert "rolled back" in html
        body = page(heal, "edge-b", "Default")
        assert "op-card op-danger" in body and 'data-outcome="rolled_back"' in body
        # The first failed step, in the order the act declares them: the apply, which says
        # why it was undone; the check that found it (intent) is failed under it.
        assert 'run-lead run-lead-failed" data-lead="apply"' in body, "the failed step leads"
        assert "so what landed was undone" in body
        assert 'run-line run-line-failed" data-took="intent"' in body
        assert "run-row-failed" in body and "run-row-done" not in body, "nothing green"

    def test_a_partial_heal_is_amber_never_green(self, heal):
        _job, _src, d = heal_one(heal, recheck="drifted")
        html = bar(heal)
        assert recorded(d) == "partial", "the card says what the record holds"
        assert 'class="ip-chip ip-warn"' in html and "In progress: 1 partial" in html
        body = page(heal, "edge-b", "Default")
        assert "op-card op-warn" in body and 'data-outcome="partial"' in body
        assert "op-card op-ok" not in body and "run-row-done" not in body

    def test_it_is_listed_for_every_person_until_each_opens_it(self, heal):
        from modules.nsot import capture_job
        job, _src, _d = heal_one(heal)
        heal.state["viewer"] = "a@example.invalid"
        page(heal, "edge-b", "Default")
        assert "ip-chip" not in bar(heal)
        # Its effect: the job remembers who opened it, and only them.
        (kept,) = [j for j in capture_job.card_jobs() if j["job"] == job]
        assert kept["opened"] == {"a@example.invalid"}
        heal.state["viewer"] = "b@example.invalid"
        assert "Open the result" in bar(heal), "a run nobody started is everybody's to read"


# ── A can't-fix: a decision, its steps on its row and in its notice ─────────────────────────

class TestACantFixsSteps:
    def test_the_row_draws_the_steps_taken_the_one_it_stopped_at_leading(self, heal_lab,  # noqa: F811
                                                                         monkeypatch):
        from modules import attention
        from tests.test_heal_analysis import cant_fix

        inc = cant_fix()
        monkeypatch.setattr(attention, "_page_network", lambda: "Default")
        (r,) = [x for x in attention.heal_source(now=T0 + 20)["rows"]
                if x["kind"] == "cant_fix"]
        taken = r["steps_taken"]
        assert taken, "the row carries no steps taken"
        assert taken["ended"] and taken["rows"][0]["group"] == "failed", "never green"
        assert taken["lead"]["state"] == "failed" and taken["lead"]["why"], taken["lead"]
        said = [t["key"] for t in taken["trail"]]
        assert said[:2] == ["claim", "stops"] and said[-1] == "record", said
        assert len(taken["trail"]) == len(r["operands"]["steps"]), "every recorded step"
        after = [s["state"] for s in taken["rows"][0]["steps"]
                 if s["key"] not in ("d-" + k for k in said)]
        assert set(after) <= {"not_reached", "skipped"}, "a step it never reached is not done"
        assert r["event"] == inc
        # Drawn: ONE closed line on the row, the stepper inside it; the cause above says why,
        # so the step it stopped at is named and its sentence is not said a second time.
        import app as A
        from flask import render_template
        r["networks"] = {r["devices"][0]: ["Default"]}
        with A.app.test_request_context("/v2/"):
            html = render_template("v2/_attention.html", a={"rows": [r], "sources": [],
                                                             "badge": {"n": 1}})
        assert f'<details class="att-taken" data-keep="att-taken-{r["id"]}">' in html, "closed"
        line = html[html.index('<details class="att-taken"'):]
        line = line[line.index("<summary>") + 9:line.index("</summary>")]
        assert line == (f"The steps Mercury took: stopped at {taken['lead']['words']} · "
                        f"{len(taken['trail'])} steps · "
                        '<span class="resub-show">Show</span>'), line
        assert len(taken["lead"]["words"].split()) <= 4, "by the step's short label"
        from markupsafe import escape
        block = html[html.index('<details class="att-taken"'):html.index('class="att-meta"')]
        assert "The steps taken" in block and 'data-lead="d-' in block
        for why in taken["lead"]["why"]:
            assert block.count(str(escape(why))) == 0, \
                "the row's cause says it above: the steps do not say it again"
            assert str(escape(why)) in html[:html.index('<details class="att-taken"')]

    def test_the_notice_carries_every_step_taken(self, heal_lab):  # noqa: F811
        from modules import heal_notice as N
        from modules.heal import steplog
        from modules.notify import message
        from tests.test_heal_analysis import cant_fix

        inc = cant_fix()
        entry = next(e for e in steplog.incidents("Default")["entries"]
                     if e["incident"] == inc)
        facts = N.facts("Default", entry)
        assert len(facts["steps"]) == len(entry["steps"]) > 2
        text = message.text(message.check_event(facts))
        for s in facts["steps"]:
            assert f"{s['said']}: {s['result']}" in text, "each step and its result"


# ── The shape: a job that names its device names its card ───────────────────────────────────

def _job_starts(paths=None, root=None):
    """Every `capture_job.start(...)` call in *paths* (by default every file git tracks under
    modules/ and routes/, from `source_index.tracked`, so an untracked copy of the program is
    never scanned as the program), by parsing: ``[(file, line, keywords)]``."""
    import ast
    import os

    from tests import source_index

    root = root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if paths is None:
        paths = source_index.tracked("modules", "routes", suffix=".py")
    out = []
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "start"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "capture_job"):
                out.append((os.path.relpath(path, root).replace(os.sep, "/"), node.lineno,
                            {k.arg for k in node.keywords}))
    return out


class TestADeviceJobNamesItsCard:
    """The property behind every outcome above, held for the class and not for its members: a
    job started for ONE device (`capture_job.start(..., device=...)`) names the card that
    draws it (``card=``), because only then does the In progress list keep its outcome under
    Finished and the device's page reopen it (`capture_job.card_jobs`). The heal's job named
    its device and no card, so its outcome was drawn nowhere but History."""

    def test_every_job_that_names_a_device_names_a_card(self, tmp_path):
        # The scan finds a planted job that names its device and no card.
        mod = tmp_path / "modules"
        mod.mkdir()
        (mod / "planted.py").write_text(
            "from modules.nsot import capture_job\n\n\ndef go(n, d, w):\n"
            "    return capture_job.start(n, 'x', 'a', w, kind='k', device=d)\n",
            encoding="utf-8")
        (planted,) = _job_starts([str(mod / "planted.py")], str(tmp_path))
        assert planted[0] == "modules/planted.py" and "device" in planted[2] \
            and "card" not in planted[2]
        starts = _job_starts()
        assert len(starts) >= 20, f"the scan found {len(starts)} job starts: it lost its sight"
        named = [(f, n) for f, n, kw in starts if "device" in kw]
        assert len(named) >= 8, named
        bare = [f"{f}:{n}" for f, n, kw in starts if "device" in kw and "card" not in kw]
        assert bare == [], ("a job that names its device and no card ends with its outcome "
                            f"drawn nowhere: {bare}")
        for wanted in ("modules/heal/act.py", "modules/heal/propose.py",
                       "modules/heal/resubscribe.py"):
            assert any(f == wanted for f, _n in named), f"{wanted}'s job names no device"
