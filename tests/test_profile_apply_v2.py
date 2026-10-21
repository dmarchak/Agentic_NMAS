"""P.9 step (d2): Monitoring > Coverage's batch Apply in v2: the preview, the
rollout order, the confirm and the result, drawn server-side under the strict
policy (today's renderer emits inline handlers, which the policy refuses).

On test_profile_apply's lab with the proposal committed: r2's REAL config and
intent (it holds the profile's lines) and r6 in its real shape (r2's with
every `snmp` line removed, so the profile supplies its SNMP). The plan is
`routes.deploy.plan_devices`, the one `/deploy/plan` uses with scope
`profile`; the apply is `apply_batch`, the one `/deploy/apply` uses, run as a
job in the ROLLOUT ORDER the preview shows and sets.
"""

import html as html_mod
import json
import os
import re
import threading
import time

import pytest

from tests.test_profile_apply import _commit_proposal, lab  # noqa: F401 (the fixture)
from tests import deploy_core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def idle(lab, monkeypatch):
    """r2 as the lab holds it: every line the profile supplies already on it,
    so it has NOTHING to send (C295)."""
    _commit_proposal()
    # The lab's list is not in the registry, and a read naming an unknown
    # list is refused (C51): the test names it as known.
    monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
    return lab


@pytest.fixture
def ready(idle):
    """Two devices that each receive a program: r6 (its SNMP and LLDP) and r2,
    whose golden is a minimal edit of its REAL one with `lldp run` removed, so
    the profile supplies it that one line. Before C295 these tests ran r2 with
    nothing to send, which is the very batch the operator found useless."""
    from modules.nsot import hostvars
    from modules.nsot.parsers import get_parser
    from modules.nsot.repo import GoldenItem, save_golden, save_host_vars
    text = idle["captured"]
    assert "\nlldp run\n" in text
    edited = text.replace("\nlldp run\n", "\n")
    out = save_golden("Lab", [GoldenItem("r2", edited, "203.0.113.12", platform="cisco_iosxe")],
                      source="capture", actor="t", baseline=False)
    assert out.get("commit"), out
    # Its intent from the same edit (as r6's lab shape is built), so the line is
    # the PROFILE's to supply: a line r2's own intent held would be its own.
    hostvars.write_committed(idle["repo"], get_parser("cisco_iosxe").parse(edited))
    assert save_host_vars("Lab", ["r2"], actor="t", source="extraction")["ok"]
    return idle


def _get(lab, url):
    r = lab["client"].get(url)
    return r, r.get_data(as_text=True)


def _page(lab, devices=("r6", "r2"), extra=""):
    q = "&".join(f"device={d}" for d in devices)
    return _get(lab, f"/v2/monitoring/apply?list=Lab&{q}{extra}")


def _body(page_html):
    """The body the page's confirm posts (its `hx-vals`, C850), or None with no confirm."""
    from tests.v2_confirm import confirm_body
    return confirm_body(page_html)


def _order(page_html):
    return re.findall(r'<li class="rollout-item" data-device="([^"]+)">', page_html)


class TestNothingToSend:
    """C295 (the operator, 2026-10-01): a device that already holds every line
    the profile supplies reads "nothing to send", leaves the rollout order and
    the confirm, and a batch where every device has nothing has no confirm."""

    def test_a_device_with_nothing_to_send_leaves_the_order_and_the_confirm(self, idle):
        _r, page = _page(idle)                         # r6 receives; r2, as the lab holds it, does not
        assert _order(page) == ["r6"]
        body = _body(page)
        assert body["order"] == ["r6"] and "r2" not in body["confirmations"]
        nothing = re.search(r'<ul class="apply-not" id="apply-nothing">(.*?)</ul>', page, re.S)
        assert nothing and "<strong>r2</strong>" in nothing.group(1)
        assert "nothing to send" in nothing.group(1)
        assert 'aria-label="Move r2' not in page and 'aria-label="Leave r2 out' not in page
        assert "Apply to 1 device(s) in this order" in page

    def test_every_device_with_nothing_to_send_offers_no_confirm(self, idle):
        _r, page = _page(idle, devices=("r2",))
        assert 'id="apply-confirm"' not in page and _body(page) is None
        assert "Nothing to apply: every device chosen already has every line the profile supplies." in page
        assert "Rollout order" not in page


