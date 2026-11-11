"""Self-healing's dampening proposal (board H's amendment, item 2, part H22;
docs/HEAL_TO_INTENT.md 19.4 and 19.6's rows 8 and 8b; C2745), `modules/heal/dampening.py`, no
network, no device.

- **The intent patch:** `intent_patch`'s ``set_dampening`` sets ``dampening: true`` on the named
  interface of a real committed document (r2's, tests/fixtures/committed/), IPv4 and IPv6
  interfaces alike; refused for an interface intent lacks, a dampening line with parameters
  held as unmodelled text, or two operations deciding one interface's dampening.
- **The verify read's parser** on a fixture SHAPED from Cisco's documented ``show interfaces
  dampening`` table (tests/fixtures/heal_dampening/; no device's answer is in the suite, and
  the module says so, `VERIFY_CAPTURED`): tracked by the interface's own name or its short form;
  an empty answer tracks nothing; text it does not recognise is unreadable, never "not tracked".
- **Raised** only in AUTO after a real bounce (still flapping, or 13d's second need), one per
  port while it waits; a policy that does not propose the kind records why; a device whose
  deploy holds other lines, or whose intent holds dampening already, is refused by name.
- **The card** (`propose.view`): its one hash; its Fix lines (the intent edit, the verify read,
  the undo); its Approve refused by name while the ``interface.dampening`` removal is not
  measured on the device's platform, and once its port is stable 24 h (lapsed).
- **The act** as the approving person: the intent committed (``Actor-Verified: access``), the
  deploy through THE apply as the person with the proposal's program hash, the verify read on
  the deploy's own session; a read not listing the port rolls back by the pipeline's rollback
  and puts the intent back; an unreadable read keeps it, unverified; a moved hash, an unmeasured
  removal or a refused deploy sends nothing.
- **Needs attention:** one row per port, its clearing by approval, decline or 24 h stable; an
  approved deploy that did not end dampened is a row of its own.

The removal measurement record in these tests is a test record, not a measurement: the real one
is the operator's probe on s1 and r2 (C2416).
"""
import json
import os
import types

import pytest

from modules.heal import dampening as _DAMPENING  # noqa: F401 (the module under test, at import)
from tests.test_heal_policy import T0
from tests.test_sdn_connections import networks  # noqa: F401 (the fixture)

NET = "Default"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMMITTED = os.path.join(ROOT, "tests", "fixtures", "committed")
SHAPED = os.path.join(ROOT, "tests", "fixtures", "heal_dampening",
                      "shaped__show_interfaces_dampening.txt")
PERSON = "op@example.com"
WHO = {"actor": PERSON, "actor_verified": "access", "person": True}
REASON = "the port keeps flapping after its bounce"
GI2 = "GigabitEthernet2"
PROGRAM = [f"interface {GI2}", " dampening", "exit"]


def D():
    from modules.heal import dampening
    return dampening


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


R2 = _read(os.path.join(COMMITTED, "r2.yml"))


def mode(m="auto", propose=("dampening_proposal",)):
    return {"network": NET, "mode": m, "set": m, "state": "ok", "words": f"{m} for the test",
            "fingerprint": "fp-1", "kinds_auto": ["port_bounce"], "kinds_propose": list(propose),
            "confirmed": {"by": "op@example.invalid", "reason": "the proposal under test",
                          "fingerprint": "fp-1"},
            "stage": {"stage": "lab"}, "stopped": {"stopped": False}}


