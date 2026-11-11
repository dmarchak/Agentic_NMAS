"""Operation progress (the operator, 2026-11-11, after a re-subscribe of r7: "a long operation
shows a stepper, with the current step, each step done, failed or pending, live waits with a
countdown, and each verify read as it happens, like sending configs"; "The second 'running'
entry sat at 'starting' for 8+ minutes with no detail. Every state shown must be the run's real
current step."). Through the real app and the real job starter, on the heal's lab (the real
decision and act over tests/test_heal_act.py's fakes) and the re-subscribe's
(tests/test_heal_resubscribe.py's box), each run held open at one of ITS OWN steps by the
test's gate, never by sleeping. No device, no network.

- **A run's own steps** (`op_progress`): a job hands over the list it records its steps in;
  what is read back is that list as it stands; each step written is announced; outside a job
  nothing is kept and nothing announced.
- **A heal, live:** mid-apply its card draws its decision's steps and its act's, the apply
  running and leading, nothing after it done; the In progress list has ONE row whose words
  are that step; waiting on its symptom, the wait's declared bound and when it began are on
  the card for the countdown; at its end the outcome replaces it.
- **A re-subscribe, live:** at its wait the card leads with it, its 10 s declared; the row's
  words are the wait's, never "started"; a run whose record says running with nothing running
  it is said to have stopped.
- **Reads, compactly:** a 32-read and a 90-read verify draw three check lines and one summary
  line each, every read in a closed list one level down; a running step, the newest read of
  each check; a step with reads and no checks, the newest read of each command.
- **The countdown** the page ticks says the server's own words (duktape).
- **In a real browser:** a heal's card advances by itself, its wait counts down, and it ends
  with its outcome.
"""
import re
import threading
import time

import pytest

import modules.heal.resubscribe  # noqa: F401  (one of the two operations drawn)
from tests.conftest import TEST_PERSON
from tests.test_heal_act import ADJ, CFG, FakeAct, decided
from tests.test_heal_decide import GOLDEN, ROUTE4, changed
from tests.test_heal_policy import T0
from tests.test_heal_resubscribe import NET, Src
from tests.test_heal_resubscribe_v2 import card, press
from tests.test_in_flight import no_hold_survives_a_test  # noqa: F401 (autouse)
from tests.test_run_outcomes import (bar, heal, heal_lab, page, recorded, resub,  # noqa: F401
                                     resub_lab, run_one)
from tests.test_sdn_connections import networks  # noqa: F401 (the labs build on it)

DECLARED = (("plan", "Plan"), ("wait", "Wait"), ("verify", "Verify"), ("record", "Record"))
SYSLOG_GONE = changed(("logging host 192.0.2.50\n", ""))


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


# ── A run's own steps ───────────────────────────────────────────────────────────────────────

class TestARunsOwnSteps:
    def test_outside_a_job_nothing_is_kept_and_nothing_announced(self, monkeypatch):
        from modules import op_progress
        said = []
        monkeypatch.setattr("modules.invalidation.announce",
                            lambda keys, by, ok=True: said.append((tuple(keys), by)))
        steps = []
        assert op_progress.current() == ""
        assert op_progress.attach(DECLARED, steps, run="r-1") is False
        op_progress.moved()
        assert said == [] and op_progress.run_of("no-such-operation") is None

    def test_a_job_s_list_is_read_as_it_stands_and_each_step_is_announced(self, monkeypatch):
        from modules import op_progress
        said = []
        monkeypatch.setattr("modules.invalidation.announce",
                            lambda keys, by, ok=True: said.append((tuple(keys), by)))
        op = "run-progress-test-0001"
        assert op_progress.start(op, "heal", "healing edge-b", actor="policy", counts="")
        try:
            steps = []
            with op_progress.running_as(op):
                assert op_progress.current() == op
                assert op_progress.attach(DECLARED, steps, run="hd-1")
                steps.append({"step": "plan", "result": "ok", "words": "planned"})
                op_progress.moved()
                steps.append({"step": "wait", "result": "running", "words": "waiting"})
                op_progress.moved()
            assert op_progress.current() == "", "the thread is nobody's again"
            got = op_progress.run_of(op)
            assert [s["step"] for s in got["steps"]] == ["plan", "wait"] and got["run"] == "hd-1"
            assert got["steps"] is not steps and got["steps"][0] is not steps[0], "a copy"
            assert said == [(("device_progress",), "run-progress")] * 3, \
                "the attach, and each step written"
            (row,) = [r for r in op_progress.running() if r["id"] == op]
            assert row["step_words"] == "Wait · step 2 of 4" and row["own_steps"], \
                "the row's words are the newest step's, never the phase it was registered with"
        finally:
            op_progress.finish(op)

    def test_the_announcer_and_its_key_are_declared(self):
        from modules import invalidation, op_progress
        assert invalidation.ANNOUNCERS[op_progress.STEP_ANNOUNCER] == op_progress.STEP_KEYS
        assert set(op_progress.STEP_KEYS) <= set(invalidation.VOCABULARY)


