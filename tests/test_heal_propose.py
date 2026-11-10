"""Heal to intent's Tier 2: the proposal, its approve and decline, and the measured OSPF process
reset (`modules/heal/propose.py`, `routes/heal_proposal_v2.py`, `modules/nsot/privileged.py`'s
`PROCESS_RESETS`; board H, part H5, docs/HEAL_TO_INTENT.md sections 5, 9, 11 and 19.8, N17;
C2374), no network, no device.

- **The reset, privileged's pattern:** the routing process's header picks the reset (OSPF and
  OSPFv3 each their own; BGP never; a process id one token of digits); it is refused as not
  measured until the platform record holds a measurement (the shipped record holds none), and
  absent and unreadable records are different refusals; N17's one adjacency; the measured
  prompt alone answered with the measured answer, any other question unanswered; the verify on
  the real neighbour tables, IPv4 and IPv6, within 2.5 times the measured settle time.
- **The proposal:** what a person reads (the program masked, the reset, what it affects and
  why rollback cannot undo it), its hash, and why it would refuse now.
- **Approve:** a verified person, a reason, the hash as previewed; refused with nothing taken
  otherwise, and while the reset is unmeasured; then taken once, applied AS THE PERSON (their
  reason on every flagged line, ``Actor-Verified: access`` in the job), the reset sent on the
  apply's session after its intent check and before its save, its Tier 2 record written; a
  reset not made puts the change back; one made is kept and the symptom decides.
- **Decline:** a verified person and a reason; recorded, the incident closed, nothing sent.
- **Interrupted:** an approved proposal whose job ended first is found and recorded as a
  heal's is.
- **The routes,** on a test app of their own (H9 drew their screen and registered them):
  their gates, invalidations, stages and History declarations hold the tables' own checks.

The reset's measurement record in these tests is a test record, not a measurement: its prompt
and answer are placeholders, and the real ones are H11's run on the lab's devices.
"""
import json
import os
import types

import pytest

from tests.test_heal_act import FakeAct
from tests.test_heal_decide import GOLDEN, PLATFORM, Fake, changed, settle
from tests.test_heal_decide import lab  # the fixture, named by each test below
from tests.test_heal_policy import T0
from tests.test_sdn_connections import networks  # the fixture `lab` builds on
from tests.test_heal_triggers import _Lazy

P, DC, DS, I, INT, SL = (_Lazy("propose"), _Lazy("decide"), _Lazy("decisions"),
                         _Lazy("incidents"), _Lazy("interrupted"), _Lazy("steplog"))
PERSON = "op@example.com"
WHO = {"actor": PERSON, "actor_verified": "access", "person": True}
REASON = "the duplicate router-id from the console change"
R8 = changed((" router-id 192.0.2.6\n", " router-id 192.0.2.99\n"))
GOLDEN6 = GOLDEN + "ipv6 router ospf 1\n router-id 192.0.2.6\n"
R8_6 = GOLDEN + "ipv6 router ospf 1\n router-id 192.0.2.99\n"
#: A test record's placeholders, not a measurement (the module's docstring).
PROMPT = "Reset OSPF process 1? [no]:"
ANSWER = "yes"
OPS = os.path.join(os.path.dirname(__file__), "fixtures", "operational")


def _cap(name):
    with open(os.path.join(OPS, name), encoding="utf-8") as fh:
        return fh.read()


#: Real captures: s3's IPv4 table (two FULL, three 2WAY) and r3's OSPFv3 table (four FULL).
NB4 = _cap("s3__show_ip_ospf_neighbor.txt")
NB6 = _cap("r3__show_ipv6_ospf_neighbor.txt")
#: The same IPv4 table, minimally edited: every neighbour stuck, none formed.
NB4_DOWN = NB4.replace("2WAY/DROTHER", "INIT/DROTHER ").replace("FULL/DR ", "EXSTART/DR ") \
    .replace("FULL/BDR", "EXSTART/BDR")
#: The IPv4 table cut to its one neighbour (N17's router with one adjacency).
NB4_ONE = "\n".join(NB4.splitlines()[:3]) + "\n"


def priv():
    from modules.nsot import privileged

    return privileged


@pytest.fixture(autouse=True)
def no_host_addresses(monkeypatch):
    monkeypatch.setattr("modules.nsot.removal.host_addresses", lambda: ["192.0.2.60"])


@pytest.fixture
def measured(tmp_path, monkeypatch):
    """A measurement record holding every reset on the test platform (placeholders)."""
    rows = {k: {"prompt": PROMPT, "answer": ANSWER, "settle_s": 40, "device": "edge-b",
                "at": "2026-11-10T00:00:00Z"} for k in priv().PROCESS_RESETS}
    path = tmp_path / "privileged_measured.json"
    path.write_text(json.dumps({"by_dialect": {PLATFORM: rows}, "unmeasured": {}}))
    monkeypatch.setattr(priv(), "RESET_MEASURED_FILE", str(path))
    return rows


@pytest.fixture
def unmeasured(tmp_path, monkeypatch):
    """The shipped record with its one measured reset (IOS-XE's `clear ip ospf N process`,
    2026-11-08, C2374) taken back out, so every reset is unmeasured again."""
    rec = json.loads(open(priv().RESET_MEASURED_FILE, encoding="utf-8").read())
    for rows in rec["by_dialect"].values():
        rows.pop("clear-ospf-process", None)
    rec["unmeasured"].setdefault(PLATFORM, {})["clear-ospf-process"] = "not run yet: a test's"
    path = tmp_path / "unmeasured.json"
    path.write_text(json.dumps(rec))
    monkeypatch.setattr(priv(), "RESET_MEASURED_FILE", str(path))
    return rec