def _fake_class():
    from modules.heal import dampening

    class FakeSources(dampening.Sources):
        """The proposal's and its act's sources, faked: r2's real committed intent (its blob
        a test name), THE plan's answers as set, the commit, the apply and the verify read
        recorded."""

        def __init__(self, *, m=None, pending=(), program=None, moved=False, verify=None,
                     apply_outcome="deployed", rolled_back=False, sent=True, device="r2",
                     text=None):
            super().__init__(NET, clock=lambda: T0)
            self._mode, self.pending, self.moved = m or mode(), list(pending), moved
            self.program = list(PROGRAM if program is None else program)
            self.verify = _read(SHAPED).replace("GigabitEthernet4", GI2) if verify is None \
                else verify
            self.apply_outcome, self.rolled_back, self.sent = apply_outcome, rolled_back, sent
            self.host, self.text = device, R2 if text is None else text
            self.commits, self.put_backs, self.applied, self.verified_as = [], [], [], None
            self.committed = False

        def mode(self, now):
            return self._mode

        def planned(self, device, now):
            return None

        def device(self, host):
            return {"hostname": host, "ip": "192.0.2.12", "device_type": "cisco_xe"}

        def platform(self, host, dev):
            return "cisco_iosxe"

        def doc(self, host):
            return {"ok": True, "yaml": self.text, "base": "blob-2" if self.committed
                    else "blob-1"}

        def plan(self, host, *, proposed=None, **kw):
            if proposed is None and not self.committed:
                return {"device": host, "commands": list(self.pending), "command_hash": "h0",
                        "capture_hash": "c0"}
            h = "h-moved" if self.moved and self.committed else "h1"
            return {"device": host, "commands": list(self.program), "command_hash": h,
                    "capture_hash": "c1"}

        def commit(self, host, patch, summary, base, actor, trailers):
            from modules import identity
            self.verified_as = identity.actor_verification(actor)
            self.commits.append({"host": host, "patch": patch, "summary": summary,
                                 "base": base, "actor": actor, "trailers": list(trailers)})
            self.committed = True
            return {"ok": True, "commit": "c0ffee1234567890"}

        def put_back(self, host, text, summary, base, actor, trailers):
            self.put_backs.append({"host": host, "text": text, "base": base, "actor": actor})
            return {"ok": True, "commit": "bac0ffee12345678"}

        def apply(self, host, **kw):
            self.applied.append(kw)
            # THE apply's result as `routes.deploy` shapes it: its program in hand, and, rolled
            # back after verify, `paired_deploy.roll_back_end`'s outcome and stage.
            r = {"device": host, "outcome": self.apply_outcome, "reason": "",
                 "commands": list(self.program)}
            if self.apply_outcome == "deployed":
                verdict = kw["after_verify"](host, r, object())
                if verdict.get("record"):
                    r["heal"] = verdict["record"]
                if verdict.get("rollback"):
                    r.update(outcome="failed", stage="after_verify", reason=verdict["rollback"],
                             rolled_back=True, rollback_outcome={"state": "restored"})
                else:
                    r["saved_startup"] = {"ok": True}
            elif self.sent:
                r.update(reason="verify failed", rolled_back=self.rolled_back,
                         rollback_outcome={"state": "restored"} if self.rolled_back else {})
            else:
                r.update(reason="refused at stage 4: the device moved")
            return {"results": [r]}

        def verify_read(self, dev, ctx):
            return self.verify

    return FakeSources


@pytest.fixture
def FakeSources():
    return _fake_class()


@pytest.fixture
def stores(networks, monkeypatch):  # noqa: F811 (the fixture)
    monkeypatch.setattr("modules.heal.auto_diagnose.drawn", lambda *a, **k: {"state": "none"})
    return networks


@pytest.fixture
def measured(tmp_path, monkeypatch):
    """A removal record holding `interface.dampening` on the test platform: a test record."""
    from modules.nsot import removal
    path = tmp_path / "removal_measured.json"
    path.write_text(json.dumps({"by_dialect": {"cisco_iosxe": {"interface.dampening": {
        "result": "exact", "device": "r2", "at": "2026-11-10T00:00:00Z", "detail": ""}}},
        "unmeasured": {}}), encoding="utf-8")
    monkeypatch.setattr(removal, "MEASURED_FILE", str(path))


@pytest.fixture
def unmeasured(tmp_path, monkeypatch):
    """A removal record with no `interface.dampening` row (as shipped, C2416)."""
    from modules.nsot import removal
    path = tmp_path / "removal_measured.json"
    path.write_text(json.dumps({"by_dialect": {"cisco_iosxe": {}}, "unmeasured": {}}),
                    encoding="utf-8")
    monkeypatch.setattr(removal, "MEASURED_FILE", str(path))


