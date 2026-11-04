"""Heal to intent's act and verify (`modules/heal/act.py`, and the heal's arguments to
`routes.deploy.plan_devices` and `apply_batch`; board H, part H4, docs/HEAL_TO_INTENT.md
section 4 steps 3 to 5, sections 8 and 11, N9, N12, N13, C2402), no network, no device.

- **The stops again at apply:** dry run sends nothing; a policy that moved, a kind no longer
  allowed, a halt, planned work, a network not marked lab, and no confirming person each
  refuse with nothing sent, naming both operands.
- **Plan against the heal's own read:** the program recomputed from a fresh read and refused
  unless its hash is the decision's, naming what moved; THE plan, with that read as its
  capture source, refused unless its program is the heal's byte for byte.
- **C2402:** every removal carries the policy's words as its stated reason, in the hash and the
  receipt; any dangerous line refuses the heal.
- **Apply as the policy:** the setter the actor, ``policy`` its kind, the device held by name;
  stage 4 compares the device with the heal's read, and a device changed again is refused.
- **Verify:** each healed unit at intent or what landed is undone; a removed feature's symptom
  (N13) still there rolls back; any other is kept, amber; unreadable is partial; the golden
  read again.
- **Record:** the outcome recorded, the incident closed; a rollback or a send neither verified
  nor rolled back halts the network.
- **Through the real plan and apply** (the transport spied, stage 4 real against a fake
  session): what was decided is what reaches the wire, IPv4 and IPv6 alike, and the receipt
  names the heal, its policy and the removal's stated reason.
"""
import os

import pytest

from tests.test_heal_decide import (Fake, GOLDEN, PLATFORM, ROUTE4, ROUTE6, changed,
                                    settle)
from tests.test_heal_decide import lab  # the fixture, named by each test below
from tests.test_heal_policy import T0, auto, confirm, iso
from tests.test_sdn_connections import networks  # the fixture `lab` builds on
from tests.test_heal_triggers import _Lazy

A, DC, DS, I, K = (_Lazy("act"), _Lazy("decide"), _Lazy("decisions"), _Lazy("incidents"),
                   _Lazy("kinds"))
SETTER = "admin@example.com"
LOAD = " ip ospf cost 10\n"
ADJ = {"kind": "adjacency", "key": "adj:1", "epoch": T0 - 900, "at": iso(T0 - 900),
       "source": "adjacencies", "protocol": "OSPF", "related": ["core-a"],
       "words": "the OSPF adjacency edge-b – core-a is down"}
CFG = {"kind": "config_change", "key": "cfg:1", "epoch": T0 - 1000, "at": iso(T0 - 1000),
       "attribution": {"by": "outside"},
       "person": {"user": "alice", "words": "the line names the account alice on vty0"},
       "words": "CONFIG_I"}


@pytest.fixture(autouse=True)
def no_host_addresses(monkeypatch):
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])


class FakeAct:
    """The act's sources: the decision's fake for the device, THE plan as the program's own
    computation (`routes.deploy._program`) and an apply that runs the check after verify on
    *post* (the read after the change, the healed configuration unless given)."""

    def __init__(self, running, *, post=None, recheck="clean", symptom=None, plan=None,
                 result=None, mode=None, planned=None, golden=GOLDEN, intended=GOLDEN,
                 read_error="", commit="c" * 40, saved=None):
        self.d = Fake(running, golden=golden, intended=intended, read_error=read_error)
        self.running, self.post, self.recheck = running, post, recheck
        self._symptom, self._plan, self._result = symptom, plan, result
        self._mode, self._planned, self.commit, self.saved = mode, planned, commit, saved
        self.plan_kw = self.apply_kw = None
        self.symptoms, self.symptoms_in_apply, self.in_apply = 0, 0, False

    def __getattr__(self, name):
        return getattr(self.d, name)

    def mode(self, now):
        from modules.heal import policy

        got = policy.current("Default", now)
        return self._mode(got) if self._mode else got

    def planned(self, device, now):
        return self._planned

    def plan(self, device, **kw):
        from modules.nsot import authorisation
        from modules.nsot.deploy import command_fingerprint
        from routes.deploy import _capture_hash, _program

        self.plan_kw = kw
        src = kw["capture"][device]
        full = _program(src["intended"], src["text"], kw["remove"][device], {"ip": "192.0.2.6"},
                        PLATFORM)
        auth = kw["authorise"][device]
        entry = {"device": device, "deployable": True, "commands": full["commands"],
                 "capture_hash": _capture_hash(src["text"]),
                 "command_hash": command_fingerprint(full["commands"], auth, full["ids"], ()),
                 "authorisation_ok": not authorisation.problems(full["commands"], auth,
                                                                 full["keys"]),
                 "expected_effects": {"reach_lost": None}}
        return self._plan(entry) if self._plan else entry

    def apply(self, device, **kw):
        self.apply_kw = kw
        post = self.post if self.post is not None else K._stored(GOLDEN)
        r = {"device": device, "outcome": "deployed", "commands": ["x"], "stage": "",
             "golden_pending": [{"config_text": post}], "heal": dict(kw["heal"][device]),
             "saved_startup": self.saved or {"ok": True}}
        if self._result:
            r.update(self._result)
        elif r["outcome"] == "deployed":
            self.in_apply = True
            verdict = kw["after_verify"](device, r, None)
            self.in_apply = False
            r["heal"].update(verdict.get("record") or {})
            if verdict.get("rollback"):
                r.update(outcome="failed", stage="after_verify", reason=verdict["rollback"],
                         rolled_back=True, rollback_outcome={"state": "restored"})
        return {"results": [r], "golden": {"commit": self.commit} if r["outcome"] == "deployed"
                else {}}

    def symptom(self, device, triggers, since):
        self.symptoms += 1
        self.symptoms_in_apply += int(self.in_apply)
        return self._symptom or {"state": "none", "words": "no symptom named"}

    def intent_state(self, device, text, platform):
        return {"state": "match", "words": "matches"}

    def golden_recheck(self, device, by):
        return {"state": self.recheck}