class TestThePreview:
    def test_the_programs_and_hashes_are_the_scoped_plans(self, ready):
        r, page = _page(ready)
        assert r.status_code == 200
        assert _order(page) == ["r6", "r2"]
        plan = deploy_core.post_plan(json={
            "devices": ["r6", "r2"], "scope": "profile", "list_name": "Lab"}).get_json()
        want = {d["device"]: d for d in plan["devices"]}
        body = _body(page)
        assert body["list"] == "Lab" and body["order"] == ["r6", "r2"]
        for name in ("r6", "r2"):
            assert body["confirmations"][name] == want[name]["capture_hash"]
            assert body["command_hashes"][name] == want[name]["command_hash"]
        # r6's program is the profile's lines, drawn MASKED on the way out.
        r6 = want["r6"]["commands"]
        assert r6 and any(c.startswith("snmp-server") for c in r6)
        assert "&lt;redacted:" in page and '<span class="apply-pos">1.</span> r6' in page

    def test_every_gate_and_operand_has_words(self, ready):
        """C296 (the operator, 2026-10-01: ten empty bullets per device). Every
        gate drawn names its check and says its state in words, and every
        operand names itself and carries a value, on every device's preview."""
        _r, page = _page(ready)
        lists = re.findall(r'<ul class="apply-gates">(.*?)</ul>', page, re.S)
        assert len(lists) == 2
        states = "passes|FAILS|does not apply|checked again at apply|not reached"
        for block in lists:
            items = re.findall(r"<li[^>]*>(.*?)</li>", block, re.S)
            assert len(items) >= 8
            for li in items:
                m = re.match(r"<strong>([^<]+)</strong> (" + states + r")\b", li.strip())
                assert m and m.group(1).strip(), li
        for block in re.findall(r'<dl class="apply-operands">(.*?)</dl>', page, re.S):
            pairs = re.findall(r"<dt>(.*?)</dt><dd><code>(.*?)</code></dd>", block, re.S)
            assert len(pairs) >= 6
            assert all(n.strip() and v.strip() for n, v in pairs), pairs

    def test_no_stored_secret_value_leaves_in_the_page(self, ready):
        from tests.test_profile_apply import _secret_values
        _r, page = _page(ready)
        for v in _secret_values(ready):
            assert v not in page

    def test_the_rollout_order_is_the_order_the_form_carries(self, ready):
        """A re-plan (a Leave out, a ticked line, a reason) is planned in the order the form's
        devices carry, which the page's moves keep (C888); `move` is Coverage's combined
        deploy's, still planned here."""
        _r, page = _page(ready, devices=("r2", "r6"))
        assert _order(page) == ["r2", "r6"] and _body(page)["order"] == ["r2", "r6"]
        _r, page = _page(ready, extra="&move=down:r6")
        assert _order(page) == ["r2", "r6"] and _body(page)["order"] == ["r2", "r6"]
        _r, page = _page(ready, extra="&move=up:r2")
        assert _order(page) == ["r2", "r6"]
        _r, page = _page(ready, extra="&drop=r2")
        assert _order(page) == ["r6"] and _body(page)["order"] == ["r6"]

    def test_earlier_and_later_ask_the_server_nothing(self, ready):
        """C888: a move plans nothing, so its buttons carry no request; Leave out still plans
        again (it changes what is confirmed). The grip is drawn on every row (C905)."""
        _r, page = _page(ready)
        rows = re.findall(r'<li class="rollout-item" data-device="[^"]+">(.*?)</li>', page, re.S)
        assert len(rows) == 2
        for row in rows:
            moves = re.findall(r'<button[^>]*data-move="(?:up|down)"[^>]*>', row)
            assert len(moves) == 2 and not any("hx-" in b for b in moves), moves
            assert re.search(r'<button[^>]*hx-get="[^"]*drop=', row)
            assert 'data-grip' in row
        first, last = rows
        assert re.search(r'data-move="up" disabled', first) and \
            not re.search(r'data-move="down" disabled', first)
        assert re.search(r'data-move="down" disabled', last)
        assert 'id="rollout-said" aria-live="polite"' in page

    def test_the_rollout_order_says_why_it_matters(self, ready):
        _r, page = _page(ready)
        assert "One device at a time, in this order." in page
        assert "the first devices are the ones a bad change would reach" in page

    def test_no_device_chosen_says_where_to_choose(self, ready):
        _r, page = _get(ready, "/v2/monitoring/apply?list=Lab")
        assert "No device was chosen" in page and 'id="apply-confirm"' not in page

    def test_the_fragment_replans_under_the_strict_policy(self, ready):
        from modules import csp
        for url in ("/v2/monitoring/apply?list=Lab&device=r6",
                    "/v2/monitoring/apply/preview?list=Lab&device=r6"):
            r, html = _get(ready, url)
            assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY, url
            assert not re.search(r"\sstyle=|\son[a-z]+=|<script(?![^>]*\ssrc=)", html), url
        r, frag = _get(ready, "/v2/monitoring/apply/preview?list=Lab&device=r6")
        assert frag.lstrip().startswith('<section class="card apply" id="apply-preview">')
        assert 'hx-trigger="change"' in frag

    def test_a_device_that_cannot_receive_it_says_why_and_is_not_confirmed(self, ready, monkeypatch):
        from modules.nsot import device_ops
        monkeypatch.setattr(device_ops, "busy_text",
                            lambda ln, host: "held by a deploy since 01:00" if host == "r6" else "")
        _r, page = _page(ready)
        assert "held by a deploy since 01:00" in page
        assert _body(page)["order"] == ["r2"]


def _confirm(lab, body):
    """Post the confirm as the page's button does (C850)."""
    from tests.v2_confirm import post_confirm
    return post_confirm(lab["client"], "/v2/monitoring/apply/confirm", body)


def _out(r):
    """The job the confirm's answer drew, and where its card is read again."""
    from tests.v2_confirm import job_of, job_url
    job = job_of(r)
    assert job, r.get_data(as_text=True)[:500]
    return {"job": job, "url": job_url(job)}


