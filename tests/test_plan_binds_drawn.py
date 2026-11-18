"""Everything a plan's hash binds is shown before Approve, and Approve starts exactly that (C3725;
CLAUDE.md, "What is confirmed is what is sent, byte for byte": a person approves by a hash, so
every value that hash binds is drawn for them first, and the press runs those values).

- **The walk:** the plan's hash is `plan_engine.plan_hash` over the network, the plan, its
  parameters and each step's kind, parameters, own hash and what its preview resolved. Each
  test captures the arguments that hash was computed from while the preview is drawn, walks
  every value in them (each leaf; a plan's or a step kind's key by its declared words), and
  fails naming each one the preview's "What its hash binds" does not draw. Then it presses
  Approve with the hash the page drew and holds the plan the engine was started with to the
  values drawn (`plan_engine.start` stood in, so nothing runs).
- **The plan card** (routes/plans_v2.py, the toolbar assistant's): a DHCP reservation on the
  lab's real Kea (tests/test_plan_engine.py's kit), its subnet found by Mercury and bound.
- **The incident's plan** (`_fixit_section.html`, routes/fixit_v2.py; the operator,
  2026-11-15: "Read the session in the plan's preflight (inside the background job, when the
  proposal is made), store it with the plan, and draw it from the stored record, so the page
  never waits. Approve re-reads at apply and refuses if it changed since the proposal, naming
  what moved"): on tests/test_fixit_section_v2.py's lab, a collector step's session is read
  once, when the proposal is recorded, and kept on its line (IPv4 and IPv6); a page draw reads
  nothing (the seam fails if called); the session is drawn beside Approve and in What its hash
  binds; Approve refuses, naming both and running nothing, when the collector holds another
  session now, and starts the plan with the session drawn when it holds the same; a read that
  named no session leaves the plan unapprovable, saying why; a read that raises is kept as its
  reason. A secret-shaped value in a bound row is masked.
- **Approve's press as two jobs** (C3867, 8f1d8006, the operator, 2026-11-16: Approve "checks
  the posted hash against the plan as shown ... starts the plan engine's job at once and
  answers 'Starting…' in place"): its live checks run after its answer, in its own job
  (`fixit_v2._start_approved`), so a refusal there is that job's failed state and the
  incident's card, never the press's status. These tests run every job a press starts on the
  real `capture_job` (`kept_jobs`), with the real `plan_engine.start` (its preview of every
  step, the bound session read again, and its hash compared with the one approved); only the
  engine's run, which would apply each step, is stood in (`engine_runs`).
- **The walker is judged:** rendered with a step's own hash left out of the drawn rows (no
  request made), the walk names that hash.

No device, no network, no AI call; the collector's dry run is replaced at its seam
(`plan_engine.collector_session`), as it reads Mercury's host.
"""
import json
import re
from html import unescape

import pytest

from modules import plan_engine as PE
from modules.nsot import capture_job
from tests import test_fixit_section_v2 as FX
from tests.test_dhcp_reservations import kea_dir  # noqa: F401 (a fixture)
from tests.test_fixit_section_v2 import web  # noqa: F401 (the fixture)
from tests.test_heal_resubscribe import lab  # noqa: F401 (the fixture `web` builds on)
from tests.test_plan_engine import HX, RES, REASON, client, kea  # noqa: F401 (fixtures)
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture `lab` builds on)


@pytest.fixture
def captured(monkeypatch):
    """Every call of the plan's hash while a preview is drawn: its arguments."""
    calls, real = [], PE.plan_hash

    def plan_hash(plan, params, steps, network=""):
        calls.append({"plan": plan, "params": json.loads(json.dumps(params)),
                      "steps": json.loads(json.dumps(steps)), "network": network})
        return real(plan, params, steps, network)
    monkeypatch.setattr(PE, "plan_hash", plan_hash)
    return calls


@pytest.fixture
def started(monkeypatch):
    """`plan_engine.start` stood in: each start's ``(network, plan, params, hash)``."""
    got = []

    def start(network, plan, params, confirmed, **kw):
        got.append({"network": network, "plan": plan, "params": json.loads(json.dumps(params)),
                    "hash": confirmed})
        return {"run": "r-walk", "job": "j-walk"}
    monkeypatch.setattr(PE, "start", start)
    return got