def decided(running, *, triggers=None, kinds=("added_line",)):
    """A heal decision on edge-b, made in AUTO by the real decision, recorded: its id."""
    auto("Default", now=T0 - 60, kinds=kinds)
    inc = settle(running, triggers=triggers)
    d = DC.decide_one("Default", inc, now=T0, sources=Fake(running))
    assert d["outcome"] == "heal", d["words"]
    return DS.record("Default", d, T0)


def act(running, decision=None, **kw):
    src = FakeAct(running, **kw)
    d = decision or decided(running)
    return A.act_one("Default", d["id"], now=T0 + 5, sources=src), src, d


def applied(decision_id):
    return DS.find("Default", decision_id).get("applied") or {}


# ── A heal through the plan and the apply ───────────────────────────────────────────────────

class TestTheHeal:
    @pytest.mark.parametrize("route, line", [
        (ROUTE4, "no ip route 192.0.2.128 255.255.255.128 192.0.2.10"),
        (ROUTE6, "no ipv6 route 2001:db8:9::/48 2001:db8:0:7::2")])
    def test_an_added_route_is_removed_as_the_policy(self, lab, route, line):
        got, src, d = act(GOLDEN + route)
        assert got["outcome"] == "healed", got["words"]
        kw = src.apply_kw
        assert (kw["actor"], kw["actor_kind"]) == (SETTER, "policy")
        assert "heal to intent (policy set by admin@example.com)" == kw["hold_detail"]
        entry = src.plan("edge-b", **src.plan_kw)
        assert entry["commands"] == [line] == d["program"]
        assert kw["command_hashes"] == {"edge-b": entry["command_hash"]}
        assert kw["confirmations"] == {"edge-b": entry["capture_hash"]}
        assert kw["capture"]["edge-b"]["text"] == K._stored(GOLDEN + route), \
            "planned against the heal's own read, never the stored capture"
        assert kw["heal"]["edge-b"]["policy"]["by"] == SETTER
        assert kw["heal"]["edge-b"]["person"]["user"] == "alice", "N12: the person named"
        assert applied(d["id"])["outcome"] == "healed"
        (inc,) = I.read("Default")["incidents"]
        assert inc["state"] == "closed" and d["id"] in inc["closed_why"]

    def test_a_missing_line_is_re_applied_from_the_golden(self, lab):
        running = changed(("logging host 192.0.2.50\n", ""))
        auto("Default", now=T0 - 60, kinds=("missing_line",))
        inc = settle(running)
        d = DS.record("Default", DC.decide_one("Default", inc, now=T0,
                                               sources=Fake(running)), T0)
        got = A.act_one("Default", d["id"], now=T0 + 5, sources=FakeAct(running))
        assert got["outcome"] == "healed" and d["program"] == ["logging host 192.0.2.50"]

    def test_the_steps_are_the_modules_own(self, lab):
        got, _src, _d = act(GOLDEN + ROUTE4)
        names = [s["step"] for s in got["steps"]]
        assert set(names) <= {n for n, _w in A.STEPS}, names
        assert names[:6] == ["take", "stops", "read", "plan", "authorise", "apply"]
        assert names[-3:] == ["golden", "symptom", "record"], names
        assert {"intent", "saved"} <= set(names)

    def test_a_decision_is_taken_once(self, lab):
        d = decided(GOLDEN + ROUTE4)
        A.act_one("Default", d["id"], now=T0 + 5, sources=FakeAct(GOLDEN + ROUTE4))
        again = A.act_one("Default", d["id"], now=T0 + 6, sources=FakeAct(GOLDEN + ROUTE4))
        assert again["sent"] is False and "was taken by" in again["words"]


# ── The stops, again at apply ───────────────────────────────────────────────────────────────

