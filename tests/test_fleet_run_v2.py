"""Board FC phase 2 (d), FC4's approval and FC5's run, PHASE8_PLAN 22.2 (3) and (4)
(routes/intent_layers_v2.py `change_approve`, `change_go_on`, `change_run`), on r2's real
config and committed intent through the real plan, r2's row tagged, as conftest's verified
person. THE apply (`routes.deploy.apply_batch`) is replaced by a recorder: no test reaches a
device.

- **The plan's approval form** carries the change as planned, its hash, the planned devices as
  the canary, the batch size and the pause, and Approve and run, gated as an approval.
- **Approve and run** answers at once with a run card that re-reads; the job commits the layer
  once and sends r2's program through THE apply; the card says done, with r2's row.
- **A hash that is not the plan's** is not run, naming why, nothing committed or sent.
- **Paused after the canary**, the card offers Go on for the devices left; Go on runs them.
- **Go on for a run that is not paused** is refused; **an unknown run** says so.
- **The run on THE stepper** (C4232): running, the card draws the batch deploy's stepper from
  the batch deploy's own record (`deploy_job.track`), a row per device in batch order, the
  running device on its running step, a waiting one naming its batch, and it redraws as each
  device finishes; ended, each device keeps its steps one level down, a stop's failed device
  failed and the rest not reached.
"""

import re

import pytest

from modules.nsot import capture_job
from tests.test_fleet_change_plan import _head, lab, r2  # noqa: F401 (the fixtures)
from tests.test_fleet_change_run import _plan_of, sent  # noqa: F401 (the fixture)
from tests.test_fleet_plan_v2 import _plan, page  # noqa: F401 (the fixture)


def _planned(client):
    html = _plan(client, "tag-blind-lab", "ntp_servers", "(absent)", "[192.0.2.123]") \
        .get_data(as_text=True)
    job = html.split("/v2/intent/change/job/", 1)[1].split("?", 1)[0]
    assert capture_job.wait(job, 30)
    return client.get(f"/v2/intent/change/job/{job}?list=Lab&layer=tag-blind-lab") \
        .get_data(as_text=True)


def _form_of(html):
    form = re.search(r'<form[^>]*action="/v2/intent/change/approve[^"]*".*?</form>', html, re.S)
    assert form, html
    fields = re.findall(r'<input type="hidden" name="(\w+)" value="([^"]*)">', form.group(0))
    out = {}
    for k, v in fields:
        out.setdefault(k, []).append(v.replace("&#39;", "'").replace("&quot;", '"'))
    return form.group(0), out


def _run(client, job):
    assert capture_job.wait(job, 30)
    return client.get(f"/v2/intent/change/run/{job}?list=Lab&layer=tag-blind-lab") \
        .get_data(as_text=True)


class TestTheApprovalForm:
    def test_it_carries_the_planned_change_and_offers_the_canary(self, page):
        form, fields = _form_of(_planned(page))
        assert fields["path"] == ["ntp_servers"] and fields["after"] == ["[192.0.2.123]"]
        assert fields["layer"] == ["tag-blind-lab"] and len(fields["hash"][0]) == 64
        assert '<option value="r2">r2</option>' in form and 'name="batch"' in form
        assert '<option value="pause">pause for my review</option>' in form
        assert "Approve and run: canary first" in form


class TestApproveAndRun:
    def test_it_commits_once_and_sends_r2s_program_through_the_apply(self, page, r2, sent):  # noqa: F811
        head = _head(r2["repo"])
        _form, fields = _form_of(_planned(page))
        r = page.post("/v2/intent/change/approve", data=dict(
            fields, summary="Lab NTP server", reason="the lab's time source", canary="r2",
            batch="1", after_canary="pause"))
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and 'hx-trigger="nmas:fleet_change from:body' in html
        job = html.split("/v2/intent/change/run/", 1)[1].split("?", 1)[0]
        html = _run(page, job)
        assert sent["calls"] == [["r2"]], "r2's program through THE apply"
        assert "data-fc-done" in html and '<tr data-outcome="deployed"><td>canary</td><td>r2</td>' \
            in html, html
        assert _head(r2["repo"]) != head, "the layer committed"

    def test_a_hash_that_is_not_the_plans_is_not_run(self, page, r2, sent):  # noqa: F811
        head = _head(r2["repo"])
        _form, fields = _form_of(_planned(page))
        fields["hash"] = ["0" * 64]
        r = page.post("/v2/intent/change/approve", data=dict(
            fields, summary="s", reason="r", canary="r2", batch="1", after_canary="go"))
        job = r.get_data(as_text=True).split("/v2/intent/change/run/", 1)[1].split("?", 1)[0]
        html = _run(page, job)
        assert "data-fc-run-error" in html and "the plan moved since you read it" in html
        assert sent["calls"] == [] and _head(r2["repo"]) == head