# ── A heal, live ────────────────────────────────────────────────────────────────────────────

class Gated(FakeAct):
    """The act's fakes, each of two steps held open by the test: the apply, and the symptom's
    read after the device is released."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.gates = {k: (threading.Event(), threading.Event()) for k in ("apply", "symptom")}

    def _hold(self, name):
        entered, go = self.gates[name]
        entered.set()
        assert go.wait(30), f"the test never let the {name} go on"

    def apply(self, device, **kw):
        self._hold("apply")
        return super().apply(device, **kw)

    def symptom(self, device, triggers, since):
        self._hold("symptom")
        return super().symptom(device, triggers, since)

    def reached(self, name):
        assert self.gates[name][0].wait(30), f"the run never reached its {name}"

    def go(self, name):
        self.gates[name][1].set()

    def let_go(self):
        for _entered, go in self.gates.values():
            go.set()


def start_heal(c, running, **decision):
    """One heal decided by the real decision and started by the real runner as its own job,
    its apply and its symptom read held by the test: ``(job, sources, decision)``."""
    from modules.heal import act, policy

    src = Gated(running, mode=lambda got: policy.current("Default", T0 + 5))
    d = decided(running, **decision)
    got = act.run("Default", now=T0 + 5,
                  starter=lambda network, taken: act.start(network, taken, sources=src))
    assert got["started"] and not got["failed"], got
    job = got["started"][0]["job"]
    c.state["jobs"].append(job)
    return job, src, d


def step_states(body):
    """``{step key: state}`` of the stepper drawn in *body*."""
    return {key: state for state, key in
            re.findall(r'class="run-step run-step-(\w+)" data-step="([^"]+)"', body)}


class TestAHealLive:
    def test_mid_apply_the_card_and_the_list_say_the_apply(self, heal):  # noqa: F811
        from modules import op_progress
        from modules.nsot import capture_job
        job, src, d = start_heal(heal, GOLDEN + ROUTE4)
        try:
            src.reached("apply")
            live = op_progress.run_of(job)
            assert live is not None, "the run's own steps are not readable while it runs"
            assert [s["step"] for s in live["steps"]] == [
                "take", "stops", "read", "plan", "authorise", "apply"]
            assert live["steps"][-1]["result"] == "running" and live["run"] == d["id"]
            html = bar(heal)
            assert "Running now · 1" in html and html.count('class="ip-row"') == 1
            assert "<strong>edge-b</strong> · Self-healing" in html
            assert "<small>Apply · step 6 of 11 · " in html, \
                "the row's words are the run's current step, by its short label"
            assert "started" not in html.split("ip-row")[1].split("</small>")[0]
            body = page(heal, "edge-b", "Default")
            assert "Self-healing is running on edge-b" in body
            got = step_states(body)
            assert got["apply"] == "running" and 'data-lead="apply"' in body
            assert ('<strong title="Apply as the policy, holding the device: the deploy&#39;s '
                    'nine stages">Now: Apply</strong>') in body, "short label, long on hover"
            assert {got[k] for k in ("take", "stops", "read", "plan", "authorise")} == {"done"}
            assert {got[k] for k in ("intent", "symptom", "saved", "golden", "record")} == {
                "waiting"}, "a step the run has not reached is pending, never done"
            assert {got[k] for k in got if k.startswith("d-")} <= {"done", "skipped"}, \
                "its decision's steps come first, each as it was recorded"
            assert got["d-claim"] == "done" and got["d-decide"] == "done"
        finally:
            src.let_go()
        assert capture_job.wait(job, 30) and recorded(d) == "healed"
        after = page(heal, "edge-b", "Default")
        assert 'data-outcome="healed"' in after and "run-step-running" not in after

    def test_waiting_on_its_symptom_the_declared_bound_is_on_the_card(self, heal):  # noqa: F811
        from modules import op_progress
        from modules.heal import act
        from modules.nsot import capture_job
        job, src, d = start_heal(heal, SYSLOG_GONE, triggers=[CFG, ADJ],
                                 kinds=("missing_line",))
        try:
            src.go("apply")
            src.reached("symptom")
            live = op_progress.run_of(job)
            assert live is not None, "the run's own steps are not readable while it runs"
            newest = live["steps"][-1]
            assert (newest["step"], newest["result"]) == ("symptom", "running")
            assert newest["wait_s"] == act.SYMPTOM_SECONDS["adjacency"] == 150
            assert newest["wait_bound"] is True and newest["began"] == newest["at"]
            body = page(heal, "edge-b", "Default")
            assert 'data-lead="symptom"' in body
            assert (f'data-run-wait-began="{newest["began"]}" data-run-wait-s="150" '
                    'data-run-wait-bound="1"') in body
            assert re.search(r"up to 150 s: \d+ s left<", body), "the server's own words"
            got = step_states(body)
            assert got["symptom"] == "running" and got["golden"] == "done" \
                and got["record"] == "waiting"
            assert "<small>Read symptom · step 8 of 11 · " in bar(heal)
        finally:
            src.let_go()
        assert capture_job.wait(job, 30) and recorded(d) == "healed"
        ended = next(s for s in capture_job.get(job)["payload"]["result"]["steps"]
                     if s["step"] == "symptom")
        assert ended["result"] == "none" and ended["began"] == newest["began"] \
            and ended["wait_s"] == 150, "ended in place: one record, with when it began"

    def test_the_recorded_steps_end_as_they_always_did(self, heal):  # noqa: F811
        from modules.nsot import capture_job
        job, src, _d = start_heal(heal, GOLDEN + ROUTE4)
        src.let_go()
        assert capture_job.wait(job, 30)
        steps = capture_job.get(job)["payload"]["result"]["steps"]
        assert [(s["step"], s["result"]) for s in steps] == [
            ("take", "ok"), ("stops", "ok"), ("read", "ok"), ("plan", "ok"),
            ("authorise", "ok"), ("apply", "running"), ("intent", "ok"), ("saved", "ok"),
            ("golden", "ok"), ("symptom", "none"), ("record", "healed")]
        assert "ip-chip" in bar(heal), "and its outcome is listed"


class TestWhileAHealApplies:
    """The deploy's stages are the device's hold's (the deploy's own stepper), drawn under the
    heal's steps while the heal holds the device as a deploy. On the re-subscribe's lab, whose
    holds are read for real."""

    def test_the_stages_come_from_the_hold_and_only_a_deploy_s(self, resub):  # noqa: F811
        import app as A
        from flask import render_template

        from modules import run_stepper as RS
        from modules.heal import run_card
        from modules.nsot import device_ops
        assert run_card._stages(NET, "r2") == [], "nothing holds it"
        with device_ops.hold(NET, "r2", "rotate", TEST_PERSON):
            assert run_card._stages(NET, "r2") == [], "held, and not as a deploy"
        with device_ops.hold(NET, "r2", "deploy", "policy@example.invalid",
                             detail="heal to intent"):
            device_ops.note("pre_snapshot")
            device_ops.note("deploy")
            stages = run_card._stages(NET, "r2")
            running = [s for s in stages if s["state"] == "running"]
            assert [s["key"] for s in running] == ["deploy"], stages
            assert [s["state"] for s in stages][:3] == ["done", "done", "done"]
            card = {"op": "heal_run", "state": "running", "host": "r2", "list": NET,
                    "job": "0" * 32, "started": "2026-11-11T16:38:00Z", "actor": "the policy",
                    "back": "overview", "stages": stages,
                    "steps": RS.record_card("r2", "Self-healing's steps on r2", [
                        run_card.act_phase([{"step": "take", "result": "ok", "words": "taken"},
                                            {"step": "apply", "result": "running",
                                             "words": "holding r2"}], ended=False)],
                        ended=False)}
            with A.app.test_request_context(f"/v2/device/r2?list={NET}"):
                html = render_template("v2/_heal_run.html", c=card)
        assert "While it applies, the deploy's stages on r2:" in html
        assert html.count("data-run-stepper") == 2, "the heal's steps, then the deploy's stages"
        assert 'class="run-step run-step-running" data-step="deploy"' in html
        assert device_ops.holder(NET, "r2") is None


# ── A re-subscribe, live ────────────────────────────────────────────────────────────────────

class TestAReSubscribeLive:
    def test_at_its_wait_the_card_leads_with_it_and_the_row_says_it(self, resub):  # noqa: F811
        from modules.heal import resubscribe as R
        from modules.nsot import capture_job, privileged
        src, entered, gate = Src(), threading.Event(), threading.Event()
        waited = src.sleep

        def held(seconds):
            entered.set()
            assert gate.wait(30), "the test never let the run go on"
            waited(seconds)
        src.sleep = held
        resub.state["src"] = src
        _r, html = card(resub, subs="101")
        try:
            assert press(resub, html, subs=("101",)).status_code == 200
            assert entered.wait(30), "the run never reached its wait"
            listed = bar(resub)
            assert "<small>Wait 10 s · step 7 of 11 · " in listed
            assert "<small>started" not in listed, "never the hold's 'started'"
            _r, going = card(resub, subs="101")
            assert 'data-lead="wait"' in going
            assert ('<strong title="Wait 10 s, once, after the last removal">Now: Wait 10 s'
                    "</strong>") in going
            assert 'data-run-wait-s="10"' in going and "data-run-wait-bound" not in going
            got = step_states(going)
            assert got["wait"] == "running" and got["remove"] == "done"
            assert {got[k] for k in ("re-add", "verify", "record")} == {"waiting"}
            assert "nmas:device_progress from:body" in going, "it redraws at each step"
        finally:
            gate.set()
        assert capture_job.wait(resub.state["jobs"][-1], 30)
        rec = privileged.runs(NET)["runs"][0]
        wait = next(s for s in rec["steps"] if s["step"] == "wait")
        assert (wait["result"], wait["wait_s"]) == ("ok", R.WAIT_S) and wait["began"]
        assert [s["step"] for s in rec["steps"]] == [
            "plan", "hash", "hold", "started", "before", "remove", "wait", "re-add", "verify",
            "record"], "the record's steps are as they always were"

    def test_a_run_nothing_is_running_is_said_to_have_stopped(self, resub, monkeypatch):  # noqa: F811
        from modules.heal import resubscribe as R
        from modules.nsot import capture_job, device_ops, privileged
        run_one(resub, Src())
        rec = privileged.runs(NET)["runs"][0]
        # The record as a run that never reached its verify left it: still "running".
        cut = dict(rec, state="running", outcome="running", finished_at=None,
                   steps=[s for s in rec["steps"] if s["step"] not in ("verify", "record")])
        privileged.record(NET, cut)
        monkeypatch.setattr(capture_job, "_jobs", {})
        url = f"/v2/device/r2/resubscribe?list={NET}&subs=101&run={rec['id']}"
        with device_ops.hold(NET, "r2", R.OPERATION, "other@example.invalid"):
            going = resub.get(url, headers={"HX-Request": "true"}).get_data(as_text=True)
            assert "Re-subscribing on r2." in going, "held by a re-subscribe: still going"
        html = resub.get(url, headers={"HX-Request": "true"}).get_data(as_text=True)
        assert "This run stopped before it recorded an outcome:" in html
        assert "no step recorded since" in html and "notice-danger" in html
        assert "Re-subscribing on r2." not in html and 'aria-busy="true"' not in html
        got = step_states(html)
        assert got["verify"] == "not_reached" and got["record"] == "not_reached"
        assert got["re-add"] == "done" and "run-row-failed" in html, "never green"
        assert device_ops.holder(NET, "r2") is None, "nothing holds the device"


# ── Reads, compactly ────────────────────────────────────────────────────────────────────────

def verify_step(sub, n, *, result="failed", start=1_794_250_000, running=False):
    """A verify step as the record keeps it once its reads are kept (the shape agreed with
    the build that writes them): its final ``checks`` and *n* ``reads``, one per check in
    turn, a round every 10 s."""
    checks = ("device", "stream", "collector")
    reads = [{"at": iso(start + 10 * (i // 3)), "check": checks[i % 3],
              "command": {"device": f"show telemetry ietf subscription {sub} receiver",
                          "stream": f"the stream's series for {sub}",
                          "collector": "the collector's sessions"}[checks[i % 3]],
              "result": "pass" if checks[i % 3] == "device" and i >= 3 else "fail",
              "words": f"{checks[i % 3]} read {i // 3 + 1}", "read_id": f"r-{sub}-{i}"}
             for i in range(n)]
    step = {"step": "verify", "result": "running" if running else result, "sub": sub,
            "words": f"subscription {sub}", "at": iso(start + 10 * (n // 3)), "reads": reads}
    if not running:
        step["checks"] = {"device": {"state": "pass", "words": "Connected on a new connection"},
                          "stream": {"state": "fail", "words": "no series"},
                          "collector": {"state": "fail", "words": "no new session"}}
    return step


def drawn(model):
    """THE stepper's own markup for *model*."""
    import app as A
    with A.app.test_request_context("/v2/"):
        macro = A.app.jinja_env.get_template("v2/_run_stepper.html").module.run_stepper
        return str(macro(model))