class TestTheStops:
    def test_dry_run_sends_nothing(self, lab):
        d = decided(GOLDEN + ROUTE4)
        confirm("Default", now=T0, heal_mode="dry_run")
        got, src, _d = act(GOLDEN + ROUTE4, decision=d)
        assert got["outcome"] == "refused" and src.apply_kw is None
        assert "only AUTO sends a heal" in got["words"]

    def test_a_policy_that_moved_since_the_decision(self, lab):
        d = decided(GOLDEN + ROUTE4)
        auto("Default", now=T0, kinds=("added_line", "missing_line"))
        got, src, _d = act(GOLDEN + ROUTE4, decision=d)
        assert "the policy moved since the decision (decided under" in got["words"]
        assert d["policy"]["fingerprint"] in got["words"] and src.apply_kw is None

    def test_a_kind_no_longer_allowed(self, lab):
        d = decided(GOLDEN + ROUTE4)
        got, src, _d = act(GOLDEN + ROUTE4, decision=d, mode=lambda m: dict(
            m, kinds_auto=["missing_line"]))
        assert "added_line is no longer allowed AUTO" in got["words"] and src.apply_kw is None

    def test_a_network_not_marked_lab(self, lab):
        d = decided(GOLDEN + ROUTE4)
        got, src, _d = act(GOLDEN + ROUTE4, decision=d, mode=lambda m: dict(
            m, stage={"stage": "production"}))
        assert "marked production, not lab" in got["words"] and src.apply_kw is None

    def test_a_halt_in_force(self, lab):
        d = decided(GOLDEN + ROUTE4)
        DS.halt("Default", guard=10, name="rate", words="six an hour", operands={}, now=T0)
        got, src, _d = act(GOLDEN + ROUTE4, decision=d)
        assert "halted by guard 10" in got["words"] and src.apply_kw is None

    def test_planned_work(self, lab):
        got, src, _d = act(GOLDEN + ROUTE4, planned={"words": "edge-b is restarting"})
        assert "guard 3, planned work: edge-b is restarting" in got["words"]
        assert src.apply_kw is None

    def test_no_confirming_person(self, lab):
        d = decided(GOLDEN + ROUTE4)
        nobody = dict(d, policy=dict(d["policy"], by=None))
        src = FakeAct(GOLDEN + ROUTE4)
        got = A.apply_decision("Default", nobody, now=T0 + 5, sources=src)
        assert "nobody is accountable" in got["words"] and src.apply_kw is None

    def test_a_failed_read(self, lab):
        got, src, _d = act(GOLDEN + ROUTE4, read_error="timed out")
        assert got["outcome"] == "refused" and "timed out" in got["words"]
        assert src.apply_kw is None


# ── The program, against the heal's own read ────────────────────────────────────────────────

class TestTheProgram:
    def test_a_device_moved_since_the_decision_is_refused_naming_what(self, lab):
        d = decided(GOLDEN + ROUTE4)
        got, src, _d = act(GOLDEN + ROUTE6, decision=d)
        assert got["outcome"] == "refused" and src.apply_kw is None
        assert f"(decided {d['program_hash']}, now " in got["words"]
        assert "the departure (decided" in got["words"] and "the units (decided 1" in got[
            "words"]

    def test_the_plan_not_deployable(self, lab):
        got, src, _d = act(GOLDEN + ROUTE4, plan=lambda e: dict(
            e, deployable=False, blocking_reasons=["template 'x' is not approved"]))
        assert "template 'x' is not approved" in got["words"] and src.apply_kw is None

    def test_a_plan_whose_program_is_not_the_heals(self, lab):
        got, src, _d = act(GOLDEN + ROUTE4, plan=lambda e: dict(e, commands=e["commands"] + [
            "logging host 192.0.2.51"]))
        assert "is not the heal's program" in got["words"] and src.apply_kw is None

    def test_a_plan_that_cuts_mercurys_path(self, lab):
        got, src, _d = act(GOLDEN + ROUTE4, plan=lambda e: dict(e, expected_effects={
            "reach_lost": {"state": "known", "cut": ["leaf-c"]}}))
        assert "would cut Mercury's path (leaf-c)" in got["words"] and src.apply_kw is None


# ── C2402: a stated reason for every removal; no dangerous line ─────────────────────────────

class TestTheReason:
    def test_every_removal_carries_the_policys_words_in_the_hash(self, lab):
        from modules.nsot import authorisation

        got, src, d = act(GOLDEN + ROUTE4)
        (auth,) = src.plan_kw["authorise"]["edge-b"]
        assert auth["line"] == "no ip route 192.0.2.128 255.255.255.128 192.0.2.10"
        assert auth["reason"] == A.policy_reason("Default", d["policy"])
        assert SETTER in auth["reason"] and d["policy"]["fingerprint"] in auth["reason"]
        assert authorisation.reason_problem(auth) == "", "the reason has the shape of one"
        entry = src.plan("edge-b", **src.plan_kw)
        assert entry["command_hash"] != d["program_hash"], "the reason is in the hash"

    def test_a_dangerous_line_is_refused(self, lab, monkeypatch):
        """A shut interface the golden and intent hold, missing on the device: re-applying it
        is a missing line the decision heals, and `shutdown` is a line the CI gate counts
        dangerous, which no person gave a reason for. (Its reach is known to cut nothing.)"""
        monkeypatch.setattr("modules.nsot.expected_effects.for_device",
                            lambda *a, **k: {"reach_lost": {"state": "known", "cut": []}})
        golden = changed((" description to leaf\n", " description to leaf\n shutdown\n"))
        running = GOLDEN
        auto("Default", now=T0 - 60, kinds=("missing_line",))
        inc = settle(running, golden=golden)
        d = DS.record("Default", DC.decide_one("Default", inc, now=T0, sources=Fake(
            running, golden=golden, intended=golden)), T0)
        assert d["outcome"] == "heal" and " shutdown" in d["program"], d["words"]
        src = FakeAct(running, golden=golden, intended=golden)
        got = A.act_one("Default", d["id"], now=T0 + 5, sources=src)
        assert got["outcome"] == "refused" and src.apply_kw is None
        assert "counts dangerous (shutdown)" in got["words"] and "C2402" in got["words"]