class FakeApproved(FakeAct):
    """The act's fake sources (H4's), and the reset sent on the apply's session: recorded with
    whether it ran inside the apply (the check after verify, the device held, its save held)."""

    def __init__(self, running, *, reset=None, **kw):
        super().__init__(running, **kw)
        self._reset, self.resets, self.verified_as = reset, [], None

    def reset(self, device, dev, ctx, plan):
        self.resets.append((plan["command"], self.in_apply))
        return dict(self._reset or {
            "state": "done", "before": NB4_DOWN, "after": NB4, "printed": "", "waited_s": 12.0,
            "verify": priv().reset_verify(NB4_DOWN, NB4)})

    def apply(self, device, **kw):
        from modules import identity

        self.verified_as = identity.actor_verification(kw["actor"])
        return super().apply(device, **kw)


def proposed(running=R8, golden=GOLDEN):
    """A proposal on edge-b, made in dry run by the real decision, recorded."""
    inc = settle(running, golden=golden)
    d = DC.decide_one("Default", inc, now=T0, sources=Fake(running, golden=golden,
                                                           intended=golden))
    assert d["outcome"] == "propose", d["words"]
    return DS.record("Default", d, T0)


def approve(d, src, **kw):
    v = P.view("Default", d["id"], now=T0 + 1, sources=src)
    started = []
    args = dict(confirmed_hash=v["hash"], reason=REASON, now=T0 + 2, sources=src,
                starter=lambda n, taken, approval, **k: started.append((taken, approval))
                or "job-1", **WHO)
    args.update(kw)
    return P.approve("Default", d["id"], **args), started, v


def run_approved(d, src, **kw):
    """Approve, then run the act the job runs, here."""
    out, started, v = approve(d, src, **kw)
    ((taken, approval),) = started
    try:
        got = P.apply_approved("Default", taken, approval, now=T0 + 3, sources=src)
    finally:
        INT.release("Default", d["id"])
    return got, approval, v


def applied(decision_id):
    return DS.find("Default", decision_id).get("applied") or {}


# ── The reset (privileged's pattern) ────────────────────────────────────────────────────────

class TestTheResetsShape:
    @pytest.mark.parametrize("section, key, command", [
        ("router ospf 1", "clear-ospf-process", "clear ip ospf 1 process"),
        ("ipv6 router ospf 2", "clear-ipv6-ospf-process", "clear ipv6 ospf 2 process"),
        ("router ospfv3 3", "clear-ospfv3-process", "clear ospfv3 3 process")])
    def test_the_process_header_picks_its_reset(self, measured, section, key, command):
        which = priv().reset_for(section)
        assert (which["key"], which["refused"]) == (key, "")
        plan = priv().reset_plan(which["key"], which["process"], dialect=PLATFORM)
        assert plan["ok"] and plan["command"] == command

    def test_bgp_is_never_reset(self):
        got = priv().reset_for("router bgp 65000")
        assert got["key"] == "" and "never sends `clear ip bgp *`" in got["refused"]

    @pytest.mark.parametrize("section", ["router ospf 1 vrf X", "router ospf ONE",
                                         "interface GigabitEthernet1"])
    def test_anything_else_is_refused_naming_why(self, section):
        got = priv().reset_for(section)
        assert got["process"] == "" and got["refused"], got

    def test_a_process_id_is_one_token_of_digits(self, measured):
        plan = priv().reset_plan("clear-ospf-process", "1; reload", dialect=PLATFORM)
        assert not plan["ok"] and "one token of digits" in plan["refused"]

    def test_the_reset_is_never_on_the_actions_menu(self):
        assert not set(priv().PROCESS_RESETS) & set(priv().COMMANDS)
        assert not set(priv().PROCESS_RESETS) & set(priv().NOT_MEASURED)

    def test_its_reads_are_on_the_read_only_allowlist(self):
        from modules.readonly_commands import refusal

        for spec in priv().PROCESS_RESETS.values():
            assert refusal(spec["read"]) == "", spec["read"]
            assert refusal(spec["command"].format(process="1")), "the reset itself is no read"


class TestNotMeasured:
    @pytest.mark.parametrize("key", ["clear-ospf-process", "clear-ipv6-ospf-process"])
    def test_the_shipped_record_measures_no_reset_and_refuses_saying_so(self, key):
        # C2374: IOS-XE's `clear ip ospf N process` was measured 2026-11-08; every other
        # reset, on each dialect it is unmeasured on, is refused saying why.
        rec = priv().reset_measured()
        assert rec["state"] == "ok"
        dialects = ("cisco_ios",) if key == "clear-ospf-process" else ("cisco_ios",
                                                                        "cisco_iosxe")
        for dialect in dialects:
            assert key not in rec["by_dialect"].get(dialect, {}), (dialect, key)
            assert rec["unmeasured"][dialect][key], "each unmeasured reset says why"
            plan = priv().reset_plan(key, "1", dialect=dialect)
            assert not plan["ok"] and f"is not measured on {dialect}" in plan["refused"]
            assert "nmas-tier2-probe" in plan["refused"], plan["refused"]
            assert plan["refused"].endswith("Nothing was sent")
            assert plan["command"], "the preview still names what would be sent"

    def test_absent_and_unreadable_are_different_refusals(self, tmp_path, monkeypatch):
        monkeypatch.setattr(priv(), "RESET_MEASURED_FILE", str(tmp_path / "none.json"))
        absent = priv().reset_plan("clear-ospf-process", "1", dialect=PLATFORM)
        (tmp_path / "bad.json").write_text("{not json")
        monkeypatch.setattr(priv(), "RESET_MEASURED_FILE", str(tmp_path / "bad.json"))
        bad = priv().reset_plan("clear-ospf-process", "1", dialect=PLATFORM)
        assert "is absent" in absent["refused"] and "cannot be read" in bad["refused"]
        assert not absent["ok"] and not bad["ok"]

    @pytest.mark.parametrize("row, words", [
        ({"answer": "yes", "settle_s": 40, "device": "x", "at": "t"}, "no prompt"),
        ({"prompt": PROMPT, "settle_s": 40, "device": "x", "at": "t"}, "no answer"),
        ({"prompt": None, "settle_s": 0, "device": "x", "at": "t"}, "no settle time"),
        ({"prompt": None, "settle_s": 40}, "no device or time")])
    def test_an_incomplete_measurement_allows_nothing(self, tmp_path, monkeypatch, row, words):
        path = tmp_path / "m.json"
        path.write_text(json.dumps({"by_dialect": {PLATFORM: {"clear-ospf-process": row}}}))
        monkeypatch.setattr(priv(), "RESET_MEASURED_FILE", str(path))
        plan = priv().reset_plan("clear-ospf-process", "1", dialect=PLATFORM)
        assert not plan["ok"] and words in plan["refused"]

    def test_a_measured_reset_waits_two_and_a_half_times_its_settle(self, measured):
        plan = priv().reset_plan("clear-ospf-process", "1", dialect=PLATFORM)
        assert (plan["prompt"], plan["answer"], plan["bound_s"]) == (PROMPT, ANSWER, 100)
        assert plan["measured"] == {"device": "edge-b", "at": "2026-11-10T00:00:00Z"}