class TestReadsAreDrawnCompactly:
    def test_a_32_and_a_90_read_verify_draw_three_checks_and_one_summary_each(self):
        from modules import run_stepper as RS
        steps = [{"step": "plan", "result": "ok", "words": "planned", "at": iso(1)},
                 verify_step("101", 32), verify_step("102", 90),
                 {"step": "record", "result": "ok", "words": "recorded", "at": iso(2)}]
        phase = RS.from_record(DECLARED, steps, ended=True)
        lead = phase["lead"]
        assert lead["key"] == "verify" and lead["lines"] == [] and lead["more"] == []
        assert lead["why"] == ["1 of 2: subscription 101", "2 of 2: subscription 102"], \
            "the lead says why, once; what the step read is under the step"
        first, second = [t for t in phase["trail"] if t["key"] == "verify"]
        for took in (first, second):
            assert [(ln["what"], ln.get("summary", False)) for ln in took["checks"]] == [
                ("device", False), ("stream", False), ("collector", False), ("", True)], \
                "its final checks and ONE line of its reads"
            assert took["said"] == "", "said in the lead, not again"
        assert first["checks"][3]["words"] == (
            "32 reads, about 10 s apart: 10 pass, 22 fail; the last: stream read 11")
        assert second["checks"][3]["words"].startswith(
            "90 reads, about 10 s apart: 29 pass, 61 fail; the last: ")
        assert [(t["more"][0]["title"], len(t["more"][0]["reads"])) for t in (first, second)] \
            == [("The 32 reads", 32), ("The 90 reads", 90)]
        assert first["more"][0]["reads"][0]["words"] == "stream read 11", "newest first"
        assert [t["checks"] for t in phase["trail"] if t["key"] != "verify"] == [[], []], \
            "a step that passed shows no checks"
        html = drawn(RS.record_card("r2", "Steps", [phase], ended=True, level="danger"))
        lead_html = html[html.index('data-lead="verify"'):html.index('class="run-trail"')]
        assert "run-line" not in lead_html, "no checks in the lead of a step that ended"
        taken = html[html.index('class="run-trail"'):]
        in_place = re.sub(r'<details class="run-checks".*?</details>\s*</details>', "", taken,
                          flags=re.S)
        assert in_place.count('<li class="run-line') == 4, "four lines in place, not 130"
        assert taken.count('<details class="run-checks"') == 2
        assert taken.count("<strong>stream</strong> (fail): no series") == 2
        assert taken.count('<details class="run-reads"') == 2
        assert '<details class="run-checks" open' not in taken \
            and '<details class="run-reads" open' not in taken \
            and taken.count(" open>") == 1, \
            "only the steps taken are open: the checks and the full list stay closed"
        assert taken.count("device read ") + taken.count("stream read ") \
            + taken.count("collector read ") >= 122, "and every read is in it"

    def test_a_running_verify_draws_the_newest_read_of_each_check(self):
        from modules import run_stepper as RS
        steps = [{"step": "plan", "result": "ok", "words": "planned", "at": iso(1)},
                 verify_step("101", 32, running=True)]
        lead = RS.from_record(DECLARED, steps, ended=False)["lead"]
        assert lead["state"] == "running"
        assert [(ln["what"], ln["words"]) for ln in lead["lines"][:3]] == [
            ("device", "device read 11"), ("stream", "stream read 11"),
            ("collector", "collector read 10")], "three lines, each the newest of its check"
        assert lead["lines"][3]["summary"] and len(lead["lines"]) == 4
        assert len(lead["more"][0]["reads"]) == 32
        # Checks a running step carries are not its final ones: the newest reads still lead.
        early = dict(verify_step("101", 32, running=True),
                     checks={"device": {"state": "waiting", "words": "an earlier round"}})
        lead = RS.from_record(DECLARED, steps[:1] + [early], ended=False)["lead"]
        assert [ln["words"] for ln in lead["lines"][:3]] == [
            "device read 11", "stream read 11", "collector read 10"]

    def test_reads_with_no_checks_draw_the_newest_of_each_command(self):
        from modules import run_stepper as RS
        reads = [{"at": iso(100 + 30 * i), "command": "the adjacencies reader's value",
                  "result": "fail" if i < 3 else "pass", "words": f"read {i + 1}",
                  "read_id": f"s-{i}"} for i in range(4)]
        steps = [{"step": "plan", "result": "ok", "words": "planned", "at": iso(1)},
                 {"step": "verify", "result": "failed", "words": "still there", "at": iso(200),
                  "reads": reads + ["a diagnosis step's reads are strings: skipped"]}]
        phase = RS.from_record(DECLARED, steps, ended=True)
        (took,) = [t for t in phase["trail"] if t["key"] == "verify"]
        assert [(ln["what"], ln["words"]) for ln in took["checks"]] == [
            ("the adjacencies reader's value", "read 4"),
            ("", "4 reads of `the adjacencies reader's value`, about 30 s apart: 1 pass, "
                 "3 fail; the last: read 4")]
        assert len(took["more"][0]["reads"]) == 4
        passed = RS.from_record(DECLARED, [steps[0], dict(steps[1], result="ok")], ended=True)
        assert [t["checks"] for t in passed["trail"]] == [[], []] and passed["lead"] is None, \
            "the same step passed: its one-line outcome alone"