class TestTheConfirm:
    def _spy(self, monkeypatch, gate=None):
        import routes.deploy as rd
        reached = []

        def spy(entry, list_name, rows, authorise, **kw):
            name = entry["artifact"].device
            reached.append((name, kw.get("scope", "")))
            if gate is not None and name == "r2":
                gate.wait(10)
            return {"device": name, "outcome": "deployed", "commands": ["x"]}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        return reached

    def test_the_batch_runs_as_a_job_in_the_rollout_order(self, ready, monkeypatch):
        from modules.nsot import capture_job
        reached = self._spy(monkeypatch)
        # The order the PAGE set, and not alphabetical (a sorted run would pass
        # an alphabetical one: the control that sorts it found that).
        _r, page = _page(ready, devices=("r2", "r6"), extra="&move=down:r2")
        assert _body(page)["order"] == ["r6", "r2"]
        r = _confirm(ready, _body(page))
        assert r.status_code == 202, r.get_data(as_text=True)
        out = _out(r)
        assert capture_job.wait(out["job"], 20)
        assert reached == [("r6", "profile"), ("r2", "profile")]
        rr, frag = _get(ready, out["url"])
        assert rr.status_code == 200
        assert "2 of 2 device(s) deployed" in frag and "every device in the batch appears here" in frag
        assert "hx-trigger" not in frag, "a finished batch listens for nothing"

    def test_the_confirm_binds_and_records_the_order_it_carries(self, ready, monkeypatch,
                                                               caplog):
        """C888: the order is set in the page and sent at the confirm. No hash covers it (each
        device's is its own program), so the route binds it: run in exactly that order, the
        job's record, its log line and the receipts in it; an order that is not exactly the
        confirmed devices, each once, is refused naming both, with nothing started."""
        import logging

        from modules import deploy_job
        from modules.nsot import capture_job, receipts
        reached = self._spy(monkeypatch)
        _r, page = _page(ready)                      # the preview draws r6, then r2
        body = _body(page)
        assert body["order"] == ["r6", "r2"]
        for bad, named in ((["r6"], "(r6)"), (["r6", "r2", "r6"], "(r6, r2, r6)"),
                           ([], None)):
            r = _confirm(ready, dict(body, order=bad))
            html = r.get_data(as_text=True)
            assert r.status_code == 400 and "Nothing was sent" in html, html
            if named:
                assert f"the rollout order sent {named} is not exactly the devices this " \
                       "confirm carries hashes for (r2, r6)" in html, html
        assert reached == [], "a refused order started a batch"
        with caplog.at_level(logging.INFO, logger="modules.deploy_job"):
            r = _confirm(ready, dict(body, order=["r2", "r6"]))  # the person's order, not drawn
        assert r.status_code == 202, r.get_data(as_text=True)
        out = _out(r)
        assert capture_job.wait(out["job"], 20)
        assert reached == [("r2", "profile"), ("r6", "profile")]
        assert deploy_job.state(out["job"])["order"] == ["r2", "r6"]
        assert any("on 2 device(s): r2, r6 started by" in m for m in caplog.messages), \
            caplog.messages
        rows = [x for x in receipts.read("Lab")["rows"] if x.get("run_id")]
        run = rows[0]["run_id"]
        assert [x["device"] for x in reversed(rows) if x["run_id"] == run] == ["r2", "r6"]

    def test_the_golden_commit_names_the_person_who_confirmed(self, ready, monkeypatch):
        """The review's finding, 2026-10-01: the job thread has no request, so
        `request_actor()` there reads `unauthenticated`, and the batch's golden
        commit named nobody while the receipts named the person. The actor
        the confirm verified is carried into the commit."""
        import routes.deploy as rd
        from modules import identity
        from modules.nsot import capture_job
        self._spy(monkeypatch)
        committed = []
        monkeypatch.setattr(rd, "_commit_batch_golden",
                            lambda ln, report, **kw: committed.append(kw.get("actor")) or {})
        seen = []
        real = identity.request_actor
        monkeypatch.setattr(identity, "request_actor", lambda: seen.append(real()) or seen[-1])
        _r, page = _page(ready, devices=("r6",))
        out = _out(_confirm(ready, _body(page)))
        assert capture_job.wait(out["job"], 20)
        person = seen[0]
        assert person and person != "unauthenticated", seen
        assert committed == [person], (committed, person)

    def test_while_it_runs_each_device_reads_where_the_batch_is(self, ready, monkeypatch):
        from modules.nsot import capture_job
        gate = threading.Event()
        self._spy(monkeypatch, gate)
        _r, page = _page(ready)                      # r6 first, then r2
        out = _out(_confirm(ready, _body(page)))
        try:
            # Wait for the state photographed below, r6 done AND r2 being applied (C422: "being
            # applied" alone is also r6's state before its spy returns, and under the gate's
            # load the fragment was read then).
            for _ in range(200):
                _rr, frag = _get(ready, out["url"])
                if 'run-row-done" data-row="r6"' in frag and \
                        'run-row-running" data-row="r2"' in frag:
                    break
                threading.Event().wait(0.02)
            # On THE stepper (2026-10-12): redrawn as each device ends and as each step moves.
            assert ('hx-trigger="nmas:deploy_job from:body, nmas:device_progress from:body"'
                    in frag)
            assert frag.index('data-row="r6"') < frag.index('data-row="r2"')
            # r6 finished; its record is committed only when the batch ends (R5's receipts)
            assert 'class="run-row run-row-done" data-row="r6"' in frag
            assert "done; its record is committed when the batch ends" in frag
            assert 'class="run-row run-row-running" data-row="r2"' in frag    # r2 running
            assert 'aria-current="step"' in frag and "<progress" in frag
            assert "Check now" in frag
        finally:
            gate.set()
            capture_job.wait(out["job"], 20)

    def test_a_program_that_moved_is_refused_alone_with_nothing_sent(self, ready, monkeypatch):
        from modules.nsot import capture_job
        reached = self._spy(monkeypatch)
        _r, page = _page(ready)
        body = _body(page)
        body["command_hashes"]["r6"] = "0" * 16
        out = _out(_confirm(ready, body))
        assert capture_job.wait(out["job"], 20)
        assert reached == [("r2", "profile")]
        _rr, frag = _get(ready, out["url"])
        assert "the exact command list changed since you confirmed" in frag
        # Its progress row reads refused, never "not reached" (the breaker's
        # words): the review's finding, 2026-10-01.
        from modules import deploy_job
        steps = {s["device"]: s for s in deploy_job.state(out["job"])["steps"]}
        assert steps["r6"]["state"] == "done" and steps["r6"]["outcome"] == "refused", steps["r6"]

    def test_a_finished_batch_offers_retry_for_each_device_it_did_not_deploy(self, ready,
                                                                           monkeypatch):
        """C1499 (step 6, 2026-10-21): a batch that committed intent first and failed on one
        device left it with no way back from the card. Each device the batch did not deploy
        gets Retry <device>, a new preview of that device alone on the batch's scope; a
        deployed one gets none."""
        import routes.deploy as rd
        from urllib.parse import parse_qs, urlsplit

        from modules.nsot import capture_job

        def spy(entry, list_name, rows, authorise, **kw):
            name = entry["artifact"].device
            if name == "r6":
                return {"device": name, "outcome": "failed", "stage": "pre_snapshot",
                        "reason": "Pre-snapshot failed for 1 device(s)"}
            return {"device": name, "outcome": "deployed", "commands": ["x"]}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        _r, page = _page(ready, devices=("r2", "r6"))
        out = _out(_confirm(ready, _body(page)))
        assert capture_job.wait(out["job"], 20)
        _rr, frag = _get(ready, out["url"])
        retry = re.findall(r'id="apply-retry-([^"]+)"[^>]* href="([^"]+)"', frag)
        assert [d for d, _h in retry] == ["r6"], frag[:3000]
        url = urlsplit(html_mod.unescape(retry[0][1]))
        assert url.path == "/v2/monitoring/apply" and parse_qs(url.query) == {
            "list": ["Lab"], "scope": ["profile"], "device": ["r6"]}

    def test_the_confirm_refuses_what_carries_nothing(self, ready):
        r = _confirm(ready, {"order": ["r6"], "confirmations": {"r6": "x"},
                             "command_hashes": {"r6": "y"}})
        assert r.status_code == 400 and "No known list" in r.get_data(as_text=True)
        r = _confirm(ready, {"list": "Nowhere", "order": ["r6"], "confirmations": {"r6": "x"},
                             "command_hashes": {"r6": "y"}})
        assert r.status_code == 400
        r = _confirm(ready, {"list": "Lab", "order": ["r6"], "confirmations": {"r6": "x"}})
        assert r.status_code == 400 and "Nothing confirmed" in r.get_data(as_text=True)
        # Lab 7 (b), the second sample (a hand mutant: mutmut makes none of a decorated route):
        # a confirm naming its list and no device starts no batch.
        r = _confirm(ready, {"list": "Lab"})
        assert r.status_code == 400 and "Nothing confirmed" in r.get_data(as_text=True)
        # C850: each structured field arrives as JSON in its form field; one of another kind is
        # refused naming it, drawn in place as a refusal (a fragment), never a 500.
        r = _confirm(ready, {"list": "Lab", "order": {"r6": 1}, "confirmations": {"r6": "x"},
                             "command_hashes": {"r6": "y"}})
        html = r.get_data(as_text=True)
        assert r.status_code == 400 and "the field order is not a list" in html, html
        assert 'role="alert"' in html and "Nothing was sent" in html
        r = _confirm(ready, {"list": "Lab", "order": ["r6"], "confirmations": "{not json",
                             "command_hashes": {"r6": "y"}})
        assert r.status_code == 400 and "the field confirmations is not readable JSON" in \
            r.get_data(as_text=True)

    def test_an_unknown_job_says_so(self, ready):
        r, frag = _get(ready, "/v2/monitoring/apply/job/nope")
        assert r.status_code == 404 and "no record of that batch" in frag

    @pytest.mark.parametrize("record", [
        # A job record with no `list` field (the suite's KeyError: 'list', C839), as a stand-in
        # for `state()` would hand it; and the real `state()` of a job kept without one.
        "state_without_list", "job_without_list"])
    def test_a_job_record_naming_no_network_is_refused_naming_that(self, ready, monkeypatch,
                                                                   record):
        from modules import deploy_job
        from modules.nsot import capture_job
        if record == "state_without_list":
            monkeypatch.setattr(deploy_job, "state", lambda job: {
                "job": job, "state": "done", "order": ["r6"], "steps": [], "elapsed_s": 1,
                "payload": None, "error": ""})
        else:
            monkeypatch.setattr(capture_job, "get", lambda job: {
                "state": "done", "elapsed_s": 1, "payload": None, "error": ""})
        try:
            r, frag = _get(ready, "/v2/monitoring/apply/job/j1")
        except KeyError as exc:                       # the app propagates under test
            pytest.fail(f"a record naming no network raised KeyError {exc}")
        assert r.status_code == 409, (r.status_code, frag[:300])
        assert frag.startswith("Couldn&#x27;t load: the batch j1 has a record that names no "
                               "network"), frag[:300]

    def test_the_confirm_is_gated_and_invalidates_through_its_announcer(self):
        from modules import invalidation, route_gates
        assert route_gates.GATES["v2.profile_apply_confirm"].kind == "confirm"
        assert isinstance(invalidation.DECLARED["v2.profile_apply_confirm"],
                          invalidation.Nothing)
        assert "deploy_job" in invalidation.ANNOUNCERS["deploy-job"]