#: `capture_job.start` as the host runs it, taken when this file is imported, before `web`
#: replaces it with a stand-in that runs the work in the request and lets its error out.
REAL_JOB_START = capture_job.start
#: The kind of Approve's own job (`fixit_v2._start_approved`).
APPROVE_JOB = "approved plan start"
#: How long a test waits for a job to end: each ended in 0.1 s or less on the laptop
#: (2026-11-18, the whole file in 5 s); far above it, for a loaded run.
JOB_WAIT_S = 10


@pytest.fixture
def kept_jobs(web, monkeypatch):  # noqa: F811
    """Every job a press starts run by the real `capture_job` (its own thread, waited here), so
    a raising work is the job's ``failed`` state with its error, as on the host. Each job's
    id, in the order each ended."""
    ids = []

    def start(*a, **kw):
        jid = REAL_JOB_START(*a, **kw)
        assert capture_job.wait(jid, JOB_WAIT_S), f"job {jid} did not end in {JOB_WAIT_S} s"
        ids.append(jid)
        return jid
    monkeypatch.setattr(capture_job, "start", start)
    return ids


def jobs_of(ids, kind):
    """The kept jobs of *kind*, as `capture_job.get` reads them."""
    return [j for j in (capture_job.get(i) for i in ids) if j and j["kind"] == kind]


@pytest.fixture
def engine_runs(monkeypatch):
    """`plan_engine.run` stood in (the run the engine's job starts, which applies each step):
    each run's ``(network, plan, params, hash)``. Everything before it is real, so a refusal
    still refuses and nothing reaches a device."""
    got = []

    def run(network, plan, params, confirmed, **kw):
        got.append({"network": network, "plan": plan, "params": json.loads(json.dumps(params)),
                    "hash": confirmed})
        return {"id": kw.get("run_id"), "outcome": "done"}
    monkeypatch.setattr(PE, "run", run)
    return got