# ── Step columns are short ──────────────────────────────────────────────────────────────────

def step_tables():
    """Every operation that declares steps for THE stepper, each as ``(name, [(key, column
    words, long words)])``: the operations drawn from their own record (their ``STEPS`` with
    their ``STEP_LABELS``, filled in for a device and one, two and five subscriptions), and
    the ones drawn from the hold's trail (`device_actions.JOB_STEPPERS`' declared tables and
    Save's, whose declared words are already the column's)."""
    import importlib

    from modules import device_actions as DA
    from modules import run_stepper as RS
    from modules.heal import act, bounce, decide, propose, session_clear
    from modules.heal import resubscribe as R
    from modules.nsot import save_op

    out = []
    for mod in (act, propose, decide, bounce, session_clear):
        labels = RS.labels_for(mod.STEP_LABELS, device="edge-b")
        out.append((mod.__name__, [(k, labels.get(k, ""), w) for k, w in mod.STEPS]))
    for subs in (["101"], ["101", "102"], ["101", "102", "103", "104", "105"], []):
        labels = R.step_labels("r7", subs)
        out.append((f"resubscribe {len(subs)}", [(k, labels.get(k, ""), w) for k, w in R.STEPS]))
    labels = R.step_labels("r7", ["101"])
    out.append(("re-add", [(k, labels.get(k, ""), w) for k, w in R.READD_STEPS]))
    for op, ref in sorted(DA.JOB_STEPPERS.items()):
        if isinstance(ref, tuple):
            table = getattr(importlib.import_module(ref[0]), ref[1])
            out.append((f"{op} ({ref[0]}.{ref[1]})", [(s[0], s[1], s[1]) for s in table]))
    out.append(("save", [(s[0], s[1], s[1]) for s in save_op.DEVICE_STEPS]))
    return out