class TestN17:
    def test_one_adjacency_alone_allows_the_single_adjacency_reset(self, measured):
        ok = priv().reset_plan("clear-ospf-process", "1", dialect=PLATFORM,
                               purpose="single_adjacency", before=NB4_ONE)
        many = priv().reset_plan("clear-ospf-process", "1", dialect=PLATFORM,
                                 purpose="single_adjacency", before=NB4)
        assert ok["ok"], ok["refused"]
        assert not many["ok"] and "has 5 OSPF adjacencies" in many["refused"]
        assert "stays Alert" in many["refused"]

    def test_an_unreadable_table_never_counts_as_one(self, measured):
        got = priv().reset_plan("clear-ospf-process", "1", dialect=PLATFORM,
                                purpose="single_adjacency", before="% Invalid input")
        assert not got["ok"] and "could not be read" in got["refused"]

    def test_a_router_id_reset_is_not_held_to_one_adjacency(self, measured):
        assert priv().reset_plan("clear-ospf-process", "1", dialect=PLATFORM,
                                 purpose="router_id", before=NB4)["ok"]

    def test_an_unknown_purpose_is_refused(self, measured):
        got = priv().reset_plan("clear-ospf-process", "1", dialect=PLATFORM, purpose="flap")
        assert not got["ok"] and "not 'flap'" in got["refused"]


class TestTheTables:
    def test_formed_reads_the_real_tables_ipv4_and_ipv6(self):
        assert (priv().adjacencies(NB4), priv().formed(NB4)) == (5, 5)
        assert (priv().adjacencies(NB6), priv().formed(NB6)) == (4, 4)
        assert (priv().adjacencies(NB4_DOWN), priv().formed(NB4_DOWN)) == (5, 0)

    def test_a_blank_table_is_empty_and_another_shape_is_unknown(self):
        assert priv().formed("") == 0 and priv().formed("   \n") == 0
        assert priv().formed("% OSPF: Router process 1 is not running") is None

    @pytest.mark.parametrize("before, after, ok", [
        (NB4_DOWN, NB4, True), (NB4, NB4_DOWN, False), (NB4, NB4, True), (NB6, NB6, True),
        ("", "", False), (NB4, "garbled", None)])
    def test_the_verify_rule(self, before, after, ok):
        assert priv().reset_verify(before, after)["ok"] is ok


class _Session:
    """A device's session at the seam `send_reset` reads and sends through: each read
    answered in turn, each send's answer by its text."""

    def __init__(self, reads, sends):
        self.reads, self.sends, self.sent, self.read_cmds = list(reads), sends, [], []

    def read(self, cmd):
        self.read_cmds.append(cmd)
        return self.reads.pop(0) if len(self.reads) > 1 else self.reads[0]

    def send(self, text):
        self.sent.append(text)
        return self.sends.get(text, "edge-b#")


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class TestTheSend:
    def _plan(self, measured, key="clear-ospf-process"):
        return priv().reset_plan(key, "1", dialect=PLATFORM, device="edge-b")

    def test_the_measured_prompt_is_answered_and_the_table_read_until_formed(self, measured):
        s = _Session([NB4_DOWN, NB4_DOWN, NB4_DOWN, NB4],
                     {"clear ip ospf 1 process": f"clear ip ospf 1 process\n{PROMPT}",
                      ANSWER: "\nedge-b#"})
        clock = _Clock()
        got = priv().send_reset(self._plan(measured), read=s.read, send=s.send, clock=clock,
                                sleep=clock.sleep)
        assert got["state"] == "done", got
        assert s.sent == ["clear ip ospf 1 process", ANSWER], "sent once, answered once"
        assert got["before"] == NB4_DOWN, "the before-state is kept"
        assert got["waited_s"] == 2 * priv().RESET_POLL_S
        assert set(s.read_cmds) == {"show ip ospf neighbor"}

    def test_the_ipv6_reset_reads_its_own_table(self, measured):
        s = _Session([NB6], {"clear ipv6 ospf 1 process": PROMPT, ANSWER: "edge-b#"})
        got = priv().send_reset(self._plan(measured, "clear-ipv6-ospf-process"), read=s.read,
                                send=s.send, clock=_Clock(), sleep=lambda s_: None)
        assert got["state"] == "done" and set(s.read_cmds) == {"show ipv6 ospf neighbor"}

    def test_another_question_is_never_answered(self, measured):
        s = _Session([NB4], {"clear ip ospf 1 process": "Reset ALL OSPF processes? [no]:"})
        got = priv().send_reset(self._plan(measured), read=s.read, send=s.send)
        assert got["state"] == "refused" and "not the measured prompt" in got["why"]
        assert s.sent == ["clear ip ospf 1 process"], "nothing answered it"

    def test_a_device_that_refuses_it_reset_nothing(self, measured):
        s = _Session([NB4], {"clear ip ospf 1 process": PROMPT,
                             ANSWER: "\n% OSPF: process 1 not running\nedge-b#"})
        got = priv().send_reset(self._plan(measured), read=s.read, send=s.send)
        assert got["state"] == "rejected" and got["why"].startswith("% OSPF")

    def test_adjacencies_not_back_within_the_bound_say_so(self, measured):
        s = _Session([NB4, NB4_DOWN], {"clear ip ospf 1 process": PROMPT, ANSWER: "edge-b#"})
        clock = _Clock()
        got = priv().send_reset(self._plan(measured), read=s.read, send=s.send, clock=clock,
                                sleep=clock.sleep)
        assert got["state"] == "not_back" and got["waited_s"] >= 100

    def test_an_unplanned_reset_sends_nothing(self):
        s = _Session([NB4], {})
        got = priv().send_reset({"ok": False, "refused": "not measured"}, read=s.read,
                                send=s.send)
        assert got["state"] == "refused" and s.sent == [] and s.read_cmds == []