# ── What the apply did ──────────────────────────────────────────────────────────────────────

class TestTheOutcome:
    def test_the_device_changed_during_the_heal(self, lab):
        got, _src, d = act(GOLDEN + ROUTE4, result={
            "outcome": "skipped_drifted", "stage": "pre_snapshot", "commands": [],
            "reason": "the device is not the capture this program was computed against"})
        assert got["outcome"] == "refused" and got["sent"] is False
        assert "the device changed during the heal" in got["words"]
        assert DS.halted("Default") == {}

    def test_a_rollback_halts_the_network(self, lab):
        got, _src, d = act(GOLDEN + ROUTE4, result={
            "outcome": "failed", "stage": "verify", "commands": ["x"], "rolled_back": True,
            "reason": "an OSPF adjacency dropped", "rollback_outcome": {"state": "restored"}})
        assert got["outcome"] == "rolled_back"
        assert DS.halted("Default")["guard"] == 14

    def test_a_send_neither_verified_nor_rolled_back_halts(self, lab):
        got, _src, _d = act(GOLDEN + ROUTE4, result={
            "outcome": "failed", "stage": "deploy", "commands": ["x"], "rolled_back": False,
            "reason": "the session closed mid-push"})
        assert got["outcome"] == "failed" and DS.halted("Default")["guard"] == 14

    def test_refused_by_the_apply_sends_nothing(self, lab):
        got, _src, _d = act(GOLDEN + ROUTE4, result={
            "outcome": "refused", "commands": [], "reason": "s3 is held by a deploy"})
        assert got["outcome"] == "refused" and "held by a deploy" in got["words"]

    def test_not_at_its_golden_when_read_again_is_partial(self, lab):
        got, _src, _d = act(GOLDEN + ROUTE4, recheck="drifted")
        assert got["outcome"] == "partial" and "not at it (drifted" in got["words"]

    def test_no_golden_commit_is_partial(self, lab):
        got, _src, _d = act(GOLDEN + ROUTE4, commit="")
        assert got["outcome"] == "partial" and "golden was not committed" in got["words"]

    def test_not_saved_to_startup_is_partial(self, lab):
        got, _src, _d = act(GOLDEN + ROUTE4, saved={"ok": False, "error": "write failed"})
        assert got["outcome"] == "partial" and "NOT saved to startup" in got["words"]


# ── Verify: intent, then the symptom ────────────────────────────────────────────────────────

class TestVerify:
    def test_a_unit_not_at_intent_after_the_change_rolls_back(self, lab):
        got, _src, _d = act(GOLDEN + ROUTE4, post=K._stored(GOLDEN + ROUTE4))
        assert got["outcome"] == "rolled_back" and "not at intent" in got["words"]
        assert DS.halted("Default")["guard"] == 14

    def feature(self):
        return changed((LOAD, LOAD + " load-interval 30\n"))

    def test_n13_a_removed_features_symptom_still_there_rolls_it_back(self, lab):
        running = self.feature()
        d = decided(running, triggers=[CFG, ADJ])
        got, src, _d = act(running, decision=d, symptom={
            "state": "present", "words": "the symptom is still there after 150 s"})
        assert got["outcome"] == "rolled_back" and "put back (N13)" in got["words"]
        assert src.symptoms_in_apply == 1, "read while the device is held, before its save"

    def test_n13_a_removed_features_symptom_gone_is_healed(self, lab):
        running = self.feature()
        d = decided(running, triggers=[CFG, ADJ])
        got, src, _d = act(running, decision=d, symptom={"state": "gone", "words": "gone"})
        assert got["outcome"] == "healed" and src.symptoms == 1

    def test_any_other_symptom_still_there_is_kept_amber(self, lab):
        running = changed(("logging host 192.0.2.50\n", ""))
        d = decided(running, triggers=[CFG, ADJ], kinds=("missing_line",))
        got, src, _d = act(running, decision=d, symptom={
            "state": "present", "words": "the symptom is still there after 150 s"})
        assert got["outcome"] == "symptom_remains", got["words"]
        assert "configuration was not the whole cause" in got["words"]
        assert src.symptoms_in_apply == 0, "read after the save, the device released"
        assert DS.halted("Default") == {}, "kept, never rolled back"

    def test_a_symptom_that_cannot_be_read_is_partial(self, lab):
        running = changed(("logging host 192.0.2.50\n", ""))
        d = decided(running, triggers=[CFG, ADJ], kinds=("missing_line",))
        got, _src, _d = act(running, decision=d, symptom={
            "state": "unreadable", "words": "the symptom could not be read again"})
        assert got["outcome"] == "partial"