class TestStepColumnsAreShort:
    """The operator, 2026-11-11: "The stepper: short labels (2-4 words: 'Read intent', 'Hold
    r7', 'Remove 101', 'Wait 10 s', 'Re-add', 'Verify 101', 'Record'), the long text on hover
    or in the list below. No full sentences in the step columns.\""""

    def test_no_step_column_is_longer_than_four_words(self):
        tables = step_tables()
        assert len(tables) >= 14, f"{len(tables)} operations' steps checked: it lost its sight"
        long = [(name, key, words) for name, steps in tables for key, words, _long in steps
                if not 1 <= len(words.split()) <= 4]
        assert long == [], f"a step column of no words or more than four: {long}"
        assert sum(len(steps) for _name, steps in tables) >= 120

    def test_the_operator_s_own_labels_are_the_re_subscribe_s(self):
        from modules.heal import resubscribe as R
        got = R.step_labels("r7", ["101"])
        assert [got[k] for k in ("plan", "hold", "remove", "wait", "re-add", "verify",
                                 "record")] == ["Read intent", "Hold r7", "Remove 101",
                                                "Wait 10 s", "Re-add", "Verify 101", "Record"]
        assert R.step_labels("r7", ["101", "102"])["verify"] == "Verify 101, 102"
        assert R.step_labels("r7", ["1", "2", "3"])["remove"] == "Remove 3 streams"

    def test_the_column_says_the_label_and_the_hover_the_long_words(self):
        from modules import run_stepper as RS
        from modules.heal import resubscribe as R
        labels = R.step_labels("r7", ["101"])
        phase = RS.from_record(R.STEPS, [
            {"step": "plan", "result": "ok", "words": "read from intent", "at": iso(1)},
            {"step": "hash", "result": "refused", "words": "the hash moved", "at": iso(2)},
            {"step": "record", "result": "ok", "words": "nothing was sent", "at": iso(3)}],
            ended=True, labels=labels)
        assert [(s["words"], s["long"]) for s in phase["steps"]] == [
            (labels[k], w) for k, w in R.STEPS], "every declared step, labelled"
        html = drawn(RS.record_card("r7", "Steps", [phase], ended=True, level="danger"))
        for key, long_words in R.STEPS:
            column = re.search(rf'data-step="{key}"[^>]*title="([^"]*)"[^>]*>.*?'
                               r'<span class="run-words">([^<]*)<', html, re.S)
            assert column, key
            assert column.group(2) == labels[key], "the column: the short label"
            assert column.group(1).startswith(str(__import__("markupsafe").escape(long_words))), \
                "the hover: the declared words"
        assert ('<strong title="Recompute each subscription&#39;s program and compare its '
                'hash">Failed at: Check hashes</strong>') in html
        assert html.count("the hash moved") == 1, "the failure is said once"
        assert '<strong title="Read each subscription&#39;s receiver from committed intent; ' \
            in html and ">Read intent</strong> (done)" in html, "the list: label, long on hover"