class TestTheShippedClient:
    def _js(self):
        return open(os.path.join(ROOT, "static", "js", "nmas_apply.js"), encoding="utf-8").read()

    def _started(self, detail):
        import dukpy
        return dukpy.evaljs("var window = {};\n" + self._js()
                            + f"\nwindow.NMAS_APPLY.startedBatch({json.dumps(detail)})")

    def test_only_a_started_batch_locks_the_preview(self):
        """The confirm's answer swapped into #apply-result (C850): 202 locks the preview
        (C602); a refusal, or a swap anywhere else, does not."""
        assert self._started({"target": {"id": "apply-result"}, "xhr": {"status": 202}}) is True
        assert self._started({"target": {"id": "apply-result"}, "xhr": {"status": 400}}) is False
        assert self._started({"target": {"id": "apply-job"}, "xhr": {"status": 202}}) is False
        assert self._started(None) is False

    def _pure(self, call):
        import dukpy
        return dukpy.evaljs("var window = {};\n" + self._js() + f"\nwindow.NMAS_APPLY.{call}")

    def test_a_note_is_drawn_only_for_a_batch_this_preview_started(self):
        """C883: no note on a preview no batch started from; 'running' while its card runs;
        'ended' after."""
        assert self._pure("lockNote(false, false)") == ""
        assert self._pure("lockNote(false, true)") == ""
        assert self._pure("lockNote(true, true)") == "running"
        assert self._pure("lockNote(true, false)") == "ended"

    def test_a_move_puts_one_device_in_one_place(self):
        """C888, C905: the order a move leaves, the slot a drag lands in, and what the
        confirm sends."""
        names = '["r1", "r2", "r3", "r4"]'
        assert self._pure(f"moved({names}, 0, 1)") == ["r2", "r1", "r3", "r4"]
        assert self._pure(f"moved({names}, 3, 0)") == ["r4", "r1", "r2", "r3"]
        assert self._pure(f"moved({names}, 1, 3)") == ["r1", "r3", "r4", "r2"]
        assert self._pure(f"moved({names}, 2, 2)") == ["r1", "r2", "r3", "r4"]
        # The other rows' middles at 10, 30, 50 px: above all, between, below all.
        assert self._pure("slotFor([10, 30, 50], 5)") == 0
        assert self._pure("slotFor([10, 30, 50], 31)") == 2
        assert self._pure("slotFor([10, 30, 50], 99)") == 3
        # The confirmed devices in the order shown; one the list lacks is left for the route
        # to refuse, never placed by guess; one shown and not confirmed is not sent.
        assert self._pure('confirmOrder(["r2", "r6"], ["r6", "r2"])') == ["r2", "r6"]
        assert self._pure('confirmOrder(["r2", "x", "r6"], ["r6", "r2"])') == ["r2", "r6"]
        assert self._pure('confirmOrder(["r2"], ["r6", "r2"])') == ["r2"]
        assert self._pure('movedWords("r6", 1, 2, 0)') == "r6 moved to 2 of 2."
        assert self._pure('movedWords("r6", 0, 2, 0)') == "r6 stays at 1 of 2."

    def test_the_component_reads_its_attributes_from_its_root(self):
        src = self._js()
        assert "this.$el" not in src and "self.$el" not in src

    def test_the_frame_loads_it_and_the_confirm_is_htmx(self, ready):
        """The confirm is the one pattern (C850): htmx posts it, busy on itself, gated by
        `may`, carrying the hashes the route binds it to; no Alpine component posts it."""
        _r, page = _page(ready)
        assert re.search(r'<script defer src="/static/js/nmas_apply\.js[^"]*"></script>', page)
        assert 'x-data="applyConfirm"' not in page and "applyConfirm" not in self._js()
        from tests.v2_confirm import button
        tag = button(page)
        assert 'hx-post="/v2/monitoring/apply/confirm?list=Lab"' in tag
        assert 'hx-target="#apply-result"' in tag and 'hx-disabled-elt="this"' in tag
        assert _body(page)["command_hashes"].keys() == {"r6", "r2"}


