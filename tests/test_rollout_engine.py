"""Board R's 00 and 0(a) to (d) (the operator, 2026-11-14; provisional, operator review pending).

**00, THE rollout engine** (`modules/nsot/fleet_change.py`, `run_waves`): "Rollouts run
themselves: one approval of the whole plan by its hash, then canary and every wave proceed
automatically, each device verified; the first failure rolls that device back and stops the
run, telling the team (notification). No per-wave or per-carrier confirm. Options on the plan,
chosen before approval: a pause after the canary (off by default) and a settle time between
waves. ... The same engine for every batch deploy."

- the run goes wave to wave with no press; a failure at wave 2 stops it, names the rest not
  started and tells the team once (the rollback is THE apply's, `apply_batch` with
  `stop_at_first`); the pause holds after the canary until continued; the settle is waited,
  counted on a clock that never sleeps; the hash covers the options;
- every caller of THE apply in a batch goes through the engine (by parsing).

**0(a)** a job a page started is listed by In progress with that page as its link, and its
result waits under "Finished, not opened yet" until opened (`capture_job` and `in_flight`, the
one registry). **0(b)** a chosen canary that cannot be the canary refuses the plan, saying why.
**0(c)** carriers go in dependency order, a cycle refused by name. **0(d)** a program of
accounts and privilege lines alone cannot cut a path: an allowlist of exact shapes.

No device is reached: THE apply is a recorder here.
"""

import ast
import os

import pytest

from modules.nsot import fleet_change as F
from modules.nsot import read_account as RA

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Waves:
    """A recorder for `run_waves`' *apply_wave*: each wave's devices; a device in *fail* does
    not deploy and verify (THE apply rolled it back and stopped its wave)."""

    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def __call__(self, _n, devices):
        self.calls.append(list(devices))
        bad = [d for d in devices if d in self.fail]
        return {"results": [{"device": d, "outcome": "failed" if d in self.fail
                             else "deployed"} for d in devices],
                "stopped": f"{', '.join(bad)} did not deploy and verify" if bad else ""}


def _told():
    sent = []
    return sent, (lambda event, teams: sent.append((event, list(teams))) or {"sent": 1})


class TestTheEngine:
    WAVES = [["c1"], ["a", "b"], ["d", "e"], ["s3"]]

    def test_it_goes_wave_to_wave_with_no_press(self):
        w = _Waves()
        got = F.run_waves("Lab", self.WAVES, w, options={}, sleep=lambda s: None)
        assert got["state"] == "done" and w.calls == self.WAVES
        assert [r["device"] for r in got["results"]] == ["c1", "a", "b", "d", "e", "s3"]

    def test_a_failure_at_wave_2_stops_it_names_the_rest_and_tells_the_team_once(self):
        sent, deliver = _told()
        w = _Waves(fail={"b"})
        got = F.run_waves("Lab", self.WAVES, w, options={}, sleep=lambda s: None,
                          deliver=deliver, teams=["noc"], label="The rollout", key="k1",
                          link="/v2/credentials/profiles?list=Lab")
        assert got["state"] == "stopped" and w.calls == self.WAVES[:2]
        assert got["not_started"] == ["d", "e", "s3"]
        assert [r["outcome"] for r in got["results"]][-3:] == ["unattempted"] * 3
        assert len(sent) == 1 and sent[0][1] == ["noc"]
        event = sent[0][0]
        assert event["event"] == F.STOPPED_EVENT and "b did not deploy" in event["happened"]
        assert "d, e, s3" in event["outcome"] and event["link"].startswith("/v2/")

    def test_the_stopped_event_is_one_the_notifier_carries(self):
        from modules.notify import message
        sent, deliver = _told()
        F.run_waves("Lab", [["a"], ["b"]], _Waves(fail={"a"}), options={},
                    sleep=lambda s: None, deliver=deliver, teams=[], key="k2")
        facts = message.check_event(sent[0][0])
        assert facts["event"] == "rollout_stopped" and facts["incident"].startswith("rollout-")

    def test_the_pause_holds_after_the_canary_until_continued(self):
        w = _Waves()
        got = F.run_waves("Lab", self.WAVES, w, options={"pause_after_canary": True},
                          sleep=lambda s: None)
        assert got["state"] == "paused" and got["next"] == 1 and w.calls == [["c1"]]
        rest = F.run_waves("Lab", self.WAVES, w, options={"pause_after_canary": True},
                           start_at=got["next"], before=got["results"], sleep=lambda s: None)
        assert rest["state"] == "done" and w.calls == self.WAVES
        assert len(rest["results"]) == 6

    def test_the_settle_is_waited_between_waves_on_a_counted_clock(self):
        slept = []
        F.run_waves("Lab", self.WAVES, _Waves(), options={"settle_s": "45"}, sleep=slept.append)
        assert slept == [45, 45, 45], "before every wave but the first"
        slept.clear()
        F.run_waves("Lab", self.WAVES, _Waves(), options={}, sleep=slept.append)
        assert slept == []

    def test_the_options_are_bounded_and_off_by_default(self):
        assert F.options_of({}) == {"pause_after_canary": False, "settle_s": 0}
        assert F.options_of({"pause_after_canary": "on", "settle_s": "99999"}) == {
            "pause_after_canary": True, "settle_s": F.SETTLE_MAX}
        assert F.options_of({"settle_s": "x"})["settle_s"] == 0

    def test_the_hash_covers_the_options(self):
        assert F.with_options("h", {}) == F.with_options("h", {"settle_s": 0})
        assert F.with_options("h", {}) != F.with_options("h", {"settle_s": 1})
        assert F.with_options("h", {}) != F.with_options("h", {"pause_after_canary": True})