# ── The symptom's reads ─────────────────────────────────────────────────────────────────────

def _adj_doc(at, *entries):
    return {"last_good": {"read_started": at, "value": {"adjacencies": {
        f"k{n}": e for n, e in enumerate(entries)}}}}


class TestTheSymptom:
    DOWN4 = {"list": "Default", "protocol": "OSPF", "devices": ["core-a", "edge-b"]}
    DOWN6 = {"list": "Default", "protocol": "OSPFv3", "devices": ["core-a", "edge-b"]}

    @pytest.mark.parametrize("entry, protocol", [(DOWN4, "OSPF"), (DOWN6, "OSPFv3")])
    def test_an_adjacency_down_is_present_and_the_other_family_is_not(self, entry, protocol):
        value = {"adjacencies": {"k": entry}}
        assert A.adjacency_down(value, "Default", ["edge-b", "core-a"], protocol)
        other = "OSPFv3" if protocol == "OSPF" else "OSPF"
        assert not A.adjacency_down(value, "Default", ["edge-b", "core-a"], other)
        assert not A.adjacency_down(value, "Branch", ["edge-b", "core-a"], protocol)

    def test_an_alert_is_matched_by_rule_device_and_interface(self):
        value = {"instances": [{"kind": "condition", "rule": "Interface down",
                                "device": "edge-b", "labels": {"ifName": "Gi4"}}]}
        assert A.alert_firing(value, "edge-b", "Interface down", "Gi4")
        assert not A.alert_firing(value, "edge-b", "Interface down", "Gi2")
        assert not A.alert_firing({"instances": [dict(value["instances"][0],
                                                      kind="no_data")]},
                                  "edge-b", "Interface down")

    def test_read_until_gone_and_stale_before_the_change(self):
        clock = {"t": 1000.0}
        docs = [_adj_doc(900, self.DOWN4), _adj_doc(1010, self.DOWN4), _adj_doc(1040)]
        got = A.read_symptom("Default", "edge-b", [ADJ], since=1000,
                             clock=lambda: clock["t"],
                             sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
                             read=lambda store: {"state": "ok", "doc": docs.pop(0)},
                             request=lambda store: True)
        assert got["state"] == "gone" and docs == []

    def test_still_down_at_the_bound_is_present(self):
        clock = {"t": 1000.0}
        got = A.read_symptom("Default", "edge-b", [ADJ], since=1000,
                             clock=lambda: clock["t"],
                             sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
                             read=lambda store: {"state": "ok",
                                                 "doc": _adj_doc(clock["t"], self.DOWN4)},
                             request=lambda store: True)
        assert got["state"] == "present" and "after 150 s" in got["words"]

    def test_never_read_since_the_change_is_unreadable(self):
        clock = {"t": 1000.0}
        got = A.read_symptom("Default", "edge-b", [ADJ], since=1000,
                             clock=lambda: clock["t"],
                             sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
                             read=lambda store: {"state": "ok", "doc": _adj_doc(900)},
                             request=lambda store: False)
        assert got["state"] == "unreadable" and "no reader for it runs here" in got["words"]

    def test_a_configuration_change_alone_names_no_symptom(self):
        got = A.read_symptom("Default", "edge-b", [CFG], since=0, read=lambda s: {})
        assert got["state"] == "none"

    def test_a_logged_drop_is_read_from_the_adjacencies_store(self):
        assert A._store_for({"kind": "adjacency_log", "source": "adjacency-log"}) == \
            "adjacencies"
        assert A._store_for({"kind": "adjacency_log", "source": "adjacency-log@g2"}) == \
            "adjacencies@g2"


class TestUnitsLeft:
    def test_a_unit_still_departed_is_named_and_one_at_intent_is_not(self):
        c = K.classify(GOLDEN, GOLDEN + ROUTE6, GOLDEN, platform=PLATFORM,
                       mgmt_ip="192.0.2.6")
        assert A.units_left(c["units"], GOLDEN + ROUTE6) == [K.unit_words(c["units"][0])]
        assert A.units_left(c["units"], GOLDEN) == []


# ── The runner's step ───────────────────────────────────────────────────────────────────────