class TestASupersededLine:
    """r6 holding ANOTHER community beside the one the profile supplies: the
    old line is offered for removal (Mode B; `snmp-server community` is
    measured exact on both platforms), never removed unless ticked, and a
    ticked one needs its stated reason before the device can be confirmed."""

    @pytest.fixture
    def old(self, ready):
        from modules.nsot.repo import GoldenItem, save_golden
        cfg = ready["r6"].replace("\nend", "\nsnmp-server community OLDCOMMUNITY RO\nend")
        assert cfg != ready["r6"]
        save_golden("Lab", [GoldenItem("r6", cfg, "203.0.113.16", platform="cisco_iosxe")],
                    source="capture", actor="t", baseline=False)
        return ready

    def _id(self, page):
        m = re.search(r'name="rm::r6" value="([0-9a-f]+)"', page)
        assert m, "the superseded line is offered with its box"
        return m.group(1)

    def test_it_is_offered_and_never_removed_unticked(self, old):
        _r, page = _page(old, devices=("r6",))
        self._id(page)
        assert "OLDCOMMUNITY" not in page and "snmp-server community &lt;redacted:" in page
        assert "<strong>will be removed</strong>" not in page and not _body(page).get("remove")

    def test_ticked_it_waits_on_a_reason_then_carries_it(self, old):
        _r, page = _page(old, devices=("r6",))
        rid = self._id(page)
        _r, ticked = _page(old, devices=("r6",), extra=f"&rm::r6={rid}")
        assert "will be removed" in ticked and f'name="why::r6::{rid}"' in ticked
        assert _body(ticked) is None, "no reason yet: r6 cannot be confirmed"
        _r, why = _page(old, devices=("r6",),
                        extra=f"&rm::r6={rid}&why::r6::{rid}=the+old+collector+is+retired")
        body = _body(why)
        assert body["remove"] == {"r6": [rid]}
        (auth,) = body["authorise"]["r6"]
        assert auth["reason"] == "the old collector is retired" and "OLDCOMMUNITY" not in auth["line"]
        assert body["command_hashes"]["r6"] != _body(page)["command_hashes"]["r6"]

    def test_the_confirmed_removal_reaches_the_device_path(self, old, monkeypatch):
        import routes.deploy as rd
        from modules.nsot import capture_job
        seen = []

        def spy(entry, list_name, rows, authorise, **kw):
            seen.append((kw.get("remove"), authorise))
            return {"device": entry["artifact"].device, "outcome": "deployed", "commands": ["x"]}
        monkeypatch.setattr(rd, "_deploy_one", spy)
        monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
        _r, page = _page(old, devices=("r6",))
        rid = self._id(page)
        _r, why = _page(old, devices=("r6",),
                        extra=f"&rm::r6={rid}&why::r6::{rid}=the+old+collector+is+retired")
        out = _out(_confirm(old, _body(why)))
        assert capture_job.wait(out["job"], 20)
        (remove, authorise), = seen
        assert remove == {"r6": [rid]} and authorise["r6"][0]["reason"] == "the old collector is retired"


# ------------------------------------------------ clicking what ships
#
# C243's lesson (the Update button's first real run was disabled by its own
# wiring): the page is loaded in a REAL browser and its shipped controls
# clicked, where Firefox runs. Skipped, saying why, where it cannot start.

@pytest.fixture(scope="module")
def live_browser():
    from tests import browser
    ok, why = browser.available()
    if not ok:
        pytest.skip(f"no real browser here ({why}); the client's pure logic and the "
                    "$root rule above still run")
    import app as A
    with browser.Served(A.app) as srv, browser.Browser() as b:
        yield browser, srv, b


_SETTLED = ("var c=document.querySelector('#apply-confirm');"
            "return window.Alpine && window.htmx && window.NMAS_DRAG && c && !c.disabled && "
            "!document.querySelector('.htmx-swapping, .htmx-settling, .htmx-request')")

#: What a browser test watches: every request a control in the preview makes (its verb, path,
#: and the order it carries), and every preview request as it finishes.
_WATCH = """
window.__seen = []; window.__done = [];
document.body.addEventListener('htmx:beforeRequest', function (e) {
  var el = e.detail.elt;
  if (el && el.closest && el.closest('#apply-preview')) {
    var p = e.detail.requestConfig.parameters;
    window.__seen.push(e.detail.requestConfig.verb.toUpperCase() + ' ' +
                       e.detail.pathInfo.requestPath + (p && p.order ? ' ' + p.order : ''));
  }
});
document.body.addEventListener('htmx:afterRequest', function (e) {
  window.__done.push(e.detail.pathInfo.requestPath); });
return 1
"""