def _calls_of(path, name):
    """``[(function, line)]`` of every call of *name* (attribute or bare) in *path*, each
    named by the INNERMOST function holding it (a call in a nested ``def`` is that def's)."""
    tree = ast.parse(open(os.path.join(ROOT, path), encoding="utf-8").read())
    out = []

    def visit(node, fn):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(child, child.name)
                continue
            if isinstance(child, ast.Call) and fn:
                f = child.func
                called = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if called == name:
                    out.append((fn, child.lineno))
            visit(child, fn)
    visit(tree, "")
    return out


class TestEveryBatchDeployUsesTheEngine:
    """By parsing: every call of THE apply (`apply_batch`) in the product is inside the
    engine's wave (`run_batches`, `deploy_job.start`'s wave) or one of the named single-device
    callers; each batch caller reaches `run_waves`."""

    #: The callers of `apply_batch` that are no batch deploy, each with why.
    SINGLE = {("modules/heal/act.py", "apply"): "a heal's one device, its own decision",
              ("modules/heal/dampening.py", "apply"): "a heal's one device, its own decision"}

    def _apply_callers(self):
        from tests import source_index

        found = set()
        for path in source_index.tracked("modules", "routes", suffix=".py"):
            rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
            found |= {(rel, fn) for fn, _line in _calls_of(rel, "apply_batch")}
        return found

    def test_every_caller_of_the_apply_is_the_engine_s_or_a_single_device(self):
        callers = self._apply_callers()
        assert len(callers) >= 3, callers
        engine = {("modules/nsot/fleet_change.py", "run_batches"),
                  ("modules/deploy_job.py", "apply_wave")}
        assert callers - engine - set(self.SINGLE) == set(), sorted(callers - engine)

    @pytest.mark.parametrize("first,before,stops", [("failed", False, True),
                                                    ("refused", True, False),
                                                    ("refused", False, True)])
    def test_the_batch_deploy_stops_at_its_first_counted_failure(self, monkeypatch, first,
                                                                  before, stops):
        """`deploy_job.start` through the engine: one wave in the confirmed order; a device
        the batch's breaker counts (sent and failed, or refused on the way to the device)
        stops it, the rest named not started, the team told once; a device refused before
        the batch (its program moved: THE apply's ``refused``) is its own row and the rest
        go on."""
        import routes.deploy as rd
        from modules import deploy_job, identity
        from modules.nsot import capture_job
        from modules.nsot.deploy import DEPLOYED, UNATTEMPTED

        told, calls = [], []

        def apply_batch(list_name, confirmations, command_hashes, **kw):
            calls.append((list(confirmations), kw.get("stop_at_first")))
            rows, hit = [], False
            for d in confirmations:
                if hit and stops:
                    rows.append({"device": d, "outcome": UNATTEMPTED})
                elif d == "r2":
                    hit = True
                    rows.append({"device": d, "outcome": first})
                else:
                    rows.append({"device": d, "outcome": DEPLOYED, "verify": {"ok": True}})
            return {"results": rows,
                    "refused": [r for r in rows if r["device"] == "r2"] if before else []}
        monkeypatch.setattr(rd, "apply_batch", apply_batch)
        monkeypatch.setattr("modules.notify.delivery.deliver_event",
                            lambda event, teams: told.append(event) or {"sent": 1})
        monkeypatch.setattr("modules.readers.ci_agreement.told_teams", lambda nets: ["t"])
        order = ["r1", "r2", "r3"]
        job = deploy_job.start("Lab", order, {d: "c" for d in order}, {d: "h" for d in order},
                               authorise={}, remove={}, scope="intent", actor="op",
                               actor_kind="person", ident=identity.request_identity())
        assert capture_job.wait(job, 10)
        out = capture_job.get(job)["payload"]
        assert calls == [(order, True)], "one wave, in the confirmed order, stop at first"
        if stops:
            assert out["stopped"] == "r2 did not deploy and verify"
            assert [e["event"] for e in told] == ["rollout_stopped"] and "r3" in told[0]["outcome"]
        else:
            assert out["stopped"] == "" and told == []
            assert [r["outcome"] for r in out["results"]] == [DEPLOYED, "refused", DEPLOYED]

    def test_each_batch_caller_reaches_run_waves(self):
        assert _calls_of("modules/deploy_job.py", "run_waves"), "deploy_job.start"
        runs = {fn for fn, _l in _calls_of("modules/nsot/fleet_change.py", "run_waves")}
        assert "_run" in runs, "a layer's and a selection's change"
        assert {fn for fn, _l in _calls_of("modules/nsot/read_account.py", "run_waves")} == {
            "_run"}, "the read-only account's rollout"
        loops = {fn for fn, _l in _calls_of("modules/nsot/read_account.py", "run_batches")}
        assert loops == set(), "no second loop over the batches"