class TestTheRunner:
    def test_each_heal_is_taken_once_and_started_as_its_own_job(self, lab):
        d = decided(GOLDEN + ROUTE4)
        started = []
        got = A.run("Default", now=T0 + 1, starter=lambda n, t: started.append(t) or "job-1")
        assert got["started"] == [{"decision": d["id"], "job": "job-1"}]
        assert started[0]["taken"]["by"].startswith("heal to intent")
        assert A.run("Default", now=T0 + 2, starter=lambda n, t: "job-2")["started"] == []

    def test_a_heal_runs_as_its_own_job_announcing_what_a_heal_changes(self, lab, monkeypatch):
        from modules import invalidation
        from modules.nsot import capture_job

        monkeypatch.setattr(capture_job, "_announce", lambda job_id, ok: None)
        monkeypatch.setattr("modules.heal.act.apply_decision", lambda n, d, sources=None: {
            "outcome": "healed", "decision": d["id"]})
        job = A.start("Default", {"id": "hd-1", "device": "edge-b",
                                  "policy": {"by": SETTER}})
        assert capture_job.wait(job, 10)
        got = capture_job.get(job)
        assert got["kind"] == "heal" and got["payload"]["result"]["outcome"] == "healed"
        assert tuple(invalidation.ANNOUNCERS[A.ANNOUNCER]) == A.DONE_KEYS

    def test_a_job_that_cannot_start_is_recorded_and_its_incident_closed(self, lab):
        d = decided(GOLDEN + ROUTE4)

        def broken(n, t):
            raise RuntimeError("no thread")

        got = A.run("Default", now=T0 + 1, starter=broken)
        assert "no thread" in got["failed"][0]
        assert applied(d["id"])["outcome"] == "refused"
        assert I.read("Default")["incidents"][0]["state"] == "closed"


class TestOneApplyPath:
    def test_the_act_reaches_a_device_only_through_the_plan_and_the_apply(self):
        """One home per action: H4 builds no second apply path. Its only device-changing call
        is THE apply (`apply_batch`), after THE plan (`plan_devices`); it opens no session and
        runs no pipeline of its own."""
        import ast
        import inspect

        from modules.heal import act

        names = {n.attr if isinstance(n, ast.Attribute) else n.id
                 for n in ast.walk(ast.parse(inspect.getsource(act)))
                 if isinstance(n, (ast.Attribute, ast.Name))}
        sent = {"send_config_set", "send_command", "run_device_command", "PipelineRunner",
                "open_ssh", "ConnectHandler", "_deploy_one", "run_batch", "with_temp_connection",
                "get_persistent_connection", "_push_config"}
        assert not names & sent, names & sent
        assert {"apply_batch", "plan_devices"} <= names


# ── The apply's heal arguments, alone ───────────────────────────────────────────────────────

class TestTheApplysArguments:
    def test_a_capture_source_is_never_combined_with_a_scope_or_a_pair(self):
        from routes import deploy as RD

        cap = {"s1": {"text": "hostname s1\n", "intended": ""}}
        with pytest.raises(ValueError, match="never combined"):
            RD.plan_devices("Lab", ["s1"], capture=cap, scope="profile")
        with pytest.raises(ValueError, match="never combined"):
            RD.apply_batch("Lab", {}, {}, actor="a", actor_kind="policy", capture=cap,
                           scope="profile")
        with pytest.raises(ValueError, match="never combined"):
            RD.apply_batch("Lab", {}, {}, actor="a", actor_kind="policy",
                           after_verify=lambda *a: {}, pair={"device": "s1"})
        with pytest.raises(ValueError, match="no read"):
            RD.plan_devices("Lab", ["s1"], capture={"s1": {"text": "", "intended": ""}})

    def _report(self):
        class Ctx:
            selected_devices = [{"ip": "192.0.2.6"}]
            warnings = []
            connections_pool = {}
            pool_lock = None
        return {"results": [{"device": "edge-b", "outcome": "deployed"},
                            {"device": "leaf-c", "outcome": "failed"}]}, {"edge-b": Ctx(),
                                                                         "leaf-c": Ctx()}

    def test_a_check_after_verify_that_raises_rolls_back_never_passes(self, monkeypatch):
        from routes import deploy as RD

        rolled, saved = [], []
        monkeypatch.setattr("modules.nsot.paired_deploy.roll_back_end",
                            lambda ln, host, r, ctx, reason, stage: rolled.append(
                                (host, stage, reason)) or r.update(outcome="failed"))
        monkeypatch.setattr("modules.pipeline.save_held", lambda ctx: saved.append(ctx) or {})

        def broken(host, result, ctx):
            raise RuntimeError("the reader store is locked")

        report, contexts = self._report()
        RD._settle_after_verify(report, contexts, broken, "Lab")
        ((host, stage, reason),) = rolled
        assert (host, stage) == ("edge-b", "after_verify") and "is locked" in reason
        assert saved == [] and report["by_outcome"] == {"failed": ["edge-b", "leaf-c"]}

    def test_a_check_that_passes_saves_and_rides_on_the_receipt(self, monkeypatch):
        from routes import deploy as RD

        monkeypatch.setattr("modules.pipeline.save_held",
                            lambda ctx: {"192.0.2.6": {"ok": True}})
        report, contexts = self._report()
        report["results"][0]["heal"] = {"decision": "hd-1"}
        RD._settle_after_verify(report, contexts, lambda h, r, c: {
            "rollback": "", "record": {"intent": {"left": []}}}, "Lab")
        r = report["results"][0]
        assert r["saved_startup"] == {"ok": True}
        assert r["heal"] == {"decision": "hd-1", "intent": {"left": []}}

    def test_the_receipts_heal_facts_are_masked(self):
        from modules.nsot import receipts

        secret = "S3cretKey"
        (row,) = receipts.rows_for({"results": [{
            "device": "edge-b", "outcome": "deployed", "commands": [],
            "heal": {"decision": "hd-1", "intent": {"left": [
                f"ip ospf message-digest-key 1 md5 {secret}"]}}}]}, list_name="Default",
            action="deploy", actor=SETTER, actor_kind="policy")
        assert row["heal"]["decision"] == "hd-1" and secret not in str(row["heal"])
        (plain,) = receipts.rows_for({"results": [{"device": "edge-b", "outcome": "deployed",
                                                   "commands": []}]}, list_name="Default",
                                     action="deploy", actor=SETTER, actor_kind="person")
        assert "heal" not in plain, "only a heal's rows carry it"