#: The page as the person reads it: the rollout list, each device's section with its number,
#: and the form's devices (what a re-plan carries).
_READ = """
function attr(sel, a) { return Array.prototype.map.call(document.querySelectorAll(sel),
  function (x) { return a ? x.getAttribute(a) : x.textContent.trim(); }); }
return {list: attr('#rollout li[data-device]', 'data-device'),
        sections: attr('section.apply-device h2', null).map(function (t) {
          return t.split(/\\s+/).slice(0, 2).join(' '); }),
        fields: attr('#apply-form input[type=hidden][name=device]', 'value'),
        said: (document.getElementById('rollout-said') || {}).textContent || ''}
"""

#: Whether an element is drawn at all (C883: `hidden` was set and the note was drawn anyway).
_SHOWN = ("var n=document.getElementById(arguments[0]);"
          "return !!n && getComputedStyle(n).display !== 'none' && n.getClientRects().length > 0")


def _pointer(b, steps):
    b._call("POST", f"/session/{b.session}/actions", {"actions": [{
        "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
        "actions": steps}]})


def _element(b, css):
    return b._call("POST", f"/session/{b.session}/element", {"using": "css selector",
                                                              "value": css})


def _grip(name):
    return f'#rollout li[data-device="{name}"] [data-grip]'


def _to_below(b, dragged, past):
    """How far down the pointer moves from *dragged*'s grip to land below *past*'s middle
    (the browser's own geometry, never the script's)."""
    return int(b.js(
        "var g=document.querySelector(arguments[0]).getBoundingClientRect();"
        "var r=document.querySelector(arguments[1]).getBoundingClientRect();"
        "return Math.round(r.top + r.height * 0.8 - (g.top + g.height / 2))",
        _grip(dragged), f'#rollout li[data-device="{past}"]'))


def _wait_done(b):
    """The job's card once it says the batch finished, asking with Check now meanwhile."""
    text = ""
    for _ in range(40):
        text = b.wait_for("var j=document.querySelector('#apply-job');"
                          "return j && j.textContent")
        if "device(s) deployed" in text:
            return text
        b.js("var x=document.querySelector('#apply-job button'); if (x) x.click(); return 1")
        time.sleep(0.25)
    return text


@pytest.fixture
def spied(monkeypatch):
    """The device path spied: the devices reached, in order, with an optional gate holding the
    batch at its first device."""
    import routes.deploy as rd
    reached, gate, started = [], threading.Event(), threading.Event()
    gate.set()

    def spy(entry, list_name, rows, authorise, **kw):
        started.set()
        gate.wait(30)
        reached.append(entry["artifact"].device)
        return {"device": entry["artifact"].device, "outcome": "deployed", "commands": ["x"]}
    monkeypatch.setattr(rd, "_deploy_one", spy)
    monkeypatch.setattr(rd, "_commit_batch_golden", lambda *a, **k: {})
    return {"reached": reached, "gate": gate, "started": started}