class TestTheCarrierOrder:
    """0(c), measured on plan cc36b8e3b9f1: s3 carries 11 (r1, r3, r4, r6, r8, s4 among them),
    s4 7, r3 3, r4 2, r6 1; it was scheduled s1, s3, s4, r1, r3, r4, r6, r8."""

    CARRIES = {"s3": ["r1", "r3", "r4", "r6", "r8", "s4", "s1", "r2", "r5", "r7", "s2"],
               "s4": ["r3", "r4", "r6", "r1", "r8", "r7", "r2"],
               "r3": ["r4", "r6", "r2"], "r4": ["r6", "r2"], "r6": ["r7"],
               "s1": [], "r1": [], "r8": []}

    def test_each_goes_after_every_carrier_reached_through_it(self):
        got, why = RA.carrier_order(self.CARRIES)
        assert why == "" and got[-1] == "s3"
        for h, reached in self.CARRIES.items():
            for d in reached:
                if d in self.CARRIES:
                    assert got.index(d) < got.index(h), (d, h, got)
        assert got[:3] == ["r1", "r6", "r8"], "ties by name"

    def test_a_cycle_is_refused_by_name(self):
        got, why = RA.carrier_order({"a": ["b"], "b": ["a"], "c": []})
        assert got == [] and "a, b" in why

    def test_the_order_puts_them_last_in_that_order(self):
        batches, confirm_at = RA.order(["a", "s3", "r6", "r3", "b"], "", 4, {
            "s3": ["r3", "r6"], "r3": ["r6"], "r6": []})
        assert batches == [["a"], ["b"], ["r6"], ["r3"], ["s3"]] and confirm_at == [2, 3, 4]