# ── The countdown ───────────────────────────────────────────────────────────────────────────

class TestTheCountdown:
    def test_the_page_ticks_the_server_s_own_words(self):
        import dukpy

        from modules import run_stepper as RS
        with open("static/js/nmas_stepper.js", encoding="utf-8") as fh:
            js = fh.read()
        began = "2026-11-11T16:38:10Z"
        at = RS._epoch(began)
        for length, bound in ((10, False), (150, True)):
            for after in (0, 4, length - 1, length, length + 30):
                server = RS._wait({"began": began, "wait_s": length, "wait_bound": bound},
                                  at + after, True)["words"]
                page_says = dukpy.evaljs(
                    "var window = {};\n" + js + "\n"
                    f"window.nmasStepper.waitWords('{began}', '{length}', "
                    f"{'true' if bound else 'false'}, {(at + after) * 1000})")
                assert page_says == server, (length, bound, after)
        assert RS._wait({"began": began, "wait_s": 10}, at + 4, True)["words"] == (
            "6 s left of 10 s")
        assert RS._wait({"began": began, "wait_s": 150, "wait_bound": True}, at + 4, True)[
            "words"] == "up to 150 s: 146 s left"
        assert RS._wait({"began": began, "wait_s": 10}, at + 60, True)["words"] == (
            "its 10 s are up; waiting for the next step")
        assert dukpy.evaljs("var window = {};\n" + js + "\n"
                            "window.nmasStepper.waitWords('not a time', '10', false, 0)") is None