# ── The proposal ────────────────────────────────────────────────────────────────────────────

class TestTheProposal:
    def test_a_router_id_proposal_reads_with_its_reset_refused_until_measured(self, lab,
                                                                              unmeasured):
        d = proposed()
        v = P.view("Default", d["id"], now=T0 + 1, sources=FakeApproved(R8))
        assert v["kind"] == "process_reset" and v["tier"] == 2
        assert v["program"] == d["program"] and d["program"], "the program, masked"
        assert v["reset"]["command"] == "clear ip ospf 1 process"
        assert v["lines"] == v["program"] + ["clear ip ospf 1 process"]
        assert "cannot be undone" in v["reset"]["rollback"]
        assert "every OSPF adjacency of process 1 on edge-b" in v["reset"]["affects"]
        assert not v["confirmable"] and "is not measured on cisco_iosxe" in v["refusals"][0]

    def test_measured_it_is_confirmable_and_its_hash_binds_the_reset(self, lab, measured):
        d = proposed()
        v = P.view("Default", d["id"], now=T0 + 1, sources=FakeApproved(R8))
        assert v["confirmable"], v["refusals"]
        assert v["hash"] == P.proposal_hash("Default", d, "clear ip ospf 1 process")
        assert v["hash"] != P.proposal_hash("Default", d, "clear ip ospf 2 process")
        assert v["hash"] != P.proposal_hash("Default", dict(d, program_hash="x"),
                                            "clear ip ospf 1 process")

    def test_an_ipv6_router_id_proposes_the_ospfv3_reset(self, lab, measured):
        d = proposed(R8_6, GOLDEN6)
        v = P.view("Default", d["id"], now=T0 + 1, sources=FakeApproved(R8_6, golden=GOLDEN6,
                                                                         intended=GOLDEN6))
        assert v["reset"]["command"] == "clear ipv6 ospf 1 process" and v["confirmable"]

    def test_only_a_proposal_is_read_as_one(self, lab):
        with pytest.raises(P.Refused, match="no heal decision"):
            P.view("Default", "hd-000000000000", sources=FakeApproved(R8))
        from tests.test_heal_act import decided
        from tests.test_heal_decide import ROUTE4

        d = decided(GOLDEN + ROUTE4)
        with pytest.raises(P.Refused, match="not a proposal"):
            P.view("Default", d["id"], sources=FakeApproved(R8))

    def test_the_stops_are_its_refusals(self, lab, measured):
        d = proposed()
        DS.halt("Default", guard=10, name="rate", words="six heals in an hour", operands={},
                now=T0)
        v = P.view("Default", d["id"], now=T0 + 1, sources=FakeApproved(R8))
        assert not v["confirmable"] and "halted by guard 10" in v["refusals"][0]
        held = FakeApproved(R8, planned={"words": "a planned window until 10:00"})
        DS.lift("Default", DS.halted("Default")["id"], reason="lifted for the test", **{
            "by": PERSON, "actor_verified": "access", "person": True})
        v = P.view("Default", d["id"], now=T0 + 1, sources=held)
        assert "guard 3, planned work" in v["refusals"][0]


# ── Approve ─────────────────────────────────────────────────────────────────────────────────

class TestApproveRefuses:
    @pytest.mark.parametrize("who", [
        {"actor": "", "actor_verified": "none", "person": False},
        {"actor": PERSON, "actor_verified": "none", "person": True},
        {"actor": "svc", "actor_verified": "access", "person": False}])
    def test_only_a_verified_person_approves(self, lab, measured, who):
        d = proposed()
        with pytest.raises(P.NotAPerson):
            approve(d, FakeApproved(R8), **who)
        assert [x["id"] for x in DS.proposals("Default")] == [d["id"]], "nothing taken"

    def test_a_reason_is_needed(self, lab, measured):
        d = proposed()
        with pytest.raises(P.Refused, match="reason of 3 words"):
            approve(d, FakeApproved(R8), reason="ok")

    def test_a_hash_not_the_previewed_one_is_refused_naming_both(self, lab, measured):
        d = proposed()
        with pytest.raises(P.Refused) as exc:
            approve(d, FakeApproved(R8), confirmed_hash="0" * 16)
        assert "confirmed 0000000000000000, now" in str(exc.value)
        assert DS.proposals("Default"), "the proposal still waits"

    def test_an_unmeasured_reset_is_refused_with_nothing_taken(self, lab, unmeasured):
        d = proposed()
        src = FakeApproved(R8)
        with pytest.raises(P.Refused, match="is not measured on cisco_iosxe"):
            approve(d, src, confirmed_hash=P.view("Default", d["id"], sources=src)["hash"])
        assert DS.proposals("Default") and src.resets == [] and src.apply_kw is None

    def test_self_healing_off_or_a_kind_no_longer_proposed_refuses(self, lab, measured):
        d = proposed()
        src = FakeApproved(R8, mode=lambda m: dict(m, mode="off", words="off"))
        with pytest.raises(P.Refused, match="self-healing is off for Default"):
            approve(d, FakeApproved(R8), sources=src)
        src = FakeApproved(R8, mode=lambda m: dict(m, kinds_propose=["qos_policy"]))
        with pytest.raises(P.Refused, match="process_reset is no longer proposed"):
            approve(d, FakeApproved(R8), sources=src)

    def test_a_second_approval_is_refused(self, lab, measured):
        d = proposed()
        src = FakeApproved(R8)
        out, _started, v = approve(d, src)
        assert out["job"] == "job-1"
        with pytest.raises(P.Refused, match="was taken by"):
            P.approve("Default", d["id"], confirmed_hash=v["hash"], reason=REASON, now=T0 + 3,
                      sources=src, starter=lambda *a, **k: pytest.fail("started twice"), **WHO)
        INT.release("Default", d["id"])