def bounce(epoch=T0 - 600, did="hd-b1", interface=GI2, device="r2"):
    return {"id": did, "incident": "hi-1", "device": device, "outcome": "heal",
            "epoch": epoch, "at": "",
            "action": {"kind": "port_bounce", "device": device, "interface": interface,
                       "far_device": "r3", "far_interface": "GigabitEthernet2"}}


def raised(src, trigger="still_flapping", now=T0, after=None):
    return D().raise_after(NET, after or bounce(), trigger=trigger, now=now, sources=src)


# ── The intent patch ───────────────────────────────────────────────────────────────────────

class TestTheIntentPatch:
    def _apply(self, *ops, doc=None):
        import yaml

        from modules.nsot import intent_patch
        return intent_patch.apply(doc or yaml.safe_load(R2),
                                  {"hostname": "r2", "operations": list(ops)})

    @pytest.mark.parametrize("name", ["GigabitEthernet2", "Gi2", "Loopback0"])
    def test_it_sets_dampening_on_the_one_interface_and_nothing_else(self, name):
        import copy

        import yaml
        doc = yaml.safe_load(R2)
        got = self._apply({"op": "set_dampening", "interface": name}, doc=copy.deepcopy(doc))
        assert got["ok"] and got["changed"], got
        want = copy.deepcopy(doc)
        canonical = "GigabitEthernet2" if name.startswith("Gi") else name
        next(i for i in want["interfaces"] if i["name"] == canonical)["dampening"] = True
        assert got["doc"] == want
        assert got["changes"][0]["summary"] == f"{canonical}: dampening (the platform's defaults)"

    def test_an_ipv6_interface_beside_an_ipv4_one(self):
        import yaml
        doc = yaml.safe_load(R2)
        gi2 = next(i for i in doc["interfaces"] if i["name"] == GI2)
        assert gi2["ipv4"] and gi2["ipv6"], "r2's Gi2 carries both families"
        gi2["ipv4"] = ""
        got = self._apply({"op": "set_dampening", "interface": GI2}, doc=doc)
        assert got["ok"] and next(i for i in got["doc"]["interfaces"]
                                  if i["name"] == GI2)["dampening"] is True

    def test_held_already_changes_nothing(self):
        import yaml
        doc = yaml.safe_load(R2)
        next(i for i in doc["interfaces"] if i["name"] == GI2)["dampening"] = True
        got = self._apply({"op": "set_dampening", "interface": GI2}, doc=doc)
        assert got["ok"] and not got["changed"]

    def test_an_interface_intent_lacks_is_refused_naming_both(self):
        got = self._apply({"op": "set_dampening", "interface": "GigabitEthernet9"})
        assert got["ok"] is False and got["stage"] == "intent"
        assert "'GigabitEthernet9'" in got["error"] and "GigabitEthernet2" in got["error"]

    def test_a_dampening_line_with_parameters_is_refused_naming_it(self):
        import yaml
        doc = yaml.safe_load(R2)
        next(i for i in doc["interfaces"] if i["name"] == GI2)["unmodeled"] = [
            "dampening 5 1000 2000 20"]
        got = self._apply({"op": "set_dampening", "interface": GI2}, doc=doc)
        assert got["ok"] is False and "'dampening 5 1000 2000 20'" in got["error"]

    def test_two_operations_deciding_one_interfaces_dampening(self):
        got = self._apply({"op": "set_dampening", "interface": GI2},
                          {"op": "set_dampening", "interface": "Gi2"})
        assert got["ok"] is False and "the dampening of GigabitEthernet2" in got["error"]

    def test_the_patched_text_round_trips_with_the_one_field(self):
        import yaml

        from modules.nsot import intent_patch
        got = intent_patch.patched_text("r2", R2, D().patch_of("r2", GI2))
        assert got["ok"] and got["changed"], got
        before, after = yaml.safe_load(R2), yaml.safe_load(got["text"])
        next(i for i in before["interfaces"] if i["name"] == GI2)["dampening"] = True
        assert after == before


# ── The verify read's parser (shaped from Cisco's documented output) ───────────────────────