# ── One entry, its real step ────────────────────────────────────────────────────────────────

class TestOneEntryItsRealStep:
    def rows(self, hold_ago, run_ago):
        from modules import in_flight
        hold = {"device": "r2", "list": NET, "operation": "telemetry re-subscribe",
                "actor": TEST_PERSON, "step": "started", "step_words": "started",
                "step_ago_s": hold_ago, "stalled": hold_ago > 600,
                "started": "2026-11-11T16:38:00Z"}
        op = {"id": "j-1", "device": "re-subscribe r2's telemetry subscription 101",
              "operation": "telemetry re-subscribe", "actor": TEST_PERSON,
              "step": "starting", "own_steps": True, "step_ago_s": run_ago,
              "step_words": "Verify each within 290 s · step 9 of 11"}
        job = {"job": "j-1", "list": NET, "device": "r2", "card": "resubscribe",
               "state": "running"}
        return [in_flight.running_row(r, TEST_PERSON)
                for r in in_flight.merge([hold], [op], [job])]

    def test_the_hold_and_the_job_are_one_row_in_the_run_s_words(self):
        (row,) = self.rows(hold_ago=500, run_ago=3)
        assert row["name"] == "Re-subscribe telemetry" and row["device"] == "r2"
        assert row["step"] == "Verify each within 290 s · step 9 of 11"
        assert row["stalled"] is False

    def test_it_has_moved_when_either_the_hold_or_the_run_has(self):
        # The operator's run was held eleven minutes and noted nothing on its hold: it is not
        # stuck while its run records steps; it is when neither has moved for ten minutes.
        assert self.rows(hold_ago=660, run_ago=5)[0]["stalled"] is False
        assert self.rows(hold_ago=660, run_ago=640)[0]["stalled"] is True