class TestTheApprovedAct:
    def test_applied_as_the_person_then_the_reset_while_held(self, lab, measured):
        d = proposed()
        src = FakeApproved(R8)
        got, approval, v = run_approved(d, src)
        assert got["outcome"] == "healed", got["words"]
        kw = src.apply_kw
        assert (kw["actor"], kw["actor_kind"]) == (PERSON, "person")
        assert kw["hold_detail"] == f"heal proposal approved by {PERSON}"
        assert kw["heal"]["edge-b"]["approved"] == {"by": PERSON, "verified": "access",
                                                    "reason": REASON, "hash": v["hash"]}
        assert src.resets == [("clear ip ospf 1 process", True)], \
            "the reset is sent inside the apply: after verify, held, before its save"
        entry = src.plan("edge-b", **src.plan_kw)
        assert entry["commands"] == d["program"], "what is approved is what is sent"
        names = [s["step"] for s in got["steps"]]
        assert set(names) <= {n for n, _w in P.STEPS}
        assert names.index("intent") < names.index("reset") < names.index("saved")
        assert applied(d["id"])["outcome"] == "healed"
        assert applied(d["id"])["by"] == PERSON
        (inc,) = I.read("Default")["incidents"]
        assert inc["state"] == "closed" and d["id"] in inc["closed_why"]

    def test_the_reset_is_a_tier_2_record_as_the_person(self, lab, measured):
        from modules.nsot import privileged

        d = proposed()
        got, _approval, v = run_approved(d, FakeApproved(R8))
        (run,) = privileged.runs("Default")["runs"]
        assert (run["actor"], run["reason"], run["command"]) == (
            PERSON, REASON, "clear ip ospf 1 process")
        assert (run["state"], run["hash"], run["decision"]) == ("done", v["hash"], d["id"])
        assert run["before"] == NB4_DOWN, "its before-state kept (T2-4)"
        assert got["report"]["results"][0]["heal"]["reset"]["run"] == run["id"]

    def test_the_step_log_and_records_name_the_person(self, lab, measured):
        d = proposed()
        got, _approval, v = run_approved(d, FakeApproved(R8))
        rows = [r for r in SL.read("Default")["rows"] if r.get("decision") == d["id"]]
        started = next(r for r in rows if r["row"] == "started")
        act = next(r for r in rows if r["row"] == "act")
        assert started["by"] == act["by"] == PERSON
        assert started["program"][-1] == "clear ip ospf 1 process", \
            "the reset is written before anything is sent, with the program"
        rec = got["records"]
        assert f"approved by {PERSON} (access)" in rec["approval"] and v["hash"] in \
            rec["approval"]
        cr = rec["change_record"]["markdown"]
        assert f"returned to intent on {PERSON}'s approval" in cr
        assert f"Approved by {PERSON}" in cr and REASON in cr
        assert "`clear ip ospf 1 process`" in cr and "cannot be undone" in cr

    def test_the_person_s_reason_carries_each_flagged_line(self, lab, measured, monkeypatch):
        """R8's program flags no line, so the CI gate's flag is planted on its router-id (the
        one definition both the act and the plan's check read)."""
        from modules.nsot import authorisation

        planted = authorisation.flagged
        monkeypatch.setattr(authorisation, "flagged", lambda commands, extra=(): sorted(
            set(planted(commands, extra)) | {authorisation.key(c) for c in commands
                                             if "router-id" in c}))
        d = proposed()
        src = FakeApproved(R8)
        got, _a, _v = run_approved(d, src)
        auth = src.plan_kw["authorise"]["edge-b"]
        entry = src.plan("edge-b", **src.plan_kw)
        assert {a["line"] for a in auth} == {"router-id 192.0.2.6"}
        assert all(a["reason"] == REASON for a in auth), "the person's reason, not the policy's"
        assert entry["authorisation_ok"] and got["outcome"] == "healed", got["words"]

    def test_the_job_runs_as_the_person_actor_verified_access(self, lab, measured,
                                                              monkeypatch):
        d = proposed()
        src = FakeApproved(R8)
        monkeypatch.setattr("modules.nsot.capture_job.start",
                            lambda net, label, actor, work, **kw: work("job-9") and "job-9")
        ident = types.SimpleNamespace(is_identified=True, actor=PERSON, kind="person")
        v = P.view("Default", d["id"], now=T0 + 1, sources=src)
        out = P.approve("Default", d["id"], confirmed_hash=v["hash"], reason=REASON,
                        now=T0 + 2, sources=src, ident=ident, **WHO)
        assert out["job"] == "job-9" and src.verified_as == "access"
        assert INT.mark_state("Default", d["id"])[0] == "none", "the job released its mark"

    def test_a_reset_not_made_puts_the_router_id_back(self, lab, measured):
        d = proposed()
        src = FakeApproved(R8, reset={"state": "refused", "why": "the device asked 'x?'"})
        got, _a, _v = run_approved(d, src)
        assert got["outcome"] == "rolled_back", got["words"]
        assert "put back: nothing is left half applied" in got["words"]
        assert DS.halted("Default")["guard"] == 14, "a rolled-back heal halts (guard 14)"

    def test_a_reset_made_whose_adjacencies_stay_down_is_kept(self, lab, measured):
        d = proposed()
        src = FakeApproved(R8, reset={
            "state": "not_back", "before": NB4, "after": NB4_DOWN, "waited_s": 100.0,
            "verify": priv().reset_verify(NB4, NB4_DOWN)},
            symptom={"state": "present", "words": "the symptom is still there"})
        got, _a, _v = run_approved(d, src)
        assert got["outcome"] == "symptom_remains", got["words"]
        assert src.symptoms == 1 and src.symptoms_in_apply == 0, \
            "a reset cannot be undone: the symptom is read once the device is released"

    def test_a_device_changed_since_the_proposal_is_refused_and_closed(self, lab, measured):
        d = proposed()
        moved = R8 + "ip route 192.0.2.128 255.255.255.128 192.0.2.10\n"
        got, _a, _v = run_approved(d, FakeApproved(moved))
        assert got["outcome"] == "refused" and got["sent"] is False
        assert "not the one proposed" in got["words"] and "Nothing was sent" in got["words"]
        (inc,) = I.read("Default")["incidents"]
        assert inc["state"] == "closed", "a later read starts over"

    def test_a_proposal_with_no_reset_sends_its_merge_alone(self, lab):
        key = " ip ospf message-digest-key 1 md5 S3cretKey\n"
        golden = changed((" ip ospf cost 10\n", " ip ospf cost 10\n" + key))
        d = proposed(GOLDEN, golden)
        assert d["kind"] == "secret_added_back", d["kind"]
        src = FakeApproved(GOLDEN, golden=golden, intended=golden,
                           post=__import__("modules.heal.kinds", fromlist=["x"])._stored(golden))
        v = P.view("Default", d["id"], now=T0 + 1, sources=src)
        assert v["reset"] is None and v["confirmable"], v["refusals"]
        assert "S3cretKey" not in json.dumps(v), "the program is masked"
        got, _a, _v = run_approved(d, src)
        assert got["outcome"] == "healed", got["words"]
        assert src.resets == []