class TestTheVerifyParser:
    def test_it_is_said_to_be_shaped_not_captured(self):
        assert D().VERIFY_CAPTURED is False
        assert any("not yet a capture" in w for w in D().units_words(
            {"device": "r2", "units": [], "action": {"interface": GI2},
             "dampening": {"dialect": "cisco_iosxe"}}))

    @pytest.mark.parametrize("name, tracked", [("GigabitEthernet4", True), ("Gi4", True),
                                               ("GigabitEthernet2", True),
                                               ("GigabitEthernet3", False)])
    def test_tracked_by_the_interfaces_own_name(self, name, tracked):
        got = D().parse(_read(SHAPED), name)
        assert got["state"] == "parsed" and got["tracked"] is tracked, got
        assert got["interfaces"]["GigabitEthernet4"]["supp"] is True
        assert got["interfaces"]["GigabitEthernet4"]["penalty"] == 2742

    def test_an_empty_answer_tracks_nothing(self):
        got = D().parse("", GI2)
        assert (got["state"], got["tracked"]) == ("parsed", False)

    def test_text_it_does_not_recognise_is_unreadable_never_not_tracked(self):
        for text in ("Dampening is enabled on 1 interface\n",
                     _read(SHAPED).replace("FALSE", "MAYBE")):
            got = D().parse(text, GI2)
            assert (got["state"], got["tracked"]) == ("unreadable", None), got

    def test_a_device_without_the_read(self):
        got = D().parse("show interfaces dampening\n                   ^\n% Invalid input "
                        "detected at '^' marker.\n", GI2)
        assert got["state"] == "unsupported"


# ── Raised after a bounce ──────────────────────────────────────────────────────────────────

class TestRaised:
    def test_still_flapping_in_auto_records_the_proposal_with_its_one_hash(self, stores,
                                                                          FakeSources):
        from modules.heal import decisions
        src = FakeSources()
        got = raised(src)
        assert got["state"] == "recorded", got
        d = got["decision"]
        assert (d["outcome"], d["kind"], d["tier"]) == ("propose", "dampening_proposal", 2)
        assert d["action"]["after"] == "hd-b1" and d["action"]["interface"] == GI2
        assert d["program"] == PROGRAM
        from modules.nsot import intent_patch
        text = intent_patch.patched_text("r2", R2, D().patch_of("r2", GI2))["text"]
        assert d["program_hash"] == D().one_hash(NET, "r2", GI2, "blob-1", text, "h1")
        assert d["dampening"]["dialect"] == "cisco_iosxe"
        assert [x["id"] for x in decisions.proposals(NET)] == [d["id"]]

    def test_one_waits_per_port(self, stores, FakeSources):
        from modules.heal import decisions
        src = FakeSources()
        first = raised(src)["decision"]
        again = raised(src, trigger="second_need", now=T0 + 60)
        assert again["state"] == "waiting" and first["id"] in again["words"]
        assert len(decisions.decisions(NET)) == 1

    def test_not_in_auto_no_bounce_was_sent_so_nothing_is_recorded(self, stores, FakeSources):
        from modules.heal import decisions
        got = raised(FakeSources(m=mode("dry_run")))
        assert got["state"] == "none" and "no bounce was sent" in got["words"]
        assert decisions.decisions(NET) == []

    def test_a_policy_that_does_not_propose_it_records_why(self, stores, FakeSources):
        got = raised(FakeSources(m=mode(propose=("process_reset",))))
        d = got["decision"]
        assert d["outcome"] == "cant_fix" and "the policy does not propose" in d["words"]
        assert "process_reset" in d["words"]

    @pytest.mark.parametrize("kw, words", [
        ({"pending": ["ip route 192.0.2.0 255.255.255.0 192.0.2.1"]},
         "already holds 1 line(s) not sent"),
        ({"program": [f"interface {GI2}", " dampening", " description x", "exit"]},
         "is not the one line under it"),
        ({"program": ["interface GigabitEthernet3", " dampening", "exit"]},
         "is not the one line under it"),
    ])
    def test_refused_by_name(self, stores, FakeSources, kw, words):
        d = raised(FakeSources(**kw))["decision"]
        assert d["outcome"] == "cant_fix" and words in d["words"], d["words"]

    def test_intent_holding_it_already_is_nothing_to_propose(self, stores, FakeSources):
        from modules.nsot import intent_patch
        held = intent_patch.patched_text("r2", R2, D().patch_of("r2", GI2))["text"]
        d = raised(FakeSources(text=held))["decision"]
        assert d["outcome"] == "cant_fix" and "already holds dampening" in d["words"]

    def test_the_bounce_still_flapping_raises_it(self, stores, monkeypatch, FakeSources):
        from tests.test_heal_bounce import (Clock, FakeRouter, GI4, act_world,  # noqa: F401
                                            auto_src, taken)
        from modules.heal import bounce, decisions
        monkeypatch.setattr("modules.commands.run_device_command",
                            lambda conn, cmd, **kw: conn.device.show(cmd))
        monkeypatch.setattr("modules.restarts._data", lambda name: str(stores / name))
        clock = Clock()
        dev = FakeRouter(clock)
        trans = {"state": "read", "words": "", "transitions": [
            {"epoch": T0 + t, "at": "", "state": s} for s, t in
            [("up", 12), ("down", 200), ("up", 230)]]}
        src = auto_src(dev, clock, transitions=trans)
        damp = FakeSources(program=[f"interface {GI4}", " dampening", "exit"], device="r3")
        damp.patched = lambda host, text, patch: {"ok": True, "changed": True,
                                                  "text": "r3's patched intent",
                                                  "changes": [{"summary": "Gi4: dampening"}]}
        src.dampening = damp
        out = bounce.apply(NET, taken(src), sources=src)
        assert out["outcome"] == "still_flapping", out["steps"]
        assert "a dampening change waits for a person" in out["words"], out["words"]
        (p,) = decisions.proposals(NET)
        assert p["action"]["kind"] == "dampening_proposal" and p["action"]["after"] == \
            out["decision"]