class TestPausedAfterTheCanary:
    def test_the_card_offers_go_on_and_go_on_runs_the_rest(self, page, sent, monkeypatch):  # noqa: F811
        from modules.nsot import fleet_change as F
        plan = _plan_of(["r2", "r3", "r4"], monkeypatch)
        job = F.run_start("Lab", plan, "abc123", [["r2"], ["r3"], ["r4"]], after_canary="pause",
                          actor="op", actor_kind="person")
        html = _run(page, job)
        assert "data-fc-paused" in html and "Go on: the 2 left" in html, html
        r = page.post("/v2/intent/change/go-on", data={"job": job, "list": "Lab",
                                                       "layer": "tag-blind-lab"})
        rest = r.get_data(as_text=True).split("/v2/intent/change/run/", 1)[1].split("?", 1)[0]
        html = _run(page, rest)
        assert sent["calls"] == [["r2"], ["r3"], ["r4"]] and "data-fc-done" in html

    def test_go_on_pressed_twice_runs_the_rest_once(self, page, sent, monkeypatch):  # noqa: F811
        """C4235: Go on checked only that the paused job said `paused`, which it still said after
        Go on started the rest, so a second press (another person, tab, or In progress's link)
        started the same batches again. Now the first press takes the paused job over: the second
        is refused naming it, nothing is sent twice, and the paused job no longer says it waits."""
        from modules.nsot import capture_job
        from modules.nsot import fleet_change as F
        plan = _plan_of(["r2", "r3", "r4"], monkeypatch)
        job = F.run_start("Lab", plan, "abc123", [["r2"], ["r3"], ["r4"]], after_canary="pause",
                          actor="op", actor_kind="person")
        _run(page, job)
        form = {"job": job, "list": "Lab", "layer": "tag-blind-lab"}
        first = page.post("/v2/intent/change/go-on", data=form)
        second = page.post("/v2/intent/change/go-on", data=form)
        rest = first.get_data(as_text=True).split("/v2/intent/change/run/", 1)[1].split("?", 1)[0]
        _run(page, rest)
        assert second.status_code == 409, second.status_code
        assert "already" in second.get_data(as_text=True), second.get_data(as_text=True)
        for j in list(capture_job._jobs):
            capture_job.wait(j, 10)
        assert sent["calls"] == [["r2"], ["r3"], ["r4"]], sent["calls"]
        assert (capture_job.get(job)["payload"] or {}).get("state") == "continued"
        # The paused job's own card (In progress's link to it) draws the continuation, never a
        # second Go on, and never "done" for a run whose only device was the canary.
        html = _run(page, job)
        assert "Go on: the" not in html and "data-fc-paused" not in html, html
        assert html == _run(page, rest)
        from modules import in_flight
        monkeypatch.setattr("modules.nsot.device_ops.in_flight", lambda name, now: [])
        monkeypatch.setattr("modules.seen_runs.is_seen", lambda viewer, j: False)
        rows = {f.get("job") or f.get("href"): f for f in
                in_flight.chip([], "op")["finished"]}
        said = [f for f in in_flight.chip([], "op")["finished"] if "continued" in f.get("words", "")]
        assert said and said[0]["level"] == "ok", (said, rows)

    def test_go_on_for_a_run_that_is_not_paused_is_refused(self, page, sent):  # noqa: F811
        r = page.post("/v2/intent/change/go-on", data={"job": "nosuchjob", "list": "Lab",
                                                       "layer": "tag-blind-lab"})
        assert r.status_code == 409 and "is not paused after its canary" in r.get_data(as_text=True)
        assert sent["calls"] == []

    def test_go_on_for_a_finished_run_sends_nothing_more(self, page, sent, monkeypatch):  # noqa: F811
        from modules.nsot import fleet_change as F
        plan = _plan_of(["r2", "r3"], monkeypatch)
        job = F.run_start("Lab", plan, "abc123", [["r2"], ["r3"]], after_canary="go",
                          actor="op", actor_kind="person")
        assert "data-fc-done" in _run(page, job)
        r = page.post("/v2/intent/change/go-on", data={"job": job, "list": "Lab",
                                                       "layer": "tag-blind-lab"})
        assert r.status_code == 409, "a finished run is never run again"
        assert sent["calls"] == [["r2"], ["r3"]]

    def test_an_unknown_run_says_so(self, page):
        html = page.get("/v2/intent/change/run/nosuchjob?list=Lab&layer=tag-blind-lab") \
            .get_data(as_text=True)
        assert "This server has no record of that run" in html


# ── C4232: the run on THE stepper ─────────────────────────────────────────────────────────────