def words_of(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _leaves(x):
    """Every value in *x* (its names are labels: a value is what the hash binds)."""
    if isinstance(x, dict):
        for v in x.values():
            yield from _leaves(v)
    elif isinstance(x, (list, tuple)):
        for v in x:
            yield from _leaves(v)
    elif x is not None and x != "":
        yield _word(x)


def _word(x) -> str:
    """A key a person reads by its declared words (the step kinds' and the plans' own)."""
    if isinstance(x, str) and x in PE.STEP_KINDS:
        return PE.STEP_KINDS[x].words
    if isinstance(x, str) and x in PE.PLANS:
        return PE.PLANS[x].words
    return str(x)


def bound_values(call: dict) -> list:
    """Every value the hash bound, walked from its arguments (the step's ``n`` is its order,
    drawn as the row's number)."""
    out = [call["network"], _word(call["plan"])] + list(_leaves(call["params"]))
    for s in call["steps"]:
        out += [_word(s["kind"])] + list(_leaves(s["params"]))
        out += [s.get("hash") or ""] + list(_leaves(s.get("resolved") or {}))
    return [v for v in dict.fromkeys(out) if v]


def binds_html(html: str) -> str:
    m = re.search(r'<details class="small plan-bound"[^>]*>(.*?)</details>', html, re.S)
    assert m, "no What its hash binds is drawn"
    return m.group(1)


def drawn_binds(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", binds_html(html))).split())


def drawn_rows(html: str) -> dict:
    """What its hash binds as drawn: ``{label: words}``."""
    return {unescape(k): unescape(v) for k, v in
            re.findall(r"<dt>(.*?)</dt><dd>(.*?)</dd>", binds_html(html), re.S)}


def undrawn(call: dict, html: str) -> list:
    text = drawn_binds(html)
    return [v for v in bound_values(call) if " ".join(str(v).split()) not in text]


def card(client):  # noqa: F811
    r = client.get("/v2/plans/preview", query_string={
        "list": "Default", "plan": "dhcp-reservation", "params": json.dumps(RES)}, headers=HX)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Approve the plan" in html, html[:400]
    return html


class TestThePlanCard:
    def test_every_value_the_hash_binds_is_drawn_and_approve_starts_exactly_them(
            self, client, captured, started):  # noqa: F811
        html = card(client)
        assert captured, "the card's preview computed the plan's hash"
        call = captured[-1]
        assert call["steps"][0].get("resolved", {}).get("subnet"), "Mercury found its subnet"
        assert len(bound_values(call)) >= 7, bound_values(call)  # the floor: as measured
        assert undrawn(call, html) == []
        assert html.index('class="small plan-bound"') < html.index('hx-post="/v2/plans/approve')
        # Pressed with the hash and parameters the card drew.
        drawn_hash = re.search(r'hx-vals=\'\{"hash": "([0-9a-f]{16})"\}\'', html).group(1)
        params = unescape(re.search(r'name="params" value="([^"]*)"', html).group(1))
        r = client.post("/v2/plans/approve?list=Default", headers=HX, data={
            "hash": drawn_hash, "plan": "dhcp-reservation", "params": params,
            "reason": REASON})
        assert r.status_code == 200, r.get_data(as_text=True)[:400]
        (run,) = started
        rows = drawn_rows(html)
        assert run["hash"] == drawn_hash == rows["The plan's hash"]
        assert {k: str(v) for k, v in run["params"].items()} == {
            k[len("Its "):]: v for k, v in rows.items() if k.startswith("Its ")}, (run, rows)


def test_the_walker_names_a_planted_undrawn_field(kea, captured, monkeypatch):  # noqa: F811
    """The card rendered with a step's own hash left out of its drawn rows (no request made):
    the walk names that hash, and nothing else."""
    import app as A
    from flask import render_template

    from routes import plans_v2

    real = PE.bound_rows
    monkeypatch.setattr(PE, "bound_rows", lambda *a, **k: [
        r for r in real(*a, **k) if "own hash" not in r[0]])
    with A.app.test_request_context("/v2/plans/preview"):
        html = render_template("v2/_plan_card.html", c=plans_v2.card("Default", {
            "plan": "dhcp-reservation", "params": json.dumps(RES)}))
    call = captured[-1]
    assert undrawn(call, html) == [call["steps"][0]["hash"]], undrawn(call, html)


STEPS = [{"operation": "telemetry-collector-resubscribe", "params": {"subs": ["101", "102"]}}]
SESSIONS = {"IPv4": ("192.0.2.6:57001", "192.0.2.60:57500"),
            "IPv6": ("[2001:db8::6]:57001", "[2001:db8::60]:57500")}


class Seam:
    """`plan_engine.collector_session` stood in: what it answers, each call counted, and a
    phase in which a call fails the test."""

    def __init__(self, monkeypatch, remote="", local="", refused="", raises=None):
        self.calls, self.answer, self.forbidden, self.raises = [], None, "", raises
        self.set(remote, local, refused)
        monkeypatch.setattr(PE, "collector_session", self)

    def set(self, remote, local="", refused=""):
        self.answer = {"session": remote, "local": local, "quiet_s": 2130 if remote else None,
                       "dry_run": "would close one session" if remote else "",
                       "refused": refused}

    def __call__(self, network, device, subs):
        if self.forbidden:
            pytest.fail(f"the collector was read {self.forbidden}")
        self.calls.append((network, device, tuple(subs)))
        if self.raises:
            raise self.raises
        return dict(self.answer)


#: The same plan in the catalog's form, as the job making the proposal reads its sessions.
CATALOG_STEPS = [{"operation": "telemetry-collector-resubscribe",
                  "params": {"device": "r2", "subscriptions": ["101", "102"]}}]


def proposed(iid):
    """The proposal made as its job makes it: the collector's session read once
    (`plan_engine.read_sessions`), then handed to the record's writer, which reads nothing."""
    from modules.fixit import incident as F

    sessions = PE.read_sessions(FX.NET, CATALOG_STEPS)
    return F.record_proposal(FX.incident(iid), "person", steps=STEPS, sessions=sessions)


def drawn_approve(html):
    """The proposal and the hash Approve carries, as the page drew them. Premise corrected
    (board R5, becced07, approved 2026-11-15: a plan waiting on Approve is its own card under
    the incident, `#inc-plan`, Approve and the session it binds on it): read from the plan's
    card, where it was the BLUF."""
    bluf = FX.plan_of(html)
    m = re.search(r'<span class="bluf-form"><input type="hidden" name="proposal" '
                  r'value="([^"]+)"><input type="hidden" name="hash" value="([0-9a-f]{16})">',
                  bluf)
    assert m, "Approve is offered, carrying its proposal and hash"
    return {"proposal": m.group(1), "hash": m.group(2)}, bluf


class TestTheIncidentsPlan:
    @pytest.mark.parametrize("family", sorted(SESSIONS))
    def test_the_session_is_read_once_at_the_proposal_drawn_and_started_as_drawn(
            self, web, monkeypatch, captured, kept_jobs, engine_runs, family):  # noqa: F811
        remote, local = SESSIONS[family]
        seam = Seam(monkeypatch, remote, local)
        iid = FX.plant()
        line = proposed(iid)
        # Read once, when the proposal was recorded, and kept on its line.
        assert len(seam.calls) == 1 and seam.calls[0][1] == "r2"
        kept = line["sessions"]["1"]
        assert (kept["session"], kept["local"], kept["quiet_s"]) == (remote, local, 2130)
        # A page draw reads nothing: the record is drawn.
        seam.forbidden = "on a page draw"
        _r, html = FX.page(web, iid)
        seam.forbidden = ""
        assert len(seam.calls) == 1
        fields, bluf = drawn_approve(html)
        # Premise corrected (board R5, becced07): the session is a line of the plan's card,
        # `<p class="bluf-session">`, where it was a span beside the BLUF's Approve.
        beside = re.search(r'<p class="bluf-session small" data-session-step="1"[^>]*>(.*?)'
                           r'</p>', bluf, re.S)
        assert beside, "the session is drawn beside Approve"
        said = " ".join(unescape(re.sub(r"<[^>]+>", " ", beside.group(1))).split())
        assert remote in said and local in said and "quiet for 2130 s" in said, said
        call = next(c for c in reversed(captured) if c["plan"] == PE.INCIDENT_FIX)
        assert remote in bound_values(call) and undrawn(call, html) == []
        # Pressed: the collector holds the same session, so the plan starts with it. Premise
        # corrected (C3867, 8f1d8006): Approve answers "Starting…" at once and its live reads
        # follow in its own job, which ends done; the engine's run is the second job.
        r = FX.post(web, iid, "approve", **fields)
        assert r.status_code == 200 and "Starting…" in words_of(r.get_data(as_text=True)), \
            r.get_data(as_text=True)[:600]
        (job,) = jobs_of(kept_jobs, APPROVE_JOB)
        assert job["state"] == "done" and job["error"] == "", job
        assert len(jobs_of(kept_jobs, PE.JOB_KIND)) == 1, "the engine's run is its own job"
        # Read twice after the proposal, each for its own check: Approve's job compares it
        # with the one bound (`fixit_v2._start_approved`), then `plan_engine.start`'s preview
        # of the step (`plan_engine._catalog_preview`) checks the bound session once more.
        assert len(seam.calls) == 3, seam.calls
        (run,) = engine_runs
        (step,) = run["params"]["steps"]
        assert step["session"] == remote and remote in drawn_rows(html).values()
        assert run["params"]["proposal"] == fields["proposal"] == line["proposal"]
        # It starts on the hash the person approved, the one the page drew.
        assert run["hash"] == fields["hash"]

    def test_approve_refuses_when_the_engine_previews_another_hash(self, web, monkeypatch,  # noqa: F811
                                                                  kept_jobs, engine_runs):
        # The second review of the verify-speed gate, 2026-11-15: the run starts on the hash
        # the person approved, never on one the engine computed after it.
        remote, local = SESSIONS["IPv6"]
        Seam(monkeypatch, remote, local)
        iid = FX.plant()
        proposed(iid)
        _r, html = FX.page(web, iid)
        fields, _bluf = drawn_approve(html)
        real = PE.preview

        def moved(network, plan, params):
            got = real(network, plan, params)
            return dict(got, hash="f" * 16) if got.get("ok") else got
        monkeypatch.setattr(PE, "preview", moved)
        r = FX.post(web, iid, "approve", **fields)
        # Premise corrected (C3867, 8f1d8006): the hash the page drew is the plan as shown, so
        # Approve answers "Starting…"; `plan_engine.start`, in Approve's job, previews the plan
        # and refuses the hash it computes now, naming both: the job's failed state and the
        # incident's card say it, where it was the press's 409.
        assert r.status_code == 200 and "Starting…" in words_of(r.get_data(as_text=True))
        (job,) = jobs_of(kept_jobs, APPROVE_JOB)
        assert job["state"] == "failed", job
        _r, after = FX.page(web, iid)
        for said in (job["error"], words_of(after)):
            assert f"you approved {fields['hash']}" in said, said[:1200]
            assert f"the plan previewed now is {'f' * 16}" in said, said[:1200]
            assert "Nothing ran" in said, said[:1200]
        assert engine_runs == [] and jobs_of(kept_jobs, PE.JOB_KIND) == [], "nothing ran"

    def test_approve_refuses_a_session_that_moved_naming_both(self, web, monkeypatch,  # noqa: F811
                                                              kept_jobs, engine_runs):
        remote, local = SESSIONS["IPv4"]
        seam = Seam(monkeypatch, remote, local)
        iid = FX.plant()
        proposed(iid)
        _r, html = FX.page(web, iid)
        fields, _bluf = drawn_approve(html)
        seam.set("192.0.2.7:57002", local)
        r = FX.post(web, iid, "approve", **fields)
        # Premise corrected (C3867, 8f1d8006): Approve answers "Starting…" and its job reads
        # the session again (`fixit_v2._start_approved`), refusing before the engine starts:
        # the job's failed state and the incident's card name both, where it was a 409.
        assert r.status_code == 200 and "Starting…" in words_of(r.get_data(as_text=True))
        (job,) = jobs_of(kept_jobs, APPROVE_JOB)
        assert job["state"] == "failed", job
        _r, after = FX.page(web, iid)
        for said in (job["error"], words_of(after)):
            assert f"the plan read the session from {remote}" in said, said[:1200]
            assert "the collector holds the one from 192.0.2.7:57002 now" in said, said[:1200]
            assert "Nothing ran" in said, said[:1200]
        # Read at the proposal and by Approve's job: refused there, before the engine's preview.
        assert len(seam.calls) == 2, seam.calls
        assert engine_runs == [] and jobs_of(kept_jobs, PE.JOB_KIND) == [], "nothing ran"

    @pytest.mark.parametrize("family", sorted(SESSIONS))
    def test_a_session_that_moves_after_approves_read_is_refused_by_the_engine_naming_both(
            self, web, monkeypatch, kept_jobs, engine_runs, family):  # noqa: F811
        """The session moves after Approve's job compared it, before `plan_engine.start`'s
        preview of the step (`plan_engine._catalog_preview`, the third read): the engine refuses
        it, naming both, nothing runs (the job's error says "Nothing ran"), and the incident's
        card says it did not start, naming both (C3976, measured 2026-11-18: the card keeps a
        failure's first 400 characters and the engine's words put the step's description,
        about 460 for the collector step, before its reason, so neither session was on the
        card)."""
        remote, local = SESSIONS[family]
        moved = {"IPv4": "192.0.2.7:57002", "IPv6": "[2001:db8::7]:57002"}[family]
        seam = Seam(monkeypatch, remote, local)
        iid = FX.plant()
        proposed(iid)
        _r, html = FX.page(web, iid)
        fields, _bluf = drawn_approve(html)

        def moves_after_approves_read(network, device, subs):
            if len(seam.calls) == 2:          # the proposal's read and Approve's job's
                seam.set(moved, local)
            return seam(network, device, subs)
        monkeypatch.setattr(PE, "collector_session", moves_after_approves_read)
        r = FX.post(web, iid, "approve", **fields)
        assert r.status_code == 200 and "Starting…" in words_of(r.get_data(as_text=True))
        assert len(seam.calls) == 3, seam.calls
        (job,) = jobs_of(kept_jobs, APPROVE_JOB)
        assert job["state"] == "failed", job
        _r, after = FX.page(web, iid)
        assert "Nothing ran" in job["error"], job["error"]
        for said in (job["error"], words_of(after)):
            assert "the approved plan did not start: step 1 is refused by its own preview: " \
                "the collector's session moved since the plan was approved" in said, said[:1200]
            assert f"the approval bound the session from {remote}" in said, said[:1200]
            assert f"the collector holds one from {moved} now" in said, said[:1200]
        assert engine_runs == [] and jobs_of(kept_jobs, PE.JOB_KIND) == [], "nothing ran"

    def test_a_read_that_named_no_session_is_not_approvable_and_says_why(self, web,  # noqa: F811
                                                                         monkeypatch):
        from modules.fixit import plan as FP

        Seam(monkeypatch, refused="no idle established session from r2 on port 57500")
        iid = FX.plant()
        line = proposed(iid)
        plan = FP.preflight(FX.incident(iid), line)
        assert plan["approvable"] is False and plan["hash"] == "", plan
        assert "no idle established session from r2 on port 57500" in plan["why_refused"]
        (s,) = plan["sessions"]
        assert s["session"] == "" and "no idle established session" in s["refused"]

    def test_a_read_that_raises_is_kept_as_its_reason(self, web, monkeypatch):  # noqa: F811
        from modules.fixit import plan as FP

        Seam(monkeypatch, raises=RuntimeError("ss could not be run"))
        got = PE.read_sessions(FX.NET, CATALOG_STEPS)
        assert got["1"]["session"] == "" and \
            "RuntimeError: ss could not be run" in got["1"]["refused"], got
        iid = FX.plant()
        line = proposed(iid)
        kept = line["sessions"]["1"]
        assert kept["session"] == "" and "RuntimeError: ss could not be run" in kept["refused"]
        plan = FP.preflight(FX.incident(iid), line)
        assert plan["approvable"] is False and "ss could not be run" in plan["why_refused"]

    def test_the_record_reads_nothing_and_refuses_a_bad_sessions_shape(self, web,  # noqa: F811
                                                                       monkeypatch):
        """`record_proposal` keeps what the job read and reads nothing itself; a sessions value
        of another shape is refused, nothing kept; a collector step proposed with none is not
        approvable, saying why."""
        from modules.fixit import incident as F
        from modules.fixit import plan as FP

        seam = Seam(monkeypatch, *SESSIONS["IPv4"])
        seam.forbidden = "by the proposal's record"
        iid = FX.plant()
        inc = FX.incident(iid)
        for bad in (["192.0.2.6:57001"], {"one": {}}, {"1": "192.0.2.6:57001"}):
            with pytest.raises(F.Refused, match="a proposal's sessions are"):
                F.record_proposal(inc, "person", steps=STEPS, sessions=bad)
        assert not [ln for ln in F.read(inc)["lines"] if "proposal" in ln], "nothing kept"
        line = F.record_proposal(inc, "person", steps=STEPS)
        plan = FP.preflight(inc, line)
        assert plan["approvable"] is False and \
            "proposed before Mercury read the session" in plan["why_refused"], plan
        assert seam.calls == []

    def test_a_secret_shaped_value_in_a_bound_row_is_masked(self, web, monkeypatch):  # noqa: F811
        from modules.fixit import plan as FP

        Seam(monkeypatch, *SESSIONS["IPv4"])
        secret = "snmp-server community S3cretRO RO"
        real = PE.bound_rows
        monkeypatch.setattr(PE, "bound_rows", lambda *a, **k: real(*a, **k) + [
            ("Its planted value", secret)])
        iid = FX.plant()
        plan = FP.preflight(FX.incident(iid), proposed(iid))
        (row,) = [w for label, w in plan["bound"] if label == "Its planted value"]
        assert "S3cretRO" not in row and row.startswith("snmp-server community"), row