# ── The card ───────────────────────────────────────────────────────────────────────────────

class TestTheCard:
    def test_while_unmeasured_it_is_drawn_and_its_approve_refused_by_name(
            self, stores, unmeasured, FakeSources):
        from modules.heal import decisions, propose
        src = FakeSources()
        d = raised(src)["decision"]
        v = propose.view(NET, d["id"], now=T0 + 1, sources=src)
        assert v["confirmable"] is False and v["program"] == PROGRAM
        (why,) = v["refusals"]
        assert "not confirmable until measured" in why and "interface.dampening" in why
        assert "has not been measured on cisco_iosxe" in why
        assert v["steps"] == [w for _n, w in D().STEPS]
        assert any("gains `dampening: true` on GigabitEthernet2" in u for u in v["units"])
        assert any(u.endswith("not measured on cisco_iosxe") for u in v["units"])
        with pytest.raises(propose.Refused) as e:
            propose.approve(NET, d["id"], confirmed_hash=v["hash"], reason=REASON,
                            now=T0 + 2, sources=src, **WHO)
        assert "interface.dampening" in str(e.value)
        assert not decisions.find(NET, d["id"]).get("taken"), "nothing was taken"

    def test_measured_it_is_confirmable_and_its_hash_binds_the_one_hash(
            self, stores, measured, FakeSources):
        from modules.heal import propose
        src = FakeSources()
        d = raised(src)["decision"]
        v = propose.view(NET, d["id"], now=T0 + 1, sources=src)
        assert v["refusals"] == [] and v["confirmable"] is True, v["refusals"]
        assert v["hash"] == propose.proposal_hash(NET, d, "")
        assert (f"undone by removing `dampening` (interface.dampening): measured on "
                f"cisco_iosxe, the rollback interface {GI2} / no dampening / exit") in v["units"]

    def test_the_rollback_is_the_measured_removal_the_pipeline_sends(self, measured):
        from modules.nsot import deploy
        undo = D().rollback_program(GI2, "cisco_iosxe")
        assert undo == {"commands": [f"interface {GI2}", " no dampening", "exit"],
                        "refused": ""}
        # The pipeline's own rollback of the deploy's one added line sends the same program.
        before = f"interface {GI2}\n ip address 192.0.2.1 255.255.255.254\n"
        assert deploy.rollback_commands(PROGRAM, before) == undo["commands"]

    def test_unmeasured_the_rollback_is_refused_by_name(self, unmeasured):
        undo = D().rollback_program(GI2, "cisco_iosxe")
        assert undo["commands"] == [] and "has not been measured on cisco_iosxe" in \
            undo["refused"]
        assert "interface.dampening" in D().rollback_refusal("cisco_iosxe", GI2)
        assert "the device's platform is not known" in D().rollback_refusal("", GI2)

    def test_stable_24_hours_it_lapsed(self, stores, measured, FakeSources):
        from modules.heal import propose
        src = FakeSources()
        d = raised(src)["decision"]
        v = propose.view(NET, d["id"], now=T0 + 24 * 3600 + 1, sources=src)
        assert v["confirmable"] is False and "lapsed: resolved by time" in v["refusals"][0]

    def test_a_read_of_its_device_never_withdraws_it(self, stores, FakeSources):
        from modules.heal import propose
        d = raised(FakeSources())["decision"]
        assert propose.withdrawn_how(d, {"state": "clean"}) == ""
        assert propose.withdrawn_how(d, {"state": "drifted", "departure": "x"}) == ""