class TestTheAccountOnlyAllowlist:
    """0(d): accounts and privilege lines alone cannot cut a path; anything else keeps a
    carrier last (allowing by resemblance is not safe)."""

    @pytest.mark.parametrize("program", [
        ["username mercury-ro privilege 3 algorithm-type scrypt secret <redacted:read-account:"
         "profile:default>"],
        ["privilege exec level 3 show telemetry ietf subscription",
         "privilege exec level 1 show",
         "username mercury-ro privilege 3 algorithm-type scrypt secret <redacted:x>"],
        ["username mercury-ro secret 9 $9$abc"],
    ])
    def test_these_cannot_cut(self, program):
        assert RA.cannot_cut(program)

    @pytest.mark.parametrize("program", [
        [], ["interface GigabitEthernet2", " shutdown"],
        ["username mercury-ro privilege 3 secret x", "ip route 0.0.0.0 0.0.0.0 192.0.2.1"],
        [" username mercury-ro secret 9 $9$abc"], ["no username mercury-ro"],
        ["username mercury-ro autocommand reload"],
        ["privilege interface level 3 shutdown"], ["ipv6 route ::/0 2001:db8::1"],
    ])
    def test_anything_else_keeps_the_carrier_rule(self, program):
        assert not RA.cannot_cut(program)


class TestTheCanary:
    """0(b): a chosen canary that cannot be the canary is refused, saying why."""

    def test_a_carrier_cannot_be_the_canary(self):
        why = RA.canary_refusal("r6", ["r6", "s2", "r7"], {"r6": ["r7"]})
        assert "r6" in why and "carries Mercury's management path to r7" in why
        assert "choose another" in why

    def test_the_other_cases_are_said(self):
        assert "nothing to send" in RA.canary_refusal("a", ["b"], {}, unchanged=["a"])
        assert "refused by the deploy" in RA.canary_refusal("a", ["b"], {}, refused=["a"])
        assert "not one of the devices" in RA.canary_refusal("z", ["b"], {})
        assert RA.canary_refusal("", ["b"], {}) == "" and RA.canary_refusal("b", ["b"], {}) == ""


class TestPageJobsInProgress:
    """0(a): a job a page started (`capture_job.start(page=...)`) is listed by In progress with
    its page as the link while it runs, and waits under "Finished, not opened yet" until opened
    there; the one registry."""

    def test_running_then_finished_then_opened(self, monkeypatch):
        import threading

        from modules import in_flight
        from modules.nsot import capture_job

        monkeypatch.setattr("modules.nsot.device_ops.in_flight", lambda name, now: [])
        monkeypatch.setattr("modules.seen_runs.is_seen", lambda viewer, job: False)
        gate = threading.Event()

        def work(_job):
            gate.wait(10)
            return {"ok": True, "network": "Lab"}
        job = capture_job.start("Lab", "Plan the rollout", "op@example.com", work,
                                kind="read-only account rollout preview",
                                page="/v2/credentials/profiles?list=Lab&ra_job={job}")
        try:
            chip = in_flight.chip([], "op@example.com")
            row = next(r for r in chip["running"] if r.get("href"))
            assert row["href"] == f"/v2/credentials/profiles?list=Lab&ra_job={job}"
        finally:
            gate.set()
        assert capture_job.wait(job, 10)
        chip = in_flight.chip([], "op@example.com")
        (done,) = [f for f in chip["finished"] if f["job"] == job]
        assert done["href"].endswith(f"ra_job={job}") and done["level"] == "ok"
        capture_job.mark_opened(job, "op@example.com")
        assert not [f for f in in_flight.chip([], "op@example.com")["finished"]
                    if f["job"] == job]

    def test_a_stopped_run_is_red_under_finished(self, monkeypatch):
        from modules import in_flight
        from modules.nsot import capture_job

        monkeypatch.setattr("modules.nsot.device_ops.in_flight", lambda name, now: [])
        monkeypatch.setattr("modules.seen_runs.is_seen", lambda viewer, job: False)
        job = capture_job.start("Lab", "Roll out", "op", lambda _j: {
            "state": "stopped", "stopped": "b did not deploy and verify"},
            kind="read-only account rollout", page="/v2/credentials/profiles?ra_job={job}")
        assert capture_job.wait(job, 10)
        (row,) = [f for f in in_flight.chip([], "op")["finished"] if f["job"] == job]
        assert row["level"] == "danger" and "b did not deploy" in row["words"]