class TestClickingTheShippedPage:
    def test_earlier_and_later_move_in_the_page_and_the_confirm_carries_it(
            self, ready, spied, live_browser):
        """C888: Later on r6 moves it at once, the sections and their numbers and the form's
        devices with it, asking nothing; the confirm is the one request, carrying the order
        shown, and the batch runs in it."""
        browser, srv, b = live_browser
        try:
            b.go(srv.url("/v2/monitoring/apply?list=Lab&device=r6&device=r2"))
            b.wait_for(_SETTLED)
            b.js(_WATCH)
            assert b.js("return document.querySelector('#apply-confirm .op-idle')"
                        ".textContent.trim()") == "Apply to 2 device(s) in this order"
            b.click('button[aria-label="Move r6 later"]')
            page = b.js(_READ)                      # read at once: nothing was waited for
            assert page["list"] == ["r2", "r6"], page
            assert page["sections"] == ["1. r2", "2. r6"], page
            assert page["fields"] == ["r2", "r6"], page
            assert page["said"] == "r6 moved to 2 of 2.", page
            assert b.js("return [document.querySelector('[aria-label=\"Move r2 earlier\"]')"
                        ".disabled, document.querySelector('[aria-label=\"Move r6 later\"]')"
                        ".disabled, document.activeElement.getAttribute('aria-label')]") \
                == [True, True, "Move r6 earlier"]
            b.click('button[aria-label="Move r6 earlier"]')
            b.click('button[aria-label="Move r6 later"]')
            time.sleep(0.5)
            assert b.js("return window.__seen") == [], "a move asked the server"
            b.click("#apply-confirm")
            assert "2 of 2 device(s) deployed" in _wait_done(b)
            assert b.js("return window.__seen") == [
                'POST /v2/monitoring/apply/confirm?list=Lab ["r2","r6"]']
            assert spied["reached"] == ["r2", "r6"]
            # The confirm drawn again by the answer (C850), never offered twice.
            assert b.js("return document.querySelector('#apply-confirm').disabled") is True
            assert b.js("return document.querySelector('#apply-confirm').textContent.trim()") \
                == "Started: its progress is below"
        finally:
            b.go("about:blank")
            browser.close_socketio_sessions()

    def test_a_drag_by_the_grip_moves_in_the_page_and_the_confirm_carries_it(
            self, ready, spied, live_browser):
        """C905: r6 dragged by its grip below r2 lands there, said for a screen reader, with
        no request; the confirm carries the order shown and the batch runs in it."""
        browser, srv, b = live_browser
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/monitoring/apply?list=Lab&device=r6&device=r2"))
            b.wait_for(_SETTLED)
            b.js(_WATCH)
            dy = _to_below(b, "r6", "r2")
            _pointer(b, [{"type": "pointerMove", "origin": _element(b, _grip("r6")),
                          "x": 0, "y": 0},
                         {"type": "pointerDown", "button": 0},
                         {"type": "pointerMove", "origin": "pointer", "x": 0, "y": dy // 2,
                          "duration": 100}])
            assert "Moving r6, at 1 of 2" in b.js(_READ)["said"]
            assert b.js("return document.querySelector('#rollout li[data-device=\"r6\"]')"
                        ".classList.contains('rollout-dragging')")
            _pointer(b, [{"type": "pointerMove", "origin": "pointer", "x": 0, "y": dy - dy // 2,
                          "duration": 100},
                         {"type": "pointerUp", "button": 0}])
            b._call("DELETE", f"/session/{b.session}/actions")
            page = b.js(_READ)
            assert page["list"] == ["r2", "r6"], page
            assert page["sections"] == ["1. r2", "2. r6"] and page["fields"] == ["r2", "r6"]
            assert page["said"] == "r6 moved to 2 of 2.", page
            assert not b.js("return document.querySelector('.rollout-dragging, "
                            ".rollout-before, .rollout-after')")
            time.sleep(0.5)
            assert b.js("return window.__seen") == [], "a drag asked the server"
            b.click("#apply-confirm")
            assert "2 of 2 device(s) deployed" in _wait_done(b)
            assert b.js("return window.__seen") == [
                'POST /v2/monitoring/apply/confirm?list=Lab ["r2","r6"]']
            assert spied["reached"] == ["r2", "r6"]
        finally:
            b._call("DELETE", f"/session/{b.session}/actions")
            b.go("about:blank")
            browser.close_socketio_sessions()

    def test_a_drop_outside_the_list_changes_nothing(self, ready, spied, live_browser):
        """C905: let go well above the list, r6 stays first, and that is said."""
        browser, srv, b = live_browser
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/monitoring/apply?list=Lab&device=r6&device=r2"))
            b.wait_for(_SETTLED)
            b.js(_WATCH)
            dy = _to_below(b, "r6", "r2")
            _pointer(b, [{"type": "pointerMove", "origin": _element(b, _grip("r6")),
                          "x": 0, "y": 0},
                         {"type": "pointerDown", "button": 0},
                         {"type": "pointerMove", "origin": "pointer", "x": 0, "y": dy,
                          "duration": 100},
                         {"type": "pointerMove", "origin": "pointer", "x": 0, "y": -dy - 120,
                          "duration": 100},
                         {"type": "pointerUp", "button": 0}])
            b._call("DELETE", f"/session/{b.session}/actions")
            page = b.js(_READ)
            assert page["list"] == ["r6", "r2"] and page["fields"] == ["r6", "r2"], page
            assert page["said"] == "r6 was let go outside the list: the order is as it was."
            assert b.js("return window.__seen") == []
        finally:
            b._call("DELETE", f"/session/{b.session}/actions")
            b.go("about:blank")
            browser.close_socketio_sessions()

    def test_an_answer_landing_mid_drag_does_not_move_the_list(self, ready, spied,
                                                               live_browser, monkeypatch):
        """C905 with C882's guard: a re-plan asked as the grip is pressed (a reason typed, its
        `change` fired) answers mid-drag. Nothing is redrawn under the pointer: the row is the
        element first drawn and the order is as it was. On the drop the row lands where the
        pointer let go, and the preview is planned again in THAT order (the answer set aside
        was planned in the old one)."""
        import routes.deploy as rd
        real_plan = rd.plan_devices

        def slow_plan(*a, **k):
            time.sleep(1.0)
            return real_plan(*a, **k)
        browser, srv, b = live_browser
        try:
            b._call("POST", f"/session/{b.session}/window/rect", {"width": 1280, "height": 1000})
            b.go(srv.url("/v2/monitoring/apply?list=Lab&device=r6&device=r2"))
            b.wait_for(_SETTLED)
            b.js(_WATCH)
            b.js("window.__r6 = document.querySelector('#rollout li[data-device=\"r6\"]');"
                 "return 1")
            monkeypatch.setattr(rd, "plan_devices", slow_plan)
            dy = _to_below(b, "r6", "r2")
            _pointer(b, [{"type": "pointerMove", "origin": _element(b, _grip("r6")),
                          "x": 0, "y": 0},
                         {"type": "pointerDown", "button": 0},
                         {"type": "pointerMove", "origin": "pointer", "x": 0, "y": 4,
                          "duration": 50}])
            b.js("htmx.trigger(document.getElementById('apply-form'), 'change'); return 1")
            b.wait_for("return window.__done.filter(function (p) {"
                       " return p.indexOf('/v2/monitoring/apply/preview') === 0; }).length === 1", 15)
            time.sleep(0.3)
            assert b.js("return window.__r6.isConnected"), "the list was redrawn mid-drag"
            assert b.js(_READ)["list"] == ["r6", "r2"]
            _pointer(b, [{"type": "pointerMove", "origin": "pointer", "x": 0, "y": dy - 4,
                          "duration": 100},
                         {"type": "pointerUp", "button": 0}])
            b._call("DELETE", f"/session/{b.session}/actions")
            # Planned again from the form, which now carries r2 first.
            b.wait_for("return window.__done.filter(function (p) {"
                       " return p.indexOf('/v2/monitoring/apply/preview') === 0; }).length === 2", 15)
            b.wait_for("return !window.__r6.isConnected")
            b.wait_for(_SETTLED, 15)
            page = b.js(_READ)
            assert page["list"] == ["r2", "r6"] and page["sections"] == ["1. r2", "2. r6"], page
            # And the confirm the server drew from that plan carries it.
            vals = json.loads(b.js("return document.getElementById('apply-confirm')"
                                   ".getAttribute('hx-vals')"))
            assert json.loads(vals["order"]) == ["r2", "r6"], vals
        finally:
            b._call("DELETE", f"/session/{b.session}/actions")
            b.go("about:blank")
            browser.close_socketio_sessions()

    @pytest.mark.parametrize("lab_state,devices", [("idle", ("r2",)), ("ready", ("r6", "r2"))],
                             ids=["nothing-to-send", "two-of-two"])
    def test_the_running_note_is_drawn_only_while_its_batch_runs(self, request, spied,
                                                                 live_browser, lab_state,
                                                                 devices):
        """C883 (the operator's walk W1): "The batch is running…" was drawn before anything was
        confirmed, with nothing to send and with 2 of 2. Neither note is drawn on a preview;
        the running one only once the confirm started a batch and while its card runs; the
        ended one once it has finished."""
        request.getfixturevalue(lab_state)
        browser, srv, b = live_browser
        q = "&".join(f"device={d}" for d in devices)
        try:
            b.go(srv.url(f"/v2/monitoring/apply?list=Lab&{q}"))
            b.wait_for("return window.htmx && document.getElementById('apply-preview')")
            assert b.js(_SHOWN, "apply-locked") is False
            assert b.js(_SHOWN, "apply-ended") is False
            text = b.js("return document.body.innerText")
            assert "The batch is running" not in text and "has ended" not in text
            if len(devices) == 1:
                assert b.js("return !document.getElementById('apply-confirm')")
                return
            b.wait_for(_SETTLED)
            spied["gate"].clear()
            b.click("#apply-confirm")
            assert spied["started"].wait(30), "the batch never reached its first device"
            b.wait_for(_SHOWN, 10, "apply-locked")
            assert b.js(_SHOWN, "apply-ended") is False
            assert b.js("return document.querySelector('[aria-label=\"Move r6 later\"]')"
                        ".getAttribute('title')").startswith("The batch is running")
            spied["gate"].set()
            assert "2 of 2 device(s) deployed" in _wait_done(b)
            b.wait_for(_SHOWN, 10, "apply-ended")
            assert b.js(_SHOWN, "apply-locked") is False
            assert b.js("return document.querySelector('[aria-label=\"Move r6 later\"]')"
                        ".getAttribute('title')").startswith("The batch confirmed here has ended")
        finally:
            spied["gate"].set()
            b.go("about:blank")
            browser.close_socketio_sessions()