# ── Decline ─────────────────────────────────────────────────────────────────────────────────

class TestDecline:
    def test_declined_recorded_closed_and_nothing_sent(self, lab):
        d = proposed()
        got = P.decline("Default", d["id"], reason="not during the course lab", now=T0 + 2,
                        **WHO)
        assert got["outcome"] == "declined" and got["sent"] is False
        assert applied(d["id"]) == {"outcome": "declined", "by": PERSON, "at": got["records"][
            "approval"].split(" at ")[1].split(",")[0],
            "words": f"declined by {PERSON}: not during the course lab"}
        (inc,) = I.read("Default")["incidents"]
        assert inc["state"] == "closed"
        (act,) = [r for r in SL.read("Default")["rows"] if r.get("row") == "act"]
        assert act["by"] == PERSON and act["outcome"] == "declined"
        assert DS.proposals("Default") == []
        assert INT.find("Default")["found"] == [], "a declined proposal is never interrupted"

    def test_only_a_verified_person_declines_with_a_reason(self, lab):
        d = proposed()
        with pytest.raises(P.NotAPerson):
            P.decline("Default", d["id"], reason="not now please", actor="",
                      actor_verified="none", person=False)
        with pytest.raises(P.Refused, match="reason"):
            P.decline("Default", d["id"], reason="", **WHO)
        assert DS.proposals("Default")

    def test_a_declined_proposal_is_not_approved_or_declined_again(self, lab, measured):
        d = proposed()
        P.decline("Default", d["id"], reason="not during the course lab", **WHO)
        with pytest.raises(P.Refused, match="was taken by"):
            P.decline("Default", d["id"], reason="not during the course lab", **WHO)
        with pytest.raises(P.Refused, match="was taken by"):
            approve(d, FakeApproved(R8))


# ── Withdrawn (C2470) ───────────────────────────────────────────────────────────────────────

#: Board H artboard E: "If r6 changes, the proposal is withdrawn and made again". R8 changed
#: again: another router-id, so another departure from the golden.
R8_AGAIN = changed((" router-id 192.0.2.6\n", " router-id 192.0.2.98\n"))


def _dep(running):
    from modules.drift_check import departure, drift_diff

    return departure(drift_diff(GOLDEN, running, "edge-b"))


class _Check:
    """`drift_check.check_device` as the detect pass calls it: the device read as *running*
    (its departure from the golden computed by the real comparison), counted."""

    def __init__(self, running=None, error=""):
        self.running, self.error, self.calls = running, error, []

    def __call__(self, network, device, by):
        self.calls.append(device)
        if self.error:
            return {"ok": False, "state": "unknown", "error": self.error}
        dep = _dep(self.running)
        return {"ok": True, "state": "drifted" if dep else "clean", "departure": dep,
                "changed_lines": 1 if dep else 0, "read_at": None}


def _pass(t, check):
    from modules.heal import detect

    return detect.run("Default", now=t, check=check, clock=lambda: t)


def _incident():
    (inc,) = I.read("Default")["incidents"]
    return inc