def announced(monkeypatch) -> list:
    """Every announcement made from here on, ``(keys, by)``, as `invalidation.announce` is
    asked; each still made."""
    from modules import invalidation

    heard, real = [], invalidation.announce

    def announce(keys, by=None, *a, **k):
        heard.append((tuple(keys), by))
        return real(keys, by, *a, **k)
    monkeypatch.setattr(invalidation, "announce", announce)
    return heard


def stepping(monkeypatch, apply_one, block_at):
    """THE apply (`routes.deploy.apply_batch`) replaced by one that steps each device as the
    real one tells its caller: *on_device*'s start, the device's hold noting the pipeline's
    stages (`device_ops.holder`, read by the stepper), *apply_one(list_name, device, kw)* its
    result, then *on_device*'s finish. At *block_at*'s turn, three stages noted, it waits until
    the test has read the running card (``(at, go)``: set when it waits, set to go on)."""
    import threading
    import time

    import routes.deploy as rd
    from modules import pipeline

    holds, at, go = {}, threading.Event(), threading.Event()
    monkeypatch.setattr("modules.nsot.device_ops.holder", lambda ln, host: (
        {"progress": {"trail": [list(x) for x in holds[host]]}} if host in holds else None))

    def apply_batch(list_name, confirmations, command_hashes, **kw):
        on, rows = kw.get("on_device"), []
        for d in confirmations:
            if on:
                on("start", d, None)
            t = time.time() - 30
            holds[d] = [(n, t + i) for i, n in enumerate(pipeline.STAGE_NAMES[:3])]
            if d == block_at:
                at.set()
                go.wait(10)
            r = apply_one(list_name, d, kw)
            # Deployed, every stage noted; failed, the trail ends at its verify.
            names = (pipeline.STAGE_NAMES if r.get("outcome") == "deployed" else
                     pipeline.STAGE_NAMES[:pipeline.STAGE_NAMES.index("verify") + 1])
            holds[d] = [(n, t + i) for i, n in enumerate(names)]
            if on:
                on("done", d, r)
            rows.append(r)
        return {"results": rows}
    monkeypatch.setattr(rd, "apply_batch", apply_batch)
    return at, go


def rows_of(html):
    """The stepper's rows as drawn: ``[(device, group, the row's markup)]``, in order."""
    return [(m.group(2), m.group(1), m.group(3)) for m in re.finditer(
        r'<li class="run-row run-row-(\w+)" data-row="([^"]+)">(.*?)(?=<li class="run-row |</ol>\s*'
        r'(?:<div class="run-final|</div>))', html, re.S)]


class TestTheRunOnTheStepper:
    """C4232: the run draws the batch deploy's live stepper (the week plan's Stage 5 item 1:
    every action reports progress through THE one stepper), from the same record."""

    CARD = "/v2/intent/change/run/{job}?list=Lab&layer=tag-blind-lab"

    def _deployed(self, fail=()):
        from modules.nsot.deploy import DEPLOYED

        def one(_ln, d, _kw):
            ok = d not in fail
            return {"device": d, "outcome": DEPLOYED if ok else "failed",
                    "reason": "" if ok else "a sent line was not read back",
                    "verify": {"ok": ok}, "checks": {"ran": True, "ok": ok}}
        return one

    def _go_on(self, page, monkeypatch):
        """r2's canary run paused, then Go on pressed (a verified person's press): the rest's
        job, r3, r4 and r5, one batch each."""
        from modules.nsot import fleet_change as F
        plan = _plan_of(["r2", "r3", "r4", "r5"], monkeypatch)
        job = F.run_start("Lab", plan, "abc123", [["r2"], ["r3"], ["r4"], ["r5"]],
                          after_canary="pause", actor="op", actor_kind="person")
        assert "data-fc-paused" in _run(page, job)
        r = page.post("/v2/intent/change/go-on", data={"job": job, "list": "Lab",
                                                       "layer": "tag-blind-lab"})
        assert r.status_code == 200, r.status_code
        return r.get_data(as_text=True).split("/v2/intent/change/run/", 1)[1].split("?", 1)[0]

    def test_running_it_draws_each_device_on_the_stepper_in_batch_order(self, page,
                                                                        monkeypatch):
        from modules import pipeline
        heard = announced(monkeypatch)
        at, go = stepping(monkeypatch, self._deployed(), block_at="r4")
        try:
            rest = self._go_on(page, monkeypatch)
            assert at.wait(10), "r4's turn came"
            html = page.get(self.CARD.format(job=rest)).get_data(as_text=True)
            moved = list(heard)
        finally:
            go.set()
        assert "nmas:device_progress from:body" in html, "it redraws as each device moves"
        # The device-write review of 2026-11-24 (MEDIUM): a device's move announces the run's
        # step key, never the batch deploy's (`deploy_job`, which wakes readers that open a
        # session to every device); a run's end announces its own keys, once.
        assert ((("device_progress",), "run-progress") in moved
                and not any(by == "deploy-job" for _k, by in moved)), moved
        assert html.count("data-run-stepper") == 1, html
        assert "Running tag-blind-lab&#39;s change · 3 devices" in html, html
        rows = rows_of(html)
        assert [(d, g) for d, g, _x in rows] == [("r3", "done"), ("r4", "running"),
                                                 ("r5", "waiting")], rows
        running = rows[1][2]
        assert re.search(r'<li class="run-step run-step-running" data-step="%s"'
                         % pipeline.STAGE_NAMES[2], running), running
        assert 'class="run-step run-step-done" data-step="%s"' % pipeline.STAGE_NAMES[0] \
            in running
        assert 'run-step-done" data-step="verify"' in rows[0][2], rows[0][2]
        assert "waiting its turn: batch 3" in rows[2][2]
        assert "running batch 2" in html, "the last row says the batch it is on"
        assert "The card redraws as it goes" not in html, "the stepper in its place"
        assert _run(page, rest).count("data-fc-done") == 1

    def test_ended_each_device_keeps_its_steps_and_a_stop_is_drawn_as_one(self, page,
                                                                          monkeypatch):
        _at, go = stepping(monkeypatch, self._deployed(fail={"r4"}), block_at="")
        go.set()
        html = _run(page, self._go_on(page, monkeypatch))
        assert "data-fc-stopped" in html and "data-fc-steps" in html, html
        rows = rows_of(html.split("data-fc-steps", 1)[1])
        assert [(d, g) for d, g, _x in rows] == [("r3", "done"), ("r4", "failed"),
                                                 ("r5", "not_reached")], rows
        assert 'run-step-done" data-step="verify"' in rows[0][2], rows[0][2]
        assert "run-step-failed" in rows[1][2] and "a sent line was not read back" in rows[1][2]
        assert '<tr data-outcome="deployed"><td>batch 1</td><td>r3</td>' in html, \
            "the rows table stays the answer"