# ── The act, as the approving person ───────────────────────────────────────────────────────

def run(src, monkeypatch):
    """Raise, view, approve and run the job inline as the person; the act's result."""
    from modules.heal import propose
    d = raised(src)["decision"]
    results = []
    monkeypatch.setattr("modules.nsot.capture_job.start",
                        lambda net, label, actor, work, **kw: results.append(work("job-1"))
                        or "job-1")
    ident = types.SimpleNamespace(is_identified=True, actor=PERSON, kind="person",
                                  verification="access")
    v = propose.view(NET, d["id"], now=T0 + 1, sources=src)
    out = propose.approve(NET, d["id"], confirmed_hash=v["hash"], reason=REASON, now=T0 + 2,
                          sources=src, ident=ident, **WHO)
    assert out["job"] == "job-1"
    return d, results[0]["result"]


class TestTheAct:
    def test_dampened_committed_and_deployed_as_the_person(self, stores, measured,
                                                         monkeypatch, FakeSources):
        from modules.heal import decisions
        src = FakeSources()
        d, got = run(src, monkeypatch)
        assert got["outcome"] == "dampened", got["steps"]
        (c,) = src.commits
        assert (c["actor"], c["base"], c["patch"]) == (PERSON, "blob-1",
                                                       D().patch_of("r2", GI2))
        assert src.verified_as == "access", "the intent commit reads Actor-Verified: access"
        assert f"Heal-Decision: {d['id']}" in c["trailers"]
        assert any(t.startswith("Heal-Proposal: ") for t in c["trailers"])
        (a,) = src.applied
        assert (a["actor"], a["actor_kind"], a["command_hashes"]) == (PERSON, "person",
                                                                      {"r2": "h1"})
        assert src.put_backs == []
        assert decisions.find(NET, d["id"])["applied"]["outcome"] == "dampened"
        assert [s["step"] for s in got["steps"]] == [
            "take", "stops", "rollback", "plan", "intent", "apply", "verify", "record"]

    def test_a_read_not_listing_the_port_rolls_back_and_puts_intent_back(
            self, stores, measured, monkeypatch, FakeSources):
        # The shaped table with Gi2 minimally edited away: Gi3 and Gi4 tracked, Gi2 not.
        src = FakeSources(verify=_read(SHAPED).replace("GigabitEthernet2", "GigabitEthernet3"))
        _d, got = run(src, monkeypatch)
        assert got["outcome"] == "rolled_back", got["words"]
        assert "does not list GigabitEthernet2" in got["words"]
        (p,) = src.put_backs
        assert p["text"] == R2 and p["actor"] == PERSON and p["base"] == "blob-2"

    def test_an_unreadable_read_neither_passes_nor_fails(self, stores, measured, monkeypatch,
                                                        FakeSources):
        _d, got = run(FakeSources(verify="something else\n"), monkeypatch)
        assert got["outcome"] == "unverified" and "neither passed nor failed" in got["words"]

    def test_a_moved_program_sends_nothing_and_puts_intent_back(self, stores, measured,
                                                              monkeypatch, FakeSources):
        src = FakeSources(moved=True)
        _d, got = run(src, monkeypatch)
        assert got["outcome"] == "refused" and src.applied == []
        assert "approved h1, now h-moved" in got["words"] and len(src.put_backs) == 1

    def test_intent_moved_since_the_proposal_commits_nothing(self, stores, measured,
                                                             monkeypatch, FakeSources):
        from modules.heal import propose
        src = FakeSources()
        d = raised(src)["decision"]
        v = propose.view(NET, d["id"], now=T0 + 1, sources=src)
        assert "domain_name: example.com" in R2
        src.text = R2.replace("domain_name: example.com", "domain_name: example.org")
        monkeypatch.setattr("modules.nsot.capture_job.start",
                            lambda net, label, actor, work, **kw: src.__dict__.setdefault(
                                "job", work("job-2")) and "job-2")
        propose.approve(NET, d["id"], confirmed_hash=v["hash"], reason=REASON, now=T0 + 2,
                        sources=src, **WHO)
        got = src.job["result"]
        assert got["outcome"] == "refused" and "the proposal moved since it was approved" in \
            got["words"]
        assert d["program_hash"] in got["words"]
        assert src.commits == [] and src.applied == [] and src.put_backs == []

    def test_a_deploy_refused_before_sending_puts_intent_back(self, stores, measured,
                                                            monkeypatch, FakeSources):
        src = FakeSources(apply_outcome="refused", sent=False)
        _d, got = run(src, monkeypatch)
        assert got["outcome"] == "refused" and "Nothing was sent" in got["words"]
        assert len(src.put_backs) == 1

    def test_unmeasured_at_the_act_commits_nothing(self, stores, measured, monkeypatch,
                                                 FakeSources, tmp_path):
        from modules.heal import decisions
        from modules.nsot import removal
        src = FakeSources()
        d = raised(src)["decision"]
        taken = decisions.take(NET, d["id"], by=f"{PERSON}: approved", now=T0 + 2)
        bare = tmp_path / "bare.json"
        bare.write_text(json.dumps({"by_dialect": {}, "unmeasured": {}}), encoding="utf-8")
        monkeypatch.setattr(removal, "MEASURED_FILE", str(bare))
        got = D().apply_approved(NET, taken, {"by": PERSON, "reason": REASON, "hash": "x",
                                              "verified": "access", "at": ""},
                                 now=T0 + 3, sources=src)
        assert got["outcome"] == "refused" and "interface.dampening" in got["words"]
        assert src.commits == [] and src.applied == []