# ── In a real browser ───────────────────────────────────────────────────────────────────────

def test_a_heal_s_card_advances_by_itself_and_ends_with_its_outcome_in_a_real_browser(heal):  # noqa: F811
    """The device's page left open while a heal runs: the card draws the apply, moves to the
    symptom's wait when the run does (no reload: the run's announcement), its countdown ticks,
    and at the end the outcome and the steps taken replace it."""
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the tests above still run")
    import app as nmas
    from modules.nsot import capture_job
    lead = "(document.querySelector('#device-op [data-lead]') || {getAttribute: function () { return ''; }}).getAttribute('data-lead')"
    left = "(document.querySelector('#device-op .run-left') || {}).textContent"
    job, src, d = start_heal(heal, SYSLOG_GONE, triggers=[CFG, ADJ], kinds=("missing_line",))
    try:
        src.reached("apply")
        with browser.Served(nmas.app) as srv, browser.Browser() as b:
            try:
                b.go(srv.url("/v2/device/edge-b?list=Default"))
                b.wait_for(f"return !!window.htmx && {lead} === 'apply'", 20)
                src.go("apply")
                src.reached("symptom")
                b.wait_for(f"return {lead} === 'symptom'", 20)
                first = b.js(f"return {left}")
                b.wait_for(f"return /^up to 150 s: \\d+ s left$/.test({left}) && "
                           f"{left} !== {first!r}", 20)
                src.go("symptom")
                b.wait_for("var p = document.querySelector('#device-op [data-outcome]');"
                           "return !!p && p.getAttribute('data-outcome') === 'healed'", 30)
                ended = b.js("return document.querySelector('#device-op').textContent")
            finally:
                b.go("about:blank")
                browser.close_socketio_sessions()
    finally:
        src.let_go()
    assert capture_job.wait(job, 30) and recorded(d) == "healed"
    assert re.match(r"up to 150 s: \d+ s left$", first), first
    assert "The steps taken" in ended and "healed" in ended and "Now:" not in ended


# ── One address for a run ───────────────────────────────────────────────────────────────────

class TestOneAddressForARun:
    """The operator, 2026-11-11: "The result opens on the device page for now; once the
    incident page exists, 'Open the result' goes to the incident's URL." So the address is
    built in ONE place, the `run_href` macro, and every link to a run takes it from there."""

    LINK = re.compile(r'<a\b[^>]*\bhref="([^"]*)"[^>]*>Open the (?:run|result)</a>')

    def test_every_link_to_a_run_takes_its_address_from_the_one_macro(self):
        from tests import source_index
        found = []
        for path in source_index.tracked("templates/v2", suffix=".html"):
            with open(path, encoding="utf-8") as fh:
                found += [(path.rsplit("/", 1)[-1], href) for href in self.LINK.findall(fh.read())]
        assert len(found) >= 5, f"{len(found)} links to a run found: the scan lost its sight"
        own = [(name, href) for name, href in found if not href.startswith("{{ run_href(")]
        assert own == [], f"a link to a run that builds its own address: {own}"
        assert self.LINK.findall('<a class="btn" href="{{ url_for(\'x\') }}">Open the run</a>') \
            == ["{{ url_for('x') }}"], "a planted link that builds its own is found"

    def test_the_macro_gives_the_device_s_page_in_its_network(self):
        import app as A
        with A.app.test_request_context("/v2/"):
            macro = A.app.jinja_env.get_template("v2/_macros.html").module.run_href
            assert str(macro("r2", "Lab-3")) == "/v2/device/r2?list=Lab-3"