# ── C3601: In progress lists a plan and a run, and their page reopens them ────────────────────

class TestInProgressReopensThem:
    """C3601's fleet change: a plan or a run started and left is listed by In progress with the
    intent page opened on its job as the link, and that page draws the job's card above the
    layers; never only the job's id."""

    @staticmethod
    def _rows(which, href):
        from modules import in_flight
        return [x for x in in_flight.chip([], "test-person@example.invalid")[which]
                if x.get("href") == href]

    def test_a_plan_is_listed_and_its_page_draws_the_plan(self, page, monkeypatch):
        monkeypatch.setattr("modules.nsot.device_ops.in_flight", lambda name, now: [])
        monkeypatch.setattr("modules.seen_runs.is_seen", lambda viewer, job: False)
        html = _plan(page, "tag-blind-lab", "ntp_servers", "(absent)", "[192.0.2.123]") \
            .get_data(as_text=True)
        job = html.split("/v2/intent/change/job/", 1)[1].split("?", 1)[0]
        assert capture_job.wait(job, 30)
        href = f"/v2/intent?list=Lab&layer=tag-blind-lab&plan_job={job}"
        (done,) = self._rows("finished", href)
        assert (done["level"], done["words"]) == ("ok", "ready to read"), done
        html = page.get(href).get_data(as_text=True)
        assert 'action="/v2/intent/change/approve' in html, "the plan's card, its approval"
        assert "Intent · layers · Lab" in html, "on the intent page, above the layers"

    def test_a_run_is_listed_running_and_paused_and_its_page_draws_the_run(self, page,
                                                                           monkeypatch):
        from modules.nsot import fleet_change as F
        monkeypatch.setattr("modules.nsot.device_ops.in_flight", lambda name, now: [])
        monkeypatch.setattr("modules.seen_runs.is_seen", lambda viewer, job: False)
        at, go = stepping(monkeypatch, TestTheRunOnTheStepper()._deployed(), block_at="r2")
        plan = _plan_of(["r2", "r3"], monkeypatch)
        plan["layer"]["key"] = "tag-blind-lab"
        try:
            job = F.run_start("Lab", plan, "abc123", [["r2"], ["r3"]], after_canary="pause",
                              actor="op", actor_kind="person")
            href = f"/v2/intent?list=Lab&layer=tag-blind-lab&run_job={job}"
            assert at.wait(10), "r2's turn came"
            assert len(self._rows("running", href)) == 1
            html = page.get(href).get_data(as_text=True)
            assert html.count("data-run-stepper") == 1, "the running run's stepper"
        finally:
            go.set()
        assert capture_job.wait(job, 30)
        (done,) = self._rows("finished", href)
        assert (done["level"], done["words"]) == (
            "warn", "paused after the canary: waits for your Go on"), done
        html = page.get(href).get_data(as_text=True)
        assert "data-fc-paused" in html and "Go on: the 1 left" in html, html