# ── The records (H23: History, the change record) ──────────────────────────────────────────

def history(device):
    from modules import history_sources as HS
    return HS.heal({"ref": types.SimpleNamespace(name=NET), "device": device, "limit": 50,
                    "members": None, "since": None, "until": None})["events"]


class TestTheRecords:
    def test_the_proposal_is_drawn_as_dampening_proposed_on_its_port(self, stores,
                                                                     FakeSources):
        raised(FakeSources())
        (e,) = history("r2")
        assert e["what"] == f"Self-healing (AUTO): r2 {GI2} dampening proposed", e["what"]
        assert dict(e["record"])["Far end"] == "r3 GigabitEthernet2"

    def test_dampened_keeps_its_change_record_naming_the_person_and_its_undo(
            self, stores, measured, monkeypatch, FakeSources):
        _d, got = run(FakeSources(), monkeypatch)
        assert got["outcome"] == "dampened", got["steps"]
        cr = got["records"]["change_record"]
        assert cr["state"] == "made" and cr["risk"] == "medium", cr
        text = cr["markdown"]
        assert f"# Change record: r2 {GI2}, dampening proposed by self-healing" in text
        assert f"Approved by {PERSON} (verified: access)" in text
        assert "interface GigabitEthernet2\n no dampening\nexit" in text, "the measured undo"
        assert "No planned window: a deploy of one intent line" in text
        (e,) = history("r2")
        assert e["what"] == f"Self-healing (AUTO): r2 {GI2} dampened", e["what"]
        rec = dict(e["record"])
        assert rec["Intent commit"] == got["records"]["intent"]
        assert rec["Verify read"].startswith("show interfaces dampening: parsed")

    def test_rolled_back_is_drawn_as_dampening_rolled_back(self, stores, measured, monkeypatch,
                                                           FakeSources):
        src = FakeSources(verify=_read(SHAPED).replace("GigabitEthernet2", "GigabitEthernet3"))
        _d, got = run(src, monkeypatch)
        assert got["outcome"] == "rolled_back"
        (e,) = history("r2")
        assert e["what"].endswith(f"r2 {GI2} dampening rolled back"), e["what"]
        assert dict(e["record"])["Intent put back"].startswith("put back as")