# ── Through the real plan and apply ─────────────────────────────────────────────────────────

class _Session:
    def __init__(self, running):
        self.running = running


class TestThroughTheRealApply:
    """THE plan and THE apply, real: `plan_devices`, `apply_batch`, `plan_batch`, `run_batch`,
    `_deploy_one`, `PipelineRunner` with stage 4 real against a fake session; only the
    transport, the reads after the change and the commit are replaced (tests/
    test_deploy_contract.py's seam)."""

    DEVICE = "s1"
    IP = "203.0.113.21"

    @pytest.fixture
    def wired(self, tmp_path, monkeypatch):
        from modules import pipeline as P
        from modules.nsot import hostvars, manifest, templates_repo
        from modules.nsot.parsers import get_parser
        from tests.intent_fixture import commit_intent, commit_paths
        from tests.test_deploy_contract import _config
        import routes.deploy as RD

        list_dir = tmp_path / "lab"
        repo = str(list_dir / "config_repo")
        os.makedirs(os.path.join(repo, "golden"), exist_ok=True)
        os.makedirs(os.path.join(repo, "host_vars"), exist_ok=True)
        templates_repo.seed_templates(repo)
        manifest.upsert_device(repo, f"uid:{self.DEVICE}", self.DEVICE, self.IP,
                               platform="cisco_ios")
        captured = _config(self.DEVICE)
        with open(os.path.join(repo, "golden", f"{self.DEVICE}.cfg"), "w",
                  encoding="utf-8") as fh:
            fh.write(captured)
        commit_paths(repo, ("golden", ".nsot"), "fixture: golden", source="capture")
        intent = get_parser("cisco_ios").parse(captured)
        secrets = dict(intent.get("secrets") or {})
        hostvars.write_committed(repo, intent)
        commit_intent(repo)
        row = {"hostname": self.DEVICE, "ip": self.IP, "device_type": "cisco_ios",
               "username": "u", "password": "p", "secret": "s", "device_uid": self.DEVICE}
        monkeypatch.setattr("modules.config.get_list_data_dir", lambda name: str(list_dir))
        monkeypatch.setattr("modules.config.get_current_list_name", lambda: "Lab")
        monkeypatch.setattr("modules.nsot.listref.exists", lambda name: name == "Lab")
        monkeypatch.setattr("modules.device.get_current_device_list",
                            lambda: ("Lab", str(list_dir / "devices.csv")))
        monkeypatch.setattr("modules.device.load_saved_devices", lambda path=None: [row])
        monkeypatch.setattr("modules.nsot.approval.is_approved", lambda *a, **k: True)
        monkeypatch.setattr("modules.nsot.hostvars.hydrate_secrets",
                            lambda hv, host, ln="": {**hv, "secrets": dict(secrets)})
        monkeypatch.setattr("modules.heal.incidents._dir", lambda n: str(list_dir / "heal"))
        monkeypatch.setattr(RD, "_commit_batch_golden",
                            lambda *a, **k: {"ok": True, "commit": "c" * 40, "devices": [
                                self.DEVICE]})
        state = {"device": None, "post": None, "rolled": [], "seen": []}

        def push(dev, cmds, pool, lock):
            state["seen"].append(list(cmds))
            return "spy: accepted"

        def save_golden(ctx):
            ctx.golden_pending = [{"hostname": self.DEVICE, "config_text": state["post"],
                                   "mgmt_ip": self.IP, "netbox_id": None,
                                   "device_uid": self.DEVICE}]

        def roll_back_after(ctx, reason, stage="pair"):
            state["rolled"].append((reason, stage))
            ctx.rollback_performed = True
            ctx.rollback_outcome = {self.IP: {"state": "restored", "remaining": [],
                                              "detail": "the removed line is back"}}
            return ctx

        monkeypatch.setattr(P, "_push_config", push)
        monkeypatch.setattr(P, "_capture_operational_snapshot", lambda *a, **k: {})
        monkeypatch.setattr("modules.connection.get_persistent_connection",
                            lambda dev, pool, lock: _Session(state["device"]))
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, cmd, **k: conn.running)
        for stage in ("_stage_netbox_query", "_stage_ci_gate", "_stage_config_diff",
                      "_stage_post_snapshot", "_stage_verify", "_stage_save_startup"):
            monkeypatch.setattr(P, stage, lambda ctx: None)
        monkeypatch.setattr(P, "_stage_save_golden", save_golden)
        monkeypatch.setattr(P, "roll_back_after", roll_back_after)
        return {"repo": repo, "captured": captured, "state": state}

    def run(self, wired, read, *, device=None, post=None, symptom=None):
        """A heal of s1 decided on *read* and applied, the device answering *device* at
        stage 4 (the read, unless given) and *post* after the change."""
        from modules.drift_check import departure, drift_diff
        from modules.heal import decide

        golden = wired["captured"]
        c = K.classify(golden, read, golden, platform="cisco_ios", mgmt_ip=self.IP)
        prog = decide.program(golden, read, c["units"], c["removal_ids"], mgmt_ip=self.IP,
                              platform="cisco_ios")
        inc = I.sight("Lab", self.DEVICE, dict(CFG), now=T0 - 1000, radius_of=lambda d: [])
        policy = {"fingerprint": "fp-1", "by": SETTER, "reason": "Lab 10's AUTO"}
        d = DS.record("Lab", {"outcome": "heal", "device": self.DEVICE,
                              "incident": inc["incident"], "mode": "auto", "kind": c["kind"],
                              "units": [K.masked_unit(u) for u in c["units"]],
                              "program": prog["commands"], "program_hash": prog["hash"],
                              "removal_ids": c["removal_ids"], "policy": policy,
                              "departure": departure(drift_diff(golden, read, self.DEVICE)),
                              "person": {}}, T0)
        taken = DS.take("Lab", d["id"], by="test", now=T0)
        wired["state"].update(device=device or read, post=post or golden)

        class Real(A.Sources):
            def device(s, name):
                return {"hostname": name, "ip": self.IP, "platform": "cisco_ios"}

            def golden(s, name, dev):
                return {"text": golden, "commit": "c0", "state": "at_intent", "words": ""}

            def intended(s, name, platform):
                return {"text": golden, "platform": platform, "why": ""}

            def platform(s, name, dev):
                return "cisco_ios"

            def read(s, dev):
                return read, ""

            def intents(s):
                return {}

            def mode(s, now):
                return {"mode": "auto", "stage": {"stage": "lab"}, "fingerprint": "fp-1",
                        "kinds_auto": ["added_line", "missing_line"], "stopped": {}}

            def planned(s, name, now):
                return None

            def intent_state(s, name, text, platform):
                return {"state": "match", "words": "matches"}

            def golden_recheck(s, name, by):
                return {"state": "clean"}

            def symptom(s, name, triggers, since):
                return symptom or {"state": "none", "words": "no symptom named"}

        got = A.apply_decision("Lab", taken, now=T0 + 5, sources=Real("Lab"))
        return got, prog, d

    def _with(self, captured, line):
        head, _sep, tail = captured.rpartition("\nend")
        return head + "\n" + line.rstrip("\n") + "\nend" + tail

    @pytest.mark.parametrize("route", [ROUTE4, ROUTE6])
    def test_what_was_decided_is_what_reaches_the_wire(self, wired, route):
        from modules.nsot import receipts

        read = self._with(wired["captured"], route)
        got, prog, d = self.run(wired, read)
        assert got["outcome"] == "healed", (got["words"], got["steps"])
        assert wired["state"]["seen"] == [prog["commands"]], wired["state"]["seen"]
        assert prog["commands"] == ["no " + route.strip()]
        (row,) = receipts.read("Lab", self.DEVICE)["rows"]
        assert (row["actor"], row["actor_kind"]) == (SETTER, "policy")
        assert row["heal"]["decision"] == d["id"] and row["heal"]["policy"]["by"] == SETTER
        (auth,) = row["authorised"]
        assert auth["reason"].startswith("heal to intent on Lab: the line was added outside")
        assert row["heal"]["intent"]["left"] == []

    def test_a_missing_line_is_merged_and_held_merge_only_to_intent(self, wired):
        line = "logging host 10.255.1.10"
        read = wired["captured"].replace(line + "\n", "")
        got, prog, _d = self.run(wired, read)
        assert got["outcome"] == "healed", (got["words"], got["steps"])
        assert wired["state"]["seen"] == [[line]] == [prog["commands"]]

    def test_a_device_changed_during_the_heal_is_refused_with_nothing_sent(self, wired):
        read = self._with(wired["captured"], ROUTE4)
        moved = self._with(read, "ntp server 192.0.2.77")
        got, _prog, _d = self.run(wired, read, device=moved)
        assert wired["state"]["seen"] == [], "nothing reached the transport"
        assert got["outcome"] == "refused" and "changed during the heal" in got["words"]
        assert "ntp server 192.0.2.77" in got["words"], "both operands named"

    def test_a_unit_not_at_intent_after_verify_is_rolled_back_by_the_pipeline(self, wired):
        read = self._with(wired["captured"], ROUTE6)
        got, _prog, _d = self.run(wired, read, post=read)
        assert wired["state"]["rolled"] and wired["state"]["rolled"][0][1] == "after_verify"
        assert got["outcome"] == "rolled_back"
        assert DS.halted("Lab")["guard"] == 14