# ------------------------------------------------ the device page (P.9 d3)

R2 = {"hostname": "r2", "ip": "203.0.113.12", "device_type": "cisco_xe",
      "platform": "cisco_iosxe", "role": "router"}
R6 = {"hostname": "r6", "ip": "203.0.113.16", "device_type": "cisco_xe",
      "platform": "cisco_iosxe", "role": "router"}


class TestMonitoredBy:
    """The device page's Monitoring tab opens with what the device is
    monitored by: Coverage's own cells (`monitoring_coverage.fleet`) for this
    device alone, and "Apply monitoring profile…" when the profile supplies
    something it lacks, opening the same preview for it alone."""

    @pytest.fixture
    def page(self, ready, monkeypatch):
        from modules import device_page
        from modules.nsot import listref
        rows = {"r2": R2, "r6": R6}
        monkeypatch.setattr(device_page, "find_device",
                            lambda name, ref=None: (listref.resolve("Lab"), dict(rows[name])))
        return lambda name: _get(ready, f"/v2/device/{name}/monitored-by")

    def test_r6_lacks_snmp_and_is_offered_the_profile(self, page):
        r, html = page("r6")
        assert r.status_code == 200
        assert "<strong>SNMP</strong><span class=\"muted\"> through Prometheus</span>: missing — the profile supplies it" in html
        assert 'href="/v2/monitoring/apply?list=Lab&amp;device=r6">Apply monitoring profile…</a>' in html

    def test_r2_lacks_nothing_and_says_so(self, page):
        _r, html = page("r2")
        assert "r2 is configured for everything the network uses." in html
        assert "Apply monitoring profile" not in html

    def test_the_link_opens_the_same_preview_for_that_device(self, ready, page):
        _r, html = page("r6")
        href = html_mod.unescape(re.search(r'href="(/v2/monitoring/apply\?[^"]+)"', html).group(1))
        _r, preview = _get(ready, href)
        assert _order(preview) == ["r6"] and _body(preview)["order"] == ["r6"]

    def test_a_failed_read_is_said_never_an_empty_section(self, page, monkeypatch):
        from modules import monitoring_coverage

        def boom(*a, **k):
            raise OSError("git show failed")
        monkeypatch.setattr(monitoring_coverage, "fleet", boom)
        _r, html = page("r6")
        assert "could not be read (OSError: git show failed)" in html
        assert "not the same as it being monitored by nothing" in html

    def test_it_redraws_on_keys_v2_relays_under_the_strict_policy(self, page):
        from modules import csp, invalidation
        r, html = page("r6")
        assert r.headers.get("Content-Security-Policy") == csp.STRICT_POLICY
        keys = re.findall(r"nmas:(\w+) from:body",
                          re.search(r'hx-trigger="([^"]*)"', html).group(1))
        src = open(os.path.join(ROOT, "static", "js", "nmas_v2.js"), encoding="utf-8").read()
        assert keys == ["goldens", "job_health"]
        for k in keys:
            assert k in invalidation.VOCABULARY and f"NMAS.subscribe('{k}'" in src

    def test_the_monitoring_tab_opens_with_it(self, ready, monkeypatch):
        from tests.test_device_v2 import _get as _dget  # noqa: F401 (same client shape)
        src = open(os.path.join(ROOT, "templates", "v2", "_monitoring.html"), encoding="utf-8").read()
        head = src[:src.index('<div class="toolbar">')]
        assert 'include "v2/_monitored_by.html"' in head


class TestNeedsAttentionOpensIt:
    def test_a_not_monitored_rows_action_opens_the_v2_preview(self):
        """The design (MONITORING_PROFILE.md 5): the row's action becomes this
        apply once it exists. Drawn on the v2 landing from the row the real
        `action_for` builds."""
        from flask import render_template

        import app as A
        from types import SimpleNamespace

        from modules import monitoring_coverage

        # `action_for` reads the ref's name alone; resolving a list would create it.
        action = monitoring_coverage.action_for(
            SimpleNamespace(name="Lab"), "r6", ["snmp"], {"applies": ["snmp"], "profile": True})
        assert action["open"] == "profile_apply"
        row = {"level": "warning", "what": "r6 is not monitored by SNMP", "cause": "c",
               "devices": ["r6"], "since": None, "operands": [], "action": action, "source": "s",
               "key": "k", "triage": None}
        with A.app.test_request_context("/v2/"):
            html = render_template("v2/_attention.html", a={
                "ok": True, "rows": [row], "sources": [], "headline": "1", "counts": {},
                "badge": {"n": 1, "level": "warning"}})     # needs_attention()'s own count
        assert 'href="/v2/monitoring/apply?device=r6&amp;list=Lab">Preview the apply…</a>' in html
        assert "today&#39;s page" not in html.split("r6 is not monitored")[1].split("</article>")[0]