# ── Needs attention ────────────────────────────────────────────────────────────────────────

class TestNeedsAttention:
    def rows(self, decisions, now=T0 + 60):
        from modules import attention
        return attention._heal_dampening_rows(NET, decisions, now)

    def proposal(self, **kw):
        d = {"id": "hd-p1", "outcome": "propose", "device": "r2", "epoch": T0, "at": "",
             "words": "proposed for a person", "kind": "dampening_proposal", "tier": 2,
             "action": {"kind": "dampening_proposal", "device": "r2", "interface": GI2,
                        "trigger": "still_flapping"}}
        d.update(kw)
        return d

    def test_one_row_per_waiting_port_opening_its_card_clearing_when_stable(self):
        (r,) = self.rows([bounce(epoch=T0 - 600), self.proposal()])
        assert (r["kind"], r["action"]["open"], r["action"]["decision"]) == (
            "dampening", "heal_proposal", "hd-p1")
        assert r["clears_at"] == D()._iso(T0 + 24 * 3600)
        assert self.rows([self.proposal()], now=T0 + 24 * 3600) == []
        # A later need of the port moves the 24 hours.
        (r,) = self.rows([self.proposal(), bounce(epoch=T0 + 3600, did="hd-b2")])
        assert r["clears_at"] == D()._iso(T0 + 3600 + 24 * 3600)

    def test_approved_and_dampened_or_declined_is_no_row(self):
        for outcome in ("dampened", "declined"):
            d = self.proposal(taken={"by": PERSON, "at": ""},
                              applied={"outcome": outcome, "by": PERSON, "words": "w"})
            assert self.rows([d]) == []

    def test_approved_and_rolled_back_is_its_own_row_until_a_later_need(self):
        d = self.proposal(taken={"by": PERSON, "at": ""},
                          applied={"outcome": "rolled_back", "by": PERSON, "words": "w"})
        (r,) = self.rows([d])
        assert r["level"] == "danger" and "rolled back" in r["what"]
        assert self.rows([d, bounce(epoch=T0 + 30, did="hd-b2")]) == []

    def test_the_general_proposal_row_leaves_it_to_its_own(self):
        from modules import attention
        assert attention._heal_proposal_rows(NET, [self.proposal()]) == []

    def test_the_kind_is_declared_with_how_it_clears(self):
        from modules import attention
        ways, words = attention.CLEARS[("heal", "dampening")]
        assert set(ways) == {"resolves", "time"} and "24" in words


class TestTheCapturedAnswer:
    """C2761: the answer with dampening on no port, captured through the reads engine on
    2026-11-08 05:16 UTC (run ids 20261108T051623895335Z-065eaf51 on the IOS-XE router and
    20261108T051626450591Z-1868a144 on the IOS switch): each printed nothing at all."""

    @pytest.mark.parametrize("name", ["r2__show_interfaces_dampening.txt",
                                      "s1__show_interfaces_dampening.txt"])
    def test_no_port_dampened_reads_as_tracking_nothing(self, name):
        here = os.path.join(os.path.dirname(__file__), "fixtures", "heal_dampening", name)
        with open(here, encoding="utf-8") as fh:
            text = fh.read()
        assert text == "", "the capture is the device's empty answer"
        got = D().parse(text, "GigabitEthernet4")
        assert (got["state"], got["tracked"], got["interfaces"]) == ("parsed", False, {}), got
