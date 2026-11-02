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