class TestWithdrawn:
    """A waiting proposal's device read again by the heal's own pass: back at intent, it is
    withdrawn and its incident closed; changed, withdrawn and made again by the normal path."""

    def test_back_at_intent_it_is_withdrawn_recorded_and_its_row_gone(self, lab):
        from modules import attention

        d = proposed()
        assert attention._heal_proposal_rows("Default", DS.decisions("Default")), "a row first"
        out = _pass(T0 + 121, _Check(GOLDEN))
        assert [w["how"] for w in out["withdrawn"]] == ["at_intent"]
        assert DS.proposals("Default") == []
        got = DS.find("Default", d["id"])
        assert got["applied"]["outcome"] == "withdrawn"
        w = got["withdrawn"]
        assert w["how"] == "at_intent" and w["bound"]["departure"] == d["departure"] != ""
        assert w["read"]["state"] == "clean" and w["read"]["departure"] == ""
        assert "read back at its golden, which matches its intent" in w["words"]
        assert d["departure"] in w["words"], "the words name the state it was bound to"
        inc = _incident()
        assert inc["state"] == "closed" and inc["closed_why"].startswith("withdrawn: ")
        (act,) = [r for r in SL.read("Default")["rows"] if r.get("row") == "act"]
        assert act["outcome"] == "withdrawn" and act["sent"] is False
        assert attention._heal_proposal_rows("Default", DS.decisions("Default")) == []
        assert INT.find("Default")["found"] == [], "a withdrawn proposal is never interrupted"

    def test_changed_it_is_withdrawn_and_made_again_by_the_decision(self, lab):
        d = proposed()
        out = _pass(T0 + 121, _Check(R8_AGAIN))
        assert [w["how"] for w in out["withdrawn"]] == ["changed"]
        w = DS.find("Default", d["id"])["withdrawn"]
        assert (w["bound"]["departure"], w["read"]["departure"]) == (d["departure"],
                                                                    _dep(R8_AGAIN))
        assert d["departure"] in w["words"] and _dep(R8_AGAIN) in w["words"], \
            "the words name both departures"
        assert _incident()["state"] == "watching", "sent back to the grace period"
        assert DS.proposals("Default") == []
        # The normal path makes it again: two reads the grace apart, then the decision.
        check = _Check(R8_AGAIN)
        _pass(T0 + 200, check)
        out = _pass(T0 + 330, check)
        assert [r["incident"] for r in out["ready"]] == [d["incident"]], out
        made = DC.run("Default", now=T0 + 331, sources=Fake(R8_AGAIN, intended=GOLDEN))
        assert [x["outcome"] for x in made["decided"]] == ["propose"], made
        (again,) = DS.proposals("Default")
        assert again["id"] != d["id"] and again["departure"] == _dep(R8_AGAIN)

    def test_the_departure_it_was_made_for_keeps_it_waiting_its_read_kept(self, lab):
        d = proposed()
        check = _Check(R8)
        out = _pass(T0 + 121, check)
        assert check.calls == ["edge-b"] and out["withdrawn"] == []
        assert [x["id"] for x in DS.proposals("Default")] == [d["id"]]
        assert _incident()["state"] == "claimed" and _incident()["reads"][-1]["epoch"] == T0 + 121
        _pass(T0 + 150, check)
        assert check.calls == ["edge-b"], "read again only a grace period after its last read"

    def test_not_read_before_it_is_due_unless_a_change_arrives(self, lab):
        d = proposed()
        check = _Check(GOLDEN)
        _pass(T0 + 60, check)
        assert check.calls == [] and DS.proposals("Default")
        I.sight("Default", "edge-b", {"kind": "config_change", "key": "cfg:2", "epoch": T0 + 70,
                                      "at": "x", "attribution": {"by": "outside"},
                                      "words": "CONFIG_I"}, now=T0 + 70)
        out = _pass(T0 + 71, check)
        assert check.calls == ["edge-b"] and [w["decision"] for w in out["withdrawn"]] == [
            d["id"]]

    def test_a_read_that_could_not_be_made_withdraws_nothing(self, lab):
        d = proposed()
        _pass(T0 + 121, _Check(error="timed out"))
        assert [x["id"] for x in DS.proposals("Default")] == [d["id"]]
        assert _incident()["state"] == "claimed"

    def test_a_proposal_a_person_took_first_is_not_withdrawn(self, lab, measured):
        d = proposed()
        approve(d, FakeApproved(R8))
        check = _Check(GOLDEN)
        _pass(T0 + 121, check)
        assert check.calls == [] and not DS.find("Default", d["id"]).get("withdrawn")
        with pytest.raises(DS.Refused, match="so it is not withdrawn"):
            DS.withdraw("Default", d["id"], how="at_intent", by="test", words="w",
                        read={"state": "clean"})
        INT.release("Default", d["id"])

    def test_approving_a_withdrawn_proposal_is_refused_naming_both_states(self, lab, measured):
        d = proposed()
        v = P.view("Default", d["id"], now=T0 + 1, sources=FakeApproved(R8))
        _pass(T0 + 121, _Check(R8_AGAIN))
        later = P.view("Default", d["id"], now=T0 + 122, sources=FakeApproved(R8))
        assert later["withdrawn"]["how"] == "changed" and not later["confirmable"]
        with pytest.raises(P.Refused) as exc:
            P.approve("Default", d["id"], confirmed_hash=v["hash"], reason=REASON,
                      now=T0 + 123, sources=FakeApproved(R8), starter=lambda *a, **k: "j", **WHO)
        said = str(exc.value)
        assert "is no longer waiting" in said and v["hash"] in said
        assert d["departure"] in said and _dep(R8_AGAIN) in said
        assert "withdrawn" in said and DS.find("Default", d["id"])["taken"]["by"] == \
            "heal to intent"


# ── Interrupted ─────────────────────────────────────────────────────────────────────────────

class TestInterrupted:
    def test_an_approval_whose_job_ended_first_is_found_and_recorded(self, lab, measured):
        d = proposed()
        out, ((taken, _approval),), _v = approve(d, FakeApproved(R8))
        assert INT.find("Default")["found"] == [], "its mark is held while its job may run"
        SL.record_started("Default", taken, [{"step": "apply", "result": "running",
                                              "words": "applying"}], taken["program"],
                          taken["program_hash"], by=PERSON, now=T0 + 3)
        INT.release("Default", d["id"])
        (found,) = INT.find("Default")["found"]
        assert found["id"] == d["id"]
        (r,) = INT.reap("Default", now=T0 + 9)["reaped"]
        assert r["halted"] and applied(d["id"])["outcome"] == "interrupted"


# ── The routes ──────────────────────────────────────────────────────────────────────────────

def _bp():
    from routes import heal_proposal_v2

    return heal_proposal_v2


@pytest.fixture
def client(networks, monkeypatch):
    """The routes on a test app of their own (registered on the real app only by H9, with the
    screen that posts them), the gate and invalidation hooks installed with the blueprint's
    own declarations in their tables."""
    from flask import Flask

    from modules import invalidation, route_gates

    monkeypatch.setattr(route_gates, "GATES", dict(route_gates.GATES, **_bp().gates()))
    monkeypatch.setattr(invalidation, "DECLARED",
                        dict(invalidation.DECLARED, **_bp().invalidates()))
    app = Flask(__name__)
    app.register_blueprint(_bp().bp)
    route_gates.install(app)
    invalidation.install(app)
    return app


class TestTheRoutes:
    def _base(self, d):
        return f"/v2/network/Default/heal/proposal/{d['id']}"

    def test_read_approve_and_decline(self, client, lab, measured, monkeypatch):
        from tests.conftest import TEST_PERSON

        d = proposed()
        monkeypatch.setattr("modules.heal.propose.Sources", lambda net: FakeApproved(R8))
        started = []
        monkeypatch.setattr("modules.heal.propose.start",
                            lambda n, taken, approval, **kw: started.append(approval) or "j-1")
        c = client.test_client()
        base = f"/v2/network/Default/heal/proposal/{d['id']}"
        r = c.get(base)
        v = r.get_json()["proposal"]
        assert r.status_code == 200 and v["confirmable"] and v["hash"]
        bad = c.post(base + "/approve", data={"hash": "f" * 16, "reason": REASON})
        assert bad.status_code == 409 and "not the one you confirmed" in bad.get_json()["error"]
        assert [x["id"] for x in DS.proposals("Default")] == [d["id"]], "nothing taken"
        ok = c.post(base + "/approve", data={"hash": v["hash"], "reason": REASON})
        assert ok.status_code == 200 and ok.get_json()["job"] == "j-1"
        assert started[0]["by"] == TEST_PERSON and started[0]["reason"] == REASON
        assert DS.find("Default", d["id"])["taken"]["by"] == f"{TEST_PERSON}: approved"
        INT.release("Default", d["id"])

    def test_decline(self, client, lab):
        d = proposed()
        c = client.test_client()
        short = c.post(self._base(d) + "/decline", data={"reason": "no"})
        assert short.status_code == 409 and "reason" in short.get_json()["error"]
        r = c.post(self._base(d) + "/decline", data={"reason": "not during the lab"})
        assert r.status_code == 200 and r.get_json()["outcome"] == "declined"
        assert "drift" in r.headers["X-NMAS-Invalidates"]
        assert DS.proposals("Default") == []

    def test_an_unknown_proposal_is_404_and_the_read_writes_nothing(self, client, lab):
        before = DS.read("Default")
        r = client.test_client().get("/v2/network/Default/heal/proposal/hd-000000000000")
        assert r.status_code == 404 and "no heal decision" in r.get_json()["error"]
        assert DS.read("Default") == before and before["state"] == "absent", \
            "a read creates no decision store"

    @pytest.mark.real_identity
    def test_an_unverified_caller_is_refused_before_anything(self, client, lab):
        d = proposed()
        for path in ("/approve", "/decline"):
            r = client.test_client().post(self._base(d) + path,
                                          data={"hash": "x", "reason": REASON})
            assert r.status_code in (401, 403), (path, r.status_code)
        assert DS.proposals("Default")


class TestTheDeclarations:
    """What H9 places in the tables, held to the tables' own checks here."""

    def _mutating(self, app):
        from modules.route_gates import SAFE_METHODS

        return {r.endpoint for r in app.url_map.iter_rules()
                if set(r.methods or ()) - SAFE_METHODS - {"HEAD", "OPTIONS"}
                and r.endpoint != "static"}

    def test_every_mutating_route_is_gated_and_declared_once(self, client):
        from modules.route_gates import NOT_DEVICE

        mutating = self._mutating(client)
        assert mutating == set(_bp().gates()) == set(_bp().invalidates())
        assert {k: g.kind for k, g in _bp().gates().items()} == {
            "heal_proposal_v2.approve": "confirm", "heal_proposal_v2.decline": "configure",
            "heal_proposal_v2.lift": "configure", "heal_proposal_v2.mark": "configure"}
        assert all(g.reason and g.kind != NOT_DEVICE for g in _bp().gates().values())

    def test_the_invalidations_are_in_the_vocabulary(self):
        from modules import invalidation

        for v in _bp().invalidates().values():
            if isinstance(v, invalidation.Nothing):
                assert len(v.reason) >= 30
            else:
                assert set(v) <= set(invalidation.VOCABULARY), v

    def test_the_stages_resolve_as_the_table_s_test_resolves_them(self, client):
        from tests.test_operation_stages import problems

        gated = {e for e, g in _bp().gates().items() if g.kind in ("confirm", "approve")}
        assert problems(_bp().stages(), client, gated) == []

    def test_the_history_names_registered_sources(self):
        from modules import history_sources

        for sources in _bp().history().values():
            if isinstance(sources, str):
                # A network's record, not a device's (Lift the halt, C2471), says why.
                assert sources.startswith("n/a: ") and len(sources) > 30, sources
                continue
            assert set(sources) <= set(history_sources.SOURCES), sources

    def test_not_registered_on_the_app_until_h9_draws_its_screen(self):
        """The property both ways (C2448): while artboard E's screen is undrawn (its fidelity
        record absent) the routes are not the app's; once H9 drew it (the record exists) the
        three are registered and their declarations are in the tables."""
        import os

        import app as A

        from modules import invalidation, operation_stages, route_gates

        drawn = os.path.exists(os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "docs", "fidelity", "heal-proposal.md"))
        registered = {r.endpoint for r in A.app.url_map.iter_rules()
                      if r.endpoint.startswith("heal_proposal_v2.")}
        if not drawn:
            assert not registered
            return
        assert registered == {
            "heal_proposal_v2.proposal", "heal_proposal_v2.approve", "heal_proposal_v2.decline",
            "heal_proposal_v2.lift", "heal_proposal_v2.mark",
            # C2773: the change record's download, a read on the same blueprint.
            "heal_proposal_v2.change_record_md"}
        assert set(_bp().gates()) <= set(route_gates.GATES)
        assert set(_bp().invalidates()) <= set(invalidation.DECLARED)
        assert set(_bp().stages()) <= set(operation_stages.STAGES)
        assert set(_bp().history()) <= set(operation_stages.HISTORY)

    def test_history_draws_who_approved(self, lab, measured):
        from modules import history_sources as HS

        d = proposed()
        run_approved(d, FakeApproved(R8))
        out = HS.heal({"ref": types.SimpleNamespace(name="Default"), "device": "", "limit": 50,
                       "since": None, "until": None, "members": None, "inventory": set()})
        (e,) = out["events"]
        assert e["who"] == PERSON
        assert dict(e["record"])["Approval"].startswith(f"approved by {PERSON} (access)")
